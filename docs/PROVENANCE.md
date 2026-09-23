# Provenance

Code copied from other repositories, never imported across them. Each row
names the source repository, the commit, the source path, the SHA-256 prefix
of the file as copied, and what happened to it here.

Source: `SamieVargas/pixels-rag` at `7bf4c8e38b1e935dc1f965d16c0eb532267b3c73`
(the merge of pull request 17, `claude/v2-12-mcp`), copied 2026-09-23.

| Here | Source path | sha256 (12) | Status |
| --- | --- | --- | --- |
| `core/parse.py` | `core/parse.py` | `382e5c415480` | copied as is: the tolerant JSON parser, native / recovered / failed paths |
| `core/dates.py` | `core/dates.py` | `d0edcd703617` | copied as is: relative date phrases resolved in code |
| `core/rerank.py` | `core/rerank.py` | `b7abf7a26173` | copied as is: lexical and cross-encoder rerankers; Part 6 runs the cross-encoder |
| `core/validate.py` | `core/validate.py` | `970c80e717ad` | copied as is: number extraction and the citation checks; Part 7 moves citations from dates to chunk id plus offsets and adds substring and revenue-row checks |
| `reference/pixels_rag/router.py` | `core/router.py` | `8ca2063ec408` | reference: Part 7 router |
| `reference/pixels_rag/contracts.py` | `core/contracts.py` | `92ad48f2175b` | reference: schemas and the `nullable_enum` workaround, Part 7 |
| `reference/pixels_rag/answer.py` | `core/answer.py` | `dcee7e53e644` | reference: answer call with one reject-and-retry, Part 7 |
| `reference/pixels_rag/aggregate.py` | `core/aggregate.py` | `2119ba1a218b` | reference: pandas aggregate route, Part 7 |
| `reference/pixels_rag/filters.py` | `core/filters.py` | `893b3baac90e` | reference: metadata filters in code, Part 7 |
| `reference/pixels_rag/pipeline.py` | `core/pipeline.py` | `fff844bac231` | reference: gather and ask, Parts 4 and 7 |
| `core/store.py` | `core/store.py` | `6f83c93ab06c` | adapted (Part 1): stamp and rebuild-on-mismatch kept; keyed by document id with a per-document content hash, one collection per chunker, freshness over documents instead of days |
| `core/embeddings.py` (HashEmbedding), `core/retrieve.py` (dense) | `core/index.py` | `923fc8439afc` | adapted (Part 1): the hash test embedder copied; dense retrieval rewritten around metadata `where` filters instead of allowed ids |
| `core/embeddings.py`, `evals/ablation.py` | `core/embeddings.py` | `de9cdff8f7da` | adapted (Parts 1 and 6): the arms and `make_embedding_function`, with query and passage prefixes added for bge and e5; `run_arm` rewritten as the ablation over the automatic set, keeping its 'not run, and why' rows |
| `reference/pixels_rag/evals_run.py` | `evals/run.py` | `634bb4839ec4` | reference: recall@k, MRR, partial-run handling, Parts 4 and 8 |
| `reference/pixels_rag/mcp_server.py` | `mcp_server.py` | `58b4c2364fd6` | reference: read-only stdio server, Part 14 |
| `reference/pixels_rag/stubs.py` | `tests/stubs.py` | `fcd328f0f9f0` | reference: scripted Anthropic client for offline tests |

Read and not copied: `core/days.py`, `core/rollup.py`, `core/quality.py`,
`core/chat.py`, `core/explain.py`, `chunk.py`, `ingest.py`, `main.py`. They
are specific to the day log; the ingest report and `--explain` patterns will
be rewritten for contracts rather than ported.

## Not yet copied

The Brain Dump Worker's rate limit, daily budget and session token code
(needed by Part 13, live mode) is not in pixels-rag and its repository was not
available in the session that set this repo up. When it is copied, add a
section here with its repository and commit.

## Third-party data and code

| What | Where from | Licence |
| --- | --- | --- |
| CUAD v1 (`CUADv1.json`, `category_descriptions.csv`) | `TheAtticusProject/cuad` at `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`, fetched by `scripts/fetch_cuad.py`, never committed | CC BY 4.0, The Atticus Project |
| SEC EDGAR submissions, filings and XBRL company facts | `sec.gov` and `data.sec.gov`, through `core/edgar.py`'s cache, never committed | US government public domain |
