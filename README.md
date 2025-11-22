# ProductionProjectUI
ByteBite UI intended to run on a Raspberry Pi.

## Setup on Raspberry Pi (via SSH)
1. SSH in with display forwarding so Tkinter can draw windows:
   - macOS/Linux: `ssh -Y pi@<pi-host-or-ip>`
   - Windows (PuTTY): enable X11 forwarding; run an X server locally (VcXsrv/Xming).
2. Ensure Tkinter is installed: `sudo apt-get update && sudo apt-get install -y python3-tk`
3. Clone or copy this repo onto the Pi.

## Run the GUI
```
python3 src/app.py
```
If you see "No display detected", reconnect SSH with `-Y` (or `-X`) or run on the Pi's attached display.

## Project layout
- `src/app.py` – entry point that launches the Tkinter window.
- `src/ui/` – UI components.
- `src/logic/` – backend helpers (system info, etc.).
- `src/assets/` – static assets; currently empty.
