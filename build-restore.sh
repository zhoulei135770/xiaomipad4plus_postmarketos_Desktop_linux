#!/bin/sh
# build-restore.sh - 在设备上生成 TWRP 可刷的恢复包
#
#   sudo ./build-restore.sh [输出目录]
#
# 产物：clover-restore-<日期>.zip（必要时分卷 .z01/.z02…）
# 校验：见 docs/RESTORE-VERIFY.md
set -eu
[ "$(id -u)" = 0 ] || { echo "需要 root"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-/tmp/restore}
DATE=$(date +%Y%m%d-%H%M)
ZIP="$OUT/clover-restore-$DATE.zip"
WORK=$(mktemp -d)

echo "==> 工作目录 $OUT"
mkdir -p "$OUT"

# 1) boot.img：当前启用的 boot 分区（按 pmos_root_uuid 识别）
echo "==> 查找 boot 分区"
BOOT=""
for p in /dev/mmcblk1p*; do
	magic=$(dd if="$p" bs=8 count=1 2>/dev/null | tr -d '\0')
	case "$magic" in
	ANDROID!*)
		if dd if="$p" bs=1M count=8 2>/dev/null | strings | grep -q "pmos_root_uuid="; then
			BOOT="$p"
			break
		fi
		;;
	esac
done
[ -n "$BOOT" ] || { echo "找不到带 pmos_root_uuid 的 boot 分区"; exit 1; }
echo "    boot = $BOOT"
dd if="$BOOT" of="$WORK/boot.img" bs=1M
file "$WORK/boot.img" | sed 's/^/    /'

# 2) rootfs.tar.gz
echo "==> 打包 rootfs（numeric-owner）"
cd /
tar --numeric-owner -czf "$WORK/rootfs.tar.gz" \
	--exclude=./proc --exclude=./sys --exclude=./dev --exclude=./run \
	--exclude=./tmp --exclude=./mnt --exclude=./media --exclude=./lost+found \
	--exclude=./var/cache/apk --exclude=./root/.cache --exclude=./home/zhoulei/.cache \
	. 2>"$OUT/tar.err" || true
ls -lh "$WORK/rootfs.tar.gz" | sed 's/^/    /'

# 3) META-INF
echo "==> 生成 TWRP 脚本"
mkdir -p "$WORK/META-INF/com/google/android"
cp "$HERE/etc/restore/update-binary" "$WORK/META-INF/com/google/android/update-binary"
cp "$HERE/etc/restore/updater-script" "$WORK/META-INF/com/google/android/updater-script"
chmod 755 "$WORK/META-INF/com/google/android/update-binary"
cp "$HERE/docs/RESTORE-VERIFY.md" "$WORK/README-RESTORE.md"

# 4) zip（超过 2 GiB 时自动分卷）
echo "==> 打包 zip"
cd "$WORK"
apk add --no-progress zip unzip >/dev/null 2>&1 || true
zip -q -r "$ZIP" boot.img rootfs.tar.gz META-INF README-RESTORE.md
SIZE=$(stat -c %s "$ZIP")
if [ "$SIZE" -gt 2000000000 ]; then
	echo "==> 超过 2 GiB，分卷为 1500 MiB"
	rm -f "$ZIP"
	zip -q -r -s 1500m "$ZIP" boot.img rootfs.tar.gz META-INF README-RESTORE.md
fi
ls -lh "$OUT"/clover-restore-* | sed 's/^/    /'

# 5) 校验
echo "==> 校验"
unzip -t "$ZIP" >/dev/null && echo "    zip -t OK"
tar -tzf "$WORK/rootfs.tar.gz" >/dev/null && echo "    rootfs readable OK"
if tar -tzf "$WORK/rootfs.tar.gz" | grep -qE '^/|\.\./'; then
	echo "    ⚠️ 发现绝对路径/穿越"
else
	echo "    无绝对路径 OK"
fi
echo "    root 分区 UUID: $(blkid -s UUID -o value /dev/mmcblk1p64)"
echo "    rootfs 大小: $(tar -tzvf "$WORK/rootfs.tar.gz" | awk '{s+=$3} END{printf "%.1f GB", s/1024/1024/1024}')"

rm -rf "$WORK"
echo "==> 完成：$ZIP"
