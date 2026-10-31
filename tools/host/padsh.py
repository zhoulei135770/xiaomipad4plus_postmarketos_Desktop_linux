#!/usr/bin/env python3
"""Run a local shell script on the pad over SSH (stdin -> sh -s).

Usage: python tools/padsh.py script.sh [--sudo] [--timeout N]
Env: PAD_HOST (default 192.168.1.100), PAD_USER user, PAD_PASS <SUDO_PASSWORD>
"""
import os
import sys
import time

import paramiko

HOST = os.environ.get("PAD_HOST", "192.168.1.100")
USER = os.environ.get("PAD_USER", "user")
PASS = os.environ.get("PAD_PASS", "<SUDO_PASSWORD>")


def main() -> int:
    args = [a for a in sys.argv[1:]]
    use_sudo = "--sudo" in args
    timeout = 300
    if "--timeout" in args:
        timeout = int(args[args.index("--timeout") + 1])
    args = [a for a in args if not a.startswith("--")]
    if args and args[0] == "sudo":
        use_sudo = True
        args.pop(0)
    path = args[0]
    script = open(path, "rb").read().decode("utf-8")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for attempt in range(3):
        try:
            client.connect(HOST, 22, username=USER, password=PASS, timeout=20,
                           banner_timeout=20, auth_timeout=20,
                           look_for_keys=False, allow_agent=False)
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                print(f"[ssh error] {exc}", file=sys.stderr)
                return 2
            time.sleep(3)

    remote = "sudo -S sh -s" if use_sudo else "sh -s"
    stdin, stdout, stderr = client.exec_command(remote, timeout=timeout)
    if use_sudo:
        stdin.write(PASS + "\n")
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    client.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
