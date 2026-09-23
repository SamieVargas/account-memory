"""SEC EDGAR: company resolution, filing history, Item 1A risk factors, and
annual revenue from XBRL company facts.

Fair access, in code:
  - Every request carries a declared User-Agent (EDGAR_USER_AGENT, "Name
    email"); the client refuses to start without one.
  - Requests are spaced to RATE per second, well under the SEC's published
    ceiling (PUBLISHED_MAX_RATE; confirm it on sec.gov's "Accessing EDGAR
    Data" page before the first run, and lower RATE if it has changed).
  - Every response is cached on disk keyed by URL, so a rerun reads disk and
    sends nothing. The cache lives in data/cache/edgar and is git-ignored.

Everything EDGAR serves is public-domain government data; the page still
names it as the source.
"""

import difflib
import gzip
import hashlib
import json
import os
import re
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "edgar"

PUBLISHED_MAX_RATE = 10  # requests per second, per sec.gov fair-access guidance; re-check before a run
RATE = 4

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CIK_LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

# Name matching. A score is difflib's ratio on the compact keys below. At or
# above ACCEPT a fuzzy match is taken; between REVIEW and ACCEPT it goes to
# data/cik_review.csv for a person to confirm and is not used until then;
# under REVIEW it is dropped. Exact key matches need no threshold.
ACCEPT = 0.94
REVIEW = 0.85

# Revenue concepts, highest priority first. For each fiscal period the first
# concept that reports it wins, and the row records which one did.
REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
    "RevenuesNetOfInterestExpense",
)
ANNUAL_FORMS = ("10-K", "10-K/A", "10-K405", "10-KT")
TEN_K_FORMS = ("10-K", "10-K405")  # Item 1A exists in 10-Ks for fiscal years ending on or after 2005-12-01


class EdgarClient:
    def __init__(self, user_agent=None, *, rate=RATE, cache_dir=CACHE, offline=False, session=None):
        ua = user_agent or os.environ.get("EDGAR_USER_AGENT", "")
        if not offline and not re.search(r"\S+@\S+\.\S+", ua):
            raise RuntimeError("set EDGAR_USER_AGENT to 'Your Name your@email' (SEC fair-access policy)")
        if rate > PUBLISHED_MAX_RATE:
            raise ValueError(f"rate {rate}/s is above the SEC's published {PUBLISHED_MAX_RATE}/s")
        self.user_agent = ua
        self.interval = 1.0 / rate
        self.cache_dir = Path(cache_dir)
        self.offline = offline
        self.session = session
        self._last = 0.0
        self.stats = {"cache_hits": 0, "requests": 0, "errors": 0}

    def _path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".gz")

    def get(self, url: str) -> bytes | None:
        """The body, from the cache when present. None for a 404 (cached too,
        so a missing filing is not asked for twice)."""
        p = self._path(url)
        if p.exists():
            self.stats["cache_hits"] += 1
            body = gzip.decompress(p.read_bytes())
            return None if body == b"__404__" else body
        if self.offline:
            raise LookupError(f"offline and not cached: {url}")
        if self.session is None:
            import requests
            self.session = requests.Session()
        for attempt in range(4):
            wait = self._last + self.interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.stats["requests"] += 1
            r = self.session.get(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}, timeout=60)
            if r.status_code == 404:
                body = b"__404__"
                break
            if r.status_code in (429, 503):
                self.stats["errors"] += 1
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            body = r.content
            break
        else:
            raise RuntimeError(f"gave up on {url} after repeated 429/503")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(gzip.compress(body))
        return None if body == b"__404__" else body

    def json(self, url: str):
        body = self.get(url)
        return None if body is None else json.loads(body)


# --- company resolution ------------------------------------------------------

_SUFFIXES = ("incorporated", "corporation", "company", "holdings", "limited", "inc", "corp", "llc", "ltd", "plc", "lp",
             "llp", "co", "sa", "ag", "nv", "bv", "gmbh")


def compact_key(name: str) -> str:
    """Letters and digits only, lowercased, one trailing corporate suffix
    removed. CUAD titles squash names ('LIMEENERGYCO'), so matching is done on
    this form on both sides."""
    s = re.sub(r"[^a-z0-9]", "", (name or "").lower().replace("&", "and"))
    if s.startswith("the") and len(s) > 6:
        s = s[3:]
    for suf in _SUFFIXES:
        if s.endswith(suf) and len(s) - len(suf) >= 4:
            return s[: -len(suf)]
    return s


