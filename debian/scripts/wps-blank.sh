#!/bin/sh
# Open a blank Writer document directly, bypassing the CEF start page.
install -D -m644 /tmp/blank.docx /usr/share/wps-office/templates/blank.docx
cat > /usr/local/bin/wps-blank <<'EOF'
#!/bin/sh
# create a fresh copy so the user never edits the template
tmp="${XDG_RUNTIME_DIR:-/tmp}/wps-untitled-$(date +%s%N).docx"
cp /usr/share/wps-office/templates/blank.docx "$tmp"
exec /usr/bin/wps "$tmp"
EOF
chmod 755 /usr/local/bin/wps-blank
cat > /usr/share/applications/wps-blank.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=WPS 文字（新建空白）
Comment=直接打开空白文档，跳过联网首页
Exec=/usr/local/bin/wps-blank
Icon=wps-office-wps
Terminal=false
Categories=Office;WordProcessor;
EOF
update-desktop-database /usr/share/applications 2>/dev/null || true
echo "=== test"
pkill -f office6/wps 2>/dev/null
sleep 2
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  /usr/local/bin/wps-blank > /tmp/wb.log 2>&1 &
sleep 16
pgrep -af 'office6/wps' | head -2
wc -c /tmp/wb.log; head -5 /tmp/wb.log
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 grim /tmp/wpsblank.png
ls -l /tmp/wpsblank.png
