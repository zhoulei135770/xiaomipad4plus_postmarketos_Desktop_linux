#!/usr/bin/env python3
"""Regenerate the unpatched ipa_power.c from our patched copy and emit a
clean unified diff (a real patch that can be sent upstream)."""
import subprocess

K = "/home/user/kbuild/src-714"
SRC = f"{K}/drivers/net/ipa/ipa_power.c"
s = open(SRC).read()

# reverse the three edits
orig = s.replace("\tu32 core_rate;\n", "", 1)
orig = orig.replace("	power->core_rate = data->core_clock_rate;\n", "", 1)

orig = orig.replace("	/* IPA-CLOCK-ORDER-FIX: rate is set after enable */\n",
                    """	ret = clk_set_rate(clk, data->core_clock_rate);
	if (ret) {
		dev_err(dev, "error %d setting core clock rate to %u\\n",
			ret, data->core_clock_rate);
		goto err_clk_put;
	}

""", 1)

orig = orig.replace("""
	/* IPA-CLOCK-ORDER-FIX: RPM clocks ignore set_rate while disabled */
	if (!ret) {
		int r = clk_set_rate(power->core, power->core_rate);

		if (r)
			dev_warn(power->dev, "core clk set_rate failed %d\\n", r);
	}
""", "", 1)

open("/tmp/ipa_power_orig.c", "w").write(orig)
open("/tmp/ipa_power_new.c", "w").write(s)

r = subprocess.run(["diff", "-u",
                    "--label", "a/drivers/net/ipa/ipa_power.c",
                    "--label", "b/drivers/net/ipa/ipa_power.c",
                    "/tmp/ipa_power_orig.c", "/tmp/ipa_power_new.c"],
                   capture_output=True, text=True)
open("/tmp/ipa-clock-order.patch", "w").write(r.stdout)
print(r.stdout)
