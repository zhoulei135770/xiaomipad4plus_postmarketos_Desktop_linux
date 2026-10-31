set -e
M=/lib/modules/7.0.14-sdm660/kernel/drivers/media/i2c/ov13855.ko.zst
cp "$M" "$M.bak-pregrbg" 2>/dev/null || true
cp /tmp/ov13855-new.ko.zst "$M"
depmod 7.0.14-sdm660
ls -l "$M" "$M.bak-pregrbg"
echo "installed"
