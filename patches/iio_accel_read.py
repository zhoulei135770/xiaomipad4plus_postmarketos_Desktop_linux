#!/usr/bin/env python3
"""Read the qcom-smgr accelerometer straight from its IIO buffer.

iio-sensor-proxy can't use this device (it has no IIO trigger), so we decode the
buffer ourselves.

Actual sample layout, measured from a hexdump (not what scan_elements claims):

    offset 0  : x   int32 LE
    offset 4  : y   int32 LE
    offset 8  : z   int32 LE
    offset 12 : 4 bytes padding
    offset 16 : timestamp int64 LE
    stride    : 24 bytes

Scale from in_accel_scale (1.5258e-5): sqrt(y^2+z^2) comes out ~650000 raw,
i.e. 9.9 m/s^2 -- about 1 g, which confirms the interpretation.

Usage:
    iio_accel_read.py            # 8 samples, raw + g
    iio_accel_read.py --stream   # one line per sample until killed
"""
import math
import os
import struct
import sys
import time

DEV = '/dev/iio:device2'
SYS = '/sys/bus/iio/devices/iio:device2'
STRIDE = 24
SCALE = 1.5258e-5


def enable(v):
    with open(os.path.join(SYS, 'buffer/enable'), 'w') as f:
        f.write(str(v))


def main():
    stream = '--stream' in sys.argv
    try:
        SCALE = float(open(os.path.join(SYS, 'in_accel_scale')).read().strip())
    except Exception:
        pass

    enable(1)
    time.sleep(0.2)
    fd = os.open(DEV, os.O_RDONLY)
    got = 0
    buf = b''
    t0 = time.time()
    try:
        while True:
            try:
                buf += os.read(fd, 1024)
            except BlockingIOError:
                time.sleep(0.05)
                continue
            while len(buf) >= STRIDE:
                s, buf = buf[:STRIDE], buf[STRIDE:]
                x, y, z = struct.unpack('<iii', s[:12])
                gx, gy, gz = x * SCALE, y * SCALE, z * SCALE
                mag = math.sqrt(gx * gx + gy * gy + gz * gz)
                print(f'x={x:9d} y={y:9d} z={z:9d}   '
                      f'gx={gx:+6.2f} gy={gy:+6.2f} gz={gz:+6.2f}  |g|={mag:5.2f}')
                got += 1
                if not stream and got >= 8:
                    return 0
            if time.time() - t0 > 60:
                return 0
    finally:
        os.close(fd)
        enable(0)


if __name__ == '__main__':
    sys.exit(main())
