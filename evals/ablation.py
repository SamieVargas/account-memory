"""Part 6: the retrieval ablation on the automatic set, in one command.

    python evals/ablation.py                       # every arm, both chunkers
    python evals/ablation.py --chunker section     # one chunker
    python evals/ablation.py --arms minilm,bge-small

Embedding arms: each builds its own index (chroma_db/arms/<arm>, incremental
like the main one) and runs dense retrieval. Retrieval arms, on each
embedding: dense, hybrid (BM25 + dense, RRF), and hybrid + cross-encoder
(retrieve 20, keep the top k). An arm that cannot load here (a missing
package, a model that will not download) is a row that says "not run" and
why, never a silent gap.

Every row carries n, the embedding model, the date, and the share of chunks
longer than the model reads. Same preconditions as evals/auto_set.py.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

import auto_set as AS  # noqa: E402
from core import store as S  # noqa: E402
from core.chunking import CHUNKERS  # noqa: E402
from core.cuad import load_contracts, load_release, questions  # noqa: E402
from core.embeddings import ARMS, make_embedding_function, over_limit  # noqa: E402
from core.rerank import make_reranker  # noqa: E402
from core.retrieve import BM25  # noqa: E402

EMBEDDING_ARMS = ("minilm", "bge-small", "e5-small")
RETRIEVAL_ARMS = (("dense", None), ("hybrid", None), ("hybrid", "cross-encoder"))


def run_arm(arm, chunker, docs, queries_for, db_root, retrieval_arms=RETRIEVAL_ARMS, rerankers=None):
    """Rows for one embedding arm and one chunker."""
    model = ARMS[arm]["model"]
    try:
        ef, _ = make_embedding_function(arm)
    except RuntimeError as e:
        return [{"embedding": arm, "model": model, "chunker": chunker, "mode": m, "reranker": r, "ran": False, "reason": str(e)}
                for m, r in retrieval_arms]
    db = Path(db_root) / arm
    t0 = time.time()
    ing = S.ingest(db, docs, chunker=chunker, embedding_function=ef, embedding_model=model)
    build_s = round(time.time() - t0, 1)
    client = S.make_client(db)
    coll = client.get_collection(S.collection_name(chunker), **({"embedding_function": ef} if ef else {}))
    chunks = S.read_chunks(db, chunker)
    bm25 = BM25(chunks)
    ol = over_limit((c["text"] for c in chunks), arm)
    manifest = S.read_manifest(db, chunker)
    queries = queries_for({k for k, v in manifest["docs"].items() if v["doc_type"] == "contract"})
    rows = []
    for mode, rname in retrieval_arms:
        base = {"embedding": arm, "model": model, "chunker": chunker, "mode": mode, "reranker": rname}
        try:
            reranker = (rerankers or {}).get(rname) or make_reranker(rname)
        except RuntimeError as e:
            rows.append({**base, "ran": False, "reason": str(e)})
            continue
        res = AS.run(queries, collection=coll, bm25=bm25, mode=mode, reranker=reranker)
        rows.append({**base, "ran": True, "n": res["summary"]["n"], "scoped": res["summary"]["scoped"], "corpus": res["summary"]["corpus"],
                     "build_s": build_s if ing["chunks_added"] else None, "over_limit": ol})
    return rows


def render(rows, meta) -> str:
    lines = [f"# Retrieval ablation, automatic set, {meta['date']}", "",
             f"Golden set {meta['golden_hash']}, playbook {meta['playbook_hash']}. recall@k is the share of gold spans a top-k chunk "
             "from the same contract overlaps; hybrid is BM25 + dense by reciprocal rank fusion; the cross-encoder retrieves 20 and keeps k.", "",
             "| Chunker | Embedding | Retrieval | n | Scoped R@3 / R@5 / R@10 | Scoped MRR | Corpus R@5 | Corpus MRR | Non-contract in corpus top 5 | Chunks over model limit | ms / query |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        retr = r["mode"] + (f" + {r['reranker']}" if r["reranker"] else "")
        if not r["ran"]:
            lines.append(f"| {r['chunker']} | {r['model']} | {retr} | not run: {r['reason']} | | | | | | | |")
            continue
        s, c = r["scoped"], r["corpus"]
        ol = f"{r['over_limit'][0] / r['over_limit'][1]:.0%}" if r.get("over_limit") and r["over_limit"][1] else "n/a"
        lines.append(f"| {r['chunker']} | {r['model']} | {retr} | {r['n']} | {s['recall']['3']:.1%} / {s['recall']['5']:.1%} / {s['recall']['10']:.1%} | "
                     f"{s['mrr']:.3f} | {c['recall']['5']:.1%} | {c['mrr']:.3f} | {c['wrong_doc_type_in_top5']} | {ol} | {s['mean_latency_ms']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunker", choices=CHUNKERS + ("both",), default="both")
    ap.add_argument("--arms", default=",".join(EMBEDDING_ARMS), help="comma-separated embedding arms")
    ap.add_argument("--db-root", default=str(S.DEFAULT_DB / "arms"))
    ap.add_argument("--out", default=str(ROOT / "evals" / "results"))
    args = ap.parse_args(argv)
    problems = AS.preconditions()
    if problems:
        print("not running:\n" + "\n".join(f"- {p}" for p in problems))
        return 2
    sys.path.insert(0, str(ROOT))
    from ingest import gather_docs
    docs, _, source = gather_docs()
    records, qtext = load_contracts(), questions(load_release())
    queries_for = lambda ids: AS.build_queries(records, qtext, ids)
    chunkers = CHUNKERS if args.chunker == "both" else (args.chunker,)
    rows = []
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        for ch in chunkers:
            rows += run_arm(arm, ch, docs, queries_for, args.db_root)
    meta = {"date": date.today().isoformat(), "documents": source, "golden_hash": AS.file_hash(AS.GOLDEN), "playbook_hash": AS.file_hash(AS.PLAYBOOK)}
    Path(args.out).mkdir(parents=True, exist_ok=True)
    stem = f"{meta['date']}-ablation"
    (Path(args.out) / f"{stem}.md").write_text(render(rows, meta), encoding="utf-8")
    (Path(args.out) / f"{stem}.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=1), encoding="utf-8")
    print(render(rows, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
