#!/usr/bin/env python3
"""Fix the previous patch: store the rate in struct ipa_power."""
import subprocess

K = "/home/user/kbuild/src-714"
POWER = f"{K}/drivers/net/ipa/ipa_power.c"

s = open(POWER).read()

# 1) add a core_rate field
if "u32 core_rate;" not in s:
    old = """struct ipa_power {
	struct device *dev;
	struct clk *core;"""
    new = """struct ipa_power {
	struct device *dev;
	struct clk *core;
	u32 core_rate;"""
    assert old in s
    s = s.replace(old, new, 1)

# 2) use power->core_rate in enable
s = s.replace("clk_set_rate(power->core, ipa->data->core_clock_rate)",
              "clk_set_rate(power->core, power->core_rate)")

# 3) remember the rate at init
if "power->core_rate = data->core_clock_rate;" not in s:
    anchor = "	power->dev = dev;\n	power->core = clk;"
    assert anchor in s
    s = s.replace(anchor, anchor + "\n	power->core_rate = data->core_clock_rate;", 1)

open(POWER, "w").write(s)
print("ipa_power.c fixed")

cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
        "make ARCH=arm64 LLVM=1 M=drivers/net/ipa KBUILD_MODPOST_WARN=1 modules > /tmp/ipamod2.log 2>&1 && "
        "ls -l drivers/net/ipa/ipa.ko") % K
subprocess.run(["bash", "-c", cmds], check=True)
print("built")
