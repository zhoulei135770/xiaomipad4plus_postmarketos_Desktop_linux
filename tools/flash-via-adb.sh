#!/bin/sh
# flash-via-adb.sh - restore the tablet entirely over adb (works when the
# TWRP zip route fails because the archive is too large to mmap).
#
#   ./flash-via-adb.sh boot.img rootfs.tar.gz
#
# Requires: adb, a USB cable, the tablet booted into TWRP.
# This is the exact sequence that was verified on real hardware on 2026-10-31.
set -eu

BOOT=${1:?usage: $0 boot.img rootfs.tar.gz}
TAR=${2:?usage: $0 boot.img rootfs.tar.gz}
ROOT_UUID=${ROOT_UUID:-8def993b-42f5-4ba1-9813-c046e498fe22}

adb wait-for-recovery
echo "==> device in recovery"

echo "==> [1/5] flashing boot.img"
adb push "$BOOT" /tmp/boot.img
adb shell "sha256sum /tmp/boot.img"
adb shell "dd if=/tmp/boot.img of=/dev/block/bootdevice/by-name/boot bs=1048576; sync"
echo "    read-back:"
adb shell "dd if=/dev/block/bootdevice/by-name/boot bs=1048576 count=64 2>/dev/null | sha256sum"

echo "==> [2/5] pushing rootfs ($(du -h "$TAR" | cut -f1))"
adb push "$TAR" /sdcard/rootfs.tar.gz

echo "==> [3/5] extracting to the filesystem root (/data)"
# TWRP's /sdcard is a *subdirectory view*; the tree must land in /data.
adb shell "mkdir -p /data; mountpoint -q /data || mount -t ext4 -o rw /dev/block/bootdevice/by-name/userdata /data"
adb shell "cd /data && tar -xzf /sdcard/rootfs.tar.gz -C /data 2>&1 | tail -n 3"
adb shell "ls /data/sbin/init /data/etc/fstab || echo 'EXTRACT LOOKS WRONG'"

echo "==> [4/5] restoring the ext4 UUID (formatting creates a new one)"
adb shell "umount /data 2>/dev/null; umount /sdcard 2>/dev/null; e2fsck -f -y /dev/block/bootdevice/by-name/userdata >/dev/null 2>&1; tune2fs -U $ROOT_UUID -L pmOS /dev/block/bootdevice/by-name/userdata 2>&1 | tail -n 2; blkid /dev/block/bootdevice/by-name/userdata"

echo "==> [5/5] cleaning up and rebooting"
adb shell "rm -f /sdcard/rootfs.tar.gz; sync; reboot"
echo "==> done; the tablet should boot into pmOS"
