"""Controlled, non-destructive offensive simulation profile."""
from __future__ import annotations

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


def _run_required_unlogged(name: str, action: Callable[[], CommandResult]) -> CommandResult:
    """Run a required action without adding a timed step to results."""
    result = action()
    if result.ok:
        return result
    raise RuntimeError(f"{name} failed: {result.stderr or result.stdout or 'unknown error'}")


def run_controlled_simulation(
    adb: Adb,
    logger: RunLogger,
    marker_dir: str,
    open_url: str,
    cancel_flag: Callable[[], bool],
    marker_file: str = "bytebite_marker.txt",
    trace_tag: str = "ByteBiteDemo",
    trace_token: str = "",
    apk_path: str = "",
    test_package: str = "",
    test_activity: str = "",
    collect_network: bool = True,
    root_mode: bool = False,
) -> None:
    """Execute a safe simulation sequence and log each step.

    If `root_mode` is true, adds root-only probes for differential experiments.
    """
    token = trace_token.strip() or "bytebite-unknown"
    marker_content = f"ByteBite controlled simulation marker trace_token={token}"
    marker_path = f"{marker_dir.rstrip('/')}/{marker_file}"

    if cancel_flag():
        return
    _run_step(logger, "adb_devices", adb.devices)

    if cancel_flag():
        return
    _run_step(logger, "wait_for_device", adb.wait_for_device)

    if cancel_flag():
        return
    _run_step(logger, "clear_logcat", adb.clear_logcat)

    if cancel_flag():
        return
    _run_required_unlogged("ensure_marker_dir", lambda: adb.ensure_marker_dir(marker_dir))

    if cancel_flag():
        return
    _run_required_unlogged(
        "write_marker",
        lambda: adb.write_marker(marker_dir, file_name=marker_file, content=marker_content),
    )

    if cancel_flag():
        return
    _run_step(
        logger,
        "write_trace_log",
        lambda: adb.write_trace_log(trace_tag, f"trace_token={token} marker={marker_path}"),
    )

    apk_path = apk_path.strip()
    if apk_path:
        if cancel_flag():
            return
        _run_step(logger, "install_test_apk", lambda: adb.install_apk(apk_path))

    test_package = test_package.strip()
    if test_package:
        if cancel_flag():
            return
        _run_step(logger, "launch_test_package", lambda: adb.launch_package(test_package, test_activity))

    if cancel_flag():
        return
    _run_step(logger, "open_url", lambda: adb.open_url(open_url))

    if collect_network:
        if cancel_flag():
            return
        _run_step(logger, "network_snapshot", adb.network_snapshot)

    if root_mode:
        if cancel_flag():
            return
        _run_step(logger, "root_probe_id", lambda: adb.su_shell("id"))

        if cancel_flag():
            return
        _run_step(
            logger,
            "root_probe_write",
            lambda: adb.su_shell(
                "printf '%s\\n' root_probe_ok > /data/local/tmp/bytebite_root_probe.txt && "
                "ls -l /data/local/tmp/bytebite_root_probe.txt"
            ),
        )

    if cancel_flag():
        return
    _run_step(logger, "collect_logcat", lambda: adb.dump_logcat(tail_lines=200))


def run_offensive_capability_profile(
    adb: Adb,
    logger: RunLogger,
    marker_dir: str,
    open_url: str,
    trace_token: str,
    root_mode: bool,
    marker_file: str = "bytebite_marker.txt",
    trace_tag: str = "ByteBiteDemo",
    apk_path: str = "",
    test_package: str = "",
    test_activity: str = "",
    collect_network: bool = True,
    cancel_flag: Callable[[], bool] = lambda: False,
) -> None:
    """Run offensive profile in stock (`root_mode=False`) or rooted mode."""
    run_controlled_simulation(
        adb=adb,
        logger=logger,
        marker_dir=marker_dir,
        open_url=open_url,
        cancel_flag=cancel_flag,
        marker_file=marker_file,
        trace_tag=trace_tag,
        trace_token=trace_token,
        apk_path=apk_path,
        test_package=test_package,
        test_activity=test_activity,
        collect_network=collect_network,
        root_mode=root_mode,
    )
