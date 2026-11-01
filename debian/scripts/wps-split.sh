#!/bin/sh
# Kingsoft's launcher scripts hide errors and, in some modes, hand off to the
# fushion UI (the blank CEF page).  Replace them with minimal wrappers that
# exec the right component directly.
LIBDIR=/opt/kingsoft/wps-office/office6/libcompat
for app in wps et wpp wpspdf; do
  BIN=/opt/kingsoft/wps-office/office6/$app
  [ -x "$BIN" ] || continue
  [ -f /usr/bin/$app.vendor ] || cp -a /usr/bin/$app /usr/bin/$app.vendor
  cat > /usr/bin/$app <<EOF
#!/bin/sh
export LD_LIBRARY_PATH=$LIBDIR:\${LD_LIBRARY_PATH}
exec $BIN "\$@"
EOF
  chmod 755 /usr/bin/$app
done
echo "=== wrappers"
head -3 /usr/bin/et
# file associations: open each type in its own component, not the fushion page
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 xdg-mime default wps-office-wps.desktop application/vnd.openxmlformats-officedocument.wordprocessingml.document
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 xdg-mime default wps-office-et.desktop application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 xdg-mime default wps-office-wpp.desktop application/vnd.openxmlformats-officedocument.presentationml.presentation
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 xdg-mime default wps-office-et.desktop application/vnd.ms-excel
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 xdg-mime default wps-office-wpp.desktop application/vnd.ms-powerpoint
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 xdg-mime default wps-office-wps.desktop application/msword
echo "=== opens"
pkill -f office6/et 2>/dev/null; sleep 1
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  /usr/bin/et /tmp/test.xlsx > /tmp/et3.log 2>&1 &
sleep 14
pgrep -af 'office6/et' | head -2
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 grim /tmp/etopen.png
ls -l /tmp/etopen.png
