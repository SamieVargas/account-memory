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

Every finished query and row is written to <date>-ablation.progress.jsonl as
it happens. An interrupted run (Ctrl+C, SIGTERM, an error) writes
<date>-ablation-partial.md/json with the finished rows and the arm in
progress as a partial row, and exits 130 on an interrupt; after a hard kill,
`--from-progress <file>` rebuilds that report from the progress file.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

import auto_set as AS  # noqa: E402
from core import store as S  # noqa: E402
from core.chunking import CHUNKERS  # noqa: E402
from core.cuad import load_contracts, load_release, questions  # noqa: E402
from core.embeddings import ARMS, make_embedding_function, over_limit  # noqa: E402
from core.rerank import make_reranker  # noqa: E402
from core.retrieve import BM25  # noqa: E402
from records import INTERRUPTED, Recorder, partial_stem, read_progress  # noqa: E402

EMBEDDING_ARMS = ("minilm", "bge-small", "e5-small")
RETRIEVAL_ARMS = (("dense", None), ("hybrid", None), ("hybrid", "cross-encoder"))


def _key(r):
    return (r["embedding"], r["chunker"], r["mode"], r["reranker"])


def _result_row(base, rows, summary_extra):
    summary = AS.summarize(rows)
    return {**base, "ran": True, "n": summary["n"], "scoped": summary["scoped"], "corpus": summary["corpus"], **summary_extra}


def run_arm(arm, chunker, docs, queries_for, db_root, retrieval_arms=RETRIEVAL_ARMS, rerankers=None,
            live=None, on_query=None, on_row=None):
    """Rows for one embedding arm and one chunker. `live` holds the arm in
    progress and its finished queries, so an interruption can report them;
    `on_query` and `on_row` hand each finished query and row to the recorder."""
    live = {} if live is None else live
    emit = on_row or (lambda r: None)
    model = ARMS[arm]["model"]
    out = []
    try:
        ef, _ = make_embedding_function(arm)
    except RuntimeError as e:
        for m, r in retrieval_arms:
            row = {"embedding": arm, "model": model, "chunker": chunker, "mode": m, "reranker": r, "ran": False, "reason": str(e)}
            out.append(row)
            emit(row)
        return out
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
    for mode, rname in retrieval_arms:
        base = {"embedding": arm, "model": model, "chunker": chunker, "mode": mode, "reranker": rname}
        try:
            reranker = (rerankers or {}).get(rname) or make_reranker(rname)
        except RuntimeError as e:
            row = {**base, "ran": False, "reason": str(e)}
            out.append(row)
            emit(row)
            continue
        extra = {"build_s": build_s if ing["chunks_added"] else None, "over_limit": ol, "n_queries": len(queries)}
        live.update(base=base, rows=[], extra=extra)
        AS.run(queries, collection=coll, bm25=bm25, mode=mode, reranker=reranker, rows=live["rows"],
               on_row=(lambda q, b=base: on_query(b, q)) if on_query else None)
        row = _result_row(base, live["rows"], extra)
        live.clear()
        out.append(row)
        emit(row)
    return out


