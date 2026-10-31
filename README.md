# Xiaomi Mi Pad 4 Plus (clover / SDM660) — Linux mainline hardware bring-up

Bringing the **Xiaomi Mi Pad 4 Plus** (`clover`, Qualcomm SDM660) up on
**postmarketOS / mainline Linux**: what works, what does not, and *why* —
with reproducible experiments, kernel patches and driver sources.

This repository is a **research log + patch collection**. It is not a
flashable distribution; the device runs
[sdm660-mainline/linux](https://github.com/sdm660-mainline/linux).

> 中文简介：这是小米平板4 Plus（SDM660）在主线 Linux 上的硬件适配记录。
> 包含已解决硬件的方案、未解决硬件的根因分析（附完整实验证据）、内核补丁和驱动源码。

---

## Status matrix

| Subsystem | State | Notes |
|---|---|---|
| Boot / eMMC / display / touch | ✅ | mainline + device tree in boot partition |
| Wi-Fi (WCN3990) | ✅ | stable **as long as the modem stays idle** |
| Bluetooth | ✅ | |
| Audio (speakers, jack, mic) | ✅ | TAS2557 + ACDB |
| GPU (Adreno 512, llvmpipe fallback) | 🔧 | no zap shader → software rendering |
| **Modem / RF / SIM** | ✅ radio / ❌ long-run | registers on CMCC, RSSI ≈ -62 dBm, but the modem asserts after ~3 min and takes Wi-Fi down with it |
| **Mobile data (LTE)** | ❌ | no IPA driver for SDM660 in mainline |
| **GPS** | ⚠️ | QMI LOC service responds, **no fix ever obtained**; testing needs the modem online (which crashes) |
| **Rear camera** | ✅ | OV13855 via qcom-camss + userspace ISP (`tablet-camera-gui`) |
| **Front camera** | ❌ | S5K5E8 never ACKs on CCI (hardware works in Android) |
| **Fingerprint** | ❌ | FPC1020 controllable, imaging lives in a closed TEE TA |
| Default camera app (GNOME Snapshot) | ❌ | libcamera cannot handle this raw-bayer pipeline |
| Charging / fuel gauge / USB-C role | ✅ | SMB2 + auto role switching |
| Suspend / resume | ⚠️ | not verified |
| Sensors (accel/gyro/mag/prox/ALS/hall) | ✅ | via `qcom_smgr` |

Legend: ✅ works · 🔧 partial · ⚠️ unverified · ❌ not working (root cause documented).

---

## What is solved here (and how)

### 1. Modem crash loop (SDM660 MSS memory banks)

Upstream patch: the MSS memory-bank count must be **29**, not 28. Without it
the modem crashes every ~18 s and drags the Wi-Fi firmware down.
→ [`docs/60-MODEM-CRASH-FIX.md`](docs/60-MODEM-CRASH-FIX.md)

### 2. Custom kernel that actually boots

Two BTF fixes are required, otherwise distro modules (including `mac80211` /
`ath10k`) refuse to load and the system never reaches the desktop:

* relax `btf_name_valid_identifier()` / `btf_name_valid_section()`
* accept empty `BTF_KIND_TYPE_TAG` names

→ [`docs/63-CUSTOM-KERNEL-AND-TZ-TEST.md`](docs/63-CUSTOM-KERNEL-AND-TZ-TEST.md)

### 3. Rear camera colour (orange rendered as green)

The OV13855 on this board outputs **BGGR**, while every consumer assumed
GRBG. Fixed in the userspace ISP and documented with the full diagnostic
path (four Bayer phases tested against a known-colour object).
→ [`docs/43-CAMERA-PIPELINE.md`](docs/43-CAMERA-PIPELINE.md)

### 4. Upstream bug found: IPA core clock rate never applied

`ipa_power_init()` calls `clk_set_rate()` **before** the clock is enabled;
RPM clocks (`clk-smd-rpm`) silently drop that request, so on every rpmcc
platform the IPA core clock keeps its default rate. Patch included:

```sh
git am patches/0001-net-ipa-apply-core-clock-rate-after-enable.patch
```

→ [`docs/64-UPSTREAM-IPA-REPORT.md`](docs/64-UPSTREAM-IPA-REPORT.md)

### 5. Charging / USB-C role detection

SMB2 `TYPE_C_STATUS` exposure + a 2-second role switcher.
→ [`docs/00-GOAL.md`](docs/00-GOAL.md), [`docs/33-SYSTEM-TUNING.md`](docs/33-SYSTEM-TUNING.md)

---

## What does **not** work, and the exact reason

| Feature | Root cause (evidence in docs) |
|---|---|
| LTE data | mainline has no SDM660 IPA platform support; **the IPA register window cannot be accessed from the AP at all** — every read stalls, and the TrustZone `SCM_SVC_MP` service is not available to the APPS (proved with a control query) → [`docs/64`](docs/64-UPSTREAM-IPA-REPORT.md) |
| Long-run cellular | the modem asserts in `ipa_util.c` a few minutes after going online, which crashes `ath10k` too → [`docs/66`](docs/66-SESSION-2026-10-31.md) |
| GPS fix | LOC service works, but positioning needs the modem online (see above) and no fix was ever obtained → [`docs/65`](docs/65-GPS-QMI-FINDINGS.md) |
| Front camera | S5K5E8 never acknowledges on CCI master 1; power/clock/reset pins, supply rails, standby GPIO and 14 reset/timing combinations were all tested → [`docs/26`](docs/26-FRONT-CAMERA-DIAGNOSIS.md) |
| Fingerprint | FPC1020 responds and frames can be captured, but imaging/matching runs inside the closed `fpctzapp` TA (TEE) → [`docs/29`](docs/29-FINGERPRINT-CEILING.md) |
| Default camera app | libcamera's simple pipeline rejects/handles badly the correct `SBGGR10` format (flicker) → [`docs/66`](docs/66-SESSION-2026-10-31.md) |

---

## Repository layout

```
docs/          research log, one file per topic (Chinese, numbered chronologically)
patches/       kernel patches (IPA clock rate, camera, DTS …)
tools/host/    helpers to run commands on the device / build VM over SSH
tools/build/   kernel, module, DTB and boot-image build scripts
tools/device/  scripts that run ON the tablet (camera GUI, cellular helper, GPS test)
tools/probe/   the IPA probe module used for the register-access experiments
```

Start reading at **[`docs/INDEX.md`](docs/INDEX.md)** — it lists every note with
a one-line summary. [`docs/66-SESSION-2026-10-31.md`](docs/66-SESSION-2026-10-31.md)
summarises the last full day of work and the lessons learned.

---

## Build / flash quick start

Kernel (clang, cross):

```sh
git clone -b qcom-sdm660-7.0.y https://github.com/sdm660-mainline/linux
cd linux
export PATH=/usr/lib/llvm-20/bin:$PATH
make ARCH=arm64 LLVM=1 Image
```

Only the boot partition is touched; keep an unpadded image so the marker /
ramoops area survives:

```sh
python3 tools/build/vm_pack_boot.py Image.gz boot.img   # kernel + original dtb + ramdisk
sudo dd if=boot.img of=/dev/mmcblk1p12 conv=fsync        # on the device
```

Recovery: `fastboot flash boot <stock boot.img>`.

### Device scripts

```sh
sudo /usr/local/bin/cellular-on.sh     # bring the modem online (Wi-Fi will die in ~3 min)
sudo /usr/local/bin/gps-test.sh 300    # outdoor GPS test
tablet-cam photo.raw                    # rear-camera capture + develop
tablet-camera-gui                       # GTK camera with correct colours
sudo modprobe -r ath10k_snoc && sudo modprobe ath10k_snoc   # recover Wi-Fi
```

---

## Hard-won lessons (please read before experimenting)

1. **Never** `qmicli --dms-set-operating-mode=offline` — on this device the
   modem cannot return to `online` and the *shutdown* path then hangs
   (`port failed halt`, black screen with a cursor).
2. **Never** restart the modem through `remoteproc` — `wcn3990` (Wi-Fi) talks
   QMI to the modem and dies with it.
3. The modem asserts ~3 minutes after going online; that is the missing IPA
   driver, not a configuration mistake.
4. `qmicli` must use **`qrtr://0`** on this platform (node 1 is not the modem).
5. When editing scripts that run on the device, keep **LF** line endings.

---

## What is intentionally *not* in this repository

* vendor firmware images, vendor kernel blobs and any extracted proprietary
  library (`.so`, `.mbn`, `.bin`, MIUI/Android partitions);
* device backups (`*.img`, `*.apk`, TWRP images) — several GB;
* build artefacts and personal network/password information (sanitised).

All findings were produced by reading public sources, the device's own
device-tree/boot image, and running experiments on hardware the author owns.

---

## Credits

* [sdm660-mainline/linux](https://github.com/sdm660-mainline/linux) — the
  mainline kernel tree this device runs;
* [postmarketOS](https://postmarketos.org) / [Nura](https://nura.eco) —
  userspace;
* mainline IPA, qcom-camss, ath10k, qcom-smb2 communities — the drivers this
  work builds on.

## License

Documentation: CC BY-SA 4.0. Code and patches: MIT (see `LICENSE`).
