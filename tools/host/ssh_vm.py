#!/usr/bin/env python3
"""Minimal SSH runner for the build VM.

Usage: python ssh_vm.py "<remote command>"
Env overrides: VM_HOST, VM_USER, VM_PASS
"""
import os
import sys

import paramiko

HOST = os.environ.get("VM_HOST", "192.168.1.200")
USER = os.environ.get("VM_USER", "user")
PASS = os.environ.get("VM_PASS", "<VM_PASSWORD>")


def main() -> int:
    cmd = " ".join(sys.argv[1:]) or "true"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            HOST,
            username=USER,
            password=PASS,
            timeout=15,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ssh error] {exc}", file=sys.stderr)
        return 2

    stdin, stdout, stderr = client.exec_command(
        cmd, timeout=int(os.environ.get("SSH_TIMEOUT", "120"))
    )
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    if out:
        sys.stdout.buffer.write(out.encode("utf-8", "replace"))
        sys.stdout.flush()
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", "replace"))
        sys.stderr.flush()
    client.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
