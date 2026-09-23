"""CUAD v1, read from its QA-format JSON and turned into contract records.

Each record carries the full contract text (CUAD's `context`), every labelled
answer span as character offsets into that text, and metadata normalized in
code from CUAD's own labels. Normalization never guesses: a label that does
not parse cleanly (a garbled date, two different durations, a governing-law
clause naming no jurisdiction we recognize) is kept raw and reported as
unparsed.

The title carries the filing it came from: the filer's name, the filing date,
and for about a third of the corpus the form type and exhibit number. Those
are what the EDGAR ingest uses to find the account and the parent filing.
"""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "cuad"

# The 41 categories, in the release's order; checked against the data on load.
CATEGORIES = (
    "Document Name", "Parties", "Agreement Date", "Effective Date", "Expiration Date", "Renewal Term",
    "Notice Period To Terminate Renewal", "Governing Law", "Most Favored Nation", "Non-Compete", "Exclusivity",
    "No-Solicit Of Customers", "Competitive Restriction Exception", "No-Solicit Of Employees", "Non-Disparagement",
    "Termination For Convenience", "Rofr/Rofo/Rofn", "Change Of Control", "Anti-Assignment", "Revenue/Profit Sharing",
    "Price Restrictions", "Minimum Commitment", "Volume Restriction", "Ip Ownership Assignment", "Joint Ip Ownership",
    "License Grant", "Non-Transferable License", "Affiliate License-Licensor", "Affiliate License-Licensee",
    "Unlimited/All-You-Can-Eat-License", "Irrevocable Or Perpetual License", "Source Code Escrow",
    "Post-Termination Services", "Audit Rights", "Uncapped Liability", "Cap On Liability", "Liquidated Damages",
    "Warranty Duration", "Insurance", "Covenant Not To Sue", "Third Party Beneficiary",
)
# Categories whose spans are metadata rather than clauses to retrieve.
METADATA_CATEGORIES = CATEGORIES[:8]

# Contract type from the title and the Document Name label: the first keyword
# found, in this priority order. Priority breaks ties like "SOFTWARE LICENSE
# AND MAINTENANCE AGREEMENT" (maintenance) or "MANUFACTURING AND SUPPLY"
# (supply); every matched type is also kept in contract_types.
TYPE_KEYWORDS = (
    ("outsourcing", r"outsourc"),
    ("hosting", r"hosting"),
    ("maintenance", r"maintenance|support and"),
    ("reseller", r"resell|remarketing"),
    ("distributor", r"distribut"),
    ("supply", r"supply"),
    ("manufacturing", r"manufactur"),
    ("license", r"licens"),
    ("services", r"\bservic(?:e|es|ing)\b"),
    ("consulting", r"consult"),
    ("agency", r"agency"),
    ("franchise", r"franchis"),
    ("sponsorship", r"sponsor"),
    ("endorsement", r"endorse"),
    ("joint_venture", r"joint venture"),
    ("strategic_alliance", r"strategic alliance"),
    ("collaboration", r"collaborat|cooperation"),
    ("co_branding", r"co-?branding"),
    ("affiliate", r"affiliate"),
    ("promotion", r"promotion"),
    ("marketing", r"marketing"),
    ("development", r"development"),
    ("non_compete", r"non[- ]?compet"),
    ("joint_filing", r"joint filing"),
    ("transportation", r"transportation"),
    ("ip", r"intellectual property"),
)
# The commercial-relationship types the subset is drawn from (data/SELECTION.md).
COMMERCIAL_TYPES = ("license", "services", "outsourcing", "supply", "manufacturing", "distributor", "reseller",
                    "maintenance", "hosting")

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
NUMBER_WORDS.update({"thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50, "sixty": 60, "seventy-five": 75,
                     "ninety": 90, "one hundred twenty": 120, "one hundred eighty": 180})

US_STATES = (
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho Illinois "
    "Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri "
    "Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia Washington "
    "Wisconsin Wyoming").split() + ["New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
                                    "North Dakota", "Rhode Island", "South Carolina", "South Dakota", "West Virginia",
                                    "District of Columbia"]
COUNTRIES = ("England and Wales", "England", "Hong Kong", "Singapore", "Ontario", "British Columbia", "Alberta",
             "Quebec", "Canada", "Israel", "Switzerland", "Germany", "France", "Netherlands", "Ireland", "Japan",
             "Sweden", "Taiwan", "Cayman Islands", "Bermuda", "China", "India", "Australia", "Korea", "Italy", "Spain")


