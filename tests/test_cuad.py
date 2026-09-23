"""CUAD parsing: titles, dates, durations, jurisdictions, parties, and the
span-to-offset mapping. The release-level checks skip when data/raw/cuad is
absent (run scripts/fetch_cuad.py)."""

import pytest

from core import cuad as C


def test_parse_title_long_short_named():
    t = C.parse_title("LOHACOMPANYLTD_20191209_F-1_EX-10.16_11917878_EX-10.16_SUPPLY AGREEMENT")
    assert (t["filer"], t["filing_date"], t["form"], t["exhibit"], t["title_type"]) == ("LOHACOMPANYLTD", "2019-12-09", "F-1", "EX-10.16", "SUPPLY AGREEMENT")
    t = C.parse_title("LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT")
    assert (t["filer"], t["filing_date"], t["form"], t["title_type"]) == ("LIMEENERGYCO", "1999-09-09", None, "DISTRIBUTOR AGREEMENT")
    t = C.parse_title("MetLife, Inc. - Remarketing Agreement")
    assert (t["filer"], t["filing_date"], t["title_format"]) == ("MetLife, Inc.", None, "named")


def test_contract_type_priority():
    assert C.contract_types("SOFTWARE LICENSE AND MAINTENANCE AGREEMENT")[0] == "maintenance"
    assert C.contract_types("Manufacturing and Supply Agreement")[0] == "supply"
    assert C.contract_types("JOINT FILING AGREEMENT") == ["joint_filing"]


@pytest.mark.parametrize("text,want", [
    ("7th day of September, 1999.", ["1999-09-07"]),
    ("January 24, 2014", ["2014-01-24"]),
    ("October 1,1996", ["1996-10-01"]),
    ("1s t day of March, 2018", ["2018-03-01"]),
    ("12/31/2019", ["2019-12-31"]),
    ("this  day of , 2012", []),
    ("February ____, 2017", []),
    ("9/9/97", []),  # two-digit year: not guessed
    ("[●]", []),
])
def test_dates_in(text, want):
    assert C.dates_in(text) == want


def test_date_field_never_guesses():
    assert C._date_field(["January 1, 1998"])["value"] == "1998-01-01"
    f = C._date_field(["January 1, 1998", "March 3, 1999"])
    assert f["status"] == "unparsed" and "conflicting" in f["reason"]
    assert C._date_field([])["status"] == "absent"


def test_durations():
    assert C.durations_in("renew for successive one-year terms") == ["1 year"]
    assert C.durations_in("at least ninety (90) days prior") == ["90 days"]
    f = C._duration_field(["five (5) year initial term", "renews for one (1) year"])
    assert f["status"] == "unparsed" and "several" in f["reason"]


@pytest.mark.parametrize("text,want", [
    ("governed by the laws of the State of New York, without regard", "New York"),
    ("THE LAWS OF THE STATE OF DELAWARE", "Delaware"),
    ("This Agreement is governed by English law", "England"),
    ("governed by the laws of the People's Republic of China", "China"),
    ("in accordance with Ohio law.", "Ohio"),
    ("the laws and judicial decisions of the State of Florida", "Florida"),
    ("the laws of [***]", None),
])
def test_jurisdiction(text, want):
    assert C.jurisdiction_in(text) == want


def test_entity_parties_drop_roles():
    got = C.entity_parties(["Distributor", "Electric City Corp.", "the Company", "Electric City Corp", 'both referred to jointly as the "Parties"'])
    assert got == ["Electric City Corp."]


def test_build_record_maps_offsets_and_flags_unmapped():
    text = "AGREEMENT made January 5, 2010 between Acme Widgets, Inc. and Beta LLC. Governed by the laws of Texas."
    entry = {"title": "ACME_01_06_2010-EX-10.1-SUPPLY AGREEMENT", "paragraphs": [{"context": text, "qas": [
        {"id": "x__Agreement Date", "question": "q", "answers": [{"text": "January 5, 2010", "answer_start": text.index("January")}]},
        {"id": "x__Parties", "question": "q", "answers": [{"text": "Acme Widgets, Inc.", "answer_start": text.index("Acme")}]},
        {"id": "x__Governing Law", "question": "q", "answers": [{"text": "Governed by the laws of Texas.", "answer_start": text.index("Governed")}]},
        {"id": "x__Cap On Liability", "question": "q", "answers": [{"text": "not in the text", "answer_start": 3}]},
    ]}]}
    r = C.build_record(entry)
    assert r["contract_type"] == "supply" and r["filing_date"] == "2010-01-06"
    assert r["metadata"]["agreement_date"]["value"] == "2010-01-05"
    assert r["metadata"]["governing_law"]["value"] == "Texas"
    assert all(text[s["start"]:s["end"]] for s in r["spans"])
    assert len(r["unmapped_spans"]) == 1 and r["unmapped_spans"][0]["category"] == "Cap On Liability"


needs_release = pytest.mark.skipif(not (C.RAW / "CUADv1.json").exists(), reason="CUAD not fetched")


@needs_release
def test_release_loads_with_every_span_mapped():
    rs = C.load_contracts()
    assert len(rs) == 510
    assert sum(len(r["spans"]) for r in rs) == 13823
    assert sum(len(r["unmapped_spans"]) for r in rs) == 0
    for r in rs[:50]:
        for s in r["spans"]:
            assert 0 <= s["start"] < s["end"] <= len(r["text"])


@needs_release
def test_questions_cover_41_categories():
    q = C.questions(C.load_release())
    assert len(q) == 41 and "Cap On Liability" in q["Cap On Liability"]
