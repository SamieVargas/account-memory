"""The golden-set helper and validator, on fixture data. Neither may import
the retriever or an embedder."""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core import cuad as C
from core import golddata as G

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CG = _load("check_golden", "evals/check_golden.py")
GH = _load("golden_helper", "scripts/golden_helper.py")

TEXT = ("SUPPLY AGREEMENT dated January 5, 2010. Governed by the laws of the State of Texas.\n"
        "Either party's liability shall not exceed  the fees paid in the prior twelve months.")
RISK = "We depend on a few customers.\nLoss of any major customer would reduce our revenue."
PLAYBOOK = "## Cap On Liability\n\n### Preferred position\nCap at twelve months of fees.\n"


def _record():
    entry = {"title": "ACME_01_06_2010-EX-10.1-SUPPLY AGREEMENT", "paragraphs": [{"context": TEXT, "qas": [
        {"id": "x__Agreement Date", "question": "q", "answers": [{"text": "January 5, 2010", "answer_start": TEXT.index("January")}]},
        {"id": "x__Governing Law", "question": "q", "answers": [{"text": "Governed by the laws of the State of Texas.", "answer_start": TEXT.index("Governed")}]},
        {"id": "x__Cap On Liability", "question": "q", "answers": [{"text": TEXT[TEXT.index("Either"):], "answer_start": TEXT.index("Either")}]},
    ]}]}
    return C.build_record(entry)


@pytest.fixture
def data(monkeypatch):
    rec = _record()
    monkeypatch.setattr(G, "selected_records", lambda candidates=False: [rec])
    monkeypatch.setattr(G, "risk_entries", lambda: [{"cik": 42, "accession": "0000000042-10-000002", "doc_id": "rf_42_000000004210000002", "text": RISK}])
    monkeypatch.setattr(G, "revenue_rows", lambda: [{"row_id": "rev_42_2009-12-31", "cik": 42, "entity": "Acme", "fiscal_year_end": "2009-12-31",
                                                     "revenue_usd": 5, "concept": "Revenues", "filed": "2010-02-20"}])
    monkeypatch.setattr(G, "accounts", lambda: {rec["id"]: {"account": "Acme Widgets Inc", "cik": 42}})
    monkeypatch.setattr(G, "playbook_text", lambda: PLAYBOOK)
    return rec


def _q(i, kind, **kw):
    base = {"id": f"{kind}-{i:02d}", "kind": kind, "question": f"{kind} question {i}?", "scope": {},
            "gold_passages": [], "gold_rows": [], "expected_contract_ids": [], "expected_facts": [], "expected_verdict": None, "notes": ""}
    return {**base, **kw}


def valid_set(rec):
    cid = rec["id"]
    s = TEXT.index("Either")
    cap = {"doc_id": cid, "start": s, "end": len(TEXT), "category": "Cap On Liability"}
    risk = {"doc_id": "rf_42_000000004210000002", "start": 0, "end": 29}
    pb = {"doc_id": "playbook", "start": 0, "end": len(PLAYBOOK)}
    qs = [_q(i, "clause", scope={"contract_id": cid}, gold_passages=[cap], expected_facts=["the fees paid in the prior twelve months"]) for i in range(10)]
    qs += [_q(i, "filing", gold_passages=[risk]) for i in range(6)]
    qs += [_q(i, "filter", expected_contract_ids=[cid]) for i in range(7)]
    qs += [_q(i, "aggregate", expected_facts=["5"], gold_rows=["rev_42_2009-12-31"] if i < 3 else []) for i in range(7)]
    qs += [_q(i, "playbook_check", gold_passages=[cap, pb], gold_rows=["rev_42_2009-12-31"] if i == 0 else [], expected_verdict="matches") for i in range(5)]
    qs += [_q(i, "unanswerable") for i in range(5)]
    return qs


def write(tmp_path, qs):
    p = tmp_path / "golden.jsonl"
    p.write_text("\n".join(json.dumps(q) for q in qs) + "\n", encoding="utf-8")
    return p


def test_valid_set_passes(data, tmp_path):
    assert CG.check(write(tmp_path, valid_set(data))) == []
    assert CG.main([str(write(tmp_path, valid_set(data)))]) == 0


