#!/bin/sh
# push.sh — Push pre-patched binaries to a rain101/the101 router
# For firmware RA_M1_v7.00.02g ONLY.
#
# Usage:
#   cd binaries/RA_M1_v7.00.02g
#   ./push.sh [router_ip] [ssh_key]
#
# Defaults: router=192.168.0.1, key=~/.ssh/openline_rain101

ROUTER="${1:-192.168.0.1}"
KEY="${2:-$HOME/.ssh/openline_rain101}"
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $KEY"

echo "Pushing pre-patched files to $ROUTER..."
echo ""

# Copy files to /tmp on router
echo "Copying files..."
$SSH "root@$ROUTER" "cat > /tmp/dtoken.lua" < dtoken.lua
$SSH "root@$ROUTER" "cat > /tmp/devmode" < devmode
$SSH "root@$ROUTER" "cat > /tmp/luci-base.json" < luci-base.json
$SSH "root@$ROUTER" "cat > /tmp/firewall.user" < firewall.user

# Run the install
echo "Installing..."
$SSH "root@$ROUTER" "cat > /tmp/install.sh && sh /tmp/install.sh" < install.sh

echo ""
echo "Done. Log into http://$ROUTER with your admin password."
