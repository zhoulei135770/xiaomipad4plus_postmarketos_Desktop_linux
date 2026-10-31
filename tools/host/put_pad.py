#!/usr/bin/env python3
"""Upload a local file to the tablet over SFTP.

Usage: put_pad.py <local_path> <remote_path>
"""
import os
import sys

import paramiko

HOST = os.environ.get("PAD_HOST", "192.168.1.29")
USER = os.environ.get("PAD_USER", "user")
PASS = os.environ.get("PAD_PASS", "<SUDO_PASSWORD>")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: put_pad.py <local> <remote>", file=sys.stderr)
        return 1
    local, remote = sys.argv[1], sys.argv[2]
    t = paramiko.Transport((HOST, 22))
    t.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(t)
    sftp.put(local, remote)
    print(f"uploaded {local} -> {remote} ({os.path.getsize(local)} bytes)")
    sftp.close()
    t.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
