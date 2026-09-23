"""Results that survive an interrupted run.

Every eval writes each finished record to <stem>.progress.jsonl the moment
it exists (flushed and fsynced), so Ctrl+C, a SIGTERM, a crash, credit
running out, or a killed process never loses the work already done.

    finished      <stem>.md and <stem>.json; the progress file is removed
    interrupted   <stem>-partial.md and <stem>-partial.json, marked PARTIAL
                  with the count done, and the progress file kept
    killed hard   only the progress file; `--from-progress <file>` on the
                  runner rebuilds the partial report from it

The first line of a progress file is {"type": "meta", ...}; every other
line is a record with a "type" the runner chose.
"""

import json
import os
import signal
from pathlib import Path

INTERRUPTED = 130


class Recorder:
    def __init__(self, out_dir, stem: str, meta: dict):
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.stem = stem
        self.progress = self.out / f"{stem}.progress.jsonl"
        self._f = self.progress.open("w", encoding="utf-8")
        self.append({"type": "meta", **meta})
        self._old_term = None

    def append(self, record: dict):
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())

    def __enter__(self):
        """SIGTERM is raised as KeyboardInterrupt inside the block, so a
        terminated run takes the same path as Ctrl+C."""
        def term(signum, frame):
            raise KeyboardInterrupt(f"signal {signum}")
        try:
            self._old_term = signal.signal(signal.SIGTERM, term)
        except ValueError:  # not the main thread
            self._old_term = None
        return self

    def __exit__(self, *exc):
        if self._old_term is not None:
            signal.signal(signal.SIGTERM, self._old_term)
        if not self._f.closed:
            self._f.close()
        return False

    def _write(self, suffix, md, data):
        if not self._f.closed:
            self._f.close()
        (self.out / f"{self.stem}{suffix}.md").write_text(md, encoding="utf-8")
        (self.out / f"{self.stem}{suffix}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")

    def finish(self, md: str, data: dict):
        self._write("", md, data)
        self.progress.unlink(missing_ok=True)

    def partial(self, md: str, data: dict):
        self._write("-partial", md, {**data, "partial": True, "progress_file": self.progress.name})


def read_progress(path) -> tuple[dict, list[dict]]:
    """(meta, records) from a progress file. A last line cut off mid-write
    is skipped."""
    meta, records = {}, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") == "meta":
            meta = {k: v for k, v in rec.items() if k != "type"}
        else:
            records.append(rec)
    return meta, records


def partial_stem(progress_path) -> tuple[Path, str]:
    p = Path(progress_path)
    return p.parent, p.name[: -len(".progress.jsonl")]
