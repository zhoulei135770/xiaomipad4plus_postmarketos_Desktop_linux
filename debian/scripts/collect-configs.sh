#!/bin/sh
# Pull the source-of-truth configuration out of the tablet into a tarball so it
# can be committed to the GitHub repo.
set -e
OUT=/tmp/mipad4plus-configs.tgz
rm -f "$OUT"
cd /
tar czf "$OUT" \
  home/zhoulei/.config/labwc \
  home/zhoulei/.config/lxqt \
  home/zhoulei/.config/pcmanfm-qt \
  home/zhoulei/.config/pulse \
  home/zhoulei/.config/autostart \
  home/zhoulei/.local/share/lxqt/themes \
  usr/local/bin/tablet-orientd \
  usr/local/bin/tablet-powerkeyd \
  usr/local/bin/tablet-battery-sni \
  usr/local/bin/tablet-rotate \
  usr/local/bin/tablet-rotate-restore \
  usr/local/bin/tablet-wayland-session \
  usr/local/bin/tablet-settings \
  usr/local/bin/tablet-touch-rotate \
  usr/local/bin/tablet-autobright \
  usr/local/bin/tablet-charge-guard \
  usr/local/bin/tablet-brightness \
  usr/local/bin/tablet-drop-caches \
  usr/local/bin/tablet-firefox \
  usr/local/bin/tablet-chromium \
  usr/local/lib/tablet-pinlock.py \
  usr/local/lib/pam_auth.py \
  usr/local/bin/tablet-pinlock \
  usr/share/alsa/ucm2/Xiaomi/clover \
  usr/share/alsa/ucm2/conf.d/sdm660-internal \
  etc/systemd/system/bt-address.service \
  etc/systemd/system/tablet-powerkeyd.service \
  etc/systemd/system/tablet-orientd.service \
  etc/sudoers.d/tablet-settings \
  etc/X11/xorg.conf.d \
  etc/greetd 2>/dev/null || true
ls -lh "$OUT"
