"""Pick the contract subset, reproducibly. The rule is written out in
data/SELECTION.md; this is that rule in code.

    python scripts/select_contracts.py                 # needs data/derived/accounts.json and revenue.json
    python scripts/select_contracts.py --provisional   # no EDGAR data yet: every candidate in the lowest tier

Writes data/selection.json (committed: ids and titles only, no contract text)
and prints the tier counts and the match rate.
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.cuad import COMMERCIAL_TYPES, METADATA_CATEGORIES, load_contracts  # noqa: E402

SEED = 20260923
TARGET = 80
PER_TYPE_CAP = 15
MIN_CLAUSE_SPANS = 3
DERIVED = ROOT / "data" / "derived"
TIERS = ("A: account resolved, revenue series", "B: account resolved, no revenue", "C: unresolved")


def candidates(contracts):
    out = []
    for c in contracts:
        if c["contract_type"] not in COMMERCIAL_TYPES:
            continue
        clause_cats = {s["category"] for s in c["spans"] if s["category"] not in METADATA_CATEGORIES}
        if len(clause_cats) < MIN_CLAUSE_SPANS:
            continue
        out.append(c)
    return out


def tier_of(c, accounts, revenue):
    a = accounts.get(c["id"])
    if not a or not a.get("cik"):
        return 2
    return 0 if revenue.get(a["cik"]) else 1


def select(cands, accounts, revenue, *, seed=SEED, target=TARGET, cap=PER_TYPE_CAP):
    rng = random.Random(seed)
    tiers = [[], [], []]
    for c in sorted(cands, key=lambda c: c["id"]):
        tiers[tier_of(c, accounts, revenue)].append(c)
    chosen, per_type = [], Counter()
    for t, group in enumerate(tiers):
        rng.shuffle(group)
        for c in group:
            if len(chosen) >= target:
                break
            if per_type[c["contract_type"]] >= cap:
                continue
            per_type[c["contract_type"]] += 1
            chosen.append((t, c))
    return chosen, tiers


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provisional", action="store_true", help="select without EDGAR data (marked provisional)")
    args = ap.parse_args(argv)
    acc_path, rev_path = DERIVED / "accounts.json", DERIVED / "revenue.json"
    if acc_path.exists() and rev_path.exists():
        accounts = {a["contract_id"]: a for a in json.loads(acc_path.read_text(encoding="utf-8"))}
        revenue = {r["cik"]: bool(r["rows"]) for r in json.loads(rev_path.read_text(encoding="utf-8"))}
        provisional = False
    elif args.provisional:
        accounts, revenue, provisional = {}, {}, True
    else:
        print("no EDGAR data: run scripts/ingest_edgar.py first, or pass --provisional")
        return 1
    cands = candidates(load_contracts())
    chosen, tiers = select(cands, accounts, revenue)
    resolved = sum(1 for t, _ in chosen if t < 2)
    out = {"seed": SEED, "target": TARGET, "per_type_cap": PER_TYPE_CAP, "min_clause_categories": MIN_CLAUSE_SPANS,
           "provisional": provisional, "candidates": len(cands),
           "candidate_tiers": {TIERS[i]: len(g) for i, g in enumerate(tiers)},
           "selected_tiers": {TIERS[i]: sum(1 for t, _ in chosen if t == i) for i in range(3)},
           "match_rate_selected": round(resolved / max(len(chosen), 1), 4),
           "by_type": dict(Counter(c["contract_type"] for _, c in chosen).most_common()),
           "contracts": [{"id": c["id"], "title": c["title"], "contract_type": c["contract_type"], "tier": TIERS[t]}
                         for t, c in sorted(chosen, key=lambda p: (p[0], p[1]["id"]))]}
    (ROOT / "data" / "selection.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "contracts"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
