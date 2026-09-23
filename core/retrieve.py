"""Retrieval: dense, BM25, their reciprocal-rank fusion, and an optional
rerank of the fused candidates. One entry point, `search`, so an ablation
is a flag.

Filters are {field: value} or {field: {"$in": [values]}} over chunk
metadata, applied the same way to both retrievers: as a Chroma `where` for
dense, as a predicate for BM25. A filter narrows before ranking in both.
"""

import re
import time

from rank_bm25 import BM25Okapi

from core.rerank import rerank as _rerank
from core.store import chunk_metadata

RRF_K = 60
CANDIDATES = 20
MODES = ("dense", "bm25", "hybrid")
_WORD = re.compile(r"[a-z0-9]+")


def bm25_tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def to_where(filters: dict | None):
    if not filters:
        return None
    parts = [{k: v} for k, v in filters.items()]
    return parts[0] if len(parts) == 1 else {"$and": parts}


def matches(md: dict, filters: dict | None) -> bool:
    for k, v in (filters or {}).items():
        if isinstance(v, dict) and "$in" in v:
            if md.get(k) not in v["$in"]:
                return False
        elif md.get(k) != v:
            return False
    return True


class BM25:
    """BM25 over every chunk in a collection. Scores are computed over the
    whole corpus, so IDF does not change with the filter; the filter then
    decides which chunks may rank."""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.meta = [chunk_metadata(c) for c in chunks]
        self.index = BM25Okapi([bm25_tokens(c["text"]) for c in chunks]) if chunks else None

    def search(self, query: str, k: int, filters=None) -> list[dict]:
        if not self.index:
            return []
        scores = self.index.get_scores(bm25_tokens(query))
        allowed = [i for i, md in enumerate(self.meta) if matches(md, filters)]
        ranked = sorted(allowed, key=lambda i: (-scores[i], self.chunks[i]["id"]))[:k]
        return [_hit(self.chunks[i]["id"], self.chunks[i]["text"], self.meta[i], float(scores[i])) for i in ranked]


def _hit(cid, text, md, score):
    return {"id": cid, "text": text, "metadata": md, "doc_id": md.get("doc_id"), "doc_type": md.get("doc_type"),
            "start": md.get("start"), "end": md.get("end"), "score": round(score, 4)}


def dense(collection, query: str, k: int, filters=None) -> list[dict]:
    if k <= 0:
        return []
    kwargs = {"where": to_where(filters)} if filters else {}
    res = collection.query(query_texts=[query], n_results=k, include=["documents", "metadatas", "distances"], **kwargs)
    return [_hit(cid, res["documents"][0][i], res["metadatas"][0][i] or {}, 1 - float(res["distances"][0][i]))
            for i, cid in enumerate(res["ids"][0])]


def rrf(*lists: list[dict], k: int = RRF_K) -> list[dict]:
    """Reciprocal rank fusion: each list adds 1 / (k + rank) to a chunk."""
    score, first = {}, {}
    for lst in lists:
        for rank, h in enumerate(lst, start=1):
            score[h["id"]] = score.get(h["id"], 0.0) + 1.0 / (k + rank)
            first.setdefault(h["id"], h)
    out = []
    for cid in sorted(score, key=lambda c: (-score[c], c)):
        out.append({**first[cid], "score": round(score[cid], 6)})
    return out


def search(query: str, *, collection, bm25: BM25 | None, k: int = 5, mode: str = "dense", filters=None,
           reranker=None, candidates: int = CANDIDATES) -> dict:
    """Top k chunks for the query. Without a reranker each retriever returns
    k (hybrid fuses the two lists of `candidates` and keeps k); with one, the
    first stage returns `candidates` and the reranker keeps k."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    t0 = time.time()
    n = max(candidates, k) if (reranker is not None or mode == "hybrid") else k
    if mode == "dense":
        hits = dense(collection, query, n, filters)
    elif mode == "bm25":
        hits = bm25.search(query, n, filters)
    else:
        hits = rrf(dense(collection, query, n, filters), bm25.search(query, n, filters))[:n]
    rerank_ms = None
    if reranker is not None:
        hits, rerank_ms = _rerank(query, hits, reranker, k)
    return {"hits": hits[:k], "mode": mode, "reranker": getattr(reranker, "name", None), "rerank_ms": rerank_ms,
            "latency_ms": int((time.time() - t0) * 1000)}
