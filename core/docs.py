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


def positions_written(text: str) -> int:
    """How many '### ' position headings have text under them."""
    parts = re.split(r"^#{2,3} .*$", text, flags=re.M)
    heads = re.findall(r"^(#{2,3}) .*$", text, flags=re.M)
    return sum(1 for h, body in zip(heads, parts[1:]) if h == "###" and body.strip())


def playbook_doc(path: Path = ROOT / "data" / "playbook.md") -> dict | None:
    """The playbook as one document; the section chunker splits it at its
    '## ' category headings. None while the positions are unwritten, so an
    empty scaffold never reaches the index."""
    text = Path(path).read_text(encoding="utf-8")
    if not positions_written(text):
        return None
    return {"id": "playbook", "doc_type": "playbook", "text": text,
            "metadata": {"doc_type": "playbook", "source": "data/playbook.md"}}
