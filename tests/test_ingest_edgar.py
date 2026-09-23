"""scripts/ingest_edgar.py end to end on a seeded cache: one synthetic
contract, every EDGAR response pre-cached, the client offline."""

import gzip
import importlib.util
import json
from pathlib import Path

from core import cuad as C
from core import edgar as E
from tests.test_edgar import TENK

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ingest_edgar", ROOT / "scripts" / "ingest_edgar.py")
ing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ing)


def seed(cache, url, body):
    c = E.EdgarClient(cache_dir=cache, offline=True)
    p = c._path(url)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(body if isinstance(body, bytes) else json.dumps(body).encode()))


def test_ingest_edgar_offline(tmp_path, monkeypatch):
    text = "SUPPLY AGREEMENT dated March 1, 2010 between Acme Widgets, Inc. and Beta Parts LLC."
    entry = {"title": "ACMEWIDGETSINC_20100305_8-K_EX-10.1_1_EX-10.1_SUPPLY AGREEMENT", "paragraphs": [{"context": text, "qas": [
        {"id": "x__Agreement Date", "question": "q", "answers": [{"text": "March 1, 2010", "answer_start": text.index("March")}]},
        {"id": "x__Parties", "question": "q", "answers": [{"text": "Beta Parts LLC", "answer_start": text.index("Beta")}]}]}]}
    rec = C.build_record(entry)
    cache = tmp_path / "cache"
    seed(cache, E.TICKERS_URL, {"0": {"cik_str": 42, "ticker": "ACME", "title": "Acme Widgets Inc"}})
    seed(cache, E.CIK_LOOKUP_URL, b"BETA PARTS LLC:0000000077:\n")
    rows = [{"accessionNumber": "0000000042-10-000001", "filingDate": "2010-03-05", "reportDate": None, "form": "8-K", "primaryDocument": "k8.htm"},
            {"accessionNumber": "0000000042-10-000002", "filingDate": "2010-02-20", "reportDate": None, "form": "10-K", "primaryDocument": "tenk.htm"}]
    seed(cache, E.SUBMISSIONS_URL.format(cik=42), {"filings": {"recent": {k: [r[k] for r in rows] for k in rows[0]}, "files": []}})
    seed(cache, E.archive_url(42, "0000000042-10-000002", "tenk.htm"), TENK.encode())
    seed(cache, E.FACTS_URL.format(cik=42), {"entityName": "Acme", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"val": 5, "start": "2009-01-01", "end": "2009-12-31", "filed": "2010-02-20", "form": "10-K", "fp": "FY", "accn": "x"}]}}}}})

    monkeypatch.setattr(ing, "load_contracts", lambda: [rec])
    monkeypatch.setattr(ing, "DERIVED", tmp_path / "derived")
    monkeypatch.setattr(ing, "REVIEW", tmp_path / "cik_review.csv")
    monkeypatch.setattr(ing, "ROOT", tmp_path)
    (tmp_path / "evals" / "results").mkdir(parents=True)
    assert ing.main(["--offline", "--cache-dir", str(cache)]) == 0

    acc = json.loads((tmp_path / "derived" / "accounts.json").read_text())[0]
    assert acc["cik"] == 42 and acc["account_method"] == "tickers_exact"
    assert [r["method"] for r in acc["resolutions"]] == ["tickers_exact", "edgar_name_index_exact"]
    assert acc["parent_filing"]["accession"] == "0000000042-10-000001"
    assert acc["ten_k"]["gap_days"] == -9 and acc["ten_k"]["item_1a_ok"]
    risk = json.loads((tmp_path / "derived" / "risk_factors.json").read_text())
    assert len(risk) == 1 and risk[0]["text"].startswith("We depend on one customer.")
    rev = json.loads((tmp_path / "derived" / "revenue.json").read_text())
    assert rev[0]["rows"][0]["row_id"] == "rev_42_2009-12-31"
    report = next((tmp_path / "evals" / "results").glob("ingest-edgar-*.md")).read_text()
    assert "| Contracts with a resolved account | 1 of 1 (100%) |" in report
    assert "Item 1A extractions succeeded / failed | 1 / 0" in report
