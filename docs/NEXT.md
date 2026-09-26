# Next session: what to run, in order

Everything below runs on the laptop. The cloud session that built this could
not reach sec.gov or Hugging Face, so nothing that needs them has run yet.
Check a box as each step is done, and commit what the step says to commit.

## 0. Set up

- [ ] Pull main and make a virtual environment:
  ```bash
  git checkout main && git pull
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt          # pulls torch through sentence-transformers
  ```
- [ ] Fetch CUAD and check it: `python scripts/fetch_cuad.py`
- [ ] Tests, no key and no network: `python -m pytest` (72 should pass)
- [ ] `cp .env.example .env` and set `EDGAR_USER_AGENT="Your Name your@email"`.
  Leave `ANTHROPIC_API_KEY` empty until Part 7.

## 1. Confirm the SEC rate limit

- [ ] Open sec.gov's "Accessing EDGAR Data" page and read the current
  maximum request rate. The code assumes 10 per second and runs at 4. If the
  page says less than 10, lower `PUBLISHED_MAX_RATE` (and `RATE` under it) in
  `core/edgar.py` before the next step.

## 2. EDGAR ingest (Part 2, time box one day)

- [ ] Smoke run on five contracts: `python scripts/ingest_edgar.py --limit 5`
- [ ] Full run: `python scripts/ingest_edgar.py`
  (cached, so a rerun sends nothing it already has). If the report lists
  errors, rerun it; only those are retried. If it stops on a 403, check
  `EDGAR_USER_AGENT` in `.env`, wait ten minutes, and rerun.
- [ ] Read `evals/results/ingest-edgar-<date>.md`: match rate, names by
  method, parent filings, Item 1A succeeded and failed, companies with
  revenue, the revenue concept used.
- [ ] Open `data/cik_review.csv`. It lists only names that can change which
  company a contract belongs to. Rows marked `auto` were matched on a close
  spelling: leave them, or set `no` to reject one. Blank rows are
  candidates: set `yes` or `no`. Then rerun `python scripts/ingest_edgar.py`
  (it is all cached). Your decisions are kept. Blank rows block nothing, so
  skip any you are unsure of.
- [ ] If the match rate is low, don't chase it: shrink the subset to the
  contracts that resolved and write the new target in `data/SELECTION.md`.
- [ ] Commit `data/cik_review.csv` and the EDGAR report.

## 3. Pick the contracts

- [ ] `python scripts/select_contracts.py`
- [ ] Copy the printed tier counts and match rate into the "Result" section
  of `data/SELECTION.md`.
- [ ] Commit `data/selection.json` and `data/SELECTION.md`.

## 4. Build the index (Part 1)

- [ ] `python ingest.py`. The first run downloads bge-small (about 130 MB).
  It embeds both chunkers over the selected contracts and their Item 1A
  sections.
- [ ] `python ingest.py --status` should show every document current and
  none stale or missing.
- [ ] Commit `evals/results/ingest-<date>.md`.

## 5. Write the playbook (before the golden set)

- [ ] Fill all 30 positions in `data/playbook.md`: Preferred position,
  Acceptable fallback and Escalate if, under each of the ten categories. The
  filing-data section at the bottom is optional.
- [ ] Check progress with `python evals/auto_set.py`. It retrieves nothing
  while the golden set is missing; it only lists every empty heading and
  stops.
- [ ] Commit the playbook.
- [ ] Once all 30 are written, run `python ingest.py` again. It adds the
  playbook to the index and leaves the contracts as they are.

## 6. Write the golden set (before any retrieval run)

- [ ] Look things up with the helper. It reads data only, so it doesn't
  count as a retrieval run.
  ```bash
  python scripts/golden_helper.py contracts
  python scripts/golden_helper.py metadata-table > /tmp/metadata.csv    # aggregate questions over parsed values only
  python scripts/golden_helper.py spans <contract_id> "Cap On Liability"
  python scripts/golden_helper.py find <contract_id> "shall not exceed"
  python scripts/golden_helper.py revenue <cik>
  python scripts/golden_helper.py risk <cik> "customer concentration"
  ```
- [ ] Write the 40 lines of `evals/golden.jsonl`: 10 clause, 6 filing, 7 filter,
  7 aggregate (at least 3 on revenue), 5 playbook_check (at least 1
  cross-document), 5 unanswerable. The format is in `evals/GOLDEN.md`.
- [ ] `python evals/check_golden.py` until it prints 0 problems.
- [ ] Commit the golden set. It is frozen from here, since every result
  records its hash.

## 7. Retrieval runs (Parts 4 to 6)

Each run saves as it goes. If one stops partway, the `-partial` report
has what finished. After a hard kill, rebuild it with
`--from-progress evals/results/<file>.progress.jsonl`.

- [ ] Automatic set, one arm at a time if you want to watch them:
  ```bash
  python evals/auto_set.py --chunker section
  python evals/auto_set.py --chunker section --hybrid
  python evals/auto_set.py --chunker section --hybrid --rerank cross-encoder
  python evals/auto_set.py --chunker fixed --hybrid
  ```
- [ ] The whole ablation in one command (every embedding arm × dense, hybrid,
  hybrid + cross-encoder × both chunkers). The first run downloads e5-small
  and the cross-encoder:
  ```bash
  python evals/ablation.py
  ```
- [ ] Commit everything new in `evals/results/`.

## 8. pixels-rag's pending arms (Part 6)

- [ ] In a pixels-rag checkout:
  ```bash
  pip install sentence-transformers==6.1.0
  python evals/run.py --offline --embedding-ablation
  python evals/run.py --offline --rerank-compare --rerank cross-encoder
  ```
- [ ] Put the results in pixels-rag on their own PR, or give the next
  Claude session push access to pixels-rag and it will open the PR.

## 9. Bring to the next Claude session

- [ ] The committed results from steps 2 to 8, pushed to main, so the numbers
  can go into the README and the brief's tables.
- [ ] Whether to start Part 7 (router and answer contract). It needs
  `ANTHROPIC_API_KEY` in `.env` only when it runs for real; building and
  testing it does not.
- [ ] The Brain Dump Worker repository (rate limit, daily budget, session
  token), for Part 13, only if live mode is still in scope.