def contract_id(title: str) -> str:
    """Stable short id from the title, which is unique in the release."""
    return "c_" + hashlib.sha1(title.strip().encode("utf-8")).hexdigest()[:10]


# --- titles ----------------------------------------------------------------

_TITLE_LONG = re.compile(r"^(?P<filer>.+?)_(?P<date>\d{8})_(?P<form>[^_]+)_(?P<exhibit>EX[^_]*)_(?P<doc>\d+)_EX[^_]*_(?P<type>.*)$")
_TITLE_SHORT = re.compile(r"^(?P<filer>.+?)_(?P<m>\d{2})_(?P<d>\d{2})_(?P<y>\d{4})-(?P<exhibit>EX[^-]*(?:-\d[^-]*)?)-(?P<type>.*)$")
_TITLE_NAMED = re.compile(r"^(?P<filer>.+?)\s+-\s+(?P<type>.+)$")


def parse_title(title: str) -> dict:
    """Filer, filing date, form, exhibit and the type words, where the title
    carries them. The long form (about a third of the corpus) names the form
    type; the short form names only the date; about 30 titles are
    'Company - Agreement Name' and carry neither."""
    t = title.strip()
    out = {"filer": None, "filing_date": None, "form": None, "exhibit": None, "title_type": None, "title_format": "other"}
    m = _TITLE_LONG.match(t)
    if m:
        d = m["date"]
        out.update(filer=m["filer"], filing_date=_iso(int(d[:4]), int(d[4:6]), int(d[6:])), form=m["form"],
                   exhibit=m["exhibit"], title_type=m["type"], title_format="long")
        return out
    m = _TITLE_SHORT.match(t)
    if m:
        out.update(filer=m["filer"], filing_date=_iso(int(m["y"]), int(m["m"]), int(m["d"])), exhibit=m["exhibit"],
                   title_type=m["type"], title_format="short")
        return out
    m = _TITLE_NAMED.match(t)
    if m:
        out.update(filer=m["filer"].strip(), title_type=m["type"].strip(), title_format="named")
        return out
    out["title_type"] = t
    return out


def contract_types(*texts) -> list[str]:
    blob = " ".join(t for t in texts if t).lower().replace("_", " ")
    return [name for name, pat in TYPE_KEYWORDS if re.search(pat, blob)]


# --- dates, durations, jurisdictions ---------------------------------------

def _iso(y, m, d):
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


_ORD = r"(\d{1,2})(?:st|nd|rd|th)?"
_MON = r"([A-Za-z]{3,9})\.?"
_DATE_PATTERNS = (
    (re.compile(rf"\b{_MON}\s+{_ORD},?\s*(\d{{4}})\b"), lambda m: (m[3], m[1], m[2])),
    (re.compile(rf"\b{_ORD}\s+(?:day\s+of\s+)?{_MON},?\s+(\d{{4}})\b", re.I), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), lambda m: (m[3], m[1], m[2])),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (m[1], m[2], m[3])),
)


def dates_in(text: str) -> list[str]:
    """Every full calendar date written in the text, as ISO strings. A date
    missing its day or its year is not a date here. The one repair made is
    CUAD's text-extraction split inside an ordinal ('1s t', '10t h'), which
    changes no digit."""
    t = re.sub(r"\s+", " ", text or "")
    t = re.sub(r"\b(\d{1,2})(s|n|r|t) (t|d|h)\b", r"\1\2\3", t)
    found = []
    for pat, parts in _DATE_PATTERNS:
        for m in pat.finditer(t):
            y, mon, d = parts(m)
            mon_n = int(mon) if str(mon).isdigit() else MONTHS.get(str(mon).lower())
            if mon_n is None:
                continue
            iso = _iso(int(y), mon_n, int(d))
            if iso and iso not in found:
                found.append(iso)
    return found


_NUM = r"(\d+|" + "|".join(sorted((re.escape(w) for w in NUMBER_WORDS), key=len, reverse=True)) + r")"
_DURATION = re.compile(rf"\b{_NUM}(?:\s*\(\s*\d+\s*\))?[\s-]*(?:calendar\s+|business\s+|consecutive\s+)?(year|month|day|week)s?\b", re.I)


