#!/usr/bin/env python3
"""
openline.py — One-shot script to enable SSH root access on the rain101/the101 router.

Usage:
    python3 openline.py [--router 192.168.0.1] [--root-pw root123] [--admin-pw YOUR_PASSWORD]

After enabling SSH, connects via SSH to make dropbear config permanent and
install the SSH public key (~/.ssh/openline_rain101.pub) if it exists.

Requirements: Python 3.6+ with pexpect (python3-pexpect)
"""

import sys
import os
import json
import urllib.request
import urllib.error
import argparse
import time


# ── helpers ──────────────────────────────────────────────────────────────

def ubus_call(router_ip, session_id, obj, method, params=None):
    """Make a JSON-RPC ubus call to the router."""
    if params is None:
        params = {}
    sid = session_id if session_id else "00000000000000000000000000000000"

    body = json.dumps({
        "jsonrpc": "2.0",
        "method": "call",
        "params": [sid, obj, method, params],
        "id": None
    }).encode("utf-8")

    req = urllib.request.Request(
        f"http://{router_ip}/ubus/",
        data=body,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode())

    if "error" in data:
        raise RuntimeError(f"ubus error: {data['error']}")

    result = data.get("result", [])
    if isinstance(result, list) and len(result) > 0 and result[0] not in (0, None):
        raise RuntimeError(f"ubus returned status {result[0]}")

    return data


def get_admin_token(router_ip, admin_pw):
    """Log into the router as admin via ubus and return the session token."""
    data = ubus_call(router_ip, None, "session", "login", {
        "username": "admin",
        "password": admin_pw
    })
    result = data["result"]
    if len(result) < 2 or not result[1]:
        raise RuntimeError("Admin login failed — wrong password?")
    return result[1]["ubus_rpc_session"]


# ── main ─────────────────────────────────────────────────────────────────

def enable_ssh(router_ip, admin_pw, root_pw, ssh_key_path):
    """Main routine — enables SSH root access on the router."""

    print(f"[*] Router: {router_ip}")
    print(f"[*] Will set root password to: {root_pw}")

    # Step 1: Get admin session token
    print("[1/5] Logging in as admin via ubus...")
    admin_sid = get_admin_token(router_ip, admin_pw)
    print(f"      Admin session: {admin_sid[:16]}...")

    # Step 2: Set root password via luci.setPassword
    print("[2/5] Setting root password...")
    ubus_call(router_ip, admin_sid, "luci", "setPassword", {
        "username": "root",
        "password": root_pw
    })
    print("      Root password set.")

    # Step 3: Log in as root to get root session
    print("[3/5] Getting root session...")
    data = ubus_call(router_ip, admin_sid, "session", "login", {
        "username": "root",
        "password": root_pw
    })
    result = data["result"]
    if len(result) < 2 or not result[1]:
        raise RuntimeError("Root login failed")
    root_sid = result[1]["ubus_rpc_session"]
    print(f"      Root session: {root_sid[:16]}...")

    # Step 4: Start dropbear SSH server
    print("[4/5] Starting dropbear SSH...")
    ubus_call(router_ip, root_sid, "luci", "setInitAction", {
        "name": "dropbear",
        "action": "start"
    })
    print("      Dropbear started.")

    # Step 5: Unlock PLMN (carrier lock)
    print("[5/5] Removing PLMN carrier lock...")
    try:
        ubus_call(router_ip, root_sid, "mtk.cell", "set_plmn_unlock", {})
        print("      PLMN lock removed.")
    except RuntimeError as e:
        print(f"      PLMN: {e} (may already be unlocked)")

    print(f"\n✅  SSH should now be accessible:")
    print(f"    ssh root@{router_ip}          # password: {root_pw}")
    print()

    # ── SSH in and make config permanent ─────────────────────────────────

    print("[*] Connecting via SSH to make config permanent...")
    time.sleep(2)

    permanent_commands = [
        "uci set dropbear.@dropbear[0].PasswordAuth=on",
        "uci set dropbear.@dropbear[0].RootPasswordAuth=on",
        "uci commit dropbear",
        "/etc/init.d/dropbear enable",
        "/etc/init.d/dropbear restart",
    ]

    try:
        import pexpect
        child = pexpect.spawn(
            f'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
            f'-o PreferredAuthentications=password -o PubkeyAuthentication=no '
            f'root@{router_ip}',
            timeout=20
        )
        idx = child.expect(['password:', 'Permission denied', pexpect.EOF], timeout=10)
        if idx != 0:
            print("⚠️  SSH password prompt not received — config may not persist.")
            print(f"    Manually run: {' && '.join(permanent_commands)}")
            return

        child.sendline(root_pw)
        child.expect(['#', 'Permission denied'], timeout=10)

        for cmd in permanent_commands:
            child.sendline(cmd)
            child.expect(['#'], timeout=10)

        # Verify
        child.sendline('echo PERMANENT_OK')
        child.expect(['PERMANENT_OK'], timeout=5)
        print("✅  Dropbear config made permanent (survives reboot).")

        # Auto-generate SSH key if it doesn't exist
        pubkey_path = ssh_key_path + ".pub"
        if not os.path.exists(ssh_key_path):
            print("[*] Generating new SSH key pair (ed25519)...")
            import subprocess
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", ssh_key_path,
                 "-N", "", "-C", "openline@rain101"],
                check=True, capture_output=True
            )
            print(f"    Key generated: {ssh_key_path}")

        print("[*] Installing SSH public key...")
        with open(pubkey_path) as f:
            pubkey = f.read().strip()
        child.sendline(f"echo '{pubkey}' >> /etc/dropbear/authorized_keys")
        child.expect(['#'], timeout=5)
        # Write key to temp file so harden.sh can use it
        child.sendline(f"echo '{pubkey}' > /tmp/user_ssh_key.pub")
        child.expect(['#'], timeout=5)
        child.sendline("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        child.expect(['#'], timeout=5)
        child.sendline(f"echo '{pubkey}' > /root/.ssh/authorized_keys")
        child.expect(['#'], timeout=5)
        child.sendline("chmod 600 /root/.ssh/authorized_keys")
        child.expect(['#'], timeout=5)
        print(f"    Key installed: {ssh_key_path}")

        child.sendline('exit')
        child.close()

    except ImportError:
        print("⚠️  'pexpect' not available. SSH in manually and run:")
        for cmd in permanent_commands:
            print(f"      {cmd}")
    except Exception as e:
        print(f"⚠️  SSH setup failed ({e}). Run manually after SSH:")
        for cmd in permanent_commands:
            print(f"      {cmd}")

    print("\n🎉  Done. Your the101 router is openline.")


def main():
    parser = argparse.ArgumentParser(
        description="Enable SSH root access on rain101/the101 router"
    )
    parser.add_argument("--router", default="192.168.0.1",
                        help="Router IP (default: 192.168.0.1)")
    parser.add_argument("--root-pw", default="root123",
                        help="Root password to set (default: root123)")
    parser.add_argument("--admin-pw", default=None,
                        help="Admin web password (or set THE101_ADMIN_PW)")
    parser.add_argument("--ssh-key", default=os.path.expanduser("~/.ssh/openline_rain101"),
                        help="SSH private key path (default: ~/.ssh/openline_rain101)")
    args = parser.parse_args()

    admin_pw = args.admin_pw or os.environ.get("THE101_ADMIN_PW") or "admin123"

    try:
        enable_ssh(args.router, admin_pw, args.root_pw, args.ssh_key)
    except RuntimeError as e:
        print(f"\n❌  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\n❌  Cannot reach router at {args.router} — check connection",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
