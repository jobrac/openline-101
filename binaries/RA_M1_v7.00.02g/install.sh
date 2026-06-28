#!/bin/sh
# install.sh — Install pre-patched files onto the router
# Run this ON the router after copying the binary files to /tmp.
#
# The push.sh script does this automatically.
# For manual use: copy dtoken.lua, devmode, luci-base.json, firewall.user
# to /tmp/ first, then run this script.

set -e

SRC=/tmp
echo "=== the101 pre-patched file installer ==="
echo "Firmware: RA_M1_v7.00.02g"
echo ""

# ── 1. Install patched dtoken.lua ─────────────────────────────────
echo "[1/7] Installing patched dtoken.lua..."
if [ ! -f /usr/lib/lua/luci/dtoken.lua.orig ]; then
    cp /usr/lib/lua/luci/dtoken.lua /usr/lib/lua/luci/dtoken.lua.orig
    echo "  Backup: dtoken.lua.orig saved"
fi
cp "$SRC/dtoken.lua" /usr/lib/lua/luci/dtoken.lua
echo "  dtoken.lua: installed ($(wc -c < /usr/lib/lua/luci/dtoken.lua) bytes)"

# ── 2. Install devmode init script ────────────────────────────────
echo "[2/7] Installing devmode init script..."
cp "$SRC/devmode" /etc/init.d/devmode
chmod +x /etc/init.d/devmode
/etc/init.d/devmode enable 2>/dev/null || true
# Verify symlink was created; create manually if enable failed
if [ -L /etc/rc.d/S97devmode ]; then
    echo "  Init: S97devmode enabled and running"
else
    ln -sf ../init.d/devmode /etc/rc.d/S97devmode 2>/dev/null || true
    if [ -L /etc/rc.d/S97devmode ]; then
        echo "  Init: S97devmode symlink created manually"
    else
        echo "  Init: WARNING — could not create S97devmode symlink"
    fi
fi
/etc/init.d/devmode boot 2>/dev/null || true

# ── 3. Install rpcd ACL wildcard ──────────────────────────────────
echo "[3/7] Installing rpcd ACL wildcard..."
if [ ! -f /usr/share/rpcd/acl.d/luci-base.json.bak ]; then
    cp /usr/share/rpcd/acl.d/luci-base.json /usr/share/rpcd/acl.d/luci-base.json.bak 2>/dev/null || true
fi
cp "$SRC/luci-base.json" /usr/share/rpcd/acl.d/luci-base.json
echo "  ACL: wildcard installed"

# ── 4. Install firewall rules ─────────────────────────────────────
echo "[4/7] Installing firewall rules..."
cp "$SRC/firewall.user" /etc/firewall.user
echo "  Firewall: installed"

# ── 4b. Patch api_system.lua to respect debug_mode=99 ──────────
echo "[4b] Patching api_system.lua (get_develop_mode bypass)..."
API_SYSTEM="/usr/lib/lua/luci/model/functions/api_system.lua"
API_BAK="/usr/lib/lua/luci/model/functions/api_system.luac.bak"

if ! grep -q "is_debug_mode" "$API_SYSTEM" 2>/dev/null; then
    [ ! -f "$API_BAK" ] && cp "$API_SYSTEM" "$API_BAK"
    cat > "$API_SYSTEM" << '\''APIPATCHEOF'\''
-- api_system.lua — wrapper that patches get_develop_mode for debug_mode=99
local orig_path = "/usr/lib/lua/luci/model/functions/api_system.luac.bak"
local orig_func = loadfile(orig_path)
if not orig_func then return {} end
orig_func()
local M = _G
for part in ("luci.model.functions.api_system"):gmatch("[^.]+") do M = M[part] end
if M and type(M) == "table" and M.get_develop_mode then
    local dt = require "luci.dtoken"
    local orig_get = M.get_develop_mode
    M.get_develop_mode = function() if dt.is_debug_mode() then return 1 end; return orig_get() end
end
return M or {}
APIPATCHEOF
    echo "  api_system.lua: patched"
else
    echo "  api_system.lua: already patched"
fi

if grep -q "DBG_MODE:no" /etc/jytl-version 2>/dev/null; then
    sed -i '\''s/DBG_MODE:no/DBG_MODE:yes/'\'' /etc/jytl-version
    echo "  DBG_MODE: yes"
fi

# ── 5. Set debug_mode=99 ──────────────────────────────────────────
echo "[5/7] Setting debug_mode=99..."
mkdir -p /data/jytl_factory
printf '99' > /data/jytl_factory/debug_mode
echo "  debug_mode: $(cat /data/jytl_factory/debug_mode)"

# ── 6. Set super_admin=1 ──────────────────────────────────────────
echo "[6/7] Setting super_admin=1..."
sed -i 's/"super_admin": "0"/"super_admin": "1"/' /etc/property.json 2>/dev/null || true
grep -q '"super_admin": "1"' /etc/property.json && echo "  super_admin: 1" || echo "  super_admin: check property.json"

# ── 7. Persist across reboots ─────────────────────────────────────
echo "[7/7] Persisting across reboots..."
if ! grep -q "openline developer persistence v2" /etc/rc.local 2>/dev/null; then
    sed -i '/^exit 0$/d' /etc/rc.local
    cat >> /etc/rc.local << 'ENDOFPERSIST'
# openline developer persistence v2
mkdir -p /data/jytl_factory
printf '99' > /data/jytl_factory/debug_mode
sed -i 's/"super_admin": "0"/"super_admin": "1"/' /etc/property.json 2>/dev/null || true

# Ensure devmode /tmp files exist (fallback if init script misses them)
if [ ! -f /tmp/jy_developer_mode ]; then
    printf '1' > /tmp/jy_developer_mode
    head -c 16 /dev/urandom | md5sum | awk '{printf $1}' > /tmp/jy_developer_token
    touch /tmp/jytl_debug_ab
fi

exit 0
ENDOFPERSIST
    echo "  rc.local: updated"
else
    echo "  rc.local: already has persistence v2"
fi

# ── Restart services ───────────────────────────────────────────────
echo ""
echo "Restarting services..."
/etc/init.d/rpcd restart 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

echo ""
echo "=== Installation complete ==="
echo "Log into http://192.168.0.1 — developer pages should now appear."
