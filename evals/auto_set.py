"""The automatic retrieval set (Part 4): no model call, no cost.

For every (contract, category) pair in the index with a gold span, the query
is CUAD's own question text for that category. Each query runs twice:
scoped to its contract with a metadata filter, and corpus-wide with every
other contract and every Item 1A chunk as distractors.

    python evals/auto_set.py --chunker section --mode dense
    python evals/auto_set.py --chunker section --mode hybrid
    python evals/auto_set.py --chunker section --mode hybrid --rerank cross-encoder

recall@k is the share of a query's gold spans that some top-k chunk from the
same contract overlaps; MRR is 1 / the rank of the first chunk that overlaps
any of them. Both are averaged over queries, and n is printed with them.

Refuses to run until evals/golden.jsonl exists and data/playbook.md has
positions: the brief puts both before any retrieval run. The results carry
their hashes.
"""

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import store as S  # noqa: E402
from core.chunking import CHUNKERS  # noqa: E402
from core.cuad import METADATA_CATEGORIES, load_contracts, load_release, questions  # noqa: E402
from core.docs import positions_written  # noqa: E402
from core.embeddings import ARMS, DEFAULT, make_embedding_function, over_limit  # noqa: E402
from core.retrieve import BM25, MODES, search  # noqa: E402

KS = (3, 5, 10)
GOLDEN = ROOT / "evals" / "golden.jsonl"
PLAYBOOK = ROOT / "data" / "playbook.md"


