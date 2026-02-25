"""Small ADB wrapper used by the controlled offensive simulation flow."""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Adb:
    def __init__(self, serial: str = "", adb_bin: str = "adb") -> None:
        self.serial = serial.strip()
        self.adb_bin = adb_bin

    def _base(self) -> list[str]:
        cmd = [self.adb_bin]
        if self.serial:
            cmd.extend(["-s", self.serial])
        return cmd

    def _run(self, args: Sequence[str], timeout_s: float = 30.0) -> CommandResult:
        cmd = self._base() + list(args)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
            return CommandResult(
                args=cmd,
                returncode=proc.returncode,
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
            )
        except FileNotFoundError:
            return CommandResult(args=cmd, returncode=127, stdout="", stderr=f"{self.adb_bin}: command not found")
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                args=cmd,
                returncode=124,
                stdout=(exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "command timed out").strip() if isinstance(exc.stderr, str) else "command timed out",
            )

    def devices(self) -> CommandResult:
        return self._run(["devices", "-l"], timeout_s=10.0)

    def wait_for_device(self, timeout_s: float = 30.0) -> CommandResult:
        return self._run(["wait-for-device"], timeout_s=timeout_s)

    def shell(self, command: str, timeout_s: float = 30.0) -> CommandResult:
        return self._run(["shell", command], timeout_s=timeout_s)

    def su_shell(self, command: str, timeout_s: float = 30.0) -> CommandResult:
        safe_cmd = shlex.quote(command)
        return self.shell(f"su -c {safe_cmd}", timeout_s=timeout_s)

    def clear_logcat(self) -> CommandResult:
        return self.shell("logcat -c", timeout_s=10.0)

    def dump_logcat(self, tail_lines: int = 200) -> CommandResult:
        lines = max(1, min(tail_lines, 2000))
        return self.shell(f"logcat -d -t {lines}", timeout_s=40.0)

    def list_packages(self, prefix: str = "") -> CommandResult:
        cmd = "pm list packages"
        if prefix:
            cmd += f" {shlex.quote(prefix)}"
        return self.shell(cmd, timeout_s=25.0)

    def package_paths(self, package_name: str) -> CommandResult:
        return self.shell(f"pm path {shlex.quote(package_name)}", timeout_s=20.0)

    def install_apk(self, apk_path: str, replace: bool = True, grant: bool = True) -> CommandResult:
        host_apk = Path(apk_path).expanduser()
        if not host_apk.exists():
            return CommandResult(
                args=self._base() + ["install", str(host_apk)],
                returncode=2,
                stdout="",
                stderr=f"APK not found: {host_apk}",
            )
        args = ["install"]
        if replace:
            args.append("-r")
        if grant:
            args.append("-g")
        args.append(str(host_apk))
        return self._run(args, timeout_s=120.0)

    def launch_package(self, package_name: str, activity: str = "") -> CommandResult:
        pkg = package_name.strip()
        if not pkg:
            return CommandResult(args=[], returncode=2, stdout="", stderr="package_name is required")
        if activity.strip():
            component = f"{pkg}/{activity.strip()}"
            return self.shell(f"am start -n {shlex.quote(component)}", timeout_s=25.0)
        return self.shell(f"monkey -p {shlex.quote(pkg)} -c android.intent.category.LAUNCHER 1", timeout_s=25.0)

    def pull(self, remote_path: str, local_path: str) -> CommandResult:
        local = Path(local_path).expanduser()
        local.parent.mkdir(parents=True, exist_ok=True)
        return self._run(["pull", remote_path, str(local)], timeout_s=120.0)

    def sha256_file(self, remote_path: str, use_root: bool = False) -> CommandResult:
        command = (
            f"sha256sum {shlex.quote(remote_path)} "
            f"|| toybox sha256sum {shlex.quote(remote_path)} "
            f"|| md5sum {shlex.quote(remote_path)}"
        )
        if use_root:
            return self.su_shell(command, timeout_s=25.0)
        return self.shell(command, timeout_s=25.0)

    def network_snapshot(self) -> CommandResult:
        cmd = (
            "echo '=== ip addr ==='; ip addr 2>/dev/null || true; "
            "echo '=== ip route ==='; ip route 2>/dev/null || true; "
            "echo '=== /proc/net/tcp ==='; cat /proc/net/tcp 2>/dev/null || true; "
            "echo '=== /proc/net/tcp6 ==='; cat /proc/net/tcp6 2>/dev/null || true; "
            "echo '=== netstat ==='; netstat -tunap 2>/dev/null || true; "
            "echo '=== ss ==='; ss -tunap 2>/dev/null || true"
        )
        return self.shell(cmd, timeout_s=30.0)

    def network_snapshot_root(self) -> CommandResult:
        cmd = (
            "echo '=== ip addr ==='; ip addr 2>/dev/null || true; "
            "echo '=== ip route ==='; ip route 2>/dev/null || true; "
            "echo '=== /proc/net/tcp ==='; cat /proc/net/tcp 2>/dev/null || true; "
            "echo '=== /proc/net/tcp6 ==='; cat /proc/net/tcp6 2>/dev/null || true; "
            "echo '=== netstat ==='; netstat -tunap 2>/dev/null || true; "
            "echo '=== ss ==='; ss -tunap 2>/dev/null || true"
        )
        return self.su_shell(cmd, timeout_s=30.0)

    def root_status(self) -> CommandResult:
        cmd = (
            "echo '=== su which ==='; which su 2>/dev/null; "
            "echo '=== su id ==='; su -c id 2>/dev/null; "
            "echo '=== whoami ==='; whoami 2>/dev/null; "
            "echo '=== test su paths ==='; ls -l /system/xbin/su /system/bin/su /sbin/su 2>/dev/null || true"
        )
        return self.shell(cmd, timeout_s=20.0)

    def read_text_file(self, file_path: str) -> CommandResult:
        return self.shell(f"cat {shlex.quote(file_path)}", timeout_s=15.0)

    def ensure_marker_dir(self, marker_dir: str) -> CommandResult:
        return self.shell(f"mkdir -p {shlex.quote(marker_dir)}", timeout_s=10.0)

    def write_marker(
        self,
        marker_dir: str,
        file_name: str = "bytebite_marker.txt",
        content: str = "ByteBite controlled simulation marker",
    ) -> CommandResult:
        safe_dir = shlex.quote(marker_dir.rstrip("/") or "/")
        safe_file = shlex.quote(f"{marker_dir.rstrip('/')}/{file_name}")
        safe_content = shlex.quote(content)
        cmd = (
            f"mkdir -p {safe_dir} && "
            f"printf '%s\\n' {safe_content} > {safe_file} && "
            f"date -u +%Y-%m-%dT%H:%M:%SZ >> {safe_file}"
        )
        return self.shell(cmd, timeout_s=15.0)

    def open_url(self, url: str) -> CommandResult:
        safe_url = shlex.quote(url)
        return self.shell(f"am start -a android.intent.action.VIEW -d {safe_url}", timeout_s=20.0)

    def write_trace_log(self, tag: str, message: str) -> CommandResult:
        safe_tag = shlex.quote(tag)
        safe_message = shlex.quote(message)
        return self.shell(f"log -t {safe_tag} {safe_message}", timeout_s=10.0)
