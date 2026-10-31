#!/usr/bin/env python3
"""Add a LEGACY-convention IPA unlock (vendor used legacy scm_call)."""
import subprocess

K = "/home/user/kbuild/src-714"
SCM = f"{K}/drivers/firmware/qcom/qcom_scm.c"
HDR = f"{K}/include/linux/firmware/qcom/qcom_scm.h"

FUNC = """
/**
 * qcom_scm_mp_unlock_legacy() - SCM_SVC_MP/0x10 using the LEGACY convention
 * @phys: physical address of the 28-byte-entry descriptor array
 * @len:  array length in bytes
 *
 * The vendor IPA driver issues this through the legacy scm_call() interface,
 * which encodes the function id differently from the SMC-64 convention that
 * mainline auto-detects on this platform.
 */
int qcom_scm_mp_unlock_legacy(phys_addr_t phys, size_t len)
{
	struct qcom_scm_desc desc = {
		.svc = QCOM_SCM_SVC_MP,
		.cmd = 0x10,
		.arginfo = QCOM_SCM_ARGS(3),
		.args[0] = lower_32_bits(phys),
		.args[1] = upper_32_bits(phys),
		.args[2] = len,
		.owner = ARM_SMCCC_OWNER_SIP,
	};
	struct qcom_scm_res res;
	int ret;

	ret = scm_legacy_call(__scm->dev, &desc, &res);
	if (ret)
		return ret;

	return res.result[0];
}
EXPORT_SYMBOL_GPL(qcom_scm_mp_unlock_legacy);
"""


def main():
    s = open(SCM).read()
    if "qcom_scm_mp_unlock_legacy" not in s:
        anchor = "EXPORT_SYMBOL_GPL(qcom_scm_mp_unlock);"
        assert anchor in s, "anchor missing"
        s = s.replace(anchor, anchor + "\n" + FUNC, 1)
        open(SCM, "w").write(s)
        print("qcom_scm.c patched (legacy variant)")

    h = open(HDR).read()
    if "qcom_scm_mp_unlock_legacy" not in h:
        a = "int qcom_scm_mp_unlock(phys_addr_t phys, size_t len);"
        assert a in h, "header anchor missing"
        h = h.replace(a, a + "\nint qcom_scm_mp_unlock_legacy(phys_addr_t phys, size_t len);", 1)
        open(HDR, "w").write(h)
        print("header patched")

    cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
            "make ARCH=arm64 LLVM=1 -j8 Image > /tmp/kb5.log 2>&1 && "
            "gzip -9 -k -f arch/arm64/boot/Image && "
            "cp arch/arm64/boot/Image.gz /home/user/Image-leg.gz") % K
    subprocess.run(["bash", "-c", cmds], check=True)
    print("kernel built")


main()