def file_hash(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None


def preconditions() -> list[str]:
    problems = []
    if not GOLDEN.exists():
        problems.append("evals/golden.jsonl does not exist yet: write and freeze the golden set first")
    if not positions_written(PLAYBOOK.read_text(encoding="utf-8")):
        problems.append("data/playbook.md has no positions yet: write the playbook first")
    return problems


def build_queries(records: list[dict], qtext: dict, contract_ids) -> list[dict]:
    out = []
    for r in records:
        if r["id"] not in contract_ids:
            continue
        by_cat = {}
        for s in r["spans"]:
            if s["category"] not in METADATA_CATEGORIES:
                by_cat.setdefault(s["category"], []).append(s)
        for cat, spans in sorted(by_cat.items()):
            out.append({"contract_id": r["id"], "category": cat, "query": qtext[cat], "gold": spans})
    return out


def score(hits: list[dict], contract_id: str, gold: list[dict], ks=KS) -> dict:
    def cov(h, s):
        return h["doc_id"] == contract_id and h["start"] < s["end"] and s["start"] < h["end"]
    out = {"recall": {}, "mrr": 0.0}
    for k in ks:
        top = hits[:k]
        out["recall"][str(k)] = round(sum(1 for s in gold if any(cov(h, s) for h in top)) / len(gold), 4)
    for rank, h in enumerate(hits, start=1):
        if any(cov(h, s) for s in gold):
            out["mrr"] = round(1 / rank, 4)
            break
    return out


def run(queries, *, collection, bm25, mode, reranker=None, ks=KS) -> dict:
    kmax = max(ks)
    rows = []
    for q in queries:
        row = {"contract_id": q["contract_id"], "category": q["category"], "n_gold": len(q["gold"])}
        for scope, filters in (("scoped", {"contract_id": q["contract_id"]}), ("corpus", None)):
            res = search(q["query"], collection=collection, bm25=bm25, k=kmax, mode=mode, filters=filters, reranker=reranker)
            row[scope] = score(res["hits"], q["contract_id"], q["gold"], ks)
            row[scope]["wrong_doc_type"] = sum(1 for h in res["hits"][:5] if h["doc_type"] != "contract")
            row[scope]["latency_ms"] = res["latency_ms"]
        rows.append(row)
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
    summary = {"n": len(rows)}
    for scope in ("scoped", "corpus"):
        summary[scope] = {"recall": {str(k): mean([r[scope]["recall"][str(k)] for r in rows]) for k in ks},
                          "mrr": mean([r[scope]["mrr"] for r in rows]),
                          "wrong_doc_type_in_top5": sum(r[scope]["wrong_doc_type"] for r in rows),
                          "mean_latency_ms": mean([r[scope]["latency_ms"] for r in rows])}
    return {"summary": summary, "rows": rows}


def render(meta, summary) -> str:
    ol = meta.get("over_limit")
    trunc = (f"{ol[0]} of {ol[1]} indexed chunks ({ol[0] / ol[1]:.0%}) are longer than the embedding model reads, so their dense "
             "vectors cover only the start of the chunk." if ol and ol[1] else "Truncation not counted (no limit, or tokenizer not on disk).")
    lines = [f"# Automatic retrieval set, {meta['date']}", "",
             f"Chunker {meta['chunker']}, mode {meta['mode']}, reranker {meta['reranker'] or 'none'}, embedding {meta['embedding_model']}, "
             f"n = {summary['n']} (contract, category) queries over {meta['contracts']} contracts. "
             f"Golden set {meta['golden_hash']}, playbook {meta['playbook_hash']}.", "",
             *([trunc, ""] if meta["mode"] != "bm25" else []),
             "| Scope | recall@3 | recall@5 | recall@10 | MRR | non-contract chunks in top 5 | mean ms |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for scope in ("scoped", "corpus"):
        s = summary[scope]
        lines.append(f"| {scope} | {s['recall']['3']:.1%} | {s['recall']['5']:.1%} | {s['recall']['10']:.1%} | {s['mrr']:.3f} | "
                     f"{s['wrong_doc_type_in_top5']} | {s['mean_latency_ms']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunker", choices=CHUNKERS, default="section")
    ap.add_argument("--mode", choices=MODES, default="dense")
    ap.add_argument("--hybrid", action="store_true", help="shorthand for --mode hybrid")
    ap.add_argument("--rerank", choices=("none", "lexical", "cross-encoder"), default="none")
    ap.add_argument("--embedding", choices=list(ARMS), default=DEFAULT)
    ap.add_argument("--db", default=str(S.DEFAULT_DB))
    ap.add_argument("--out", default=str(ROOT / "evals" / "results"))
    args = ap.parse_args(argv)
    mode = "hybrid" if args.hybrid else args.mode
    problems = preconditions()
    if problems:
        print("not running:\n" + "\n".join(f"- {p}" for p in problems))
        return 2
    ef, model = make_embedding_function(args.embedding)
    collection = S.make_client(args.db).get_collection(S.collection_name(args.chunker), **({"embedding_function": ef} if ef else {}))
    mismatch = S.version_mismatch(collection, args.chunker, model)
    if mismatch:
        print("the index was built by different code or a different model; run ingest.py first:\n" + "\n".join(mismatch))
        return 2
    manifest = S.read_manifest(args.db, args.chunker)
    contract_ids = {k for k, v in manifest["docs"].items() if v["doc_type"] == "contract"}
    queries = build_queries(load_contracts(), questions(load_release()), contract_ids)
    chunks = S.read_chunks(args.db, args.chunker)
    bm25 = BM25(chunks) if mode != "dense" else None
    from core.rerank import make_reranker
    reranker = make_reranker(None if args.rerank == "none" else args.rerank)
    result = run(queries, collection=collection, bm25=bm25, mode=mode, reranker=reranker)
    meta = {"date": date.today().isoformat(), "chunker": args.chunker, "mode": mode, "reranker": getattr(reranker, "name", None),
            "embedding_model": model, "contracts": len(contract_ids), "golden_hash": file_hash(GOLDEN), "playbook_hash": file_hash(PLAYBOOK),
            "over_limit": over_limit((c["text"] for c in chunks), args.embedding)}
    stem = f"{meta['date']}-auto-{args.chunker}-{mode}" + (f"-{args.rerank}" if reranker else "")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / f"{stem}.md").write_text(render(meta, result["summary"]), encoding="utf-8")
    (Path(args.out) / f"{stem}.json").write_text(json.dumps({"meta": meta, **result}, indent=1), encoding="utf-8")
    print(render(meta, result["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
