#!/usr/bin/env python3
"""Rebuild the ov13855 driver with the empirically verified BGGR mbus code."""
import os
import shutil
import subprocess

K = "/home/user/kbuild/src-714"
SRC = "/home/user/ov13855.c"
WORK = "/home/user/ovmod"

os.makedirs(WORK, exist_ok=True)
s = open(SRC).read()
n = s.count("MEDIA_BUS_FMT_SGRBG10_1X10")
s = s.replace("MEDIA_BUS_FMT_SGRBG10_1X10", "MEDIA_BUS_FMT_SBGGR10_1X10")
open(f"{WORK}/ov13855.c", "w").write(s)
print(f"replaced {n} occurrence(s) SGRBG10 -> SBGGR10")

open(f"{WORK}/Makefile", "w").write("obj-m := ov13855.o\n")

cmd = (f"cd {K} && export PATH=/usr/lib/llvm-20/bin:$PATH && "
       f"make ARCH=arm64 LLVM=1 M={WORK} modules > /tmp/ov.log 2>&1 && "
       f"ls -l {WORK}/ov13855.ko && zstd -f -19 {WORK}/ov13855.ko -o {WORK}/ov13855.ko.zst")
r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
print(r.stdout[-600:])
if r.returncode:
    print(r.stderr[-1500:])
    subprocess.run(["bash", "-c", "grep -E 'error:|Error ' /tmp/ov.log | head -10"])
