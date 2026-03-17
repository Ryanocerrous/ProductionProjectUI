from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.local_llm import classify_text_with_llama
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local llama.cpp JSON classification demo.")
    parser.add_argument(
        "--text",
        default="User searched for encrypted vault apps and burner phones.",
        help="Text chunk to classify.",
    )
    parser.add_argument(
        "--file",
        default="",
        help="Optional file to read and classify from (first chunk only).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1800,
        help="Max characters to send to the model when --file is used.",
    )
    args = parser.parse_args()

    cfg_path = resolve_config_path(PROJECT_ROOT)
    cfg = load_or_create_config(cfg_path, build_default_config())
    text = args.text
    if args.file:
        source = Path(args.file).expanduser()
        if not source.exists() or not source.is_file():
            print(f"[ByteBite] File not found: {source}", file=sys.stderr)
            return 2
        raw = source.read_text(encoding="utf-8", errors="ignore")
        cleaned = re.sub(r"\s+", " ", raw).strip()
        limit = max(100, int(args.max_chars))
        text = cleaned[:limit]
        if not text:
            print(f"[ByteBite] File has no readable text: {source}", file=sys.stderr)
            return 2

    result = classify_text_with_llama(text, cfg)

    print(f"[ByteBite] Config: {cfg_path}")
    print(f"[ByteBite] Return code: {result.returncode}")
    if result.stderr:
        print(f"[ByteBite] Stderr: {result.stderr}")
    print(
        json.dumps(
            {
                "category": result.category,
                "suspicion_score": result.suspicion_score,
                "rationale": result.rationale,
            },
            indent=2,
        )
    )

    if result.parsed_json is None:
        print("\n[ByteBite] Raw model output:")
        print(result.raw_output)
    return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
