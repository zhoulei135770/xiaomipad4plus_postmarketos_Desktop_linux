# 17 · Android vs pmOS 硬件数据对比（V10.3.2.0 采集）

> 采集时间：2026-10-24 19:42 ~ 19:51
> Android：MIUI V10.3.2.0.ODJCNXM（8.1.0，内核 4.4.78，2019-05-15），Magisk 26.4 root
> pmOS：postmarketOS Nura edge，内核 7.0.14-sdm660（mainline）
> 设备：Xiaomi Mi Pad 4 Plus（clover-plus / SDM660），序列号 27eec4d2
>
> 目的：用 Android 原厂的数据作为"标准答案"，指导 mainline 驱动补齐。

---

## 一、最终结论：扬声器无声的根因

### 1.1 硬件真相：TI TAS2557 智能功放（两颗）

```
i2c-6 (c1b6000) @ 0x4c  = tas2557s   ← 左声道
                        @ 0x4e  = tas2557s   ← 右声道

tas2557s 6-004c: tas2557_i2c_probe enter
tas2557s 6-004c: tas2557_parse_dt, left reset gpio 80
tas2557s 6-004c: tas2557_parse_dt, right reset gpio 48
tas2557s 6-004c: ti,left-channel=0x4c
tas2557s 6-004c: ti,right-channel=0x4e
tas2557s 6-004c: PG2.1 found
tas2557s 6-004c: irq = 226, 253
tas2557s 6-004c: hw_id_check: hw_id is D9P_LTE
tas2557s 6-004c: DDC Name = D9, Description = TI SmartAmp
tas2557s 6-004c: FW Size = 39615, Checksum = 0x1AE215C1
tas2557s 6-004c: PPC Version = 0x68700, FW Version = 0x1010000
tas2557s 6-004c: Driver Version = 0x0400
tas2557s 6-004c: Die=0x116a2aaa, degree=34
```

**关键资源：**

| 资源 | 值 |
|---|---|
| I2C 总线 | 6（`c1b6000.i2c`） |
| 地址 | 左 0x4c，右 0x4e |
| 复位 GPIO | 左 **80**，右 **48** |
| IRQ | 226（左），253（右） |
| 固件 | `/vendor/firmware/tas2557s_uCDSP_d9p.bin`（39,615 B） |
| 又一份 | `/vendor/firmware/tas2557s_uCDSP.bin`（39,615 B） |
| 调音配置 | `/system/etc/tas2557_stereo_TAS2557_d9p.ftcfg` 等 4 个 |
| 校准数据 | `/persist/audio/tas2557_cal.bin` |
| 驱动 | `tas2557s`（`/sys/bus/i2c/drivers/tas2557s`） |
| 用户态接口 | `/dev/tas2557s`（misc，主设备号 229） |
| 供电 regulator | **`cdc-vdd-spkdrv`** |

**Android 播放时 TAS2557 的完整初始化序列：**
```
tas2557_dai_startup
tas2557_hw_params -> setup_clocks: 48000 Hz
tas2557_set_bias_level: 1 -> 2 -> 3
tas2557_prepare
tas2557_mute
tas2557_enable: ref_count 0 -> 1
  -> load startup sequence (configuration_Tuning Mode_48 KHz_s1_0)
  -> load unmute sequence
IRQ status L: 0x2, R: 0x2
```

### 1.2 为什么 pmOS 无声

| 环节 | pmOS mainline | Android 原厂 |
|---|---|---|
| DSP 音频流 | ✅ 正常（ftrace 证实 q6asm/q6afe 全跑） | ✅ |
| 数字 codec | ✅ 寄存器全开（f049/f1b0/f1b2/f1b5） | ✅ |
| 模拟 codec | ✅ VBAT LDO 开（f19E bit0=1） | ✅ |
| **TAS2557 功放** | ❌ **无驱动，从未加载** | ✅ 完整工作 |
| **扬声器** | ❌ **无声** | ✅ **有声** |
| **听筒** | ❌ 无声（同样经过 TAS2557 的 EAR PA） | ✅ |

**这不是配置问题，是缺驱动。** mainline 假设扬声器由 PM660L 内部 Class-D 直接驱动，
但小米实际用了 TAS2557 外置智能功放。

**验证方式**：耳机有声（绕过 TAS2557，走 PM660L 内部 HPH PA）→ 证明 codec 和 DSP 都正常。

### 1.3 修复路径

**方案 A：移植 mainline TAS2557 驱动（推荐）**

Linux 主线有 `sound/soc/codecs/tas2557.c`（TI 在 2019 年提交）。需要：
1. 把 `tas2557.c` 加入内核
2. 设备树加 TAS2557 节点（I2C6 0x4c/0x4e，reset GPIO 80/48）
3. 配置 `cdc-vdd-spkdrv` regulator
4. 加 firmware（`tas2557s_uCDSP_d9p.bin`）
5. 修改 `sdm660-internal.c` 机器驱动，把 DAI link 接到 TAS2557

