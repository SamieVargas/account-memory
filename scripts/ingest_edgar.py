"""EDGAR ingest for the CUAD candidates: resolve each filer and party to a
CIK, link the parent filing, pull Item 1A from the 10-K nearest the
contract, and build the revenue table. Everything goes through the cached,
rate-limited client in core/edgar.py.

    EDGAR_USER_AGENT="Name email" python scripts/ingest_edgar.py
    python scripts/ingest_edgar.py --offline     # cache only, sends nothing

Writes (all git-ignored except the review file and the report):
    data/derived/accounts.json       per contract: account, CIK, method, parent filing, 10-K link
    data/derived/risk_factors.json   Item 1A text per (CIK, accession), successes only
    data/derived/revenue.json        the revenue table, one row per company and fiscal year
    data/cik_review.csv              borderline name matches for a person to confirm
    evals/results/ingest-edgar-<date>.md

Scope is the commercial candidates (core.cuad.COMMERCIAL_TYPES), since the
selection prefers the ones that resolve; see data/SELECTION.md.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from core import edgar as E  # noqa: E402
from core.cuad import COMMERCIAL_TYPES, load_contracts  # noqa: E402

DERIVED = ROOT / "data" / "derived"
REVIEW = ROOT / "data" / "cik_review.csv"
REVIEW_FIELDS = ("contract_id", "name", "candidate_cik", "candidate_name", "method", "score", "confirmed")


def read_review(path=None) -> list[dict]:
    path = path or REVIEW
    if not path.exists():
        return []
    return [dict(r) for r in csv.DictReader(path.open(encoding="utf-8"))]


def _decision(row) -> str:
    return (row.get("confirmed") or "").strip().lower()


def decided_rows(rows) -> list[dict]:
    """Rows a person marked yes or no. They are kept exactly as written."""
    return [r for r in rows if _decision(r) in ("yes", "no")]


def read_confirmed(rows=None) -> dict:
    """Name -> (cik, matched name) for a candidate marked yes, or None when
    every candidate for that name is marked no. A yes wins over any no; a
    name with some candidates still blank is left to resolve again."""
    rows = read_review() if rows is None else rows
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r)
    out = {}
    for name, rs in by_name.items():
        yes = [r for r in rs if _decision(r) == "yes"]
        if yes:
            out[name] = (int(yes[0]["candidate_cik"]), yes[0]["candidate_name"])
        elif all(_decision(r) == "no" for r in rs):
            out[name] = None
    return out


def merge_review(previous: list[dict], new_candidates: list[dict]) -> list[dict]:
    """Decided rows from `previous`, unchanged, then one blank row per new
    (name, candidate) pair that is not already decided. Blank rows from an
    earlier run are regenerated from this run's candidates, not carried."""
    kept = decided_rows(previous)
    seen = {(r["name"], str(r["candidate_cik"])) for r in kept}
    out = list(kept)
    for r in new_candidates:
        key = (r["name"], str(r["cik"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"contract_id": r["contract_id"], "name": r["name"], "candidate_cik": r["cik"], "candidate_name": r["matched_name"],
                    "method": r["method"], "score": r["score"], "confirmed": ""})
    return out


def resolve_contract(c, tickers, lookup, confirmed):
    names = [n for n in dict.fromkeys([c["filer"], c.get("title_filer")] + c["metadata"]["parties"]["value"]) if n]
    results, review = [], []
    for n in names:
        if n in confirmed:
            hit = confirmed[n]
            results.append({"name": n, "cik": hit[0] if hit else None, "matched_name": hit[1] if hit else None,
                            "method": "manual_review" if hit else "unresolved"})
            continue
        r = E.resolve_name(n, tickers, lookup)
        results.append(r)
        review += [{"contract_id": c["id"], **x} for x in r.get("review", [])]
    account = next((r for r in results if r["cik"]), None)
    return results, account, review


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="read the cache only; fail on anything uncached")
    ap.add_argument("--limit", type=int, default=None, help="first N candidates, for a smoke run")
    ap.add_argument("--cache-dir", default=str(E.CACHE), help="response cache (default data/cache/edgar)")
    args = ap.parse_args(argv)

    client = E.EdgarClient(offline=args.offline, cache_dir=args.cache_dir)
    contracts = [c for c in load_contracts() if c["contract_type"] in COMMERCIAL_TYPES][: args.limit]
    tickers = E.NameIndex(E.load_tickers(client))
    lookup = E.NameIndex(E.load_cik_lookup(client))
    previous_review = read_review()
    confirmed = read_confirmed(previous_review)

    accounts, review_rows, risk, revenue = [], [], {}, {}
    methods, item1a, parents = Counter(), Counter(), Counter()
    fail_reasons = Counter()
    filings_cache = {}
    errors, no_10k = [], Counter()
    for c in contracts:
        results, account, review = resolve_contract(c, tickers, lookup, confirmed)
        review_rows += review
        for r in results:
            methods[r["method"]] += 1
        rec = {"contract_id": c["id"], "title": c["title"], "resolutions": results, "account": None, "cik": None,
               "parent_filing": None, "ten_k": None}
        accounts.append(rec)
        if not account:
            continue
        cik = account["cik"]
        rec.update(account=account["matched_name"], cik=cik, account_method=account["method"])
        try:
            if cik not in filings_cache:
                filings_cache[cik] = E.filings(client, cik)
            rows = filings_cache[cik]
            pf = E.parent_filing(rows, c["filing_date"], c["form"])
            rec["parent_filing"] = pf
            parents[pf["status"]] += 1
            when = c["metadata"]["agreement_date"]["value"] or c["filing_date"]
            tk = E.nearest_10k(rows, when) if when else None
            if not tk:
                reason = E.ten_k_gap_reason(rows) if when else "no agreement or filing date to match a 10-K to"
                rec["ten_k"] = {"skipped": reason}
                no_10k[reason] += 1
            else:
                key = f"{cik}:{tk['accessionNumber']}"
                if key not in risk:
                    if not tk.get("primaryDocument"):
                        ex = {"ok": False, "reason": "the filing index names no primary document"}
                    else:
                        body = client.get(E.archive_url(cik, tk["accessionNumber"], tk["primaryDocument"]))
                        ex = E.extract_item_1a(E.html_to_text(body.decode("utf-8", "replace"))) if body else {"ok": False, "reason": "document not found"}
                    risk[key] = {"cik": cik, "accession": tk["accessionNumber"], "filing_date": tk["filingDate"], "form": tk["form"], **ex}
                    item1a["succeeded" if ex["ok"] else "failed"] += 1
                    if not ex["ok"]:
                        fail_reasons[ex["reason"]] += 1
                rec["ten_k"] = {"accession": tk["accessionNumber"], "filing_date": tk["filingDate"], "gap_days": tk["gap_days"],
                                "item_1a_ok": risk[key]["ok"], "dated_from": "agreement_date" if c["metadata"]["agreement_date"]["value"] else "filing_date"}
            if cik not in revenue:
                revenue[cik] = E.revenue_series(client.json(E.FACTS_URL.format(cik=cik)), cik)
        except E.EdgarBlocked:
            raise
        except (E.EdgarUnavailable, OSError, ValueError) as e:
            # one contract's failure is recorded, and the run goes on; a rerun retries it (the cache keeps the rest)
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            errors.append((c["title"], rec["error"]))

    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "accounts.json").write_text(json.dumps(accounts, indent=1), encoding="utf-8")
    (DERIVED / "risk_factors.json").write_text(json.dumps([v for v in risk.values() if v["ok"]], indent=1), encoding="utf-8")
    (DERIVED / "revenue.json").write_text(json.dumps(list(revenue.values()), indent=1), encoding="utf-8")
    merged_review = merge_review(previous_review, review_rows)
    with REVIEW.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged_review)
    n_decided = len(decided_rows(previous_review))

    resolved = [a for a in accounts if a["cik"]]
    with_rev = [r for r in revenue.values() if r["rows"]]
    concepts = Counter(c for r in with_rev for c in r["concepts_used"])
    lines = [f"# EDGAR ingest, {date.today().isoformat()}", "",
             f"Candidates: {len(contracts)} commercial contracts. Client: {client.stats['requests']} requests, "
             f"{client.stats['cache_hits']} cache hits, rate {E.RATE}/s.", "",
             "| Measure | n |", "| --- | --- |",
             f"| Contracts with a resolved account | {len(resolved)} of {len(contracts)} ({len(resolved) / max(len(contracts), 1):.0%}) |",
             *[(f"| Names unresolved | {n} |" if m == "unresolved" else f"| Names resolved by {m} | {n} |") for m, n in sorted(methods.items())],
             f"| data/cik_review.csv: decided rows kept / new rows to review | {n_decided} / {len(merged_review) - n_decided} |",
             *[f"| Parent filing {s} | {n} |" for s, n in sorted(parents.items())],
             f"| 10-Ks fetched | {sum(item1a.values())} |",
             f"| Item 1A extractions succeeded / failed | {item1a['succeeded']} / {item1a['failed']} |",
             *[f"| Contracts with no 10-K to use: {r} | {n} |" for r, n in no_10k.most_common()],
             f"| Contracts that hit an error (rerun to retry) | {len(errors)} |",
             f"| Companies with a revenue series | {len(with_rev)} of {len(revenue)} |",
             *[f"| Revenue concept used: {c} | {n} companies |" for c, n in concepts.most_common()],
             "", "## Item 1A failures", "", *[f"- {r}: {n}" for r, n in fail_reasons.most_common()],
             "", "## Errors", "", *[f"- {t}: {e}" for t, e in errors],
             "", "## Unresolved contracts", "", *[f"- {a['title']}" for a in accounts if not a["cik"]]]
    out = ROOT / "evals" / "results" / f"ingest-edgar-{date.today().isoformat()}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:20]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
