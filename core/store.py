"""The index, one Chroma collection per chunker, kept current incrementally.

Ported from pixels-rag core/store.py (see docs/PROVENANCE.md): ingest is
keyed by document id and idempotent; the collection is stamped with the
chunker version, the chunker source hash and the embedding model, and a
mismatch with the running code rebuilds the whole collection and says why.
New here: a per-document content hash in a manifest, so a changed contract
replaces only its own chunks, and a freshness status that compares the
manifest with the documents at the source.

The manifest (manifest-<chunker>.json) and every chunk's text and offsets
(chunks-<chunker>.json, which BM25 reads) live beside the Chroma files.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from core.chunking import CHUNKER_VERSION, chunk_document, source_hash
from core.docs import content_hash

DEFAULT_DB = Path(__file__).resolve().parent.parent / "chroma_db"
BATCH = 256


def collection_name(chunker: str) -> str:
    return f"am_{chunker}"


def stamp(chunker: str, embedding_model: str) -> dict:
    return {"chunker_version": CHUNKER_VERSION[chunker], "chunker_hash": source_hash(), "embedding_model": embedding_model}


def make_client(path=None):
    return chromadb.PersistentClient(path=str(path)) if path else chromadb.EphemeralClient()


def _paths(db, chunker):
    db = Path(db)
    return db / f"manifest-{chunker}.json", db / f"chunks-{chunker}.json"


def read_manifest(db, chunker) -> dict:
    p, _ = _paths(db, chunker)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"stamp": None, "docs": {}}


def read_chunks(db, chunker) -> list[dict]:
    _, p = _paths(db, chunker)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def _write(db, chunker, manifest, chunks):
    m, c = _paths(db, chunker)
    Path(db).mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    c.write_text(json.dumps(sorted(chunks, key=lambda x: x["id"]), ensure_ascii=False), encoding="utf-8")


def chunk_metadata(ch: dict) -> dict:
    md = {**ch["metadata"], "doc_id": ch["doc_id"], "doc_type": ch["doc_type"], "chunker": ch["chunker"],
          "start": ch["start"], "end": ch["end"], "tokens": ch["tokens"], "boundary": ch["boundary"]}
    if ch["doc_type"] == "playbook":
        m = re.match(r"## (.+)", ch["text"])
        if m:
            md["category"] = m[1].strip()
    return md


def version_mismatch(collection, chunker, embedding_model) -> list[str]:
    md = collection.metadata or {}
    return [f"{k}: index has {md.get(k)!r}, code has {v!r}" for k, v in stamp(chunker, embedding_model).items() if md.get(k) != v]


def _collection(client, chunker, embedding_model, embedding_function, fresh=False):
    name = collection_name(chunker)
    kwargs = {"embedding_function": embedding_function} if embedding_function is not None else {}
    if fresh:
        try:
            client.delete_collection(name)
        except Exception:
            pass
        return client.create_collection(name=name, metadata={"hnsw:space": "cosine", **stamp(chunker, embedding_model)}, **kwargs)
    return client.get_collection(name, **kwargs)


def _add(coll, chunks):
    for i in range(0, len(chunks), BATCH):
        b = chunks[i:i + BATCH]
        coll.add(ids=[c["id"] for c in b], documents=[c["text"] for c in b], metadatas=[chunk_metadata(c) for c in b])


def ingest(db, docs: list[dict], *, chunker: str, embedding_function=None, embedding_model: str = "all-MiniLM-L6-v2",
           prune: bool = False, client=None) -> dict:
    """Upsert `docs` into the chunker's collection. A document whose content
    hash is unchanged is skipped; a changed one has its old chunks deleted
    and its new ones added. With prune, documents in the index but not in
    `docs` are removed. A stamp mismatch rebuilds everything."""
    client = client or make_client(db)
    manifest = read_manifest(db, chunker)
    chunks = {c["id"]: c for c in read_chunks(db, chunker)}
    report = {"chunker": chunker, "new": 0, "changed": 0, "unchanged": 0, "removed": 0, "chunks_added": 0,
              "rebuilt": False, "reasons": []}
    try:
        coll = _collection(client, chunker, embedding_model, embedding_function)
        report["reasons"] = version_mismatch(coll, chunker, embedding_model)
    except Exception:
        coll, report["reasons"] = None, ["no collection yet"]
    if coll is None or report["reasons"]:
        coll = _collection(client, chunker, embedding_model, embedding_function, fresh=True)
        manifest, chunks = {"stamp": None, "docs": {}}, {}
        report["rebuilt"] = True
    seen = set()
    for doc in docs:
        seen.add(doc["id"])
        h = content_hash(doc)
        old = manifest["docs"].get(doc["id"])
        if old and old["hash"] == h:
            report["unchanged"] += 1
            continue
        if old:
            coll.delete(ids=old["chunk_ids"])
            for cid in old["chunk_ids"]:
                chunks.pop(cid, None)
        new = chunk_document(doc, chunker)
        _add(coll, new)
        for c in new:
            chunks[c["id"]] = c
        manifest["docs"][doc["id"]] = {"hash": h, "doc_type": doc["doc_type"], "chunk_ids": [c["id"] for c in new],
                                       "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        report["changed" if old else "new"] += 1
        report["chunks_added"] += len(new)
    if prune:
        for doc_id in [d for d in manifest["docs"] if d not in seen]:
            ids = manifest["docs"].pop(doc_id)["chunk_ids"]
            coll.delete(ids=ids)
            for cid in ids:
                chunks.pop(cid, None)
            report["removed"] += 1
    manifest["stamp"] = stamp(chunker, embedding_model)
    _write(db, chunker, manifest, list(chunks.values()))
    report["total_docs"], report["total_chunks"] = len(manifest["docs"]), len(chunks)
    return report


def status(db, docs: list[dict] | None, *, chunker: str, embedding_model: str = "all-MiniLM-L6-v2") -> dict:
    """Freshness: documents current, stale (source changed since ingest),
    missing (at the source, not indexed), extra (indexed, gone from the
    source), and whether the stamp still matches the code."""
    manifest = read_manifest(db, chunker)
    want = stamp(chunker, embedding_model)
    out = {"chunker": chunker, "indexed_docs": len(manifest["docs"]),
           "indexed_chunks": sum(len(d["chunk_ids"]) for d in manifest["docs"].values()),
           "stamp": manifest["stamp"],
           "stamp_mismatch": [f"{k}: index has {(manifest['stamp'] or {}).get(k)!r}, code has {v!r}" for k, v in want.items()
                              if (manifest["stamp"] or {}).get(k) != v],
           "newest_ingest": max((d["ingested_at"] for d in manifest["docs"].values()), default=None)}
    if docs is not None:
        src = {d["id"]: content_hash(d) for d in docs}
        idx = {k: v["hash"] for k, v in manifest["docs"].items()}
        out.update(current=sum(1 for k, h in src.items() if idx.get(k) == h),
                   stale=sorted(k for k, h in src.items() if k in idx and idx[k] != h),
                   missing=sorted(k for k in src if k not in idx), extra=sorted(k for k in idx if k not in src))
        out["fresh"] = not (out["stale"] or out["missing"] or out["stamp_mismatch"])
    return out
