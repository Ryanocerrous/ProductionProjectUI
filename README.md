# ProductionProjectUI (ByteBite) - Device Manual

ByteBite is a Raspberry Pi forensic workflow device with:
1. A physical-button UI (`left`, `right`, `enter`).
2. Android evidence collection through ADB.
3. Post-extraction analysis with rule-based + optional LLM triage.
4. Investigator-ready outputs (CSV + Excel + narrative summary).

## 1. What The Device Does

ByteBite supports three core workflows:
1. **Forensic extraction** from a connected Android device.
2. **Forensic post-analysis** of extracted artefacts (including data on external USB storage).
3. **Comparison runs** (stock vs rooted) for capability testing.

After extraction, ByteBite can automatically:
1. Classify artefacts as `safe`, `suspicious`, or `high_priority`.
2. Sort artefacts into triage folders.
3. Build a readable timeline from filesystem times, EXIF dates, and log/message timestamps.
4. Generate an LLM-authored narrative findings summary (when LLM is enabled).
5. Build an `investigator_report.xlsx` workbook.

## 2. Hardware And Wiring

Raspberry Pi GPIO navigation buttons (BCM):
1. `left` = GPIO 22
2. `enter` = GPIO 27
3. `right` = GPIO 17

Use module wiring that provides valid HIGH/LOW transitions on press (your tested setup uses 3.3V/VCC + OUT correctly).

## 3. One-Time Software Setup (Pi)

Clone/copy repo to:
```bash
/home/kali/ProductionProjectUI
```

Install runtime dependencies:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-tk python3-gpiozero android-sdk-platform-tools python3-openpyxl
```

Prepare data/config:
```bash
mkdir -p ~/bytebite-data/logs
cp ~/ProductionProjectUI/config.example.json ~/bytebite-data/config.json
```

Enable startup service:
```bash
sudo systemctl enable --now bytebite.service
sudo systemctl status --no-pager bytebite.service
```

## 4. Startup And Daily Use

1. Power on device.
2. Wait for ByteBite UI to appear.
3. Connect Android phone via USB.
4. Confirm USB debugging authorized:
```bash
adb devices -l
```
5. Navigate home UI using physical `left/right/enter` buttons.

## 5. Configuration (Important)

Primary config:
```bash
~/bytebite-data/config.json
```

Environment overrides:
1. `BYTEBITE_CONFIG` for explicit config file path.
2. `BYTEBITE_DATA_DIR` for data root (`<root>/config.json`, `<root>/logs`).

Key sections:
1. `ui_gpio`: home UI button pins.
2. `forensic`: extraction behaviour.
3. `forensic_analysis`: triage/timeline/report behaviour.
4. `llm`: local llama.cpp integration.

## 6. Forensic Extraction Workflow

Run:
```bash
cd ~/ProductionProjectUI
python3 src/ui/forensic_runner.py
```

Extraction stage performs:
1. Device readiness checks.
2. Logcat collection.
3. Package listing.
4. Optional APK path/hash/pull.
5. Optional network snapshot.
6. Root status collection.

Post-extraction analysis then runs automatically (if enabled).

## 7. Post-Extraction Analysis Workflow

### 7.1 Automatic (during forensic run)
Automatically runs at end of extraction via `run_forensic_extraction(...)`.

### 7.2 Manual (for existing USB extraction folders)
```bash
cd ~/ProductionProjectUI
python3 scripts/forensic_post_analysis.py --source /media/kali/YOUR_USB/case_folder
```

## 8. Analysis Outputs (Readable Investigator Format)

Given source folder:
```bash
.../forensic_artifacts
```
ByteBite writes:
```text
.../forensic_artifacts/analysis/
  analysis_summary.json
  llm_findings_summary.txt
  llm_findings_summary.md
  investigator_report.xlsx
  triage/
    safe/
    suspicious/
    high_priority/
    triage_manifest.csv
    triage_manifest.json
    triage_manifest.xlsx
  timeline/
    timeline.csv
    timeline.json
    timeline.xlsx
