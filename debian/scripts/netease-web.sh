#!/bin/sh
# YesPlayMusic 官方 web 演示已暂停部署（Deployment Paused），改用网易云官方网页版，
# 用 Chromium 应用窗口打开，登录/歌单/播放都可用。
cat > /usr/local/bin/netease-web <<'EOF'
#!/bin/sh
exec /usr/local/bin/tablet-chromium --app=https://music.163.com
EOF
chmod 755 /usr/local/bin/netease-web
rm -f /usr/share/applications/yesplaymusic-web.desktop
cat > /usr/share/applications/netease-web.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=网易云音乐（网页版）
Comment=官方网页版，Chromium 应用窗口
Exec=/usr/local/bin/netease-web
Icon=chromium
Terminal=false
Categories=AudioVideo;Audio;Player;
EOF
update-desktop-database /usr/share/applications 2>/dev/null || true
pkill -f 'music.qier222.com' 2>/dev/null
sleep 1
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  /usr/local/bin/netease-web > /tmp/new.log 2>&1 &
sleep 14
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 grim /tmp/newmusic.png
ls -l /tmp/newmusic.png
