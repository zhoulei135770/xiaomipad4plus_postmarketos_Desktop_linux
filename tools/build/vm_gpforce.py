#!/usr/bin/env python3
"""Build a tiny bring-up helper: drive one raw GPIO to a level."""
import os
import subprocess

K = "/home/user/kbuild/src-714"
WORK = "/home/user/gpforce"

SRC = r'''
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/gpio.h>
#include <linux/init.h>

static int gpio_num = 44;
module_param(gpio_num, int, 0644);
static int gpio_level;
module_param(gpio_level, int, 0644);
MODULE_PARM_DESC(gpio_num, "GPIO number to drive");
MODULE_PARM_DESC(gpio_level, "level (0/1)");

static int __init gpforce_init(void)
{
	int r = gpio_request(gpio_num, "gpforce");
	if (r) {
		pr_err("gpforce: request gpio%d failed %d\n", gpio_num, r);
		return r;
	}
	gpio_direction_output(gpio_num, gpio_level ? 1 : 0);
	pr_err("gpforce: gpio%d driven to %d\n", gpio_num, gpio_level ? 1 : 0);
	return 0;
}

static void __exit gpforce_exit(void)
{
	gpio_free(gpio_num);
	pr_err("gpforce: gpio%d released\n", gpio_num);
}

module_init(gpforce_init);
module_exit(gpforce_exit);
MODULE_LICENSE("GPL");
'''

os.makedirs(WORK, exist_ok=True)
open(f"{WORK}/gpforce.c", "w").write(SRC)
open(f"{WORK}/Makefile", "w").write("obj-m := gpforce.o\n")

cmd = (f"cd {K} && export PATH=/usr/lib/llvm-20/bin:$PATH && "
       f"make ARCH=arm64 LLVM=1 M={WORK} KBUILD_MODPOST_WARN=1 modules > /tmp/gp.log 2>&1 && "
       f"ls -l {WORK}/gpforce.ko")
r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
print(r.stdout[-300:])
if r.returncode:
    print(r.stderr[-500:])
    subprocess.run(["bash", "-c", "grep -E 'error:' /tmp/gp.log | head -6"])