def render(rows, meta, partial: str | None = None) -> str:
    title = f"# Retrieval ablation, automatic set, {meta['date']}" + (f" (PARTIAL: {partial})" if partial else "")
    lines = [title, "",
             f"Golden set {meta['golden_hash']}, playbook {meta['playbook_hash']}. recall@k is the share of gold spans a top-k chunk "
             "from the same contract overlaps; hybrid is BM25 + dense by reciprocal rank fusion; the cross-encoder retrieves 20 and keeps k.", "",
             "| Chunker | Embedding | Retrieval | n | Scoped R@3 / R@5 / R@10 | Scoped MRR | Corpus R@5 | Corpus MRR | Non-contract in corpus top 5 | Chunks over model limit | ms / query |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        retr = r["mode"] + (f" + {r['reranker']}" if r["reranker"] else "") + (" (partial)" if r.get("partial") else "")
        if not r["ran"]:
            lines.append(f"| {r['chunker']} | {r['model']} | {retr} | not run: {r['reason']} | | | | | | | |")
            continue
        s, c = r["scoped"], r["corpus"]
        ol = f"{r['over_limit'][0] / r['over_limit'][1]:.0%}" if r.get("over_limit") and r["over_limit"][1] else "n/a"
        n = f"{r['n']} of {r['n_queries']}" if r.get("partial") and r.get("n_queries") else r["n"]
        lines.append(f"| {r['chunker']} | {r['model']} | {retr} | {n} | {AS.pct(s['recall']['3'])} / {AS.pct(s['recall']['5'])} / {AS.pct(s['recall']['10'])} | "
                     f"{AS.num(s['mrr'])} | {AS.pct(c['recall']['5'])} | {AS.num(c['mrr'])} | {c['wrong_doc_type_in_top5']} | {ol} | {AS.num(s['mean_latency_ms'], '{}')} |")
    return "\n".join(lines) + "\n"


def rows_from_progress(records) -> list[dict]:
    """Finished rows, plus a partial row for any arm whose queries were
    recorded but whose row never was."""
    rows = [r["row"] for r in records if r.get("type") == "arm"]
    done = {_key(r) for r in rows}
    pending = {}
    for r in records:
        if r.get("type") == "query" and _key(r["arm"]) not in done:
            pending.setdefault(_key(r["arm"]), (r["arm"], []))[1].append(r["row"])
    for base, qrows in pending.values():
        rows.append(_result_row(base, qrows, {"partial": True, "n_queries": base.get("n_queries")}))
    return rows


def from_progress(path) -> int:
    meta, records = read_progress(path)
    rows = rows_from_progress(records)
    out, stem = partial_stem(path)
    note = f"{sum(1 for r in rows if not r.get('partial'))} of {meta.get('planned_rows', '?')} rows finished, rebuilt from {Path(path).name}"
    md = render(rows, meta, note)
    (out / f"{stem}-partial.md").write_text(md, encoding="utf-8")
    (out / f"{stem}-partial.json").write_text(json.dumps({"meta": meta, "rows": rows, "partial": True}, indent=1), encoding="utf-8")
    print(md)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunker", choices=CHUNKERS + ("both",), default="both")
    ap.add_argument("--arms", default=",".join(EMBEDDING_ARMS), help="comma-separated embedding arms")
    ap.add_argument("--db-root", default=str(S.DEFAULT_DB / "arms"))
    ap.add_argument("--out", default=str(ROOT / "evals" / "results"))
    ap.add_argument("--from-progress", metavar="FILE", help="rebuild a partial report from a .progress.jsonl and exit")
    args = ap.parse_args(argv)
    if args.from_progress:
        return from_progress(args.from_progress)
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
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    meta = {"date": date.today().isoformat(), "documents": source, "golden_hash": AS.file_hash(AS.GOLDEN), "playbook_hash": AS.file_hash(AS.PLAYBOOK),
            "arms": arms, "chunkers": list(chunkers), "planned_rows": len(arms) * len(chunkers) * len(RETRIEVAL_ARMS)}
    stem = f"{meta['date']}-ablation"
    rows, live = [], {}
    with Recorder(args.out, stem, meta) as rec:
        on_query = lambda base, q: rec.append({"type": "query", "arm": {**base, "n_queries": live.get("extra", {}).get("n_queries")}, "row": q})
        def on_row(r):
            rows.append(r)  # each row as it finishes, so an interruption inside an arm keeps the arm's earlier rows
            rec.append({"type": "arm", "row": r})
        try:
            for arm in arms:
                for ch in chunkers:
                    run_arm(arm, ch, docs, queries_for, args.db_root, live=live, on_query=on_query, on_row=on_row)
        except BaseException as e:
            shown = list(rows)
            if live.get("rows"):
                shown.append(_result_row(live["base"], live["rows"], {**live["extra"], "partial": True}))
            why = "interrupted" if isinstance(e, KeyboardInterrupt) else f"{type(e).__name__}: {str(e)[:120]}"
            md = render(shown, meta, f"{len(rows)} of {meta['planned_rows']} rows finished, {why}")
            rec.partial(md, {"meta": meta, "rows": shown, "stopped_by": why})
            print(md)
            print(f"wrote {stem}-partial.md; progress kept in {rec.progress.name}")
            if isinstance(e, KeyboardInterrupt):
                return INTERRUPTED
            raise
        md = render(rows, meta)
        rec.finish(md, {"meta": meta, "rows": rows})
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
