"""Start, status and completion lines for every entry point, in Samie's
house style: a timestamped line when a script starts, status lines while it
works, and a ✓ line with the elapsed time when it finishes cleanly (✗ when
it fails, ⏹ when it is interrupted).

    if __name__ == "__main__":
        sys.exit(runlog.run(main, "ingest_edgar"))

    runlog.status("resolving names")
    runlog.progress(i, n, "contracts")      # prints every `every` items and at the end

Everything goes to stderr, so it shows in the terminal but never mixes into
output that is piped or redirected (golden_helper's TSV and CSV, for one).
A console that cannot print ✓ gets plain ASCII instead of an error.
"""

import os
import sys
import time
from datetime import datetime

INTERRUPTED = 130
ASCII = {"▶": ">", "✓": "OK", "✗": "X", "⏹": "STOP", "·": "-", "→": "->"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write(line: str):
    stream = sys.stderr
    try:
        stream.write(line + "\n")
    except UnicodeEncodeError:
        for k, v in ASCII.items():
            line = line.replace(k, v)
        stream.write(line.encode("ascii", "replace").decode("ascii") + "\n")
    stream.flush()


def elapsed(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def status(msg: str):
    _write(f"  · [{_now()}] {msg}")


def progress(i: int, n: int, what: str = "", every: int = 10, extra: str = ""):
    """A status line every `every` items and on the last one."""
    if n and (i % every == 0 or i == n):
        _write(f"  · [{_now()}] {i}/{n} ({i / n:.0%}) {what}{(' · ' + extra) if extra else ''}")


def run(main, name: str, argv=None) -> int:
    """Call main(argv) between a start line and a completion line, and
    return its exit code. Exceptions are reported and re-raised."""
    t0 = time.time()
    _write(f"▶ [{_now()}] {name} started")
    try:
        code = main(argv) if argv is not None else main()
    except KeyboardInterrupt:
        _write(f"⏹ [{_now()}] {name} interrupted after {elapsed(time.time() - t0)}")
        return INTERRUPTED
    except BrokenPipeError:  # the reader (head, a pager) closed the pipe early; not a failure
        _write(f"✓ [{_now()}] {name} completed in {elapsed(time.time() - t0)} (output closed early by the reader)")
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except BaseException as e:
        _write(f"✗ [{_now()}] {name} failed after {elapsed(time.time() - t0)}: {type(e).__name__}: {str(e)[:200]}")
        raise
    code = 0 if code is None else code
    if code == 0:
        _write(f"✓ [{_now()}] {name} completed in {elapsed(time.time() - t0)}")
    elif code == INTERRUPTED:
        _write(f"⏹ [{_now()}] {name} interrupted after {elapsed(time.time() - t0)} (partial results saved)")
    else:
        _write(f"✗ [{_now()}] {name} stopped with exit code {code} after {elapsed(time.time() - t0)}")
    return code