**难点**：小米用的 `tas2557s` 是 TI 的定制版本（`s` 后缀，D9P 硬件），
主线驱动可能需要适配。且需要 `/persist/audio/tas2557_cal.bin` 校准数据（我们已备份 persist）。

**方案 B：绕过 TAS2557（临时可用）**
用耳机或 USB 声卡。或者尝试让 PM660L 的 SPK_OUT 直连（需要改硬件，不现实）。

---

## 二、I2C 硬件地图（完整）

| Android 总线 | 地址 | 设备 | pmOS 状态 |
|---|---|---|---|
| i2c-2 (`c176000`) | 0x1d | `smb1351-charger` | ❌ 缺 |
| i2c-3 (`c177000`) | 0x38 | `fts`（FocalTech 触摸） | ❌ 缺（用 Goodix） |
| i2c-3 (`c177000`) | 0x5d | `gt9xx`（Goodix 触摸） | ✅ `gt9110` |
| **i2c-6 (`c1b6000`)** | **0x4c** | **`tas2557s` 左功放** | ❌ **缺** |
| **i2c-6 (`c1b6000`)** | **0x4e** | **`tas2557s` 右功放** | ❌ **缺** |
| i2c-8 (`c1b8000`) | 0x2c | `lp8556`（背光升压） | ✅ `lp8556` |

**pmOS 侧只有 2 个 I2C 设备（gt9110 + lp8556），其余都因缺驱动而未探测。**

---

## 三、硬件清单（Android 权威数据）

### 3.1 指纹：FPC1020

```
compatible       = "fpc,fpc1020"
status           = "okay"
input-device-name = "fpc1020"
fpc,gpio_irq     = <&tlmm 0xe8 0x47 0>   → GPIO 232, 引脚 71
fpc,gpio_rst     = <&tlmm 0xe8 0x6c 0>   → GPIO 232, 引脚 108
interrupts       = <0xe8 0x47 0>         → IRQ 269
interrupt-parent = <&tlmm>
spi-max-frequency = <1000000>            → SPI 1 MHz
clock-names      = "iface_clk", "core_clk"
clocks           = <&gcc 0x2e>, <&gcc 0x34>
pinctrl-names    = "fpc1020_avdd_active", "fpc1020_avdd_suspend",
                   "fpc1020_vddio_active", "fpc1020_vddio_suspend",
                   "fpc1020_reset_reset", "fpc1020_reset_active",
                   "fpc1020_irq_active", "fpc1020_irq_suspend"
```

**软件栈：**
```
/vendor/lib64/hw/fingerprint.fpc.so                              143,624 B
/vendor/bin/hw/android.hardware.biometrics.fingerprint@2.1-service  28,168 B
firmware/image/fpctzapp.{mdt,b00..b07}                           ~657 KB
system/com.qualcomm.qti.biometrics.fingerprint.service
```

**运行方式：TEE（QSEECOM）**
```
QSEECOM: qseecom_load_app: App (fpctzapp) doesn't exist, loading first time
QSEECOM: App with id 393221 (fpctzapp) now loaded
input: uinput-fpc as /devices/virtual/input/input6
```

**评估**：指纹在 TEE 里跑，mainline 完全没有 TEE 支持（QSEECOM）。
**移植难度极高**，需要：mainline TEE 驱动 + FPC1020 SPI 驱动 + TZ 里的 fpctzapp（闭源）。
**短期内无法实现。**

### 3.2 实体按键：gpio-keys

| 按键 | GPIO | 键码 | 名称 |
|---|---|---|---|
| `vol_up` | `<0x1d2 0x07 1>` = GPIO 466, pin 7, active-low | **0x73 = 115** KEY_VOLUMEUP | volume_up |
| `camera_focus` | `<0x0e8 0x40 1>` = GPIO 232, pin 64 | **0x210 = 528** KEY_CAMERA_FOCUS | camera_focus |
| `camera_snapshot` | `<0x0e8 0x71 1>` = GPIO 232, pin 113 | **0x2fe = 766** KEY_CAMERA_SNAPSHOT | camera_snapshot |

**共同属性：**
```
compatible = "gpio-keys"
input-name = "gpio-keys"
debounce-interval = <15>          ← 15 ms
pinctrl-names = "tlmm_gpio_key_active", "tlmm_gpio_key_suspend"
vol_up 有 gpio-key,wakeup（可唤醒）
```

**电源键**：走 `qpnp_pon`（PM660 PON），不�� gpio-keys
```
N: Name="qpnp_pon"
H: Handlers=event0 cpufreq
B: KEY=14000000000000 0        ← KEY_POWER(116) + KEY_VOLUMEDOWN(114)?
```

