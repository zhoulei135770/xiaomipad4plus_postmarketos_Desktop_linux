import os
import sys

import paramiko

HOST = os.environ.get("VM_HOST", "192.168.1.200")
USER = os.environ.get("VM_USER", "user")
PASS = os.environ.get("VM_PASS", "<VM_PASSWORD>")

local, remote = sys.argv[1], sys.argv[2]
t = paramiko.Transport((HOST, 22))
t.connect(username=USER, password=PASS)
sftp = paramiko.SFTPClient.from_transport(t)
sftp.put(local, remote)
sftp.close()
t.close()
print(f"uploaded {local} -> {remote}")
