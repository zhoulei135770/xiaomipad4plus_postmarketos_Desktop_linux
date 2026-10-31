import struct
import sys

src, dst, cmdline = sys.argv[1], sys.argv[2], sys.argv[3]
d = bytearray(open(src, "rb").read())
if d[:8] != b"ANDROID!":
    raise SystemExit("not an android boot image")
raw = cmdline.encode() + b"\x00"
if len(raw) > 512:
    raise SystemExit("cmdline too long")
d[0x38:0x38 + 512] = raw + b"\x00" * (512 - len(raw))
open(dst, "wb").write(d)
print("wrote", dst, "cmdline:", cmdline)
