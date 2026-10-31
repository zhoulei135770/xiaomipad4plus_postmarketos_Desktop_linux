export XDG_RUNTIME_DIR=/run/user/10000
export WAYLAND_DISPLAY=wayland-0
echo "=== 窗口 ==="
su -s /bin/sh zhoulei -c 'XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 wlrctl toplevel list 2>/dev/null' | head -n 5
echo
echo "=== 创建固定启动器 ==="
cat > /usr/local/bin/tablet-firefox <<'EOF'
#!/bin/sh
# Firefox on the tablet: force native Wayland and the Mesa command-buffer
# workarounds (a downstream msm kernel + upstream Mesa combination).
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/10000}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/10000/bus}
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}
export XDG_SESSION_TYPE=wayland
export MOZ_ENABLE_WAYLAND=1
export GDK_BACKEND=wayland
export FD_MESA_DEBUG=${FD_MESA_DEBUG:-nogrow,noindirect,sysmem}
exec /usr/lib/firefox-esr/firefox-esr "$@"
EOF
chmod 755 /usr/local/bin/tablet-firefox
sh -n /usr/local/bin/tablet-firefox && echo "launcher OK"

echo
echo "=== 桌面图标里的 Firefox（如存在）==="
grep -rl "firefox" /home/zhoulei/桌面/*.desktop 2>/dev/null | head -n 3
grep -rh "^Exec=" /home/zhoulei/桌面/*.desktop 2>/dev/null | grep -i firefox | head -n 3

echo
echo "=== 截图 ==="
su -s /bin/sh zhoulei -c 'XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 /usr/sbin/grim /tmp/ffnow.png'
ls -l /tmp/ffnow.png