def test_each_rule_is_enforced(data, tmp_path):
    qs = valid_set(data)
    qs[0]["expected_facts"] = ["forty-two dollars"]
    qs[1]["gold_passages"] = [{**qs[1]["gold_passages"][0], "end": 10 ** 6}]
    qs[2]["gold_passages"] = [{"doc_id": data["id"], "start": 0, "end": 10, "category": "Cap On Liability"}]
    qs[3]["scope"] = {"contract_id": "c_nothere"}
    qs[10]["gold_passages"] = [{"doc_id": data["id"], "start": 0, "end": 5}]
    qs[16]["expected_contract_ids"] = []
    qs[23]["gold_rows"] = ["rev_1_1999-12-31"]
    qs[30]["expected_verdict"] = "fine"
    qs[35]["gold_rows"] = ["rev_42_2009-12-31"]
    qs.append(dict(qs[-1]))
    del qs[5]["notes"]
    problems = "\n".join(CG.check(write(tmp_path, qs)))
    for needle in ("'forty-two dollars' is not inside any gold passage", "outside 0..", "overlaps no CUAD span of Cap On Liability",
                   "c_nothere is not in the selection", "a filing passage must be in an Item 1A extraction",
                   "a filter question needs expected_contract_ids", "revenue row rev_1_1999-12-31 does not exist",
                   "expected_verdict must be one of", "an unanswerable question has no gold", "appears 2 times",
                   "mix: 6 unanswerable questions, expected 5", "missing field notes"):
        assert needle in problems, needle
    assert CG.main([str(write(tmp_path, qs))]) == 1


def test_mix_minimums(data, tmp_path):
    qs = valid_set(data)
    for q in qs:
        if q["kind"] in ("aggregate", "playbook_check"):
            q["gold_rows"] = []
    problems = "\n".join(CG.check(write(tmp_path, qs)))
    assert "0 aggregate questions cite revenue rows" in problems and "0 cross-document playbook checks" in problems


def test_bad_json_and_missing_file(data, tmp_path):
    p = tmp_path / "golden.jsonl"
    p.write_text("{not json\n", encoding="utf-8")
    assert "line 1: not JSON" in "\n".join(CG.check(p))
    assert CG.check(tmp_path / "none.jsonl") == [f"{tmp_path / 'none.jsonl'} does not exist"]


def run_helper(*argv):
    out = io.StringIO()
    GH.main(list(argv), out=out)
    return out.getvalue()


def test_helper_commands(data):
    cid = data["id"]
    rows = run_helper("contracts").splitlines()
    assert rows[1].split("\t")[:5] == [cid, "ACME", "Acme Widgets Inc", "42", "supply"]
    assert "Texas" in rows[1] and "Cap On Liability" in rows[1]
    spans = run_helper("spans", cid, "cap on liability").strip().split("\t")
    assert spans[:3] == ["Cap On Liability", str(TEXT.index("Either")), str(len(TEXT))]
    hit = run_helper("find", cid, "not exceed the fees").split("\t")
    s, e = int(hit[0]), int(hit[1])
    assert TEXT[s:e] == "not exceed  the fees"
    assert run_helper("find", cid, "nowhere to be found").strip() == "not found"
    assert "rev_42_2009-12-31\t42\tAcme" in run_helper("revenue", "42")
    risk = run_helper("risk", "42", "major customer").split("\t")
    assert risk[0] == "rf_42_000000004210000002" and RISK[int(risk[1]):int(risk[2])] == "major customer"
    table = run_helper("metadata-table").splitlines()
    assert table[0].startswith("contract_id,filer,account,cik,contract_type,agreement_date")
    assert table[1].split(",")[5] == "2010-01-05" and table[1].endswith("Texas")


def test_helper_and_checker_never_load_the_retriever():
    code = ("import sys, importlib.util\n"
            "for name, rel in (('gh', 'scripts/golden_helper.py'), ('cg', 'evals/check_golden.py')):\n"
            "    spec = importlib.util.spec_from_file_location(name, rel); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "bad = [m for m in sys.modules if m in ('core.retrieve', 'core.embeddings', 'core.store', 'chromadb', 'rank_bm25', 'sentence_transformers')]\n"
            "print(','.join(bad))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert out == ""
