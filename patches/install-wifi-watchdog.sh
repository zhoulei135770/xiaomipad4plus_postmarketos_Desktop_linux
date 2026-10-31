#!/bin/sh
# Install (or remove) the WiFi watchdog on the tablet.
#   sh install-wifi-watchdog.sh
#   sh install-wifi-watchdog.sh --remove
set -e

LIB=/usr/local/lib/wifi-watchdog.sh
SVC=/etc/systemd/system/wifi-watchdog.service
TMR=/etc/systemd/system/wifi-watchdog.timer

if [ "${1:-}" = "--remove" ]; then
	systemctl disable --now wifi-watchdog.timer 2>/dev/null || true
	rm -f "$SVC" "$TMR" "$LIB"
	systemctl daemon-reload
	echo "removed"
	exit 0
fi

mkdir -p /usr/local/lib
cat > "$LIB" <<'EOS'
#!/bin/sh
# WiFi watchdog: bring the link back within a minute when it drops.
LOG=/run/wifi-watchdog.log
DEV=wlan0
exec >>"$LOG" 2>&1

if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 200000 ]; then
	: > "$LOG"
fi

[ -d "/sys/class/net/$DEV" ] || exit 0

state=$(nmcli -t -f DEVICE,STATE d status 2>/dev/null | awk -F: -v d="$DEV" '$1==d{print $2}')
[ "$state" = "connected" ] && exit 0

echo "=== $(date) $DEV state=$state, recovering"
rfkill unblock wifi 2>/dev/null
ip link set "$DEV" up 2>/dev/null

prof=$(nmcli -t -f NAME,TYPE c show 2>/dev/null | awk -F: '$2=="802-11-wireless"{print $1; exit}')
[ -n "$prof" ] && timeout 40 nmcli connection up "$prof" 2>&1

echo "=== now: $(nmcli -t -f DEVICE,STATE d status 2>/dev/null | awk -F: -v d="$DEV" '$1==d{print $2}')"
EOS
chmod +x "$LIB"

cat > "$SVC" <<'EOS'
[Unit]
Description=WiFi watchdog (reconnect when the link drops)
After=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/lib/wifi-watchdog.sh
EOS

cat > "$TMR" <<'EOS'
[Unit]
Description=Run the WiFi watchdog every minute

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5s

[Install]
WantedBy=timers.target
EOS

systemctl daemon-reload
systemctl enable --now wifi-watchdog.timer
echo "installed"
systemctl list-timers wifi-watchdog.timer --no-pager 2>/dev/null | head -3
