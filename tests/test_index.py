"""Chunkers, the versioned store, retrieval and the automatic-set scorer, on
small fixtures with the hash embedder: no model download, no network."""

import json
import importlib.util
from pathlib import Path

import pytest

from core import chunking as K
from core import store as S
from core.cuad import source_footer
from core.docs import content_hash, positions_written
from core.embeddings import HashEmbedding
from core.retrieve import BM25, matches, rrf, search, to_where

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("auto_set", ROOT / "evals" / "auto_set.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

WORDS = " ".join(f"word{i}" for i in range(1000))
CONTRACT = "\n".join([
    "SUPPLY AGREEMENT", "",
    "ARTICLE 1 DEFINITIONS", "The following terms apply. " * 30, "",
    "1.1 Products. Supplier shall supply widgets. " * 5, "",
    "ARTICLE 2 TERM AND TERMINATION", "This Agreement continues for three years and renews for one year. " * 20, "",
    "ARTICLE 3 LIMITATION OF LIABILITY", "In no event shall either party's liability exceed the fees paid. " * 15, "",
    "Source: ACME WIDGETS INC., 10-K, 3/1/2010",
])


def doc(did="c_1", text=CONTRACT, dt="contract", **md):
    return {"id": did, "doc_type": dt, "text": text, "metadata": {"doc_type": dt, "contract_id": did, **md}}


def test_fixed_windows_size_and_overlap():
    w = K.fixed_windows(WORDS)
    assert len(w) == 3  # 1000 tokens, stride 320
    toks = [WORDS[s:e].split() for s, e in w]
    assert len(toks[0]) == K.FIXED_TOKENS and toks[0][-K.FIXED_OVERLAP:] == toks[1][:K.FIXED_OVERLAP]
    assert toks[-1][-1] == "word999"


def test_section_chunks_follow_articles_and_respect_bounds():
    cs = K.chunk_document(doc(), "section")
    assert cs[0]["boundary"] == "contract_heading"
    assert all(K.SECTION_MIN <= c["tokens"] <= K.SECTION_MAX for c in cs[:-1])
    assert any(c["text"].startswith("ARTICLE 3 LIMITATION") for c in cs)
    for c in cs:
        assert CONTRACT[c["start"]:c["end"]] == c["text"]


def test_paragraph_fallback_and_coverage():
    text = ("Plain paragraph text without headings. " * 40 + "\n\n") * 3
    cs = K.chunk_document(doc(text=text), "section")
    assert {c["boundary"] for c in cs} == {"paragraph"}
    assert K.covers(cs[0], {"start": cs[0]["end"] - 1, "end": cs[0]["end"] + 10})
    assert not K.covers(cs[0], {"start": cs[0]["end"], "end": cs[0]["end"] + 10})


def test_risk_headings():
    body = "Our revenue depends on a few customers and could decline if any of them leaves us for a competitor. " * 6
    text = "\n".join(["RISKS RELATED TO OUR BUSINESS", "",
                      "We depend on a small number of customers for most of our revenue.", body, "",
                      "Our suppliers may fail to deliver components on time or at all.", body])
    starts = K.risk_heading_starts(text)
    assert text[starts[0]:].startswith("RISKS RELATED") and any(text[s:].startswith("Our suppliers") for s in starts)


def test_source_footer_and_playbook_positions():
    assert source_footer(CONTRACT) == {"filer": "ACME WIDGETS INC.", "form": "10-K", "filing_date": "2010-03-01"}
    assert source_footer("Source: A INC, 8-K, 1/1/2000\nSource: B INC, 8-K, 1/1/2001") is None
    assert positions_written("## Cap\n\n### Preferred position\n\n### Escalate if\n") == 0
    assert positions_written("## Cap\n\n### Preferred position\nCap at 12 months of fees.\n### Escalate if\n") == 1


def test_store_is_incremental_idempotent_and_versioned(tmp_path):
    ef = HashEmbedding()
    client = S.make_client(tmp_path)
    d1, d2 = doc("c_1"), doc("c_2", text=CONTRACT.replace("widgets", "gadgets"))
    r = S.ingest(tmp_path, [d1, d2], chunker="section", embedding_function=ef, embedding_model="hash-test", client=client)
    assert r["rebuilt"] and r["new"] == 2
    n = r["total_chunks"]
    r = S.ingest(tmp_path, [d1, d2], chunker="section", embedding_function=ef, embedding_model="hash-test", client=client)
    assert (r["new"], r["changed"], r["unchanged"], r["chunks_added"], r["total_chunks"]) == (0, 0, 2, 0, n)
    d2b = {**d2, "text": d2["text"] + "\n\nARTICLE 4 NOTICES\n" + "Notices go by mail. " * 30}
    st = S.status(tmp_path, [d1, d2b], chunker="section", embedding_model="hash-test")
    assert st["stale"] == ["c_2"] and not st["fresh"]
    r = S.ingest(tmp_path, [d1, d2b], chunker="section", embedding_function=ef, embedding_model="hash-test", client=client)
    assert r["changed"] == 1 and r["unchanged"] == 1
    coll = client.get_collection(S.collection_name("section"), embedding_function=ef)
    assert coll.count() == r["total_chunks"] == len(S.read_chunks(tmp_path, "section"))
    r = S.ingest(tmp_path, [d1], chunker="section", embedding_function=ef, embedding_model="hash-test", prune=True, client=client)
    assert r["removed"] == 1 and coll.count() == r["total_chunks"]
    assert S.status(tmp_path, [d1], chunker="section", embedding_model="hash-test")["fresh"]
    r = S.ingest(tmp_path, [d1], chunker="section", embedding_function=ef, embedding_model="other-model", client=client)
    assert r["rebuilt"] and "embedding_model" in r["reasons"][0]


def test_content_hash_sees_metadata():
    assert content_hash(doc(governing_law="Texas")) != content_hash(doc(governing_law="Ohio"))


def test_rrf_and_filters():
    a = [{"id": "x"}, {"id": "y"}, {"id": "z"}]
    b = [{"id": "y"}, {"id": "w"}]
    assert [h["id"] for h in rrf(a, b)] == ["y", "x", "w", "z"]
    assert to_where({"a": 1}) == {"a": 1} and to_where({"a": 1, "b": 2}) == {"$and": [{"a": 1}, {"b": 2}]}
    assert matches({"a": 1, "b": "x"}, {"b": {"$in": ["x", "y"]}}) and not matches({"a": 1}, {"a": 2})


@pytest.fixture
def small_index(tmp_path):
    ef = HashEmbedding()
    client = S.make_client(tmp_path)
    docs = [doc("c_1"), doc("c_2", text=CONTRACT.replace("liability", "indemnity")),
            {"id": "rf_1", "doc_type": "risk_factors", "text": "We face liability claims that exceed our insurance. " * 30,
             "metadata": {"doc_type": "risk_factors", "cik": 1}}]
    S.ingest(tmp_path, docs, chunker="section", embedding_function=ef, embedding_model="hash-test", client=client)
    coll = client.get_collection(S.collection_name("section"), embedding_function=ef)
    return coll, BM25(S.read_chunks(tmp_path, "section"))


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
def test_search_modes_respect_filters(small_index, mode):
    coll, bm25 = small_index
    res = search("limitation of liability fees paid", collection=coll, bm25=bm25, k=3, mode=mode, filters={"contract_id": "c_1"})
    assert res["hits"] and all(h["doc_id"] == "c_1" for h in res["hits"])
    assert "ARTICLE 3 LIMITATION" in res["hits"][0]["text"] or mode == "dense"
    wide = search("liability exceed", collection=coll, bm25=bm25, k=10, mode=mode)
    assert {h["doc_type"] for h in wide["hits"]} >= {"contract"}


def test_search_with_reranker(small_index):
    from core.rerank import LexicalReranker
    coll, bm25 = small_index
    res = search("liability fees", collection=coll, bm25=bm25, k=2, mode="hybrid", reranker=LexicalReranker())
    assert len(res["hits"]) == 2 and res["reranker"] == "lexical" and "rerank_score" in res["hits"][0]


def test_auto_set_score_and_run(small_index):
    coll, bm25 = small_index
    start = CONTRACT.index("In no event")
    gold = [{"category": "Cap On Liability", "start": start, "end": start + 60}]
    hits = [{"doc_id": "c_2", "start": start, "end": start + 100}, {"doc_id": "c_1", "start": start - 5, "end": start + 10}]
    s = A.score(hits, "c_1", gold, ks=(1, 2))
    assert s == {"recall": {"1": 0.0, "2": 1.0}, "mrr": 0.5}
    q = [{"contract_id": "c_1", "category": "Cap On Liability", "query": "cap on liability fees paid", "gold": gold}]
    out = A.run(q, collection=coll, bm25=bm25, mode="hybrid")
    assert out["summary"]["n"] == 1 and out["summary"]["scoped"]["recall"]["10"] == 1.0
    assert "| scoped |" in A.render({"date": "d", "chunker": "section", "mode": "hybrid", "reranker": None, "embedding_model": "hash-test",
                                     "contracts": 2, "golden_hash": "g", "playbook_hash": "p"}, out["summary"])


def test_auto_set_refuses_before_golden_and_playbook(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "GOLDEN", tmp_path / "golden.jsonl")
    assert any("golden" in p for p in A.preconditions())
    assert A.main([]) == 2


def test_build_queries_skips_metadata_categories():
    rec = {"id": "c_1", "spans": [{"category": "Parties", "start": 0, "end": 5}, {"category": "Audit Rights", "start": 10, "end": 20},
                                  {"category": "Audit Rights", "start": 30, "end": 40}]}
    q = A.build_queries([rec], {"Audit Rights": "audit?", "Parties": "who?"}, {"c_1"})
    assert len(q) == 1 and q[0]["category"] == "Audit Rights" and len(q[0]["gold"]) == 2
