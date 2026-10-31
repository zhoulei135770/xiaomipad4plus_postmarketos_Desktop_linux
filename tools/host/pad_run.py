"""Run one remote script on the pmOS pad over SSH (password auth).

Usage: python pad_run.py <local_script> [args...] [--sudo]

Uploads the script to /tmp and executes it (optionally through sudo -S).
Prints remote stdout/stderr.
"""
import os
import sys

import paramiko

HOST = os.environ.get("PAD_HOST", "192.168.1.29")
USER = os.environ.get("PAD_USER", "user")
PASS = os.environ.get("PAD_PASS", "<SUDO_PASSWORD>")

argv = sys.argv[1:]
use_sudo = "--sudo" in argv
argv = [a for a in argv if a != "--sudo"]
script = argv[0]
args = " ".join(argv[1:])

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15,
               look_for_keys=False, allow_agent=False)

remote = "/tmp/dsh_" + os.path.basename(script)
sftp = client.open_sftp()
sftp.put(script, remote)
sftp.close()

cmd = f"sh {remote} {args}"
if use_sudo:
    cmd = f"echo {PASS} | sudo -S sh {remote} {args}"

stdin, stdout, stderr = client.exec_command(cmd, timeout=int(os.environ.get("PAD_TIMEOUT", "300")))
out = stdout.read().decode("utf-8", "replace")
err = stderr.read().decode("utf-8", "replace")
print(out, end="")
if err.strip():
    print("[stderr]", err.replace(f"[sudo] password for {USER}:", "").strip(), file=sys.stderr)
client.close()
