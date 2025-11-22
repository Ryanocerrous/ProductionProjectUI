"""Control handlers for device modes and settings.

Replace the stub implementations with real hardware or tool integrations
(GPIO triggers, launching scripts, etc.).
"""
from __future__ import annotations

import platform
from datetime import date

from logic.system_info import get_memory_summary

APP_NAME = "ByteBite"
APP_VERSION = "0.1.0"
LATEST_UPDATE = "2025-11-15 — Stability and UI polish"


def enter_forensic_mode() -> str:
    """Hook up to your forensic workflow here."""
    # TODO: integrate with actual forensic tooling/flows
    return "Forensic mode ready. (Replace this with real actions.)"


def enter_offensive_mode() -> str:
    """Hook up to your offensive tooling here."""
    # TODO: integrate with actual offensive tooling/flows
    return "Offensive mode armed. (Replace this with real actions.)"


def open_settings() -> str:
    """Open or apply device settings."""
    # TODO: adjust settings (network/display/preferences) as needed
    return "Settings panel placeholder. (Extend with real settings UI.)"


def show_about() -> str:
    """Provide app metadata."""
    hostname = platform.node() or "raspberrypi"
    os_name = platform.platform()
    today = date.today().isoformat()
    memory = get_memory_summary()
    lines = [
        f"{APP_NAME} v{APP_VERSION}",
        f"Latest update: {LATEST_UPDATE}",
        f"OS: {os_name}",
        f"Device: {hostname}",
        f"Memory: {memory}",
        f"Date: {today}",
        "ByteBite — All rights reserved.",
    ]
    return "\n".join(lines)
