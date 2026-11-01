#!/bin/sh
set -e
ROOT=/srv/debport/rootfs
for f in "$ROOT"/usr/share/applications/spark-store.desktop "$ROOT"/usr/share/applications/store.spark-app.spark-store.desktop; do
  [ -f "$f" ] || continue
  sed -i 's|^Exec=spark-store.*$|Exec=spark-store --disable-gpu %u|' "$f"
  echo "patched $f: $(grep '^Exec=' "$f")"
done
ls -l "$ROOT/usr/bin/spark-store"
grep -n 'enableBatteryWatcher' "$ROOT/home/zhoulei/.config/lxqt/lxqt-powermanagement.conf"
ls -l "$ROOT/usr/local/bin/tablet-battery-sni" "$ROOT/home/zhoulei/.config/autostart/tablet-battery-sni.desktop"
grep -c 'webrender' "$ROOT/home/zhoulei/.mozilla/firefox/o3nzgs7q.default-release/user.js"
echo "=== rebuild"
/srv/debport/make-image.sh /srv/debport/debian-rootfs.img 8G
