#!/bin/sh
set -e
# WPS 11.1 (built for Debian 10/UOS) needs libxml2.so.2, Debian forky ships
# soname 16.  Install the bookworm copy privately and prepend it via wrapper.
rm -rf /tmp/xml && mkdir -p /tmp/xml
dpkg-deb -x /tmp/libxml2.deb /tmp/xml
LIBDIR=/opt/kingsoft/wps-office/office6/libcompat
mkdir -p "$LIBDIR"
cp -a /tmp/xml/usr/lib/aarch64-linux-gnu/libxml2.so.2* "$LIBDIR"/
ls -l "$LIBDIR"
for app in wps et wpp wpspdf; do
  if [ -x "/opt/kingsoft/wps-office/office6/$app" ]; then
    cat > "/usr/local/bin/$app" <<EOF
#!/bin/sh
export LD_LIBRARY_PATH=$LIBDIR:\${LD_LIBRARY_PATH}
exec /opt/kingsoft/wps-office/office6/$app "\$@"
EOF
    chmod 755 "/usr/local/bin/$app"
  fi
done
echo "=== try wps"
sudo -u zhoulei env XDG_RUNTIME_DIR=/run/user/10000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  timeout 12 /usr/local/bin/wps > /tmp/wps4.log 2>&1 || true
wc -c /tmp/wps4.log
head -20 /tmp/wps4.log
