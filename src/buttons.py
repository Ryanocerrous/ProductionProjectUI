"""Hardware button setup for ByteBite.

Thread-safe GPIO handling: GPIO callbacks run in their own thread, so we schedule
the GUI actions onto Tk's main thread via `root.after(0, ...)`.
Safe to import on non-Pi systems; it becomes a no-op if RPi.GPIO is unavailable.
"""

from __future__ import annotations

import atexit
import importlib
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path

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
except Exception:  # pragma: no cover - optional dependency
    Button = None
    Device = None

if Button is not None:
    try:
        LGPIOFactory = getattr(importlib.import_module("gpiozero.pins.lgpio"), "LGPIOFactory", None)
    except Exception:  # pragma: no cover - optional dependency
        LGPIOFactory = None
    try:
        NativeFactory = getattr(importlib.import_module("gpiozero.pins.native"), "NativeFactory", None)
    except Exception:  # pragma: no cover - optional dependency
        NativeFactory = None
    try:
        PiGPIOFactory = getattr(importlib.import_module("gpiozero.pins.pigpio"), "PiGPIOFactory", None)
    except Exception:  # pragma: no cover - optional dependency
        PiGPIOFactory = None

try:
    GPIO = importlib.import_module("RPi.GPIO")
except Exception:  # pragma: no cover - optional dependency
    GPIO = None

try:
    GPIOD = importlib.import_module("gpiod")
except Exception:  # pragma: no cover - optional dependency
    GPIOD = None

# Default BCM pin mapping; change if you wire differently.
DEFAULT_PINS = {"left": 5, "right": 6, "enter": 13}
_active = False
_buttons = []
_pins = dict(DEFAULT_PINS)
_backend = "none"
_cleanup_registered = False
_gpiod_request: Any | None = None
_gpiod_stop = threading.Event()
_gpiod_thread: threading.Thread | None = None
_gpiod_last_event_ts: dict[int, float] = {}
_gpiod_root: Any | None = None
_gpiod_line_to_cb: dict[int, Callable[[], None]] = {}
_gpiod_idle: dict[int, int] = {}
_gpiod_prev: dict[int, int] = {}
_gpiod_after_id: str | None = None
_gpiod_init_error = ""

CONFIG_PATH = resolve_config_path(PROJECT_ROOT)
DEFAULT_CONFIG = build_default_config()


def _load_nav_pins() -> dict[str, int]:
    pins = dict(DEFAULT_PINS)
    try:
        cfg = load_or_create_config(CONFIG_PATH, DEFAULT_CONFIG)
    except Exception:
        return pins
    ui_gpio = cfg.get("ui_gpio", {})
    for key in ("left", "right", "enter"):
        try:
            pins[key] = int(ui_gpio.get(key, pins[key]))
        except Exception:
            pass
    return pins


