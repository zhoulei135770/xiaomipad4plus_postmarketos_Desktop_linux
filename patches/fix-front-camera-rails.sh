#!/bin/sh
# Fix the front camera (S5K5E8) power rails in pmaports patch 0007.
#
# Current (wrong): the front camera is powered from the REAR camera's rails
#     vana-supply = <&cam_avdd_2v8>;        /* rear 2.8V */
#     vdig-supply = <&cam_rear_dvdd_1v2>;   /* rear 1.2V */
# The vendor DT gives the front sensor its OWN switches (cam_vana=0x1da,
# cam_vdig=0x1db, plus CAM_VANA on GPIO49 and CAM_VDIG on PMIC GPIO3), which in
# the pmOS DTS are the fixed regulators cam_avdd_front_2v8 / cam_front_dvdd_1v8.
#
# Run on the build VM, then rebuild the kernel package / dtb.
set -e
P=/home/user/.local/var/pmbootstrap/cache_git/pmaports/device/testing/linux-postmarketos-qcom-sdm660/0007-arm64-dts-qcom-sdm660-xiaomi-clover-camera.patch
[ -f "$P" ] || { echo "patch not found: $P"; exit 1; }

cp "$P" "$P.bak.$(date +%s)"

# only change the two lines that belong to the s5k5e8 node (they appear once)
sed -i 's|vana-supply = <&cam_avdd_2v8>;|vana-supply = <\&cam_avdd_front_2v8>;|' "$P"
sed -i 's|vdig-supply = <&cam_rear_dvdd_1v2>;|vdig-supply = <\&cam_front_dvdd_1v8>;|' "$P"

echo "== new s5k5e8 power lines =="
grep -nE 'vana-supply|vdig-supply|vddio-supply' "$P"
echo
echo "rebuild with:  pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660"
echo "then flash boot:  fastboot flash boot <new boot.img>"
