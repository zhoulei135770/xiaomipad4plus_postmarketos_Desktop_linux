#!/bin/sh
set -e
ROOT=/srv/debport/rootfs
mount --bind /proc "$ROOT/proc" 2>/dev/null || true
mount --bind /sys "$ROOT/sys" 2>/dev/null || true
mount --bind /dev "$ROOT/dev" 2>/dev/null || true
mkdir -p "$ROOT/dev/pts"; mount --bind /dev/pts "$ROOT/dev/pts" 2>/dev/null || true
install -m755 /usr/bin/qemu-aarch64-static "$ROOT/usr/bin/qemu-aarch64-static"
tar xzf /tmp/persist12.tgz -C "$ROOT"
chown -R 10000:10000 "$ROOT/home/zhoulei"
chmod 755 "$ROOT/usr/local/bin/tablet-battery-sni"
# spark store (arm64 deb) inside the image
cp /tmp/spark.deb "$ROOT/tmp/spark.deb"
chroot "$ROOT" apt-get update -qq
chroot "$ROOT" apt-get install -y --no-install-recommends python3-dbus
chroot "$ROOT" apt-get install -y /tmp/spark.deb
ln -sf /opt/spark-store/bin/spark-store "$ROOT/usr/bin/spark-store"
rm -f "$ROOT/tmp/spark.deb"
rm -f "$ROOT/usr/bin/qemu-aarch64-static"
grep -n 'enableBatteryWatcher' "$ROOT/home/zhoulei/.config/lxqt/lxqt-powermanagement.conf"
grep -n 'webrender' "$ROOT/home/zhoulei/.mozilla/firefox/o3nzgs7q.default-release/user.js"
echo "=== rebuild"
/srv/debport/make-image.sh /srv/debport/debian-rootfs.img 8G
