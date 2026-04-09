#!/bin/bash
# Gas Price Tracker — double-click this file in Finder to launch.
# A browser tab will open automatically at http://localhost:5999
# Press Ctrl+C in this window (or close it) to stop the server.

cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found."
    echo "Install it from https://python.org/downloads and try again."
    read -rp "Press Enter to close..."
    exit 1
fi

# Install dependencies if needed
python3 -c "import flask, selenium" 2>/dev/null || {
    echo "Installing dependencies..."
    python3 -m pip install -r requirements.txt
}

echo ""
echo "  ⛽  Gas Price Tracker"
echo "  Starting server — browser will open automatically."
echo "  Close this window (or press Ctrl+C) to stop."
echo ""

python3 app.py
