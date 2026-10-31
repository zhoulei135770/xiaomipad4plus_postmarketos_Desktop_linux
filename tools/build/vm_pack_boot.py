#!/usr/bin/env python3
"""pack_boot.py <Image.gz> <out.img> — kernel + original dtb + ramdisk."""
import struct
import sys

PAGE = 4096
BASE = "/home/user/boot-icc3.img"

gz_path, out = sys.argv[1], sys.argv[2]
d = open(BASE, "rb").read()
ks, rs = struct.unpack_from("<I", d, 8)[0], struct.unpack_from("<I", d, 16)[0]
blob = d[PAGE:PAGE + ks]
off = blob.find(bytes.fromhex("d00dfeed"))
dtb = blob[off:]
rd_off = PAGE + ((ks + PAGE - 1) // PAGE) * PAGE
ramdisk = d[rd_off:rd_off + rs]
gz = open(gz_path, "rb").read()

new_blob = gz + dtb
hdr = bytearray(d[:PAGE])
struct.pack_into("<I", hdr, 8, len(new_blob))
struct.pack_into("<I", hdr, 16, len(ramdisk))
img = bytearray(hdr) + new_blob
img += b"\x00" * (-len(img) % PAGE)
img += ramdisk
img += b"\x00" * (-len(img) % PAGE)
open(out, "wb").write(img)
print(f"wrote {out} {len(img)/1048576:.2f} MiB")
