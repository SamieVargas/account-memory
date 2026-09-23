"""Two chunkers behind one flag, over contracts, Item 1A sections and the
playbook. Every chunk is a character range [start, end) into its document's
text, so a chunk covers a gold span when the two ranges overlap.

Tokens here are `\\w+` runs and single punctuation marks, a deterministic
count that needs no model. all-MiniLM-L6-v2's tokenizer gives a median 1.07
wordpieces per token on these contracts, and that model reads at most 256
wordpieces, so most 400-token chunks are embedded from their first ~240
tokens; the ingest report counts them and docs/decisions.md says what
follows from it.

fixed    FIXED_TOKENS-token windows, FIXED_OVERLAP tokens of overlap.
section  breaks at structural headings: ARTICLE / Section markers and numbered
         headings in contracts, risk-factor headings in Item 1A, '##' headings
         in the playbook. Sections under SECTION_MIN tokens merge into the
         next; sections over SECTION_MAX are split with the fixed window
         inside them. A contract with fewer than MIN_HEADINGS headings falls
         back to paragraph breaks, and the chunk records which boundary kind
         it used.
"""

import hashlib
import re
from pathlib import Path

CHUNKERS = ("fixed", "section")
CHUNKER_VERSION = {"fixed": "fixed@v1", "section": "section@v1"}
FIXED_TOKENS = 400
FIXED_OVERLAP = 80
SECTION_MIN = 80
SECTION_MAX = 400
MIN_HEADINGS = 3

_TOKEN = re.compile(r"\w+|[^\w\s]")

CONTRACT_HEADING = re.compile(
    r"^[ \t]*(?:"
    r"(?:ARTICLE|Article)\s+[IVXLC\d]+\b"
    r"|(?:SECTION|Section)\s+\d+(?:\.\d+)*\b"
    r"|\d{1,2}(?:\.\d{1,2}){0,2}\.?[ \t]+[A-Z(\"“]"
    r"|[A-Z][A-Z0-9&,'\- ]{3,60}(?:[.:]|$)"
    r")", re.M)
PARAGRAPH = re.compile(r"\n[ \t]*\n+")
PLAYBOOK_HEADING = re.compile(r"^## ", re.M)


def source_hash() -> str:
    """Hash of this file: a chunker edit nobody versioned still forces a rebuild."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def tokens(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _TOKEN.finditer(text)]


def count_tokens(text: str) -> int:
    return sum(1 for _ in _TOKEN.finditer(text))


def fixed_windows(text: str, start: int = 0, end: int | None = None, size: int = FIXED_TOKENS, overlap: int = FIXED_OVERLAP):
    """Character ranges of token windows over text[start:end]."""
    end = len(text) if end is None else end
    toks = [(s + start, e + start) for s, e in tokens(text[start:end])]
    if not toks:
        return []
    out, step, i = [], size - overlap, 0
    while True:
        window = toks[i:i + size]
        out.append((window[0][0], window[-1][1]))
        if i + size >= len(toks):
            break
        i += step
    return out


def _boundaries(text: str, pattern) -> list[int]:
    return sorted({m.start() for m in pattern.finditer(text)} | {0})


def risk_heading_starts(text: str) -> list[int]:
    """Risk-factor headings in extracted Item 1A text: a line that is a
    sentence of 6 to 80 tokens followed by a longer paragraph, or a short
    all-capitals group header ('RISKS RELATED TO OUR BUSINESS'). 10-K layouts
    vary; the ingest report counts how many sections each filing produced so
    a filing this misreads shows up as one giant section."""
    starts, pos = [], 0
    lines = text.split("\n")
    offsets = []
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        n = count_tokens(s)
        nxt = next((l.strip() for l in lines[i + 1:] if l.strip()), "")
        group = s.isupper() and 2 <= n <= 15
        sentence = s[0].isupper() and 6 <= n <= 80 and len(nxt) > len(s)
        if group or sentence:
            starts.append(offsets[i] + (len(line) - len(line.lstrip())))
    return starts


def _sections(text: str, starts: list[int]) -> list[tuple[int, int]]:
    starts = sorted(set([0] + starts))
    ends = starts[1:] + [len(text)]
    return [(s, e) for s, e in zip(starts, ends) if text[s:e].strip()]


def _merge_and_split(text: str, sections: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged, cur = [], None
    for s, e in sections:
        cur = (cur[0], e) if cur else (s, e)
        if count_tokens(text[cur[0]:cur[1]]) >= SECTION_MIN:
            merged.append(cur)
            cur = None
    if cur:
        if merged and count_tokens(text[cur[0]:cur[1]]) < SECTION_MIN:
            merged[-1] = (merged[-1][0], cur[1])
        else:
            merged.append(cur)
    out = []
    for s, e in merged:
        if count_tokens(text[s:e]) > SECTION_MAX:
            out += fixed_windows(text, s, e, size=SECTION_MAX, overlap=FIXED_OVERLAP)
        else:
            out.append((s, e))
    return out


def section_ranges(text: str, doc_type: str) -> tuple[list[tuple[int, int]], str]:
    """(ranges, boundary kind) for the section chunker."""
    if doc_type == "playbook":
        return _sections(text, _boundaries(text, PLAYBOOK_HEADING)), "playbook_heading"
    if doc_type == "risk_factors":
        starts, kind = risk_heading_starts(text), "risk_heading"
    else:
        starts, kind = _boundaries(text, CONTRACT_HEADING), "contract_heading"
    if len(starts) < MIN_HEADINGS:
        starts, kind = [m.end() for m in PARAGRAPH.finditer(text)], "paragraph"
    return _merge_and_split(text, _sections(text, starts)), kind


def _trim(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def chunk_document(doc: dict, chunker: str) -> list[dict]:
    """doc: {id, text, doc_type, metadata}. Returns chunk dicts with id,
    doc_id, chunker, start, end, text, tokens, boundary, and the document's
    metadata copied onto each chunk."""
    if chunker not in CHUNKERS:
        raise ValueError(f"unknown chunker {chunker!r}")
    text = doc["text"]
    if chunker == "fixed":
        ranges, kind = fixed_windows(text), "window"
    else:
        ranges, kind = section_ranges(text, doc["doc_type"])
    out = []
    for i, (s, e) in enumerate(ranges):
        s, e = _trim(text, s, e)
        if s >= e:
            continue
        out.append({"id": f"{doc['id']}:{chunker}:{len(out):04d}", "doc_id": doc["id"], "doc_type": doc["doc_type"],
                    "chunker": chunker, "start": s, "end": e, "text": text[s:e], "tokens": count_tokens(text[s:e]),
                    "boundary": kind, "metadata": dict(doc.get("metadata") or {})})
    return out


def covers(chunk: dict, span: dict) -> bool:
    """A chunk covers a gold span when their character ranges overlap."""
    return chunk["start"] < span["end"] and span["start"] < chunk["end"]
