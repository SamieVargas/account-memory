# The golden set

`evals/golden.jsonl`, 40 questions, written by hand before any retrieval run,
then frozen: the runner records the file's SHA-256 in every result. The
playbook (`data/playbook.md`) is written first, because the playbook-check
questions are graded against it.

## Mix

| Kind | n | Gold |
| --- | --- | --- |
| `clause` | 10 | CUAD spans: contract id, category, character offsets |
| `filing` | 6 | hand-marked passages in Item 1A: CIK, accession, offsets into the extracted text |
| `filter` | 7 | the expected contract ids |
| `aggregate` | 7, at least 3 on revenue | the expected table rows and the numbers the answer must carry |
| `playbook_check` | 5, at least 1 cross-document | the verdict (`matches`, `deviates`, `unclear`) and the passages it rests on |
| `unanswerable` | 5 | none; includes a company the corpus has no document for |

## One line per question

```jsonc
{"id": "C01", "kind": "clause", "question": "...",
 "scope": {"contract_id": "c_...", "account": null, "doc_type": "contract"},
 "gold_passages": [{"doc_id": "c_...", "start": 0, "end": 0, "category": "Cap On Liability"}],
 "gold_rows": [],                 // revenue row ids, aggregate and cross-document questions
 "expected_contract_ids": [],     // filter questions: the contracts that match; aggregate questions over contracts may list them too
 "expected_facts": ["..."],       // strings a correct answer contains
 "expected_verdict": null,        // playbook_check only
 "notes": ""}
```

Offsets are into the contract text as `core/cuad.py` loads it (CUAD's
`context`), into the Item 1A text as `core/edgar.py` extracts it (doc id
`rf_<cik>_<accession without dashes>`), or into `data/playbook.md` (doc id
`playbook`), so a chunk covers a gold passage when their character ranges
overlap.

## Writing it

`notebooks/golden_workbench.ipynb` does all of this in one place: it
loads the selected contracts and their parsed metadata, looks up spans and
offsets, builds each question in this format, checks it as it is added,
and saves and validates the file. It reads data only, like the helper.

`python scripts/golden_helper.py` looks things up without touching the
index: `contracts`, `spans <id> [category]`, `find <id> "<phrase>"`,
`revenue [cik]`, `risk <cik> "<phrase>"`, and `metadata-table` (parsed
values only, so aggregate questions can be written over what the pipeline
can actually filter on).

## Checking it

`python evals/check_golden.py` exits non-zero on any problem:

- every line parses and has every field above, ids are unique, kinds are known
- the mix: 10 clause, 6 filing, 7 filter, 7 aggregate (at least 3 with
  revenue rows), 5 playbook_check (at least 1 cross-document: it cites revenue
  rows or an Item 1A passage besides the clause and the position), 5 unanswerable
- every contract id (scope, passages, expected_contract_ids) is in the selection
- every passage has 0 <= start < end <= the length of its document
- clause passages are contract passages that overlap a CUAD span of their
  category, and every clause expected fact appears inside a gold passage
- filing passages are in an Item 1A extraction
- every revenue row id exists in the revenue table
- filter questions list their expected contracts; aggregate questions list
  expected facts
- playbook_check has a verdict of matches, deviates or unclear; no other
  kind has one
- unanswerable questions have no gold passages, rows or contracts

