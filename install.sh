#!/bin/sh
# install.sh - Android / Mac / Linux bootstrap for openline-101
#
# Run:
#     curl -fsSL https://raw.githubusercontent.com/jobrac/openline-101/main/install.sh | sh
#
# It finds a working Python (tries python3, then python; requires 3.6+),
# downloads openline.py, and runs it. You end up at one interactive prompt for
# your admin password (printed on the sticker under the router). Make sure this
# device is on the router's Wi-Fi with mobile data OFF.
#
# This is the counterpart to install.ps1 (Windows). It exists so the one-liner
# works whether your system calls Python "python3" or "python".

REPO="https://raw.githubusercontent.com/jobrac/openline-101/main"

echo "=== openline-101 ==="

# 1. Find a Python 3.6+ interpreter (python3 preferred, then python).
PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
        if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)' 2>/dev/null; then
            PY="$c"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "Python 3.6+ was not found. Install it, then run this again:" >&2
    echo "  - Android (Termux): pkg install -y python" >&2
    echo "  - Debian / Ubuntu : sudo apt install -y python3" >&2
    echo "  - Fedora          : sudo dnf install -y python3" >&2
    echo "  - Arch            : sudo pacman -S python" >&2
    echo "  - macOS           : brew install python  (or get it from python.org)" >&2
    exit 1
fi
echo "Using $PY ($("$PY" --version 2>&1))."

# 2. Download openline.py to a temp file.
TMP="$(mktemp 2>/dev/null)" || TMP="/tmp/openline.$$.py"
cleanup() { rm -f "$TMP"; }
trap cleanup EXIT INT TERM

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO/openline.py" -o "$TMP" || { echo "Download failed." >&2; exit 1; }
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP" "$REPO/openline.py" || { echo "Download failed." >&2; exit 1; }
else
    echo "Need curl or wget to download. Install one and retry." >&2
    exit 1
fi

# 3. Run it. Give it the terminal as stdin (so prompts work even though this
#    script itself arrived over the pipe). Pass through any arguments.
if [ -r /dev/tty ]; then
    "$PY" "$TMP" "$@" </dev/tty
else
    "$PY" "$TMP" "$@"
fi
