"""Entry point for the ByteBite UI running on the Raspberry Pi."""
import os
import sys

# Prefer local virtualenv packages (ttkthemes lives here)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_VENV_SITE = os.path.join(
    _ROOT, ".venv", f"lib/python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"
)
if os.path.isdir(_VENV_SITE) and _VENV_SITE not in sys.path:
    sys.path.insert(0, _VENV_SITE)

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - makes it obvious on headless environments
    print("Tkinter is not installed. On Raspberry Pi run: sudo apt-get install python3-tk", file=sys.stderr)
    sys.exit(1)

from ui.main_window import MainWindow
from buttons import init_buttons, cleanup_buttons


def _has_display() -> bool:
    """Determine if a display server is available (useful when SSHing in)."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def main() -> None:
    if not _has_display():
        print(
            "No display detected. If you SSH into the Pi, reconnect with X forwarding:\n"
            "  ssh -Y pi@<pi-hostname-or-ip>\n"
            "Then run: python3 src/app.py",
            file=sys.stderr,
        )
        return

    root = tk.Tk()
    root.title("ByteBite UI")
    root.geometry("800x480")
    root.minsize(800, 480)
    root.config(cursor="none")  # hide the flashing cursor on the display
    window = MainWindow(root)

    # Wire physical buttons safely (no-op off Pi)
    init_buttons(
        root,
        on_left=window._handle_left,
        on_right=window._handle_right,
        on_enter=window._activate_selection,
    )

    def _on_exit() -> None:
        cleanup_buttons()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_exit)
    root.mainloop()


if __name__ == "__main__":
    main()
