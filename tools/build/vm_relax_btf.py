#!/usr/bin/env python3
"""Relax BTF name validation so distro-built modules (BTF from a newer
pahole) are accepted, and re-enable BTF so struct module sizes match."""
import re
import subprocess

K = "/home/user/kbuild/src-714"
BTF = f"{K}/kernel/bpf/btf.c"


def patch_btf_c():
    s = open(BTF).read()
    if "RELAXED-BY-BRINGUP" in s:
        print("btf.c already patched")
        return
    for fn in ("btf_name_valid_identifier", "btf_name_valid_section"):
        m = re.search(r"static bool %s\([^)]*\)\n\{.*?\n\}\n" % fn, s, re.S)
        if not m:
            print("not found:", fn)
            continue
        body = m.group(0)
        head = body.split("{")[0]
        new = head + "{\n\t/* RELAXED-BY-BRINGUP: accept any BTF name */\n\treturn true;\n}\n"
        s = s.replace(body, new, 1)
    open(BTF, "w").write(s)
    print("btf.c patched")


def enable_btf():
    subprocess.run(["bash", "-c",
                    f"cd {K} && ./scripts/config --enable DEBUG_INFO_BTF"], check=True)


def build():
    cmds = ("cd %s && export PATH=/usr/lib/llvm-20/bin:$PATH && "
            "make ARCH=arm64 LLVM=1 olddefconfig > /tmp/o22.log 2>&1 && "
            "make ARCH=arm64 LLVM=1 -j8 Image > /tmp/src714-btfrelax.log 2>&1 && "
            "gzip -9 -k -f arch/arm64/boot/Image && "
            "cp arch/arm64/boot/Image.gz /home/user/Image-relax.gz && "
            "ls -l /home/user/Image-relax.gz") % K
    subprocess.run(["bash", "-c", cmds], check=True)


patch_btf_c()
enable_btf()
build()
print("DONE")
