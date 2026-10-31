#!/usr/bin/env python3
"""Fetch a file from the tablet over SFTP.

Usage: python get_pad.py <remote_path> <local_path>
"""
import os
import sys

import paramiko

HOST = os.environ.get("PAD_HOST", "192.168.1.29")
USER = os.environ.get("PAD_USER", "user")
PASS = os.environ.get("PAD_PASS", "<SUDO_PASSWORD>")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: get_pad.py <remote> <local>", file=sys.stderr)
        return 1
    remote, local = sys.argv[1], sys.argv[2]
    t = paramiko.Transport((HOST, 22))
    t.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(t)
    sftp.get(remote, local)
    size = os.path.getsize(local)
    print(f"fetched {remote} -> {local} ({size} bytes)")
    sftp.close()
    t.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
