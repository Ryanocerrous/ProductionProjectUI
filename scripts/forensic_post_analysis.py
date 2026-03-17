from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.forensic_analysis import run_post_extraction_analysis
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ByteBite post-extraction triage + timeline analysis.")
    parser.add_argument(
        "--source",
        default="",
        help="Forensic source directory (default: from config.forensic_analysis.source_dir, or required).",
    )
    args = parser.parse_args()

    cfg_path = resolve_config_path(PROJECT_ROOT)
    cfg = load_or_create_config(cfg_path, build_default_config())

    source = str(args.source or "").strip()
    if source:
        cfg.setdefault("forensic_analysis", {})["source_dir"] = source

    source_cfg = str((cfg.get("forensic_analysis") or {}).get("source_dir", "")).strip()
    if not source_cfg:
        print("[ByteBite] --source is required when forensic_analysis.source_dir is empty.", file=sys.stderr)
        return 2

    summary = run_post_extraction_analysis(source_dir=Path(source_cfg).expanduser(), cfg=cfg)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
