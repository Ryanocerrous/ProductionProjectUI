from __future__ import annotations
import select
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from gpiozero import Button, Device
    try:
        from gpiozero.pins.lgpio import LGPIOFactory
    except Exception:
        LGPIOFactory = None
    try:
        from gpiozero.pins.pigpio import PiGPIOFactory
    except Exception:
        PiGPIOFactory = None
except Exception:
    Button = None
    Device = None
    LGPIOFactory = None
    PiGPIOFactory = None

from logic.adb import Adb
from logic.runlog import RunLogger
from logic.offensive_profile import run_controlled_simulation
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path, resolve_logs_dir

CONFIG_PATH = resolve_config_path(PROJECT_ROOT)
DEFAULT_CONFIG = build_default_config()


class _PinRef:
    def __init__(self, number: int):
        self.number = number


class _NullButton:
    def __init__(self, number: int):
        self.pin = _PinRef(number)
        self.when_pressed = None

    def close(self) -> None:
        return


class OffensiveApp:
    def __init__(self):
        if Button is None:
            raise RuntimeError("gpiozero is not installed. Install with: sudo apt install -y python3-gpiozero")
        self._init_gpio_factory()
        cfg = load_or_create_config(CONFIG_PATH, DEFAULT_CONFIG)
        self._gpio_available = True

        self.logs_dir = resolve_logs_dir(PROJECT_ROOT, cfg)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.results_workbook = self.logs_dir / "results.xlsx"

        self.adb = Adb(serial=cfg.get("device_serial", "") or "")

        off_cfg = cfg["offensive"]
        self.marker_dir = off_cfg["marker_dir"]
        self.marker_file = off_cfg.get("marker_file", "bytebite_marker.txt")
        self.trace_tag = off_cfg.get("trace_tag", "ByteBiteDemo")
        self.open_url = off_cfg["open_url"]
        self.test_apk_path = off_cfg.get("test_apk_path", "")
        self.test_package = off_cfg.get("test_package", "")
        self.test_activity = off_cfg.get("test_activity", "")
        self.collect_network = bool(off_cfg.get("collect_network", True))

        pins = cfg["gpio"]
        try:
            self.btn_start = Button(pins["start"], pull_up=True, bounce_time=0.05)
            self.btn_cancel = Button(pins["cancel"], pull_up=True, bounce_time=0.05)
            self.btn_view = Button(pins["view_logs"], pull_up=True, bounce_time=0.05)
        except Exception as exc:
            self._gpio_available = False
            hint = (
                "Install a supported backend (lgpio/pigpio) or run on Pi-native GPIO image."
                if LGPIOFactory is None and PiGPIOFactory is None
                else "Check GPIO permissions/hardware and retry."
            )
            print(f"[ByteBite] WARNING: GPIO init failed: {exc}. {hint}")
            print("[ByteBite] Entering terminal control mode (start/cancel/view/quit).")
            self.btn_start = _NullButton(pins["start"])
            self.btn_cancel = _NullButton(pins["cancel"])
            self.btn_view = _NullButton(pins["view_logs"])

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = False
        self._state = "SAFE"

        self.btn_start.when_pressed = self.start_pressed
        self.btn_cancel.when_pressed = self.cancel_pressed
        self.btn_view.when_pressed = self.view_pressed

        print("[ByteBite] Offensive Menu ready.")
        print(f"[ByteBite] Config = {CONFIG_PATH}")
        print(f"[ByteBite] Logs = {self.logs_dir}")
        print(f"[ByteBite] Excel = {self.results_workbook}")
        print("[ByteBite] State = SAFE (nothing runs until START)")
        if not self._gpio_available:
            print("[ByteBite] Terminal controls: type start | cancel | view | quit")

    def _init_gpio_factory(self) -> None:
        if Device is None:
            return
        if LGPIOFactory is not None:
            try:
                Device.pin_factory = LGPIOFactory()
                print("[ByteBite] GPIO backend = lgpio")
                return
            except Exception:
                pass
        if PiGPIOFactory is not None:
            try:
                Device.pin_factory = PiGPIOFactory()
                print("[ByteBite] GPIO backend = pigpio")
            except Exception:
                pass

    def _set_state(self, s: str) -> None:
        with self._lock:
            self._state = s
        print(f"[ByteBite] State = {s}")

    def _is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_pressed(self) -> None:
        if self._is_running():
            print("[ByteBite] Already running.")
            return

        # Check device is attached (non-destructive)
        devs = self.adb.devices()
        has_authorised_device = False
        for line in devs.stdout.splitlines():
            cols = line.split()
            if len(cols) >= 2 and cols[1] == "device":
                has_authorised_device = True
                break
        if not has_authorised_device:
            print("[ByteBite] No authorised ADB device detected.")
            print("[ByteBite] Run: adb devices -l")
            return

        self._cancel = False
        self._set_state("RUNNING")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.logs_dir / run_id
        logger = RunLogger(run_dir, results_workbook=self.results_workbook)
        logger.set_meta(
            run_id=run_id,
            mode="offensive",
            profile="controlled_simulation",
            trace_tag=self.trace_tag,
            trace_token=run_id,
            marker_file=self.marker_file,
            test_apk_path=self.test_apk_path,
            test_package=self.test_package,
            test_activity=self.test_activity,
            collect_network=self.collect_network,
            gpio_pins={
                "start": self.btn_start.pin.number,
                "cancel": self.btn_cancel.pin.number,
                "view": self.btn_view.pin.number,
            },
        )

        def worker():
            status = "success"
            err = None
            try:
                run_controlled_simulation(
                    adb=self.adb,
                    logger=logger,
                    marker_dir=self.marker_dir,
                    open_url=self.open_url,
                    cancel_flag=lambda: self._cancel,
                    marker_file=self.marker_file,
                    trace_tag=self.trace_tag,
                    trace_token=run_id,
                    apk_path=self.test_apk_path,
                    test_package=self.test_package,
                    test_activity=self.test_activity,
                    collect_network=self.collect_network,
                )
                if self._cancel:
                    status = "cancelled"
            except Exception as e:
                status = "error"
                err = str(e)

            out = logger.write(status=status, error=err)
            if status == "success":
                self._set_state("COMPLETE")
            elif status == "cancelled":
                self._set_state("CANCELLED")
            else:
                self._set_state("ERROR")

            print(f"[ByteBite] Run saved: {out}")

            # Return to SAFE after a short pause so you can see outcome
            time.sleep(1.0)
            self._set_state("SAFE")

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def cancel_pressed(self) -> None:
        if not self._is_running():
            print("[ByteBite] Nothing to cancel.")
            return
        print("[ByteBite] Cancel requested.")
        self._cancel = True

    def view_pressed(self) -> None:
        runs = sorted(self.logs_dir.glob("*"))
        if not runs:
            print("[ByteBite] No runs logged yet.")
            return
        latest = runs[-1]
        run_json = latest / "run.json"
        print(f"[ByteBite] Latest run: {latest.name}")
        if run_json.exists():
            data = json.loads(run_json.read_text(encoding="utf-8"))
            print(json.dumps({
                "status": data.get("status"),
                "elapsed_s": data.get("elapsed_s"),
                "profile": data.get("meta", {}).get("profile"),
                "steps": [(s["name"], s["ok"], s["duration_ms"]) for s in data.get("steps", [])]
            }, indent=2))
        else:
            print("[ByteBite] Latest run has no run.json (may have been interrupted early).")

    def loop(self):
        try:
            while True:
                if not self._gpio_available and sys.stdin.isatty():
                    ready, _, _ = select.select([sys.stdin], [], [], 0.5)
                    if ready:
                        cmd = sys.stdin.readline().strip().lower()
                        if cmd in {"start", "s"}:
                            self.start_pressed()
                        elif cmd in {"cancel", "c"}:
                            self.cancel_pressed()
                        elif cmd in {"view", "v"}:
                            self.view_pressed()
                        elif cmd in {"quit", "q", "exit"}:
                            break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            for btn in (self.btn_start, self.btn_cancel, self.btn_view):
                try:
                    btn.close()
                except Exception:
                    pass

if __name__ == "__main__":
    app = OffensiveApp()
    app.loop()
