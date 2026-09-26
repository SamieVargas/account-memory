"""EDGAR client and parsers against fixtures: nothing here touches sec.gov."""

import gzip
import json

import pytest

from core import edgar as E


class FakeResponse:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.content, self.headers = status, body, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.responses.pop(0)


def test_client_requires_a_declared_user_agent(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="EDGAR_USER_AGENT"):
        E.EdgarClient(cache_dir=tmp_path)
    with pytest.raises(ValueError):
        E.EdgarClient("A Person a@example.com", rate=E.PUBLISHED_MAX_RATE + 1, cache_dir=tmp_path)


def test_client_caches_by_url_and_sends_the_user_agent(tmp_path):
    s = FakeSession([FakeResponse(200, b'{"a": 1}'), FakeResponse(404)])
    c = E.EdgarClient("A Person a@example.com", cache_dir=tmp_path, session=s, rate=10)
    assert c.json("https://data.sec.gov/x") == {"a": 1}
    assert c.json("https://data.sec.gov/x") == {"a": 1}
    assert c.get("https://data.sec.gov/missing") is None
    assert c.get("https://data.sec.gov/missing") is None
    assert len(s.calls) == 2 and s.calls[0][1]["User-Agent"] == "A Person a@example.com"
    assert c.stats == {"cache_hits": 2, "requests": 2, "errors": 0}
    off = E.EdgarClient(cache_dir=tmp_path, offline=True)
    assert off.json("https://data.sec.gov/x") == {"a": 1}
    with pytest.raises(LookupError):
        off.get("https://data.sec.gov/never")


def test_client_backs_off_on_429(tmp_path, monkeypatch):
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    s = FakeSession([FakeResponse(429), FakeResponse(200, b"ok")])
    c = E.EdgarClient("A Person a@example.com", cache_dir=tmp_path, session=s)
    assert c.get("https://www.sec.gov/y") == b"ok" and c.stats["errors"] == 1


def test_compact_key_matches_squashed_titles():
    assert E.compact_key("LIMEENERGYCO") == E.compact_key("Lime Energy Co.")
    assert E.compact_key("WHITESMOKE,INC") == E.compact_key("WhiteSmoke, Inc.")
    assert E.compact_key("The Coca-Cola Company") == E.compact_key("COCACOLACO")


def test_resolve_name_order_and_thresholds():
    tickers = E.NameIndex([{"cik": 1, "name": "Lime Energy Co."}, {"cik": 2, "name": "Veoneer, Inc."}])
    lookup = E.NameIndex([{"cik": 3, "name": "CENTRACK INTERNATIONAL INC"}, {"cik": 4, "name": "ADAMS GOLF INC"}])
    assert E.resolve_name("LIMEENERGYCO", tickers, lookup)["method"] == "tickers_exact"
    assert E.resolve_name("CENTRACKINTERNATIONALINC", tickers, lookup) | {} == {
        "name": "CENTRACKINTERNATIONALINC", "cik": 3, "matched_name": "CENTRACK INTERNATIONAL INC", "method": "edgar_name_index_exact", "score": 1.0}
    near = E.resolve_name("ADAMSGOLFINCORPORATED X", tickers, lookup)
    assert near["cik"] is None
    none = E.resolve_name("Nothing Like It LLC", tickers, lookup)
    assert none["method"] == "unresolved" and none["review"] == []


def test_ambiguous_exact_name_is_not_a_match():
    idx = E.NameIndex([{"cik": 1, "name": "Acme Corp"}, {"cik": 2, "name": "ACME CORP"}])
    assert idx.exact("Acme Corporation") is None


FILINGS = [
    {"accessionNumber": "0001-10-000001", "filingDate": "2010-03-01", "reportDate": None, "form": "10-K", "primaryDocument": "a.htm"},
    {"accessionNumber": "0001-10-000002", "filingDate": "2010-05-10", "reportDate": None, "form": "10-Q", "primaryDocument": "b.htm"},
    {"accessionNumber": "0001-10-000003", "filingDate": "2010-05-10", "reportDate": None, "form": "8-K", "primaryDocument": "c.htm"},
    {"accessionNumber": "0001-11-000004", "filingDate": "2011-03-02", "reportDate": None, "form": "10-K", "primaryDocument": "d.htm"},
]