> **注意**：这台平板**没有独立的音量减键**！`vol_up` 是 gpio-keys，
> 音量减可能通过 `qpnp_pon` 的 resin（长按）实现，或者根本没有。

**评估**：gpio-keys 是最容易移植的。设备树加三个键即可。
pmOS 现在应该已经有 vol_up 和 power，但 `camera_focus`/`camera_snapshot` 可能缺失。

### 3.3 传感器

**Android 的 IIO 只有 1 个设备：**
```
iio:device0 = 800f000.qcom,spmi:qcom,pm660@0:rradc@4500
  in_current_dcin_i_raw     = (空)
  in_current_usbin_i_raw    = 91
  in_temp_skin_temp_raw     = 1206      ← 皮肤温度
  in_voltage_dcin_v_raw     = (空)
  in_voltage_usbin_v_raw    = 220
```

这是 **PM660 的 RRADC**（充电电流/电压/温度监测），不是运动传感器。

**运动传感器走 SLPI（ADSP）**，通过 QMI/SNS 接口，不走 IIO：
```
/vendor/etc/sensors/sensor_def_qcomdev.conf
dumpsys sensorservice  → "No Sensors on the device"（这次居然没读到）
```

> **对比 pmOS**：mainline 用 `qcom_smgr` 驱动走 QRTR 直接读 ADSP，
> 已经有 5 个传感器（accel/gyro/mag/prox/als）。
> **pmOS 的传感器支持其实比 Android 的 IIO 更完整**（Android 走的是另一套栈）。

### 3.4 背光：LP8556

```
i2c-8 (c1b8000) @ 0x2c = lp8556
```

**pmOS 也认到了**（`i2c-1 @ 0x2c = lp8556`），✅ 已支持。
Android 里背光是 `/sys/class/backlight/lcd-backlight`，pmOS 同名。

### 3.5 充电：SMB1351

```
i2c-2 (c176000) @ 0x1d = smb1351-charger
```

**pmOS 缺失**。这解释了 08 文档里"充电器 DCP 识别"的问题
——`smb1351` 是 Qualcomm 的快充识别芯片，pmOS 用的是 PM660 内部的
`qpnp-smb2`，可能只支持 SDP/DCP 基本识别，不支持 QC 快充协议。

### 3.6 GPS：QTI GNSS

```
init: starting service 'qti_gnss_service'
init: starting service 'loc_launcher'
/vendor/bin/loc_launcher                                    83,440 B
memshare_child qcom,client_1: for memshare_GPS segments only will be dumped
```

**没有 `/dev/gnss`** —— Android 的 GNSS 完全走 QMI（ADSP 里的 GNSS 子系统）。
启动日志显示 `tloc_daemon` 缺失（`cannot find /system/bin/tloc_daemon`），
说明这是个**功能不完整的 ROM**（第三方 MIUI 包常见）。

**评估**：pmOS 缺 `CONFIG_QCOM_Q6V5_PAS` 的 GNSS 支持或 ADSP GNSS 固件。
工作量中等，且需要 `gnss` 子系统的 QMI 服务。

### 3.7 摄像头：OV13855 + S5K5E8

（从 vendor.img 的 `camera_config.xml` 提取，见 doc 16）

```
CameraId 0 (后置)  ov13855_f13v10l  + bu64297_f13v10l + qtech_ov13855
                   CSI: csiphy0/csid0, LaneMask 0x1F, LaneAssign 0x4320
                   MountAngle 90, 3.44mm f/2.0

CameraId 2 (前置)  s5k5e8            + qtech_s5k5e8
                   CSI: csiphy2/csid2, LaneMask 0x7,  LaneAssign 0x4320
                   MountAngle 270, 2.639mm f/2.0
```

**Android 有完整的 /dev/video0-4 + /dev/media0-2**，pmOS 只有 venus（视频编解码）。

### 3.8 电源 / 电池

```
battery: status=2(充电中) health=2(良好) capacity=50-51% temp=31°C
充电电流 ~1,048,339 µA = 1.05 A
usb usbin_v = 220 (RRADC), usbin_i = 91
```

### 3.9 网络

```
wlan0: ath10k (WCN3990)，MAC 从 persist 读
bt0  : BTFM（蓝牙+FM）
rmnet: 基带数据（无 SIM，这台是 WiFi 版）
```

### 3.10 振动马达

```
/sys/class/timed_output/   → 空
/proc/device-tree 里无 vib/haptics 节点
```

**这台平板没有振动马达。**（与官方规格一致）

---

## 四、pmOS 待补齐清单（按可行性排序）

