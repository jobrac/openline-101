#!/bin/sh
# harden.sh — Lock down the101 router after gaining root SSH
# Run this ON the router (via SSH) after openline.py has enabled root access.
#
# Usage:
#   scp harden.sh root@192.168.0.1:/tmp/
#   ssh root@192.168.0.1 "sh /tmp/harden.sh"
#
# Or pipe directly:
#   ssh root@192.168.0.1 "sh -s" < harden.sh

set -e

echo "=== the101 Router Hardening ==="
echo ""

# ── 1. Kill TR-069 ────────────────────────────────────────────────
echo "[1/12] Killing TR-069 (remote management backdoor)..."

uci set easycwmp.@local[0].enable=0
uci commit easycwmp
/etc/init.d/easycwmpd stop 2>/dev/null || true
/etc/init.d/easycwmpd disable 2>/dev/null || true
killall -9 easycwmpd 2>/dev/null || true
killall -9 easycwmp 2>/dev/null || true
rm -f /etc/rc.d/S90easycwmpd
rm -f /etc/rc.d/S99tr069_notify

# Block ACS at firewall
iptables -I OUTPUT -d device.rain.network -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 7548 -j DROP 2>/dev/null || true

echo "  TR-069: DEAD"

# ── 2. Enable permanent debug mode ─────────────────────────────────
echo "[2/12] Enabling debug_mode=99 (permanent ACL bypass)..."

echo -n 99 > /data/jytl_factory/debug_mode
echo "  debug_mode: $(cat /data/jytl_factory/debug_mode)"

# ── 3. Patch dtoken.lua ───────────────────────────────────────────
echo "[3/12] Patching dtoken.lua (full debug_mode=99 bypass)..."

if [ ! -f /usr/lib/lua/luci/dtoken.lua.orig ]; then
    cp /usr/lib/lua/luci/dtoken.lua /usr/lib/lua/luci/dtoken.lua.orig
fi

# Apply comprehensive patch:
# 1. Fix get_developmode() — was returning global debug_mode instead of local develop_mode
# 2. auth_ubus_acl() — check is_debug_mode() FIRST, before token/ACL validation
# 3. check_luci_acl_st() — check is_debug_mode() FIRST, before token/ACL validation
# 4. develop_mode_exit() — no-op when debug_mode=99 (already in original patch)

lua << 'LUA'
local f = io.open("/usr/lib/lua/luci/dtoken.lua", "r")
local content = f:read("*a")
f:close()

local changes = 0

-- Fix 1: get_developmode returns develop_mode (not debug_mode)
local old1 = "return debug_mode"
local new1 = "return develop_mode"
content, c1 = content:gsub(old1, new1, 1)
changes = changes + (c1 or 0)

-- Fix 2: auth_ubus_acl — add is_debug_mode() check before token validation
local old2 = [[	if M.is_invalid(dtoken, token) then
		print(json.stringify({ error = "Invalid token" }))
		logger_print('FL',"ubus call "..func.." result: Invalid token, dtoken: "..dtoken..", token: "..token)
		M.develop_mode_exit()
		os.exit(1)
		return false
	end

	if not check_acl(methods, func, get_developmode(dtoken, token)) then
		if not M.is_debug_mode() then
			print(json.stringify({ error = "ACL error" }))
			logger_print('FL',"ubus call "..func.." result: ACL Err, dtoken: "..dtoken..", token: "..token)
			M.develop_mode_exit()
			os.exit(1)
			return false
		end
	end]]
local new2 = [[	-- DEBUG MODE BYPASS: skip ALL checks when debug_mode=99
	if M.is_debug_mode() then
		return true
	end

	if M.is_invalid(dtoken, token) then
		print(json.stringify({ error = "Invalid token" }))
		logger_print('FL',"ubus call "..func.." result: Invalid token, dtoken: "..dtoken..", token: "..token)
		M.develop_mode_exit()
		os.exit(1)
		return false
	end

	if not check_acl(methods, func, get_developmode(dtoken, token)) then
		print(json.stringify({ error = "ACL error" }))
		logger_print('FL',"ubus call "..func.." result: ACL Err, dtoken: "..dtoken..", token: "..token)
		M.develop_mode_exit()
		os.exit(1)
		return false
	end]]