def durations_in(text: str) -> list[str]:
    """Distinct durations like '90 days' or '1 year', in order of first appearance."""
    out = []
    for m in _DURATION.finditer(re.sub(r"\s+", " ", text or "")):
        tok = m[1].lower()
        n = int(tok) if tok.isdigit() else NUMBER_WORDS.get(tok)
        if n is None:
            continue
        unit = m[2].lower()
        s = f"{n} {unit}{'' if n == 1 else 's'}"
        if s not in out:
            out.append(s)
    return out


ADJECTIVAL_LAW = {"english": "England", "new york": "New York", "delaware": "Delaware", "california": "California",
                  "israeli": "Israel", "swiss": "Switzerland", "german": "Germany", "french": "France", "dutch": "Netherlands",
                  "irish": "Ireland", "japanese": "Japan", "chinese": "China", "canadian": "Canada", "singapore": "Singapore"}


def jurisdiction_in(text: str):
    """The jurisdiction a governing-law clause names: the recognized place
    right after 'laws of', else 'English law' style, else None."""
    t = re.sub(r"\s+", " ", text or "")
    t = re.sub(r"People'?s Republic of China|\bPRC\b", "China", t)
    t = re.sub(r"\bR\.?O\.?C\.?(?=\W|$)", "Taiwan", t)
    m = re.search(r"laws?(?:\s+and\s+[a-z ]{1,30}?)?\s+(?:of|in)\s+(?:the\s+)?(?:State|Commonwealth|Province|Republic|Kingdom)?\s*(?:of\s+)?(.{0,60})", t, re.I)
    if m:
        for name in sorted(US_STATES + list(COUNTRIES), key=len, reverse=True):
            if re.match(rf"{re.escape(name)}\b", m[1], re.I):
                return name
    m = re.search(r"\b([A-Za-z]+(?: [A-Za-z]+)?) law\b", t, re.I)
    if m:
        for name in sorted(US_STATES + list(COUNTRIES), key=len, reverse=True):
            if m[1].lower().endswith(name.lower()):
                return name
        for k, v in ADJECTIVAL_LAW.items():
            if m[1].lower().endswith(k):
                return v
    return None


# --- parties ---------------------------------------------------------------

_ENTITY_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|llc|l\.l\.c|ltd|limited|lp|l\.p|llp|plc|"
                            r"gmbh|ag|s\.a|sa|n\.v|nv|b\.v|bv|ab|as|s\.p\.a|s\.r\.l|pty|pte|trust|bank|holdings|group|"
                            r"partners|university)\b\.?", re.I)
# For deciding a span names an entity: the short suffixes only in capitals,
# so "as" and "co" in running text do not count.
_ENTITY_MARK = re.compile(r"\b(?:(?i:inc|incorporated|corp|corporation|company|llc|l\.l\.c|ltd|limited|llp|plc|gmbh|"
                          r"holdings|trust|bank|university)\b\.?|(?:AG|AB|AS|SA|S\.A|NV|N\.V|BV|B\.V|LP|L\.P|Co|CO|PLC)\b)")


