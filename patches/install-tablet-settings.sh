#!/bin/sh
# Install the tablet control centre: application, narrow sudo rules, launcher.
#   sh install-tablet-settings.sh
#   sh install-tablet-settings.sh --remove
set -e

APP=/usr/local/bin/tablet-settings
SUDO=/etc/sudoers.d/tablet-settings
DESK=/usr/share/applications/tablet-settings.desktop
PANEL=/home/user/Desktop/tablet-settings.desktop

if [ "${1:-}" = "--remove" ]; then
	rm -f "$APP" "$SUDO" "$DESK" "$PANEL"
	rm -rf /usr/local/lib/tablet-settings
	echo removed
	exit 0
fi

mkdir -p /usr/local/lib/tablet-settings
cp /tmp/tablet-settings "$APP"
chmod +x "$APP"

# Only these exact commands may run without a password, and only by user.
cat > "$SUDO" <<'EOS'
user ALL=(root) NOPASSWD: /usr/bin/tee /sys/class/backlight/lcd-backlight/brightness
user ALL=(root) NOPASSWD: /bin/sh -c echo * > /sys/class/backlight/lcd-backlight/brightness
user ALL=(root) NOPASSWD: /bin/sh -c sync; echo 3 > /proc/sys/vm/drop_caches
user ALL=(root) NOPASSWD: /bin/systemctl reboot
user ALL=(root) NOPASSWD: /bin/systemctl poweroff
EOS
chmod 0440 "$SUDO"
visudo -cf "$SUDO" >/dev/null && echo "sudoers ok"

cat > "$DESK" <<'EOS'
[Desktop Entry]
Type=Application
Name=平板设置
Name[en]=Tablet Settings
Comment=WiFi、蓝牙、亮度、音量、内存与电源
Exec=/usr/local/bin/tablet-settings
Icon=preferences-system
Terminal=false
Categories=Settings;System;
EOS

cp "$DESK" "$PANEL"
chown 10000:10000 "$PANEL" 2>/dev/null || true
chmod +x "$PANEL"

echo "installed:"
ls -l "$APP" "$SUDO" "$DESK" "$PANEL"
