#!/usr/bin/env python3
"""Patch the mainline IPA driver so it can get further on sdm660:
 1) ipa_power: set the core clock rate *after* enabling it (RPM clocks
    ignore set_rate while disabled).
 2) ipa_smp2p: tolerate a DT without smem-state-names (bring-up only).
"""
import re
import subprocess

K = "/home/user/kbuild/src-714"
POWER = f"{K}/drivers/net/ipa/ipa_power.c"
SMP2P = f"{K}/drivers/net/ipa/ipa_smp2p.c"


def patch_power():
    s = open(POWER).read()
    if "IPA-CLOCK-ORDER-FIX" in s:
        print("power already patched")
        return
    # remove the early set_rate from init
    old = """	ret = clk_set_rate(clk, data->core_clock_rate);
	if (ret) {
		dev_err(dev, "error %d setting core clock rate to %u\\n",
			ret, data->core_clock_rate);
		goto err_clk_put;
	}
"""
    if old not in s:
        raise SystemExit("power anchor missing")
    s = s.replace(old, "	/* IPA-CLOCK-ORDER-FIX: rate is set after enable */\n", 1)

    # set the rate right after enabling in ipa_power_enable()
    anchor = """	ret = clk_prepare_enable(power->core);
	if (ret) {
		dev_err(power->dev, "error %d enabling core clock\\n", ret);
		icc_bulk_disable(power->interconnect_count,
				 power->interconnect);
	}
"""
    add = anchor + """
	/* IPA-CLOCK-ORDER-FIX: RPM clocks ignore set_rate while disabled */
	if (!ret) {
		int r = clk_set_rate(power->core, ipa->data->core_clock_rate);

		if (r)
			dev_warn(power->dev, "core clk set_rate failed %d\\n", r);
	}
"""
    if anchor not in s:
        raise SystemExit("enable anchor missing")
    s = s.replace(anchor, add, 1)
    open(POWER, "w").write(s)
    print("ipa_power.c patched")


def patch_smp2p():
    s = open(SMP2P).read()
    if "IPA-SMP2P-SKIP" in s:
        print("smp2p already patched")
        return
    m = re.search(r"(int\s+ipa_smp2p_init\(struct ipa \*ipa, struct platform_device \*pdev, bool modem_init\)\n\{\n)", s)
    if not m:
        raise SystemExit("smp2p init not found")
    ins = ("\t/* IPA-SMP2P-SKIP: bring-up without smem-state DT nodes */\n"
           "\tdev_info(&pdev->dev, \"IPA-SMP2P-SKIP: no smp2p handshake\\n\");\n"
           "\tipa->smp2p = NULL;\n"
           "\treturn 0;\n\n")
    s = s[:m.end()] + ins + s[m.end():]
    open(SMP2P, "w").write(s)
    print("ipa_smp2p.c patched")


def build():
    cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
            "make ARCH=arm64 LLVM=1 M=drivers/net/ipa KBUILD_MODPOST_WARN=1 modules > /tmp/ipamod.log 2>&1 && "
            "ls -l drivers/net/ipa/ipa.ko") % K
    subprocess.run(["bash", "-c", cmds], check=True)


patch_power()
patch_smp2p()
build()
print("DONE")
