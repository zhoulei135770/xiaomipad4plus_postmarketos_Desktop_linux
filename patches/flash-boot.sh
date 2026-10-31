#!/bin/sh
# Flash the front-camera boot image to the boot partition, with safety checks.
#
#   sh flash-boot.sh            # flash boot-frontcam.img
#   sh flash-boot.sh --rollback # restore the original boot.img
#
# The boot partition is /dev/mmcblk1p12 (64 MB).  Before writing we verify that
# its current content still matches the saved original, so we never overwrite
# something unexpected.
set -e
P=/dev/mmcblk1p12
DIR=/tmp/bootwork
ORIG=$DIR/boot.img
NEW=$DIR/boot-frontcam.img

[ -b "$P" ] || { echo "$P not found"; exit 1; }

if [ "${1:-}" = "--rollback" ]; then
	SRC=$ORIG
	echo "rolling back to the original boot.img"
else
	SRC=$NEW
fi
[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }

SZ=$(wc -c < "$SRC")
echo "target : $P  ($(blockdev --getsize64 "$P") bytes)"
echo "image  : $SRC  ($SZ bytes)"

# --- safety: current partition content must equal the saved original ---
if [ -f "$ORIG" ]; then
	CUR=$(dd if="$P" bs=1M count=25 2>/dev/null | head -c "$(wc -c < "$ORIG")" | md5sum | cut -d' ' -f1)
	EXP=$(md5sum "$ORIG" | cut -d' ' -f1)
	if [ "$CUR" != "$EXP" ]; then
		echo "REFUSING: partition content does not match the saved original"
		echo "  current : $CUR"
		echo "  expected: $EXP"
		exit 1
	fi
	echo "safety check: partition matches the saved original  OK"
fi

echo
echo "writing..."
dd if="$SRC" of="$P" bs=1M conv=fsync 2>&1 | tail -2

echo
echo "read back verification:"
RB=$(dd if="$P" bs=1M count=25 2>/dev/null | head -c "$SZ" | md5sum | cut -d' ' -f1)
WANT=$(md5sum "$SRC" | cut -d' ' -f1)
echo "  written: $WANT"
echo "  readback: $RB"
[ "$RB" = "$WANT" ] && echo "  OK — identical" || { echo "  MISMATCH!"; exit 1; }

echo
echo "done. reboot to apply:  sudo reboot"
