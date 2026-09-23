# Ingest, 2026-09-23

Documents: all 238 commercial candidates (no selection applied); 0 Item 1A sections; playbook left out until all 30 positions are written.
Embedding model: BAAI/bge-small-en-v1.5 (dry run: chunked, nothing embedded).
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

Over a model's limit: chunks longer than that model reads (its max wordpieces less [CLS] and [SEP]), counted with the WordPiece vocabulary bge-small, e5-small and MiniLM share; the model embeds only the start of those chunks.

| Chunker | doc type | docs | chunks | median tokens | max tokens | over bge-small (510) | over minilm (254) | boundaries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | contract | 238 | 7431 | 400 | 400 | 39 (1%) | 7327 (99%) | window 238 |
| section | contract | 238 | 10523 | 226 | 400 | 22 (0%) | 5118 (49%) | contract_heading 213, paragraph 25 |