| 优先级 | 设备 | 缺失内容 | 难度 | 可行性 |
|---|---|---|---|---|
| **1** | **摄像头** | OV13855/S5K5E8 驱动 + camss DTS | 中 | ⭐⭐⭐⭐ 内核有 camss 支持，只差 sensor 驱动 |
| **2** | **扬声器** | TAS2557 驱动 + DTS + 固件 | 中 | ⭐⭐⭐ 主线有 tas2557.c 可参考 |
| **3** | **快充** | SMB1351 驱动 | 中 | ⭐⭐⭐ 主线有 smb1351 驱动 |
| **4** | **实体按键** | camera_focus/snapshot | 低 | ⭐⭐⭐⭐⭐ 只改 DTS |
| **5** | **GPS** | GNSS QMI 支持 | 中 | ⭐⭐ 需要 ADSP GNSS 固件 |
| **6** | **指纹** | TEE + FPC1020 SPI | **极高** | ⭐ 需要 QSEECOM（闭源） |
| — | 振动马达 | — | — | 硬件不存在 |
| — | 触摸 | — | — | ✅ 已支持（gt9110） |
| — | 背光 | — | — | ✅ 已支持（lp8556） |
| — | 传感器 | — | — | ✅ 已支持（5 个，比 Android IIO 更全） |
| — | WiFi/BT | — | — | ✅ 已支持（ath10k） |

---

## 五、关键寄存器对照（扬声器）

### Android 播放时（TAS2557 工作）
```
RX3 Digital Volume = 84
RX3 MIX1 INP1      = ZERO        ← 注意！Android 不用 RX3 路径
EAR PA Boost       = ENABLE
EAR PA Gain        = POS_1P5_DB
Ext Spk Boost      = DISABLE
Ext Spk Switch     = Off         ← 待机时 Off，播放时 On
SPK                = ZERO
```

### Android 的扬声器路由
```xml
<path name="compress-offload-playback speaker">
    <ctl name="PRI_MI2S_RX Audio Mixer MultiMedia4" value="1" />
</path>
```

**Android 用 `PRI_MI2S_RX` + `MultiMedia4`（compress-offload），
不是 pmOS 用的 `INT0_MI2S_RX` + `MultiMedia1`。**

但因为 TAS2557 是独立 I2S 从设备，实际音频路径是：
```
AP -> DSP(ASM) -> AFE(PRI_MI2S_RX) -> I2S 总线 -> TAS2557 -> 扬声器
                                              ↑
                                    这里 pmOS 断了（无驱动）
```

---

## 六、数据文件索引

| 文件 | 大小 | 内容 |
|---|---|---|
| `evidence/android-v1032-hw.txt` | 61.7 KB | 第一轮：39 章节（音频/摄像头/传感器/显示/电源/存储等） |
| `evidence/android-v1032-hw2.txt` | 72.0 KB | 第二轮：32 章节（指纹/按键/网络/GPS/霍尔/DT 等） |
| `evidence/android-v1032-hw3.txt` | 8.2 KB | 第三轮：按键 GPIO/键码、TAS2557、FPC1020、I2C 地图 |
| `evidence/android-v1032-dt.txt` | 8.5 KB | Android 设备树顶层节点列表 |
| `evidence/android-8.1-v1032-hw.txt` | 13.2 KB | 早期采集（V9.6.4.0 时期，含 V10.3.2.0 部分） |
| `evidence/hw-full-preflash-20261024.txt` | 23.2 KB | **pmOS 侧**全量数据（刷机前） |

---

## 七、复现步骤

```powershell
# 1. 设备需 root（Magisk 26.4，用当前 ROM 的 boot.img 现打补丁）
# 2. 上传脚本
adb push tools/android_dump_light.sh /data/local/tmp/dump.sh
adb push tools/android_dump2.sh /data/local/tmp/d2.sh
adb push tools/android_dump3.sh /data/local/tmp/d3.sh

# 3. 执行（必须用 /sbin/magisk su，不能用 su 符号链接）
adb shell "/sbin/magisk su -c 'sh /data/local/tmp/dump.sh'"
adb shell "/sbin/magisk su -c 'sh /data/local/tmp/d2.sh'"
adb shell "/sbin/magisk su -c 'sh /data/local/tmp/d3.sh'"

# 4. 取回
adb pull /sdcard/hw/dump.txt  evidence/android-v1032-hw.txt
adb pull /sdcard/hw/dump2.txt evidence/android-v1032-hw2.txt
adb pull /sdcard/hw/dump3.txt evidence/android-v1032-hw3.txt
adb pull /sdcard/hw/dt.txt    evidence/android-v1032-dt.txt
```

> **踩过的坑**：
> 1. `su -c` 会 Permission denied，**必须用 `/sbin/magisk su -c`**
> 2. 采集脚本每段之间要 `sleep 1`，否则系统过载重启
> 3. 输出目录要先 `mkdir -p /sdcard/hw`
> 4. 不要在 PowerShell 字符串里嵌 shell 的 `$(...)`，会被 PS 抢先解析
