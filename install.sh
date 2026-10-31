#!/bin/sh
# install.sh - 把本仓库的适配层安装到已运行的 postmarketOS 上
#
# 用法：  sudo ./install.sh
# 完成后重启。
set -eu

[ "$(id -u)" = 0 ] || { echo "请用 root 运行： sudo $0"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
echo "==> 从 $HERE 安装"

# ---------------------------------------------------------------- 依赖
echo "==> 安装软件包"
apk add --no-progress \
	labwc lxqt-session lxqt-panel pcmanfm-qt lxqt-powermanagement \
	grim wlr-randr wlrctl wtype wvkbd wvkbd-deskintl \
	fcitx5 fcitx5-chinese-addons fcitx5-gtk \
	gtk4-layer-shell py3-gobject3 python3 pulseaudio pulseaudio-utils \
	ffmpeg mpv yt-dlp wl-clipboard wl-clipboard \
	> /dev/null 2>&1 || echo "   (部分包可能已存在或不可用，继续)"

# ---------------------------------------------------------------- 脚本
echo "==> 安装设备脚本"
for f in "$HERE"/tools/device/*; do
	[ -f "$f" ] || continue
	install -m 755 "$f" "/usr/local/bin/$(basename "$f")"
	echo "    /usr/local/bin/$(basename "$f")"
done

# ---------------------------------------------------------------- 配置
echo "==> 安装配置"
if [ -d "$HERE/etc/udev" ]; then
	install -m 644 "$HERE"/etc/udev/*.rules /etc/udev/rules.d/ 2>/dev/null || true
fi
if [ -d "$HERE/etc/systemd" ]; then
	for u in "$HERE"/etc/systemd/*.service; do
		[ -f "$u" ] || continue
		install -m 644 "$u" /etc/systemd/system/
		systemctl enable "$(basename "$u")" 2>/dev/null || true
	done
	for s in "$HERE"/etc/systemd/tablet-*; do
		[ -f "$s" ] && install -m 755 "$s" "/usr/local/bin/$(basename "$s")"
	done
fi
if [ -f "$HERE/etc/systemd/logind.conf" ]; then
	install -m 644 "$HERE/etc/systemd/logind.conf" /etc/systemd/logind.conf
fi

# GPU 加固（msm 是内置模块，只能用服务写 sysfs）
if [ -x "$HERE/etc/systemd/tablet-gpu-harden" ]; then
	install -m 755 "$HERE/etc/systemd/tablet-gpu-harden" /usr/local/bin/tablet-gpu-harden
	cat > /etc/systemd/system/tablet-gpu-harden.service <<'EOF'
[Unit]
Description=Adreno GPU stability knobs (preemption/eviction off, keep powered)
DefaultDependencies=no
After=sysinit.target local-fs.target
Before=graphical.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tablet-gpu-harden
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
	systemctl enable tablet-gpu-harden.service
fi

systemctl daemon-reload
udevadm control --reload-rules || true

# ---------------------------------------------------------------- 会话
echo "==> 安装会话启动器（原生 Wayland + Mesa 加固）"
cat > /usr/local/bin/tablet-wayland-session <<'EOF'
#!/bin/sh
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/10000}
export XDG_SESSION_TYPE=wayland
export QT_QPA_PLATFORM=wayland
export GDK_BACKEND=wayland,x11
# Adreno 512 + downstream msm: 关掉会产生零长度 IB 的命令缓冲路径
export FD_MESA_DEBUG=nogrow,noindirect,sysmem
export GSK_RENDERER=cairo
export XMODIFIERS=@im=fcitx
export GTK_IM_MODULE=fcitx
export QT_IM_MODULE=fcitx
export SDL_IM_MODULE=fcitx
export LC_CTYPE=zh_CN.UTF-8
exec /usr/bin/startlxqtwayland
EOF
chmod 755 /usr/local/bin/tablet-wayland-session

echo
echo "==> 完成。还需要手动确认："
echo "   1) /etc/phrog/greetd-config.toml 的 default_session 指向 /usr/local/bin/tablet-wayland-session"
echo "   2) 触摸标定矩阵（见 docs/HARDWARE.md 第 2 节）"
echo "   3) 默认账户密码见 README"
echo
echo "重启生效： sudo reboot"
