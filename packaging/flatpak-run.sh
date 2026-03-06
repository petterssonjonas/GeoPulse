#!/bin/sh
# Flatpak launcher: set PYTHONPATH and run main.py
export PYTHONPATH="/app/share/geopulse"
exec python3 /app/share/geopulse/main.py "$@"
