"""Run logging utilities for controlled simulation output."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logic.results_workbook import append_run_to_workbook


class RunLogger:
    def __init__(self, run_dir: Path, results_workbook: Path | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.results_workbook = Path(results_workbook) if results_workbook is not None else None
        self._meta: dict[str, Any] = {}
        self._steps: list[dict[str, Any]] = []
        self._started_perf = time.perf_counter()
        self._started_utc = datetime.now(timezone.utc).isoformat()

    def set_meta(self, **kwargs: Any) -> None:
        self._meta.update(kwargs)

    def begin_step(self, name: str) -> float:
        if not name:
            raise ValueError("step name cannot be empty")
        return time.perf_counter()

    def end_step(
        self,
        name: str,
        started_perf: float,
        ok: bool,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        duration_ms = int((time.perf_counter() - started_perf) * 1000)
        step: dict[str, Any] = {"name": name, "ok": bool(ok), "duration_ms": duration_ms}
        if details:
            step["details"] = details
        if error:
            step["error"] = error
        self._steps.append(step)

    def write(self, status: str, error: str | None = None) -> Path:
        out = self.run_dir / "run.json"
        payload = {
            "meta": {"started_utc": self._started_utc, **self._meta},
            "status": status,
            "error": error,
            "elapsed_s": round(time.perf_counter() - self._started_perf, 3),
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "steps": self._steps,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if self.results_workbook is not None:
            try:
                ok = append_run_to_workbook(self.results_workbook, out, payload)
                if not ok:
                    print(f"[ByteBite] Excel export skipped (openpyxl missing): {self.results_workbook}")
            except Exception as exc:
                # Do not fail run logging if workbook export fails.
                print(f"[ByteBite] Excel export failed: {exc}")
        return out
