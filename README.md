# ProductionProjectUI
ByteBite UI + controlled offensive/forensic experiment workflow for Raspberry Pi.

## 1) One-time setup on the Pi
1. Clone/copy this repo to:
```bash
/home/kali/ProductionProjectUI
```
2. Install base runtime:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-tk python3-gpiozero android-sdk-platform-tools python3-openpyxl
```
3. Ensure GUI-first boot service is enabled:
```bash
sudo systemctl enable --now bytebite.service
systemctl status --no-pager bytebite.service
```
4. Create external runtime data directory and config:
```bash
mkdir -p ~/bytebite-data/logs
cp ~/ProductionProjectUI/config.example.json ~/bytebite-data/config.json
```

## 2) Power on and verify GUI-first startup
1. Turn on the Pi.
2. Wait for the main ByteBite GUI (`src/app.py`) to appear.
3. Optional remote check:
```bash
ssh bytebite
systemctl status --no-pager bytebite.service
```

## 3) Connect the Android test device
1. Connect phone via USB.
2. Enable Android Developer Options + USB debugging.
3. Accept the RSA trust prompt on the phone.
4. Verify ADB:
```bash
adb devices -l
```
You must see at least one device with state `device` (not `unauthorized`).

## 4) Configure the experiment (`config.json`)
Default config file:
```bash
~/bytebite-data/config.json
```

Optional overrides:
1. `BYTEBITE_CONFIG` to set an explicit config file path
2. `BYTEBITE_DATA_DIR` to set a different data root (`<data-root>/config.json`, `<data-root>/logs`)
3. Legacy `~/ProductionProjectUI/config.json` is auto-migrated to `~/bytebite-data/config.json` on first run

Current defaults:
```json
{
  "device_serial": "",
  "gpio": { "start": 22, "cancel": 27, "view_logs": 17 },
  "paths": { "logs_dir": "~/bytebite-data/logs" },
  "offensive": {
    "marker_dir": "/sdcard/ByteBiteDemo",
    "marker_file": "bytebite_marker.txt",
    "trace_tag": "ByteBiteDemo",
    "open_url": "https://example.com",
    "test_apk_path": "",
    "test_package": "",
    "test_activity": "",
    "collect_network": true
  },
  "forensic": {
    "logcat_tail": 1000,
    "target_package": "",
    "pull_apk": true,
    "collect_network": true,
    "root_mode": false
  },
  "comparison": { "run_root_phase": true }
}
```

## 5) Run offensive simulation
From repo root:
```bash
python3 src/ui/offensive_menu.py
```

Control modes:
1. Physical GPIO available:
   - `Start` button runs offensive profile
   - `Cancel` requests stop after current step
   - `View Logs` prints latest run summary
2. GPIO backend unavailable:
   - App enters terminal control mode
   - Type: `start`, `cancel`, `view`, `quit`

Output:
```bash
~/bytebite-data/logs/<RUN_ID>/run.json
```

## 6) Run forensic extraction (independent of offensive mode)
```bash
python3 src/ui/forensic_runner.py
```

This performs:
1. Device readiness checks via ADB
2. Log collection
3. Package listing
4. Optional APK path/hash/pull (if `forensic.target_package` is set)
5. Optional network snapshot
6. Root indicator collection

Outputs:
1. `~/bytebite-data/logs/<RUN_ID>/run.json`
2. `~/bytebite-data/logs/<RUN_ID>/forensic_artifacts/` (includes pulled APKs when enabled)

## 7) Run stock-vs-root comparison suite
```bash
python3 src/ui/compare_runner.py
```

This runs:
1. Stock phase (`root_mode=false`)
2. Rooted phase (`root_mode=true`) if `su` is available and `comparison.run_root_phase=true`
3. Delta calculation across phases

Notes:
1. Offensive and forensic modules are logically separate.
2. Shared component is only the ADB transport layer.

Outputs:
1. `~/bytebite-data/logs/<RUN_ID>-compare/stock/run.json`
2. `~/bytebite-data/logs/<RUN_ID>-compare/rooted/run.json` (or skipped)
3. `~/bytebite-data/logs/<RUN_ID>-compare/comparison.json`

## 8) Generate dissertation-ready results table
```bash
python3 src/logic/results_table.py --limit 20 --top 8
```

This prints:
1. Run count
2. Success rate
3. Mean/median duration
4. Step bottlenecks by mean duration

## 8b) Excel workbook (single cumulative file)
Every run appends into one workbook:
```bash
~/bytebite-data/logs/results.xlsx
```

Sheets:
1. `Easy Read` (plain-language run overview for non-technical users)
2. `Summary` (auto-updated rollup + bottlenecks)
3. `Runs` (technical one row per run)
4. `Steps` (technical one row per step)

Open it from Pi desktop or VS Code file explorer. Optional command:
```bash
xdg-open ~/bytebite-data/logs/results.xlsx
```

Backfill older runs into the workbook:
```bash
python3 src/logic/rebuild_workbook.py
```

## 9) Recommended full run order (turn on to results)
1. Power on Pi and wait for GUI.
2. Connect and authorize Android device (`adb devices -l`).
3. Confirm/update `~/bytebite-data/config.json`.
4. Run `python3 src/ui/offensive_menu.py` and execute offensive run.
5. Run `python3 src/ui/forensic_runner.py`.
6. Run `python3 src/ui/compare_runner.py`.
7. Run `python3 src/logic/results_table.py --limit 20 --top 8`.
8. Archive `~/bytebite-data/logs/` for Chapter 4 evidence.

## Troubleshooting
1. `wait_for_device failed: command timed out`:
   - Device not connected/authorized. Re-check USB, debugging, RSA prompt, and `adb devices -l`.
2. `GPIO init failed ...`:
   - Current Kali image may lack a working GPIO backend. Use terminal mode controls (`start/cancel/view/quit`) or switch to a Pi image with supported GPIO stack.
3. `No display detected`:
   - If remote: reconnect with X forwarding (`ssh -Y ...`) or use attached Pi display.

## Project layout
1. `src/app.py` – GUI entry point.
2. `src/ui/offensive_menu.py` – offensive runner controller (GPIO/terminal mode).
3. `src/ui/forensic_runner.py` – independent forensic extraction runner.
4. `src/ui/compare_runner.py` – stock-vs-root differential suite runner.
5. `src/logic/` – ADB wrapper, offensive/forensic profiles, logging, results table script.
