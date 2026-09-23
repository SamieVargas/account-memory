# Ingest, 2026-09-23

Documents: all 238 commercial candidates (no selection applied); 0 Item 1A sections; playbook not written yet, left out.
Embedding model: all-MiniLM-L6-v2 (dry run: chunked, nothing embedded).
Chunkers: fixed = 400 tokens with 80 overlap; section = headings, merged under 80 tokens, split over 400. Tokens are \w+ runs and punctuation marks.

## Contracts

| Measure | n |
| --- | --- |
| Contracts | 238 |
| Gold spans | 6413 |
| Spans not mapped to offsets | 0 |
| agreement_date: parsed / unparsed / absent | 168 / 47 / 23 |
| effective_date: parsed / unparsed / absent | 132 / 56 / 50 |
| expiration_date: parsed / unparsed / absent | 30 / 175 / 33 |

## Chunks

Over MiniLM's limit: chunks longer than 254 wordpieces by the all-MiniLM-L6-v2 tokenizer, which that model embeds only in part.

| Chunker | doc type | docs | chunks | median tokens | max tokens | over MiniLM's limit | boundaries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | contract | 238 | 7431 | 400 | 400 | 7327 (99%) | window 238 |
| section | contract | 238 | 10523 | 226 | 400 | 5118 (49%) | contract_heading 213, paragraph 25 |
