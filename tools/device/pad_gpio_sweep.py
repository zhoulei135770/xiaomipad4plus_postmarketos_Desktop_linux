#!/usr/bin/env python3
"""Last-resort front-camera experiment: sweep unclaimed TLMM GPIOs.

For every TLMM pin that no driver owns, drive it high, probe the front
sensor (S5K5E8, 0x10) on CCI master 1, then restore it.  If some pin is a
hidden power enable, the sensor will start acknowledging and we report it.

Safety: only pins shown as unclaimed in /sys/kernel/debug/gpio are touched,
plus a hard blacklist of pins that must never be toggled.
"""
import fcntl
import os
import re
import struct
import subprocess
import sys
import time

GPIO_GET = 0xC16CB403
GPIO_SET = 0xC040B409
TLMM_LABEL = "3100000.pinctrl"
CCI_BUS = 5               # CCI master 1 (front camera)
SENSOR_ADDR = 0x10

# never touch these, whatever the debugfs says
BLACKLIST = set(range(0, 12)) | {13, 14, 15, 19, 20, 21, 22, 23, 24, 25, 26, 27,
                                 32, 33, 36, 37, 38, 39, 44, 45, 46, 49, 51,
                                 52, 61, 62, 63, 64, 65, 66, 67, 71, 76, 77,
                                 78, 79, 80, 81, 82, 83, 84, 85, 86, 88, 89,
                                 92, 98, 108}


def tlmm_chip():
    for i in range(8):
        path = "/dev/gpiochip%d" % i
        if not os.path.exists(path):
            continue
        fd = os.open(path, os.O_RDWR)
        buf = struct.pack("<32s32sI", b"", b"", 0)
        buf = bytearray(68)
        fcntl.ioctl(fd, 0x8044B401, buf, True)
        name, label, lines = struct.unpack_from("32s32sI", buf.raw, 0)
        if TLMM_LABEL in label.decode(errors="replace"):
            return path, fd, lines
        os.close(fd)
    return None, None, 0


def claimed_pins():
    """Parse debugfs to find every GPIO a driver already owns."""
    claimed = set()
    try:
        with open("/sys/kernel/debug/gpio") as f:
            in_tlmm = False
            for line in f:
                if line.startswith("gpiochip"):
                    in_tlmm = TLMM_LABEL in line
                    continue
                if in_tlmm:
                    m = re.match(r"\s+gpio(\d+)\s*:", line)
                    if m:
                        claimed.add(int(m.group(1)))
    except OSError:
        pass
    return claimed


def request_out(chip_fd, off):
    r = bytearray(364)
    struct.pack_into("<I", r, 0, off)
    struct.pack_into("<I", r, 256, 2)      # OUTPUT
    struct.pack_into("<B", r, 260, 0)      # start low
    r[324:325] = b"sweep"
    struct.pack_into("<I", r, 356, 1)
    fcntl.ioctl(chip_fd, GPIO_GET, r, True)
    return struct.unpack_from("<i", r, 360)[0]


def set_val(line_fd, val):
    d = bytearray(64)
    struct.pack_into("<B", d, 0, val)
    fcntl.ioctl(line_fd, GPIO_SET, d, True)


def probe_sensor():
    """True if the sensor acknowledges on the CCI bus."""
    try:
        out = subprocess.run(
            ["i2ctransfer", "-y", "-f", str(CCI_BUS), "w2@0x%02x" % SENSOR_ADDR,
             "0x00", "0x00", "r1"],
            capture_output=True, text=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False


def main():
    path, chip_fd, ngpio = tlmm_chip()
    if chip_fd is None:
        print("TLMM gpiochip not found")
        return 1
    claimed = claimed_pins()
    print("TLMM: %s (%d lines), %d pins claimed by drivers"
          % (path, ngpio, len(claimed)))

    if probe_sensor():
        print("!! sensor already answers - nothing to sweep")
        return 0

    candidates = [g for g in range(ngpio)
                  if g not in claimed and g not in BLACKLIST]
    print("sweeping %d unclaimed pins..." % len(candidates))

    for gpio in candidates:
        try:
            fd = request_out(chip_fd, gpio)
        except OSError:
            continue
        set_val(fd, 1)
        time.sleep(0.04)
        hit = probe_sensor()
        set_val(fd, 0)
        os.close(fd)
        if hit:
            print("*** PIN %d made the sensor answer! ***" % gpio)
            return 0
        if gpio % 10 == 0:
            print("  ...%d" % gpio, flush=True)

    print("no pin enabled the sensor")
    return 0


raise SystemExit(main())