def normalize_name(name: str) -> str:
    """Lowercase, punctuation and corporate suffixes stripped: the key CIK
    resolution matches on."""
    s = re.sub(r"[\"'“”‘’()]", " ", name or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[.,]", " ", s)
    words = [w for w in s.split() if not _ENTITY_SUFFIX.fullmatch(w)]
    words = [w for w in words if w not in ("the", "a")]
    return " ".join(words).strip()


def entity_parties(spans: list[str]) -> list[str]:
    """The party spans that name an entity rather than a defined role
    ("Distributor", "the Company"): the ones with a corporate suffix, or of
    three or more capitalized words. Deduped on the normalized key."""
    out, seen = [], set()
    for raw in spans:
        s = re.sub(r"\s+", " ", raw).strip().strip('"“”,;').strip()
        if not s or len(s) > 120:
            continue
        caps = [w for w in re.findall(r"[A-Za-z][\w&.'-]*", s) if w[0].isupper()]
        if not (_ENTITY_MARK.search(s) or len(caps) >= 3):
            continue
        key = normalize_name(s)
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    return out


# --- records ---------------------------------------------------------------

def _field(value, raw, status, reason=None):
    return {"value": value, "raw": raw, "status": status, **({"reason": reason} if reason else {})}


def _date_field(spans):
    if not spans:
        return _field(None, [], "absent")
    found = []
    for s in spans:
        for d in dates_in(s):
            if d not in found:
                found.append(d)
    if len(found) == 1:
        return _field(found[0], spans, "parsed")
    return _field(None, spans, "unparsed", "no full calendar date in the label" if not found else f"conflicting dates {found}")


def _duration_field(spans):
    if not spans:
        return _field(None, [], "absent")
    found = []
    for s in spans:
        for d in durations_in(s):
            if d not in found:
                found.append(d)
    if len(found) == 1:
        return _field(found[0], spans, "parsed")
    return _field(None, spans, "unparsed", "no duration in the label" if not found else f"several durations {found}")


def _expiration_field(spans):
    """An expiration date is parsed only when the label writes one calendar
    date; 'three years from the Effective Date' stays unparsed (the term is
    kept raw), because computing it would be a guess about the start."""
    return _date_field(spans)


def _law_field(spans):
    if not spans:
        return _field(None, [], "absent")
    found = []
    for s in spans:
        j = jurisdiction_in(s)
        if j and j not in found:
            found.append(j)
    if len(found) == 1:
        return _field(found[0], spans, "parsed")
    return _field(None, spans, "unparsed", "no recognized jurisdiction" if not found else f"several jurisdictions {found}")


def build_record(entry: dict) -> dict:
    title = entry["title"]
    para = entry["paragraphs"][0]
    text = para["context"]
    spans, questions, by_cat = [], {}, {}
    unmapped = []
    for qa in para["qas"]:
        cat = qa["id"].split("__", 1)[1]
        questions[cat] = qa["question"]
        for a in qa["answers"]:
            start, end = a["answer_start"], a["answer_start"] + len(a["text"])
            if text[start:end] != a["text"]:
                unmapped.append({"category": cat, "text": a["text"][:80], "answer_start": start})
                continue
            spans.append({"category": cat, "start": start, "end": end})
            by_cat.setdefault(cat, []).append(a["text"])
    t = parse_title(title)
    doc_name = (by_cat.get("Document Name") or [None])[0]
    types = contract_types(t["title_type"], doc_name)
    party_spans = by_cat.get("Parties", [])
    meta = {
        "parties": {"value": entity_parties(party_spans), "raw": party_spans, "status": "parsed" if party_spans else "absent"},
        "agreement_date": _date_field(by_cat.get("Agreement Date", [])),
        "effective_date": _date_field(by_cat.get("Effective Date", [])),
        "expiration_date": _expiration_field(by_cat.get("Expiration Date", [])),
        "renewal_term": _duration_field(by_cat.get("Renewal Term", [])),
        "notice_period_to_terminate_renewal": _duration_field(by_cat.get("Notice Period To Terminate Renewal", [])),
        "governing_law": _law_field(by_cat.get("Governing Law", [])),
    }
    return {"id": contract_id(title), "title": title, "doc_type": "contract", "text": text, "chars": len(text),
            "filer": t["filer"], "filing_date": t["filing_date"], "form": t["form"], "exhibit": t["exhibit"],
            "title_format": t["title_format"], "document_name": doc_name, "contract_type": types[0] if types else None,
            "contract_types": types, "metadata": meta, "spans": sorted(spans, key=lambda s: (s["start"], s["category"])),
            "unmapped_spans": unmapped}


def load_release(raw_dir: Path = RAW) -> dict:
    path = Path(raw_dir) / "CUADv1.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run python scripts/fetch_cuad.py")
    return json.loads(path.read_text(encoding="utf-8"))


def questions(release: dict) -> dict:
    """CUAD's own question text per category, the query for the automatic set."""
    qas = release["data"][0]["paragraphs"][0]["qas"]
    out = {qa["id"].split("__", 1)[1]: qa["question"] for qa in qas}
    if tuple(out) != CATEGORIES:
        raise ValueError("the release's categories differ from CATEGORIES; update core/cuad.py")
    return out


def load_contracts(raw_dir: Path = RAW) -> list[dict]:
    release = load_release(raw_dir)
    questions(release)
    records = [build_record(e) for e in release["data"]]
    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("contract ids collide; titles are not unique")
    return records
