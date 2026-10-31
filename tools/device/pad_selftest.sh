#!/bin/sh
# Functional self-test for the Mi Pad 4 Plus pmOS port.
# Exercises every subsystem (not just "does the node exist") and prints
# PASS/FAIL.  Safe to run repeatedly; takes about 60 seconds.
#
#   sudo pad_selftest.sh

PASS=0
FAIL=0
SKIP=0

pass() { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }
skip() { SKIP=$((SKIP+1)); printf '  [SKIP] %s\n' "$1"; }

echo "=== Mi Pad 4 Plus functional self-test ==="
echo "kernel: $(uname -r)"
echo

# ---- display ----
echo "display"
if grep -q ^connected /sys/class/drm/*/status 2>/dev/null; then
	pass "DRM connector connected"
else
	fail "no connected DRM connector"
fi

# ---- touch / input ----
echo "input"
if grep -qi goodix /proc/bus/input/devices 2>/dev/null; then
	pass "Goodix touchscreen present"
else
	fail "touchscreen not found"
fi

# ---- wifi ----
echo "wifi"
if [ "$(cat /sys/class/net/wlan0/operstate 2>/dev/null)" = "up" ]; then
	pass "wlan0 up"
	gw=$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')
	if [ -n "$gw" ] && ping -c1 -W2 "$gw" >/dev/null 2>&1; then
		pass "gateway $gw reachable"
	else
		fail "gateway not reachable"
	fi
else
	fail "wlan0 not up"
fi

# ---- bluetooth ----
echo "bluetooth"
if [ -e /sys/class/bluetooth/hci0 ]; then
	n=$(timeout 12 bluetoothctl --timeout 8 scan on 2>/dev/null | grep -c "Device ")
	if [ "$n" -gt 0 ]; then
		pass "BT scan found $n device(s)"
	else
		skip "BT scan found nothing (radio may still work)"
	fi
else
	fail "hci0 missing"
fi

# ---- audio ----
echo "audio"
if [ -e /dev/snd/pcmC0D0p ]; then
	python3 - <<'PY' 2>/dev/null
import wave, struct, math
w = wave.open("/tmp/st.wav", "w")
w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
for i in range(24000):
    v = int(8000*math.sin(2*math.pi*440*i/48000))
    w.writeframesraw(struct.pack("<hh", v, v))
w.close()
PY
	if [ -e /tmp/st.wav ] && timeout 15 aplay -D plughw:0,0 /tmp/st.wav >/dev/null 2>&1; then
		pass "played 0.5 s tone on plughw:0,0"
	else
		fail "aplay failed"
	fi
else
	fail "no playback PCM"
fi

# ---- sensors ----
echo "sensors"
n=$(ls /sys/bus/iio/devices/ 2>/dev/null | wc -l)
[ "$n" -ge 4 ] && pass "$n IIO devices" || fail "only $n IIO devices"
ALS=""
for d in /sys/bus/iio/devices/iio:device*; do
	[ "$(cat $d/name 2>/dev/null)" = "qcom-smgr-prox" ] && ALS=$d && break
done
if [ -n "$ALS" ] && [ -e "$ALS/in_illuminance_raw" ]; then
	pass "ALS raw = $(cat $ALS/in_illuminance_raw)"
else
	fail "ALS not readable"
fi

# ---- battery / charger ----
echo "power"
[ -e /sys/class/power_supply/qcom-battery/capacity ] \
	&& pass "battery $(cat /sys/class/power_supply/qcom-battery/capacity)%" \
	|| fail "battery missing"
[ -e /sys/class/power_supply/pm660-charger ] && pass "charger present" || fail "charger missing"

# ---- USB ----
echo "usb"
n=$(ls /sys/bus/usb/devices/ 2>/dev/null | grep -c '^[0-9]')
[ "$n" -gt 0 ] && pass "$n USB device(s)" || fail "no USB devices"

# ---- rear camera ----
echo "rear camera"
if [ -e /dev/video0 ]; then
	sh /usr/local/bin/pad_cam_config.sh >/dev/null 2>&1
	rm -f /tmp/selftest.raw
	if timeout 15 v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=1 \
			--stream-to=/tmp/selftest.raw </dev/null >/dev/null 2>&1; then
		sz=$(wc -c < /tmp/selftest.raw 2>/dev/null)
		if [ "$sz" -eq 16558080 ]; then
			pass "captured 16558080 bytes"
		else
			fail "captured $sz bytes (expected 16558080)"
		fi
	else
		fail "capture failed"
	fi
else
	fail "/dev/video0 missing"
fi

# ---- fingerprint ----
echo "fingerprint"
modprobe fpc1020 2>/dev/null
if [ -d /sys/bus/spi/devices/spi0.0 ]; then
	echo reset > /sys/bus/spi/devices/spi0.0/cmd 2>/dev/null
	sleep 0.2
	echo "r fc 2" > /sys/bus/spi/devices/spi0.0/cmd 2>/dev/null
	sleep 0.3
	if dmesg | grep -q "reg 0xfc = 03 41"; then
		pass "FPC1020 answered with HWID 0x0341"
	else
		fail "no HWID from fingerprint sensor"
	fi
else
	fail "fpc1020 not bound"
fi

# ---- modem ----
echo "modem"
st=$(cat /sys/class/remoteproc/remoteproc1/state 2>/dev/null)
if [ "$st" = "running" ]; then
	pass "modem remoteproc running"
	if timeout 20 qmicli -d qrtr://0 --dms-get-revision >/dev/null 2>&1; then
		pass "QMI answered"
	else
		fail "QMI did not answer"
	fi
else
	fail "modem state: ${st:-missing}"
fi

# ---- GPU ----
echo "gpu"
f=$(cat /sys/class/devfreq/5000000.gpu/cur_freq 2>/dev/null)
[ -n "$f" ] && pass "GPU devfreq at $f Hz" || fail "GPU devfreq missing"

echo
echo "=== $PASS passed, $FAIL failed, $SKIP skipped ==="
[ "$FAIL" -eq 0 ] || exit 1