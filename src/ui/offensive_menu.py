from __future__ import annotations
import importlib
import json
import select
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

Button: Any = None
Device: Any = None
LGPIOFactory: Any = None
NativeFactory: Any = None
PiGPIOFactory: Any = None
GPIO: Any = None
GPIOD: Any = None

try:
    gpiozero = importlib.import_module("gpiozero")
    Button = getattr(gpiozero, "Button", None)
    Device = getattr(gpiozero, "Device", None)
except Exception:
    Button = None
    Device = None

if Button is not None:
    try:
        LGPIOFactory = getattr(importlib.import_module("gpiozero.pins.lgpio"), "LGPIOFactory", None)
    except Exception:
        LGPIOFactory = None
    try:
        NativeFactory = getattr(importlib.import_module("gpiozero.pins.native"), "NativeFactory", None)
    except Exception:
        NativeFactory = None
    try:
        PiGPIOFactory = getattr(importlib.import_module("gpiozero.pins.pigpio"), "PiGPIOFactory", None)
    except Exception:
        PiGPIOFactory = None

try:
    GPIO = importlib.import_module("RPi.GPIO")
except Exception:
    GPIO = None

try:
    GPIOD = importlib.import_module("gpiod")
except Exception:
    GPIOD = None

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
        cfg = load_or_create_config(CONFIG_PATH, DEFAULT_CONFIG)
        self._gpio_available = False
        self._gpio_backend = "terminal"
        self._rpi_pins: tuple[int, int, int] | None = None
        self._gpiod_request: Any | None = None
        self._gpiod_stop = threading.Event()
        self._gpiod_thread: threading.Thread | None = None
        self._gpiod_last: dict[int, int] = {}
        self._gpiod_idle: dict[int, int] = {}

        self.logs_dir = resolve_logs_dir(PROJECT_ROOT, cfg)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.results_workbook = self.logs_dir / "results.xlsx"

        self.adb = Adb(serial=cfg.get("device_serial", "") or "")

        off_cfg = cfg.get("offensive", {})
        off_defaults = DEFAULT_CONFIG.get("offensive", {})
        self.marker_dir = str(off_cfg.get("marker_dir", off_defaults.get("marker_dir", "/sdcard/ByteBiteDemo")))
        self.marker_file = str(off_cfg.get("marker_file", off_defaults.get("marker_file", "bytebite_marker.txt")))
        self.trace_tag = str(off_cfg.get("trace_tag", off_defaults.get("trace_tag", "ByteBiteDemo")))
        self.open_url = str(off_cfg.get("open_url", off_defaults.get("open_url", "https://example.com")))
        self.test_apk_path = off_cfg.get("test_apk_path", "")
        self.test_package = off_cfg.get("test_package", "")
        self.test_activity = off_cfg.get("test_activity", "")
        self.collect_network = bool(off_cfg.get("collect_network", True))

        pins_cfg = cfg.get("gpio", {})
        default_pins = DEFAULT_CONFIG.get("gpio", {})
        start_pin = int(pins_cfg.get("start", default_pins.get("start", 22)))
        cancel_pin = int(pins_cfg.get("cancel", default_pins.get("cancel", 27)))
        view_pin = int(pins_cfg.get("view_logs", default_pins.get("view_logs", 17)))

        # Prefer libgpiod on Pi 5 / modern kernels.
        if self._init_gpiod(start_pin, cancel_pin, view_pin):
            self._gpio_available = True
            self._gpio_backend = "gpiod"
            print("[ByteBite] GPIO backend = gpiod")
        elif self._init_rpi_gpio(start_pin, cancel_pin, view_pin):
            self._gpio_available = True
            self._gpio_backend = "rpi_gpio"
            print("[ByteBite] GPIO backend = RPi.GPIO")
        elif Button is not None:
            self._init_gpio_factory()
            try:
                self.btn_start = Button(start_pin, pull_up=True, bounce_time=0.05)
                self.btn_cancel = Button(cancel_pin, pull_up=True, bounce_time=0.05)
                self.btn_view = Button(view_pin, pull_up=True, bounce_time=0.05)
                self._gpio_available = True
                self._gpio_backend = "gpiozero"
            except Exception as exc:
                hint = (
                    "Install a supported backend (lgpio/pigpio) or run on Pi-native GPIO image."
                    if LGPIOFactory is None and PiGPIOFactory is None
                    else "Check GPIO permissions/hardware and retry."
                )
                print(f"[ByteBite] WARNING: gpiozero init failed: {exc}. {hint}")
                self._use_terminal_buttons(start_pin, cancel_pin, view_pin)
        else:
            print("[ByteBite] WARNING: gpiozero/RPi.GPIO unavailable; GPIO controls disabled.")
            self._use_terminal_buttons(start_pin, cancel_pin, view_pin)

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = False
        self._state = "SAFE"

        if self._gpio_backend == "gpiozero":
            self.btn_start.when_pressed = self.start_pressed
            self.btn_cancel.when_pressed = self.cancel_pressed
            self.btn_view.when_pressed = self.view_pressed

        print("[ByteBite] Offensive Menu ready.")
        print(f"[ByteBite] Config = {CONFIG_PATH}")
        print(f"[ByteBite] Logs = {self.logs_dir}")
        print(f"[ByteBite] Excel = {self.results_workbook}")
        print(f"[ByteBite] GPIO backend active = {self._gpio_backend}")
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
        if NativeFactory is not None:
            try:
                Device.pin_factory = NativeFactory()
                print("[ByteBite] GPIO backend = native")
                return
            except Exception:
                pass
        if PiGPIOFactory is not None:
            try:
                Device.pin_factory = PiGPIOFactory()
                print("[ByteBite] GPIO backend = pigpio")
            except Exception:
                pass

    def _init_rpi_gpio(self, start_pin: int, cancel_pin: int, view_pin: int) -> bool:
        if GPIO is None:
            return False
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in (start_pin, cancel_pin, view_pin):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            def _wrap(cb):
                return lambda _channel: cb()

            GPIO.add_event_detect(start_pin, GPIO.FALLING, callback=_wrap(self.start_pressed), bouncetime=200)
            GPIO.add_event_detect(cancel_pin, GPIO.FALLING, callback=_wrap(self.cancel_pressed), bouncetime=200)
            GPIO.add_event_detect(view_pin, GPIO.FALLING, callback=_wrap(self.view_pressed), bouncetime=200)

            self._rpi_pins = (start_pin, cancel_pin, view_pin)
            self.btn_start = _NullButton(start_pin)
            self.btn_cancel = _NullButton(cancel_pin)
            self.btn_view = _NullButton(view_pin)
            return True
        except Exception as exc:
            print(f"[ByteBite] WARNING: RPi.GPIO init failed: {exc}")
            try:
                GPIO.cleanup()
            except Exception:
                pass
            return False

    def _use_terminal_buttons(self, start_pin: int, cancel_pin: int, view_pin: int) -> None:
        self._gpio_available = False
        self._gpio_backend = "terminal"
        print("[ByteBite] Entering terminal control mode (start/cancel/view/quit).")
        self.btn_start = _NullButton(start_pin)
        self.btn_cancel = _NullButton(cancel_pin)
        self.btn_view = _NullButton(view_pin)

    def _init_gpiod(self, start_pin: int, cancel_pin: int, view_pin: int) -> bool:
        if GPIOD is None:
            return False
        try:
            settings = GPIOD.LineSettings(
                direction=GPIOD.line.Direction.INPUT,
                bias=GPIOD.line.Bias.PULL_UP,
            )
            pins = (start_pin, cancel_pin, view_pin)
            self._gpiod_request = GPIOD.request_lines(
                "/dev/gpiochip0",
                consumer="bytebite-offensive",
                config={pins: settings},
            )

            self._gpiod_last = {pin: int(self._gpiod_request.get_value(pin).value) for pin in pins}
            self._gpiod_idle = dict(self._gpiod_last)
            self.btn_start = _NullButton(start_pin)
            self.btn_cancel = _NullButton(cancel_pin)
            self.btn_view = _NullButton(view_pin)
            self._gpiod_stop.clear()
            self._gpiod_thread = threading.Thread(target=self._gpiod_poll_loop, daemon=True)
            self._gpiod_thread.start()
            return True
        except Exception as exc:
            print(f"[ByteBite] WARNING: gpiod init failed: {exc}")
            if self._gpiod_request is not None:
                try:
                    self._gpiod_request.release()
                except Exception:
                    pass
                self._gpiod_request = None
            return False

    def _gpiod_poll_loop(self) -> None:
        if self._gpiod_request is None or GPIOD is None:
            return
        handlers = {
            self.btn_start.pin.number: self.start_pressed,
            self.btn_cancel.pin.number: self.cancel_pressed,
            self.btn_view.pin.number: self.view_pressed,
        }
        while not self._gpiod_stop.is_set():
            try:
                for pin, handler in handlers.items():
                    cur = int(self._gpiod_request.get_value(pin).value)
                    prev = self._gpiod_last.get(pin, cur)
                    idle = self._gpiod_idle.get(pin, cur)
                    # Trigger press on transition away from the observed idle level.
                    if prev == idle and cur != idle:
                        handler()
                    self._gpiod_last[pin] = cur
            except Exception:
                break
            time.sleep(0.03)

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
        run_json_files = [p for p in self.logs_dir.rglob("run.json") if p.is_file()]
        if not run_json_files:
            print("[ByteBite] No runs logged yet.")
            return
        latest_run_json = max(run_json_files, key=lambda p: p.stat().st_mtime)
        print(f"[ByteBite] Latest run: {latest_run_json.parent.relative_to(self.logs_dir)}")
        try:
            data = json.loads(latest_run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[ByteBite] Latest run.json is invalid JSON: {exc}")
            return

        steps = []
        for step in data.get("steps", []):
            if not isinstance(step, dict):
                continue
            steps.append((step.get("name"), bool(step.get("ok")), step.get("duration_ms")))
        print(
            json.dumps(
                {
                    "status": data.get("status"),
                    "elapsed_s": data.get("elapsed_s"),
                    "profile": data.get("meta", {}).get("profile"),
                    "steps": steps,
                },
                indent=2,
            )
        )

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
            if self._gpio_backend == "rpi_gpio" and GPIO is not None and self._rpi_pins:
                for pin in self._rpi_pins:
                    try:
                        GPIO.remove_event_detect(pin)
                    except Exception:
                        pass
                try:
                    GPIO.cleanup()
                except Exception:
                    pass
            if self._gpio_backend == "gpiod" and self._gpiod_request is not None:
                self._gpiod_stop.set()
                try:
                    self._gpiod_request.release()
                except Exception:
                    pass
                self._gpiod_request = None
            for btn in (self.btn_start, self.btn_cancel, self.btn_view):
                try:
                    btn.close()
                except Exception:
                    pass

if __name__ == "__main__":
    app = OffensiveApp()
    app.loop()
