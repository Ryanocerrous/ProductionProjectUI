"""Summarise run.json artefacts into clean results tables."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.runtime_paths import default_logs_dir


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_runs(logs_dir: Path, limit: int) -> list[dict[str, Any]]:
    candidates = sorted((p for p in logs_dir.iterdir() if p.is_dir()), reverse=True)
    rows: list[dict[str, Any]] = []
    for run_dir in candidates:
        run_json = run_dir / "run.json"
        if not run_json.exists():
            continue
        try:
            payload = json.loads(run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["_run_id"] = run_dir.name
        rows.append(payload)
        if len(rows) >= limit:
            break
    return rows


def _step_stats(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    run_count = len(runs)
    for run in runs:
        for step in run.get("steps", []):
            name = str(step.get("name", "unknown"))
            entry = stats.setdefault(name, {"durations": [], "ok_count": 0, "seen_count": 0})
            duration_ms = _safe_float(step.get("duration_ms"), 0.0)
            entry["durations"].append(duration_ms)
            entry["seen_count"] += 1
            if bool(step.get("ok")):
                entry["ok_count"] += 1

    rows: list[dict[str, Any]] = []
    for name, entry in stats.items():
        durations = entry["durations"] or [0.0]
        avg_ms = statistics.fmean(durations)
        rows.append(
            {
                "step": name,
                "mean_ms": round(avg_ms, 2),
                "max_ms": round(max(durations), 2),
                "failure_count": int(entry["seen_count"] - entry["ok_count"]),
                "presence_pct": round((entry["seen_count"] / run_count) * 100, 1) if run_count else 0.0,
            }
        )
    rows.sort(key=lambda r: r["mean_ms"], reverse=True)
    return rows


def _print_markdown_summary(runs: list[dict[str, Any]], top: int) -> int:
    if not runs:
        print("No valid runs found.")
        return 1

    durations = [_safe_float(r.get("elapsed_s"), 0.0) for r in runs]
    successes = sum(1 for r in runs if r.get("status") == "success")
    success_rate = (successes / len(runs)) * 100 if runs else 0.0
    mean_duration = statistics.fmean(durations) if durations else 0.0
    median_duration = statistics.median(durations) if durations else 0.0

    print(f"Runs analysed: {len(runs)}")
    print(f"Success rate: {success_rate:.1f}% ({successes}/{len(runs)})")
    print(f"Mean duration (s): {mean_duration:.3f}")
    print(f"Median duration (s): {median_duration:.3f}")
    print("")

    print("| Metric | Value |")
    print("|---|---:|")
    print(f"| Runs | {len(runs)} |")
    print(f"| Success rate | {success_rate:.1f}% |")
    print(f"| Mean duration (s) | {mean_duration:.3f} |")
    print(f"| Median duration (s) | {median_duration:.3f} |")
    print("")

    steps = _step_stats(runs)[:top]
    print("| Step bottleneck | Mean ms | Max ms | Failures | Seen in runs |")
    print("|---|---:|---:|---:|---:|")
    for row in steps:
        print(
            f"| {row['step']} | {row['mean_ms']:.2f} | {row['max_ms']:.2f} | "
            f"{row['failure_count']} | {row['presence_pct']:.1f}% |"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create clean results tables from ByteBite run.json logs.")
    parser.add_argument(
        "--logs-dir",
        default="",
        help="Directory containing run folders (default: $BYTEBITE_DATA_DIR/logs or ~/bytebite-data/logs; falls back to ./logs)",
    )
    parser.add_argument("--limit", type=int, default=20, help="How many latest runs to include (default: 20)")
    parser.add_argument("--top", type=int, default=8, help="How many bottleneck steps to print (default: 8)")
    args = parser.parse_args()

    if args.logs_dir.strip():
        logs_dir = Path(args.logs_dir).expanduser()
    else:
        logs_dir = default_logs_dir()
        legacy_logs = PROJECT_ROOT / "logs"
        if not logs_dir.exists() and legacy_logs.exists():
            logs_dir = legacy_logs
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        return 1
    if args.limit <= 0:
        print("--limit must be > 0")
        return 1
    if args.top <= 0:
        print("--top must be > 0")
        return 1

    runs = _load_runs(logs_dir=logs_dir, limit=args.limit)
    return _print_markdown_summary(runs=runs, top=args.top)


if __name__ == "__main__":
    raise SystemExit(main())
