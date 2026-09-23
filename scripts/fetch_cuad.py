"""Fetch the CUAD v1 release into data/raw/cuad (git-ignored), pinned to a
commit and checked against a hash, so every machine starts from the same
bytes. Nothing downloaded here is committed.

    python scripts/fetch_cuad.py            # download, verify, unzip
    python scripts/fetch_cuad.py --check    # verify what is already on disk

Source: github.com/TheAtticusProject/cuad at the commit below. That repo's
data.zip holds the QA-format JSON only (the full contract text is each
entry's `context`); the Zenodo record 4595826 release adds the plain-text
files and master_clauses.csv, and is not needed by this pipeline. See
data/README.md for what is actually in the archive.

CUAD is CC BY 4.0: The Atticus Project, https://www.atticusprojectai.org/cuad
"""

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "cuad"
COMMIT = "67faa0e6023b04fcaae6cc09497ab00e5d63a2a2"
BASE = f"https://raw.githubusercontent.com/TheAtticusProject/cuad/{COMMIT}"
FILES = {
    "data.zip": "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a",
    "category_descriptions.csv": "7499950ee04d2ed2841c0f8ec2ef96b91be039bc2ea3c4edcc36334a465b1f36",
}
UNZIPPED = ("CUADv1.json", "test.json", "train_separate_questions.json")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(name: str) -> Path:
    dest = RAW / name
    if dest.exists() and sha256(dest) == FILES[name]:
        return dest
    r = requests.get(f"{BASE}/{name}", timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    got = sha256(dest)
    if got != FILES[name]:
        dest.unlink()
        raise SystemExit(f"{name}: sha256 {got} does not match the pinned {FILES[name]}")
    return dest


def check() -> list[str]:
    problems = []
    for name, want in FILES.items():
        p = RAW / name
        if not p.exists():
            problems.append(f"missing {p}")
        elif sha256(p) != want:
            problems.append(f"{p} does not match the pinned hash")
    for name in UNZIPPED:
        if not (RAW / name).exists():
            problems.append(f"missing {RAW / name} (unzip data.zip)")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify the files on disk, download nothing")
    args = ap.parse_args(argv)
    RAW.mkdir(parents=True, exist_ok=True)
    if not args.check:
        for name in FILES:
            fetch(name)
        with zipfile.ZipFile(RAW / "data.zip") as z:
            z.extractall(RAW)
    problems = check()
    for p in problems:
        print(p)
    if problems:
        return 1
    print(f"CUAD v1 at {RAW}, commit {COMMIT[:7]}, hashes verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
