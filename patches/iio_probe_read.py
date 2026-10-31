#!/usr/bin/env python3
"""Probe how the qcom-smgr IIO buffer must be read.

IIO rejects reads whose size is not a multiple of the sample size, and the
buffer should be enabled before the device is opened.  Try a few orders/sizes.
"""
import os
import time

DEV = '/dev/iio:device2'
SYS = '/sys/bus/iio/devices/iio:device2'
SAMPLE = 16


def enable(v):
    with open(os.path.join(SYS, 'buffer/enable'), 'w') as f:
        f.write(str(v))


def attempt(label, enable_first, size, n=1):
    try:
        if enable_first:
            enable(1)
            time.sleep(0.2)
        fd = os.open(DEV, os.O_RDONLY)
        if not enable_first:
            enable(1)
            time.sleep(0.2)
        got = 0
        for _ in range(n):
            try:
                b = os.read(fd, size)
                got += len(b)
            except BlockingIOError:
                time.sleep(0.1)
            except OSError as e:
                print(f'  {label}: read 失败 {e}')
                break
        os.close(fd)
        enable(0)
        print(f'  {label}: 读到 {got} 字节')
        return got
    except Exception as e:
        print(f'  {label}: {type(e).__name__} {e}')
        try:
            enable(0)
        except Exception:
            pass
        return 0


print('样本大小 =', SAMPLE)
attempt('先开缓冲后 open, 读 16', True, 16)
attempt('先 open 后开缓冲, 读 16', False, 16)
attempt('先开缓冲后 open, 读 128', True, 128, 4)
attempt('先开缓冲后 open, 读 1024', True, 1024, 2)
