#!/bin/sh
# Stage 2: customize the Debian rootfs (runs as root, chrooted into /srv/debport/rootfs).
set -e
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C

ROOT=/srv/debport/rootfs
ART=/srv/debport/artifacts

echo "=== [1/9] mounts"
mount --bind /proc  "$ROOT/proc" 2>/dev/null || true
mount --bind /sys   "$ROOT/sys"  2>/dev/null || true
mount --bind /dev   "$ROOT/dev"  2>/dev/null || true
mount --bind /dev/pts "$ROOT/dev/pts" 2>/dev/null || true

echo "=== [2/9] qemu + sources"
install -m755 /usr/bin/qemu-aarch64-static "$ROOT/usr/bin/qemu-aarch64-static"
cat > "$ROOT/etc/apt/sources.list" <<'EOF'
deb [trusted=yes] http://mirrors.aliyun.com/debian forky main contrib non-free-firmware
EOF

echo "=== [3/9] apt update"
printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"
chmod +x "$ROOT/usr/sbin/policy-rc.d"
chroot "$ROOT" apt-get update -qq

echo "=== [4/9] install desktop stack"
chroot "$ROOT" apt-get install -y --no-install-recommends \
  xwayland labwc lxqt-session lxqt-panel lxqt-powermanagement lxqt-qtplugin \
  lxqt-themes lxqt-globalkeys lxqt-runner lxqt-config lxqt-about lxqt-admin \
  lxqt-archiver lxqt-wayland-session pcmanfm-qt qterminal \
  fcitx5 fcitx5-chinese-addons fcitx5-frontend-gtk3 fcitx5-frontend-gtk4 \
  fcitx5-frontend-qt5 fcitx5-config-qt fcitx5-modules \
  wvkbd wtype wlr-randr grim wl-clipboard \
  pulseaudio pulseaudio-utils alsa-utils \
  bluez blueman network-manager-applet \
  udisks2 upower polkitd pkexec \
  gtklock jgmenu \
  python3-gi gir1.2-gtk-3.0 python3-pil \
  fonts-noto-cjk fonts-dejavu-core fonts-noto-color-emoji fonts-wqy-microhei \
  firefox-esr mpv ffmpeg yt-dlp zathura zathura-pdf-poppler \
  libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-l10n-zh-cn \
  cups avahi-daemon i2c-tools v4l-utils usbutils \
  systemd-zram-generator fake-hwclock greetd \
  mesa-utils libgl1-mesa-dri libegl1 wireless-tools iw rfkill \
  libinput-tools xdg-utils dbus-x11 libqt5svg5

echo "=== [5/9] user + locale"
groupadd -g 119 iio 2>/dev/null || true
groupadd -g 982 fingerprint 2>/dev/null || true
groupadd -g 10000 zhoulei 2>/dev/null || true
useradd -u 10000 -g 10000 -m -d /home/zhoulei -s /bin/bash zhoulei 2>/dev/null || true
for g in sudo audio video input plugdev netdev bluetooth iio fingerprint; do
  getent group "$g" >/dev/null && usermod -aG "$g" zhoulei
done
PWHASH=$(openssl passwd -6 147258 2>/dev/null || python3 -c 'import crypt;print(crypt.crypt("147258", crypt.mksalt(crypt.METHOD_SHA512)))')
chroot "$ROOT" usermod -p "$PWHASH" zhoulei
chroot "$ROOT" usermod -p "$PWHASH" root
sed -i 's/^# *zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/; s/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' "$ROOT/etc/locale.gen"
chroot "$ROOT" locale-gen
echo 'LANG=zh_CN.UTF-8' > "$ROOT/etc/default/locale"
ln -sf /usr/share/zoneinfo/Asia/Shanghai "$ROOT/etc/localtime"
echo "xiaomi-clover" > "$ROOT/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 xiaomi-clover\n' > "$ROOT/etc/hosts"

echo "=== [6/9] unpack ported files"
tar xzf "$ART/core.tgz" -C "$ROOT"
tar xzf "$ART/etc.tgz"  -C "$ROOT"
tar xzf "$ART/bin.tgz"  -C "$ROOT"
tar xzf "$ART/home.tgz" -C "$ROOT"
chown -R 10000:10000 "$ROOT/home/zhoulei"

echo "=== [7/9] system config"
cat > "$ROOT/etc/fstab" <<'EOF'
UUID=8def993b-42f5-4ba1-9813-c046e498fe22 / ext4 defaults 0 1
EOF

cat > "$ROOT/etc/greetd/config.toml" <<'EOF'
[terminal]
vt = 7

[default_session]
command = "/usr/local/bin/tablet-wayland-session"
user = "zhoulei"
EOF

mkdir -p "$ROOT/etc/greetd"
chmod 600 "$ROOT/etc/greetd/config.toml" 2>/dev/null || true

echo "=== [8/9] enable services"
cat > "$ROOT/etc/systemd/zram-generator.conf" <<'EOF'
[zram0]
zram-size = min(ram * 1.5, 6144)
compression-algorithm = zstd
EOF
rm -f "$ROOT"/etc/ssh/ssh_host_*
chroot "$ROOT" systemctl set-default graphical.target 2>/dev/null || true
chroot "$ROOT" systemctl enable ssh NetworkManager bluetooth greetd cups avahi-daemon 2>/dev/null || true
for u in tablet-audio-route tablet-autobright tablet-charge-guard tablet-gpu-harden \
         tablet-no-blank tablet-orientd tablet-otg tablet-powerkeyd \
         tablet-reconnect tablet-reconnect-resume tablet-touch-rotate \
         alsa-mic-tablet alsa-restore-tablet; do
  [ -f "$ROOT/etc/systemd/system/$u.service" ] && chroot "$ROOT" systemctl enable "$u" 2>/dev/null || true
done

echo "=== [9/9] depmod"
chroot "$ROOT" depmod -a 7.0.14-sdm660 2>&1 | tail -3 || true

echo "=== DONE"
