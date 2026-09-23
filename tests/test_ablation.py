"""Part 6 harness: prefixed embedders, arms that cannot load, and the
ablation rows, with fakes in place of torch and the Hugging Face models."""

import importlib.util
import sys
from pathlib import Path

from core import embeddings as E
from core import store as S
from tests.test_index import CONTRACT, doc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))
spec = importlib.util.spec_from_file_location("ablation", ROOT / "evals" / "ablation.py")
AB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AB)


class FakeST:
    """Records what it was asked to encode; the vector is the hash embedding."""

    def __init__(self):
        self.seen = []

    def encode(self, texts, normalize_embeddings=True):
        texts = list(texts)
        self.seen += texts
        return E.HashEmbedding()(texts)


def test_prefixes_reach_documents_and_queries(tmp_path):
    fake = FakeST()
    ef = E.PrefixedSentenceTransformer("intfloat/e5-small-v2", "query: ", "passage: ", _model=fake)
    client = S.make_client(tmp_path)
    S.ingest(tmp_path, [doc("c_1")], chunker="section", embedding_function=ef, embedding_model="e5", client=client)
    coll = client.get_collection(S.collection_name("section"), embedding_function=ef)
    coll.query(query_texts=["cap on liability"], n_results=1)
    assert all(t.startswith("passage: ") for t in fake.seen[:-1])
    assert fake.seen[-1] == "query: cap on liability"


def test_arm_that_cannot_load_is_a_not_run_row(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise ImportError("No module named 'sentence_transformers'")
    monkeypatch.setattr(E.PrefixedSentenceTransformer, "__init__", boom)
    rows = AB.run_arm("bge-small", "section", [doc("c_1")], lambda ids: [], tmp_path)
    assert len(rows) == 3 and not any(r["ran"] for r in rows)
    assert "sentence-transformers" in rows[0]["reason"]
    assert "not run: bge-small needs" in AB.render(rows, {"date": "d", "golden_hash": "g", "playbook_hash": "p"})


def test_run_arm_rows_and_missing_reranker(monkeypatch, tmp_path):
    start = CONTRACT.index("In no event")
    gold = [{"category": "Cap On Liability", "start": start, "end": start + 60}]
    queries_for = lambda ids: [{"contract_id": "c_1", "category": "Cap On Liability", "query": "liability fees paid", "gold": gold}] if "c_1" in ids else []

    def no_ce(name):
        if name == "cross-encoder":
            raise RuntimeError("the cross-encoder reranker needs sentence-transformers")
        return None
    monkeypatch.setattr(AB, "make_reranker", no_ce)
    rows = AB.run_arm("hash", "section", [doc("c_1"), doc("c_2")], queries_for, tmp_path)
    assert [(r["mode"], r["reranker"], r["ran"]) for r in rows] == [("dense", None, True), ("hybrid", None, True), ("hybrid", "cross-encoder", False)]
    assert rows[1]["n"] == 1 and rows[1]["scoped"]["recall"]["10"] == 1.0
    md = AB.render(rows, {"date": "d", "golden_hash": "g", "playbook_hash": "p"})
    assert "| section | hash-test | hybrid | 1 |" in md and "not run: the cross-encoder" in md


def test_ablation_refuses_before_golden(monkeypatch, tmp_path):
    monkeypatch.setattr(AB.AS, "GOLDEN", tmp_path / "nope.jsonl")
    assert AB.main([]) == 2
