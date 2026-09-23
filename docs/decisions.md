# Decisions

Where this repo departs from the brief, or from what a reader might expect,
and why. The repo wins where the two disagree; this is the record.

## CUAD comes from the GitHub archive, not Zenodo

The brief allows either. The GitHub `data.zip` at a pinned commit is
fetched and hash-checked by `scripts/fetch_cuad.py`. It holds the QA JSON
only, whose `context` is the full contract text and whose `answer_start`
offsets map every span exactly (0 of 13,823 unmapped), which is the ground
truth Part 4 needs. What it lacks is `master_clauses.csv`; see the next
entry.

## Metadata is parsed from the label spans, and much of it stays unparsed

Without CUAD's clause table, dates and terms come from the text of the
labelled spans. A value is parsed only when the span writes it
unambiguously. Two-digit years, blank dates in unsigned forms, redactions,
and expiration terms written relative to another date are unparsed and
listed in the ingest report. The aggregate route can only use parsed values,
so questions like "contracts expiring in 2027" will run over a smaller set
than the corpus, and the golden set has to be written knowing which
contracts carry a parsed expiration.

## Contract type is inferred from the title and the Document Name label

The Zenodo release sorts contracts into folders by type; the JSON does not
carry that. `core/cuad.py` maps keywords in the title and the Document Name
label to types in a fixed priority order. The order is the decision: a
"license and maintenance" agreement is maintenance, a "manufacturing and
supply" agreement is supply.

## EDGAR name search reads the company-name index instead of scraping

The brief's second resolution step is EDGAR's company search by name. The
same data is published as one file, `cik-lookup-data.txt` (every name any
filer has used, with its CIK). Reading it once through the cache is one
request instead of one per name, and it can be matched offline and tested.
The method recorded for those matches is `edgar_name_index_exact` or
`edgar_name_index_fuzzy`.

## Matching is on a compact key

CUAD filer names are squashed ("LIMEENERGYCO"), so names on both sides are
reduced to lowercase letters and digits with one trailing corporate suffix
removed before comparing. An exact key that maps to more than one CIK is not
a match. Fuzzy matches use difflib's ratio on the same keys; the thresholds
are constants in `core/edgar.py` and are written in `data/README.md`.

## The SEC request rate is set below the published ceiling and checked in code

`core/edgar.py` records the published maximum (10 requests per second, from
the SEC's fair-access guidance) and runs at 4. The client refuses a rate
above the recorded maximum. The sec.gov page could not be reached from the
session that wrote this, so the number is from the SEC's long-standing
guidance and must be re-read on sec.gov before the first run.

## Revenue is chosen per fiscal period, not per company

Companies switch revenue concepts (`SalesRevenueNet` before ASC 606,
`RevenueFromContractWithCustomerExcludingAssessedTax` after). Taking one
concept per company would drop the years before or after the switch. For
each fiscal-year end, the highest-priority concept that reports it wins, and
the row records which concept that was; the report counts companies by
concept used. Within a concept, a later-filed value for the same period (a
restatement or a comparative column) replaces the earlier one.

## Item 1A: the longest candidate section wins

A 10-K's table of contents carries the same "Item 1A" and "Item 1B" headings
as the body. Every heading occurrence is tried as a start, each ends at the
next Item 1B, 1C or 2 heading, and the longest section is kept. Under 2,000
characters is a failure, and so is a section that only incorporates by
reference. Failures are counted and never indexed. Item 1A exists only for
fiscal years ending on or after 2005-12-01, and 10-KSB filers have none, so
older contracts will often have no risk-factor document; that shows up as a
failure count, not a gap filled from elsewhere.

## pixels-rag modules copied as reference, then ported part by part

Domain-free modules (`parse`, `dates`, `rerank`, `validate`) are in `core/`
as copied. The ones shaped around the day log (router, contracts, answer,
pipeline, eval runner, MCP server) are verbatim in `reference/pixels_rag/`
until their part ports them, so the provenance of every line stays traceable.

## Chunk sizes are counted in plain tokens, and MiniLM cannot read most of them

The brief asks for a fixed window of about 400 tokens. Tokens here are
`\w+` runs and punctuation marks, so the count is deterministic and needs no
model: 400 with 80 of overlap, and the section chunker merges under 80 and
splits over 400. By the all-MiniLM-L6-v2 tokenizer that is a median 1.07
wordpieces per token, and MiniLM reads at most 256 wordpieces. On the 238
commercial candidates 99% of fixed chunks and 49% of section chunks are
longer than that, so MiniLM embeds only their first ~240 tokens. BM25 and
the cross-encoder read the whole chunk.

Left as the brief has it, a fixed-versus-section comparison under MiniLM
partly measures truncation. The choice is Samie's, and the ingest report
counts the chunks over the limit whatever it is. The options: make
`bge-small-en-v1.5` (512 wordpieces) the default dense model, which Part 6
installs anyway; shrink the window to about 220 tokens for MiniLM; or keep
both and report the truncation beside every dense number.

## The automatic set's recall is per gold span

A (contract, category) pair can have several gold spans (CUAD labels every
passage that bears on the category). recall@k is the share of those spans
that some top-k chunk from the same contract overlaps, averaged over pairs;
MRR is the reciprocal rank of the first chunk overlapping any of them.
Corpus-wide, a chunk from another contract never counts, even if it holds
the same boilerplate.

## BM25 scores over the whole corpus, then filters

For a scoped query, BM25's IDF still comes from every chunk, and the filter
only decides which chunks may rank. That keeps a term's weight the same
across scoped and corpus-wide runs, and matches the dense side, where the
vectors do not change with the filter either.

## The runner refuses to run before the golden set and the playbook exist

`evals/auto_set.py` exits without retrieving while `evals/golden.jsonl` is
missing or `data/playbook.md` has no positions, and every result records
both files' hashes. The guardrail is in code so it cannot be skipped by
accident.

## The source footer outranks the title for the filer

176 contracts carry EDGAR's `Source: COMPANY, FORM, M/D/YYYY` footer. It
agrees with the title's filing date on all 176 and names the filer with
spaces and the exact form, so `core/cuad.py` prefers it; the squashed title
name is still tried as a second name during CIK resolution.
