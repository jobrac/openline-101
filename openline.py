#!/usr/bin/env python3
"""
openline.py - One-shot, self-contained openline + harden for the
rain101 / the101 router (Globe AT HOME 5G WIFI, firmware RA_M1_v7.00.02g).

This single file carries everything it needs (the hardening script and the
pre-patched binaries are embedded below). It can therefore be run straight
from the network with no git clone and no extra files:

    Android / Mac / Linux:
        curl -fsSL https://raw.githubusercontent.com/jobrac/openline-101/main/install.sh | sh
        # (install.sh finds python3/python for you; or pipe this file straight
        #  into python3 if you already have it:  ... /openline.py | python3 -)

    Windows (PowerShell):
        irm https://raw.githubusercontent.com/jobrac/openline-101/main/install.ps1 | iex

Run with no arguments and it will ask for your admin password interactively
(the prompt reads from the terminal, so the pipe above still works).

What it does:
  1. Connects to the router's ubus (JSON-RPC over HTTP) as admin
  2. Sets the root password and logs in as root
  3. Removes the PLMN carrier lock
  4. Pushes the pre-patched files and runs the hardening routine
  5. Offers to reboot

Primary path uses ONLY the Python standard library (urllib + json) - it drives
the router entirely over HTTP via ubus `file.write` / `file.exec`, so no SSH
client, ssh-keygen, scp or pexpect are needed. If the router's ACL blocks
`file.exec`, it automatically falls back to the classic SSH path (which does
need an `ssh` client, and optionally `pexpect`).

Requirements (primary path): Python 3.6+ only.
"""

import sys
import os
import json
import base64
import time
import socket
import getpass
import argparse
import urllib.request
import urllib.error


# ── Embedded files (base64) ──────────────────────────────────────────────
# These are injected by tools/build_openline.py from harden.sh and
# binaries/<version>/. Keeping them here is what makes the script a single
# self-contained file that can be piped straight into python3.

DEFAULT_VERSION = "RA_M1_v7.00.02g"