def init_buttons(
    root,
    on_left: Optional[Callable[[], None]] = None,
    on_right: Optional[Callable[[], None]] = None,
    on_enter: Optional[Callable[[], None]] = None,
    bouncetime_ms: int = 200,
) -> None:
    """Initialize GPIO and attach callbacks (no-op if GPIO or root missing)."""
    global _active
    global _buttons
    global _pins
    global _backend
    global _cleanup_registered
    global _gpiod_request
    global _gpiod_thread
    global _gpiod_last_event_ts
    global _gpiod_root
    global _gpiod_line_to_cb
    global _gpiod_idle
    global _gpiod_prev
    global _gpiod_init_error
    if root is None:
        return
    _pins = _load_nav_pins()

    if _init_gpiod(root, on_left, on_right, on_enter, bouncetime_ms):
        _backend = "gpiod"
        if not _cleanup_registered:
            atexit.register(cleanup_buttons)
            _cleanup_registered = True
        print(f"[ByteBite] Nav GPIO backend = gpiod, pins = {_pins}")
        return
    if _gpiod_init_error:
        print(f"[ByteBite] Nav GPIO gpiod init failed: {_gpiod_init_error}")

    # Fall back to RPi.GPIO if libgpiod is unavailable.
    if GPIO is not None:
        if _active:
            cleanup_buttons()
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in _pins.values():
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            def _wrap(cb: Callable[[], None]):
                return lambda _ch: root.after(0, cb)

            if on_left:
                GPIO.add_event_detect(_pins["left"], GPIO.FALLING, callback=_wrap(on_left), bouncetime=bouncetime_ms)
            if on_right:
                GPIO.add_event_detect(_pins["right"], GPIO.FALLING, callback=_wrap(on_right), bouncetime=bouncetime_ms)
            if on_enter:
                GPIO.add_event_detect(_pins["enter"], GPIO.FALLING, callback=_wrap(on_enter), bouncetime=bouncetime_ms)

            if not _cleanup_registered:
                atexit.register(cleanup_buttons)
                _cleanup_registered = True
            _backend = "rpi_gpio"
            _active = True
            print(f"[ByteBite] Nav GPIO backend = RPi.GPIO, pins = {_pins}")
            return
        except Exception as exc:
            cleanup_buttons()
            print(f"[ByteBite] Nav GPIO RPi.GPIO init failed: {exc}")

    if Button is not None and _init_gpiozero(root, on_left, on_right, on_enter, bouncetime_ms):
        _backend = "gpiozero"
        if not _cleanup_registered:
            atexit.register(cleanup_buttons)
            _cleanup_registered = True
        print(f"[ByteBite] Nav GPIO backend = gpiozero, pins = {_pins}")
        return

    _backend = "none"
    print("[ByteBite] Nav GPIO disabled: no working backend (RPi.GPIO/gpiozero).")


def cleanup_buttons() -> None:
    """Remove event detects and cleanup GPIO."""
    global _active
    global _buttons
    global _backend
    global _gpiod_request
    global _gpiod_root
    global _gpiod_line_to_cb
    global _gpiod_thread
    global _gpiod_last_event_ts
    global _gpiod_idle
    global _gpiod_prev
    global _gpiod_after_id
    # gpiozero cleanup
    if _buttons:
        for b in _buttons:
            try:
                b.close()
            except Exception:
                pass
        _buttons = []
    if GPIO is not None:
        for pin in _pins.values():
            try:
                GPIO.remove_event_detect(pin)
            except Exception:
                pass
        try:
            GPIO.cleanup()
        except Exception:
            pass
    if _gpiod_request is not None:
        if _gpiod_after_id and _gpiod_root is not None:
            try:
                _gpiod_root.after_cancel(_gpiod_after_id)
            except Exception:
                pass
            _gpiod_after_id = None
        if _gpiod_root is not None and hasattr(_gpiod_root, "deletefilehandler"):
            try:
                _gpiod_root.deletefilehandler(_gpiod_request.fd)
            except Exception:
                pass
        _gpiod_stop.set()
        try:
            _gpiod_request.release()
        except Exception:
            pass
        _gpiod_request = None
    _gpiod_root = None
    _gpiod_line_to_cb = {}
    _gpiod_thread = None
    _gpiod_last_event_ts = {}
    _gpiod_idle = {}
    _gpiod_prev = {}
    _gpiod_after_id = None
    _active = False
    _backend = "none"


def _init_gpiozero(root, on_left, on_right, on_enter, bouncetime_ms: int) -> bool:
    """Fallback using gpiozero (works with Pi 5 / lgpio)."""
    global _active, _buttons
    try:
        if LGPIOFactory is not None and Device is not None:
            Device.pin_factory = LGPIOFactory()
        elif NativeFactory is not None and Device is not None:
            Device.pin_factory = NativeFactory()
        elif PiGPIOFactory is not None and Device is not None:
            Device.pin_factory = PiGPIOFactory()
        _buttons = []
        if on_left:
            btn = Button(_pins["left"], pull_up=True, bounce_time=bouncetime_ms / 1000.0)
            btn.when_pressed = lambda: root.after(0, on_left)
            _buttons.append(btn)
        if on_right:
            btn = Button(_pins["right"], pull_up=True, bounce_time=bouncetime_ms / 1000.0)
            btn.when_pressed = lambda: root.after(0, on_right)
            _buttons.append(btn)
        if on_enter:
            btn = Button(_pins["enter"], pull_up=True, bounce_time=bouncetime_ms / 1000.0)
            btn.when_pressed = lambda: root.after(0, on_enter)
            _buttons.append(btn)
        _active = True
        return True
    except Exception:
        _buttons = []
        _active = False
        return False


