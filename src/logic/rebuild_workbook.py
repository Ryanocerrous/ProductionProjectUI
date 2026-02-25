"""Rebuild cumulative Excel workbook from existing run.json files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.results_workbook import append_run_to_workbook


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild logs/results.xlsx from all existing run.json files.")
    parser.add_argument("--logs-dir", default="logs", help="Logs directory (default: logs)")
    parser.add_argument("--workbook", default="", help="Workbook path (default: <logs-dir>/results.xlsx)")
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        return 1

    workbook = Path(args.workbook) if args.workbook else (logs_dir / "results.xlsx")
    if workbook.exists():
        workbook.unlink()

    run_files = sorted(logs_dir.glob("**/run.json"))
    if not run_files:
        print("No run.json files found.")
        return 1

    imported = 0
    for run_json in run_files:
        try:
            payload = json.loads(run_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        ok = append_run_to_workbook(workbook, run_json, payload)
        if ok:
            imported += 1

    if imported == 0:
        print("No rows imported. Ensure openpyxl is installed (python3-openpyxl).")
        return 1

    print(f"Workbook rebuilt: {workbook}")
    print(f"Runs imported: {imported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
