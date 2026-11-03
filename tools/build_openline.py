#!/usr/bin/env python3
"""
build_openline.py — Inject the embedded file blobs into openline.py.

openline.py ships with @@PLACEHOLDER@@ tokens in its EMBEDDED_B64 dict. This
script reads harden.sh and binaries/<version>/* from the repo, base64-encodes
them, and writes them into those tokens in place, producing the single
self-contained openline.py that can be piped straight into python3.

Run this whenever harden.sh or any pre-patched binary changes:

    python3 tools/build_openline.py
"""

import base64
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "RA_M1_v7.00.02g"

# token in openline.py  ->  path of the source file in the repo
SOURCES = {
    "@@HARDEN_SH@@":       os.path.join(REPO, "harden.sh"),
    "@@DTOKEN_LUA@@":      os.path.join(REPO, "binaries", VERSION, "dtoken.lua"),
    "@@DEVMODE@@":         os.path.join(REPO, "binaries", VERSION, "devmode"),
    "@@LUCI_BASE_JSON@@":  os.path.join(REPO, "binaries", VERSION, "luci-base.json"),
    "@@FIREWALL_USER@@":   os.path.join(REPO, "binaries", VERSION, "firewall.user"),
}

TARGET = os.path.join(REPO, "openline.py")


def main():
    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    for token, path in SOURCES.items():
        if not os.path.isfile(path):
            sys.exit(f"missing source: {path}")
        with open(path, "rb") as f:
            blob = base64.b64encode(f.read()).decode("ascii")
        if token not in src:
            sys.exit(f"token {token} not found in openline.py — already built? "
                     f"Re-checkout openline.py and run again.")
        src = src.replace(token, blob)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"Injected {len(SOURCES)} embedded files into {TARGET}")
    # Sanity-check: the file must still import.
    ns = {}
    try:
        exec(compile(src, TARGET, "exec"), {"__name__": "__built__"})
    except SyntaxError as e:
        sys.exit(f"built openline.py has a syntax error: {e}")
    print("Syntax OK.")


if __name__ == "__main__":
    main()
