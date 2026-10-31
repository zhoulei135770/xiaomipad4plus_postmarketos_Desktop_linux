set -e
mkdir -p /home/user/ipa_marker
printf 'obj-m := ipa_marker.o\nccflags-y := -DHAVE_SCM_MP_UNLOCK\n' > /home/user/ipa_marker/Makefile
cd /home/user/kbuild/src-714
export PATH=/usr/lib/llvm-20/bin:$PATH
make ARCH=arm64 LLVM=1 M=/home/user/ipa_marker KBUILD_MODPOST_WARN=1 modules > /tmp/mk2.log 2>&1 || {
  echo "BUILD FAILED"; grep -E "error" /tmp/mk2.log | head -8; exit 1; }
ls -l /home/user/ipa_marker/ipa_marker.ko
echo OK
