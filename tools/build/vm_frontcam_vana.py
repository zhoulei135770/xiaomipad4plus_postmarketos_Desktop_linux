#!/usr/bin/env python3
"""Point the front camera's VANA at the shared cam_avdd_2v8 (gpio51),
keeping the reset/standby fixes already present in the live DTB."""
import subprocess

K = "/home/user"
dts = open(f"{K}/live.dts").read()

# current live DTB already has reset=47 + standby=44 (flashed earlier);
# re-dump it first so we build on that state
subprocess.run(["bash", "-c", f"cd {K} && dtc -I dtb -O dts -o live2.dts current.dtb 2>/dev/null || true"])

src = open(f"{K}/live.dts").read()
old = "\t\t\t\t\tvana-supply = <0x93>;"
new = "\t\t\t\t\tvana-supply = <0x8e>;  /* shared cam_avdd_2v8 (gpio51) */"
assert old in src, "vana-supply 0x93 not found"
src = src.replace(old, new, 1)
open(f"{K}/front2.dts", "w").write(src)

r = subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", f"{K}/front2.dtb", f"{K}/front2.dts"],
                   capture_output=True, text=True)
if r.returncode:
    print(r.stderr[-1200:])
    raise SystemExit(1)
print("dtb written")
