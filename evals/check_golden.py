"""Validate evals/golden.jsonl against evals/GOLDEN.md. Reads data only
(no retriever, no embedder). Prints every problem and exits 1 if there is
any, 0 otherwise.

    python evals/check_golden.py [path/to/golden.jsonl]
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import golddata as G  # noqa: E402
from core import runlog  # noqa: E402
from core.cuad import CATEGORIES  # noqa: E402

GOLDEN = ROOT / "evals" / "golden.jsonl"
MIX = {"clause": 10, "filing": 6, "filter": 7, "aggregate": 7, "playbook_check": 5, "unanswerable": 5}
MIN_REVENUE_AGGREGATES = 3
MIN_CROSS_DOC_PLAYBOOK = 1
VERDICTS = ("matches", "deviates", "unclear")
FIELDS = {"id": str, "kind": str, "question": str, "scope": dict, "gold_passages": list, "gold_rows": list,
          "expected_contract_ids": list, "expected_facts": list, "expected_verdict": (str, type(None)), "notes": str}


def load_sources():
    """What the checks look things up in; missing EDGAR outputs are empty."""
    try:
        records = {r["id"]: r for r in G.selected_records()}
        selection_problem = None
    except SystemExit as e:
        records, selection_problem = {}, str(e)
    return {"records": records, "selection_problem": selection_problem,
            "risk": {e["doc_id"]: e for e in G.risk_entries()},
            "revenue": {r["row_id"] for r in G.revenue_rows()},
            "playbook": G.playbook_text()}


def doc_text(doc_id, src):
    if doc_id in src["records"]:
        return "contract", src["records"][doc_id]["text"]
    if doc_id in src["risk"]:
        return "risk_factors", src["risk"][doc_id]["text"]
    if doc_id == "playbook":
        return "playbook", src["playbook"]
    return None, None


def check_line(q: dict, src: dict) -> list[str]:
    p = []
    for f, t in FIELDS.items():
        if f not in q:
            p.append(f"missing field {f}")
        elif not isinstance(q[f], t):
            p.append(f"{f} has the wrong type")
    if p:
        return p
    kind = q["kind"]
    if kind not in MIX:
        return [f"unknown kind {kind!r}"]
    if not q["question"].strip():
        p.append("empty question")

    scope_cid = q["scope"].get("contract_id")
    if scope_cid and scope_cid not in src["records"]:
        p.append(f"scope.contract_id {scope_cid} is not in the selection")
    for cid in q["expected_contract_ids"]:
        if cid not in src["records"]:
            p.append(f"expected contract {cid} is not in the selection")

    types = set()
    for i, gp in enumerate(q["gold_passages"]):
        where = f"gold_passages[{i}]"
        if not isinstance(gp, dict) or not {"doc_id", "start", "end"} <= set(gp):
            p.append(f"{where} needs doc_id, start and end")
            continue
        dtype, text = doc_text(gp["doc_id"], src)
        if dtype is None:
            p.append(f"{where}: {gp['doc_id']} is not a selected contract, an extracted Item 1A, or the playbook")
            continue
        types.add(dtype)
        s, e = gp["start"], gp["end"]
        if not (isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= len(text)):
            p.append(f"{where}: offsets [{s}, {e}) are outside 0..{len(text)} or empty")
            continue
        if kind == "clause":
            cat = gp.get("category")
            if dtype != "contract":
                p.append(f"{where}: a clause passage must be in a contract")
            elif cat not in CATEGORIES:
                p.append(f"{where}: category {cat!r} is not a CUAD category")
            elif not any(sp["category"] == cat and sp["start"] < e and s < sp["end"] for sp in src["records"][gp["doc_id"]]["spans"]):
                p.append(f"{where}: [{s}, {e}) overlaps no CUAD span of {cat}")
        if kind == "filing" and dtype != "risk_factors":
            p.append(f"{where}: a filing passage must be in an Item 1A extraction")

    for rid in q["gold_rows"]:
        if rid not in src["revenue"]:
            p.append(f"revenue row {rid} does not exist")

    if kind == "clause":
        if not q["gold_passages"]:
            p.append("a clause question needs gold passages")
        texts = [G.normalize(doc_text(gp["doc_id"], src)[1][gp["start"]:gp["end"]]) for gp in q["gold_passages"]
                 if isinstance(gp, dict) and doc_text(gp.get("doc_id"), src)[1] is not None]
        for fact in q["expected_facts"]:
            if not any(G.normalize(str(fact)) in t for t in texts):
                p.append(f"expected fact {fact!r} is not inside any gold passage")
    if kind == "filing" and not q["gold_passages"]:
        p.append("a filing question needs gold passages")
    if kind == "filter" and not q["expected_contract_ids"]:
        p.append("a filter question needs expected_contract_ids")
    if kind == "aggregate" and not q["expected_facts"]:
        p.append("an aggregate question needs expected_facts")
    if kind == "playbook_check":
        if q["expected_verdict"] not in VERDICTS:
            p.append(f"expected_verdict must be one of {', '.join(VERDICTS)}")
        if not q["gold_passages"]:
            p.append("a playbook_check needs gold passages (the clause and the playbook position)")
    elif q["expected_verdict"] is not None:
        p.append("only playbook_check questions carry an expected_verdict")
    if kind == "unanswerable" and (q["gold_passages"] or q["gold_rows"] or q["expected_contract_ids"]):
        p.append("an unanswerable question has no gold passages, rows or contracts")
    q["_doc_types"] = types
    return p


def check(path: Path = GOLDEN) -> list[str]:
    path = Path(path)
    if not path.exists():
        return [f"{path} does not exist"]
    src = load_sources()
    problems = [src["selection_problem"]] if src["selection_problem"] else []
    questions, ids = [], Counter()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"line {n}: not JSON ({e.msg})")
            continue
        if not isinstance(q, dict):
            problems.append(f"line {n}: not an object")
            continue
        label = f"line {n} ({q.get('id', '?')})"
        problems += [f"{label}: {x}" for x in check_line(q, src)]
        ids[q.get("id")] += 1
        questions.append(q)
    problems += [f"id {i!r} appears {c} times" for i, c in ids.items() if c > 1]
    kinds = Counter(q.get("kind") for q in questions)
    for kind, want in MIX.items():
        if kinds[kind] != want:
            problems.append(f"mix: {kinds[kind]} {kind} questions, expected {want}")
    rev = sum(1 for q in questions if q.get("kind") == "aggregate" and q.get("gold_rows"))
    if rev < MIN_REVENUE_AGGREGATES:
        problems.append(f"mix: {rev} aggregate questions cite revenue rows, expected at least {MIN_REVENUE_AGGREGATES}")
    cross = sum(1 for q in questions if q.get("kind") == "playbook_check" and (q.get("gold_rows") or "risk_factors" in q.get("_doc_types", ())))
    if cross < MIN_CROSS_DOC_PLAYBOOK:
        problems.append(f"mix: {cross} cross-document playbook checks, expected at least {MIN_CROSS_DOC_PLAYBOOK}")
    return problems


def main(argv=None):
    path = Path((argv or sys.argv[1:] or [str(GOLDEN)])[0])
    problems = check(path)
    for x in problems:
        print(x)
    print(f"{len(problems)} problem{'s' if len(problems) != 1 else ''} in {path}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(runlog.run(main, "check_golden"))
