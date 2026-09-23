"""Look things up while writing evals/golden.jsonl. Reads data only: it
never imports the retriever or an embedder, so using it is not a retrieval
run and does not break the golden-set-first rule.

    python scripts/golden_helper.py contracts [--candidates]
    python scripts/golden_helper.py spans <contract_id> [category]
    python scripts/golden_helper.py find <contract_id> "<phrase>"
    python scripts/golden_helper.py revenue [cik]
    python scripts/golden_helper.py risk <cik> "<phrase>"
    python scripts/golden_helper.py metadata-table [--candidates] > metadata.csv

Offsets are [start, end) into the text exactly as the pipeline loads it,
so they can go straight into gold_passages. `find` matches the phrase's
words with any whitespace between them, case-insensitively, and prints the
text it matched.
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import golddata as G  # noqa: E402

CONTEXT = 60


def _one_line(s: str) -> str:
    return " ".join(s.split())


def _record(cid: str, candidates=False) -> dict:
    for r in G.selected_records(candidates):
        if r["id"] == cid:
            return r
    raise SystemExit(f"{cid} is not in the {'candidates' if candidates else 'selection'}")


def cmd_contracts(args, out):
    accts = G.accounts()
    w = csv.writer(out, delimiter="\t", lineterminator="\n")
    w.writerow(["id", "filer", "account", "cik", "contract_type", *G.META_FIELDS, "clause_categories_with_spans"])
    for r in sorted(G.selected_records(args.candidates), key=lambda r: r["id"]):
        a = accts.get(r["id"], {})
        w.writerow([r["id"], r["filer"] or "", a.get("account") or "", a.get("cik") or "", r["contract_type"],
                    *[G.parsed(r, f) or "" for f in G.META_FIELDS], "; ".join(G.clause_categories(r))])


def cmd_spans(args, out):
    r = _record(args.contract_id, args.candidates)
    spans = [s for s in r["spans"] if not args.category or s["category"].lower() == args.category.lower()]
    if not spans:
        print(f"no spans{' for ' + args.category if args.category else ''} in {r['id']}", file=out)
    for s in spans:
        print(f"{s['category']}\t{s['start']}\t{s['end']}\t{_one_line(r['text'][s['start']:s['end']])}", file=out)


def _print_hits(text, hits, out, prefix=""):
    if not hits:
        print(f"{prefix}not found", file=out)
    for s, e in hits:
        before = _one_line(text[max(0, s - CONTEXT):s])
        after = _one_line(text[e:e + CONTEXT])
        print(f"{prefix}{s}\t{e}\t{_one_line(text[s:e])}\t…{before} [[{_one_line(text[s:e])}]] {after}…", file=out)


def cmd_find(args, out):
    r = _record(args.contract_id, args.candidates)
    _print_hits(r["text"], G.find(r["text"], args.phrase), out)


def cmd_revenue(args, out):
    w = csv.writer(out, delimiter="\t", lineterminator="\n")
    w.writerow(["row_id", "cik", "entity", "fiscal_year_end", "revenue_usd", "concept", "filed"])
    rows = [r for r in G.revenue_rows() if args.cik is None or int(r["cik"]) == int(args.cik)]
    if not rows:
        print("no revenue rows" + (f" for CIK {args.cik}" if args.cik else "") + " (has scripts/ingest_edgar.py run?)", file=sys.stderr)
    for r in rows:
        w.writerow([r["row_id"], r["cik"], r.get("entity") or "", r["fiscal_year_end"], r["revenue_usd"], r["concept"], r["filed"]])


def cmd_risk(args, out):
    entries = [e for e in G.risk_entries() if int(e["cik"]) == int(args.cik)]
    if not entries:
        print(f"no Item 1A extraction for CIK {args.cik}", file=out)
    for e in entries:
        _print_hits(e["text"], G.find(e["text"], args.phrase), out, prefix=f"{e['doc_id']}\t")


def cmd_metadata_table(args, out):
    accts = G.accounts()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["contract_id", "filer", "account", "cik", "contract_type", *G.META_FIELDS])
    for r in sorted(G.selected_records(args.candidates), key=lambda r: r["id"]):
        a = accts.get(r["id"], {})
        w.writerow([r["id"], r["filer"] or "", a.get("account") or "", a.get("cik") or "", r["contract_type"],
                    *[G.parsed(r, f) or "" for f in G.META_FIELDS]])


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("contracts", "metadata-table"):
        p = sub.add_parser(name)
        p.add_argument("--candidates", action="store_true", help="every commercial candidate, before the selection exists")
    p = sub.add_parser("spans")
    p.add_argument("contract_id")
    p.add_argument("category", nargs="?")
    p.add_argument("--candidates", action="store_true")
    p = sub.add_parser("find")
    p.add_argument("contract_id")
    p.add_argument("phrase")
    p.add_argument("--candidates", action="store_true")
    p = sub.add_parser("revenue")
    p.add_argument("cik", nargs="?")
    p = sub.add_parser("risk")
    p.add_argument("cik")
    p.add_argument("phrase")
    args = ap.parse_args(argv)
    {"contracts": cmd_contracts, "spans": cmd_spans, "find": cmd_find, "revenue": cmd_revenue, "risk": cmd_risk,
     "metadata-table": cmd_metadata_table}[args.cmd](args, out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # piped into head
        sys.stderr.close()
        sys.exit(0)
