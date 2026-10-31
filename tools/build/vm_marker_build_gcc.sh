set -e
mkdir -p /home/user/ipa_marker
printf 'obj-m := ipa_marker.o\n' > /home/user/ipa_marker/Makefile
cd /home/user/kbuild/linux-7.0.14-sdm660
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M=/home/user/ipa_marker KBUILD_MODPOST_WARN=1 modules > /tmp/mk.log 2>&1 || {
  echo "BUILD FAILED"; grep -E "error" /tmp/mk.log | head -10; exit 1; }
ls -l /home/user/ipa_marker/ipa_marker.ko
echo OK
