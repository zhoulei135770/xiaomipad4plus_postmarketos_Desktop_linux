set -e
M=/lib/modules/7.0.14-sdm660/kernel/drivers/media/i2c/ov13855.ko.zst
if [ -f "$M.bak-pregrbg" ]; then
  cp "$M.bak-pregrbg" "$M"
  depmod 7.0.14-sdm660
  echo "reverted to original SGRBG10 module"
else
  echo "backup missing!"
fi
ls -l "$M"
