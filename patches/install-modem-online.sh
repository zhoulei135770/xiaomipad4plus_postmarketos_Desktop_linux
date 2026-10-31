#!/bin/sh
# Install the "modem online at boot" helper on the tablet.
#
# Usage (on the tablet, as root):
#   sh install-modem-online.sh            install + enable
#   sh install-modem-online.sh --remove   disable + remove
set -e

if [ "${1:-}" = "--remove" ]; then
	systemctl disable --now modem-online.service 2>/dev/null || true
	rm -f /etc/systemd/system/modem-online.service /usr/local/bin/modem-online.sh
	systemctl daemon-reload
	echo "removed"
	exit 0
fi

HERE=$(dirname "$0")
[ -f "$HERE/modem-online.sh" ] || { echo "modem-online.sh not found next to this script"; exit 1; }
[ -f "$HERE/modem-online.service" ] || { echo "modem-online.service not found next to this script"; exit 1; }

install -m 0755 "$HERE/modem-online.sh" /usr/local/bin/modem-online.sh
install -m 0644 "$HERE/modem-online.service" /etc/systemd/system/modem-online.service
systemctl daemon-reload
systemctl enable --now modem-online.service
echo
echo "== status =="
systemctl --no-pager status modem-online.service | head -12
