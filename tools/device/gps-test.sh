#!/bin/sh
# GPS test: start the location session and follow position reports.
# Run OUTDOORS with a clear view of the sky, then wait up to N seconds.
#   sudo gps-test.sh [seconds]
SECS=${1:-240}
NODES="qrtr://0 qrtr://1"

for n in $NODES; do
	if qmicli -d "$n" --loc-get-operation-mode >/dev/null 2>&1; then
		NODE="$n"
		break
	fi
done
[ -n "$NODE" ] || { echo "no QMI node serving LOC"; exit 1; }
echo "using $NODE"

echo "--- operation mode ---"
qmicli -d "$NODE" --loc-get-operation-mode

echo "--- start ---"
qmicli -d "$NODE" --loc-start

echo "--- following position reports (up to ${SECS}s) ---"
timeout "$SECS" qmicli -d "$NODE" --loc-follow-position-report 2>&1 | head -n 40

echo "--- NMEA (10s) ---"
timeout 12 qmicli -d "$NODE" --loc-follow-nmea 2>&1 | head -n 20
