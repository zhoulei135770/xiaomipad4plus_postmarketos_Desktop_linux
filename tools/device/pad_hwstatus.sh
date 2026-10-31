#!/bin/sh
# Xiaomi Mi Pad 4 Plus (clover-plus) hardware status check for pmOS.
# Prints one line per subsystem: OK / PARTIAL / MISSING.
# Run on the device:  sh /tmp/hwstatus.sh

say() { printf '%-22s %s\n' "$1" "$2"; }
have() { [ -e "$1" ] && echo yes || echo no; }

echo "=== Xiaomi Mi Pad 4 Plus — hardware status ==="
echo "kernel: $(uname -r)   uptime: $(cut -d' ' -f1 /proc/uptime)s"
echo

# --- display / GPU -------------------------------------------------------
conn=$(grep -l ^connected /sys/class/drm/*/status 2>/dev/null | head -1)
if [ -n "$conn" ]; then
	say "display" "OK $(dirname $conn | xargs basename)"
else
	say "display" "MISSING"
fi

# --- touchscreen ---------------------------------------------------------
if grep -qs . /sys/class/input/input*/name; then
	names=$(cat /sys/class/input/input*/name 2>/dev/null | tr '\n' ',' | cut -c1-60)
	say "input devices" "OK ($names)"
else
	say "input devices" "MISSING"
fi
if ls /dev/input/event* >/dev/null 2>&1; then
	say "touch (/dev/input)" "OK $(ls /dev/input/event* | wc -l) nodes"
else
	say "touch (/dev/input)" "MISSING"
fi

# --- wifi ----------------------------------------------------------------
if [ -e /sys/class/net/wlan0 ]; then
	say "wifi" "OK $(cat /sys/class/net/wlan0/operstate 2>/dev/null)"
else
	say "wifi" "MISSING"
fi

# --- bluetooth -----------------------------------------------------------
if [ -e /sys/class/bluetooth/hci0 ]; then
	say "bluetooth" "OK"
else
	say "bluetooth" "MISSING"
fi

# --- audio ---------------------------------------------------------------
if [ -e /proc/asound/card0 ]; then
	say "audio (ALSA)" "OK $(cat /proc/asound/card0/id 2>/dev/null)"
else
	say "audio (ALSA)" "MISSING"
fi

# --- USB -----------------------------------------------------------------
if [ -d /sys/bus/usb/devices/usb1 ]; then
	say "usb" "OK $(ls /sys/bus/usb/devices/ | grep -c '^[0-9]') device(s)"
else
	say "usb" "MISSING"
fi

# --- rear camera ---------------------------------------------------------
# /dev/video0 alone proves nothing: the vfe node exists even when the sensor
# module (ov13855) was never loaded.  Require the sensor entity in the graph.
if [ -e /dev/video0 ]; then
	ent=$(media-ctl -d /dev/media0 -p 2>/dev/null | grep -c 'ov13855')
	if [ "$ent" -gt 0 ]; then
		say "rear camera (video0)" "OK (ov13855 entity present, refs=$ent)"
	else
		say "rear camera (video0)" "PARTIAL (sensor not registered - modprobe ov13855)"
	fi
else
	say "rear camera (video0)" "MISSING"
fi

# --- front camera --------------------------------------------------------
if [ -e /dev/v4l-subdev17 ]; then
	front=$(media-ctl -d /dev/media0 -p 2>/dev/null | grep -c 's5k5e8')
	if [ "$front" -gt 0 ]; then
		say "front camera" "PARTIAL (entity bound)"
	else
		say "front camera" "MISSING (no entity)"
	fi
else
	say "front camera" "MISSING"
fi
# probe result
if dmesg 2>/dev/null | grep -q "S5K5E8 FOUND device"; then
	say "front i2c" "OK (sensor answered)"
else
	say "front i2c" "FAILED (no ACK)"
fi

# --- ambient light sensor (CM3232, exposed as qcom-smgr-prox) ---
# The CM3232 is surfaced through the IIO *buffer* (in_proximity_* scan
# elements), not an in_illuminance_* channel; tablet-autobright reads it there.
ALS=""
for d in /sys/bus/iio/devices/iio:device*; do
	if [ "$(cat $d/name 2>/dev/null)" = "qcom-smgr-prox" ]; then ALS=$d; break; fi
done
if [ -n "$ALS" ] && [ -e "$ALS/scan_elements/in_proximity_en" ]; then
	raw=""
	if [ -e "$ALS/buffer/enable" ] && [ -e "$ALS/buffer0" ]; then
		echo 1 > "$ALS/buffer/enable" 2>/dev/null
		raw=$(dd if="$ALS/buffer0" bs=16 count=1 2>/dev/null | od -An -tu2 | tr -s ' ' | sed 's/^ //')
		echo 0 > "$ALS/buffer/enable" 2>/dev/null
	fi
	if [ -n "$raw" ]; then
		say "ambient light (ALS)" "OK (CM3232 via IIO buffer: $raw)"
	else
		say "ambient light (ALS)" "OK (CM3232 present, buffer idle)"
	fi
else
	say "ambient light (ALS)" "MISSING"
fi
if systemctl is-active --quiet tablet-autobright 2>/dev/null; then
	say "auto-brightness" "OK (tablet-autobright)"
else
	say "auto-brightness" "absent"
fi

# --- modem / 4G ----------------------------------------------------------
if [ -r /sys/class/remoteproc/remoteproc1/state ]; then
	st=$(cat /sys/class/remoteproc/remoteproc1/state 2>/dev/null)
	say "modem (mss)" "$(echo "$st" | tr a-z A-Z)"
	if command -v qmicli >/dev/null 2>&1 && [ "$st" = "running" ]; then
		rev=$(timeout 15 qmicli -d qrtr://0 --dms-get-revision 2>/dev/null | grep -o "MPSS[^']*" | cut -c1-40)
		[ -n "$rev" ] && say "modem firmware" "OK $rev"
		sim=$(timeout 15 qmicli -d qrtr://0 --uim-get-card-status 2>/dev/null | grep -o "Card state: '[a-z]*'" | head -1)
		[ -n "$sim" ] && say "SIM" "$sim"
	fi
else
	say "modem (mss)" "MISSING"
fi
if [ -e /sys/class/net/rmnet_ipa0 ] || [ -e /sys/class/net/wwan0 ]; then
	say "mobile data" "OK (net port present)"
else
	say "mobile data" "MISSING (no IPA net port)"
fi

# --- hardware video codec (venus) ---
if v4l2-ctl --list-devices 2>/dev/null | grep -qi venus; then
	# device nodes register, but decoding currently times out (see HARDWARE-DATA.md)
	say "video codec (venus)" "PARTIAL (nodes register, decode fails)"
else
	say "video codec (venus)" "MISSING"
fi

# --- fingerprint ---------------------------------------------------------
# fingerprint: the fpc1020 driver registers an input device named "fpc1020"
if modprobe fpc1020 2>/dev/null; grep -qs '"fpc1020"' /proc/bus/input/devices 2>/dev/null; then
	fp=$(grep -c '"fpc1020"' /proc/bus/input/devices 2>/dev/null)
	say "fingerprint" "OK (driver bound, input dev)"
elif dmesg 2>/dev/null | grep -qi "FPC1020 ready"; then
	say "fingerprint" "OK (driver bound)"
else
	say "fingerprint" "MISSING (no driver)"
fi

# --- sensors / misc ------------------------------------------------------
for s in accelerometer proximity light; do :; done
if [ -n "$(ls /sys/bus/iio/devices/ 2>/dev/null)" ]; then
	say "iio sensors" "OK $(ls /sys/bus/iio/devices/ | wc -l) device(s)"
else
	say "iio sensors" "MISSING"
fi
bat=$(ls -d /sys/class/power_supply/*batt* /sys/class/power_supply/bms 2>/dev/null | head -1)
if [ -n "$bat" ]; then
	cap=$(cat $bat/capacity 2>/dev/null)
	say "battery" "OK $(basename $bat) ${cap}%"
else
	say "battery" "MISSING"
fi
if [ -e /dev/rtc0 ]; then
	say "rtc" "OK"
else
	say "rtc" "MISSING"
fi
echo
echo "=== end ==="
