#!/usr/bin/env python3
"""Add a bring-up debug hook to the s5k5e8 driver: force a raw GPIO level
before power-on, so the standby pin can be exercised without DT changes."""
import os
import subprocess

K = "/home/user/kbuild/src-714"
SRC = "/home/user/tools/s5k5e8.c"
WORK = "/home/user/s5mod"

s = open(SRC).read()

if "force_gpio" not in s:
    # module params next to reset_mode
    anchor = 'MODULE_PARM_DESC(reset_mode, "0=assert+release, 1=release only, 2=assert only");'
    add = anchor + """

static int force_gpio = -1;
module_param(force_gpio, int, 0644);
MODULE_PARM_DESC(force_gpio, "bring-up: raw GPIO number to drive before power-on");

static int force_level;
module_param(force_level, int, 0644);
MODULE_PARM_DESC(force_level, "bring-up: level for force_gpio (0/1)");"""
    assert anchor in s
    s = s.replace(anchor, add, 1)

    # drive it at the start of power_on
    anchor2 = "static int s5k5e8_power_on(struct s5k5e8 *s5k5e8)\n{\n\tint ret;\n"
    add2 = anchor2 + """
	if (force_gpio >= 0) {
		int r = gpio_request(force_gpio, "s5k5e8-force");
		if (!r) {
			gpio_direction_output(force_gpio, force_level ? 1 : 0);
			dev_err(s5k5e8->sd.dev,
				"S5K5E8: forced gpio%d = %d\\n",
				force_gpio, force_level ? 1 : 0);
		} else {
			dev_err(s5k5e8->sd.dev,
				"S5K5E8: force gpio%d request failed %d\\n",
				force_gpio, r);
		}
	}
"""
    assert anchor2 in s
    s = s.replace(anchor2, add2, 1)

os.makedirs(WORK, exist_ok=True)
open(f"{WORK}/s5k5e8.c", "w").write(s)
open(f"{WORK}/Makefile", "w").write("obj-m := s5k5e8.o\nccflags-y := -Wno-unused-variable\n")

cmd = (f"cd {K} && export PATH=/usr/lib/llvm-20/bin:$PATH && "
       f"make ARCH=arm64 LLVM=1 M={WORK} KBUILD_MODPOST_WARN=1 modules > /tmp/s5.log 2>&1 && "
       f"zstd -f -19 {WORK}/s5k5e8.ko -o {WORK}/s5k5e8.ko.zst && "
       f"ls -l {WORK}/s5k5e8.ko.zst")
r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
print(r.stdout[-400:])
if r.returncode:
    print(r.stderr[-800:])
    subprocess.run(["bash", "-c", "grep -E 'error:' /tmp/s5.log | head -8"])
