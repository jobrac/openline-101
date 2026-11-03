# Security & Audit Reference — openline-101

For reviewers who want to know **exactly what this tool changes on the device,
why, and how to verify each claim** before trusting or running it.

- Simple usage → [main README](../README.md)
- Power-user operations → [Advanced Guide](ADVANCED.md)

Everything below targets **Globe AT HOME 5G WIFI (rain101/the101), firmware
`RA_M1_v7.00.02g`, hardware V1.0** — OpenWRT 19.07-SNAPSHOT, kernel 4.19.205,
aarch64, MediaTek platform, LuCI `develop_secureboot` branch.

---

## Table of contents

- [Threat model / intent](#threat-model--intent)
- [How the unlock works](#how-the-unlock-works)
- [How the hardening works](#how-the-hardening-works)
- [Enabled after unlock](#enabled-after-unlock)
- [Disabled / removed after hardening](#disabled--removed-after-hardening)
- [Backdoor SSH keys removed](#backdoor-ssh-keys-removed)
- [TR-069 ACS (killed)](#tr-069-acs-killed)
- [Phone-home services (killed)](#phone-home-services-killed)
- [Serial console (hardware path)](#serial-console-hardware-path)
- [Key API endpoints](#key-api-endpoints)
- [Files the tool reads and writes](#files-the-tool-reads-and-writes)
- [Verification commands](#verification-commands)
- [Residual risks / notes](#residual-risks--notes)

---

## Threat model / intent

This tool is for an **owner** taking full control of **their own** carrier-locked
router. It does two things:

1. **Openline** — removes the carrier/SIM (PLMN) lock so the modem accepts any SIM.
2. **Harden** — removes the manufacturer/carrier's remote-management channel and
   the leftover factory backdoors, so the owner (not Globe/Rain) controls the device.

The "unlock" relies on credentials/flows already present in the firmware
(password formulas, a developer mode, and an unauthenticated `session.login`),
not on a remote exploit. Everything runs over the LAN.

---

## How the unlock works

1. **Unauthenticated `ubus session.login`.** The `/ubus/` endpoint accepts
   `session.login` with an all-zero session ID, so anyone on the LAN can
   authenticate as `admin`/`root` with just the password. This is how Rain's LuCI
   fork is configured (not a stock OpenWRT behavior).
2. **`luci.setPassword`.** As admin, set the root password (writes `/etc/shadow`).
3. **`luci.setInitAction`.** As root, start/enable the dropbear SSH server.
4. **`mtk.cell.set_plmn_unlock`.** Removes the carrier lock on the MediaTek modem.
5. **Password formulas are in the firmware.** Admin password = MAC-derived
   (`secret_1()`); factory root password = SHA256 of the serial number. Both
   formulas are visible in the extracted squashfs rootfs.

---

## How the hardening works

1. **TR-069 kill.** `easycwmpd` (CWMP daemon) is disabled in UCI, stopped, its
   init symlinks removed, and running processes killed. A redundant iptables DROP
   to the ACS host/port backs this up.
2. **ACL bypass via `debug_mode=99`.** `/data/jytl_factory/debug_mode=99` plus
   four fixes in `dtoken.lua`:
   - `get_debug_mode()` returned `develop_mode` (nil) instead of `debug_mode`
     (99) — a typo that made `is_debug_mode()` **always false**, dead-coding every
     bypass. Fixed.
   - `auth_ubus_acl()` checked tokens **before** `is_debug_mode()`. Bypass moved
     to the top.
   - `check_luci_acl_st()` had the same ordering bug. Fixed.
   - `get_developmode()` returns 1 immediately when `debug_mode==99`. Needed
     because the compiled `jt_system.lua` controller (polled by the Vue frontend)
     calls it and can't be edited as bytecode.
3. **rpcd ACL wildcard.** `luci-base.json` method lists replaced with `["*"]` so
   restricted methods (e.g. `getMenu`, hidden pages) are callable.
4. **Boot persistence.** `/etc/init.d/devmode` (S97devmode) recreates dev-mode
   flag files at boot; `rc.local` re-asserts `debug_mode=99` and `super_admin=1`.
5. **Geo-lock chain broken.** GPS → `mtk_agpsd` → `mnld` → cloud check → modem
   lock, cut at multiple points.
6. **Firewall persistence.** iptables rules are also written to
   `/etc/firewall.user`, loaded at boot.

> Older versions installed a `/bin/rm` wrapper to stop bytecode modules deleting
> dev-mode files; it caused web-UI login failures after reboot and has been
> removed. The revert steps still handle it if present.

---

## Enabled after unlock

| Feature | Status | Details |
|---|---|---|
| SSH root access | ✅ | Port 22, password + key auth, survives reboot |
| Dev mode (`debug_mode=99`) | ✅ | Persists; bypasses server-side ACLs |
| Hidden developer pages | ✅ | PLMN/band lock, GPS, diagnosis, net tools — directly in web UI |
| Unrestricted ubus | ✅ | All `luci.*` and `mtk.*` methods callable |
| PLMN / carrier unlock | ✅ | No SIM/carrier restriction |
| Full root filesystem | ✅ | Read/write everywhere |
| LCD touch screen | ✅ | MQTT firewalled, LCD UI keeps working |
| Local modem comms | ✅ | `atcid` still bridges to modem on localhost |

---

## Disabled / removed after hardening

| Feature | Action | Why |
|---|---|---|
| TR-069 remote management | easycwmpd stopped/disabled, rc.d links removed | Carrier can otherwise push config, lock, or reflash without consent |
| ACS phone-home | iptables DROP to `device.rain.network` + port 7548 | Backstop if TR-069 respawns |
| Manufacturer SSH keys | Developer keys deleted; only your key remains | Anyone holding the matching private key has passwordless root |
| Telnet backdoor | telnetd stopped/disabled, symlink removed | Unencrypted remote shell, weak/no auth on some firmware |
| ADB over USB | Binary renamed `adbd_usb.disabled` | Physical USB = root shell, no password |
| AT command agent | ate_agent killed; ports 17171–17172 firewalled to localhost (`atcid` kept) | Factory test listener exposed AT commands to the whole LAN |
| Geo-lock (GPS + cloud) | mnld, mtk_agpsd, jytl_gps killed | Stops location-based enforcement and tracking |
| MQTT cloud phone-home | Ports 1883/8883 + `globe-mqtt.the101.cloud` blocked | LCD telemetry to Globe's broker; LCD still works locally |
| OTA firmware checker | udpApp removed (phoned jointelli.cn + firmware.rain.network) | Could silently reflash and undo unlocks |
| Bulk data reporter | bulk_inform removed | Uploads usage, connected devices, location |
| SSL cert auto-download | cert_sync removed (FTP w/ hardcoded creds) | MITM risk over unencrypted FTP |
| iperf3 open port | iperf_service removed (5201) | Open speed-test server on LAN/WAN |
| ACL token validation | debug_mode checked first in dtoken.lua | Dev mode skips token checks |
| rpcd ACL restrictions | luci-base.json wildcarded | Unlocks restricted ubus methods |

---

## Backdoor SSH keys removed

Stock firmware ships 5–7 developer public keys in
`/etc/dropbear/authorized_keys`. Anyone with a matching private key has
passwordless root on **every** device. Hardening wipes the file; in keyless
(pure-ubus) mode it is **preserved only if** no user key was provided, to avoid
locking you out — review it manually in that case:

```bash
cat /etc/dropbear/authorized_keys
```

---

## TR-069 ACS (killed)

| Property | Value |
|---|---|
| ACS URL | `https://device.rain.network:7548/tr069/ServiceHandle` |
| Inform interval | every 3600s (1 hour) |

---

## Phone-home services (killed)

| Service | Init script | Phones home to | Purpose |
|---|---|---|---|
| `udpApp` | S70udpApp | jointelli.cn, firmware.rain.network | OTA firmware check + download |
| `bulk_inform` | S70bulk_inform | Rain servers | Bulk telemetry upload |
| `cert_sync` | S99cert_sync | apk.jointelli.com (FTP) | SSL cert download w/ hardcoded creds |
| `iperf_service` | S99iperf_service | open port 5201 | iperf3 speed-test server |
| `littlevgl` (MQTT) | LCD driver | globe-mqtt.the101.cloud:8883 | MQTT cloud link — firewalled, LCD kept alive |

---

## Serial console (hardware path)

```
console::respawn:/sbin/getty -L ttyS0 921600 -t 60 vt100
```

A physical UART at 921600 baud gives an immediate root shell — a hardware access
path requiring no software unlock (open the case, attach a UART adapter).

---

## Key API endpoints

| Endpoint | Auth required | Purpose |
|---|---|---|
| `POST /ubus/` `session.login` | Password only | Authenticate as any user, no prior session |
| `POST /ubus/` `luci.setPassword` | Admin session | Change any user's password |
| `POST /ubus/` `luci.setInitAction` | Root session | Start/enable/disable init services |
| `POST /ubus/` `mtk.cell.set_plmn_unlock` | Root session | Remove carrier lock |
| `POST /ubus/` `file.write` | Root session | Write a file on the device |
| `POST /ubus/` `file.exec` | Root session | Run a command (primary harden path) |
| `POST /ubus/` `luci.getMenu` | Session + ACL | Full menu tree incl. hidden pages |
| `POST /cgi-bin/luci/admin/jt_system/set_local_system_upgrade` | Session | Firmware upgrade |

---

## Files the tool reads and writes

**Pushed to the router (into `/tmp`, then installed by `harden.sh`):**
`dtoken.lua`, `devmode`, `luci-base.json`, `firewall.user`, `harden.sh`.

**Modified on the device:**

| Path | Change |
|---|---|
| `/etc/shadow` | root password set (via `luci.setPassword`) |
| `/etc/dropbear/authorized_keys` | cleaned (key mode) or preserved (keyless) |
| `/usr/lib/lua/luci/dtoken.lua` | replaced with patched version (`.orig` backup) |
| `/usr/lib/lua/luci/model/functions/api_system.lua` | wrapped to honor `debug_mode=99` (`.luac.bak` backup) |
| `/usr/share/rpcd/acl.d/luci-base.json` | wildcard ACL (`.bak` backup) |
| `/etc/init.d/devmode`, `/etc/rc.d/S97devmode` | added (boot persistence) |
| `/etc/firewall.user` | MQTT/ACS/AT firewall rules |
| `/etc/property.json` | `super_admin=1`, TR-069 flags |
| `/data/jytl_factory/debug_mode` | set to `99` |
| `/etc/rc.local` | persistence block appended |
| `/etc/config/dropbear` (UCI) | PasswordAuth/RootPasswordAuth on |
| `/etc/config/easycwmp` (UCI) | TR-069 disabled |

Backups (`.orig` / `.bak`) are created before overwriting; see
[Reverting all changes](ADVANCED.md#reverting-all-changes).

---

## Verification commands

Run these over SSH after hardening to confirm each claim:

```bash
# Dev mode / ACL bypass
cat /data/jytl_factory/debug_mode                      # -> 99
grep -q 'DEBUG MODE BYPASS' /usr/lib/lua/luci/dtoken.lua && echo PATCHED || echo ORIGINAL

# TR-069 dead
ls /etc/rc.d/S90easycwmpd 2>/dev/null || echo "TR-069 symlink gone"
pgrep easycwmpd || echo "easycwmpd not running"

# Backdoors
pgrep telnetd || echo "telnet dead"
ls /sbin/adbd_usb 2>/dev/null || echo "ADB disabled"
wc -l < /etc/dropbear/authorized_keys                  # review key count

# Phone-home services
for s in udpApp bulk_inform cert_sync iperf_service; do
  ls /etc/init.d/$s 2>/dev/null || echo "$s removed"
done

# Firewall blocks present
iptables -S OUTPUT | grep -E '7548|1883|8883' || echo "no cloud blocks (check firewall.user loaded)"
iptables -S INPUT  | grep -E '17171|17172'   || echo "AT ports not firewalled yet"

# super_admin flag
grep super_admin /etc/property.json
```

---

## Residual risks / notes

- **`session.login` remains open** on this firmware — it's the mechanism the tool
  relies on. Anyone on the LAN who knows (or can derive) the password can do the
  same. Rain may patch it in future firmware.
- **Root password defaults to `root123`** — change it (`passwd`) immediately.
- **Key-auth caution** — with SSH key auth enabled, anyone holding the private
  key has root. Keep it safe; use your own key path.
- **Not reset/upgrade-proof** — a factory reset or firmware upgrade restores stock
  files and re-enables the carrier channel and backdoors.
- **AT ports 17171–17172** are reachable from localhost only (the modem bridge
  `atcid` needs them); they are dropped from the LAN.
- **The `rm` wrapper** (older versions) logged blocked deletes to syslog under tag
  `RM_BLOCK`; it is no longer installed.
