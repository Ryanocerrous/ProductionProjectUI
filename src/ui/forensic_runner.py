from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.adb import Adb
from logic.forensic_profile import run_forensic_extraction
from logic.runlog import RunLogger
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path, resolve_logs_dir

CONFIG_PATH = resolve_config_path(PROJECT_ROOT)
DEFAULT_CONFIG = build_default_config()


def _load_config() -> dict:
    return load_or_create_config(CONFIG_PATH, DEFAULT_CONFIG)


def main() -> int:
    cfg = _load_config()
    logs_dir = resolve_logs_dir(PROJECT_ROOT, cfg)
    logs_dir.mkdir(parents=True, exist_ok=True)
    results_workbook = logs_dir / "results.xlsx"

    forensic_cfg = cfg.get("forensic", {})
    logcat_tail = int(forensic_cfg.get("logcat_tail", 1000))
    target_package = str(forensic_cfg.get("target_package", "") or "")
    pull_apk = bool(forensic_cfg.get("pull_apk", True))
    collect_network = bool(forensic_cfg.get("collect_network", True))
    root_mode = bool(forensic_cfg.get("root_mode", False))

    adb = Adb(serial=cfg.get("device_serial", "") or "")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = logs_dir / run_id
    logger = RunLogger(run_dir, results_workbook=results_workbook)
    logger.set_meta(
        run_id=run_id,
        mode="forensic",
        profile="independent_extraction",
        logcat_tail=logcat_tail,
        target_package=target_package,
        pull_apk=pull_apk,
        collect_network=collect_network,
        root_mode=root_mode,
    )

    status = "success"
    err: str | None = None
    try:
        run_forensic_extraction(
            adb=adb,
            logger=logger,
            output_dir=run_dir / "forensic_artifacts",
            target_package=target_package,
            pull_apk=pull_apk,
            collect_network=collect_network,
            root_mode=root_mode,
            logcat_tail=logcat_tail,
        )
    except Exception as exc:
        status = "error"
        err = str(exc)

    out = logger.write(status=status, error=err)
    print(f"[ByteBite] Forensic run status = {status}")
    print(f"[ByteBite] Run saved: {out}")
    if err:
        print(f"[ByteBite] Error: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
