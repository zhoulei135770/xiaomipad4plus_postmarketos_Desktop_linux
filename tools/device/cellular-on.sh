#!/bin/sh
# Bring the modem online and report the cellular state.
# WARNING: on this device the modem asserts (IPA) a few minutes after going
# online, which also takes the WiFi firmware down.  Reboot (or reload
# ath10k_snoc) afterwards.
set -e
qmicli -d qrtr://0 --dms-set-operating-mode=online
sleep 20
echo "--- serving system ---"
qmicli -d qrtr://0 --nas-get-serving-system | grep -E "Registration|Description"
echo "--- signal ---"
qmicli -d qrtr://0 --nas-get-signal-info | head -n 8
echo "--- sim ---"
qmicli -d qrtr://0 --uim-get-card-status | grep -E "Card state"
