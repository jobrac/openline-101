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
/etc/init.d/devmode boot 2>/dev/null || true
echo "  Init: S97devmode enabled and running"

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
if ! grep -q "debug_mode" /etc/rc.local 2>/dev/null; then
    sed -i '/^exit 0$/i\
# Developer mode persistence\
mkdir -p /data/jytl_factory\
printf '\''99'\'' > /data/jytl_factory/debug_mode\
sed -i '\''s/"super_admin": "0"/"super_admin": "1"/'\'' /etc/property.json 2>/dev/null || true\
' /etc/rc.local
    echo "  rc.local: updated"
else
    echo "  rc.local: already has debug_mode"
fi

# ── Restart services ───────────────────────────────────────────────
echo ""
echo "Restarting services..."
/etc/init.d/rpcd restart 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

echo ""
echo "=== Installation complete ==="
echo "Log into http://192.168.0.1 — developer pages should now appear."
