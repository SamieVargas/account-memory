"""The three document types the index holds, as plain dicts the chunkers and
the store take: {id, doc_type, text, metadata}. Metadata values are scalars
(Chroma stores nothing else), and a value that did not parse is left out
rather than stored as a guess."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_TYPES = ("contract", "risk_factors", "playbook")


def content_hash(doc: dict) -> str:
    """What decides whether a document changed: its text and its metadata."""
    h = hashlib.sha256(doc["text"].encode("utf-8"))
    h.update(repr(sorted(doc["metadata"].items())).encode("utf-8"))
    return h.hexdigest()[:16]


def _clean(md: dict) -> dict:
    return {k: v for k, v in md.items() if v is not None and v != "" and isinstance(v, (str, int, float, bool))}


def contract_doc(rec: dict, account: dict | None = None) -> dict:
    """A CUAD record as an index document. `account` is its row from
    data/derived/accounts.json when the EDGAR ingest has run."""
    m = rec["metadata"]
    val = lambda k: m[k]["value"] if m[k]["status"] == "parsed" else None
    agreement = val("agreement_date")
    expiration = val("expiration_date")
    md = {"doc_type": "contract", "contract_id": rec["id"], "title": rec["title"][:200], "contract_type": rec["contract_type"],
          "filer": rec["filer"], "filing_date": rec["filing_date"], "form": rec["form"],
          "governing_law": val("governing_law"), "agreement_date": agreement, "effective_date": val("effective_date"),
          "expiration_date": expiration, "renewal_term": val("renewal_term"),
          "notice_period": val("notice_period_to_terminate_renewal"),
          "agreement_year": int(agreement[:4]) if agreement else None,
          "expiration_year": int(expiration[:4]) if expiration else None,
          "parties": "; ".join(m["parties"]["value"])[:500] or None}
    if account and account.get("cik"):
        md.update(account=account["account"], cik=int(account["cik"]))
    return {"id": rec["id"], "doc_type": "contract", "text": rec["text"], "metadata": _clean(md)}


def risk_doc(entry: dict, account: str | None = None) -> dict:
    """An Item 1A extraction from data/derived/risk_factors.json."""
    doc_id = f"rf_{entry['cik']}_{entry['accession'].replace('-', '')}"
    md = {"doc_type": "risk_factors", "cik": int(entry["cik"]), "account": account, "accession": entry["accession"],
          "filing_date": entry["filing_date"], "form": entry.get("form"),
          "filing_year": int(entry["filing_date"][:4]) if entry.get("filing_date") else None}
    return {"id": doc_id, "doc_type": "risk_factors", "text": entry["text"], "metadata": _clean(md)}


POSITIONS = ("Preferred position", "Acceptable fallback", "Escalate if")
N_CATEGORIES = 10
OPTIONAL_SECTION = re.compile(r"filing-data", re.I)


def heading_name(h: str) -> str:
    """A heading as the checks compare it: '1. Cap On Liability' and
    '**Preferred position:**' read as 'Cap On Liability' and 'Preferred position'."""
    h = re.sub(r"^\d+[.)]\s*", "", h.strip().strip("*_").strip())
    return h.rstrip(":").strip().strip("*_").rstrip(":").strip()


def playbook_status(text: str) -> dict:
    """Which of the 30 required position headings (three under each of the
    ten category headings) have text under them. The optional filing-data
    section does not count. A position heading that is missing counts as
    empty."""
    cats, cur, misplaced = {}, None, []
    for block in re.split(r"(?=^#{2,3} )", text, flags=re.M):
        m = re.match(r"^(#{2,3}) (.+?)\s*$", block, flags=re.M)
        if not m:
            continue
        body = block[m.end():].strip()
        name = heading_name(m[2])
        if m[1] == "##" and name in POSITIONS and cur:
            # '## Escalate if' under a category: a typo for '###', not an 11th category
            misplaced.append(f"'## {m[2].strip()}' under {cur} should be '### {name}'")
            cats[cur][name] = bool(body)
        elif m[1] == "##":
            cur = None if OPTIONAL_SECTION.search(m[2]) else name
            if cur:
                cats[cur] = {}
        elif cur:
            cats[cur][name] = bool(body)
    empty = [f"{c} / {p}" for c, pos in cats.items() for p in POSITIONS if not pos.get(p)]
    expected = N_CATEGORIES * len(POSITIONS)
    filled = sum(1 for pos in cats.values() for p in POSITIONS if pos.get(p))
    problems = [] if len(cats) == N_CATEGORIES else [f"{len(cats)} category headings, expected {N_CATEGORIES}"]
    problems += misplaced
    return {"categories": list(cats), "expected": expected, "filled": filled, "empty": empty, "problems": problems,
            "complete": not problems and filled == expected}


def positions_written(text: str) -> int:
    """How many of the required position headings have text."""
    return playbook_status(text)["filled"]


def playbook_doc(path: Path = ROOT / "data" / "playbook.md") -> dict | None:
    """The playbook as one document; the section chunker splits it at its
    '## ' category headings. None while the positions are unwritten, so an
    empty scaffold never reaches the index. Indexed only when all 30
    positions are written, so no run sees half a playbook."""
    text = Path(path).read_text(encoding="utf-8")
    if not playbook_status(text)["complete"]:
        return None
    return {"id": "playbook", "doc_type": "playbook", "text": text,
            "metadata": {"doc_type": "playbook", "source": "data/playbook.md"}}
