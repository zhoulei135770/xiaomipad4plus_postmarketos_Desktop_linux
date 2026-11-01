#!/bin/sh
P=/home/zhoulei/.mozilla/firefox/o3nzgs7q.default-release
cat > "$P/user.js" <<'EOF'
// freedreno: GPU WebRender renders black/garbled pages with FD_MESA_DEBUG=sysmem;
// without sysmem it draws correctly but the compositor still burns a core.
user_pref("gfx.webrender.all", true);
user_pref("gfx.webrender.software", false);
user_pref("layers.acceleration.force-enabled", true);
user_pref("gfx.canvas.accelerated", true);
// keep the compositor from spinning on every vsync
user_pref("widget.wayland.vsync", false);
user_pref("layout.frame_rate", 45);
user_pref("general.smoothScroll", false);
user_pref("toolkit.cosmeticAnimations.enabled", false);
EOF
chown -R 10000:10000 "$P/user.js"
pkill -f /usr/lib/firefox-esr/firefox-esr 2>/dev/null
sleep 2
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  /usr/local/bin/tablet-firefox https://www.baidu.com >/tmp/ff4.log 2>&1 &
sleep 14
for i in 1 2 3 4; do
  ps -eo pcpu,args | grep firefox-esr | grep -v grep | awk '{s+=$1} END {printf "cpu=%.1f\n", s}'
  sleep 1
done
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 grim /tmp/ff5.png
ls -l /tmp/ff5.png
