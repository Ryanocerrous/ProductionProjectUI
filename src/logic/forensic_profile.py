"""Forensic traceability check using marker file + Android logcat."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from logic.adb import Adb, CommandResult
from logic.runlog import RunLogger


def _result_details(result: CommandResult) -> dict[str, object]:
    details: dict[str, object] = {"returncode": result.returncode}
    if result.stdout:
        details["stdout"] = result.stdout[:400]
    if result.stderr:
        details["stderr"] = result.stderr[:400]
    return details


def _run_step(logger: RunLogger, name: str, action: Callable[[], CommandResult]) -> CommandResult:
    started = logger.begin_step(name)
    result = action()
    if result.ok:
        logger.end_step(name=name, started_perf=started, ok=True, details=_result_details(result))
        return result

    logger.end_step(
        name=name,
        started_perf=started,
        ok=False,
        details=_result_details(result),
        error=f"{name} failed with return code {result.returncode}",
    )
    raise RuntimeError(f"{name} failed: {result.stderr or result.stdout or 'unknown error'}")


def _extract_trace_token(marker_text: str) -> str:
    match = re.search(r"trace_token=([A-Za-z0-9._:-]+)", marker_text)
    return match.group(1) if match else ""


def _package_paths_from_pm_output(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            paths.append(line.split("package:", 1)[1].strip())
    return paths


def run_forensic_traceability_check(
    adb: Adb,
    logger: RunLogger,
    marker_dir: str,
    marker_file: str = "bytebite_marker.txt",
    trace_tag: str = "ByteBiteDemo",
    logcat_tail: int = 1000,
    cancel_flag: Callable[[], bool] = lambda: False,
) -> None:
    """Validate that a marker on-device is corroborated by logcat evidence."""
    marker_path = f"{marker_dir.rstrip('/')}/{marker_file}"

    if cancel_flag():
        return
    _run_step(logger, "adb_devices", adb.devices)

    if cancel_flag():
        return
    _run_step(logger, "wait_for_device", adb.wait_for_device)

    if cancel_flag():
        return
    marker_result = _run_step(logger, "read_marker", lambda: adb.read_text_file(marker_path))
    marker_text = marker_result.stdout
    trace_token = _extract_trace_token(marker_text)

    validate_marker_started = logger.begin_step("validate_marker")
    if not marker_text:
        logger.end_step(
            name="validate_marker",
            started_perf=validate_marker_started,
            ok=False,
            error=f"Marker file is empty or unreadable: {marker_path}",
        )
        raise RuntimeError(f"Marker file is empty or unreadable: {marker_path}")
    if not trace_token:
        logger.end_step(
            name="validate_marker",
            started_perf=validate_marker_started,
            ok=False,
            error="Marker does not contain trace_token=...",
            details={"marker_preview": marker_text[:200]},
        )
        raise RuntimeError("Marker does not contain trace_token=...")
    logger.end_step(
        name="validate_marker",
        started_perf=validate_marker_started,
        ok=True,
        details={"trace_token": trace_token, "marker_path": marker_path},
    )

    if cancel_flag():
        return
    logcat_result = _run_step(logger, "collect_logcat", lambda: adb.dump_logcat(tail_lines=logcat_tail))
    logcat_text = logcat_result.stdout

    validate_trace_started = logger.begin_step("validate_traceability")
    has_tag = trace_tag in logcat_text
    has_token = trace_token in logcat_text
    ok = has_tag and has_token
    logger.end_step(
        name="validate_traceability",
        started_perf=validate_trace_started,
        ok=ok,
        details={"trace_tag_found": has_tag, "trace_token_found": has_token, "trace_token": trace_token},
        error=None if ok else "Trace token/tag not found in logcat output",
    )
    if not ok:
        raise RuntimeError("Traceability check failed: marker and logcat evidence could not be correlated")


def run_forensic_extraction(
    adb: Adb,
    logger: RunLogger,
    output_dir: Path,
    target_package: str = "",
    pull_apk: bool = True,
    collect_network: bool = True,
    root_mode: bool = False,
    logcat_tail: int = 1000,
    cancel_flag: Callable[[], bool] = lambda: False,
) -> None:
    """Collect extraction artefacts for forensic comparison."""
    output_dir.mkdir(parents=True, exist_ok=True)
    apks_dir = output_dir / "apks"
    apks_dir.mkdir(parents=True, exist_ok=True)

    if cancel_flag():
        return
    _run_step(logger, "adb_devices", adb.devices)

    if cancel_flag():
        return
    _run_step(logger, "wait_for_device", adb.wait_for_device)

    if cancel_flag():
        return
    _run_step(logger, "collect_logcat", lambda: adb.dump_logcat(tail_lines=logcat_tail))

    if cancel_flag():
        return
    _run_step(logger, "list_packages", adb.list_packages)

    pkg = target_package.strip()
    if pkg:
        if cancel_flag():
            return
        paths_result = _run_step(logger, "package_paths", lambda: adb.package_paths(pkg))
        remote_paths = _package_paths_from_pm_output(paths_result.stdout)
        if not remote_paths:
            raise RuntimeError(f"No package paths found for: {pkg}")

        for idx, remote_path in enumerate(remote_paths, start=1):
            if cancel_flag():
                return
            _run_step(logger, f"hash_remote_apk_{idx}", lambda rp=remote_path: adb.sha256_file(rp, use_root=root_mode))

            if pull_apk:
                local_name = f"{pkg.replace('.', '_')}_{idx}.apk"
                local_path = apks_dir / local_name
                if cancel_flag():
                    return
                _run_step(logger, f"pull_apk_{idx}", lambda rp=remote_path, lp=local_path: adb.pull(rp, str(lp)))

    if collect_network:
        if cancel_flag():
            return
        if root_mode:
            _run_step(logger, "network_snapshot_root", adb.network_snapshot_root)
        else:
            _run_step(logger, "network_snapshot", adb.network_snapshot)

    if cancel_flag():
        return
    _run_step(logger, "root_status", adb.root_status)
