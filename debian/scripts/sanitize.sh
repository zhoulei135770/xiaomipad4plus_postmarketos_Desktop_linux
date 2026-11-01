#!/bin/sh
# Turn the private working rootfs into a publishable image: strip credentials,
# browser profiles, history and logs.  Run inside the VM as root.
set -e
ROOT=/srv/debport/rootfs
H="$ROOT/home/zhoulei"

# --- personal data ---------------------------------------------------------
rm -rf "$H/.mozilla" "$H/.config/chromium" "$H/.cache" "$H/.ssh" \
       "$H/.bash_history" "$H/.local/share/recently-used.xbel" \
       "$H/.config/pcmanfm-qt/lxqt/recent-files.conf" \
       "$H/.config/pcmanfm-qt/default/recent-files.conf" \
       "$H/.config/lxqt/"*.bak* "$H/桌面/"*.desktop.bak* 2>/dev/null || true

# WiFi / VPN credentials
rm -rf "$ROOT/etc/NetworkManager/system-connections"/* 2>/dev/null || true
rm -rf "$ROOT/etc/NetworkManager/system-connections" 2>/dev/null || true

# shell / sudo history, logs, temp
rm -f "$ROOT/root/.bash_history" "$ROOT/root/.viminfo"
rm -rf "$ROOT/var/log"/* "$ROOT/tmp"/* "$ROOT/var/tmp"/* 2>/dev/null || true
rm -rf "$ROOT/var/cache/apt/archives"/*.deb 2>/dev/null || true

# known machine-id / SSH host keys (regenerated on first boot)
rm -f "$ROOT/etc/machine-id" "$ROOT/var/lib/dbus/machine-id"
rm -f "$ROOT/etc/ssh/ssh_host_"* 2>/dev/null || true

# --- shrink ----------------------------------------------------------------
rm -rf "$ROOT/usr/share/doc"/* 2>/dev/null || true
rm -rf "$ROOT/usr/share/man"/* 2>/dev/null || true
rm -rf "$ROOT/var/lib/apt/lists"/* 2>/dev/null || true

echo "=== leftovers (should be empty)"
ls "$H/.mozilla" "$H/.config/chromium" 2>&1 | head -3
du -sh "$ROOT" 2>/dev/null
