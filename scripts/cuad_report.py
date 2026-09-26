"""The CUAD half of the ingest report, before any chunking or embedding:
contracts, gold spans, spans that could not be mapped to offsets, and every
metadata field's parsed / unparsed / absent counts, for the whole release
and for the commercial candidates. Unparsed values are listed, never guessed.

    python scripts/cuad_report.py      # writes evals/results/ingest-cuad-<date>.md
"""

import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import runlog  # noqa: E402
from core.cuad import COMMERCIAL_TYPES, load_contracts  # noqa: E402

FIELDS = ("agreement_date", "effective_date", "expiration_date", "renewal_term", "notice_period_to_terminate_renewal", "governing_law")


def section(title, rows):
    lines = [f"## {title}", "", f"Contracts: {len(rows)}. Gold spans: {sum(len(r['spans']) for r in rows)}. "
             f"Spans not mapped to offsets: {sum(len(r['unmapped_spans']) for r in rows)}. "
             f"With at least one entity party: {sum(1 for r in rows if r['metadata']['parties']['value'])}.", "",
             "| Field | parsed | unparsed | absent |", "| --- | --- | --- | --- |"]
    for f in FIELDS:
        c = Counter(r["metadata"][f]["status"] for r in rows)
        lines.append(f"| {f} | {c['parsed']} | {c['unparsed']} | {c['absent']} |")
    return lines


def main():
    runlog.status("loading CUAD")
    rs = load_contracts()
    com = [r for r in rs if r["contract_type"] in COMMERCIAL_TYPES]
    today = date.today().isoformat()
    lines = [f"# CUAD ingest, {today}", "", "Source: CUAD v1 (The Atticus Project, CC BY 4.0), CUADv1.json from "
             "github.com/TheAtticusProject/cuad at 67faa0e. No model, no embedding.", ""]
    lines += section("Whole release", rs) + [""]
    lines += section("Commercial candidates", com) + [""]
    lines += ["## Contract types (whole release, primary type)", "", "| Type | n | commercial |", "| --- | --- | --- |"]
    for t, n in Counter(r["contract_type"] for r in rs).most_common():
        lines.append(f"| {t} | {n} | {'yes' if t in COMMERCIAL_TYPES else ''} |")
    lines += ["", "## Unparsed metadata, commercial candidates", ""]
    for f in FIELDS:
        bad = [r for r in com if r["metadata"][f]["status"] == "unparsed"]
        lines += [f"### {f} ({len(bad)})", ""]
        for r in bad:
            m = r["metadata"][f]
            raw = " / ".join(x.replace("\n", " ").replace("|", "/")[:100] for x in m["raw"][:2])
            lines.append(f"- `{r['id']}` {m.get('reason', '')}: {raw}")
        lines.append("")
    out = ROOT / "evals" / "results" / f"ingest-cuad-{today}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:30]))
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(runlog.run(main, "cuad_report"))
