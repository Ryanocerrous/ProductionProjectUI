from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.adb import Adb
from logic.forensic_profile import run_forensic_extraction
from logic.offensive_profile import run_offensive_capability_profile
from logic.runlog import RunLogger
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path, resolve_logs_dir

CONFIG_PATH = resolve_config_path(PROJECT_ROOT)
DEFAULT_CONFIG = build_default_config()
ROOT_ONLY_STEPS = {"root_probe_id", "root_probe_write", "network_snapshot_root"}


def _load_config() -> dict[str, Any]:
    return load_or_create_config(CONFIG_PATH, DEFAULT_CONFIG)


def _run_stats(run_json_path: Path) -> dict[str, Any]:
    data = json.loads(run_json_path.read_text(encoding="utf-8"))
    steps = data.get("steps", [])
    step_map = {s.get("name", ""): s for s in steps if isinstance(s, dict)}
    return {
        "status": data.get("status"),
        "elapsed_s": data.get("elapsed_s"),
        "steps_total": len(steps),
        "steps_failed": sum(1 for s in steps if not s.get("ok")),
        "steps_by_name": {
            k: {"ok": bool(v.get("ok")), "duration_ms": v.get("duration_ms")}
            for k, v in step_map.items()
            if k
        },
        "root_only_success_count": sum(
            1 for s in steps if s.get("name") in ROOT_ONLY_STEPS and bool(s.get("ok"))
        ),
        "apk_hash_count": sum(1 for s in steps if str(s.get("name", "")).startswith("hash_remote_apk_")),
        "apk_pull_count": sum(1 for s in steps if str(s.get("name", "")).startswith("pull_apk_")),
    }


def _run_phase(
    *,
    adb: Adb,
    phase_name: str,
    root_mode: bool,
    parent_dir: Path,
    results_workbook: Path,
    cfg: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    off_cfg = cfg.get("offensive", {})
    for_cfg = cfg.get("forensic", {})
    phase_dir = parent_dir / phase_name
    logger = RunLogger(phase_dir, results_workbook=results_workbook)
    logger.set_meta(
        run_id=run_id,
        mode="comparison_phase",
        phase=phase_name,
        root_mode=root_mode,
        offensive_profile="capability_profile",
        forensic_profile="independent_extraction",
    )

    status = "success"
    err: str | None = None
    try:
        run_offensive_capability_profile(
            adb=adb,
            logger=logger,
            marker_dir=off_cfg.get("marker_dir", "/sdcard/ByteBiteDemo"),
            open_url=off_cfg.get("open_url", "https://example.com"),
            trace_token=f"{run_id}-{phase_name}",
            root_mode=root_mode,
            marker_file=off_cfg.get("marker_file", "bytebite_marker.txt"),
            trace_tag=off_cfg.get("trace_tag", "ByteBiteDemo"),
            apk_path=off_cfg.get("test_apk_path", ""),
            test_package=off_cfg.get("test_package", ""),
            test_activity=off_cfg.get("test_activity", ""),
            collect_network=bool(off_cfg.get("collect_network", True)),
        )
        run_forensic_extraction(
            adb=adb,
            logger=logger,
            output_dir=phase_dir / "forensic_artifacts",
            target_package=str(for_cfg.get("target_package", "") or ""),
            pull_apk=bool(for_cfg.get("pull_apk", True)),
            collect_network=bool(for_cfg.get("collect_network", True)),
            root_mode=root_mode,
            logcat_tail=int(for_cfg.get("logcat_tail", 1000)),
        )
    except Exception as exc:
        status = "error"
        err = str(exc)

    run_json = logger.write(status=status, error=err)
    stats = _run_stats(run_json)
    return {"phase": phase_name, "run_json": str(run_json), "error": err, **stats}


def main() -> int:
    cfg = _load_config()
    logs_dir = resolve_logs_dir(PROJECT_ROOT, cfg)
    logs_dir.mkdir(parents=True, exist_ok=True)
    results_workbook = logs_dir / "results.xlsx"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    compare_dir = logs_dir / f"{run_id}-compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    adb = Adb(serial=cfg.get("device_serial", "") or "")

    root_probe = adb.su_shell("id", timeout_s=10.0)
    root_available = root_probe.ok and "uid=0" in root_probe.stdout
    run_root_phase = bool(cfg.get("comparison", {}).get("run_root_phase", True))

    stock = _run_phase(
        adb=adb,
        phase_name="stock",
        root_mode=False,
        parent_dir=compare_dir,
        results_workbook=results_workbook,
        cfg=cfg,
        run_id=run_id,
    )

    rooted: dict[str, Any] = {
        "phase": "rooted",
        "status": "skipped",
        "elapsed_s": 0.0,
        "steps_total": 0,
        "steps_failed": 0,
        "steps_by_name": {},
        "root_only_success_count": 0,
        "apk_hash_count": 0,
        "apk_pull_count": 0,
        "error": None,
    }
    if run_root_phase:
        if root_available:
            rooted = _run_phase(
                adb=adb,
                phase_name="rooted",
                root_mode=True,
                parent_dir=compare_dir,
                results_workbook=results_workbook,
                cfg=cfg,
                run_id=run_id,
            )
        else:
            rooted["error"] = "Root phase skipped: su not available"

    comparison = {
        "run_id": run_id,
        "root_available": root_available,
        "run_root_phase": run_root_phase,
        "stock": stock,
        "rooted": rooted,
        "delta": {
            "elapsed_s": round(float(rooted.get("elapsed_s", 0.0)) - float(stock.get("elapsed_s", 0.0)), 3)
            if rooted.get("status") != "skipped"
            else None,
            "failed_steps": int(rooted.get("steps_failed", 0)) - int(stock.get("steps_failed", 0))
            if rooted.get("status") != "skipped"
            else None,
            "root_only_success_gain": int(rooted.get("root_only_success_count", 0))
            - int(stock.get("root_only_success_count", 0))
            if rooted.get("status") != "skipped"
            else None,
            "apk_hash_count_gain": int(rooted.get("apk_hash_count", 0)) - int(stock.get("apk_hash_count", 0))
            if rooted.get("status") != "skipped"
            else None,
            "apk_pull_count_gain": int(rooted.get("apk_pull_count", 0)) - int(stock.get("apk_pull_count", 0))
            if rooted.get("status") != "skipped"
            else None,
        },
    }

    out = compare_dir / "comparison.json"
    out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"[ByteBite] Comparison saved: {out}")
    print(json.dumps({"run_id": run_id, "root_available": root_available, "stock": stock["status"], "rooted": rooted["status"]}, indent=2))
    return 0 if stock.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
