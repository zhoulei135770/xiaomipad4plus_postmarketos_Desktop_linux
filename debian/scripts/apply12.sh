#!/bin/sh
set -e
ROOT=/srv/debport/rootfs
mount --bind /proc "$ROOT/proc" 2>/dev/null || true
mount --bind /sys "$ROOT/sys" 2>/dev/null || true
mount --bind /dev "$ROOT/dev" 2>/dev/null || true
mkdir -p "$ROOT/dev/pts"; mount --bind /dev/pts "$ROOT/dev/pts" 2>/dev/null || true
tar xzf /tmp/persist10.tgz -C "$ROOT"
chown -R 10000:10000 "$ROOT/home/zhoulei"
# mask plymouth inside the image too
for u in plymouth-start plymouth-quit-wait plymouth-quit; do
  ln -sf /dev/null "$ROOT/etc/systemd/system/$u.service"
done
grep -n 'Wallpaper=' "$ROOT/home/zhoulei/.config/pcmanfm-qt/lxqt/settings.conf"
grep -n 'all input devices gone' "$ROOT/usr/local/bin/tablet-powerkeyd" | head -1
echo "=== rebuild"
/srv/debport/make-image.sh /srv/debport/debian-rootfs.img 8G
