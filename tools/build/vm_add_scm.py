#!/usr/bin/env python3
"""Add the SCM_SVC_MP/cmd 0x10 unlock wrapper to the working kernel tree,
rebuild, and pack a boot image with the ORIGINAL initramfs."""
import struct
import subprocess

K = "/home/user/kbuild/src-714"
SCM = f"{K}/drivers/firmware/qcom/qcom_scm.c"
HDR = f"{K}/include/linux/firmware/qcom/qcom_scm.h"
BASE_IMG = "/home/user/boot-icc3.img"
OUT_IMG = "/home/user/boot-scmp.img"
PAGE = 4096

FUNC = """
/**
 * qcom_scm_mp_unlock() - ask TZ to unlock register/memory ranges
 * @phys: physical address of the 28-byte-entry descriptor array
 * @len:  array length in bytes
 *
 * Mirrors downstream ipa3_tz_unlock_reg(): SCM_SVC_MP (0x0c), cmd 0x10,
 * three 32-bit args {phys_lo, phys_hi, len}.
 */
int qcom_scm_mp_unlock(phys_addr_t phys, size_t len)
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

	ret = qcom_scm_call(__scm->dev, &desc, &res);
	if (ret)
		return ret;

	return res.result[0];
}
EXPORT_SYMBOL_GPL(qcom_scm_mp_unlock);
"""


def patch():
    s = open(SCM).read()
    if "qcom_scm_mp_unlock" not in s:
        anchor = "EXPORT_SYMBOL_GPL(qcom_scm_io_writel);"
        assert anchor in s, "anchor missing"
        s = s.replace(anchor, anchor + "\n" + FUNC, 1)
        open(SCM, "w").write(s)
        print("qcom_scm.c patched")

    h = open(HDR).read()
    if "qcom_scm_mp_unlock" not in h:
        a = "int qcom_scm_io_writel(phys_addr_t addr, unsigned int val);"
        assert a in h, "header anchor missing"
        h = h.replace(a, a + "\n\nint qcom_scm_mp_unlock(phys_addr_t phys, size_t len);", 1)
        open(HDR, "w").write(h)
        print("header patched")


def build():
    cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
            "make ARCH=arm64 LLVM=1 -j8 Image > /tmp/kb4.log 2>&1 && "
            "gzip -9 -k -f arch/arm64/boot/Image && "
            "cp arch/arm64/boot/Image.gz /home/user/Image-scmp.gz && "
            "ls -l /home/user/Image-scmp.gz") % K
    subprocess.run(["bash", "-c", cmds], check=True)


def pack():
    d = open(BASE_IMG, "rb").read()
    ks, rs = struct.unpack_from("<I", d, 8)[0], struct.unpack_from("<I", d, 16)[0]
    blob = d[PAGE:PAGE + ks]
    off = blob.find(bytes.fromhex("d00dfeed"))
    dtb = blob[off:]
    rd_off = PAGE + ((ks + PAGE - 1) // PAGE) * PAGE
    ramdisk = d[rd_off:rd_off + rs]
    gz = open("/home/user/Image-scmp.gz", "rb").read()

    new_blob = gz + dtb
    hdr = bytearray(d[:PAGE])
    struct.pack_into("<I", hdr, 8, len(new_blob))
    struct.pack_into("<I", hdr, 16, len(ramdisk))
    img = bytearray(hdr) + new_blob
    img += b"\x00" * (-len(img) % PAGE)
    img += ramdisk
    img += b"\x00" * (-len(img) % PAGE)
    open(OUT_IMG, "wb").write(img)
    print(f"wrote {OUT_IMG} {len(img)/1048576:.2f} MiB")


patch()
build()
pack()
print("DONE")
