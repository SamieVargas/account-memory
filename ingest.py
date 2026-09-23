"""Build or update the index, and write the ingest report.

    python ingest.py                          # the selected contracts (data/selection.json), both chunkers
    python ingest.py --chunker section        # one chunker
    python ingest.py --candidates             # every commercial candidate, before selection exists
    python ingest.py --status                 # freshness only, no writes
    python ingest.py --dry-run                # chunk and report, embed nothing

Documents: the contracts, the Item 1A extractions in
data/derived/risk_factors.json when the EDGAR ingest has run, and the
playbook once its positions are written. Incremental and idempotent: a rerun
with nothing changed adds nothing (see core/store.py).

Writes evals/results/ingest-<date>.md.
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from core import store as S  # noqa: E402
from core.chunking import CHUNKERS, FIXED_OVERLAP, FIXED_TOKENS, SECTION_MAX, SECTION_MIN, chunk_document  # noqa: E402
from core.cuad import COMMERCIAL_TYPES, load_contracts  # noqa: E402
from core.docs import contract_doc, playbook_doc, risk_doc  # noqa: E402
from core.embeddings import ARMS, DEFAULT, make_embedding_function, wordpiece_counter  # noqa: E402

DERIVED = ROOT / "data" / "derived"
DATE_FIELDS = ("agreement_date", "effective_date", "expiration_date")


def _json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def gather_docs(candidates: bool = False):
    """(documents, contract records, source description)."""
    records = load_contracts()
    sel_path = ROOT / "data" / "selection.json"
    if candidates:
        chosen = [r for r in records if r["contract_type"] in COMMERCIAL_TYPES]
        source = f"all {len(chosen)} commercial candidates (no selection applied)"
    else:
        sel = _json(sel_path, None)
        if sel is None:
            raise SystemExit("data/selection.json is missing: run scripts/select_contracts.py, or pass --candidates")
        ids = {c["id"] for c in sel["contracts"]}
        chosen = [r for r in records if r["id"] in ids]
        source = f"{len(chosen)} selected contracts" + (" (PROVISIONAL selection)" if sel.get("provisional") else "")
    accounts = {a["contract_id"]: a for a in _json(DERIVED / "accounts.json", [])}
    names = {a["cik"]: a["account"] for a in accounts.values() if a.get("cik")}
    docs = [contract_doc(r, accounts.get(r["id"])) for r in chosen]
    ciks = {accounts[r["id"]]["cik"] for r in chosen if accounts.get(r["id"], {}).get("cik")}
    risk = [risk_doc(e, names.get(e["cik"])) for e in _json(DERIVED / "risk_factors.json", []) if e["cik"] in ciks]
    pb = playbook_doc()
    return docs + risk + ([pb] if pb else []), chosen, source


def report(docs, records, source, results, embedding_model, dry_run, embedding_arm=DEFAULT):
    today = date.today().isoformat()
    by_type = Counter(d["doc_type"] for d in docs)
    lines = [f"# Ingest, {today}", "", f"Documents: {source}; {by_type['risk_factors']} Item 1A sections; "
             f"playbook {'included' if by_type['playbook'] else 'left out until all 30 positions are written'}.",
             f"Embedding model: {embedding_model}{' (dry run: chunked, nothing embedded)' if dry_run else ''}.",
             f"Chunkers: fixed = {FIXED_TOKENS} tokens with {FIXED_OVERLAP} overlap; section = headings, merged under "
             f"{SECTION_MIN} tokens, split over {SECTION_MAX}. Tokens are \\w+ runs and punctuation marks.", "",
             "## Contracts", "", "| Measure | n |", "| --- | --- |",
             f"| Contracts | {len(records)} |",
             f"| Gold spans | {sum(len(r['spans']) for r in records)} |",
             f"| Spans not mapped to offsets | {sum(len(r['unmapped_spans']) for r in records)} |"]
    for f in DATE_FIELDS:
        c = Counter(r["metadata"][f]["status"] for r in records)
        lines.append(f"| {f}: parsed / unparsed / absent | {c['parsed']} / {c['unparsed']} / {c['absent']} |")
    wp = wordpiece_counter()
    limits = [(a, ARMS[a]["max_wordpieces"] - 2) for a in (embedding_arm, "minilm") if ARMS[a]["max_wordpieces"]]
    limits = list(dict.fromkeys(limits))
    lines += ["", "## Chunks", "", "Over a model's limit: chunks longer than that model reads (its max wordpieces less [CLS] and [SEP]), "
              "counted with the WordPiece vocabulary bge-small, e5-small and MiniLM share; the model embeds only the start of those chunks"
              + ("" if wp else " (tokenizer not on disk, not counted)") + ".", "",
              "| Chunker | doc type | docs | chunks | median tokens | max tokens | " + " | ".join(f"over {a} ({l})" for a, l in limits) + " | boundaries |",
              "| --- " * (7 + len(limits)) + "|"]
    for chunker, res in results.items():
        chunks = res["chunks"]
        for dt in ("contract", "risk_factors", "playbook"):
            cs = [c for c in chunks if c["doc_type"] == dt]
            if not cs:
                continue
            kinds = Counter()
            for doc_id in {c["doc_id"] for c in cs}:
                kinds[next(c["boundary"] for c in cs if c["doc_id"] == doc_id)] += 1
            t = [c["tokens"] for c in cs]
            counts = wp([c["text"] for c in cs]) if wp else None
            over_s = " | ".join((lambda o: f"{o} ({o / len(cs):.0%})")(sum(1 for n in counts if n > l)) if counts else "n/a" for _, l in limits)
            lines.append(f"| {chunker} | {dt} | {len({c['doc_id'] for c in cs})} | {len(cs)} | {statistics.median(t):.0f} | {max(t)} | {over_s} | "
                         + ", ".join(f"{k} {v}" for k, v in kinds.most_common()) + " |")
    if not dry_run:
        lines += ["", "## Index", "", "| Chunker | new | changed | unchanged | removed | chunks added | total chunks | rebuilt |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for chunker, res in results.items():
            r = res["ingest"]
            lines.append(f"| {chunker} | {r['new']} | {r['changed']} | {r['unchanged']} | {r['removed']} | {r['chunks_added']} | "
                         f"{r['total_chunks']} | {'yes: ' + '; '.join(r['reasons']) if r['rebuilt'] else 'no'} |")
    out = ROOT / "evals" / "results" / f"ingest-{today}{'-dry' if dry_run else ''}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunker", choices=CHUNKERS + ("both",), default="both")
    ap.add_argument("--embedding", choices=list(ARMS), default=DEFAULT)
    ap.add_argument("--db", default=str(S.DEFAULT_DB))
    ap.add_argument("--candidates", action="store_true", help="every commercial candidate instead of the selection")
    ap.add_argument("--prune", action="store_true", help="remove indexed documents no longer in the set")
    ap.add_argument("--status", action="store_true", help="freshness only")
    ap.add_argument("--dry-run", action="store_true", help="chunk and report, embed nothing")
    args = ap.parse_args(argv)
    chunkers = CHUNKERS if args.chunker == "both" else (args.chunker,)
    docs, records, source = gather_docs(args.candidates)
    model = ARMS[args.embedding]["model"]
    if args.status:
        for ch in chunkers:
            print(json.dumps(S.status(args.db, docs, chunker=ch, embedding_model=model), indent=1))
        return 0
    results = {}
    ef = None if args.dry_run else make_embedding_function(args.embedding)[0]
    for ch in chunkers:
        if args.dry_run:
            results[ch] = {"chunks": [c for d in docs for c in chunk_document(d, ch)]}
        else:
            r = S.ingest(args.db, docs, chunker=ch, embedding_function=ef, embedding_model=model, prune=args.prune)
            results[ch] = {"ingest": r, "chunks": S.read_chunks(args.db, ch)}
    out, lines = report(docs, records, source, results, model, args.dry_run, args.embedding)
    print("\n".join(lines))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
