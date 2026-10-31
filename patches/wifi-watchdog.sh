#!/bin/sh
# WiFi watchdog: bring the link back within a minute when it drops.
#
# The tablet loses WiFi on its own (ath10k + this AP).  tablet-reconnect only
# runs at boot/resume, so a long ssh session dies when the link drops mid-way.
# This runs every minute and does the minimum needed.
LOG=/run/wifi-watchdog.log
DEV=wlan0
exec >>"$LOG" 2>&1

# keep the log from growing forever
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
