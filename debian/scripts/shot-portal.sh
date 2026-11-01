#!/bin/sh
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends xdg-desktop-portal xdg-desktop-portal-wlr slurp 2>&1 | tail -3
cat > /usr/local/bin/tablet-screenshot <<'EOF'
#!/bin/sh
# region screenshot -> clipboard + ~/Pictures
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/10000}
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}
mkdir -p "$HOME/Pictures"
f="$HOME/Pictures/shot-$(date +%Y%m%d-%H%M%S).png"
if command -v slurp >/dev/null 2>&1; then
  geom=$(slurp) || exit 0
  grim -g "$geom" "$f" || exit 1
else
  grim "$f" || exit 1
fi
wl-copy < "$f" 2>/dev/null || true
notify-send -a screenshot -i camera-photo "截图已保存" "$f" 2>/dev/null || true
EOF
chmod 755 /usr/local/bin/tablet-screenshot
cat > /usr/share/applications/tablet-screenshot.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=截图（区域）
Comment=grim + slurp，结果复制到剪贴板
Exec=/usr/local/bin/tablet-screenshot
Icon=camera-photo
Terminal=false
Categories=Utility;
EOF
update-desktop-database /usr/share/applications 2>/dev/null || true
# bind Super+P and Print
CFG=/home/zhoulei/.config/labwc/rc.xml
if ! grep -q 'tablet-screenshot' "$CFG"; then
python3 - <<'PY'
p = "/home/zhoulei/.config/labwc/rc.xml"
s = open(p).read()
add = '''  <keybind key="W-p"><action name="Execute" command="/usr/local/bin/tablet-screenshot" /></keybind>
  <keybind key="Print"><action name="Execute" command="/usr/local/bin/tablet-screenshot" /></keybind>
</keyboard>'''
s = s.replace('</keyboard>', add, 1)
open(p, 'w').write(s)
print("keybinds added")
PY
fi
chown 10000:10000 "$CFG"
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus labwc --reconfigure >/dev/null 2>&1
# make sure the portal backend is running
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemctl --user enable --now xdg-desktop-portal-wlr.service 2>&1 | tail -2
systemctl --user status xdg-desktop-portal-wlr --no-pager 2>/dev/null | head -4
echo done
