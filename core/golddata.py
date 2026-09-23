"""Read-only access to the data a golden question is written against: the
selected contracts, their spans, the Item 1A extractions, the revenue
table and the playbook. Nothing here touches the index, the retriever or
an embedder, so writing and checking the golden set is not a retrieval run.
"""

import json
import re
from pathlib import Path

from core.cuad import METADATA_CATEGORIES, load_contracts

ROOT = Path(__file__).resolve().parent.parent
SELECTION = ROOT / "data" / "selection.json"
DERIVED = ROOT / "data" / "derived"
PLAYBOOK = ROOT / "data" / "playbook.md"
META_FIELDS = ("agreement_date", "effective_date", "expiration_date", "renewal_term", "notice_period_to_terminate_renewal", "governing_law")


def _json(path, default):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else default


def selection() -> dict | None:
    return _json(SELECTION, None)


def selected_records(candidates: bool = False) -> list[dict]:
    """The selected contracts' records. With candidates, every commercial
    candidate (before the selection exists)."""
    from core.cuad import COMMERCIAL_TYPES
    records = load_contracts()
    if candidates:
        return [r for r in records if r["contract_type"] in COMMERCIAL_TYPES]
    sel = selection()
    if sel is None:
        raise SystemExit("data/selection.json is missing: run scripts/select_contracts.py (or pass --candidates)")
    ids = {c["id"] for c in sel["contracts"]}
    return [r for r in records if r["id"] in ids]


def accounts() -> dict:
    return {a["contract_id"]: a for a in _json(DERIVED / "accounts.json", [])}


def risk_entries() -> list[dict]:
    """Successful Item 1A extractions, each with the doc id the index uses."""
    out = []
    for e in _json(DERIVED / "risk_factors.json", []):
        out.append({**e, "doc_id": f"rf_{e['cik']}_{e['accession'].replace('-', '')}"})
    return out


def revenue_rows() -> list[dict]:
    rows = []
    for company in _json(DERIVED / "revenue.json", []):
        for r in company["rows"]:
            rows.append({**r, "entity": company.get("entity")})
    return rows


def playbook_text() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def parsed(rec: dict, field: str):
    m = rec["metadata"][field]
    return m["value"] if m["status"] == "parsed" else None


def clause_categories(rec: dict) -> list[str]:
    return sorted({s["category"] for s in rec["spans"] if s["category"] not in METADATA_CATEGORIES})


def phrase_pattern(phrase: str):
    """The phrase's words with any run of whitespace between them, case
    insensitive: contract text wraps and double-spaces unpredictably."""
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"\s+".join(words), re.I)


def find(text: str, phrase: str) -> list[tuple[int, int]]:
    return [m.span() for m in phrase_pattern(phrase).finditer(text)] if phrase.strip() else []


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()