def test_parent_filing():
    assert E.parent_filing(FILINGS, "2010-05-10", "8-K")["accession"] == "0001-10-000003"
    assert E.parent_filing(FILINGS, "2010-05-10")["status"] == "ambiguous"
    assert E.parent_filing(FILINGS, "2010-06-01")["status"] == "not_found"
    assert E.parent_filing(FILINGS, None)["status"] == "no_date"
    amended = FILINGS + [{"accessionNumber": "0001-10-000009", "filingDate": "2010-05-10", "reportDate": None, "form": "S-1/A", "primaryDocument": "e.htm"}]
    assert E.parent_filing(amended, "2010-05-10", "S-1A")["accession"] == "0001-10-000009"


def test_nearest_10k_with_gap():
    tk = E.nearest_10k(FILINGS, "2010-11-01")
    assert tk["accessionNumber"] == "0001-11-000004" and tk["gap_days"] == 121
    assert E.nearest_10k([f for f in FILINGS if f["form"] != "10-K"], "2010-01-01") is None


def test_filings_reads_recent_and_older_pages(tmp_path):
    sub = {"filings": {"recent": {k: [f[k] for f in FILINGS[2:]] for k in FILINGS[0]}, "files": [{"name": "CIK0000000001-submissions-001.json"}]}}
    page = {k: [f[k] for f in FILINGS[:2]] for k in FILINGS[0]}
    s = FakeSession([FakeResponse(200, json.dumps(sub).encode()), FakeResponse(200, json.dumps(page).encode())])
    c = E.EdgarClient("A Person a@example.com", cache_dir=tmp_path, session=s)
    rows = E.filings(c, 1)
    assert [r["accessionNumber"] for r in rows] == [f["accessionNumber"] for f in FILINGS]


RISK = "Our business faces many risks. " * 100
TENK = f"""<html><body>
<p>Table of Contents</p><p>Item 1A. Risk Factors 12</p><p>Item 1B. Unresolved Staff Comments 20</p><p>Item 2. Properties 21</p>
<p>Item 1. Business</p><p>We make widgets.</p>
<h2>ITEM 1A. RISK FACTORS</h2><p><b>We depend on one customer.</b></p><p>{RISK}</p>
<h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2><p>None.</p><h2>Item 2. Properties</h2>
<script>var x = 1;</script></body></html>"""


def test_item_1a_skips_the_table_of_contents():
    ex = E.extract_item_1a(E.html_to_text(TENK))
    assert ex["ok"] and ex["text"].startswith("We depend on one customer.") and "UNRESOLVED" not in ex["text"] and "var x" not in ex["text"]


def test_item_1a_failures_are_reported():
    assert E.extract_item_1a("Item 1. Business\nwidgets")["reason"].startswith("no Item 1A")
    by_ref = E.extract_item_1a("Item 1A. Risk Factors\nIncorporated herein by reference to the annual report.\nItem 1B. None")
    assert not by_ref["ok"] and by_ref["reason"] == "incorporated by reference"


def fact(val, start, end, filed, form="10-K", fp="FY", accn="a"):
    return {"val": val, "start": start, "end": end, "filed": filed, "form": form, "fp": fp, "accn": accn}


