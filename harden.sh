#!/bin/sh
# harden.sh — Lock down the101 router after gaining root SSH
# Run this ON the router (via SSH) after openline.py has enabled root access.
#
# Usage:
#   ssh root@192.168.0.1 "sh -s" < harden.sh
#
# Or openline.py copies pre-patched files to /tmp first, then pipes this.

set -e

echo "=== the101 Router Hardening ==="
echo ""

ok()   { echo "  OK: $*"; }
fail() { echo "  FAIL: $*"; }
skip() { echo "  SKIP: $*"; }

BIN=/tmp

# ── 1. Kill TR-069 ────────────────────────────────────────────────
echo "[1/10] Killing TR-069..."
uci set easycwmp.@local[0].enable=0 2>/dev/null || true
uci commit easycwmp 2>/dev/null || true
/etc/init.d/easycwmpd stop 2>/dev/null || true
/etc/init.d/easycwmpd disable 2>/dev/null || true
killall -9 easycwmpd easycwmp 2>/dev/null || true
rm -f /etc/rc.d/S90easycwmpd /etc/rc.d/S99tr069_notify 2>/dev/null
iptables -I OUTPUT -d device.rain.network -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 7548 -j DROP 2>/dev/null || true
ok "TR-069 disabled"

# ── 2. Enable debug_mode=99 + super_admin=1 ───────────────────────
echo "[2/10] Enabling debug_mode=99 + super_admin..."
mkdir -p /data/jytl_factory
printf '99' > /data/jytl_factory/debug_mode
[ "$(cat /data/jytl_factory/debug_mode)" = "99" ] && ok "debug_mode=99" || fail "debug_mode"
sed -i 's/"super_admin": "0"/"super_admin": "1"/' /etc/property.json 2>/dev/null || true
grep -q '"super_admin": "1"' /etc/property.json && ok "super_admin=1" || true

# ── 3. Install pre-patched files (if available) ────────────────────
echo "[3/10] Installing pre-patched files..."

# Clean any leftover restore-cron jobs from previous troubleshooting
sed -i '/dtoken.lua/d' /etc/crontabs/root 2>/dev/null || true

if [ -f "$BIN/dtoken.lua" ]; then
    [ ! -f /usr/lib/lua/luci/dtoken.lua.orig ] && cp /usr/lib/lua/luci/dtoken.lua /usr/lib/lua/luci/dtoken.lua.orig
    cp "$BIN/dtoken.lua" /usr/lib/lua/luci/dtoken.lua
    ok "dtoken.lua"
else
    skip "dtoken.lua not in $BIN — run openline.py or copy manually"
fi

if [ -f "$BIN/devmode" ]; then
    cp "$BIN/devmode" /etc/init.d/devmode
    chmod +x /etc/init.d/devmode
    /etc/init.d/devmode enable 2>/dev/null || true
    /etc/init.d/devmode boot 2>/dev/null || true
    ok "devmode init"
else
    skip "devmode not in $BIN"
fi

if [ -f "$BIN/luci-base.json" ]; then
    [ ! -f /usr/share/rpcd/acl.d/luci-base.json.bak ] && cp /usr/share/rpcd/acl.d/luci-base.json /usr/share/rpcd/acl.d/luci-base.json.bak 2>/dev/null || true
    cp "$BIN/luci-base.json" /usr/share/rpcd/acl.d/luci-base.json
    ok "rpcd ACL"
else
    skip "luci-base.json not in $BIN"
fi

if [ -f "$BIN/firewall.user" ]; then
    cp "$BIN/firewall.user" /etc/firewall.user
    ok "firewall.user"
else
    skip "firewall.user not in $BIN"
fi

# ── 4. Remove rm wrapper (causes login issues) ────────────────────
echo "[4/10] Removing rm wrapper (if present)..."
if [ -f /bin/rm.busybox ]; then
    /bin/busybox rm -f /bin/rm
    /bin/busybox mv /bin/rm.busybox /bin/rm
    /bin/busybox rm -f /usr/local/bin/rm
    ok "rm wrapper removed"
else
    ok "rm wrapper not present"
fi

# ── 5. SSH key + password auth ────────────────────────────────────
echo "[5/10] Securing SSH configuration..."
PUBKEY_FILE=/tmp/user_ssh_key.pub
if [ -s "$PUBKEY_FILE" ]; then
    cp "$PUBKEY_FILE" /etc/dropbear/authorized_keys
    chmod 600 /etc/dropbear/authorized_keys
    ok "authorized_keys: user key only"
else
    echo "  authorized_keys: PRESERVED (no user key — skipping to avoid lockout)"
fi
uci set dropbear.@dropbear[0].PasswordAuth=on 2>/dev/null
uci set dropbear.@dropbear[0].RootPasswordAuth=on 2>/dev/null
uci commit dropbear 2>/dev/null
ok "dropbear: PasswordAuth=on, RootPasswordAuth=on (effective after reboot)"

