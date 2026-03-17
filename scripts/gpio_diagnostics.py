from __future__ import annotations

import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path


def main() -> int:
    cfg_path = resolve_config_path(PROJECT_ROOT)
    cfg = load_or_create_config(cfg_path, build_default_config())
    off = cfg.get("gpio", {})
    ui = cfg.get("ui_gpio", {})

    pins = {
        "start": int(off.get("start", 22)),
        "cancel": int(off.get("cancel", 27)),
        "view_logs": int(off.get("view_logs", 17)),
        "left": int(ui.get("left", 5)),
        "right": int(ui.get("right", 6)),
        "enter": int(ui.get("enter", 13)),
    }

    print(f"[ByteBite] Config: {cfg_path}")
    print(f"[ByteBite] Testing pins (BCM): {pins}")
    print("[ByteBite] Press buttons now. Ctrl+C to stop.")

    try:
        import gpiod

        settings = gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT,
            bias=gpiod.line.Bias.PULL_UP,
        )
        bcm_pins = tuple(sorted(set(pins.values())))
        req = gpiod.request_lines(
            "/dev/gpiochip0",
            consumer="bytebite-gpio-diagnostics",
            config={bcm_pins: settings},
        )

        values_prev: dict[int, int] = {}
        idle_values: dict[int, int] | None = None
        pressed_prev: set[str] = set()
        try:
            while True:
                values_now = {
                    pin: int(req.get_value(pin).value) for pin in sorted(set(pins.values()))
                }
                if idle_values is None:
                    idle_values = dict(values_now)
                    print(f"[ByteBite] Idle baseline: {idle_values}")
                pressed_now = {
                    name
                    for name, pin in pins.items()
                    if idle_values is not None and values_now[pin] != idle_values[pin]
                }
                if values_now != values_prev:
                    print(f"[ByteBite] Raw states: {values_now} (1=high, 0=low)")
                    values_prev = values_now
                if pressed_now != pressed_prev:
                    if pressed_now:
                        print(f"[ByteBite] Pressed: {', '.join(sorted(pressed_now))}")
                    else:
                        print("[ByteBite] Released all")
                    pressed_prev = pressed_now
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            req.release()
            print("[ByteBite] gpiod cleanup complete.")
        return 0
    except Exception as gpiod_exc:
        print(f"[ByteBite] gpiod diagnostics unavailable: {gpiod_exc}")
        # On Pi 5/Kali we rely on libgpiod. Falling back to RPi.GPIO typically
        # fails and obscures the real cause (usually line ownership).
        return 1

    try:
        import RPi.GPIO as GPIO
    except Exception as rpi_exc:
        print(f"[ByteBite] RPi.GPIO import failed: {rpi_exc}")
        return 1

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in pins.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    pressed_prev: set[str] = set()
    try:
        while True:
            pressed_now = {name for name, pin in pins.items() if GPIO.input(pin) == 0}
            if pressed_now != pressed_prev:
                if pressed_now:
                    print(f"[ByteBite] Pressed: {', '.join(sorted(pressed_now))}")
                else:
                    print("[ByteBite] Released all")
                pressed_prev = pressed_now
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        print("[ByteBite] RPi.GPIO cleanup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