def load_tickers(client: EdgarClient) -> list[dict]:
    data = client.json(TICKERS_URL) or {}
    return [{"cik": int(v["cik_str"]), "name": v["title"], "ticker": v.get("ticker")} for v in data.values()]


def load_cik_lookup(client: EdgarClient) -> list[dict]:
    """EDGAR's full company-name index (every filer, current or not), as
    NAME:CIK: lines. This is the name search the brief's second step asks
    for, read once and cached rather than scraped per name."""
    body = client.get(CIK_LOOKUP_URL) or b""
    out = []
    for line in body.decode("latin-1").splitlines():
        m = re.match(r"^(.*):(\d{10}):\s*$", line)
        if m:
            out.append({"cik": int(m[2]), "name": m[1].strip()})
    return out


class NameIndex:
    def __init__(self, rows: list[dict]):
        self.by_key = {}
        for r in rows:
            self.by_key.setdefault(compact_key(r["name"]), []).append(r)
        self.keys = list(self.by_key)

    def exact(self, name):
        rows = self.by_key.get(compact_key(name), [])
        ciks = {r["cik"] for r in rows}
        return rows[0] if len(ciks) == 1 else None

    def fuzzy(self, name, n=3):
        k = compact_key(name)
        if len(k) < 5:
            return []
        out = []
        for cand in difflib.get_close_matches(k, self.keys, n=n, cutoff=REVIEW):
            ciks = {r["cik"] for r in self.by_key[cand]}
            if len(ciks) == 1:
                out.append((round(difflib.SequenceMatcher(None, k, cand).ratio(), 4), self.by_key[cand][0]))
        return out


def resolve_name(name: str, tickers: NameIndex, lookup: NameIndex | None) -> dict:
    """Tickers file, then EDGAR's name index, exact before fuzzy at each
    step. Returns the match with its method and score, or the reason it is
    unresolved, with any borderline candidates for review."""
    review = []
    for method, idx in (("tickers", tickers), ("edgar_name_index", lookup)):
        if idx is None:
            continue
        hit = idx.exact(name)
        if hit:
            return {"name": name, "cik": hit["cik"], "matched_name": hit["name"], "method": f"{method}_exact", "score": 1.0}
        for score, row in idx.fuzzy(name):
            if score >= ACCEPT:
                return {"name": name, "cik": row["cik"], "matched_name": row["name"], "method": f"{method}_fuzzy", "score": score}
            review.append({"name": name, "cik": row["cik"], "matched_name": row["name"], "method": f"{method}_fuzzy", "score": score})
    return {"name": name, "cik": None, "method": "unresolved", "review": review}


# --- filings -------------------------------------------------------------------

def _rows(block: dict) -> list[dict]:
    keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    n = len(block.get("accessionNumber", []))
    return [{k: (block.get(k) or [None] * n)[i] for k in keys} for i in range(n)]


def filings(client: EdgarClient, cik: int) -> list[dict]:
    """Every filing in the submissions JSON, the recent block and the older
    pages it points to."""
    sub = client.json(SUBMISSIONS_URL.format(cik=cik))
    if not sub:
        return []
    out = _rows(sub.get("filings", {}).get("recent", {}))
    for f in sub.get("filings", {}).get("files", []):
        page = client.json(SUBMISSIONS_PAGE_URL.format(name=f["name"]))
        if page:
            out += _rows(page)
    return sorted(out, key=lambda r: (r["filingDate"] or "", r["accessionNumber"] or ""))


def parent_filing(rows: list[dict], filing_date, form=None) -> dict:
    """The filing a CUAD contract was an exhibit to: same filing date, and the
    same form when the title names one. Resolved only when exactly one filing
    fits."""
    if not filing_date:
        return {"status": "no_date"}
    hits = [r for r in rows if r["filingDate"] == filing_date]
    if form:
        # CUAD writes amendments without the slash: S-1A, SB-2A, F-1A are S-1/A, SB-2/A, F-1/A on EDGAR.
        want = {form.upper()}
        if form.upper().endswith("A") and "/" not in form:
            want.add(form.upper()[:-1].rstrip("-") + "/A")
        narrowed = [r for r in hits if (r["form"] or "").upper() in want]
        hits = narrowed or hits
    if len(hits) == 1:
        return {"status": "resolved", "accession": hits[0]["accessionNumber"], "form": hits[0]["form"], "filing_date": filing_date}
    return {"status": "ambiguous" if hits else "not_found", "candidates": len(hits)}