```

## 9. LLM Integration

Set in `config.json`:
```json
"llm": {
  "enabled": true,
  "binary": "~/llama.cpp/build/bin/llama-cli",
  "model": "~/llama.cpp/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
  "temperature": 0.2,
  "context_tokens": 256,
  "max_tokens": 256,
  "threads": 2,
  "gpu_layers": 0,
  "timeout_s": 120
}
```

Notes:
1. If LLM is disabled or fails, ByteBite still triages using rule keywords.
2. LLM outputs are used for:
   1. Per-artefact classification assistance.
   2. Narrative findings summary (`llm_findings_summary.*`).

## 10. Triage Logic (Safe / Suspicious / High Priority)

ByteBite uses:
1. Rule-based keyword scoring (`high_priority_keywords`, `suspicious_keywords`).
2. Optional LLM classification.
3. Final label uses the higher-severity of rule and LLM result.

Defaults include terms such as:
1. High-priority: `murder`, `kill`, `knife`, `gun`, `firearm`, `bomb`, `kidnap`, `ransom`.
2. Suspicious: `burner`, `encrypted`, `vault`, `wipe`, `delete`, `crypto`, `drugs`, `weapon`, `hide`.

You can edit these lists in `forensic_analysis`.

## 11. Timeline Summary

Timeline currently extracts:
1. Filesystem timestamps (`mtime`, `ctime`).
2. EXIF image timestamps (where available).
3. Text/log timestamps:
   1. ISO datetime forms
   2. Simple datetime forms
   3. Logcat-style timestamps
   4. Epoch-like timestamps

Output is sorted chronologically and exported to CSV/Excel.

## 12. Comparison Workflow (Stock vs Rooted)

Run:
```bash
cd ~/ProductionProjectUI
python3 src/ui/compare_runner.py
```

Outputs:
1. `.../<RUN_ID>-compare/stock/run.json`
2. `.../<RUN_ID>-compare/rooted/run.json` (or skipped)
3. `.../<RUN_ID>-compare/comparison.json`

Each phase includes forensic extraction and post-analysis outputs.

## 13. Home UI Controls

1. `left`: move selection left.
2. `right`: move selection right.
3. `enter`: activate selected action.

If buttons stop responding:
1. Check service is running.
2. Verify pin config and wiring.
3. Confirm GPIO backend availability in logs.

## 14. Service Commands

```bash
sudo systemctl restart bytebite.service
sudo systemctl status --no-pager bytebite.service
sudo journalctl -u bytebite.service -n 120 --no-pager
```

## 15. Troubleshooting

1. `adb wait-for-device` timeout:
   1. Reconnect USB.
   2. Re-authorize RSA prompt on phone.
   3. Re-check `adb devices -l`.
2. LLM memory errors (`failed to allocate`):
   1. Use a smaller GGUF.
   2. Lower `context_tokens` and `max_tokens`.
3. `forensic_post_analysis.py` says source missing:
   1. Check USB mount path (`/media/kali/...`).
4. No Excel outputs:
   1. Install `python3-openpyxl`.

## 16. Project File Guide

1. `src/app.py`: GUI entry point.
2. `src/buttons.py`: GPIO button backend.
3. `src/ui/main_window.py`: home UI and screens.
4. `src/ui/forensic_runner.py`: forensic extraction runner.
5. `src/ui/compare_runner.py`: stock vs rooted runner.
6. `src/logic/adb.py`: ADB wrapper.
7. `src/logic/forensic_profile.py`: extraction workflow orchestration.
8. `src/logic/forensic_analysis.py`: triage + timeline + report generation.
9. `src/logic/local_llm.py`: llama.cpp subprocess integration.
10. `scripts/forensic_post_analysis.py`: manual analysis on existing extraction folder.

## 17. Recommended Investigator Run Sequence

1. Boot device and verify UI.
2. Connect Android and verify `adb devices -l`.
3. Run forensic extraction:
```bash
python3 src/ui/forensic_runner.py
```
4. Open analysis folder (`.../forensic_artifacts/analysis/`).
5. Review:
   1. `investigator_report.xlsx`
   2. `llm_findings_summary.md`
   3. `triage/high_priority/`
   4. `timeline/timeline.csv`

