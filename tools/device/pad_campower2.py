import fcntl, os, struct, sys

def req_line(chip, off, val):
    fd = os.open(chip, os.O_RDWR)
    r = bytearray(364)
    struct.pack_into("=I", r, 0, off)
    struct.pack_into("=I", r, 256, 2)      # OUTPUT
    struct.pack_into("=B", r, 260, val)
    r[324:325] = b"t"
    struct.pack_into("=I", r, 356, 1)
    fcntl.ioctl(fd, 0xC16CB403, r, True)
    return struct.unpack_from("=i", r, 360)[0]

def set_line(lfd, val):
    d = bytearray(64)
    struct.pack_into("=B", d, 0, val)
    fcntl.ioctl(lfd, 0xC040B409, d, True)

level = 0 if (len(sys.argv) > 1 and sys.argv[1] == "low") else 1
for chip, off, name in (("/dev/gpiochip0", 49, "TLMM gpio49 VANA"),
                        ("/dev/gpiochip2", 3, "PM660L gpio3 VDIG")):
    try:
        lfd = req_line(chip, off, level)
        set_line(lfd, level)
        print("%s -> %s" % (name, "HIGH" if level else "LOW"))
    except OSError as e:
        print("%s FAILED %s" % (name, e))