# ── 6. Kill geo-lock ──────────────────────────────────────────────
echo "[6/10] Killing geo-lock chain..."
/etc/init.d/mnld stop 2>/dev/null; /etc/init.d/mnld disable 2>/dev/null || true
/etc/init.d/mtk_agpsd stop 2>/dev/null; /etc/init.d/mtk_agpsd disable 2>/dev/null || true
rm -f /etc/rc.d/S53mnld /etc/rc.d/S54mtk_agpsd 2>/dev/null
killall -9 mnld mnld_test mtk_agpsd 2>/dev/null || true
/etc/init.d/jytl_gps stop 2>/dev/null; /etc/init.d/jytl_gps disable 2>/dev/null || true
rm -f /etc/rc.d/S98jytl_gps /etc/rc.d/K97jytl_gps 2>/dev/null
iptables -I OUTPUT -d globe-mqtt.the101.cloud -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 8883 -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 1883 -j DROP 2>/dev/null || true
ok "geo-lock DEAD"

# ── 7. Disable backdoors ──────────────────────────────────────────
echo "[7/10] Disabling backdoor services..."
/etc/init.d/telnetd stop 2>/dev/null; /etc/init.d/telnetd disable 2>/dev/null || true
rm -f /etc/rc.d/S99telnetd /data/jytl_factory/telnet_on 2>/dev/null
killall -9 telnetd 2>/dev/null || true
[ -f /sbin/adbd_usb ] && mv /sbin/adbd_usb /sbin/adbd_usb.disabled 2>/dev/null
killall -9 adbd_usb 2>/dev/null || true
/etc/init.d/zate_agent.init stop 2>/dev/null; /etc/init.d/zate_agent.init disable 2>/dev/null || true
rm -f /etc/rc.d/S98zate_agent.init 2>/dev/null
killall -9 ate_agent 2>/dev/null || true
ok "telnet, ADB, AT agent: DEAD"

# ── 8. Kill phone-home ────────────────────────────────────────────
echo "[8/10] Killing phone-home services..."
rm -f /etc/init.d/udpApp /etc/rc.d/S70udpApp 2>/dev/null
killall -9 udpApp 2>/dev/null || true
rm -f /etc/init.d/bulk_inform /etc/rc.d/S70bulk_inform 2>/dev/null
killall -9 bulk_inform 2>/dev/null || true
/etc/init.d/cert_sync stop 2>/dev/null; /etc/init.d/cert_sync disable 2>/dev/null || true
rm -f /etc/rc.d/S99cert_sync 2>/dev/null
sed -i '/check_ssl_cert/d' /etc/crontabs/root 2>/dev/null || true
rm -f /etc/init.d/iperf_service /etc/rc.d/S99iperf_service 2>/dev/null
killall -9 iperf3 2>/dev/null || true
ok "udpApp, bulk_inform, cert_sync, iperf3: DEAD"

# ── 9. Firewall AT ports ──────────────────────────────────────────
echo "[9/10] Firewalling AT command ports..."
iptables -I INPUT -i lo -p tcp --dport 17171 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -i lo -p tcp --dport 17172 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 17171 -j DROP 2>/dev/null || true
iptables -I INPUT -p tcp --dport 17172 -j DROP 2>/dev/null || true
ok "AT ports firewalled (localhost only)"

# ── 10. Persist across reboots ────────────────────────────────────
echo "[10/10] Ensuring boot persistence..."
if ! grep -q "debug_mode" /etc/rc.local 2>/dev/null; then
    sed -i '/^exit 0$/i\
# Developer mode persistence\
mkdir -p /data/jytl_factory\
printf '\''99'\'' > /data/jytl_factory/debug_mode\
sed -i '\''s/"super_admin": "0"/"super_admin": "1"/'\'' /etc/property.json 2>/dev/null || true\
' /etc/rc.local
    ok "rc.local updated"
else
    ok "rc.local already has debug_mode"
fi

# ── Restart services + ensure devmode files ─────────────────────
echo ""
echo "Restarting services..."
/etc/init.d/rpcd restart 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true
# Create /tmp devmode files AFTER rpcd restart — the new dtoken.lua
# with bypasses is now loaded, so develop_mode_exit() won't fire.
/etc/init.d/devmode boot 2>/dev/null || true

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "=== Hardening Complete ==="
echo "TR-069:         DEAD"
echo "Geo-lock:       DEAD"
echo "MQTT phonehome: BLOCKED"
echo "Backdoors:      telnet/ADB/AT DEAD"
echo "AT ports:       FIREWALLED (localhost only)"
echo "debug_mode:     $(cat /data/jytl_factory/debug_mode 2>/dev/null || echo 'not set')"
echo "super_admin:    $(grep super_admin /etc/property.json 2>/dev/null || echo 'unknown')"
echo "dtoken.lua:     $(grep -q 'DEBUG MODE BYPASS' /usr/lib/lua/luci/dtoken.lua 2>/dev/null && echo 'PATCHED' || echo 'ORIGINAL')"
echo "SSH keys:       $(wc -l < /etc/dropbear/authorized_keys 2>/dev/null || echo 0) keys"
echo ""
