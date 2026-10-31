#!/usr/bin/env python3
"""Dump raw bytes from the smgr accelerometer buffer for layout analysis."""
import os
import time

DEV = '/dev/iio:device2'
SYS = '/sys/bus/iio/devices/iio:device2'


def enable(v):
    with open(os.path.join(SYS, 'buffer/enable'), 'w') as f:
        f.write(str(v))


enable(1)
time.sleep(0.3)
fd = os.open(DEV, os.O_RDONLY)
data = b''
t0 = time.time()
while len(data) < 256 and time.time() - t0 < 5:
    try:
        data += os.read(fd, 1024)
    except BlockingIOError:
        time.sleep(0.05)
os.close(fd)
enable(0)

print(f'总字节 {len(data)}')
for off in range(0, min(len(data), 256), 16):
    chunk = data[off:off + 16]
    hexs = ' '.join(f'{b:02x}' for b in chunk)
    # 同时按 int32 小端解读 4 个整数
    ints = []
    for i in range(0, min(len(chunk) - 3, 16), 4):
        ints.append(int.from_bytes(chunk[i:i + 4], 'little', signed=True))
    print(f'{off:04x}: {hexs:<48} {ints}')
