import os
import sys

import paramiko

HOST = os.environ.get("VM_HOST", "192.168.1.200")
USER = os.environ.get("VM_USER", "user")
PASS = os.environ.get("VM_PASS", "<VM_PASSWORD>")

remote, local = sys.argv[1], sys.argv[2]
t = paramiko.Transport((HOST, 22))
t.connect(username=USER, password=PASS)
sftp = paramiko.SFTPClient.from_transport(t)
size = sftp.stat(remote).st_size
print(f"downloading {remote} ({size/1024/1024:.1f} MB)")
sftp.get(remote, local)
sftp.close()
t.close()
print(f"saved {local} ({os.path.getsize(local)/1024/1024:.1f} MB)")
