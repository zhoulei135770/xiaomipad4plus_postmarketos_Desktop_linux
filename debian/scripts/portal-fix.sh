#!/bin/sh
mkdir -p /home/zhoulei/.config/systemd/user/xdg-desktop-portal-wlr.service.d
cat > /home/zhoulei/.config/systemd/user/xdg-desktop-portal-wlr.service.d/override.conf <<'EOF'
[Service]
Environment=XDG_CURRENT_DESKTOP=labwc
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/10000
Environment=XDG_SESSION_TYPE=wayland
EOF
chown -R 10000:10000 /home/zhoulei/.config/systemd/user
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemctl --user daemon-reload
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemctl --user restart xdg-desktop-portal-wlr.service 2>&1 | tail -2
sleep 2
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemctl --user status xdg-desktop-portal-wlr --no-pager 2>&1 | head -6
echo "=== test portal screenshot"
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  grim /tmp/portal-test.png && ls -l /tmp/portal-test.png