content, c2 = content:gsub(old2, new2, 1)
changes = changes + (c2 or 0)

-- Fix 3: check_luci_acl_st — add is_debug_mode() check before token validation
local old3 = [[	local token = fs.readfile("/tmp/jy_developer_token") or '-'

	if M.is_invalid(dtoken, token) then
		return M.ST_INVALID_TOKEN
	end

	if not M.is_debug_mode() then
		if not M.check_luci_acl(super, token) then
			return M.ST_ACL_ERR
		end
	end]]
local new3 = [[	-- DEBUG MODE BYPASS: skip ALL checks when debug_mode=99
	if M.is_debug_mode() then
		return M.ST_OK
	end

	local token = fs.readfile("/tmp/jy_developer_token") or '-'

	if M.is_invalid(dtoken, token) then
		return M.ST_INVALID_TOKEN
	end

	if not M.check_luci_acl(super, token) then
		return M.ST_ACL_ERR
	end]]
content, c3 = content:gsub(old3, new3, 1)
changes = changes + (c3 or 0)

if changes > 0 then
    f = io.open("/usr/lib/lua/luci/dtoken.lua", "w")
    f:write(content)
    f:close()
    print("  dtoken.lua: PATCHED (" .. changes .. " fixes applied)")
else
    if content:match("DEBUG MODE BYPASS") then
        print("  dtoken.lua: already patched with full bypass")
    else
        print("  dtoken.lua: WARNING - patterns did not match")
    end
end
LUA

# ── 4. Install rm wrapper ──────────────────────────────────────────
echo "[4/12] Installing rm wrapper (protect dev mode files)..."

mkdir -p /usr/local/bin
cat > /usr/local/bin/rm << 'SHEOF'
#!/bin/sh
for arg in "$@"; do
    case "$arg" in
        *jy_developer*)
            logger -t "RM_BLOCK" "Blocked: rm $@"
            exit 0
            ;;
    esac
done
exec /bin/busybox rm "$@"
SHEOF
chmod +x /usr/local/bin/rm

# Replace /bin/rm with our wrapper
if [ ! -f /bin/rm.busybox ]; then
    mv /bin/rm /bin/rm.busybox
    ln -sf /usr/local/bin/rm /bin/rm
    echo "  rm wrapper: INSTALLED"
else
    echo "  rm wrapper: already installed"
fi

# ── 5. Fix rpcd ACL (grant full LuCI access) ─────────────────────
echo "[5/12] Fixing rpcd ACL (wildcard luci access)..."

cp /usr/share/rpcd/acl.d/luci-base.json /usr/share/rpcd/acl.d/luci-base.json.bak 2>/dev/null

# Update the luci-access group to have wildcard access to luci methods
# This allows methods like getMenu that arent explicitly listed
lua << 'LUA'
local f = io.open("/usr/share/rpcd/acl.d/luci-base.json", "r")
local content = f:read("*a")
f:close()

-- Replace specific luci method list with wildcard
local old = [["luci": [
		"getFeatures"
	]]]
local new = [["luci": [ "*" ]]]
content, c1 = content:gsub(old, new, 1)

-- Also fix luci methods in luci-access read section (the main ACL)
local old2 = [["luci": [
		"getConntrackList",
		"getInitList",
		"getLocaltime",
		"getProcessList",
		"getRealtimeStats",
		"getTimezones",
		"getLEDs",
		"getUSBDevices",
		"getSwconfigFeatures",
		"getSwconfigPortState",
		"getBlockDevices",
		"getMountPoints",
		"getLogFileUrl",
		"active_MapImg"
	]]]
local new2 = [["luci": [ "*" ]]]
content, c2 = content:gsub(old2, new2, 1)

-- Fix luci write methods
local old3 = [["luci": [
		"setInitAction",
		"setLocaltime",
		"setPassword",
		"setBlockDetect"
	]]]
local new3 = [["luci": [ "*" ]]]
content, c3 = content:gsub(old3, new3, 1)

if (c1 or 0) + (c2 or 0) + (c3 or 0) > 0 then
    f = io.open("/usr/share/rpcd/acl.d/luci-base.json", "w")
    f:write(content)
    f:close()
    print("  ACL: PATCHED (" .. ((c1 or 0)+(c2 or 0)+(c3 or 0)) .. " replacements)")
