#!/bin/sh
# Install the front-camera-fixed DTB on the tablet.
#
# The bootloader (extlinux) loads /sdm660-xiaomi-clover-plus.dtb as a separate
# file, so fixing the front camera only needs this one file — no kernel rebuild
# and no flashing.
#
# Usage (ON THE TABLET, as root):
#   sh install-frontcam-dtb.sh <fixed.dtb>
#   sh install-frontcam-dtb.sh --rollback
set -e

DTB=/boot/sdm660-xiaomi-clover-plus.dtb
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "${1:-}" = "--rollback" ]; then
	LATEST=$(ls -1t /boot/sdm660-xiaomi-clover-plus.dtb.bak-* 2>/dev/null | head -1)
	[ -n "$LATEST" ] || { echo "no backup found"; exit 1; }
	cp "$LATEST" "$DTB"
	echo "restored $DTB from $LATEST"
	echo "reboot to apply"
	exit 0
fi

SRC=${1:-}
[ -f "$SRC" ] || { echo "usage: sh $0 <fixed.dtb>   |   sh $0 --rollback"; exit 1; }

# sanity: the new file must look like a DTB
MAGIC=$(od -An -tx1 -N4 "$SRC" | tr -d ' \n')
[ "$MAGIC" = "d00dfeed" ] || { echo "not a DTB (magic=$MAGIC), aborting"; exit 1; }

cp "$DTB" "$DTB.bak-$STAMP"
echo "backup  -> $DTB.bak-$STAMP"
cp "$SRC" "$DTB"
sync
echo "installed -> $DTB"
ls -l "$DTB" "$DTB.bak-$STAMP"

echo
echo "reboot to apply.  if the rear camera or boot breaks:"
echo "  sh $0 --rollback && reboot"