def nearest_10k(rows: list[dict], when: str) -> dict | None:
    """The 10-K filed closest to `when`, with the gap in days. Ties go to the
    later filing."""
    target = date.fromisoformat(when)
    tenks = [r for r in rows if r["form"] in TEN_K_FORMS and r["filingDate"]]
    if not tenks:
        return None
    best = min(tenks, key=lambda r: (abs((date.fromisoformat(r["filingDate"]) - target).days), -date.fromisoformat(r["filingDate"]).toordinal()))
    return {**best, "gap_days": (date.fromisoformat(best["filingDate"]) - target).days}


def archive_url(cik: int, accession: str, doc: str) -> str:
    return ARCHIVE_URL.format(cik=cik, acc=accession.replace("-", ""), doc=doc)


# --- Item 1A -------------------------------------------------------------------

class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_ITEM_1A = re.compile(r"^\s*item\s*1a\s*[.:\-–—]?\s*(?:risk\s+factors)?", re.I | re.M)
_NEXT_ITEM = re.compile(r"^\s*item\s*(?:1b|1c|2)\s*[.:\-–—]?", re.I | re.M)
MIN_ITEM_1A_CHARS = 2000


def extract_item_1a(text: str) -> dict:
    """Item 1A, parsed between its heading and the next Item heading. The
    table of contents carries the same headings, so every candidate start is
    tried and the longest section wins; a section under MIN_ITEM_1A_CHARS, or
    one that only incorporates by reference, is a failure and never reaches
    the index."""
    best = None
    for m in _ITEM_1A.finditer(text):
        nxt = _NEXT_ITEM.search(text, m.end())
        if not nxt:
            continue
        body = text[m.end():nxt.start()].strip()
        if best is None or len(body) > len(best[2]):
            best = (m.start(), nxt.start(), body)
    if best is None:
        return {"ok": False, "reason": "no Item 1A heading followed by an Item 1B, 1C or 2 heading"}
    start, end, body = best
    if len(body) < MIN_ITEM_1A_CHARS:
        why = "incorporated by reference" if re.search(r"incorporated\s+(?:herein\s+)?by\s+reference", body, re.I) else f"section is {len(body)} chars"
        return {"ok": False, "reason": why}
    return {"ok": True, "text": body, "start": start, "end": end, "chars": len(body)}


# --- revenue -------------------------------------------------------------------

def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def revenue_series(facts: dict, cik: int) -> dict:
    """Annual revenue per fiscal period from company facts: 10-K family
    forms, FY periods of about a year, one row per period end. A restated
    value (same concept, same period, filed later) replaces the earlier one;
    across concepts the priority order decides. Arithmetic on these rows is
    for pandas, never the model."""
    gaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    by_end = {}
    for rank, concept in enumerate(REVENUE_CONCEPTS):
        for v in gaap.get(concept, {}).get("units", {}).get("USD", []):
            if v.get("form") not in ANNUAL_FORMS or v.get("fp") != "FY" or not v.get("start") or not v.get("end"):
                continue
            if not 350 <= _days(v["start"], v["end"]) <= 380:
                continue
            cur = by_end.get(v["end"])
            if cur is None or rank < cur["rank"] or (rank == cur["rank"] and v["filed"] > cur["filed"]):
                by_end[v["end"]] = {"rank": rank, "concept": concept, "value": v["val"], "start": v["start"], "end": v["end"],
                                    "filed": v["filed"], "accession": v.get("accn"), "form": v["form"]}
    rows = []
    for end in sorted(by_end):
        r = by_end[end]
        rows.append({"row_id": f"rev_{cik}_{end}", "cik": cik, "fiscal_year_end": end, "period_start": r["start"],
                     "revenue_usd": r["value"], "concept": r["concept"], "filed": r["filed"], "accession": r["accession"],
                     "form": r["form"]})
    return {"cik": cik, "entity": (facts or {}).get("entityName"), "rows": rows,
            "concepts_used": sorted({r["concept"] for r in rows}, key=REVENUE_CONCEPTS.index)}