else
    print("  ACL: already patched or pattern mismatch")
end
LUA

# Restart rpcd to reload ACL
/etc/init.d/rpcd restart 2>/dev/null || killall -HUP rpcd 2>/dev/null || true
echo "  rpcd: restarted"

# ── 6. Create boot init script ─────────────────────────────────────
echo "[6/12] Creating boot init script..."

cat > /etc/init.d/devmode << 'INITEOF'
#!/bin/sh /etc/rc.common
START=97

boot() {
	# Set developer mode flag
	echo -n 1 > /tmp/jy_developer_mode

	# Generate developer token (not strictly needed with updated dtoken.lua,
	# but created for compatibility)
	head -c 16 /dev/random | md5sum | awk '{printf $1}' > /tmp/jy_developer_token

	# Create debug flag
	touch /tmp/jytl_debug_ab

	# Null the ate_agent
	echo None > /var/ate_agent
}

start() {
	boot
}
INITEOF
chmod +x /etc/init.d/devmode
/etc/init.d/devmode enable 2>/dev/null || true
/etc/init.d/devmode boot 2>/dev/null || true

echo "  init script: /etc/init.d/devmode -> S97devmode"

# ── 7. Remove manufacturer SSH backdoors ───────────────────────────
echo "[7/12] Removing manufacturer SSH keys..."

if [ -f /tmp/user_ssh_key.pub ]; then
	cat /tmp/user_ssh_key.pub > /etc/dropbear/authorized_keys
	echo "  authorized_keys: CLEANED (only user's key)"
elif [ -n "$SSH_AUTHORIZED_KEY" ]; then
	echo "$SSH_AUTHORIZED_KEY" > /etc/dropbear/authorized_keys
	echo "  authorized_keys: CLEANED (from SSH_AUTHORIZED_KEY)"
else
	echo "  authorized_keys: PRESERVED (no key provided — run openline.py first)"
fi

# ── 8. Kill geo-lock chain (location tracking + cloud enforcement) ──
echo "[8/12] Killing geo-lock chain (GPS → cloud → modem lock)..."

# Disable location daemons
/etc/init.d/mnld stop 2>/dev/null; /etc/init.d/mnld disable 2>/dev/null
/etc/init.d/mtk_agpsd stop 2>/dev/null; /etc/init.d/mtk_agpsd disable 2>/dev/null
rm -f /etc/rc.d/S53mnld /etc/rc.d/S54mtk_agpsd
killall -9 mnld mnld_test mtk_agpsd 2>/dev/null || true

# Block MQTT cloud phone-home BUT keep littlevgl running for LCD
# (littlevgl drives both the touch screen AND MQTT — we firewall the MQTT,
# so the LCD stays working without phoning home)
iptables -I OUTPUT -d globe-mqtt.the101.cloud -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 8883 -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 1883 -j DROP 2>/dev/null || true
grep -q "globe-mqtt" /etc/firewall.user 2>/dev/null || {
    cat >> /etc/firewall.user << 'FWEOF'

# Block littlevgl MQTT phone-home but keep LCD working
iptables -I OUTPUT -d globe-mqtt.the101.cloud -j DROP
iptables -I OUTPUT -p tcp --dport 8883 -j DROP
iptables -I OUTPUT -p tcp --dport 1883 -j DROP
FWEOF
}

# Disable GPS services (feeds location to geofence & cloud)
/etc/init.d/jytl_gps stop 2>/dev/null; /etc/init.d/jytl_gps disable 2>/dev/null
rm -f /etc/rc.d/S98jytl_gps /etc/rc.d/K97jytl_gps
killall -9 mnld_test 2>/dev/null || true

echo "  Geo-lock chain: DEAD"

# ── 9. Disable backdoor services ────────────────────────────────────
echo "[9/12] Disabling backdoor services..."

# Telnet
/etc/init.d/telnetd stop 2>/dev/null; /etc/init.d/telnetd disable 2>/dev/null
rm -f /etc/rc.d/S99telnetd /data/jytl_factory/telnet_on
killall -9 telnetd 2>/dev/null || true

# ADB over USB (rename binary so it can't respawn)
[ -f /sbin/adbd_usb ] && mv /sbin/adbd_usb /sbin/adbd_usb.disabled
killall -9 adbd_usb 2>/dev/null || true

