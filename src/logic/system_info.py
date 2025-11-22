"""Helpers for retrieving lightweight system information on the Pi."""
from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime
from typing import List


def _uptime_pretty() -> str:
    try:
        output = subprocess.check_output(["uptime", "-p"], text=True)
        return output.strip().replace("up ", "")
    except Exception:
        return "unknown"


def _load_average() -> str:
    try:
        one, five, fifteen = os.getloadavg()
        return f"{one:.2f} / {five:.2f} / {fifteen:.2f}"
    except Exception:
        return "n/a"


def _cpu_temperature() -> str:
    thermal_path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(thermal_path, "r", encoding="utf-8") as f:
            millideg = int(f.read().strip())
        return f"{millideg / 1000:.1f}°C"
    except Exception:
        return "n/a"


def get_system_summary() -> str:
    """Return a multi-line summary string for display."""
    parts: List[str] = [
        f"Device: {platform.node() or 'raspberrypi'}",
        f"Platform: {platform.platform()}",
        f"CPU temp: {_cpu_temperature()}",
        f"Load (1/5/15 min): {_load_average()}",
        f"Uptime: {_uptime_pretty()}",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    return "\n".join(parts)


def get_battery_percentage() -> int | None:
    """Best-effort battery percentage reader; returns None if not available."""
    candidates = [
        "/sys/class/power_supply/BAT0/capacity",
        "/sys/class/power_supply/battery/capacity",
        "/sys/class/power_supply/BAT1/capacity",
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = int(f.read().strip())
            if 0 <= value <= 100:
                return value
        except Exception:
            continue
    return None


def get_memory_summary() -> str:
    """Return a compact memory summary string."""
    try:
        meminfo: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, value, *_ = line.strip().split()
                meminfo[key.rstrip(":")] = int(value)  # kB
        total_kb = meminfo.get("MemTotal")
        free_kb = meminfo.get("MemAvailable") or meminfo.get("MemFree")
        if total_kb:
            total_gb = total_kb / (1024 * 1024)
            if free_kb:
                free_gb = free_kb / (1024 * 1024)
                return f"{total_gb:.1f} GB total / {free_gb:.1f} GB free"
            return f"{total_gb:.1f} GB total"
    except Exception:
        pass
    return "Memory: n/a"
