"""Command line: python -m spybot check-history | ingest DAY HHMM | assemble DAY HHMM QUOTES_FILE... | report | final | dashboard [PORT]"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

from spybot import ingest, report

PROJECT = Path(__file__).resolve().parent.parent


def _write(root: Path, name: str, md: str, rows: list[dict]) -> Path:
    out = root / "reports"
    out.mkdir(exist_ok=True)
    (out / f"{name}.md").write_text(md)
    keys = sorted({k for r in rows for k in r})
    with open(out / f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    return out / f"{name}.md"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spybot")
    parser.add_argument("command", choices=["check-history", "ingest", "assemble", "report", "final", "dashboard"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--root", default=str(PROJECT))
    a = parser.parse_args(argv)
    root = Path(a.root)
    today = date.today()

    if a.command == "dashboard":
        from spybot import dashboard
        dashboard.serve(root, int(a.args[0]) if a.args else 8790)
        return 0
    if a.command == "check-history":
        problems = report.check_history(root)
        for p in problems:
            print(p)
        print(f"{len(problems)} problems")
        return 1 if problems else 0
    if a.command in ("ingest", "assemble"):
        day, hhmm = date.fromisoformat(a.args[0]), a.args[1]
        if a.command == "assemble":
            problems = ingest.assemble(root, day, hhmm, [Path(x) for x in a.args[2:]])
        else:
            problems = ingest.ingest(root, day, hhmm)
        print("ok" if not problems else "BAD: " + "; ".join(problems))
        return 1 if problems else 0
    final = a.command == "final"
    md, rows = report.build_report(root, today, final=final)
    path = _write(root, f"{'final' if final else 'backtest'}-{today.isoformat()}", md, rows)
    if final:
        with open(root / "reports" / "final-runs.log", "a") as f:
            f.write(f"{datetime.now().isoformat(timespec='minutes')} final run\n")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