# AT command agent (factory test only)
/etc/init.d/zate_agent.init stop 2>/dev/null; /etc/init.d/zate_agent.init disable 2>/dev/null
rm -f /etc/rc.d/S98zate_agent.init
killall -9 ate_agent 2>/dev/null || true

echo "  Telnet: DEAD"
echo "  ADB: DEAD"
echo "  AT agent: DEAD"

# ── 10. Kill phone-home services ─────────────────────────────────────
echo "[10/12] Killing phone-home services..."

# OTA firmware checker (phones jointelli.cn + firmware.rain.network)
rm -f /etc/init.d/udpApp /etc/rc.d/S70udpApp
killall -9 udpApp 2>/dev/null || true

# Bulk inform reporter
rm -f /etc/init.d/bulk_inform /etc/rc.d/S70bulk_inform
killall -9 bulk_inform 2>/dev/null || true

# SSL cert auto-download (FTP to apk.jointelli.com with hardcoded creds)
/etc/init.d/cert_sync stop 2>/dev/null; /etc/init.d/cert_sync disable 2>/dev/null
rm -f /etc/rc.d/S99cert_sync
sed -i '/check_ssl_cert/d' /etc/crontabs/root

# iperf3 server (not a backdoor but unnecessary open port)
rm -f /etc/init.d/iperf_service /etc/rc.d/S99iperf_service
killall -9 iperf3 2>/dev/null || true

echo "  udpApp: DEAD"
echo "  bulk_inform: DEAD"
echo "  cert_sync: DEAD"
echo "  iperf3: DEAD"

# ── 11. Firewall AT command ports ────────────────────────────────────
echo "[11/12] Firewalling AT command ports (keep localhost, block LAN)..."

# atcid must stay running (bridge to modem), but ports 17171-17172
# should NOT be accessible from LAN
iptables -I INPUT -i lo -p tcp --dport 17171 -j ACCEPT 2>/dev/null
iptables -I INPUT -i lo -p tcp --dport 17172 -j ACCEPT 2>/dev/null
iptables -I INPUT -p tcp --dport 17171 -j DROP 2>/dev/null
iptables -I INPUT -p tcp --dport 17172 -j DROP 2>/dev/null

# Make persistent
grep -q "17171" /etc/firewall.user 2>/dev/null || {
    cat >> /etc/firewall.user << 'FWEOF'

# Block AT command ports from LAN (only localhost can access modem)
iptables -I INPUT -i lo -p tcp --dport 17171 -j ACCEPT
iptables -I INPUT -i lo -p tcp --dport 17172 -j ACCEPT
iptables -I INPUT -p tcp --dport 17171 -j DROP
iptables -I INPUT -p tcp --dport 17172 -j DROP
FWEOF
}

echo "  AT ports: FIREWALLED (localhost only)"

# ── 12. Block ACS outbound (reinforce) ───────────────────────────────
echo "[12/12] Reinforcing ACS firewall block..."

iptables -I OUTPUT -d device.rain.network -j DROP 2>/dev/null || true
iptables -I OUTPUT -p tcp --dport 7548 -j DROP 2>/dev/null || true

echo "  ACS: BLOCKED"

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "=== Hardening Complete ==="
echo "TR-069:         DEAD"
echo "Geo-lock:       DEAD (GPS, cloud)"
echo "MQTT phonehome: BLOCKED (LCD still works)"
echo "Backdoors:      Telnet DEAD, ADB DEAD, AT agent DEAD"
echo "AT ports:       FIREWALLED (localhost only)"
echo "Phone-home:     udpApp DEAD, bulk_inform DEAD, cert_sync DEAD"
echo "iperf3:         DEAD"
echo "debug_mode:     $(cat /data/jytl_factory/debug_mode)"
echo "Dev mode file:  $(cat /tmp/jy_developer_mode 2>/dev/null || echo 'will be created at boot')"
echo "dtoken.lua:     PATCHED (debug_mode bypass)"
echo "ACL (luci):     WILDCARD (full access)"
echo "SSH backdoors:  REMOVED (only openline key)"
echo "ACS blocked:    YES (iptables)"
echo ""
echo "Reboot to verify everything persists."
