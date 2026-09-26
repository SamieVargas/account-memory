# Working in this repo

## Samie's code style (use it for every script, notebook cell and snippet)

- **Every entry point prints a start line, status lines and a completion
  line**, each with a timestamp, and the completion line has a ✓ and the
  elapsed time. Scripts here do it through `core/runlog.py`:

  ```python
  from core import runlog

  def main(argv=None):
      runlog.status("loading CUAD")                     #  · [2026-09-26 10:00:01] loading CUAD
      for i, item in enumerate(items, start=1):
          runlog.progress(i, len(items), "contracts")   #  · [...] 10/238 (4%) contracts
      return 0

  if __name__ == "__main__":
      sys.exit(runlog.run(main, "script_name"))         # ▶ ... started / ✓ ... completed in 3m 12s
  ```

  A failure prints ✗ with the error, an interrupt prints ⏹, and the lines go
  to stderr so piped output stays clean.
- **Notebook cells and one-off snippets** follow the same idea: a section
  header comment, `# NOTE:` comments on the imports, and an expected-output
  comment right above a confirmation print:

  ```python
  # ── IMPORTS ─────────────────────────────
  import pandas as pd          # NOTE: data manipulation

  # OUTPUT → should print cleanly with no errors
  print("✓ All packages loaded")
  ```

## Repo rules

- No retrieval run before `evals/golden.jsonl` exists and `data/playbook.md`
  has all 30 positions; the runners enforce it and record both files' hashes.
- Tests never use the network: `python -m pytest` runs with Hugging Face in
  offline mode and fake SEC responses.
- Code copied from another repo is recorded in `docs/PROVENANCE.md`; a
  departure from the brief is recorded in `docs/decisions.md`.
- Arithmetic over data is done in code, never by the model.
- The laptop is Windows (Git Bash, Python 3.14); commands in instructions
  should work there (`python`, not `python3`; `.venv/Scripts/activate`).
