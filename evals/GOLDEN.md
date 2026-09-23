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
 "expected_facts": ["..."],       // strings a correct answer contains
 "expected_verdict": null,        // playbook_check only
 "notes": ""}
```

Offsets are into the contract text as `core/cuad.py` loads it (CUAD's
`context`), or into the Item 1A text as `core/edgar.py` extracts it, so a
chunk covers a gold passage when their character ranges overlap.
