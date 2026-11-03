# Advanced Guide - openline-101

Power-user reference for the rain101 / the101 openline. For the simple 3-step
start, see the **[main README](../README.md)**. For how it works internally and
how to verify what it changes, see the **[Security & Audit Reference](AUDIT.md)**.

> ⚠️ Everything here assumes your device matches the exact model/firmware in the
> [README's supported-device section](../README.md#supported-device--requirements).

---

## Table of contents

- [Repository layout](#repository-layout)
- [How it runs (architecture)](#how-it-runs-architecture)
- [Command-line options](#command-line-options)
- [Requirements by platform](#requirements-by-platform)
- [Finding your admin password](#finding-your-admin-password)
- [Passwords reference](#passwords-reference)
- [Developer UI (hidden pages)](#developer-ui-hidden-pages)
- [Manual API calls (no browser)](#manual-api-calls-no-browser)
- [Recovery if the web UI breaks](#recovery-if-the-web-ui-breaks)
- [Reverting all changes](#reverting-all-changes)
- [Re-enabling after a factory reset](#re-enabling-after-a-factory-reset)
- [What a factory reset wipes](#what-a-factory-reset-wipes)
- [What NOT to touch](#what-not-to-touch)
- [Rebuilding the self-contained script](#rebuilding-the-self-contained-script)
- [Building the Windows .exe](#building-the-windows-exe)
- [Adding support for a new firmware](#adding-support-for-a-new-firmware)
- [Troubleshooting](#troubleshooting)

---

## Repository layout

```
├── README.md            ← landing page / quick start
├── openline.py          ← the one self-contained tool (run this)
├── install.sh           ← Android/Mac/Linux one-liner bootstrap (finds Python)
├── install.ps1          ← Windows one-liner bootstrap (finds Python, or grabs the .exe)
├── harden.sh            ← the hardening routine (embedded into openline.py)
├── binaries/            ← pre-patched router files (embedded into openline.py)
│   └── RA_M1_v7.00.02g/
├── tools/
│   ├── build_openline.py   ← re-embeds harden.sh + binaries after you edit them
│   └── windows-build.bat   ← builds the standalone openline.exe
└── docs/
    ├── ADVANCED.md      ← this guide
    └── AUDIT.md         ← security / auditor reference
```

To run the tool you only need **`openline.py`** - everything else is embedded
inside it. The other files are for maintainers and for people who want to
understand or rebuild it.

---

## How it runs (architecture)

`openline.py` is a **single self-contained file**: `harden.sh` and the four
pre-patched binaries are base64-embedded inside it, so it can be piped straight
into `python3` with no git clone.

It has two execution paths:

1. **Primary (pure ubus / HTTP)** - standard library only. It drives the router
   entirely over `http://<router>/ubus/` using `file.write` (push files) and
   `file.exec` (run the hardening). No `ssh`, `ssh-keygen`, `scp`, or `pexpect`.
   Because `harden.sh` restarts `rpcd` near the end - which invalidates the ubus
   session - the script runs it **detached** (`setsid … >/tmp/harden.log`) and
   **re-logs-in** while polling the log until it sees the done marker.
2. **Fallback (SSH)** - used **only** if the router's ACL blocks `file.exec`.
   It installs a generated SSH key via `file.write`, then pushes files and pipes
   `harden.sh` over `ssh`. This path needs an `ssh` client and `ssh-keygen`.

The flow in both cases: **ubus login → set root password → log in as root →
enable dropbear → remove PLMN lock → push files → run harden.sh → (optional)
reboot.**

---

## Command-line options

```bash
python3 openline.py [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--router <ip>` | `192.168.0.1` | Router IP address |
| `--admin-pw <pw>` | *(prompted)* | Admin web password. If omitted, read from `THE101_ADMIN_PW`, else prompted interactively |
| `--root-pw <pw>` | `root123` | Root password to set (change it afterward!) |
| `--ssh-key <path>` | `~/.ssh/openline_rain101` | SSH key path - **only** used if the SSH fallback is triggered |
| `-y`, `--yes` | off | Reboot at the end without asking |
| `--force` | off | Override the automatic compatibility gate (see below) |

### Automatic compatibility gate

The script detects the router's firmware (via `file.read`, falling back to
`file.exec cat /etc/jytl-version`) and decides **before any risky change**:

- **matches `RA_M1_v7.00.02g`** → proceeds
- **clearly different** → stops, nothing changed
- **can't read the version** → stops and asks for explicit confirmation

`--force` skips this gate entirely. It's for maintainers testing a new
firmware; on a genuinely mismatched device it risks a brick. There's also an
even-earlier check right after admin login (before the root password is set)
that aborts on a definitive mismatch.

Non-interactive examples:

```bash
# Supply the password as a flag
python3 openline.py --admin-pw 'aB3cD5eF'

# Or via environment variable (keeps it out of shell history / argv)
export THE101_ADMIN_PW='aB3cD5eF'
python3 openline.py -y

# Different router IP
python3 openline.py --router 192.168.1.1
```

When run with no `--admin-pw` and no env var, the script prompts with
`getpass`, which reads from the terminal (not stdin) - that's why the
`curl … | python3 -` one-liner can still ask for the password interactively.

---

## Requirements by platform

The **primary path needs only Python 3.6+**. The SSH fallback additionally needs
an `ssh` client + `ssh-keygen`.

| OS | Status | Notes |
|---|---|---|
| **Linux** | ✅ | Primary dev platform (Ubuntu 22.04+, Debian 12+). |
| **macOS** | ✅ | Python 3 built in. |
| **Android (Termux)** | ✅ | `pkg install python`. Use the **F-Droid** build of Termux. |
| **Windows (native)** | ✅ | `install.ps1` or `python openline.py`. No WSL/bash needed. |
| **Windows (WSL2)** | ✅ | Works, but no longer required. |

No third-party Python packages are required - only stdlib (`urllib`, `json`,
`base64`, `getpass`, `socket`, …).

---

## Finding your admin password

The admin password is **unique per device** - derived from the router's MAC
address, not a fixed value.

In order of ease:

1. **Sticker under the router** - usually printed there.
2. **Already logged into the web UI?** - you already know it. Try `admin123`
   (hardcoded fallback) too.
3. **Router's box** - MAC is printed on it; use the last 6 hex characters.
4. **Have SSH already?** - `cat /data/jytl_factory/2g_mac` for the MAC.
5. **Derive it from the MAC** with the firmware's own formula:

```bash
# seed = "JY" + last 6 hex chars of MAC
secret_1() {
    passwd=$(echo $(echo $(echo "JY$(cat /data/jytl_factory/2g_mac | cut -b 7-12)" | md5sum)) | \
             openssl base64 | tr -d '01Ol' | tr '[o-z]' '[6-92-9]' | tr '[O-Z]' '[6-92-9]')
}
```

Example: MAC `AA11BB22CC33` → seed `JY2CC33` → password `aB3cD5eF` *(illustrative -
yours will differ)*.

After a factory reset the admin password stays the same (MAC doesn't change). If
it won't work, the `superadmin` / `developer#888` backdoor exists on factory
firmware (the hardening later removes the `super_admin` flag).

---

## Passwords reference

### Root SSH password
`openline.py` sets `root123` by default. **Change it immediately:**

```bash
ssh root@192.168.0.1
passwd
```

### Superadmin (dev mode)
If `super_admin=1` in `/etc/property.json`: username `superadmin`, password
`developer#888`. Manufacturer-provided - treat as a backdoor. Hardening removes
the flag.

### Root password from serial number (factory)
The factory root password is SHA256-derived from the serial number:

```javascript
// SHA256("{SN}+*#developer*#rain*#") → chars 1-16 + chars 49-64
async function generateHash(sn) {
    const input = sn + "+*#developer*#rain*#";
    const hashBuffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
    const hashHex = Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, "0")).join("");
    return hashHex.slice(0, 16) + hashHex.slice(48, 64);
}
```

Example: SN `RACCPHB8Q3400XXXX` → `a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6`. Only useful
on stock firmware with the original root password intact.

---

## Developer UI (hidden pages)

After hardening, developer mode is enabled via `debug_mode=99` (ACL bypass),
`super_admin=1`, the patched `dtoken.lua`, and the wildcard rpcd ACL.

Log in at `http://192.168.0.1` with your admin password; hidden pages appear
automatically if your firmware's menu includes them. If `/#/developerMode` shows
a 404, that's a Vue routing quirk - the underlying functionality is still active.

### Hidden pages reference

| Page | URL Hash | Router Path |
|---|---|---|
| PLMN Lock | `#/toolSet/plmnLock` | `/toolSet/plmnLock` |
| Band Lock | `#/toolSet/lockSpectrum` | `/toolSet/connectSetting/toolSet/lockSpectrum` |
| Developer Mode | `#/developerMode` | `/developerMode` |
| Connection Mode | `#/toolSet/connectSetting` | - |
| Network Selection | `#/toolSet/netSelect` | - |
| GPS | `#/advancedSet/system/advancedSet/gps` | - |
| Diagnosis | `#/advancedSet/system/advancedSet/diag` | - |
| Network Tools | `#/advancedSet/system/advancedSet/netTool` | - |

---

## Manual API calls (no browser)

Because `debug_mode=99` bypasses server-side ACLs, you can call ubus directly:

```bash
# 1. Get a session token
TOKEN=$(curl -s http://192.168.0.1/ubus/ \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":["00000000000000000000000000000000","session","login",{"username":"admin","password":"YOUR_PASSWORD"}],"id":1}' | \
  jq -r '.result[1].ubus_rpc_session')

# 2. PLMN unlock
curl -s http://192.168.0.1/ubus/ \
  -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"params\":[\"$TOKEN\",\"mtk.cell\",\"set_plmn_unlock\",{}],\"id\":1}"

# 3. Get hidden menu items
curl -s http://192.168.0.1/ubus/ \
  -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"params\":[\"$TOKEN\",\"luci\",\"getMenu\",{}],\"id\":1}"
```

See the [API endpoints table](AUDIT.md#key-api-endpoints) in the audit doc for
the full list.

---

## Recovery if the web UI breaks

If the web UI returns 403 on all requests after hardening, a mismatched
`dtoken.lua` may have been applied. SSH in and restore:

```bash
ssh root@192.168.0.1

# Clear stuck dev-mode token files
/bin/busybox rm -f /tmp/jy_developer_token /tmp/jy_developer_mode

# Or restore the original dtoken.lua from the backup the script made
cp /usr/lib/lua/luci/dtoken.lua.orig /usr/lib/lua/luci/dtoken.lua
/etc/init.d/rpcd restart
```

If hidden pages stop showing: `/etc/init.d/devmode boot` recreates the
`/tmp/jy_developer_*` files the frontend controller polls for.

---

## Reverting all changes

Restore stock behavior (assumes the `.orig`/`.bak` backups the script made are
present):

```bash
ssh root@192.168.0.1 << 'EOF'
# Restore original dtoken.lua
cp /usr/lib/lua/luci/dtoken.lua.orig /usr/lib/lua/luci/dtoken.lua

# Restore original rpcd ACL
cp /usr/share/rpcd/acl.d/luci-base.json.bak /usr/share/rpcd/acl.d/luci-base.json
/etc/init.d/rpcd restart

# Restore original rm (if a wrapper was present on older versions)
[ -f /bin/rm.busybox ] && { /bin/busybox rm -f /bin/rm; /bin/busybox mv /bin/rm.busybox /bin/rm; }

# Remove the dev-mode init script
rm -f /etc/init.d/devmode /etc/rc.d/S97devmode

# Re-enable TR-069
uci set easycwmp.@local[0].enable=1
uci commit easycwmp
/etc/init.d/easycwmpd enable

# Restore ADB binary
[ -f /sbin/adbd_usb.disabled ] && mv /sbin/adbd_usb.disabled /sbin/adbd_usb

# (Edit /etc/firewall.user to remove the added MQTT/AT blocks)
EOF
```

---

## Re-enabling after a factory reset

A reset wipes the unlock. To redo it, just run the tool again - it does openline
+ harden in one shot:

```bash
python3 openline.py --admin-pw YOUR_ADMIN_PASSWORD
```

Say `y` to reboot when prompted, then verify everything survived.

---

## What a factory reset wipes

A factory reset erases `/data` and restores the read-only rootfs from squashfs.

**Wiped:** `/data/jytl_factory/debug_mode` (ACL bypass flag),
`/etc/dropbear/authorized_keys` (your SSH key), all UCI changes (dropbear,
TR-069 flag), `/etc/firewall.user` additions, `/tmp` runtime files.

**Restored to stock:** original `dtoken.lua` (bypass broken again), original
`luci-base.json` (ACL restrictions back), original `/bin/rm`, and all init
scripts for TR-069 / telnet / ADB / phone-home services.

**Net result:** TR-069 phones home again, backdoors re-enabled, hidden pages
locked, PLMN lock possibly back, no SSH, admin password back to MAC-derived
default. If you intend to reset (selling/returning the device), run
[Reverting all changes](#reverting-all-changes) first for a clean stock state.

---

## What NOT to touch

| File | Why |
|---|---|
| `/data/jytl_factory/debug_mode` | Set to `99` - changing it disables the ACL bypass |
| `/usr/lib/lua/luci/dtoken.lua` | Patched - do not revert |
| `/usr/share/rpcd/acl.d/luci-base.json` | Patched wildcard ACL - do not revert |
| `/etc/init.d/devmode` | Recreates dev-mode files at boot |
| `/etc/property.json` | Controls TR-069 and super_admin flags |
| `/etc/firewall.user` | MQTT block + AT port firewall rules |
| `/sbin/adbd_usb.disabled` | Renamed ADB binary - do not restore |

---

## Rebuilding the self-contained script

`openline.py` embeds `harden.sh` and `binaries/<version>/*` as base64. After you
edit any of those sources, re-embed them:

```bash
python3 tools/build_openline.py
```

This replaces the `@@…@@` tokens (or the previously injected blobs) in
`openline.py` and verifies the result still compiles. Commit the regenerated
`openline.py`.

> If `build_openline.py` reports "token not found," the file was already built.
> `git checkout openline.py` to restore the token version, then rebuild - or just
> edit the sources and rebuild from a fresh checkout.

---

## Building the Windows .exe

For Windows users without Python, `install.ps1` fetches a prebuilt
`openline.exe`. Build it **once** on a Windows machine that has Python:

```bat
tools\windows-build.bat
```

It injects the embedded files, creates an isolated venv, installs PyInstaller,
and produces `dist\openline.exe`. Upload that to your GitHub Release (tag
`latest`) and point `$ExeUrl` in `install.ps1` at it.

---

## Adding support for a new firmware

1. Create `binaries/<new-version>/` with that firmware's patched
   `dtoken.lua`, `devmode`, `luci-base.json`, and `firewall.user`.
2. Point `tools/build_openline.py`'s `VERSION` at it (or extend it to embed
   multiple versions) and re-run it.
3. Update `DEFAULT_VERSION` in `openline.py` if appropriate.
4. Test on the actual hardware before publishing - the ubus methods, file paths,
   and Lua internals differ between firmware versions.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `Can't reach the router` | Not on router's Wi-Fi, or mobile data on | Reconnect Wi-Fi, mobile data OFF, `ping 192.168.0.1` |
| `login failed - wrong password` | Wrong admin password | [Find your admin password](#finding-your-admin-password); try `admin123` |
| `file.exec` blocked → SSH fallback | Router ACL restricts exec | Needs an `ssh` client; otherwise SSH in and run `harden.sh` manually |
| Hardening didn't report completion in 180s | `rpcd` restart dropped the session and re-login stalled | Usually it still finished - check the web UI; re-run if unsure |
| Hidden pages not showing | `/tmp/jy_developer_*` missing | SSH in: `/etc/init.d/devmode boot` |
| TR-069 respawns after reboot | Init symlink survived | `ls /etc/rc.d/S90easycwmpd` should be "No such file" |
| MQTT still connects right after hardening | Firewall loaded after MQTT started | Reboot - firewall loads early in boot |
