# account-memory

Retrieval over real commercial contracts, the SEC filings and financials of
the companies on them, and a clause-position playbook. It builds on
[pixels-rag](https://github.com/SamieVargas/pixels-rag)'s router, citation
contract and evals, applied to enterprise documents with expert ground truth.

**Not legal or investment advice.** Everything here is public contracts and
public filings. Nothing runs on customer data.

## Status

The index can be built. No retrieval run and no model call has happened
yet, and `evals/auto_set.py` refuses to run until the playbook and the golden
set are written.

| Part | State |
| --- | --- |
| Provenance: pixels-rag modules copied, source commit recorded | done, `docs/PROVENANCE.md` |
| CUAD fetch, records, spans to offsets, metadata, ingest report | done, `core/cuad.py`, `scripts/cuad_report.py` |
| 1. Versioned, incremental ingest with freshness status | done, `core/store.py`, `ingest.py`; smoke-tested with MiniLM on 10 contracts |
| 2. EDGAR: CIK resolution, parent filings, Item 1A, revenue table | code and fixture tests; **not run**, sec.gov was unreachable from the setup session |
| 3. Fixed and section-aware chunkers | done, `core/chunking.py`; counts in `evals/results/ingest-2026-09-23-dry.md` |
| 4. Automatic retrieval set | harness done, `evals/auto_set.py`; **not run**, waits on the golden set and playbook |
| 5. Hybrid BM25 plus dense with reciprocal rank fusion | done, `core/retrieve.py`, `--hybrid`; **not run** |
| Contract subset | rule written, `data/SELECTION.md`; waits on the EDGAR run |
| Playbook | headings only, `data/playbook.md`; Samie writes the positions |
| Golden set | format and mix, `evals/GOLDEN.md`; Samie writes the 40 |
| 6 to 11 | not started |

A decision is open: MiniLM, the default embedder, reads at most 256
wordpieces, and 99% of the 400-token fixed chunks and 49% of section chunks
are longer. See `docs/decisions.md`.

## Numbers so far

From `evals/results/ingest-cuad-2026-09-23.md`, no model, no embedding:

| Measure | Whole release | Commercial candidates |
| --- | --- | --- |
| Contracts | 510 | 238 |
| Gold spans / unmapped | 13,823 / 0 | 6,413 / 0 |
| Agreement date parsed / unparsed / absent | 384 / 86 / 40 | 168 / 47 / 23 |
| Expiration date parsed / unparsed / absent | 65 / 348 / 97 | 30 / 175 / 33 |
| Governing law parsed / unparsed / absent | 397 / 40 / 73 | 182 / 23 / 33 |

Chunks on the 238 candidates, from `evals/results/ingest-2026-09-23-dry.md`:

| Chunker | chunks | median tokens | over MiniLM's 256-wordpiece limit |
| --- | --- | --- | --- |
| fixed, 400 with 80 overlap | 7,431 | 400 | 7,327 (99%) |
| section, 80 to 400 | 10,523 | 226 | 5,118 (49%) |

## Run

```bash
pip install -r requirements.txt
python scripts/fetch_cuad.py                     # CUAD v1 into data/raw/cuad, hashes checked
python scripts/cuad_report.py                    # the CUAD ingest report
cp .env.example .env                             # set EDGAR_USER_AGENT="Name email"
python scripts/ingest_edgar.py                   # CIKs, parent filings, Item 1A, revenue; cached
python scripts/select_contracts.py               # the 80-contract subset
python ingest.py                                 # both chunkers into chroma_db/, incremental
python ingest.py --status                        # freshness: current, stale, missing
python evals/auto_set.py --chunker section --hybrid   # after the golden set and playbook exist
python -m pytest                                 # no key, no network
```

## Layout

| Path | What |
| --- | --- |
| `core/cuad.py` | CUAD records: text, gold spans as offsets, normalized metadata, contract type, the filing in the title |
| `core/chunking.py` | the fixed and section-aware chunkers, as character ranges |
| `core/docs.py`, `core/store.py` | index documents and the versioned, incremental Chroma store |
| `core/retrieve.py` | dense, BM25, reciprocal rank fusion, rerank |
| `ingest.py`, `evals/auto_set.py` | the ingest report; the automatic retrieval set |
| `core/edgar.py` | the EDGAR client (declared User-Agent, rate limit, URL-keyed cache) and the resolution, filing, Item 1A and revenue parsers |
| `core/parse.py`, `dates.py`, `rerank.py`, `validate.py` | copied from pixels-rag |
| `reference/pixels_rag/` | pixels-rag modules waiting to be ported |
| `scripts/` | fetch, report, EDGAR ingest, selection |
| `data/` | data notes, selection rule, playbook, CIK review sheet; raw data and cache are git-ignored |
| `docs/` | provenance and decisions |

## Sources and attribution

- **CUAD v1**, the Contract Understanding Atticus Dataset, by The Atticus
  Project, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Hendrycks, Burns, Chen and Ball, "CUAD: An Expert-Annotated NLP Dataset for
  Legal Contract Review", NeurIPS 2021. <https://www.atticusprojectai.org/cuad>
- **SEC EDGAR** filings and XBRL company facts, U.S. Securities and Exchange
  Commission, public domain. Fetched with a declared User-Agent under the
  SEC's fair-access policy and cached locally; nothing bulk is committed.
