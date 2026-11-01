#!/bin/sh
for f in /usr/share/applications/spark-store.desktop /usr/share/applications/*spark*.desktop; do
  [ -f "$f" ] || continue
  if grep -q '^Exec=.*spark-store' "$f"; then
    sed -i 's|^Exec=spark-store.*$|Exec=spark-store --disable-gpu %u|' "$f"
    echo "patched $f"
    grep '^Exec=' "$f"
  fi
done
pkill -f /opt/spark-store/bin/spark-store 2>/dev/null
sleep 2
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemctl --user reset-failed spark-desktop 2>/dev/null
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemd-run --user --unit=spark-desktop --collect /usr/bin/spark-store --disable-gpu >/dev/null 2>&1
sleep 10
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 grim /tmp/store4.png
ls -l /tmp/store4.png
