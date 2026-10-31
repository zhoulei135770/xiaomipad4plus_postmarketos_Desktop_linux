#!/usr/bin/env python3
"""Patch the live DTB for the front camera and build a boot image.

  * reset-gpios: gpio52 -> gpio47 (vendor cam_sensor_front_active)
  * pinctrl cam-reset2-default: pins gpio52 -> gpio47
  * add standby-gpios = <&tlmm 44 GPIO_ACTIVE_HIGH> (vendor configures gpio44 too)
"""
import re
import struct
import subprocess

K = "/home/user"
dts = open(f"{K}/live.dts").read()

# 1) reset gpio 0x34 (52) -> 0x2f (47), flags stay ACTIVE_LOW
old = "\t\t\t\t\treset-gpios = <0x29 0x34 0x01>;"
new = "\t\t\t\t\treset-gpios = <0x29 0x2f 0x01>;\n\t\t\t\t\tstandby-gpios = <0x29 0x2c 0x00>;"
assert old in dts, "reset-gpios line not found"
dts = dts.replace(old, new, 1)

# 2) pinctrl pin
old2 = '\t\t\tcam-reset2-default {\n\t\t\t\tpins = "gpio52";'
new2 = '\t\t\tcam-reset2-default {\n\t\t\t\tpins = "gpio47";'
assert old2 in dts, "pinctrl node not found"
dts = dts.replace(old2, new2, 1)

open(f"{K}/front.dts", "w").write(dts)

# compile
r = subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", f"{K}/front.dtb", f"{K}/front.dts"],
                   capture_output=True, text=True)
if r.returncode:
    print(r.stderr[-1500:])
    raise SystemExit(1)
print("dtb ok", subprocess.run(["stat", "-c", "%s", f"{K}/front.dtb"],
                                capture_output=True, text=True).stdout.strip())
