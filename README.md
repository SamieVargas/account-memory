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
| Playbook | headings only, `data/playbook.md`; Samie writes the 30 positions (runs refuse until all 30 have text and list the empty ones) |
| Golden set | format, mix and checks in `evals/GOLDEN.md`; `scripts/golden_helper.py` to write it, `evals/check_golden.py` to validate it; Samie writes the 40 |
| 6. Embedding arms (MiniLM, bge-small, e5-small) and cross-encoder rerank | harness done, `evals/ablation.py`; **not run**: needs the golden set, and Hugging Face was unreachable from this session |
| 6. pixels-rag's pending arms | not run: needs the model downloads, and push access to pixels-rag for its PR |
| 7 to 11 | not started |

bge-small-en-v1.5 is the default embedder, with the brief's chunk sizes. It
reads 512 wordpieces, and only 1% of fixed chunks and 22 of 10,523 section
chunks are longer; MiniLM (256, which 99% and 49% exceed) and e5-small stay
as ablation arms. Every dense result reports the share of chunks over its
model's limit. See `docs/decisions.md`.

Every eval writes each finished record to a `.progress.jsonl` as it goes.
An interrupted run (Ctrl+C, SIGTERM, an error, credit running out) writes a
`-partial` report marked PARTIAL with the count done and exits 130; after a
hard kill, `--from-progress <file>` rebuilds that report.

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

| Chunker | chunks | median tokens | over bge-small's 512 | over MiniLM's 256 |
| --- | --- | --- | --- | --- |
| fixed, 400 with 80 overlap | 7,431 | 400 | 39 (1%) | 7,327 (99%) |
| section, 80 to 400 | 10,523 | 226 | 22 (0.2%) | 5,118 (49%) |

## Run

```bash
pip install -r requirements.txt
python scripts/fetch_cuad.py                     # CUAD v1 into data/raw/cuad, hashes checked
python scripts/cuad_report.py                    # the CUAD ingest report
cp .env.example .env                             # set EDGAR_USER_AGENT="Name email"; every entry point loads .env
python scripts/ingest_edgar.py                   # CIKs, parent filings, Item 1A, revenue; cached
python scripts/select_contracts.py               # the 80-contract subset
python ingest.py                                 # both chunkers into chroma_db/, incremental
python ingest.py --status                        # freshness: current, stale, missing
python scripts/golden_helper.py contracts         # look-ups for writing the golden set (reads data only)
python evals/check_golden.py                     # validate evals/golden.jsonl; non-zero on any problem
python evals/auto_set.py --chunker section --hybrid   # after the golden set and all 30 playbook positions exist
python evals/ablation.py                         # Part 6: embedding arms x dense / hybrid / hybrid + cross-encoder
python -m pytest                                 # no key, no network
```

## Layout

| Path | What |
| --- | --- |
| `core/cuad.py` | CUAD records: text, gold spans as offsets, normalized metadata, contract type, the filing in the title |
| `core/chunking.py` | the fixed and section-aware chunkers, as character ranges |
| `core/docs.py`, `core/store.py` | index documents and the versioned, incremental Chroma store |
| `core/retrieve.py` | dense, BM25, reciprocal rank fusion, rerank |
| `ingest.py`, `evals/auto_set.py`, `evals/ablation.py` | the ingest report; the automatic retrieval set; the Part 6 ablation |
| `evals/records.py` | progress files and partial reports for interrupted runs |
| `scripts/golden_helper.py`, `evals/check_golden.py`, `core/golddata.py` | writing and validating the golden set, from data only |
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

## pixels-rag's pending arms (Part 6)

The brief also asks for pixels-rag's "not run" rows to be run while
sentence-transformers is installed. In a pixels-rag checkout:

```bash
pip install sentence-transformers==6.1.0
python evals/run.py --offline --embedding-ablation
python evals/run.py --offline --rerank-compare --rerank cross-encoder
```

The results go in pixels-rag on their own PR.
