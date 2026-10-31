#!/usr/bin/env python3
"""Export a call-availability probe so a module can ask TZ whether a
(svc, cmd) pair exists."""
import subprocess

K = "/home/user/kbuild/src-714"
SCM = f"{K}/drivers/firmware/qcom/qcom_scm.c"
HDR = f"{K}/include/linux/firmware/qcom/qcom_scm.h"

FUNC = """
/** qcom_scm_is_call_available() - does TZ know this (svc, cmd) pair? */
int qcom_scm_is_call_available(u32 svc, u32 cmd)
{
	return __qcom_scm_is_call_available(__scm->dev, svc, cmd) ? 1 : 0;
}
EXPORT_SYMBOL_GPL(qcom_scm_is_call_available);
"""


def main():
    s = open(SCM).read()
    if "qcom_scm_is_call_available" not in s:
        anchor = "EXPORT_SYMBOL_GPL(qcom_scm_mp_unlock_legacy);"
        assert anchor in s
        s = s.replace(anchor, anchor + "\n" + FUNC, 1)
        open(SCM, "w").write(s)
        print("qcom_scm.c patched")
    h = open(HDR).read()
    if "qcom_scm_is_call_available" not in h:
        a = "int qcom_scm_mp_unlock_legacy(phys_addr_t phys, size_t len);"
        assert a in h
        h = h.replace(a, a + "\nint qcom_scm_is_call_available(u32 svc, u32 cmd);", 1)
        open(HDR, "w").write(h)
        print("header patched")

    cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
            "make ARCH=arm64 LLVM=1 -j8 Image > /tmp/kb6.log 2>&1 && "
            "gzip -9 -k -f arch/arm64/boot/Image && "
            "cp arch/arm64/boot/Image.gz /home/user/Image-avail.gz") % K
    subprocess.run(["bash", "-c", cmds], check=True)
    print("kernel built")


main()
