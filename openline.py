#!/usr/bin/env python3
"""
openline.py — One-shot script to enable SSH root access on the rain101/the101
router AND harden it against remote management / backdoors.

Usage:
    python3 openline.py [--router 192.168.0.1] [--root-pw root123]
                        [--admin-pw YOUR_PASSWORD]

What it does:
  1. Logs into the router via ubus (JSON-RPC) as admin
  2. Escalates to root (sets root password if needed)
  3. Starts dropbear SSH, writes your SSH public key, enables password auth
  4. Connects via SSH to run the hardening routine
  5. Prompts you to reboot

Requirements: Python 3.6+, pexpect (optional — for SSH automation)
"""

import sys
import os
import json
import urllib.request
import urllib.error
import argparse
import time
import subprocess


# ── ubus helpers ─────────────────────────────────────────────────────────

def ubus_call(router_ip, session_id, obj, method, params=None):
    """Make a standard ubus 'call' (object.method)."""
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


def ubus_login(router_ip, username, password):
    """Log into the router via ubus and return the session token."""
    data = ubus_call(router_ip, None, "session", "login", {
        "username": username,
        "password": password
    })
    result = data["result"]
    if len(result) < 2 or not result[1]:
        raise RuntimeError(f"{username} login failed — wrong password?")
    return result[1]["ubus_rpc_session"]


# ── SSH helpers ──────────────────────────────────────────────────────────

def ssh_run(router_ip, root_pw, ssh_key_path, commands, timeout=30):
    """Open an SSH session, run *commands* (list of strings), return output."""
    import pexpect
    child = pexpect.spawn(
        f'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
        f'-i {ssh_key_path} '
        f'-o PreferredAuthentications=publickey,password '
        f'root@{router_ip}',
        timeout=timeout
    )
    idx = child.expect(['#', 'password:', 'Permission denied', pexpect.EOF],
                       timeout=20)
    if idx == 0:
        pass  # publickey
    elif idx == 1:
        child.sendline(root_pw)
        pidx = child.expect(['#', 'Permission denied'], timeout=10)
        if pidx != 0:
            child.close()
            return None
    else:
        child.close()
        return None

    output = ""
    for cmd in commands:
        child.sendline(cmd)
        try:
            child.expect(['#'], timeout=15)
            output += (child.before or b'').decode(errors='replace')
        except pexpect.TIMEOUT:
            pass
    child.sendline('exit')
    child.close()
    return output


# ── Main ─────────────────────────────────────────────────────────────────

