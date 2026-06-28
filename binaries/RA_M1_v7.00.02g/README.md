# Pre-patched files for RA_M1_v7.00.02g

Drop-in replacement files for the Globe AT HOME 5G WIFI (rain101/the101).

**WARNING: This firmware version ONLY.** Check your router's firmware before use.

## Files

| File | Router Path | Purpose |
|---|---|---|
| `dtoken.lua` | `/usr/lib/lua/luci/dtoken.lua` | Patched ACL/token module — debug_mode=99 bypass |
| `dtoken.lua.orig` | (reference only) | Original unpatched dtoken.lua from firmware |
| `devmode` | `/etc/init.d/devmode` | Boot init — sets debug_mode=99 then creates /tmp devmode files |
| `luci-base.json` | `/usr/share/rpcd/acl.d/luci-base.json` | rpcd ACL with wildcard luci access |
| `firewall.user` | `/etc/firewall.user` | Firewall rules blocking MQTT/ACS phone-home |

## What gets installed

Running `openline.py` (or `push.sh` + `install.sh`) applies these in order:

1. **dtoken.lua** — Patches 4 bugs: `get_debug_mode()` returned wrong variable, adds debug_mode=99 bypass to `auth_ubus_acl()` and `check_luci_acl_st()`, makes `get_developmode()` return 1 when debug_mode=99.
2. **devmode init** (S97devmode) — Creates `/tmp/jy_developer_mode`, `/tmp/jy_developer_token`, `/tmp/jytl_debug_ab` on boot. Sets `debug_mode=99` **before** creating the files so `develop_mode_exit()` won't delete them.
3. **luci-base.json** — Grants unauthenticated and authenticated access to all `luci.*` ubus methods.
4. **firewall.user** — Drops MQTT ports (1883, 8883) and blocks `globe-mqtt.the101.cloud`.
5. **api_system.lua wrapper** — Replaces the compiled `api_system.lua` with a source wrapper that patches `get_develop_mode()` to return `1` when `debug_mode=99`. This is the critical piece that makes hidden developer pages appear in the web UI.
6. **rc.local persistence** — Ensures `debug_mode=99`, `super_admin=1`, and `/tmp` devmode files survive reboots.
7. **DBG_MODE:yes** in `/etc/jytl-version`.

## Quick Install

```bash
cd binaries/RA_M1_v7.00.02g
./push.sh [router_ip] [ssh_key_path]
```

Or manually:

```bash
# 1. Copy files to router
scp dtoken.lua devmode luci-base.json firewall.user install.sh root@192.168.0.1:/tmp/

# 2. Run installer on router
ssh root@192.168.0.1 "sh /tmp/install.sh"
```

## Recovery

If something breaks, restore the originals:

```bash
ssh root@192.168.0.1

# Restore dtoken.lua
cp /usr/lib/lua/luci/dtoken.lua.orig /usr/lib/lua/luci/dtoken.lua

# Restore api_system.lua
cp /usr/lib/lua/luci/model/functions/api_system.luac.bak /usr/lib/lua/luci/model/functions/api_system.lua

# Restart
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
```