def test_revenue_series_priority_restatement_and_annual_only():
    facts = {"entityName": "Acme", "facts": {"us-gaap": {
        "SalesRevenueNet": {"units": {"USD": [
            fact(100, "2016-01-01", "2016-12-31", "2017-02-01"),
            fact(105, "2016-01-01", "2016-12-31", "2018-02-01"),  # restated in the next 10-K
            fact(30, "2016-10-01", "2016-12-31", "2017-02-01"),  # a quarter: dropped
            fact(90, "2015-01-01", "2015-12-31", "2016-02-01", form="10-Q"),  # wrong form: dropped
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            fact(120, "2018-01-01", "2018-12-31", "2019-02-01"),
            fact(999, "2016-01-01", "2016-12-31", "2019-02-01"),  # higher priority concept wins for 2016
        ]}},
    }}}
    s = E.revenue_series(facts, 7)
    assert [(r["fiscal_year_end"], r["revenue_usd"], r["concept"]) for r in s["rows"]] == [
        ("2016-12-31", 999, "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("2018-12-31", 120, "RevenueFromContractWithCustomerExcludingAssessedTax")]
    assert s["rows"][0]["row_id"] == "rev_7_2016-12-31"
    only_sales = E.revenue_series({"facts": {"us-gaap": {"SalesRevenueNet": facts["facts"]["us-gaap"]["SalesRevenueNet"]}}}, 7)
    assert [(r["fiscal_year_end"], r["revenue_usd"]) for r in only_sales["rows"]] == [("2016-12-31", 105)]
    assert E.revenue_series(None, 7)["rows"] == []


def test_cik_lookup_parse(tmp_path):
    body = b"!J INC:0001438823:\nLIME ENERGY CO.:0001065860:\nnot a line\n"
    c = E.EdgarClient(cache_dir=tmp_path, offline=True)
    p = c._path(E.CIK_LOOKUP_URL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(body))
    assert E.load_cik_lookup(c) == [{"cik": 1438823, "name": "!J INC"}, {"cik": 1065860, "name": "LIME ENERGY CO."}]


def test_client_honors_retry_after_then_gives_up_without_caching(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr(E.time, "sleep", lambda s: slept.append(s))
    s = FakeSession([FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, b"ok")])
    c = E.EdgarClient("A Person a@example.com", cache_dir=tmp_path, session=s)
    assert c.get("https://www.sec.gov/a") == b"ok" and 7.0 in slept
    s = FakeSession([FakeResponse(503)] * (len(E.BACKOFF_S) + 1))
    c = E.EdgarClient("A Person a@example.com", cache_dir=tmp_path, session=s)
    with pytest.raises(E.EdgarUnavailable):
        c.get("https://www.sec.gov/b")
    assert not c._path("https://www.sec.gov/b").exists() and len(s.calls) == len(E.BACKOFF_S) + 1


def test_client_stops_on_403(tmp_path):
    c = E.EdgarClient("A Person a@example.com", cache_dir=tmp_path, session=FakeSession([FakeResponse(403)]))
    with pytest.raises(E.EdgarBlocked, match="User-Agent"):
        c.get("https://www.sec.gov/c")


def test_nearest_10k_skips_filings_before_item_1a():
    old = [{"accessionNumber": "a", "filingDate": "1998-03-01", "reportDate": "1997-12-31", "form": "10-K", "primaryDocument": ""},
           {"accessionNumber": "b", "filingDate": "2005-12-20", "reportDate": "2005-09-30", "form": "10-K", "primaryDocument": "b.htm"}]
    assert E.nearest_10k(old, "1998-06-01") is None
    assert "before 2005-12-01" in E.ten_k_gap_reason(old)
    assert E.ten_k_gap_reason([]) == "no 10-K on file"
    new = old + [{"accessionNumber": "c", "filingDate": "2006-03-01", "reportDate": "2005-12-31", "form": "10-K", "primaryDocument": "c.htm"}]
    tk = E.nearest_10k(new, "1998-06-01")
    assert tk["accessionNumber"] == "c" and tk["gap_days"] > 2700


def test_exact_anywhere_beats_a_close_spelling_in_tickers():
    tickers = E.NameIndex([{"cik": 1, "name": "Apollo Endosurgeri Inc"}])
    lookup = E.NameIndex([{"cik": 2, "name": "APOLLO ENDOSURGERY INC"}])
    r = E.resolve_name("Apollo Endosurgery", tickers, lookup)
    assert (r["cik"], r["method"]) == (2, "edgar_name_index_exact")


def test_a_different_first_letter_is_not_a_typo():
    lookup = E.NameIndex([{"cik": 5, "name": "SHF ENTERPRISES LLC"}])
    r = E.resolve_name("HfEnterprisesInc", E.NameIndex([]), lookup)
    assert r["cik"] is None and r["review"] == []   # a different start is not even compared
    assert E.same_start("Blackstone GSO Long-Short", "Blackstone Long-Short") and not E.same_start("HF Enterprises", "SHF Enterprises")


def test_ambiguous_exact_goes_to_review_and_blocks_close_spellings():
    lookup = E.NameIndex([{"cik": 10, "name": "APOLLO ENDOSURGERY, INC."}, {"cik": 11, "name": "Apollo Endosurgery Inc"},
                          {"cik": 12, "name": "APOLLO ENDOSURGERY US INC"}])
    r = E.resolve_name("Apollo Endosurgery", E.NameIndex([]), lookup)
    assert r["cik"] is None
    assert {(x["cik"], x["method"]) for x in r["review"]} >= {(10, "edgar_name_index_exact_ambiguous"), (11, "edgar_name_index_exact_ambiguous")}


def test_item_1a_not_provided_is_labelled_with_its_text():
    text = "Item 1A. Risk Factors\nAs a smaller reporting company, we are not required to provide the information required by this Item.\nItem 1B. None"
    ex = E.extract_item_1a(text)
    assert not ex["ok"] and ex["reason"].startswith("not provided") and ex["snippet"].startswith("As a smaller reporting company")
    short = E.extract_item_1a("Item 1A. Risk Factors\nSee page 12.\nItem 2. Properties")
    assert short["reason"] == "section is 12 chars" and short["snippet"] == "See page 12."
