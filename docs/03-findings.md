# 03 · 证据与细节（Findings）

> 本文件记录"为什么得出这些结论"，方便新会话复核，不用重新跑分析。

---

## 1. 线刷包分析（`clover_images_9.8.29_20190829.0000.00_8.1_cn_927549c5be.tgz`）

### 1.1 基本信息

| 项 | 值 |
|---|---|
| 大小 | 1 614.3 MB |
| 包内根目录 | `clover_images_9.8.29_20190829.0000.00_8.1_cn/` |
| Android 版本 | 8.1（文件名 `_8.1_cn_`） |
| 镜像数 | 76 个条目，含 `boot/system/vendor/recovery/userdata/cache/cust` 等 |

### 1.2 分区表（`images/rawprogram0.xml`，EDL 刷机用）

共 68 个 label，关键项：

```
abl  apdp  bluetooth  boot  cache  cmnlib  cmnlib64  devcfg  devinfo  dsp
frp  fsc  fsg  hyp  keymaster  keystore  limits  logdump  logo  mdtp
misc  modem  modemst1  modemst2  msadp  persist  pmic  rawdump  recovery
rpm  sec  splash  ssd  sti  storsec  system  toolsfv  tz  userdata
vbmeta  vbmetabak  vendor  xbl
```

**没有 `dtbo`**（有 `vbmeta`），所以 8.1 的 clover 不用独立 dtbo 分区，DTB 应内嵌在 boot.img。

### 1.3 boot.img 结构

```
magic      ANDROID!
kernel     45 757 895 B
ramdisk     1 609 348 B（gzip → 3 545 856 B cpio）
second              0
pagesize        4 096
header name     (空)
cmdline         console=ttyMSM0,115200,n8 androidboot.console=... androidboot.hardware=qcom ...
```

ramdisk 里 `clover` / `xiaomi` / `sdm660` 字符串 **均为 0 次**（只有通用 `default.prop`、`ueventd.rc` 等）。

### 1.4 DTB 扫描结果（关键证据）

在 boot.img 全文件按 4 字节对齐扫描 FDT magic `d0 0d fe ed`，得到 **32 个 blob**，起始偏移 ~`0xbd9658`（在 kernel 段内，属 qcom 的 kernel+dtb 拼接）。

逐个解析根节点 `model`，**没有一个是小米**，全是高通参考板：

| 示例 | model |
|---|---|
| dtb_00 | Qualcomm Technologies, Inc. SDM 660 PM660 + PM660L CDP |
| dtb_05 | … SDM 660 PM660 + PM660L MTP |
| dtb_16 | … SDM 660 PM660 + PM660L QRD |
| dtb_06 | … SDA 660 PM660 + PM660A MTP |
| dtb_23 | … SDA 630 PM660 + PM660A MTP |

完整清单见 `artifacts/rom/dtb-models.txt`。

`recovery.img`（51 787 086 B）同样：32 个 DTB，`clover`/`xiaomi` 计数为 0。

### 1.5 结论

- 这个包的 boot/recovery **不带设备专用 DTB**，无法提取 Plus 的面板/触控配置
- 若要设备侧真值，只能靠：设备 `/proc/device-tree`、或 Android 9/10 带 `dtbo.img` 的包、或小米开源内核源码
- **但已证明不需要**——上游 DTS 已经有完整定义（见第 2 节）

### 1.6 复现命令

```powershell
# 解 boot.img
tar -xzf <tgz> -C <out> --strip-components=2 "clover_images_.../images/boot.img"
# 切 DTB + 读 model
python tools/split_dtb.py boot.img dtb/
python tools/fdt_model.py dtb/
```

---

## 2. 上游内核 DTS（决定性证据）

### 2.1 来源

pmaports 内核包 `device/testing/linux-postmarketos-qcom-sdm660/APKBUILD`：

```
pkgver=7.0.14
_tag="v$pkgver-sdm660"
source="linux-$_tag.tar.gz::https://github.com/sdm660-mainline/linux/archive/refs/tags/$_tag.tar.gz"
```

对应 raw 路径：

```
https://raw.githubusercontent.com/sdm660-mainline/linux/v7.0.14-sdm660/arch/arm64/boot/dts/qcom/
    sdm660-xiaomi-clover-plus.dts          (3 817 B)
    sdm660-xiaomi-clover.dts               (346 B)
    sda660-xiaomi-clover.dts               (351 B)
    sdm660-xiaomi-clover-common.dtsi       (16 193 B)
```

> 注意：wiki 写的内核是 6.13，pmaports 实际已到 7.0.14（`edge` 分支），wiki 滞后。

### 2.2 `sdm660-xiaomi-clover-plus.dts` 要点（原文摘要）

