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

## Matching is on a compact key, exact before close, with guards

(Revised after the first real run, 2026-09-25.)

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
partly measures truncation. Samie's call (2026-09-23): the default dense
model is `BAAI/bge-small-en-v1.5`, which reads 512 wordpieces; only 39 of
7,431 fixed chunks and 22 of 10,523 section chunks exceed that. MiniLM and
e5-small stay as ablation arms, and every dense result still prints the
share of chunks over its model's limit. Whether bge-small retrieves better
here is for the ablation table to say, not this note.

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

## bge and e5 run with their query and passage prefixes

bge-small-en-v1.5 is trained to see a retrieval instruction before short
queries, and e5-small-v2 to see "query: " and "passage: ". pixels-rag ran
both through Chroma's plain sentence-transformers function, without them.
Here `PrefixedSentenceTransformer` adds the document prefix when chunks are
embedded and the query prefix through Chroma's `embed_query`, so each arm is
measured the way it is meant to be used. MiniLM takes no prefix.

## The ablation cannot run in the setup session

Hugging Face was unreachable from the session that wrote Part 6, and
sentence-transformers needs torch, so bge-small, e5-small and the
cross-encoder were tested with fakes only. The ablation writes those rows as
"not run" with the reason wherever they cannot load, and it waits on the
golden set and the playbook like every retrieval run.

## Interrupted runs keep their records

`evals/records.py` writes every finished query (and, in the ablation, every
finished row) to `<stem>.progress.jsonl` as it happens, flushed and fsynced.
Ctrl+C, SIGTERM or an exception (a model error, credit running out) writes
`<stem>-partial.md/json` with the count done and exits 130 on an interrupt;
the ablation also reports the arm in progress as a partial row. A hard kill
leaves the progress file, and `--from-progress` rebuilds the partial report
from it. A finished run removes its progress file.

## Review decisions in data/cik_review.csv are kept across reruns

A row marked yes or no is written back unchanged on every EDGAR ingest, and
a name's decision is used instead of resolving it again: a yes wins, and a
name whose candidates are all no stays unresolved. Only (name, candidate)
pairs nobody has decided come back as blank rows, regenerated from the
current run.

## The playbook counts only when all 30 positions are written

Ten categories, three positions each. Retrieval runs refuse, and the index
leaves the playbook out, until every one of the 30 has text; the refusal
lists the empty headings. The optional filing-data section does not count.

## The golden set is written with tools that read data only

`scripts/golden_helper.py` and `evals/check_golden.py` read the contracts,
spans, Item 1A text and revenue table through `core/golddata.py` and never
import the store, the retriever or an embedder (a test checks that), so
looking up offsets while writing questions is not a retrieval run. The line
format gained `expected_contract_ids` for filter questions, which
`evals/GOLDEN.md` described but gave no field for.

## The 10-K used for Item 1A is the nearest one that can have an Item 1A

The brief says to take the 10-K closest to the contract's date. Item 1A is
required only for fiscal years ending on or after 2005-12-01, and many CUAD
contracts are from the late 1990s, so the closest 10-K often has no Item 1A
at all (the first real run asked for a 1998 filing whose index also named
no primary document). `nearest_10k` now picks the closest 10-K whose
reported period ends on or after that date, and records the gap in days,
which can be years. A company with only older 10-Ks is counted in the
ingest report as having no 10-K to use, and nothing is fetched for it.

## One failed contract does not stop the EDGAR ingest

A URL the SEC keeps answering with 429 or 503 (after waiting as long as its
Retry-After header asks, or 10, 30, 60 and 120 seconds) is recorded against
that contract and the run goes on; the report lists the errors, and a rerun
retries only those, because everything else is cached. A 403 stops the
run: the SEC sends it for a missing User-Agent or for going over its rate,
and continuing would only extend the block.

## Name matching after the first real run

The first full run accepted "HF Enterprises" as SHF Enterprises LLC (a
different company, score 0.96) and Apollo Endosurgery as its US
subsidiary. Three changes:

- Exact matches are tried in both the tickers file and EDGAR's name index
  before any close spelling. Before, a close spelling in the tickers file
  could win over an exact name in the index.
- A close spelling is accepted only when both names share their first three
  characters, so a prefix that differs (HF, SHF) goes to review instead.
- An exact name that belongs to more than one CIK (a parent and a
  subsidiary, a name reused after a merger) is never settled
  automatically: every CIK for it goes to review, and no close spelling is
  accepted for that name either.

## The review sheet holds only names that decide a contract's company

The first run wrote 226 rows, most of them parties matched after the filer
had already decided the account. Now a row is written only when confirming
it could change the account: candidates for names ranked above the name
that decided it (all names when nothing resolved), plus the deciding name
itself when it was accepted on a close spelling. That last kind is written
with `confirmed` = `auto`; changing it to `no` rejects the match on the next
run, and the account moves to the next name.

## Item 1A failures carry the start of the section

A short Item 1A is usually a company choosing not to give risk factors,
which smaller reporting companies may do. The report now labels those
"not provided" when the text says so, and lists every failure with the
company, the filing date and the first 160 characters of what the section
held, so each one can be checked by eye.

## Close spellings are searched within the same three-letter prefix

The second full run took 20 minutes with every response cached: each
unresolved name was compared with all of EDGAR's million names. Since a
close spelling is only ever accepted with the same first three characters,
the index now keeps the names bucketed by that prefix and compares within
the bucket. A name with a different start is no longer even offered for
review, which is the same call the acceptance rule already made.
