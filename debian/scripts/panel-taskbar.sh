#!/bin/sh
# The panel had lost its taskbar plugin (we removed the camera/settings/terminal
# buttons earlier and the taskbar went with them), so minimized windows had no
# button to restore them from.
python3 - <<'PY'
import re
p = "/home/zhoulei/.config/lxqt/panel.conf"
s = open(p).read()
s = re.sub(r'^plugins=.*$',
           'plugins=fancymenu, taskbar, statusnotifier, volume, worldclock',
           s, count=1, flags=re.M)
if '[taskbar]' not in s:
    s += '\n[taskbar]\nalignment=Left\ntype=taskbar\n'
open(p, 'w').write(s)
print([l for l in s.splitlines() if l.startswith('plugins')])
PY
chown 10000:10000 /home/zhoulei/.config/lxqt/panel.conf
pkill -f /usr/bin/lxqt-panel 2>/dev/null
sleep 2
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  systemd-run --user --unit=panel-t1 --collect /usr/bin/lxqt-panel >/dev/null 2>&1
sleep 5
pgrep -af lxqt-panel | head -2
# open a test window so the taskbar has an entry
pkill -f 'music.163.com' 2>/dev/null
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  /usr/local/bin/tablet-chromium --app=https://example.com > /tmp/tw.log 2>&1 &
sleep 12
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 grim /tmp/taskbar.png
ls -l /tmp/taskbar.png