```dts
/ { model = "Xiaomi Mi Pad 4 Plus"; compatible = "xiaomi,clover-plus", "qcom,sdm660"; };

battery { compatible = "simple-battery"; charge-full-design-microamp-hours = <8620000>; };

vreg_bl_vddio: lcd-backlight-regulator {
    regulator-min-microvolt = <3150000>;
    gpio = <&tlmm 72 GPIO_ACTIVE_HIGH>;      // 背光使能
};

&blsp_i2c3 {
    touchscreen@5d {
        compatible = "goodix,gt9110";
        AVDD28-supply = <&vreg_l3b_3p0>;  VDDIO-supply = <&vreg_l11a_1p8>;
        interrupts-extended = <&tlmm 67 IRQ_TYPE_LEVEL_LOW>;
        reset-gpios = <&tlmm 66 GPIO_ACTIVE_HIGH>;
        touchscreen-size-x = <1200>;  touchscreen-size-y = <1920>;
    };
};

&blsp_i2c8 {
    backlight@2c {
        compatible = "ti,lp8556";  reg = <0x2c>;
        enable-supply = <&vreg_bl_vddio>;
        dev-ctrl = /bits/ 8 <0x87>;   // pwm + i2c combined, 12-bit
        init-brt = /bits/ 8 <0x7f>;   // 50%
    };
};

&mdss_dsi0 { panel@0 {
    compatible = "boe,tv101wum-nx0", "novatek,nt51021";
    avdd-supply = <&lcd_pwr>;
    reset-gpios = <&tlmm 62 GPIO_ACTIVE_LOW>;
}; };

&remoteproc_mss { firmware-name = "mba.mbn", "modem.mdt"; status = "okay"; };
```

### 2.3 普通版对比

`sdm660-xiaomi-clover.dts` → `model = "Xiaomi Mi Pad 4 LTE"`，`compatible = "xiaomi,clover-lte"`，include 的是 `sdm660-xiaomi-clover-regular-common.dtsi`（Plus 用的是 `-common.dtsi`）。**两者触控/面板确实不同**，Plus 走 goodix + BOE。

### 2.4 驱动存在性验证（HTTP 200 = 文件在）

| 文件 | 结果 |
|---|---|
| `drivers/gpu/drm/panel/panel-novatek-nt51021.c` | **200** ✅ |
| `drivers/video/backlight/lp855x_bl.c` | **200** ✅ |
| `drivers/input/touchscreen/goodix.c` | **200**，内含 `{ .id = "9110", .data = &gt911_chip_data }` ✅ |
| `drivers/gpu/drm/panel/panel-boe-tv101wum-nx0.c` | 404（由 nt51021 驱动覆盖，属正常） |
| `drivers/input/touchscreen/goodix_ts.c` | 404（mainline 文件名是 `goodix.c`） |

### 2.5 `sdm660-xiaomi-clover-common.dtsi` 里的 compatible

```
gpio-keys | qcom,rpm-pm660-regulators | qcom,rpm-pm660l-regulators
qcom,sdm660-internal-sndcard | qcom,wcn3990-bt | ramoops
regulator-fixed | shared-dma-pool | simple-framebuffer
```

另有 `&lpass_codec`、`&pm660l_codec`、`&qusb2phy0`、`&usb3_dwc3`、`&wifi` 等节点override。

---

## 3. 设备 wiki 状态（Nura / postmarketOS）

来源：<https://wiki.nura.eco/wiki/Xiaomi_Mi_Pad_4_(xiaomi-clover)>，页面修订 2026-09-27

| 分类 | 项目 |
|---|---|
| Works | Flashing / USB Networking / Internal storage / SD / Battery / Screen / Touchscreen / 3D Acceleration / Bluetooth / FDE / Accelerometer |
| Partial | Audio / Wi-Fi |
| Broken | Camera / Camera Flash / GPS / Calls / SMS / Mobile data / USB OTG / Magnetometer / Ambient Light / Proximity / Hall Effect |

设备分类：`testing`；U-Boot：Primary Broken、Secondary Works、Mainline Partial、USB Host Broken。

---

## 4. 关键数字汇总

| 项 | 值 |
|---|---|
| SoC | SDM660（4×Kryo 260 Gold 2.2 GHz + 4×Silver 1.8 GHz，Adreno 512） |
| 屏幕 | 10.1" 1920×1200 IPS（DTS 里触控上报 1200×1920 竖屏坐标系） |
| 电池 | 8 620 mAh（DTS `charge-full-design-microamp-hours`） |
| 机型代号 | `xiaomi-clover`；变体 `clover` / `cloverlte` / `cloverplus` |
| 内核 | 7.0.14-sdm660（pmaports edge 当前），wiki 记 6.13 |
| 设备包 | `device/testing/device-xiaomi-clover` |
