#!/bin/sh
# Stage 3: pack /srv/debport/rootfs into an ext4 image with the SAME UUID as the
# current pmOS root, so the untouched boot.img can still find it.
set -e
ROOT=/srv/debport/rootfs
IMG=${1:-/srv/debport/debian-rootfs.img}
SIZE=${2:-8G}
UUID=8def993b-42f5-4ba1-9813-c046e498fe22

echo "=== cleanup"
rm -rf "$ROOT"/var/lib/apt/lists/* "$ROOT"/var/cache/apt/archives/*.deb 2>/dev/null || true
rm -rf "$ROOT"/tmp/* 2>/dev/null || true
rm -f "$ROOT"/usr/bin/qemu-aarch64-static
rm -f "$ROOT"/usr/sbin/policy-rc.d

echo "=== unmount"
for m in $(mount | awk '/\/srv\/debport\/rootfs/ {print $3}' | sort -r); do umount -l "$m" 2>/dev/null || true; done
sleep 1

echo "=== mkfs"
rm -f "$IMG"
truncate -s "$SIZE" "$IMG"
mkfs.ext4 -q -F -U "$UUID" -L "Debian" -E lazy_itable_init=1 "$IMG"

echo "=== copy"
MNT=/mnt/debimg
mkdir -p "$MNT"
mount -o loop "$IMG" "$MNT"
rsync -aHAX --numeric-ids "$ROOT"/ "$MNT"/
sync
df -h "$MNT" | tail -1
umount "$MNT"

echo "=== image ready"
ls -lh "$IMG"
blkid "$IMG" || true
