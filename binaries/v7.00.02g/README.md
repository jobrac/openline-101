# Pre-patched binaries for RA_M1_v7.00.02g

Drop-in replacement files for the Globe AT HOME 5G WIFI (rain101/the101).

**WARNING: This firmware version ONLY.** Check your router's firmware before use.

## Files

| File | Router Path | Purpose |
|---|---|---|
| `dtoken.lua` | `/usr/lib/lua/luci/dtoken.lua` | Patched ACL/token module — 4 fixes applied |
| `dtoken.lua.orig` | (reference only) | Original unpatched dtoken.lua from firmware |
| `devmode` | `/etc/init.d/devmode` | Boot init script — creates developer mode flag files |
| `luci-base.json` | `/usr/share/rpcd/acl.d/luci-base.json` | rpcd ACL with wildcard luci access |
| `firewall.user` | `/etc/firewall.user` | Firewall rules blocking MQTT/ACS phone-home |

## No device-specific data

These files are **universal** — they contain no MAC addresses, serial numbers,
IMEI, passwords, SSH keys, or any device-identifying information. Safe to share.

## Quick Install

```bash
cd binaries/v7.00.02g
./push.sh [router_ip] [ssh_key_path]
```

Or manually:

```bash
# 1. Copy files to router
scp dtoken.lua devmode luci-base.json firewall.user install.sh root@192.168.0.1:/tmp/

# 2. Run installer on router
ssh root@192.168.0.1 "sh /tmp/install.sh"
```

## What the patches fix

1. **get_debug_mode()** — returned `develop_mode` (nil) instead of `debug_mode` (99). Made `is_debug_mode()` always return false.
2. **auth_ubus_acl()** — debug_mode bypass added before token validation.
3. **check_luci_acl_st()** — debug_mode bypass added before token validation.  
4. **get_developmode()** — returns 1 when debug_mode=99 (required by compiled jt_system.lua controller).

## Recovery

If something breaks, restore the original:

```bash
ssh root@192.168.0.1
cp /usr/lib/lua/luci/dtoken.lua.orig /usr/lib/lua/luci/dtoken.lua
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
```
