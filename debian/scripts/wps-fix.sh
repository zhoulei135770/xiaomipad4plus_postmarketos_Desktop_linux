#!/bin/sh
# Make WPS Office 11.1 (built for Debian 10 / UOS) run on Debian forky.
#
# Two sonames were bumped in the meantime:
#   libxml2.so.2  -> forky ships libxml2.so.16
#   libicu*.so.72 -> forky ships ICU 76
# WPS ships neither, so install private copies from Debian 12 (bookworm) into
# /opt/kingsoft/wps-office/office6/libcompat and prefer them via a wrapper.
set -e

LIBDIR=/opt/kingsoft/wps-office/office6/libcompat
MIRROR=${MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian}
mkdir -p "$LIBDIR" /tmp/wps-compat
cd /tmp/wps-compat

fetch() {  # $1 package, $2 pool dir, $3 regex
  url="$MIRROR/pool/main/$2/"
  name=$(curl -s "$url" | grep -oE "$3" | sort -u | tail -1)
  [ -n "$name" ] || { echo "not found: $1"; exit 1; }
  echo "downloading $name"
  curl -sL -o "$1.deb" "$url$name"
  rm -rf "x-$1" && mkdir "x-$1" && dpkg-deb -x "$1.deb" "x-$1"
}

fetch libxml2 'libx/libxml2' 'libxml2_2\.9\.[0-9.]+[^"]*_arm64\.deb'
fetch libicu72 'i/icu' 'libicu72_[^"]*_arm64\.deb'

cp -a x-libxml2/usr/lib/aarch64-linux-gnu/libxml2.so.2* "$LIBDIR"/
cp -a x-libicu72/usr/lib/aarch64-linux-gnu/libicu*.so.72* "$LIBDIR"/
ldconfig 2>/dev/null || true

for app in wps et wpp wpspdf; do
  [ -x "/opt/kingsoft/wps-office/office6/$app" ] || continue
  cat > "/usr/local/bin/$app" <<EOF
#!/bin/sh
export LD_LIBRARY_PATH=$LIBDIR:\${LD_LIBRARY_PATH}
exec /opt/kingsoft/wps-office/office6/$app "\$@"
EOF
  chmod 755 "/usr/local/bin/$app"
done

echo "done. 启动: wps / et / wpp"
echo "首次启动会弹出《WPS Office 最终用户许可协议》，点“确定”即可。"