EMBEDDED_B64 = {
    "harden.sh": "IyEvYmluL3NoCiMgaGFyZGVuLnNoIOKAlCBMb2NrIGRvd24gdGhlMTAxIHJvdXRlciBhZnRlciBnYWluaW5nIHJvb3QgU1NICiMgUnVuIHRoaXMgT04gdGhlIHJvdXRlciAodmlhIFNTSCkgYWZ0ZXIgb3BlbmxpbmUucHkgaGFzIGVuYWJsZWQgcm9vdCBhY2Nlc3MuCiMKIyBVc2FnZToKIyAgIHNzaCByb290QDE5Mi4xNjguMC4xICJzaCAtcyIgPCBoYXJkZW4uc2gKIwojIE9yIG9wZW5saW5lLnB5IGNvcGllcyBwcmUtcGF0Y2hlZCBmaWxlcyB0byAvdG1wIGZpcnN0LCB0aGVuIHBpcGVzIHRoaXMuCgpzZXQgLWUKCmVjaG8gIj09PSB0aGUxMDEgUm91dGVyIEhhcmRlbmluZyA9PT0iCmVjaG8gIiIKCm9rKCkgICB7IGVjaG8gIiAgT0s6ICQqIjsgfQpmYWlsKCkgeyBlY2hvICIgIEZBSUw6ICQqIjsgfQpza2lwKCkgeyBlY2hvICIgIFNLSVA6ICQqIjsgfQoKQklOPS90bXAKCiMg4pSA4pSAIDEuIEtpbGwgVFItMDY5IOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICJbMS8xMF0gS2lsbGluZyBUUi0wNjkuLi4iCnVjaSBzZXQgZWFzeWN3bXAuQGxvY2FsWzBdLmVuYWJsZT0wIDI+L2Rldi9udWxsIHx8IHRydWUKdWNpIGNvbW1pdCBlYXN5Y3dtcCAyPi9kZXYvbnVsbCB8fCB0cnVlCi9ldGMvaW5pdC5kL2Vhc3ljd21wZCBzdG9wIDI+L2Rldi9udWxsIHx8IHRydWUKL2V0Yy9pbml0LmQvZWFzeWN3bXBkIGRpc2FibGUgMj4vZGV2L251bGwgfHwgdHJ1ZQpraWxsYWxsIC05IGVhc3ljd21wZCBlYXN5Y3dtcCAyPi9kZXYvbnVsbCB8fCB0cnVlCnJtIC1mIC9ldGMvcmMuZC9TOTBlYXN5Y3dtcGQgL2V0Yy9yYy5kL1M5OXRyMDY5X25vdGlmeSAyPi9kZXYvbnVsbAppcHRhYmxlcyAtSSBPVVRQVVQgLWQgZGV2aWNlLnJhaW4ubmV0d29yayAtaiBEUk9QIDI+L2Rldi9udWxsIHx8IHRydWUKaXB0YWJsZXMgLUkgT1VUUFVUIC1wIHRjcCAtLWRwb3J0IDc1NDggLWogRFJPUCAyPi9kZXYvbnVsbCB8fCB0cnVlCm9rICJUUi0wNjkgZGlzYWJsZWQiCgojIOKUgOKUgCAyLiBFbmFibGUgZGVidWdfbW9kZT05OSArIHN1cGVyX2FkbWluPTEg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmVjaG8gIlsyLzEwXSBFbmFibGluZyBkZWJ1Z19tb2RlPTk5ICsgc3VwZXJfYWRtaW4uLi4iCm1rZGlyIC1wIC9kYXRhL2p5dGxfZmFjdG9yeQpwcmludGYgJzk5JyA+IC9kYXRhL2p5dGxfZmFjdG9yeS9kZWJ1Z19tb2RlClsgIiQoY2F0IC9kYXRhL2p5dGxfZmFjdG9yeS9kZWJ1Z19tb2RlKSIgPSAiOTkiIF0gJiYgb2sgImRlYnVnX21vZGU9OTkiIHx8IGZhaWwgImRlYnVnX21vZGUiCnNlZCAtaSAncy8ic3VwZXJfYWRtaW4iOiAiMCIvInN1cGVyX2FkbWluIjogIjEiLycgL2V0Yy9wcm9wZXJ0eS5qc29uIDI+L2Rldi9udWxsIHx8IHRydWUKZ3JlcCAtcSAnInN1cGVyX2FkbWluIjogIjEiJyAvZXRjL3Byb3BlcnR5Lmpzb24gJiYgb2sgInN1cGVyX2FkbWluPTEiIHx8IHRydWUKCiMg4pSA4pSAIDMuIEluc3RhbGwgcHJlLXBhdGNoZWQgZmlsZXMgKGlmIGF2YWlsYWJsZSkg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmVjaG8gIlszLzEwXSBJbnN0YWxsaW5nIHByZS1wYXRjaGVkIGZpbGVzLi4uIgoKIyBDbGVhbiBhbnkgbGVmdG92ZXIgcmVzdG9yZS1jcm9uIGpvYnMgZnJvbSBwcmV2aW91cyB0cm91Ymxlc2hvb3RpbmcKc2VkIC1pICcvZHRva2VuLmx1YS9kJyAvZXRjL2Nyb250YWJzL3Jvb3QgMj4vZGV2L251bGwgfHwgdHJ1ZQoKaWYgWyAtZiAiJEJJTi9kdG9rZW4ubHVhIiBdOyB0aGVuCiAgICBbICEgLWYgL3Vzci9saWIvbHVhL2x1Y2kvZHRva2VuLmx1YS5vcmlnIF0gJiYgY3AgL3Vzci9saWIvbHVhL2x1Y2kvZHRva2VuLmx1YSAvdXNyL2xpYi9sdWEvbHVjaS9kdG9rZW4ubHVhLm9yaWcKICAgIGNwICIkQklOL2R0b2tlbi5sdWEiIC91c3IvbGliL2x1YS9sdWNpL2R0b2tlbi5sdWEKICAgIG9rICJkdG9rZW4ubHVhIgplbHNlCiAgICBza2lwICJkdG9rZW4ubHVhIG5vdCBpbiAkQklOIOKAlCBydW4gb3BlbmxpbmUucHkgb3IgY29weSBtYW51YWxseSIKZmkKCmlmIFsgLWYgIiRCSU4vZGV2bW9kZSIgXTsgdGhlbgogICAgY3AgIiRCSU4vZGV2bW9kZSIgL2V0Yy9pbml0LmQvZGV2bW9kZQogICAgY2htb2QgK3ggL2V0Yy9pbml0LmQvZGV2bW9kZQogICAgL2V0Yy9pbml0LmQvZGV2bW9kZSBlbmFibGUgMj4vZGV2L251bGwgfHwgdHJ1ZQogICAgIyBWZXJpZnkgc3ltbGluayB3YXMgY3JlYXRlZDsgY3JlYXRlIG1hbnVhbGx5IGlmIGVuYWJsZSBmYWlsZWQKICAgIGlmIFsgLUwgL2V0Yy9yYy5kL1M5N2Rldm1vZGUgXTsgdGhlbgogICAgICAgIG9rICJkZXZtb2RlIGluaXQgKFM5N2Rldm1vZGUgZW5hYmxlZCkiCiAgICBlbHNlCiAgICAgICAgbG4gLXNmIC4uL2luaXQuZC9kZXZtb2RlIC9ldGMvcmMuZC9TOTdkZXZtb2RlIDI+L2Rldi9udWxsIHx8IHRydWUKICAgICAgICBpZiBbIC1MIC9ldGMvcmMuZC9TOTdkZXZtb2RlIF07IHRoZW4KICAgICAgICAgICAgb2sgImRldm1vZGUgaW5pdCAoc3ltbGluayBjcmVhdGVkIG1hbnVhbGx5KSIKICAgICAgICBlbHNlCiAgICAgICAgICAgIGZhaWwgImRldm1vZGUgaW5pdCBzeW1saW5rIOKAlCBkZXZlbG9wZXIgcGFnZXMgbWF5IG5vdCBzdXJ2aXZlIHJlYm9vdCIKICAgICAgICBmaQogICAgZmkKICAgIC9ldGMvaW5pdC5kL2Rldm1vZGUgYm9vdCAyPi9kZXYvbnVsbCB8fCB0cnVlCmVsc2UKICAgIHNraXAgImRldm1vZGUgbm90IGluICRCSU4iCmZpCgppZiBbIC1mICIkQklOL2x1Y2ktYmFzZS5qc29uIiBdOyB0aGVuCiAgICBbICEgLWYgL3Vzci9zaGFyZS9ycGNkL2FjbC5kL2x1Y2ktYmFzZS5qc29uLmJhayBdICYmIGNwIC91c3Ivc2hhcmUvcnBjZC9hY2wuZC9sdWNpLWJhc2UuanNvbiAvdXNyL3NoYXJlL3JwY2QvYWNsLmQvbHVjaS1iYXNlLmpzb24uYmFrIDI+L2Rldi9udWxsIHx8IHRydWUKICAgIGNwICIkQklOL2x1Y2ktYmFzZS5qc29uIiAvdXNyL3NoYXJlL3JwY2QvYWNsLmQvbHVjaS1iYXNlLmpzb24KICAgIG9rICJycGNkIEFDTCIKZWxzZQogICAgc2tpcCAibHVjaS1iYXNlLmpzb24gbm90IGluICRCSU4iCmZpCgppZiBbIC1mICIkQklOL2ZpcmV3YWxsLnVzZXIiIF07IHRoZW4KICAgIGNwICIkQklOL2ZpcmV3YWxsLnVzZXIiIC9ldGMvZmlyZXdhbGwudXNlcgogICAgb2sgImZpcmV3YWxsLnVzZXIiCmVsc2UKICAgIHNraXAgImZpcmV3YWxsLnVzZXIgbm90IGluICRCSU4iCmZpCgojIOKUgOKUgCAzYi4gUGF0Y2ggYXBpX3N5c3RlbS5sdWEgdG8gcmVzcGVjdCBkZWJ1Z19tb2RlPTk5IOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICJbM2JdIFBhdGNoaW5nIGFwaV9zeXN0ZW0ubHVhIChnZXRfZGV2ZWxvcF9tb2RlIGJ5cGFzcykuLi4iCkFQSV9TWVNURU09Ii91c3IvbGliL2x1YS9sdWNpL21vZGVsL2Z1bmN0aW9ucy9hcGlfc3lzdGVtLmx1YSIKQVBJX0JBSz0iL3Vzci9saWIvbHVhL2x1Y2kvbW9kZWwvZnVuY3Rpb25zL2FwaV9zeXN0ZW0ubHVhYy5iYWsiCgppZiAhIGdyZXAgLXEgImRlYnVnX21vZGUuKmJ5cGFzc1x8aXNfZGVidWdfbW9kZSIgIiRBUElfU1lTVEVNIiAyPi9kZXYvbnVsbDsgdGhlbgogICAgIyBCYWNrdXAgdGhlIG9yaWdpbmFsIGNvbXBpbGVkIGZpbGUKICAgIFsgISAtZiAiJEFQSV9CQUsiIF0gJiYgY3AgIiRBUElfU1lTVEVNIiAiJEFQSV9CQUsiCgogICAgIyBSZXBsYWNlIHdpdGggc291cmNlIHdyYXBwZXIgdGhhdCBwYXRjaGVzIGdldF9kZXZlbG9wX21vZGUKICAgIGNhdCA+ICIkQVBJX1NZU1RFTSIgPDwgJ0FQSVBBVENIRU9GJwotLSBhcGlfc3lzdGVtLmx1YSDigJQgd3JhcHBlciB0aGF0IHBhdGNoZXMgZ2V0X2RldmVsb3BfbW9kZSBmb3IgZGVidWdfbW9kZT05OQpsb2NhbCBvcmlnX3BhdGggPSAiL3Vzci9saWIvbHVhL2x1Y2kvbW9kZWwvZnVuY3Rpb25zL2FwaV9zeXN0ZW0ubHVhYy5iYWsiCmxvY2FsIG9yaWdfZnVuYyA9IGxvYWRmaWxlKG9yaWdfcGF0aCkKaWYgbm90IG9yaWdfZnVuYyB0aGVuIHJldHVybiB7fSBlbmQKb3JpZ19mdW5jKCkKbG9jYWwgTSA9IF9HCmZvciBwYXJ0IGluICgibHVjaS5tb2RlbC5mdW5jdGlvbnMuYXBpX3N5c3RlbSIpOmdtYXRjaCgiW14uXSsiKSBkbyBNID0gTVtwYXJ0XSBlbmQKaWYgTSBhbmQgdHlwZShNKSA9PSAidGFibGUiIGFuZCBNLmdldF9kZXZlbG9wX21vZGUgdGhlbgogICAgbG9jYWwgZHQgPSByZXF1aXJlICJsdWNpLmR0b2tlbiIKICAgIGxvY2FsIG9yaWdfZ2V0ID0gTS5nZXRfZGV2ZWxvcF9tb2RlCiAgICBNLmdldF9kZXZlbG9wX21vZGUgPSBmdW5jdGlvbigpCiAgICAgICAgaWYgZHQuaXNfZGVidWdfbW9kZSgpIHRoZW4gcmV0dXJuIDEgZW5kCiAgICAgICAgcmV0dXJuIG9yaWdfZ2V0KCkKICAgIGVuZAplbmQKcmV0dXJuIE0gb3Ige30KQVBJUEFUQ0hFT0YKICAgIG9rICJhcGlfc3lzdGVtLmx1YSBwYXRjaGVkIChkZWJ1Z19tb2RlIGJ5cGFzcykiCmVsc2UKICAgIG9rICJhcGlfc3lzdGVtLmx1YSBhbHJlYWR5IHBhdGNoZWQiCmZpCgojIEFsc28gZW5zdXJlIERCR19NT0RFIGlzIHNldCB0byB5ZXMKaWYgZ3JlcCAtcSAiREJHX01PREU6bm8iIC9ldGMvanl0bC12ZXJzaW9uIDI+L2Rldi9udWxsOyB0aGVuCiAgICBzZWQgLWkgJ3MvREJHX01PREU6bm8vREJHX01PREU6eWVzLycgL2V0Yy9qeXRsLXZlcnNpb24KICAgIG9rICJEQkdfTU9ERSBzZXQgdG8geWVzIgplbHNlCiAgICBvayAiREJHX01PREUgYWxyZWFkeSB5ZXMgb3Igbm90IHByZXNlbnQiCmZpCgojIOKUgOKUgCA0LiBSZW1vdmUgcm0gd3JhcHBlciAoY2F1c2VzIGxvZ2luIGlzc3Vlcykg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmVjaG8gIls0LzEwXSBSZW1vdmluZyBybSB3cmFwcGVyIChpZiBwcmVzZW50KS4uLiIKaWYgWyAtZiAvYmluL3JtLmJ1c3lib3ggXTsgdGhlbgogICAgL2Jpbi9idXN5Ym94IHJtIC1mIC9iaW4vcm0KICAgIC9iaW4vYnVzeWJveCBtdiAvYmluL3JtLmJ1c3lib3ggL2Jpbi9ybQogICAgL2Jpbi9idXN5Ym94IHJtIC1mIC91c3IvbG9jYWwvYmluL3JtCiAgICBvayAicm0gd3JhcHBlciByZW1vdmVkIgplbHNlCiAgICBvayAicm0gd3JhcHBlciBub3QgcHJlc2VudCIKZmkKCiMg4pSA4pSAIDUuIFNTSCBrZXkgKyBwYXNzd29yZCBhdXRoIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICJbNS8xMF0gU2VjdXJpbmcgU1NIIGNvbmZpZ3VyYXRpb24uLi4iClBVQktFWV9GSUxFPS90bXAvdXNlcl9zc2hfa2V5LnB1YgppZiBbIC1zICIkUFVCS0VZX0ZJTEUiIF07IHRoZW4KICAgIGNwICIkUFVCS0VZX0ZJTEUiIC9ldGMvZHJvcGJlYXIvYXV0aG9yaXplZF9rZXlzCiAgICBjaG1vZCA2MDAgL2V0Yy9kcm9wYmVhci9hdXRob3JpemVkX2tleXMKICAgIG9rICJhdXRob3JpemVkX2tleXM6IHVzZXIga2V5IG9ubHkiCmVsc2UKICAgIGVjaG8gIiAgYXV0aG9yaXplZF9rZXlzOiBQUkVTRVJWRUQgKG5vIHVzZXIga2V5IOKAlCBza2lwcGluZyB0byBhdm9pZCBsb2Nrb3V0KSIKZmkKdWNpIHNldCBkcm9wYmVhci5AZHJvcGJlYXJbMF0uUGFzc3dvcmRBdXRoPW9uIDI+L2Rldi9udWxsCnVjaSBzZXQgZHJvcGJlYXIuQGRyb3BiZWFyWzBdLlJvb3RQYXNzd29yZEF1dGg9b24gMj4vZGV2L251bGwKdWNpIGNvbW1pdCBkcm9wYmVhciAyPi9kZXYvbnVsbApvayAiZHJvcGJlYXI6IFBhc3N3b3JkQXV0aD1vbiwgUm9vdFBhc3N3b3JkQXV0aD1vbiAoZWZmZWN0aXZlIGFmdGVyIHJlYm9vdCkiCgojIOKUgOKUgCA2LiBLaWxsIGdlby1sb2NrIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICJbNi8xMF0gS2lsbGluZyBnZW8tbG9jayBjaGFpbi4uLiIKL2V0Yy9pbml0LmQvbW5sZCBzdG9wIDI+L2Rldi9udWxsOyAvZXRjL2luaXQuZC9tbmxkIGRpc2FibGUgMj4vZGV2L251bGwgfHwgdHJ1ZQovZXRjL2luaXQuZC9tdGtfYWdwc2Qgc3RvcCAyPi9kZXYvbnVsbDsgL2V0Yy9pbml0LmQvbXRrX2FncHNkIGRpc2FibGUgMj4vZGV2L251bGwgfHwgdHJ1ZQpybSAtZiAvZXRjL3JjLmQvUzUzbW5sZCAvZXRjL3JjLmQvUzU0bXRrX2FncHNkIDI+L2Rldi9udWxsCmtpbGxhbGwgLTkgbW5sZCBtbmxkX3Rlc3QgbXRrX2FncHNkIDI+L2Rldi9udWxsIHx8IHRydWUKL2V0Yy9pbml0LmQvanl0bF9ncHMgc3RvcCAyPi9kZXYvbnVsbDsgL2V0Yy9pbml0LmQvanl0bF9ncHMgZGlzYWJsZSAyPi9kZXYvbnVsbCB8fCB0cnVlCnJtIC1mIC9ldGMvcmMuZC9TOThqeXRsX2dwcyAvZXRjL3JjLmQvSzk3anl0bF9ncHMgMj4vZGV2L251bGwKaXB0YWJsZXMgLUkgT1VUUFVUIC1kIGdsb2JlLW1xdHQudGhlMTAxLmNsb3VkIC1qIERST1AgMj4vZGV2L251bGwgfHwgdHJ1ZQppcHRhYmxlcyAtSSBPVVRQVVQgLXAgdGNwIC0tZHBvcnQgODg4MyAtaiBEUk9QIDI+L2Rldi9udWxsIHx8IHRydWUKaXB0YWJsZXMgLUkgT1VUUFVUIC1wIHRjcCAtLWRwb3J0IDE4ODMgLWogRFJPUCAyPi9kZXYvbnVsbCB8fCB0cnVlCm9rICJnZW8tbG9jayBERUFEIgoKIyDilIDilIAgNy4gRGlzYWJsZSBiYWNrZG9vcnMg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmVjaG8gIls3LzEwXSBEaXNhYmxpbmcgYmFja2Rvb3Igc2VydmljZXMuLi4iCi9ldGMvaW5pdC5kL3RlbG5ldGQgc3RvcCAyPi9kZXYvbnVsbDsgL2V0Yy9pbml0LmQvdGVsbmV0ZCBkaXNhYmxlIDI+L2Rldi9udWxsIHx8IHRydWUKcm0gLWYgL2V0Yy9yYy5kL1M5OXRlbG5ldGQgL2RhdGEvanl0bF9mYWN0b3J5L3RlbG5ldF9vbiAyPi9kZXYvbnVsbApraWxsYWxsIC05IHRlbG5ldGQgMj4vZGV2L251bGwgfHwgdHJ1ZQpbIC1mIC9zYmluL2FkYmRfdXNiIF0gJiYgbXYgL3NiaW4vYWRiZF91c2IgL3NiaW4vYWRiZF91c2IuZGlzYWJsZWQgMj4vZGV2L251bGwKa2lsbGFsbCAtOSBhZGJkX3VzYiAyPi9kZXYvbnVsbCB8fCB0cnVlCi9ldGMvaW5pdC5kL3phdGVfYWdlbnQuaW5pdCBzdG9wIDI+L2Rldi9udWxsOyAvZXRjL2luaXQuZC96YXRlX2FnZW50LmluaXQgZGlzYWJsZSAyPi9kZXYvbnVsbCB8fCB0cnVlCnJtIC1mIC9ldGMvcmMuZC9TOTh6YXRlX2FnZW50LmluaXQgMj4vZGV2L251bGwKa2lsbGFsbCAtOSBhdGVfYWdlbnQgMj4vZGV2L251bGwgfHwgdHJ1ZQpvayAidGVsbmV0LCBBREIsIEFUIGFnZW50OiBERUFEIgoKIyDilIDilIAgOC4gS2lsbCBwaG9uZS1ob21lIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICJbOC8xMF0gS2lsbGluZyBwaG9uZS1ob21lIHNlcnZpY2VzLi4uIgpybSAtZiAvZXRjL2luaXQuZC91ZHBBcHAgL2V0Yy9yYy5kL1M3MHVkcEFwcCAyPi9kZXYvbnVsbApraWxsYWxsIC05IHVkcEFwcCAyPi9kZXYvbnVsbCB8fCB0cnVlCnJtIC1mIC9ldGMvaW5pdC5kL2J1bGtfaW5mb3JtIC9ldGMvcmMuZC9TNzBidWxrX2luZm9ybSAyPi9kZXYvbnVsbApraWxsYWxsIC05IGJ1bGtfaW5mb3JtIDI+L2Rldi9udWxsIHx8IHRydWUKL2V0Yy9pbml0LmQvY2VydF9zeW5jIHN0b3AgMj4vZGV2L251bGw7IC9ldGMvaW5pdC5kL2NlcnRfc3luYyBkaXNhYmxlIDI+L2Rldi9udWxsIHx8IHRydWUKcm0gLWYgL2V0Yy9yYy5kL1M5OWNlcnRfc3luYyAyPi9kZXYvbnVsbApzZWQgLWkgJy9jaGVja19zc2xfY2VydC9kJyAvZXRjL2Nyb250YWJzL3Jvb3QgMj4vZGV2L251bGwgfHwgdHJ1ZQpybSAtZiAvZXRjL2luaXQuZC9pcGVyZl9zZXJ2aWNlIC9ldGMvcmMuZC9TOTlpcGVyZl9zZXJ2aWNlIDI+L2Rldi9udWxsCmtpbGxhbGwgLTkgaXBlcmYzIDI+L2Rldi9udWxsIHx8IHRydWUKb2sgInVkcEFwcCwgYnVsa19pbmZvcm0sIGNlcnRfc3luYywgaXBlcmYzOiBERUFEIgoKIyDilIDilIAgOS4gRmlyZXdhbGwgQVQgcG9ydHMg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmVjaG8gIls5LzEwXSBGaXJld2FsbGluZyBBVCBjb21tYW5kIHBvcnRzLi4uIgppcHRhYmxlcyAtSSBJTlBVVCAtaSBsbyAtcCB0Y3AgLS1kcG9ydCAxNzE3MSAtaiBBQ0NFUFQgMj4vZGV2L251bGwgfHwgdHJ1ZQppcHRhYmxlcyAtSSBJTlBVVCAtaSBsbyAtcCB0Y3AgLS1kcG9ydCAxNzE3MiAtaiBBQ0NFUFQgMj4vZGV2L251bGwgfHwgdHJ1ZQppcHRhYmxlcyAtSSBJTlBVVCAtcCB0Y3AgLS1kcG9ydCAxNzE3MSAtaiBEUk9QIDI+L2Rldi9udWxsIHx8IHRydWUKaXB0YWJsZXMgLUkgSU5QVVQgLXAgdGNwIC0tZHBvcnQgMTcxNzIgLWogRFJPUCAyPi9kZXYvbnVsbCB8fCB0cnVlCm9rICJBVCBwb3J0cyBmaXJld2FsbGVkIChsb2NhbGhvc3Qgb25seSkiCgojIOKUgOKUgCAxMC4gUGVyc2lzdCBhY3Jvc3MgcmVib290cyDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKZWNobyAiWzEwLzEwXSBFbnN1cmluZyBib290IHBlcnNpc3RlbmNlLi4uIgppZiAhIGdyZXAgLXEgIm9wZW5saW5lIGRldmVsb3BlciBwZXJzaXN0ZW5jZSB2MiIgL2V0Yy9yYy5sb2NhbCAyPi9kZXYvbnVsbDsgdGhlbgogICAgc2VkIC1pICcvXmV4aXQgMCQvZCcgL2V0Yy9yYy5sb2NhbAogICAgY2F0ID4+IC9ldGMvcmMubG9jYWwgPDwgJ0VORE9GUEVSU0lTVCcKIyBvcGVubGluZSBkZXZlbG9wZXIgcGVyc2lzdGVuY2UgdjIKbWtkaXIgLXAgL2RhdGEvanl0bF9mYWN0b3J5CnByaW50ZiAnOTknID4gL2RhdGEvanl0bF9mYWN0b3J5L2RlYnVnX21vZGUKc2VkIC1pICdzLyJzdXBlcl9hZG1pbiI6ICIwIi8ic3VwZXJfYWRtaW4iOiAiMSIvJyAvZXRjL3Byb3BlcnR5Lmpzb24gMj4vZGV2L251bGwgfHwgdHJ1ZQoKIyBFbnN1cmUgZGV2bW9kZSAvdG1wIGZpbGVzIGV4aXN0IChmYWxsYmFjayBpZiBpbml0IHNjcmlwdCBtaXNzZXMgdGhlbSkKaWYgWyAhIC1mIC90bXAvanlfZGV2ZWxvcGVyX21vZGUgXTsgdGhlbgogICAgcHJpbnRmICcxJyA+IC90bXAvanlfZGV2ZWxvcGVyX21vZGUKICAgIGhlYWQgLWMgMTYgL2Rldi91cmFuZG9tIHwgbWQ1c3VtIHwgYXdrICd7cHJpbnRmICQxfScgPiAvdG1wL2p5X2RldmVsb3Blcl90b2tlbgogICAgdG91Y2ggL3RtcC9qeXRsX2RlYnVnX2FiCmZpCgpleGl0IDAKRU5ET0ZQRVJTSVNUCiAgICBvayAicmMubG9jYWwgdXBkYXRlZCIKZWxzZQogICAgb2sgInJjLmxvY2FsIGFscmVhZHkgaGFzIHBlcnNpc3RlbmNlIHYyIgpmaQoKIyDilIDilIAgUmVzdGFydCBzZXJ2aWNlcyArIGVuc3VyZSBkZXZtb2RlIGZpbGVzIOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICIiCmVjaG8gIlJlc3RhcnRpbmcgc2VydmljZXMuLi4iCi9ldGMvaW5pdC5kL3JwY2QgcmVzdGFydCAyPi9kZXYvbnVsbCB8fCB0cnVlCi9ldGMvaW5pdC5kL3VodHRwZCByZXN0YXJ0IDI+L2Rldi9udWxsIHx8IHRydWUKIyBDcmVhdGUgL3RtcCBkZXZtb2RlIGZpbGVzIEFGVEVSIHJwY2QgcmVzdGFydCDigJQgdGhlIG5ldyBkdG9rZW4ubHVhCiMgd2l0aCBieXBhc3NlcyBpcyBub3cgbG9hZGVkLCBzbyBkZXZlbG9wX21vZGVfZXhpdCgpIHdvbid0IGZpcmUuCi9ldGMvaW5pdC5kL2Rldm1vZGUgYm9vdCAyPi9kZXYvbnVsbCB8fCB0cnVlCgojIOKUgOKUgCBTdW1tYXJ5IOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgOKUgAplY2hvICIiCmVjaG8gIj09PSBIYXJkZW5pbmcgQ29tcGxldGUgPT09IgplY2hvICJUUi0wNjk6ICAgICAgICAgREVBRCIKZWNobyAiR2VvLWxvY2s6ICAgICAgIERFQUQiCmVjaG8gIk1RVFQgcGhvbmVob21lOiBCTE9DS0VEIgplY2hvICJCYWNrZG9vcnM6ICAgICAgdGVsbmV0L0FEQi9BVCBERUFEIgplY2hvICJBVCBwb3J0czogICAgICAgRklSRVdBTExFRCAobG9jYWxob3N0IG9ubHkpIgplY2hvICJkZWJ1Z19tb2RlOiAgICAgJChjYXQgL2RhdGEvanl0bF9mYWN0b3J5L2RlYnVnX21vZGUgMj4vZGV2L251bGwgfHwgZWNobyAnbm90IHNldCcpIgplY2hvICJzdXBlcl9hZG1pbjogICAgJChncmVwIHN1cGVyX2FkbWluIC9ldGMvcHJvcGVydHkuanNvbiAyPi9kZXYvbnVsbCB8fCBlY2hvICd1bmtub3duJykiCmVjaG8gImR0b2tlbi5sdWE6ICAgICAkKGdyZXAgLXEgJ0RFQlVHIE1PREUgQllQQVNTJyAvdXNyL2xpYi9sdWEvbHVjaS9kdG9rZW4ubHVhIDI+L2Rldi9udWxsICYmIGVjaG8gJ1BBVENIRUQnIHx8IGVjaG8gJ09SSUdJTkFMJykiCmVjaG8gIlNTSCBrZXlzOiAgICAgICAkKHdjIC1sIDwgL2V0Yy9kcm9wYmVhci9hdXRob3JpemVkX2tleXMgMj4vZGV2L251bGwgfHwgZWNobyAwKSBrZXlzIgplY2hvICIiCg==",
    "dtoken.lua": "LS0gQ29weXJpZ2h0IDIwMDkgU3RldmVuIEJhcnRoIDxzdGV2ZW5AbWlkbGluay5vcmc+Ci0tIENvcHlyaWdodCAyMDA5IEpvLVBoaWxpcHAgV2ljaCA8am93QG9wZW53cnQub3JnPgotLSBMaWNlbnNlZCB0byB0aGUgcHVibGljIHVuZGVyIHRoZSBBcGFjaGUgTGljZW5zZSAyLjAuCgpsb2NhbCBNID0ge30gCgpsb2NhbCBmcyA9IHJlcXVpcmUgIm5peGlvLmZzIgpsb2NhbCBqc29uICA9IHJlcXVpcmUgImx1Y2kuanNvbmMiCmxvY2FsIG54ID0gcmVxdWlyZSAibml4aW8iCgoKbG9jYWwgZnVuY3Rpb24gbG9nZ2VyX3ByaW50KGZsYWcsIG1lc3NhZ2UpCglueC5vcGVubG9nKCJKWVRMX1RPIi4uZmxhZy4uIl8iLi5hcmdbMF06bWF0Y2goIi4rLyglUyspJCIpOnVwcGVyKCkpCglueC5zeXNsb2coImluZm8iLG1lc3NhZ2UpCglueC5jbG9zZWxvZygpCmVuZAoKbG9jYWwgZnVuY3Rpb24gZ2V0X2RldmVsb3Btb2RlKGR0b2tlbiwgdG9rZW4pCglpZiBnZXRfZGVidWdfbW9kZSgpID09IDk5IHRoZW4KCQlyZXR1cm4gMQoJZW5kCgoJbG9jYWwgZGV2ZWxvcF9tb2RlID0gMAoJaWYgdG9rZW4gfj0gJy0nIGFuZCB0b2tlbiA9PSBkdG9rZW4gdGhlbgoJCWRldmVsb3BfbW9kZSA9IDEKCWVsc2UKCQlkZXZlbG9wX21vZGUgPSAwCgllbmQKCQoJcmV0dXJuIGRldmVsb3BfbW9kZQplbmQKCmxvY2FsIGZ1bmN0aW9uIGdldF9kZWJ1Z19tb2RlKCkKCWxvY2FsIGRlYnVnX21vZGUgPSBmcy5yZWFkZmlsZSgiL2RhdGEvanl0bF9mYWN0b3J5L2RlYnVnX21vZGUiKSBvciAnMCcKCWRlYnVnX21vZGUgPSB0b251bWJlcihkZWJ1Z19tb2RlKQoJCglyZXR1cm4gZGVidWdfbW9kZQplbmQKCmxvY2FsIGZ1bmN0aW9uIGNoZWNrX2FjbChtZXRob2RzLCBmdW5jLCBtb2RlKQoJbG9jYWwgbWV0aG9kID0gbWV0aG9kc1tmdW5jXQoJCglpZiBub3QgbWV0aG9kIHRoZW4KCQlwcmludChqc29uLnN0cmluZ2lmeSh7IGVycm9yID0gIk1ldGhvZCBub3QgZm91bmQiIH0pKQoJCW9zLmV4aXQoMSkKCWVuZAoJCglsb2NhbCBzdXBlciA9IChtZXRob2Quc3VwZXIgYW5kIDEgb3IgMCkKCQoJaWYgc3VwZXIgPT0gMSBhbmQgbW9kZSA9PSAwIHRoZW4KCQlyZXR1cm4gZmFsc2UKCWVuZAoKCXJldHVybiB0cnVlCmVuZAoKZnVuY3Rpb24gTS5kZXZlbG9wX21vZGVfZXhpdCgpCglvcy5leGVjdXRlKCJybSAtZiAvdG1wL2p5X2RldmVsb3Blcl9tb2RlIikKCW9zLmV4ZWN1dGUoInJtIC1mIC90bXAvanlfZGV2ZWxvcGVyX3Rva2VuIikKZW5kCgpmdW5jdGlvbiBNLmlzX2ludmFsaWQoZHRva2VuLCB0b2tlbikKCWxvY2FsIGludmFsaWQgPSBmYWxzZQoJaWYgKHRva2VuIH49ICctJyBhbmQgdG9rZW4gfj0gZHRva2VuKSBvciAodG9rZW4gPT0gJy0nIGFuZCBkdG9rZW4gfj0gJy0nKSB0aGVuCgkJaW52YWxpZCA9IHRydWUKCWVsc2UKCQlpbnZhbGlkID0gZmFsc2UKCWVuZAoJCglyZXR1cm4gaW52YWxpZAplbmQKCmZ1bmN0aW9uIE0uaXNfbm90X2RldmVsb3AodG9rZW4pCglpZiB0b2tlbiA9PSAnLScgdGhlbgoJCXJldHVybiB0cnVlCgllbmQKCQoJcmV0dXJuIGZhbHNlCmVuZAoKZnVuY3Rpb24gTS5pc19kZWJ1Z19tb2RlKCkKCWlmIGdldF9kZWJ1Z19tb2RlKCkgPT0gOTkgdGhlbgoJCXJldHVybiB0cnVlCgllbmQKCQoJcmV0dXJuIGZhbHNlCmVuZAoKZnVuY3Rpb24gTS5hdXRoX3VidXNfYWNsKHJwY19zaWQsIG1ldGhvZHMsIGZ1bmMsIGR0b2tlbikKCWxvY2FsIHRva2VuID0gZnMucmVhZGZpbGUoIi90bXAvanlfZGV2ZWxvcGVyX3Rva2VuIikgb3IgJy0nCgkKCWlmIG5vdCBycGNfc2lkIHRoZW4KCQlyZXR1cm4gdHJ1ZQoJZW5kCgkKCS0tIERFQlVHIE1PREUgQllQQVNTOiBza2lwIEFMTCBjaGVja3Mgd2hlbiBkZWJ1Z19tb2RlPTk5CglpZiBNLmlzX2RlYnVnX21vZGUoKSB0aGVuCgkJcmV0dXJuIHRydWUKCWVuZAoKCWlmIE0uaXNfaW52YWxpZChkdG9rZW4sIHRva2VuKSB0aGVuCgkJcHJpbnQoanNvbi5zdHJpbmdpZnkoeyBlcnJvciA9ICJJbnZhbGlkIHRva2VuIiB9KSkKCQlsb2dnZXJfcHJpbnQoJ0ZMJywidWJ1cyBjYWxsICIuLmZ1bmMuLiIgcmVzdWx0OiBJbnZhbGlkIHRva2VuLCBkdG9rZW46ICIuLmR0b2tlbi4uIiwgdG9rZW46ICIuLnRva2VuKQoJCU0uZGV2ZWxvcF9tb2RlX2V4aXQoKQoJCW9zLmV4aXQoMSkKCQlyZXR1cm4gZmFsc2UKCWVuZAoKCWlmIG5vdCBjaGVja19hY2wobWV0aG9kcywgZnVuYywgZ2V0X2RldmVsb3Btb2RlKGR0b2tlbiwgdG9rZW4pKSB0aGVuCgkJaWYgbm90IE0uaXNfZGVidWdfbW9kZSgpIHRoZW4KCQkJcHJpbnQoanNvbi5zdHJpbmdpZnkoeyBlcnJvciA9ICJBQ0wgZXJyb3IiIH0pKQoJCQlsb2dnZXJfcHJpbnQoJ0ZMJywidWJ1cyBjYWxsICIuLmZ1bmMuLiIgcmVzdWx0OiBBQ0wgRXJyLCBkdG9rZW46ICIuLmR0b2tlbi4uIiwgdG9rZW46ICIuLnRva2VuKQoJCQlNLmRldmVsb3BfbW9kZV9leGl0KCkKCQkJb3MuZXhpdCgxKQoJCQlyZXR1cm4gZmFsc2UKCQllbmQKCWVuZAoJCglyZXR1cm4gdHJ1ZQplbmQKCmZ1bmN0aW9uIE0uY2hlY2tfbHVjaV9hY2woc3VwZXIsIHRva2VuKQoJaWYgTS5pc19ub3RfZGV2ZWxvcCh0b2tlbikgYW5kIHN1cGVyIHRoZW4KCQlyZXR1cm4gZmFsc2UKCWVuZAoJCglyZXR1cm4gdHJ1ZQplbmQKCk0uU1RfT0s9MApNLlNUX0lOVkFMSURfVE9LRU49MQpNLlNUX0FDTF9FUlI9MgoKCmZ1bmN0aW9uIE0uY2hlY2tfbHVjaV9hY2xfc3QoZHRva2VuLCBzdXBlcikKCS0tIERFQlVHIE1PREUgQllQQVNTOiBza2lwIEFMTCBjaGVja3Mgd2hlbiBkZWJ1Z19tb2RlPTk5CglpZiBNLmlzX2RlYnVnX21vZGUoKSB0aGVuCgkJcmV0dXJuIE0uU1RfT0sKCWVuZAoKCWxvY2FsIHRva2VuID0gZnMucmVhZGZpbGUoIi90bXAvanlfZGV2ZWxvcGVyX3Rva2VuIikgb3IgJy0nCgkKCWlmIE0uaXNfaW52YWxpZChkdG9rZW4sIHRva2VuKSB0aGVuCgkJcmV0dXJuIE0uU1RfSU5WQUxJRF9UT0tFTgoJZW5kCgoJaWYgbm90IE0uaXNfZGVidWdfbW9kZSgpIHRoZW4KCQlpZiBub3QgTS5jaGVja19sdWNpX2FjbChzdXBlciwgdG9rZW4pIHRoZW4KCQkJcmV0dXJuIE0uU1RfQUNMX0VSUgoJCWVuZAoJZW5kCgkKCXJldHVybiBNLlNUX09LCmVuZAoKcmV0dXJuIE0KCg==",
    "devmode": "IyEvYmluL3NoIC9ldGMvcmMuY29tbW9uClNUQVJUPTk3CmJvb3QoKSB7CiAgICAjIFNldCBkZWJ1Z19tb2RlPTk5IEZJUlNUIHNvIGR0b2tlbi5sdWEgYnlwYXNzIGlzIGFjdGl2ZSBiZWZvcmUKICAgICMgL3RtcCBmaWxlcyBhcHBlYXIg4oCUIHByZXZlbnRzIGRldmVsb3BfbW9kZV9leGl0KCkgZnJvbSBkZWxldGluZyB0aGVtLgogICAgbWtkaXIgLXAgL2RhdGEvanl0bF9mYWN0b3J5CiAgICBwcmludGYgJzk5JyA+IC9kYXRhL2p5dGxfZmFjdG9yeS9kZWJ1Z19tb2RlCiAgICBzZWQgLWkgJ3MvInN1cGVyX2FkbWluIjogIjAiLyJzdXBlcl9hZG1pbiI6ICIxIi8nIC9ldGMvcHJvcGVydHkuanNvbiAyPi9kZXYvbnVsbCB8fCB0cnVlCgogICAgcHJpbnRmICcxJyA+IC90bXAvanlfZGV2ZWxvcGVyX21vZGUKICAgIGhlYWQgLWMgMTYgL2Rldi91cmFuZG9tIHwgbWQ1c3VtIHwgYXdrICd7cHJpbnRmICQxfScgPiAvdG1wL2p5X2RldmVsb3Blcl90b2tlbgogICAgdG91Y2ggL3RtcC9qeXRsX2RlYnVnX2FiCiAgICBlY2hvIE5vbmUgPiAvdmFyL2F0ZV9hZ2VudAp9CnN0YXJ0KCkgeyBib290OyB9Cg==",
    "luci-base.json": "ewoJInVuYXV0aGVudGljYXRlZCI6IHsKCQkiZGVzY3JpcHRpb24iOiAiQWxsb3cgc3lzdGVtIGZlYXR1cmUgcHJvYmluZyIsCgkJInJlYWQiOiB7CgkJCSJ1YnVzIjogewoJCQkJImx1Y2kiOiBbICIqIiBdCgkJCX0KCQl9Cgl9LAoKCSJ1Y2ktYWNjZXNzIjogewoJCSJkZXNjcmlwdGlvbiI6ICJHcmFudCB1Y2kgd3JpdGUgYWNjZXNzIHRvIGFsbCBjb25maWd1cmF0aW9ucyIsCgkJInJlYWQiOiB7CgkJCSJ1Y2kiOiBbICIqIiBdCgkJfSwKCQkid3JpdGUiOiB7CgkJCSJ1Y2kiOiBbICIqIiBdCgkJfQoJfSwKCSJsdWNpLWFjY2VzcyI6IHsKCQkiZGVzY3JpcHRpb24iOiAiR3JhbnQgYWNjZXNzIHRvIGJhc2ljIEx1Q0kgcHJvY2VkdXJlcyIsCgkJInJlYWQiOiB7CgkJCSJjZ2ktaW8iOiBbICJiYWNrdXAiLCAiZG93bmxvYWQiLCAiZXhlYyIgXSwKCQkJImZpbGUiOiB7CgkJCQkiLyI6IFsgImxpc3QiIF0sCgkJCQkiLyoiOiBbICJsaXN0IiBdLAoJCQkJIi9kZXYvbXRkYmxvY2sqIjogWyAicmVhZCIgXSwKCQkJCSIvZXRjL2Nyb250YWJzL3Jvb3QiOiBbICJyZWFkIiBdLAoJCQkJIi9ldGMvZHJvcGJlYXIvYXV0aG9yaXplZF9rZXlzIjogWyAicmVhZCIgXSwKCQkJCSIvZXRjL2ZpbGVzeXN0ZW1zIjogWyAicmVhZCIgXSwKCQkJCSIvZXRjL3JjLmxvY2FsIjogWyAicmVhZCIgXSwKCQkJCSIvZXRjL3N5c3VwZ3JhZGUuY29uZiI6IFsgInJlYWQiIF0sCgkJCQkiL2V0Yy9wYXNzd2QiOiBbICJyZWFkIiBdLAoJCQkJIi9ldGMvZ3JvdXAiOiBbICJyZWFkIiBdLAoJCQkJIi9wcm9jL2ZpbGVzeXN0ZW1zIjogWyAicmVhZCIgXSwKCQkJCSIvcHJvYy9tdGQiOiBbICJyZWFkIiBdLAoJCQkJIi9wcm9jL3BhcnRpdGlvbnMiOiBbICJyZWFkIiBdLAoJCQkJIi9wcm9jL3N5cy9rZXJuZWwvaG9zdG5hbWUiOiBbICJyZWFkIiBdLAoJCQkJIi9wcm9jL3N5cy9uZXQvbmV0ZmlsdGVyL25mX2Nvbm50cmFja18qIjogWyAicmVhZCIgXSwKCQkJCSIvcHJvYy9tb3VudHMiOiBbICJyZWFkIiBdLAoJCQkJIi91c3IvbGliL2x1YS9sdWNpL3ZlcnNpb24ubHVhIjogWyAicmVhZCIgXSwKCQkJCSIvYmluL2RtZXNnIC1yIjogWyAiZXhlYyIgXSwKCQkJCSIvYmluL3BpbmcgKiI6IFsgImV4ZWMiIF0sCgkJCQkiL2Jpbi9waW5nNiAqIjogWyAiZXhlYyIgXSwKCQkJCSIvYmluL3RyYWNlcm91dGUgKiI6IFsgImV4ZWMiIF0sCgkJCQkiL2Jpbi90cmFjZXJvdXRlNiAqIjogWyAiZXhlYyIgXSwKCQkJCSIvc2Jpbi9pcCAtNCBuZWlnaCBzaG93IjogWyAiZXhlYyIgXSwKCQkJCSIvc2Jpbi9pcCAtNCByb3V0ZSBzaG93IHRhYmxlIGFsbCI6IFsgImV4ZWMiIF0sCgkJCQkiL3NiaW4vaXAgLTYgbmVpZ2ggc2hvdyI6IFsgImV4ZWMiIF0sCgkJCQkiL3NiaW4vaXAgLTYgcm91dGUgc2hvdyB0YWJsZSBhbGwiOiBbICJleGVjIiBdLAoJCQkJIi9zYmluL2xvZ3JlYWQgLWUgXiI6IFsgImV4ZWMiIF0sCgkJCQkiL3Vzci9zYmluL2xvZ3JlYWQgLWUgXiI6IFsgImV4ZWMiIF0sCgkJCQkiL3Vzci9iaW4vcGluZyAqIjogWyAiZXhlYyIgXSwKCQkJCSIvdXNyL2Jpbi9waW5nNiAqIjogWyAiZXhlYyIgXSwKCQkJCSIvdXNyL2Jpbi90cmFjZXJvdXRlICoiOiBbICJleGVjIiBdLAoJCQkJIi91c3IvYmluL3RyYWNlcm91dGU2ICoiOiBbICJleGVjIiBdLAoJCQkJIi91c3IvYmluL25zbG9va3VwICoiOiBbICJleGVjIiBdLAoJCQkJIi91c3IvbGliZXhlYy9sdWNpLXBlZXJhZGRyIjogWyAiZXhlYyIgXSwKCQkJCSIvdXNyL3NiaW4vaXB0YWJsZXMgLS1saW5lLW51bWJlcnMgLXcgLW52eEwgLXQgKiI6IFsgImV4ZWMiIF0sCgkJCQkiL3Vzci9zYmluL2lwNnRhYmxlcyAtLWxpbmUtbnVtYmVycyAtdyAtbnZ4TCAtdCAqIjogWyAiZXhlYyIgXQoJCQl9LAoJCQkidWJ1cyI6IHsKCQkJCSJmaWxlIjogWyAibGlzdCIsICJyZWFkIiwgInN0YXQiIF0sCgkJCQkiaXdpbmZvIjogWyAiYXNzb2NsaXN0IiwgImZyZXFsaXN0IiwgInR4cG93ZXJsaXN0IiwgImNvdW50cnlsaXN0IiBdLAoJCQkJImx1Y2kiOiBbICIqIiBdLAoJCQkJImx1Y2ktcnBjIjogWyAiZ2V0Qm9hcmRKU09OIiwgImdldERIQ1BMZWFzZXMiLCAiZ2V0RFNMU3RhdHVzIiwgImdldERVSURIaW50cyIsICJnZXRIb3N0SGludHMiLCAiZ2V0TmV0d29ya0RldmljZXMiLCAiZ2V0V2lyZWxlc3NEZXZpY2VzIiBdLAoJCQkJIm5ldHdvcmsuaW50ZXJmYWNlIjogWyAiZHVtcCIgXSwKCQkJCSJuZXR3b3JrLnJyZG5zIjogWyAibG9va3VwIiBdLAoJCQkJIm5ldHdvcmsiOiBbICJnZXRfcHJvdG9faGFuZGxlcnMiIF0sCgkJCQkic3lzdGVtIjogWyAiYm9hcmQiLCAiaW5mbyIsICJ2YWxpZGF0ZV9maXJtd2FyZV9pbWFnZSIgXSwKCQkJCSJ1Y2kiOiBbICJjaGFuZ2VzIiwgImdldCIgXQoJCQl9LAoJCQkidWNpIjogWyAiKiIgXQoJCX0sCgkJIndyaXRlIjogewoJCQkiY2dpLWlvIjogWyAidXBsb2FkIiBdLAoJCQkiZmlsZSI6IHsKCQkJCSIvZGF0YS93ZWJfY3VzdG9tSW1nLyoiOiBbICJ3cml0ZSIgXSwKCQkJCSIvZXRjL2Nyb250YWJzL3Jvb3QiOiBbICJ3cml0ZSIgXSwKCQkJCSIvZXRjL2Ryb3BiZWFyL2F1dGhvcml6ZWRfa2V5cyI6IFsgIndyaXRlIiBdLAoJCQkJIi9ldGMvaW5pdC5kL2ZpcmV3YWxsIHJlc3RhcnQiOiBbICJleGVjIiBdLAoJCQkJIi9ldGMvbHVjaS11cGxvYWRzLyoiOiBbICJ3cml0ZSIgXSwKCQkJCSIvZXRjL3JjLmxvY2FsIjogWyAid3JpdGUiIF0sCgkJCQkiL2V0Yy9zeXN1cGdyYWRlLmNvbmYiOiBbICJ3cml0ZSIgXSwKCQkJCSIvc2Jpbi9ibG9jayI6IFsgImV4ZWMiIF0sCgkJCQkiL3NiaW4vZmlyc3Rib290IjogWyAiZXhlYyIgXSwKCQkJCSIvc2Jpbi9pZmRvd24iOiBbICJleGVjIiBdLAoJCQkJIi9zYmluL2lmdXAiOiBbICJleGVjIiBdLAoJCQkJIi9zYmluL3JlYm9vdCI6IFsgImV4ZWMiIF0sCgkJCQkiL3NiaW4vc3lzdXBncmFkZSI6IFsgImV4ZWMiIF0sCgkJCQkiL3NiaW4vd2lmaSI6IFsgImV4ZWMiIF0sCgkJCQkiL2Jpbi9raWxsIjogWyAiZXhlYyIgXSwKCQkJCSIvYmluL3RhciI6IFsgImV4ZWMiIF0sCgkJCQkiL2Jpbi91bW91bnQiOiBbICJleGVjIiBdLAoJCQkJIi90bXAvYmFja3VwLnRhci5neiI6IFsgIndyaXRlIiBdLAoJCQkJIi90bXAvZmlybXdhcmUuYmluIjogWyAid3JpdGUiIF0sCgkJCQkiL3RtcC91cGxvYWQuaXBrIjogWyAid3JpdGUiIF0sCgkJCQkiL3Vzci9zYmluL2lwdGFibGVzIC1aIjogWyAiZXhlYyIgXSwKCQkJCSIvdXNyL3NiaW4vaXA2dGFibGVzIC1aIjogWyAiZXhlYyIgXQoJCQl9LAoJCQkidWJ1cyI6IHsKCQkJCSJmaWxlIjogWyAid3JpdGUiLCAicmVtb3ZlIiwgImV4ZWMiIF0sCgkJCQkiaG9zdGFwZC4qIjogWyAiZGVsX2NsaWVudCIgXSwKCQkJCSJpd2luZm8iOiBbICJzY2FuIiBdLAoJCQkJImx1Y2kiOiBbICIqIiBdLAoJCQkJInVjaSI6IFsgImFkZCIsICJhcHBseSIsICJjb25maXJtIiwgImRlbGV0ZSIsICJvcmRlciIsICJzZXQiLCAicmVuYW1lIiBdCgkJCX0sCgkJCSJ1Y2kiOiBbICIqIiBdCgkJfQoJfSwKCSJsdWNpLWFwcC1maXJld2FsbCI6IHsKCQkiZGVzY3JpcHRpb24iOiAiR3JhbnQgYWNjZXNzIHRvIGZpcmV3YWxsIHByb2NlZHVyZXMiLAoJCSJyZWFkIjogewoJCQkiZmlsZSI6IHsKCQkJCSIvZXRjL2ZpcmV3YWxsLnVzZXIiOiBbICJyZWFkIiBdCgkJCX0sCgkJCSJ1YnVzIjogewoJCQkJImx1Y2kiOiBbICJnZXRDb25udHJhY2tIZWxwZXJzIiBdCgkJCX0sCgkJCSJ1Y2kiOiBbICJmaXJld2FsbCIgXQoJCX0sCgkJIndyaXRlIjogewoJCQkiZmlsZSI6IHsKCQkJCSIvZXRjL2ZpcmV3YWxsLnVzZXIiOiBbICJ3cml0ZSIgXSwKCQkJCSIvZXRjL2luaXQuZC9maXJld2FsbCI6IFsgImV4ZWMiIF0KCQkJfSwKCQkJInVjaSI6IFsgImZpcmV3YWxsIiBdCgkJfQoJfQp9Cg==",
    "firewall.user": "IyBUaGlzIGZpbGUgaXMgaW50ZXJwcmV0ZWQgYXMgc2hlbGwgc2NyaXB0LgojIFB1dCB5b3VyIGN1c3RvbSBpcHRhYmxlcyBydWxlcyBoZXJlLCB0aGV5IHdpbGwKIyBiZSBleGVjdXRlZCB3aXRoIGVhY2ggZmlyZXdhbGwgKHJlLSlzdGFydC4KCiMgSW50ZXJuYWwgdWNpIGZpcmV3YWxsIGNoYWlucyBhcmUgZmx1c2hlZCBhbmQgcmVjcmVhdGVkIG9uIHJlbG9hZCwgc28KIyBwdXQgY3VzdG9tIHJ1bGVzIGludG8gdGhlIHJvb3QgY2hhaW5zIGUuZy4gSU5QVVQgb3IgRk9SV0FSRCBvciBpbnRvIHRoZQojIHNwZWNpYWwgdXNlciBjaGFpbnMsIGUuZy4gaW5wdXRfd2FuX3J1bGUgb3IgcG9zdHJvdXRpbmdfbGFuX3J1bGUuCgoKIyBjbG9zZSBwb3J0IDIwLzIxLzIyLzIzLzY5LzU1NTUgZm9yIHN5c3RlbSBzZWN1cml0eQojIGNsb3NlIEZUUCBwb3J0IDIwICYgMjEgYnkgZGVmYXVsdAppcHRhYmxlcyAtSSBJTlBVVCAtcCB0Y3AgLS1kcG9ydCAyMCAtaiBEUk9QCmlwdGFibGVzIC1JIE9VVFBVVCAtcCB0Y3AgLS1zcG9ydCAyMCAtaiBEUk9QCgppcHRhYmxlcyAtSSBJTlBVVCAtcCB0Y3AgLS1kcG9ydCAyMSAtaiBEUk9QCmlwdGFibGVzIC1JIE9VVFBVVCAtcCB0Y3AgLS1zcG9ydCAyMSAtaiBEUk9QCgojIGNsb3NlIFNTSCBwb3J0IDIyIGJ5IGRlZmF1bHQKIyBpcHRhYmxlcyAtSSBJTlBVVCAtcCB0Y3AgLS1kcG9ydCAyMiAtaiBEUk9QCiMgaXB0YWJsZXMgLUkgT1VUUFVUIC1wIHRjcCAtLXNwb3J0IDIyIC1qIERST1AKCiMgY2xvc2UgVGVsbmV0IHBvcnQgMjMgYnkgZGVmYXVsdAojIGlwdGFibGVzIC1JIElOUFVUIC1wIHRjcCAtLWRwb3J0IDIzIC1qIERST1AKIyBpcHRhYmxlcyAtSSBPVVRQVVQgLXAgdGNwIC0tc3BvcnQgMjMgLWogRFJPUAoKIyBjbG9zZSB0ZnRwIHBvcnQgNjkgYnkgZGVmYXVsdAppcHRhYmxlcyAtSSBJTlBVVCAtcCB0Y3AgLS1kcG9ydCA2OSAtaiBEUk9QCmlwdGFibGVzIC1JIE9VVFBVVCAtcCB0Y3AgLS1zcG9ydCA2OSAtaiBEUk9QCgojIGNsb3NlIGFkYiBwb3J0IDU1NTUgYnkgZGVmYXVsdAppcHRhYmxlcyAtSSBJTlBVVCAtcCB0Y3AgLS1kcG9ydCA1NTU1IC1qIERST1AKaXB0YWJsZXMgLUkgT1VUUFVUIC1wIHRjcCAtLXNwb3J0IDU1NTUgLWogRFJPUAoKIyBCbG9jayBNUVRUIHBob25lLWhvbWUKaXB0YWJsZXMgLUkgT1VUUFVUIC1kIGdsb2JlLW1xdHQudGhlMTAxLmNsb3VkIC1qIERST1AKaXB0YWJsZXMgLUkgT1VUUFVUIC1wIHRjcCAtLWRwb3J0IDg4ODMgLWogRFJPUAppcHRhYmxlcyAtSSBPVVRQVVQgLXAgdGNwIC0tZHBvcnQgMTg4MyAtaiBEUk9QCg==",
}

