"""Entry point for the ByteBite UI running on the Raspberry Pi."""
import os
import sys
from buttons import init_buttons

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
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
