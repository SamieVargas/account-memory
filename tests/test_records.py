"""Interrupted runs keep their records, and the playbook gate needs all 30
positions. Fixture index, hash embedder, no network."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from core import cuad as C
from core import store as S
from core.docs import contract_doc, playbook_status
from core.embeddings import HashEmbedding
from tests.test_index import CONTRACT

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AS = _load("auto_set_t", "evals/auto_set.py")
AB = _load("ablation_t", "evals/ablation.py")
R = _load("records_t", "evals/records.py")

CATS = ("Cap On Liability", "Anti-Assignment", "Audit Rights")


def _record():
    qas = []
    for i, cat in enumerate(CATS):
        s = CONTRACT.index("In no event") if i == 0 else CONTRACT.index("ARTICLE 2") + 20 * i
        qas.append({"id": f"x__{cat}", "question": cat, "answers": [{"text": CONTRACT[s:s + 30], "answer_start": s}]})
    return C.build_record({"title": "ACME_01_06_2010-EX-10.1-SUPPLY AGREEMENT", "paragraphs": [{"context": CONTRACT, "qas": qas}]})


@pytest.fixture
def env(tmp_path, monkeypatch):
    rec = _record()
    for mod in (AS, AB):
        monkeypatch.setattr(mod, "load_contracts", lambda: [rec])
        monkeypatch.setattr(mod, "load_release", lambda: None)
        monkeypatch.setattr(mod, "questions", lambda release: {c: f"what about {c.lower()}?" for c in C.CATEGORIES})
    monkeypatch.setattr(AS, "preconditions", lambda: [])
    monkeypatch.setattr(AB.AS, "preconditions", lambda: [])
    monkeypatch.setattr(AS, "make_embedding_function", lambda arm: (HashEmbedding(), "hash-test"))
    monkeypatch.setattr(AS, "over_limit", lambda texts, arm: None)
    docs = [contract_doc(rec)]
    db = tmp_path / "db"
    S.ingest(db, docs, chunker="section", embedding_function=HashEmbedding(), embedding_model="hash-test")
    monkeypatch.setitem(sys.modules, "ingest", types.SimpleNamespace(gather_docs=lambda: (docs, [rec], "1 fixture contract")))
    return {"rec": rec, "db": db, "out": tmp_path / "out"}


def interrupt_after(monkeypatch, calls):
    """Raise KeyboardInterrupt on the search after `calls`, in both the
    auto_set loaded here and the one the ablation imports."""
    n = {"n": 0}
    for mod in (AS, AB.AS):
        real = mod.search

        def search(*a, _real=real, **k):
            n["n"] += 1
            if n["n"] > calls:
                raise KeyboardInterrupt
            return _real(*a, **k)
        monkeypatch.setattr(mod, "search", search)


def test_auto_set_finishes_and_removes_progress(env):
    code = AS.main(["--embedding", "hash", "--db", str(env["db"]), "--out", str(env["out"])])
    files = sorted(p.name for p in env["out"].iterdir())
    assert code == 0 and any(f.endswith("-auto-section-dense.md") for f in files) and not any("progress" in f for f in files)
    data = json.loads(next(env["out"].glob("*-auto-section-dense.json")).read_text())
    assert data["summary"]["n"] == 3


def test_auto_set_interrupted_keeps_finished_queries(env, monkeypatch):
    interrupt_after(monkeypatch, 4)  # two searches per query: two queries finish
    code = AS.main(["--embedding", "hash", "--db", str(env["db"]), "--out", str(env["out"])])
    assert code == R.INTERRUPTED
    md = next(env["out"].glob("*-partial.md")).read_text()
    assert "PARTIAL: 2 of 3 queries, interrupted" in md.splitlines()[0]
    data = json.loads(next(env["out"].glob("*-partial.json")).read_text())
    assert data["partial"] and data["summary"]["n"] == 2 and len(data["rows"]) == 2
    progress = next(env["out"].glob("*.progress.jsonl"))
    meta, recs = R.read_progress(progress)
    assert meta["n_queries"] == 3 and len(recs) == 2
    # a hard kill leaves only the progress file, and a torn last line
    progress.write_text(progress.read_text() + '{"type": "query", "row": {"cut', encoding="utf-8")
    for p in env["out"].glob("*-partial.*"):
        p.unlink()
    assert AS.main(["--from-progress", str(progress)]) == 0
    assert "PARTIAL: 2 of 3 queries, rebuilt from" in next(env["out"].glob("*-partial.md")).read_text()


def test_auto_set_error_writes_partial_then_raises(env, monkeypatch):
    real = AS.search
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("credit balance is too low")
        return real(*a, **k)
    monkeypatch.setattr(AS, "search", flaky)
    with pytest.raises(RuntimeError):
        AS.main(["--embedding", "hash", "--db", str(env["db"]), "--out", str(env["out"])])
    assert "RuntimeError: credit balance is too low" in next(env["out"].glob("*-partial.md")).read_text()


def test_ablation_interrupted_keeps_finished_rows_and_the_arm_in_progress(env, monkeypatch):
    interrupt_after(monkeypatch, 8)  # dense finishes (6 searches), hybrid finishes one query
    args = ["--arms", "hash", "--chunker", "section", "--db-root", str(env["db"].parent / "arms"), "--out", str(env["out"])]
    assert AB.main(args) == R.INTERRUPTED
    md = next(env["out"].glob("*-ablation-partial.md")).read_text()
    assert "PARTIAL: 1 of 3 rows finished, interrupted" in md.splitlines()[0]
    assert "| section | hash-test | dense | 3 |" in md and "| section | hash-test | hybrid (partial) | 1 of 3 |" in md
    progress = next(env["out"].glob("*-ablation.progress.jsonl"))
    for p in env["out"].glob("*-partial.*"):
        p.unlink()
    assert AB.main(["--from-progress", str(progress)]) == 0
    rebuilt = next(env["out"].glob("*-ablation-partial.md")).read_text()
    assert "| section | hash-test | dense | 3 |" in rebuilt and "hybrid (partial) | 1 of 3 |" in rebuilt


def test_ablation_finishes(env):
    args = ["--arms", "hash", "--chunker", "section", "--db-root", str(env["db"].parent / "arms"), "--out", str(env["out"])]
    assert AB.main(args) == 0
    md = next(env["out"].glob("*-ablation.md")).read_text()
    assert "| section | hash-test | hybrid | 3 |" in md and not list(env["out"].glob("*.progress.jsonl"))


def _playbook(n_cats=10, skip=(), optional=True):
    parts = []
    for i in range(n_cats):
        parts.append(f"## Category {i}\n")
        for p in ("Preferred position", "Acceptable fallback", "Escalate if"):
            parts.append(f"### {p}\n" + ("" if (i, p) in skip else f"Text for {i} {p}.\n"))
    if optional:
        parts.append("## Filing-data rules (optional)\n\n### Anything\n")
    return "\n".join(parts)


def test_playbook_needs_all_thirty():
    st = playbook_status(_playbook())
    assert st["complete"] and st["filled"] == 30 and st["expected"] == 30 and st["empty"] == []
    st = playbook_status(_playbook(skip={(3, "Escalate if")}))
    assert not st["complete"] and st["filled"] == 29 and st["empty"] == ["Category 3 / Escalate if"]
    st = playbook_status(_playbook(n_cats=9))
    assert not st["complete"] and st["problems"] == ["9 category headings, expected 10"]
    missing = _playbook().replace("### Acceptable fallback\nText for 0 Acceptable fallback.\n", "")
    assert playbook_status(missing)["empty"] == ["Category 0 / Acceptable fallback"]


def test_scaffold_playbook_lists_every_empty_heading():
    st = playbook_status((ROOT / "data" / "playbook.md").read_text(encoding="utf-8"))
    assert st["filled"] == 0 and len(st["empty"]) == 30 and st["empty"][0] == "Cap On Liability / Preferred position"