def _init_gpiod(root, on_left, on_right, on_enter, bouncetime_ms: int = 200) -> bool:
    global _active, _gpiod_request, _gpiod_thread, _gpiod_last_event_ts
    global _gpiod_root, _gpiod_line_to_cb, _gpiod_idle, _gpiod_prev, _gpiod_after_id
    global _gpiod_init_error
    if GPIOD is None:
        return False
    try:
        _gpiod_init_error = ""
        line_to_cb: dict[int, Callable[[], None]] = {}
        if on_left:
            line_to_cb[_pins["left"]] = on_left
        if on_right:
            line_to_cb[_pins["right"]] = on_right
        if on_enter:
            line_to_cb[_pins["enter"]] = on_enter
        if not line_to_cb:
            return False

        pins = tuple(sorted(line_to_cb.keys()))
        _gpiod_request = _request_gpiod_lines(pins, _build_gpiod_settings())
        _gpiod_last_event_ts = {pin: 0.0 for pin in pins}
        _gpiod_idle = {pin: int(_gpiod_request.get_value(pin).value) for pin in pins}
        _gpiod_prev = dict(_gpiod_idle)
        _gpiod_stop.clear()
        debounce_s = max(float(bouncetime_ms) / 1000.0, 0.05)
        _gpiod_root = root
        _gpiod_line_to_cb = dict(line_to_cb)

        def _poll_edges() -> None:
            global _gpiod_after_id
            if _gpiod_request is None or _gpiod_stop.is_set():
                _gpiod_after_id = None
                return
            try:
                now = time.monotonic()
                values_now = {
                    pin: int(_gpiod_request.get_value(pin).value)
                    for pin in sorted(_gpiod_line_to_cb.keys())
                }
                for pin, cur in values_now.items():
                    prev = _gpiod_prev.get(pin, cur)
                    idle = _gpiod_idle.get(pin, cur)
                    if cur != prev:
                        cb = _gpiod_line_to_cb.get(pin)
                        if cb is not None and prev == idle and cur != idle:
                            last = _gpiod_last_event_ts.get(pin, 0.0)
                            if now - last >= debounce_s:
                                _gpiod_last_event_ts[pin] = now
                                root.after(0, cb)
                        _gpiod_prev[pin] = cur
            except Exception:
                _gpiod_after_id = None
                return
            _gpiod_after_id = root.after(15, _poll_edges)

        _gpiod_after_id = root.after(15, _poll_edges)
        _active = True
        return True
    except Exception as exc:
        _gpiod_init_error = f"{type(exc).__name__}: {exc}"
        if _gpiod_request is not None:
            try:
                _gpiod_request.release()
            except Exception:
                pass
            _gpiod_request = None
        _active = False
        return False


def _build_gpiod_settings() -> list[Any]:
    if GPIOD is None:
        return []
    candidates: list[Any] = []
    bias_candidates: list[Any | None] = []
    try:
        bias_candidates.append(GPIOD.line.Bias.PULL_UP)
    except Exception:
        pass
    try:
        bias_candidates.append(GPIOD.line.Bias.DISABLED)
    except Exception:
        pass
    bias_candidates.append(None)

    for bias in bias_candidates:
        kwargs: dict[str, Any] = {"direction": GPIOD.line.Direction.INPUT}
        if bias is not None:
            kwargs["bias"] = bias
        try:
            candidates.append(GPIOD.LineSettings(**kwargs))
        except Exception:
            continue

    if not candidates:
        candidates.append(GPIOD.LineSettings(direction=GPIOD.line.Direction.INPUT))
    return candidates


def _request_gpiod_lines(pins: tuple[int, ...], settings_candidates: list[Any]) -> Any:
    last_error: Exception | None = None
    for settings in settings_candidates:
        try:
            return GPIOD.request_lines(
                "/dev/gpiochip0",
                consumer="bytebite-nav",
                config={pins: settings},
            )
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("No gpiod settings candidates available")