# Files that harden.sh expects to find in /tmp before it runs.
BINARY_FILES = ["dtoken.lua", "devmode", "luci-base.json", "firewall.user"]

DONE_MARKER = "__OPENLINE_DONE__"


def embedded_bytes(name):
    """Return the decoded bytes of an embedded file."""
    return base64.b64decode(EMBEDDED_B64[name])


def embedded_text(name):
    """Return the decoded text of an embedded file (UTF-8)."""
    return embedded_bytes(name).decode("utf-8")


# ── Terminal prompts (work even through `curl | python3 -`) ───────────────
# When the script itself is piped into python, sys.stdin is the script, not the
# keyboard. So read interactive answers from the controlling terminal (/dev/tty)
# when we can, and fall back to stdin (Windows / no tty).

def _read_line(prompt):
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(prompt)
            tty.flush()
            return tty.readline()
    except OSError:
        try:
            return input(prompt) + "\n"
        except EOFError:
            return ""


def ask_yes_no(question, default=False):
    """Ask a yes/no question. Returns a bool. Empty answer -> *default*."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        ans = _read_line(question + suffix).strip().lower()
    except KeyboardInterrupt:
        return False
    if not ans:
        return default
    return ans in ("y", "yes")


# ── ubus helpers ─────────────────────────────────────────────────────────

class UbusAccessDenied(RuntimeError):
    """Raised when ubus reports a permission / method error (status != 0)."""


def ubus_call(router_ip, session_id, obj, method, params=None, timeout=20):
    """Make a standard ubus 'call' (object.method) and return the parsed
    JSON-RPC response. Raises UbusAccessDenied on a non-zero ubus status."""
    if params is None:
        params = {}
    sid = session_id if session_id else "00000000000000000000000000000000"

    body = json.dumps({
        "jsonrpc": "2.0",
        "method": "call",
        "params": [sid, obj, method, params],
        "id": None,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"http://{router_ip}/ubus/",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode())

    if "error" in data:
        raise UbusAccessDenied(f"ubus error: {data['error']}")

    result = data.get("result", [])
    if isinstance(result, list) and len(result) > 0 and result[0] not in (0, None):
        raise UbusAccessDenied(f"ubus returned status {result[0]} "
                               f"for {obj}.{method}")
    return data


def ubus_login(router_ip, username, password):
    """Log into the router via ubus and return the session token."""
    data = ubus_call(router_ip, None, "session", "login", {
        "username": username,
        "password": password,
    })
    result = data["result"]
    if len(result) < 2 or not result[1]:
        raise RuntimeError(f"{username} login failed - wrong password?")
    return result[1]["ubus_rpc_session"]


def ubus_file_write(router_ip, sid, path, data, mode=None):
    """Write *data* (str) to *path* on the router via ubus file.write."""
    params = {"path": path, "data": data}
    if mode is not None:
        params["mode"] = mode
    ubus_call(router_ip, sid, "file", "write", params)


def ubus_file_read(router_ip, sid, path):
    """Read *path* from the router via ubus file.read. Returns str ("" if
    the file does not exist yet)."""
    try:
        data = ubus_call(router_ip, sid, "file", "read", {"path": path})
    except UbusAccessDenied:
        return ""
    result = data.get("result", [])
    if len(result) > 1 and isinstance(result[1], dict):
        return result[1].get("data", "") or ""
    return ""


def ubus_file_exec(router_ip, sid, command, params=None, timeout=60):
    """Run *command* with argv *params* via ubus file.exec.
    Returns dict {code, stdout, stderr}."""
    call_params = {"command": command}
    if params:
        call_params["params"] = params
    data = ubus_call(router_ip, sid, "file", "exec", call_params,
                     timeout=timeout)
    result = data.get("result", [])
    if len(result) > 1 and isinstance(result[1], dict):
        return result[1]
    return {}


# ── Preflight ──────────────────────────────────────────────────────────────

def preflight_reachable(router_ip, port=80, timeout=4):
    """Return True if the router's web port is reachable right now."""
    try:
        with socket.create_connection((router_ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_firmware(router_ip, sid):
    """Read /etc/jytl-version over ubus and return the version string, or
    None if it can't be read/parsed. Tries file.read first, then file.exec
    (cat) as a fallback - on the target device at least one works."""
    import re
    text = ubus_file_read(router_ip, sid, "/etc/jytl-version")
    if not text:
        try:
            out = ubus_file_exec(router_ip, sid, "/bin/cat",
                                 ["/etc/jytl-version"], timeout=15)
            text = out.get("stdout", "") or ""
        except UbusAccessDenied:
            text = ""
    if not text:
        return None
    m = re.search(r'"version"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(r"option software_version '([^']+)'", text)
    if m:
        return m.group(1)
    return None


def check_compatibility(router_ip, sid, force=False):
    """Hard compatibility gate. Runs BEFORE any risky change (PLMN unlock /
    hardening) so a non-technical user never has to check the firmware by hand.

    - firmware matches        -> proceed
    - firmware clearly differs -> stop (unless --force)
    - firmware can't be read   -> stop and ask for explicit confirmation
    """
    print("[*] Checking this is the supported router...")
    fw = detect_firmware(router_ip, sid)

    if fw == DEFAULT_VERSION:
        print(f"      ✅  firmware {fw} - supported, continuing")
        return fw

    if fw is None:
        print("      ⚠️  Could not read the firmware version from this device.")
        print("      This tool is ONLY safe on the Globe AT HOME 5G WIFI "
              f"(rain101/the101), firmware {DEFAULT_VERSION}.")
        if force:
            print("      --force given - continuing without confirmation.")
            return None
        if ask_yes_no("      Are you SURE this is that exact router and want "
                      "to continue?", default=False):
            return None
        raise RuntimeError(
            "Stopped - couldn't confirm this is the supported router.\n"
            "  Running on the wrong device can brick it. If you are certain "
            "it's the right one, re-run with --force."
        )

    # fw is known but does NOT match.
    print(f"      ❌  This router reports firmware {fw!r}.")
    print(f"      This tool ONLY supports {DEFAULT_VERSION} - other versions "
          "can brick the device.")
    if force:
        print("      --force given - proceeding against a MISMATCH (risky).")
        return fw
    raise RuntimeError(
        f"Stopped - firmware {fw} is not supported (need {DEFAULT_VERSION}).\n"
        "  Nothing was changed on the modem. If you really know what you're "
        "doing, re-run with --force."
    )


# ── Phase 1: openline over ubus (admin -> root -> unlock) ──────────────────

def gain_root(router_ip, admin_pw, root_pw, force=False):
    """Log in as admin, set + log in as root. Returns (root_sid, root_pw)."""
    print("[1/6] Logging in as admin...")
    admin_sid = ubus_login(router_ip, "admin", admin_pw)
    print(f"      ✅  admin session {admin_sid[:12]}...")

    # Earliest possible safety check: if the admin session can already read the
    # version and it clearly doesn't match, bail out before changing anything.
    early_fw = detect_firmware(router_ip, admin_sid)
    if early_fw and early_fw != DEFAULT_VERSION and not force:
        raise RuntimeError(
            f"Stopped - firmware {early_fw} is not supported "
            f"(need {DEFAULT_VERSION}). Nothing was changed. Re-run with "
            "--force only if you are certain."
        )

    print("[2/6] Setting root password...")
    try:
        ubus_call(router_ip, admin_sid, "luci", "setPassword", {
            "username": "root",
            "password": root_pw,
        })
        print("      ✅  root password set")
    except UbusAccessDenied as e:
        print(f"      ℹ️  root password may already be set ({e})")

    print("[3/6] Logging in as root...")
    try:
        root_sid = ubus_login(router_ip, "root", root_pw)
    except RuntimeError:
        print("      trying fallback root passwords...")
        for pw in [root_pw, "root123", "admin123", admin_pw]:
            try:
                root_sid = ubus_login(router_ip, "root", pw)
                root_pw = pw
                break
            except RuntimeError:
                continue
        else:
            raise RuntimeError(
                "Cannot log in as root. The admin password may lack permission "
                "to set the root password, or the router is locked down."
            )
    print(f"      ✅  root session {root_sid[:12]}...")
    return root_sid, root_pw


def enable_dropbear(router_ip, root_sid):
    """Best-effort: start dropbear + enable password auth so the user can SSH
    in later with the root password. Never fatal."""
    print("[4/6] Enabling SSH (dropbear) for later manual access...")
    try:
        ubus_call(router_ip, root_sid, "luci", "setInitAction",
                  {"name": "dropbear", "action": "start"})
    except UbusAccessDenied:
        pass
    try:
        ubus_call(router_ip, root_sid, "uci", "set", {
            "config": "dropbear", "section": "@dropbear[0]", "type": "dropbear",
            "values": {"PasswordAuth": "on", "RootPasswordAuth": "on"},
        })
        ubus_call(router_ip, root_sid, "uci", "commit", {"config": "dropbear"})
        print("      ✅  dropbear: PasswordAuth + RootPasswordAuth = on")
    except UbusAccessDenied:
        print("      ℹ️  PasswordAuth deferred (harden.sh sets it too)")
    try:
        ubus_call(router_ip, root_sid, "luci", "setInitAction",
                  {"name": "dropbear", "action": "enable"})
    except UbusAccessDenied:
        pass


def remove_plmn_lock(router_ip, root_sid):
    print("[5/6] Removing PLMN carrier lock...")
    try:
        ubus_call(router_ip, root_sid, "mtk.cell", "set_plmn_unlock", {})
        print("      ✅  PLMN lock removed - modem accepts any SIM")
    except UbusAccessDenied as e:
        print(f"      ⚠️  PLMN unlock: {e}")


# ── Phase 2a: harden over ubus (no SSH) ────────────────────────────────────

def exec_available(router_ip, root_sid):
    """Probe whether the ACL lets us run file.exec."""
    try:
        out = ubus_file_exec(router_ip, root_sid, "/bin/echo",
                             ["OPENLINE_PROBE"], timeout=15)
        return "OPENLINE_PROBE" in (out.get("stdout") or "")
    except UbusAccessDenied:
        return False


def harden_via_ubus(router_ip, root_sid, root_pw):
    """Push embedded files and run harden.sh entirely over ubus.
    Returns True on success."""
    print("[6/6] Hardening the router (over ubus, no SSH needed)...")

    # 1. Push the pre-patched binaries + the hardening script into /tmp.
    print("      pushing embedded files...")
    for name in BINARY_FILES:
        ubus_file_write(router_ip, root_sid, f"/tmp/{name}", embedded_text(name))
        print(f"        /tmp/{name}")
    ubus_file_write(router_ip, root_sid, "/tmp/harden.sh",
                    embedded_text("harden.sh"))
    print("        /tmp/harden.sh")

    # 2. Run harden.sh DETACHED. It restarts rpcd near the end, which kills
    #    ubus sessions and any process still parented to rpcd - so we detach
    #    with setsid and tee output to a log we poll separately.
    runner = (
        "rm -f /tmp/harden.log; "
        "( setsid /bin/sh /tmp/harden.sh >/tmp/harden.log 2>&1; "
        f"echo {DONE_MARKER}$? >>/tmp/harden.log ) >/dev/null 2>&1 & "
        "echo STARTED"
    )
    print("      starting hardening routine...")
    ubus_file_exec(router_ip, root_sid, "/bin/sh", ["-c", runner], timeout=30)

    # 3. Poll /tmp/harden.log, re-logging in whenever rpcd restart drops our
    #    session, until we see the done marker (or time out).
    print("      ---- harden.sh output ----")
    sid = root_sid
    printed = 0
    deadline = time.time() + 180
    done = False
    while time.time() < deadline:
        try:
            log = ubus_file_read(router_ip, sid, "/tmp/harden.log")
        except (UbusAccessDenied, urllib.error.URLError, OSError):
            log = None

        if log is None:
            # rpcd/uhttpd likely bouncing - wait and get a fresh session.
            time.sleep(2)
            try:
                sid = ubus_login(router_ip, "root", root_pw)
            except Exception:
                pass
            continue

        if len(log) > printed:
            chunk = log[printed:]
            # indent router output under our own
            for line in chunk.splitlines():
                print(f"      | {line}")
            printed = len(log)

        if DONE_MARKER in log or "Hardening Complete" in log:
            done = True
            break
        time.sleep(1.5)

    print("      ---------------------------")
    if done:
        print("      ✅  hardening complete")
    else:
        print("      ⚠️  hardening did not report completion within 180s "
              "(it may still have finished - check the web UI)")
    return done


def reboot_via_ubus(router_ip, root_pw):
    """Re-login (session was likely dropped by the service restarts) and
    reboot the router."""
    try:
        sid = ubus_login(router_ip, "root", root_pw)
    except Exception:
        return False
    try:
        ubus_file_exec(router_ip, sid, "/sbin/reboot", [], timeout=10)
    except Exception:
        try:
            ubus_call(router_ip, sid, "system", "reboot", {})
        except Exception:
            return False
    return True


# ── Phase 2b: SSH fallback (only if file.exec is blocked) ──────────────────

def harden_via_ssh(router_ip, root_pw, ssh_key_path):
    """Classic fallback: install an SSH key via ubus, then run harden.sh over
    SSH. Needs an `ssh` client (and ssh-keygen). Returns True on success."""
    import subprocess
    import tempfile

    print("      ⚠️  file.exec is blocked by the router's ACL.")
    print("      Falling back to the SSH path (needs an ssh client).")

    pubkey_path = ssh_key_path + ".pub"
    # Generate a key if we don't have one.
    if not os.path.exists(ssh_key_path):
        try:
            os.makedirs(os.path.dirname(ssh_key_path), exist_ok=True)
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", ssh_key_path,
                 "-N", "", "-C", "openline@rain101"],
                check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"      ❌  ssh-keygen failed ({e}). Cannot use SSH fallback.")
            print("      Run harden.sh manually after SSHing in.")
            return False
    with open(pubkey_path) as f:
        pubkey = f.read().strip()

    # Re-login (previous session may be stale) and install the key.
    try:
        sid = ubus_login(router_ip, "root", root_pw)
        ubus_file_write(router_ip, sid, "/etc/dropbear/authorized_keys",
                        pubkey + "\n")
        ubus_file_write(router_ip, sid, "/tmp/user_ssh_key.pub", pubkey + "\n")
        ubus_call(router_ip, sid, "luci", "setInitAction",
                  {"name": "dropbear", "action": "restart"})
    except Exception as e:
        print(f"      ❌  could not install SSH key via ubus ({e}).")
        return False
    time.sleep(2)

    ssh_base = ["ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "PreferredAuthentications=publickey",
                "-o", "ConnectTimeout=10", "-i", ssh_key_path,
                f"root@{router_ip}"]
    subprocess.run(["ssh-keygen", "-R", router_ip], capture_output=True)

    # Push embedded files, then pipe harden.sh over SSH.
    try:
        for name in BINARY_FILES:
            subprocess.run(ssh_base + [f"cat > /tmp/{name}"],
                           input=embedded_bytes(name),
                           capture_output=True, timeout=20, check=True)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh",
                                          delete=False) as tf:
            tf.write(embedded_text("harden.sh"))
            tmp_sh = tf.name
        with open(tmp_sh) as stdin_f:
            result = subprocess.run(ssh_base + ["sh -s"], stdin=stdin_f,
                                    capture_output=True, text=True, timeout=180)
        os.unlink(tmp_sh)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        print(f"      ❌  SSH hardening failed ({e}).")
        return False


# ── Orchestration ──────────────────────────────────────────────────────────

def run(router_ip, admin_pw, root_pw, ssh_key_path, assume_yes=False,
        force=False):
    print("=" * 60)
    print("  openline + harden - rain101 / the101")
    print("=" * 60)
    print(f"  Router: {router_ip}")
    print()

    # Preflight: are we actually on the router's network?
    if not preflight_reachable(router_ip):
        raise RuntimeError(
            f"Can't reach the router at {router_ip}.\n"
            "  • Connect this device's Wi-Fi to the router's network.\n"
            "  • Turn OFF mobile data (so traffic goes over Wi-Fi).\n"
            "  • If your router uses a different IP, pass --router <ip>.\n"
            "  Then run this again."
        )

    root_sid, root_pw = gain_root(router_ip, admin_pw, root_pw, force=force)

    # Hard compatibility gate - runs BEFORE any risky change (PLMN unlock /
    # hardening). The user never has to check the firmware by hand.
    check_compatibility(router_ip, root_sid, force=force)

    enable_dropbear(router_ip, root_sid)
    remove_plmn_lock(router_ip, root_sid)

    # Phase 2: harden. Prefer the pure-ubus path; fall back to SSH.
    if exec_available(router_ip, root_sid):
        ok = harden_via_ubus(router_ip, root_sid, root_pw)
    else:
        ok = harden_via_ssh(router_ip, root_pw, ssh_key_path)

    # Done.
    print()
    print("=" * 60)
    print("  ALL DONE" if ok else "  FINISHED (with warnings)")
    print("=" * 60)
    print(f"  Web UI:  http://{router_ip}   (user: admin)")
    print(f"  SSH:     ssh root@{router_ip}   # password: {root_pw}")
    print()
    print("  ⚠️  A reboot makes the hardening fully effective.")

    do_reboot = assume_yes or ask_yes_no("  Reboot the router now?",
                                         default=False)
    if do_reboot:
        if reboot_via_ubus(router_ip, root_pw):
            print("  Rebooting - give it ~60 seconds.")
        else:
            print(f"  Couldn't reboot automatically. Run: "
                  f"ssh root@{router_ip} reboot")
    else:
        print(f"  Skipped. Reboot later with: ssh root@{router_ip} reboot")

    print()
    print("🎉  Your the101 router is openline and hardened.")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Openline + harden the rain101/the101 router "
                    "(self-contained; needs only Python on the primary path).")
    parser.add_argument("--router", default="192.168.0.1",
                        help="Router IP (default: 192.168.0.1)")
    parser.add_argument("--root-pw", default="root123",
                        help="Root password to set (default: root123)")
    parser.add_argument("--admin-pw", default=None,
                        help="Admin web password (else THE101_ADMIN_PW env, "
                             "else you'll be prompted)")
    parser.add_argument("--ssh-key",
                        default=os.path.expanduser("~/.ssh/openline_rain101"),
                        help="SSH private key path (only used if the router "
                             "blocks file.exec and we fall back to SSH)")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Reboot at the end without asking")
    parser.add_argument("--force", action="store_true",
                        help="Override the compatibility gate and run even if "
                             "the firmware doesn't match (ADVANCED - risks "
                             "bricking a non-matching device)")
    args = parser.parse_args()

    admin_pw = args.admin_pw or os.environ.get("THE101_ADMIN_PW")
    if not admin_pw:
        print("The admin password is printed on the sticker underneath the "
              "router.")
        try:
            admin_pw = getpass.getpass("Admin web password: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        if not admin_pw:
            print("No password entered - aborting.", file=sys.stderr)
            sys.exit(1)

    try:
        run(args.router, admin_pw, args.root_pw, args.ssh_key,
            assume_yes=args.yes, force=args.force)
    except RuntimeError as e:
        print(f"\n❌  {e}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError:
        print(f"\n❌  Cannot reach router at {args.router} - check you're on "
              f"its Wi-Fi and mobile data is off.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
