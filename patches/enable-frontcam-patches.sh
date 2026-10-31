#!/bin/sh
# Wire the front-camera DT patches into the kernel package — source list AND
# sha512sums (a missing checksum makes the build fail).
#
# 0048 (already in pmaports) wires the sensor into &camss -> csiphy2.
# 0053 replaces the stale 0032 (whose hunk no longer applies): a bit-banged i2c
#      bus on the front sensor's CCI pins, generated as an EOF append.
#
# IMPORTANT: source-list entries are TAB-indented, checksum entries start with a
# hex digest.  A naive ".patch$" match hits the checksum block too — the first
# version of this script did exactly that and had to be rolled back.
set -e
P=/home/user/.local/var/pmbootstrap/cache_git/pmaports/device/testing/linux-postmarketos-qcom-sdm660
A="$P/APKBUILD"
HERE=$(cd "$(dirname "$0")" && pwd)

cp "$HERE/0053-frontcam-i2c-gpio.patch" "$P/0053-frontcam-i2c-gpio.patch"

NEW1=0048-arm64-dts-clover-front-camera-endpoint.patch
NEW2=0053-frontcam-i2c-gpio.patch
for n in "$NEW1" "$NEW2"; do
	[ -f "$P/$n" ] || { echo "missing: $P/$n"; exit 1; }
done

if grep -q "$NEW2" "$A"; then
	echo "already wired; nothing to do"
	exit 0
fi

before_src=$(grep -c '^	[0-9][0-9][0-9][0-9]-.*\.patch$' "$A")
before_sum=$(grep -c '^[0-9a-f]\{128\}  ' "$A")
echo "before: $before_src source entries, $before_sum checksums"

cp "$A" "$A.bak.$(date +%s)"

# --- 1. source list (tab-indented entries only) --------------------------
last=$(grep -n '^	[0-9][0-9][0-9][0-9]-.*\.patch$' "$A" | tail -1 | cut -d: -f1)
[ -n "$last" ] || { echo "cannot find the tab-indented patch list"; exit 1; }
{
	head -n "$last" "$A"
	printf '\t%s\n' "$NEW1"
	printf '\t%s\n' "$NEW2"
	tail -n +$((last + 1)) "$A"
} > "$A.new"
mv "$A.new" "$A"

# --- 2. sha512sums -------------------------------------------------------
start=$(grep -n '^sha512sums="' "$A" | head -1 | cut -d: -f1)
[ -n "$start" ] || { echo "no sha512sums block"; exit 1; }
end=$(awk -v s="$start" 'NR>s && $0=="\""{print NR; exit}' "$A")
[ -n "$end" ] || { echo "cannot find the closing quote of sha512sums"; exit 1; }

h1=$(sha512sum "$P/$NEW1" | awk '{print $1}')
h2=$(sha512sum "$P/$NEW2" | awk '{print $1}')
{
	head -n $((end - 1)) "$A"
	echo "$h1  $NEW1"
	echo "$h2  $NEW2"
	tail -n +"$end" "$A"
} > "$A.new"
mv "$A.new" "$A"

after_src=$(grep -c '^	[0-9][0-9][0-9][0-9]-.*\.patch$' "$A")
after_sum=$(grep -c '^[0-9a-f]\{128\}  ' "$A")
echo "after:  $after_src source entries, $after_sum checksums"
[ "$after_src" -eq $((before_src + 2)) ] || { echo "SOURCE COUNT WRONG"; exit 1; }
[ "$after_sum" -eq $((before_sum + 2)) ] || { echo "CHECKSUM COUNT WRONG"; exit 1; }

echo
echo "== new source entries =="
grep -n "^	$NEW1\|^	$NEW2" "$A"
echo "== new checksums =="
grep -n "$h1\|$h2" "$A"
echo
echo "next:  pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660"
