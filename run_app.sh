#!/usr/bin/env bash
set -e
cd /home/kali/ProductionProjectUI
# ensure venv exists
if [ ! -x .venv/bin/python3 ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet ttkbootstrap ttkthemes Pillow
else
  # Make sure required deps are present even if the venv already existed
  .venv/bin/pip install --quiet --upgrade ttkbootstrap ttkthemes Pillow
fi

# Start X on vt1 and launch the app
exec /usr/bin/startx /home/kali/ProductionProjectUI/.venv/bin/python3 /home/kali/ProductionProjectUI/src/app.py -- :0 -nolisten tcp vt1 -keeptty
