#!/bin/sh
# Keep the Qualcomm modem in "online" mode.
#
# The modem boots in 'shutting-down' and its firmware crashes a few times
# during boot (IPA/wlan_process); each crash resets the operating mode.  Poll
# QMI forever and put it back online whenever it drops.  ModemManager is not
# used: it does not see this QRTR-only modem and restarting it resets the
# modem (which takes the WLAN firmware down with it).
set -u
QRTR=${QRTR_DEV:-qrtr://0}

command -v qmicli >/dev/null 2>&1 || { echo "qmicli not installed"; exit 1; }

online() {
	qmicli -d "$QRTR" --dms-get-operating-mode 2>/dev/null | grep -q "Mode: 'online'"
}

while :; do
	if online; then
		sleep 30
		continue
	fi
	if qmicli -d "$QRTR" --dms-set-operating-mode=online >/dev/null 2>&1; then
		sleep 5
		if online; then
			echo "modem online"
			qmicli -d "$QRTR" --nas-get-serving-system 2>/dev/null \
				| grep -iE 'registration state|Selected network' || true
			qmicli -d "$QRTR" --nas-get-signal-strength 2>/dev/null \
				| grep -iE "Network 'lte'" | head -1 || true
		fi
	fi
	sleep 10
done
