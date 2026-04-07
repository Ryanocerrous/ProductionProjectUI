#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if check and cp.returncode != 0:
        raise RuntimeError(
            f"Command failed ({cp.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{cp.stdout}\n"
            f"stderr:\n{cp.stderr}"
        )
    return cp


def main() -> int:
    parser = argparse.ArgumentParser(description="Push ByteBite offline lure/click pages to Android device.")
    parser.add_argument("--adb-bin", default="adb")
    parser.add_argument("--device-serial", default="")
    parser.add_argument("--dest-dir", default="/sdcard/Download")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    lure_src = repo_root / "test_assets" / "offline_lure_page.html"
    clicked_src = repo_root / "test_assets" / "offline_clicked_page.html"
    if not lure_src.exists() or not clicked_src.exists():
        raise SystemExit("Offline HTML assets not found in test_assets/.")

    adb = [args.adb_bin]
    if args.device_serial.strip():
        adb.extend(["-s", args.device_serial.strip()])

    devices = run(adb + ["devices"], check=False)
    if "device" not in devices.stdout:
        raise SystemExit(f"No device found/authorized.\n{devices.stdout}\n{devices.stderr}")

    dest_lure = f"{args.dest_dir.rstrip('/')}/bytebite_offline_lure.html"
    dest_clicked = f"{args.dest_dir.rstrip('/')}/bytebite_clicked.html"
    run(adb + ["push", str(clicked_src), dest_clicked])
    run(adb + ["push", str(lure_src), dest_lure])

    print("[ByteBite] Offline lure pages deployed")
    print(f"[ByteBite] Lure page: file://{dest_lure}")
    print(f"[ByteBite] Clicked page: file://{dest_clicked}")
    print("[ByteBite] Use this URL for OFF1/OFF2:")
    print(f"file://{dest_lure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
