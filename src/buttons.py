"""Hardware button setup for ByteBite.

Thread-safe GPIO handling: GPIO callbacks run in their own thread, so we schedule
the GUI actions onto Tk's main thread via `root.after(0, ...)`.
Safe to import on non-Pi systems; it becomes a no-op if RPi.GPIO is unavailable.
"""

from __future__ import annotations

import atexit
from typing import Callable, Optional

try:
    from gpiozero import Button, Device  # type: ignore
    try:
        from gpiozero.pins.lgpio import LGPIOFactory  # type: ignore
    except Exception:  # pragma: no cover - lgpio may not be present
        LGPIOFactory = None
except Exception:  # pragma: no cover - may not be installed
    Button = None
    Device = None
    LGPIOFactory = None

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # pragma: no cover - off-Pi fallback
    GPIO = None

# Default BCM pin mapping; change if you wire differently.
PINS = {"left": 5, "right": 6, "enter": 13}
_active = False
_buttons = []


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
    if root is None:
        return

    # Prefer gpiozero (works with lgpio on Pi 5)
    if Button is not None:
        _init_gpiozero(root, on_left, on_right, on_enter, bouncetime_ms)
        return

    if GPIO is None:
        return

    if _active:
        cleanup_buttons()

    try:
        GPIO.setmode(GPIO.BCM)
        for pin in PINS.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except Exception:
        # If legacy RPi.GPIO fails (common on Pi 5), fall back to gpiozero if present.
        cleanup_buttons()
        if Button is not None:
            _init_gpiozero(root, on_left, on_right, on_enter, bouncetime_ms)
        return

    def _wrap(cb: Callable[[], None]):
        return lambda _ch: root.after(0, cb)

    if on_left:
        GPIO.add_event_detect(PINS["left"], GPIO.FALLING, callback=_wrap(on_left), bouncetime=bouncetime_ms)
    if on_right:
        GPIO.add_event_detect(PINS["right"], GPIO.FALLING, callback=_wrap(on_right), bouncetime=bouncetime_ms)
    if on_enter:
        GPIO.add_event_detect(PINS["enter"], GPIO.FALLING, callback=_wrap(on_enter), bouncetime=bouncetime_ms)

    atexit.register(cleanup_buttons)
    _active = True


def cleanup_buttons() -> None:
    """Remove event detects and cleanup GPIO."""
    global _active
    global _buttons
    # gpiozero cleanup
    if _buttons:
        for b in _buttons:
            try:
                b.close()
            except Exception:
                pass
        _buttons = []
    if GPIO is None:
        return
    for pin in PINS.values():
        try:
            GPIO.remove_event_detect(pin)
        except Exception:
            pass
    try:
        GPIO.cleanup()
    except Exception:
        pass
    _active = False


def _init_gpiozero(root, on_left, on_right, on_enter, bouncetime_ms: int) -> None:
    """Fallback using gpiozero (works with Pi 5 / lgpio)."""
    global _active, _buttons
    try:
        if LGPIOFactory is not None and Device is not None:
            Device.pin_factory = LGPIOFactory()
        _buttons = []
        if on_left:
            btn = Button(PINS["left"], pull_up=True, bounce_time=bouncetime_ms / 1000.0)
            btn.when_pressed = lambda: root.after(0, on_left)
            _buttons.append(btn)
        if on_right:
            btn = Button(PINS["right"], pull_up=True, bounce_time=bouncetime_ms / 1000.0)
            btn.when_pressed = lambda: root.after(0, on_right)
            _buttons.append(btn)
        if on_enter:
            btn = Button(PINS["enter"], pull_up=True, bounce_time=bouncetime_ms / 1000.0)
            btn.when_pressed = lambda: root.after(0, on_enter)
            _buttons.append(btn)
        atexit.register(cleanup_buttons)
        _active = True
    except Exception:
        _buttons = []
        _active = False
        # Swallow to avoid crashing the UI
