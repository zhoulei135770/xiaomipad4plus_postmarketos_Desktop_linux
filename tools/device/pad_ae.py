#!/usr/bin/env python3
"""Simple auto-exposure loop for the OV13855 rear camera.

Captures a frame, measures its mean brightness and walks exposure/gain
until the image sits near the target.  Run after /tmp/cfg.sh.
"""
import os
import subprocess
import sys

SUB = "/dev/v4l-subdev17"
VID = "/dev/video0"
RAW = "/tmp/ae_frame.raw"

EXP_MIN, EXP_MAX = 4, 3206
GAIN_MIN, GAIN_MAX = 0, 8191
TARGET = 400          # out of 1023 (~39 %)
TOL = 45

def set_ctrl(exp, gain):
    subprocess.run(["v4l2-ctl", "-d", SUB, "-c",
                    "exposure=%d,analogue_gain=%d" % (exp, gain)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def capture():
    if os.path.exists(RAW):
        subprocess.run(["rm", "-f", RAW], stderr=subprocess.DEVNULL)
    subprocess.run(["v4l2-ctl", "-d", VID, "--stream-mmap", "--stream-count=1",
                    "--stream-to=" + RAW],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=15)
    if not os.path.exists(RAW):
        return None
    with open(RAW, "rb") as f:
        f.seek(2 * 1024 * 1024)
        data = f.read(1024 * 1024)
    return sum(data) / len(data) if data else None

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def main():
    exp, gain = 400, 128
    for i in range(10):
        set_ctrl(exp, gain)
        mean = capture()
        if mean is None:
            print("capture failed")
            return 1
        # raw 8-bit mean maps roughly to 1/4 of the 10-bit value
        print("iter %d: exposure=%4d gain=%4d mean8=%6.1f (~%d/1023)"
              % (i, exp, gain, mean, int(mean * 4)))
        if abs(mean * 4 - TARGET) <= TOL:
            print("converged")
            return 0
        ratio = TARGET / max(mean * 4, 1)
        if exp < EXP_MAX:
            exp = clamp(int(exp * ratio), EXP_MIN, EXP_MAX)
        else:
            gain = clamp(int(gain * ratio), GAIN_MIN, GAIN_MAX)
    print("stopped: exposure=%d gain=%d" % (exp, gain))
    return 0

raise SystemExit(main())