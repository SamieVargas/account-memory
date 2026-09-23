# account-memory

Retrieval over real commercial contracts, the SEC filings and financials of
the companies on them, and a clause-position playbook. It builds on
[pixels-rag](https://github.com/SamieVargas/pixels-rag)'s router, citation
contract and evals, applied to enterprise documents with expert ground truth.

**Not legal or investment advice.** Everything here is public contracts and
public filings. Nothing runs on customer data.

## Status

Setup is done. No retrieval run and no model call has happened yet, and none
will until the playbook and the golden set are written.

| Part | State |
| --- | --- |
| Provenance: pixels-rag modules copied, source commit recorded | done, `docs/PROVENANCE.md` |
| CUAD fetch, pinned and hash-checked | done, `scripts/fetch_cuad.py` |
| CUAD records: spans to offsets, metadata normalized, ingest report | done, `core/cuad.py`, `scripts/cuad_report.py` |
| 2. EDGAR: CIK resolution, parent filings, Item 1A, revenue table | code and fixture tests done; **not run**, sec.gov was unreachable from the setup session |
| Contract subset | rule written, `data/SELECTION.md`; waits on the EDGAR run |
| Playbook | headings only, `data/playbook.md`; Samie writes the positions |
| Golden set | format and mix, `evals/GOLDEN.md`; Samie writes the 40 |
| 1, 3 to 11 | not started |

## Numbers so far

From `evals/results/ingest-cuad-2026-09-23.md`, no model, no embedding:

| Measure | Whole release | Commercial candidates |
| --- | --- | --- |
| Contracts | 510 | 238 |
| Gold spans / unmapped | 13,823 / 0 | 6,413 / 0 |
| Agreement date parsed / unparsed / absent | 384 / 86 / 40 | 168 / 47 / 23 |
| Expiration date parsed / unparsed / absent | 65 / 348 / 97 | 30 / 175 / 33 |
| Governing law parsed / unparsed / absent | 397 / 40 / 73 | 182 / 23 / 33 |

## Run

```bash
pip install -r requirements.txt
python scripts/fetch_cuad.py                     # CUAD v1 into data/raw/cuad, hashes checked
python scripts/cuad_report.py                    # the CUAD ingest report
cp .env.example .env                             # set EDGAR_USER_AGENT="Name email"
python scripts/ingest_edgar.py                   # CIKs, parent filings, Item 1A, revenue; cached
python scripts/select_contracts.py               # the 80-contract subset
python -m pytest                                 # no key, no network
```

## Layout

| Path | What |
| --- | --- |
| `core/cuad.py` | CUAD records: text, gold spans as offsets, normalized metadata, contract type, the filing in the title |
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
