#!/bin/sh
# Merge the release parts, verify, and flash userdata with fastboot.
# Usage: ./flash.sh [image-version]   (default: v13)
set -e
VER="${1:-v13}"
IMG="debian-rootfs-${VER}.img"
GZ="${IMG}.gz"

if [ ! -f "$IMG" ]; then
  if ls "${GZ}.part-"* >/dev/null 2>&1; then
    echo "==> merging parts"
    cat "${GZ}.part-"* > "$GZ"
  fi
  echo "==> decompressing"
  gzip -d "$GZ"
fi

if [ -f SHA256SUMS ]; then
  echo "==> verifying"
  sha256sum -c SHA256SUMS
fi

echo "==> rebooting to bootloader"
adb reboot bootloader || true
sleep 3
fastboot devices

echo "==> flashing userdata ($IMG)"
fastboot flash userdata "$IMG"
echo "==> rebooting"
fastboot reboot
echo "done. 首次启动 PIN: 147258（用户 zhoulei）"

