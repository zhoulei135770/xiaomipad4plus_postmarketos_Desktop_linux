#!/bin/sh
# Make Xorg drive the display through the Adreno GPU once it is available.
#
# With the GPU disabled the modesetting driver runs on llvmpipe (software).
# When /dev/dri/card0 (adreno) exists, Mesa picks the freedreno driver and the
# compositor gets hardware acceleration.  This snippet just makes the choice
# explicit and reversible.
set -e
CONF=/etc/X11/xorg.conf.d/20-gpu.conf

if [ "${1:-}" = "--remove" ]; then
	rm -f "$CONF"
	echo removed
	exit 0
fi

mkdir -p /etc/X11/xorg.conf.d
cat > "$CONF" <<'EOS'
# Prefer the KMS/glamor path: when the Adreno GPU is present Xorg uses it,
# otherwise this is harmless and llvmpipe is used instead.
Section "Device"
    Identifier  "msm"
    Driver      "modesetting"
    Option      "AccelMethod" "glamor"
    Option      "DRI"         "3"
EndSection
EOS
echo "installed $CONF"
cat "$CONF"
