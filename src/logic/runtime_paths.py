from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_data_dir() -> Path:
    override = os.environ.get("BYTEBITE_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "bytebite-data"


def default_logs_dir() -> Path:
    return default_data_dir() / "logs"


def build_default_config() -> dict[str, Any]:
    return {
        "device_serial": "",
        "gpio": {"start": 22, "cancel": 27, "view_logs": 17},
        "paths": {"logs_dir": str(default_logs_dir())},
        "offensive": {
            "marker_dir": "/sdcard/ByteBiteDemo",
            "marker_file": "bytebite_marker.txt",
            "trace_tag": "ByteBiteDemo",
            "open_url": "https://example.com",
            "test_apk_path": "",
            "test_package": "",
            "test_activity": "",
            "collect_network": True,
        },
        "forensic": {
            "logcat_tail": 1000,
            "target_package": "",
            "pull_apk": True,
            "collect_network": True,
            "root_mode": False,
        },
        "comparison": {"run_root_phase": True},
    }


def resolve_config_path(project_root: Path) -> Path:
    explicit = os.environ.get("BYTEBITE_CONFIG", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    data_cfg = default_data_dir() / "config.json"
    if data_cfg.exists():
        return data_cfg

    legacy_cfg = project_root / "config.json"
    if legacy_cfg.exists():
        data_cfg.parent.mkdir(parents=True, exist_ok=True)
        data_cfg.write_text(legacy_cfg.read_text(encoding="utf-8"), encoding="utf-8")
        return data_cfg

    return data_cfg


def load_or_create_config(config_path: Path, default_config: dict[str, Any]) -> dict[str, Any]:
    cfg_path = Path(config_path).expanduser()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if not cfg_path.exists() or not cfg_path.read_text(encoding="utf-8").strip():
        cfg_path.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
        return dict(default_config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    paths = cfg.setdefault("paths", {})
    logs_dir_cfg = str(paths.get("logs_dir", "")).strip()
    if logs_dir_cfg in {"", "logs", "./logs"}:
        paths["logs_dir"] = str(default_logs_dir())
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def resolve_logs_dir(project_root: Path, cfg: dict[str, Any]) -> Path:
    logs_dir_cfg = str((cfg.get("paths") or {}).get("logs_dir", "")).strip()
    if logs_dir_cfg:
        logs_dir = Path(logs_dir_cfg).expanduser()
        return logs_dir if logs_dir.is_absolute() else (project_root / logs_dir)
    return default_logs_dir()
