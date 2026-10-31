#!/usr/bin/env python3
"""Allow empty BTF_KIND_TYPE_TAG names (newer pahole emits them), then
rebuild the kernel and produce a boot image with the ORIGINAL initramfs."""
import re
import struct
import subprocess

K = "/home/user/kbuild/src-714"
BTF = f"{K}/kernel/bpf/btf.c"
BASE_IMG = "/home/user/boot-icc3.img"
OUT_IMG = "/home/user/boot-nbtf2.img"
PAGE = 4096


def patch():
    s = open(BTF).read()
    if "EMPTY-TYPETAG-OK" in s:
        print("already patched")
        return
    old = """	} else if (BTF_INFO_KIND(t->info) == BTF_KIND_TYPE_TAG) {
		value = btf_name_by_offset(env->btf, t->name_off);
		if (!value || !value[0]) {"""
    new = """	} else if (BTF_INFO_KIND(t->info) == BTF_KIND_TYPE_TAG) {
		/* EMPTY-TYPETAG-OK: newer pahole emits empty type-tag names */
		value = btf_name_by_offset(env->btf, t->name_off);
		if (!value) {"""
    if old not in s:
        raise SystemExit("pattern not found")
    s = s.replace(old, new, 1)
    open(BTF, "w").write(s)
    print("btf.c patched (TYPE_TAG empty name allowed)")


def build():
    cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
            "make ARCH=arm64 LLVM=1 -j8 Image > /tmp/kb3.log 2>&1 && "
            "gzip -9 -k -f arch/arm64/boot/Image && "
            "cp arch/arm64/boot/Image.gz /home/user/Image-tag.gz && "
            "ls -l /home/user/Image-tag.gz") % K
    subprocess.run(["bash", "-c", cmds], check=True)


def pack():
    d = open(BASE_IMG, "rb").read()
    ks, rs, ss = (struct.unpack_from("<I", d, 8)[0],
                  struct.unpack_from("<I", d, 16)[0],
                  struct.unpack_from("<I", d, 24)[0])
    blob = d[PAGE:PAGE + ks]
    off = blob.find(bytes.fromhex("d00dfeed"))
    dtb = blob[off:]
    rd_off = PAGE + ((ks + PAGE - 1) // PAGE) * PAGE
    ramdisk = d[rd_off:rd_off + rs]
    gz = open("/home/user/Image-tag.gz", "rb").read()

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