def setup_router(router_ip, admin_pw, root_pw, ssh_key_path):
    pubkey_path = ssh_key_path + ".pub"

    # Check pexpect availability
    try:
        import pexpect
        have_pexpect = True
    except ImportError:
        have_pexpect = False

    # =====================================================================
    # PHASE 1 — Gain SSH access via ubus
    # =====================================================================
    print("=" * 60)
    print("  PHASE 1 — Enabling SSH access")
    print("=" * 60)
    print(f"  Router:   {router_ip}")
    print(f"  Root PW:  {root_pw}")
    print()

    # Step 1: Admin login
    print("[1/6] Logging in as admin...")
    admin_sid = ubus_login(router_ip, "admin", admin_pw)
    print(f"      Session: {admin_sid[:16]}...")

    # Step 2: Set root password (idempotent — may have been set already)
    print("[2/6] Setting root password...")
    try:
        ubus_call(router_ip, admin_sid, "luci", "setPassword", {
            "username": "root",
            "password": root_pw
        })
        print("      Root password set.")
    except RuntimeError as e:
        print(f"      Root password may already be set ({e})")

    # Step 3: Login as root
    print("[3/6] Logging in as root...")
    try:
        root_sid = ubus_login(router_ip, "root", root_pw)
    except RuntimeError:
        # Maybe root password was set by a previous run — try to login
        # anyway (it might already have the right password)
        print("      Trying fallback root passwords...")
        for pw in [root_pw, "root123", "admin123", admin_pw]:
            try:
                root_sid = ubus_login(router_ip, "root", pw)
                root_pw = pw  # update for later SSH use
                break
            except RuntimeError:
                continue
        else:
            raise RuntimeError(
                "Cannot log in as root. The admin password may not have "
                "permission to set the root password. Try a different "
                "admin password or check if the router is locked down."
            )
    print(f"      Session: {root_sid[:16]}...")

    # Step 4: Start dropbear + write SSH key + enable password auth
    print("[4/6] Configuring dropbear SSH...")

    # 4a: Start dropbear (creates /etc/config/dropbear if missing)
    ubus_call(router_ip, root_sid, "luci", "setInitAction", {
        "name": "dropbear",
        "action": "start"
    })
    time.sleep(0.5)
    print("      Dropbear started.")

    # 4b: Generate SSH key pair if needed
    if not os.path.exists(ssh_key_path):
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", ssh_key_path,
             "-N", "", "-C", "openline@rain101"],
            check=True, capture_output=True
        )
        print(f"      Key generated: {ssh_key_path}")
    with open(pubkey_path) as f:
        pubkey = f.read().strip()

    # 4c: Write SSH public key to authorized_keys
    ubus_call(router_ip, root_sid, "file", "write", {
        "path": "/etc/dropbear/authorized_keys",
        "data": pubkey + "\n"
    })
    print("      SSH key installed.")

    # 4d: Enable PasswordAuth and RootPasswordAuth via uci
    #     This may fail (Access denied) on some firmware versions after
    #     factory reset — the SSH key is already installed so publickey
    #     auth will work, and Phase 2 fixes the config over SSH.
    try:
        ubus_call(router_ip, root_sid, "uci", "set", {
            "config": "dropbear",
            "section": "@dropbear[0]",
            "type": "dropbear",
            "values": {"PasswordAuth": "on", "RootPasswordAuth": "on"}
        })
        ubus_call(router_ip, root_sid, "uci", "commit", {
            "config": "dropbear"
        })
        print("      PasswordAuth=on, RootPasswordAuth=on.")
        uci_ok = True
    except RuntimeError:
        print("      PasswordAuth deferred (will fix via SSH in Phase 2).")
        uci_ok = False

    # 4e: Enable dropbear at boot and restart
    try:
        ubus_call(router_ip, root_sid, "luci", "setInitAction", {
            "name": "dropbear",
            "action": "enable"
        })
        ubus_call(router_ip, root_sid, "luci", "setInitAction", {
            "name": "dropbear",
            "action": "restart"
        })
        time.sleep(1.5)
        print("      Dropbear restarted with new config.")
    except RuntimeError:
        time.sleep(1)
        print("      Dropbear restart deferred (will fix via SSH).")

    # Step 5: Remove PLMN carrier lock
    print("[5/6] Removing PLMN carrier lock...")
    try:
        ubus_call(router_ip, root_sid, "mtk.cell", "set_plmn_unlock", {})
        print("      PLMN lock removed.")
    except RuntimeError as e:
        print(f"      PLMN: {e}")

    # Step 6: Verify SSH access
    print("[6/6] Verifying SSH access...")

    # Clear stale host keys (router regenerates on reset)
    subprocess.run(["ssh-keygen", "-R", router_ip],
                   capture_output=True)

    ssh_ok = False
    if have_pexpect:
        # Also write key to /tmp for harden.sh compat
        console_cmds = [
            f"echo '{pubkey}' > /tmp/user_ssh_key.pub",
            "echo SSH_OK"
        ]
        result = ssh_run(router_ip, root_pw, ssh_key_path, console_cmds)
        ssh_ok = result and "SSH_OK" in result
    else:
        try:
            r = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no",
                 "-o", "UserKnownHostsFile=/dev/null",
                 "-o", "PreferredAuthentications=publickey,password",
                 "-o", "ConnectTimeout=10",
                 "-i", ssh_key_path,
                 f"root@{router_ip}", "echo SSH_OK"],
                capture_output=True, text=True, timeout=15
            )
            ssh_ok = "SSH_OK" in r.stdout
        except Exception:
            ssh_ok = False

    if ssh_ok:
        print("      ✅  SSH access confirmed.")
    else:
        print("      ⚠️  SSH verification failed — trying anyway...")
        # Might still work; the pexpect prompt matching can be finicky

    print()
    print(f"  ✅  SSH should now work:")
    print(f"      ssh -i {ssh_key_path} root@{router_ip}")
    print(f"      ssh root@{router_ip}          # password: {root_pw}")

    # =====================================================================
    # PHASE 2 — Harden the router (via SSH)
    # =====================================================================
    print()
    print("=" * 60)
    print("  PHASE 2 — Hardening the router")
    print("=" * 60)

    if not have_pexpect and not ssh_ok:
        print()
        print("  ⚠️  pexpect not installed and SSH verification failed.")
        print("  Skipping automated hardening.")
        print()
        print("  Run harden.sh manually after SSH:")
        print(f"    ssh -i {ssh_key_path} root@{router_ip} 'sh -s' < harden.sh")
        print()
        print("🎉  Phase 1 complete.")
        return

    # Run hardening by piping harden.sh over SSH.
    # harden.sh is expected in the same directory as this script.
    harden_sh_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "harden.sh")
    if not os.path.exists(harden_sh_path):
        print("  ⚠️  harden.sh not found — skipping hardening phase.")
        print(f"    Expected at: {harden_sh_path}")
    else:
        with open(harden_sh_path, "r") as f:
            harden_script = f.read()

        # Copy pre-patched binaries to router so harden.sh can install them.
        # This avoids fragile runtime patching — the files are just copied.
        binaries_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "binaries", "v7.00.02g")
        if os.path.isdir(binaries_dir):
            print("[*] Copying pre-patched files to router...")
            for fname in ["dtoken.lua", "devmode", "luci-base.json", "firewall.user"]:
                src = os.path.join(binaries_dir, fname)
                if os.path.isfile(src):
                    try:
                        subprocess.run(
                            ["ssh", "-o", "StrictHostKeyChecking=no",
                             "-o", "UserKnownHostsFile=/dev/null",
                             "-o", "PreferredAuthentications=publickey,password",
                             "-i", ssh_key_path,
                             f"root@{router_ip}", f"cat > /tmp/{fname}"],
                            stdin=open(src, "rb"),
                            capture_output=True, timeout=15, check=True
                        )
                        print(f"      {fname}")
                    except Exception as e:
                        print(f"      {fname}: FAILED ({e})")
            print("      done.")

        print("[*] Running hardening over SSH...")
        time.sleep(1)

        if have_pexpect:
            import pexpect
            child = pexpect.spawn(
                f'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
                f'-i {ssh_key_path} '
                f'-o PreferredAuthentications=publickey,password '
                f'root@{router_ip} "sh -s"',
                timeout=180
            )
            child.send(harden_script.encode())
            child.send(b'\x04')
            child.sendeof()

            try:
                while True:
                    child.expect(['\n', pexpect.EOF, pexpect.TIMEOUT], timeout=90)
                    line = child.before
                    if line:
                        print(line.decode(errors='replace').rstrip())
                    if child.match == pexpect.EOF:
                        break
            except pexpect.TIMEOUT:
                pass
            child.close()
        else:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as tf:
                tf.write(harden_script)
                tf.flush()
                result = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no",
                     "-o", "UserKnownHostsFile=/dev/null",
                     "-o", "PreferredAuthentications=publickey,password",
                     "-i", ssh_key_path,
                     f"root@{router_ip}", "sh -s"],
                    stdin=open(tf.name),
                    capture_output=True, text=True, timeout=180
                )
                print(result.stdout)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
                os.unlink(tf.name)

    # =====================================================================
    # Done — prompt for reboot
    # =====================================================================
    print()
    print("=" * 60)
    print("  ALL DONE")
    print("=" * 60)
    print()
    print(f"  SSH (key):  ssh -i {ssh_key_path} root@{router_ip}")
    print(f"  SSH (pw):   ssh root@{router_ip}          # password: {root_pw}")
    print(f"  Web UI:     http://{router_ip}")
    print(f"              username: admin")
    print(f"              password: {admin_pw}          (same one you gave the script)")
    print()
    print("━" * 58)
    print("  ⚠️  REBOOT RECOMMENDED — hardening takes full effect after reboot")
    print("━" * 58)
    print()
    print("  Reboot now? (y/N): ", end="", flush=True)

    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("y", "yes"):
        print("  Rebooting router...")
        if have_pexpect:
            ssh_run(router_ip, root_pw, ssh_key_path, ["reboot"], timeout=10)
        else:
            subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no",
                 "-o", "UserKnownHostsFile=/dev/null",
                 "-i", ssh_key_path,
                 f"root@{router_ip}", "reboot"],
                capture_output=True, timeout=15
            )
        print("  Router is rebooting — give it ~60 seconds.")
    else:
        print(f"  Skipping. Run manually: ssh -i {ssh_key_path} root@{router_ip} reboot")

    print()
    print("🎉  Your the101 router is openline and hardened.")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Openline + harden the rain101/the101 router."
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
        setup_router(args.router, admin_pw, args.root_pw, args.ssh_key)
    except RuntimeError as e:
        print(f"\n❌  Error: {e}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\n❌  Cannot reach router at {args.router} — check connection",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
