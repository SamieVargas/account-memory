# Data

Nothing in `data/raw/`, `data/cache/` or `data/derived/` is committed. The
scripts fetch and rebuild it.

## CUAD v1: what is actually in the release

`python scripts/fetch_cuad.py` downloads from `github.com/TheAtticusProject/cuad`
at commit `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`, checks the SHA-256 of
each file, and unzips into `data/raw/cuad/`. What it holds, listed from the
archive, not assumed:

| File | Size | What it is |
| --- | --- | --- |
| `data.zip` | 18,309,308 bytes | the archive below; sha256 `f8161d18…b999a` |
| `CUADv1.json` | 40,128,638 bytes | SQuAD-format, version `aok_v1.0`: 510 entries, one per contract. `title` is the source file name; `paragraphs[0].context` is the full contract text; `qas` holds 41 questions per contract, one per category, each with its answer spans as `text` and `answer_start` |
| `train_separate_questions.json` | 35,065,844 bytes | the paper's train split, same format |
| `test.json` | 7,378,232 bytes | the paper's test split, same format |
| `category_descriptions.csv` | 8,987 bytes | the 41 categories: name, description, answer format, group; sha256 `7499950e…1b36` |

Checked on load (`core/cuad.py`, `tests/test_cuad.py`): 510 contracts, one
paragraph each, 13,823 answer spans, and every span's `answer_start` points at
exactly its `text` in the context, so 0 spans are unmapped. The QA ids are
`<title>__<Category>`.

This GitHub archive does **not** contain the plain-text contract files, the
PDFs, or `master_clauses.csv` (the per-contract clause table with lawyers'
normalized answers, such as "3 years" for an expiration term). Those are in
the full release on Zenodo, record 4595826, which was not reachable from the
session that set this repo up. The pipeline does not need the text files
(the JSON context is the text). The clause table would improve metadata:
see "Metadata" below.

### Metadata

Normalized in `core/cuad.py` from CUAD's own label spans, never guessed:

| Field | From the label | Parsed when |
| --- | --- | --- |
| `parties` | Parties | spans that name an entity (a corporate suffix, or three or more capitalized words); defined roles like "Distributor" are dropped, the raw spans kept |
| `agreement_date`, `effective_date` | Agreement Date, Effective Date | the label writes exactly one full calendar date. A two-digit year, a blank ("____ day of May, 2000"), a redaction, or two different dates is unparsed |
| `expiration_date` | Expiration Date | the label writes one calendar date. "Three years from the Effective Date" is unparsed, since computing it would be a guess about the start |
| `renewal_term`, `notice_period_to_terminate_renewal` | Renewal Term, Notice Period To Terminate Renewal | the label names exactly one duration |
| `governing_law` | Governing Law | the clause names one recognized US state or country after "laws of", or "English law" style |
| `contract_type` | the title's type words and the Document Name label | the first keyword in `TYPE_KEYWORDS` priority order; every match is kept in `contract_types` |

`python scripts/cuad_report.py` writes the counts and lists every unparsed
value to `evals/results/ingest-cuad-<date>.md`. On the commercial candidates,
expiration is the weak field (175 of 238 unparsed), because CUAD labels the
term clause rather than a date. If the Zenodo release becomes reachable,
`master_clauses.csv` answers can replace the span parsing for the date and
term fields; until then the unparsed count is the honest number.

### The filing each contract came from

CUAD titles are EDGAR exhibit file names. Three shapes (`parse_title`):

- long, 181 contracts: `LOHACOMPANYLTD_20191209_F-1_EX-10.16_11917878_EX-10.16_SUPPLY AGREEMENT` (filer, filing date, form, exhibit)
- short, 302: `LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT` (filer, filing date, exhibit)
- named, 26, plus 1 other: `MetLife, Inc. - Remarketing Agreement` (filer only)

The filer and filing date are what `parent_filing` matches against the
company's submissions.

## SEC EDGAR

`scripts/ingest_edgar.py`, through `core/edgar.py`. Needs `EDGAR_USER_AGENT`
set to "Name email". Reads and writes:

| Path | What |
| --- | --- |
| `data/cache/edgar/` | every response, gzip, keyed by a hash of the URL |
| `data/derived/accounts.json` | per contract: every name tried, its CIK and method, the account, parent filing, the 10-K used and its gap in days |
| `data/derived/risk_factors.json` | Item 1A text for successful extractions only |
| `data/derived/revenue.json` | per company: annual revenue rows with `row_id`, fiscal year end, value, concept, filing |
| `data/cik_review.csv` | committed: borderline name matches, one row each, for a person to mark `confirmed` yes or no; decided rows are kept unchanged across reruns and only new pairs are added |

Resolution order is the SEC tickers file, then EDGAR's company-name index
(`cik-lookup-data.txt`, every filer past and present), exact before fuzzy at
each step. Thresholds are in `core/edgar.py`: a fuzzy score at or above 0.94
is accepted, 0.85 to 0.94 goes to review and is not used until confirmed.

## The playbook

`data/playbook.md` is Samie's and is written before the golden set.
