# 18 · 完整硬件清单（48 项，Android V10.3.2.0 实测）

> 采集环境：MIUI V10.3.2.0.ODJCNXM（Android 8.1，内核 4.4.78，2019-05-15）
> 设备：Xiaomi Mi Pad 4 Plus（clover-plus / SDM660），序列号 27eec4d2
> Root：Magisk 26.4（用当前 ROM 的 boot.img 现打补丁）
> 采集时间：2026-10-24 19:42 ~ 20:18
> 数据文件：`evidence/android-v1032-*.txt`（12 份，约 205 KB）

---

## 零、总览

| 分类 | 数量 | 状态 |
|---|---|---|
| **存在且已确认** | **45** | ✅ |
| **确认不存在** | **3** | ❌ 振动马达 / 按键背光 / FM 收音 |

---

## 一、I2C 总线地图（完整）

| Android | 地址 | 设备 | pmOS 状态 |
|---|---|---|---|
| i2c-2 (`c176000`) | 0x1d | `smb1351-charger` | ❌ 缺驱动 |
| i2c-3 (`c177000`) | 0x38 | `fts`（FocalTech 触摸） | ❌ 缺（备选） |
| i2c-3 (`c177000`) | 0x5d | `gt9xx`（Goodix GT9110） | ✅ `gt9110` |
| **i2c-6 (`c1b6000`)** | **0x4c** | **`tas2557s` 左功放** | ❌ **缺 DTS** |
| **i2c-6 (`c1b6000`)** | **0x4e** | **`tas2557s` 右功放** | ❌ **缺 DTS** |
| i2c-8 (`c1b8000`) | 0x2c | `lp8556`（背光升压） | ✅ `lp8556` |

**SDM660 全部 I2C 控制器**（`/proc/device-tree/soc/`）：
```
i2c@c175000  i2c@c176000  i2c@c177000  i2c@c178000
i2c@c1b5000  i2c@c1b6000  i2c@c1b7000  i2c@c1b8000
```

---

## 二、显示与视觉

### 2.1 屏幕

| 项 | 值 |
|---|---|
| 面板 | **BOE NT51021**（`mdss_dsi_nt51021_boe_10wu_wuxga_video`） |
| 分辨率 | 1200 × 1920 |
| 接口 | DSI-1，单 DSI |
| cmdline 参数 | `mdss_mdp.panel=1:dsi:0:qcom,mdss_dsi_nt51021_boe_10wu_wuxga_video:config0:1:none:cfg:single_dsi` |
| 驱动 | `panel-novatek-nt51021.c`（主线已有） |
| pmOS | ✅ 已支持，1200x1920 |

### 2.2 背光

| 项 | 值 |
|---|---|
| 芯片 | **TI LP8556** |
| I2C | `i2c-8`（Android）/ `i2c-1`（pmOS）@ **0x2c** |
| sysfs | `/sys/class/backlight/lcd-backlight` |
| 范围 | 0 - 255（Android 实测 max=255） |
| WLED 通道 | `/sys/class/leds/wled`，0 - **4095** |
| pmOS | ✅ 已支持（`lp855x_bl.c`） |

### 2.3 RGB 呼吸灯（新发现）

| 项 | 值 |
|---|---|
| 控制器 | **PM660L QPNP LED**，SPMI 寄存器 **0xd000** |
| DT 路径 | `800f000.qcom,spmi/spmi-0/spmi0-03/...pm660l@3:qcom,leds@d000/leds` |
| 通道 | `red` / `green` / `blue`，各 **0-255** |
| **Android 驱动** | `CONFIG_LEDS_QPNP=y`（老式 Qualcomm，**主线没有**） |
| **主线现状** | ❌ 无 `leds-qpnp.c`；有 `leds-qcom-lpg.c`（`CONFIG_LEDS_QCOM_LPG=m` 已开） |

**呼吸灯专用参数**（只有 `red` 有，因为它是主通道）：
```
blink         闪烁开关
duty_pcts     占空比百分比（呼吸曲线）
lut_flags     LUT 模式标志
pause_hi      高电平保持时间
pause_lo      低电平保持时间
pwm_us        PWM 周期（微秒）
ramp_step_ms  渐变步进（呼吸平滑度）
start_idx     LUT 起始索引（呼吸模式选择）
```

**可用 trigger（呼吸效果的来源）**：
```
battery-charging-blink-full-solid   ← 充电呼吸（闪烁+常亮）
battery-charging / battery-full / battery-charging-or-full
dc-online / usb-online / main-online / pc_port-online
rfkill0 / rfkill1                   ← WiFi / 蓝牙
mmc0 / mmc1                         ← 存储活动
bms-online
switch0_trigger / flash0_trigger / flash1_trigger
torch0_trigger / torch1_trigger
```

**实测状态**：`red = 255`（全亮），`green = 0`，`blue = 0`

**pmOS 现状**：`sdm660-xiaomi-clover-common.dtsi` 里已有一个 `led@3` 节点
（`color = <LED_COLOR_ID_WHITE>`, `function = LED_FUNCTION_STATUS`），但**没有 RGB 三色节点**。

### 2.4 闪光灯 / 手电筒

| 项 | 值 |
|---|---|
| 控制器 | **PM660L QPNP Flash**，SPMI **0xd300** |
| DT | `pm660l_flash: led-controller@d300 { compatible = "qcom,pm660l-flash-led", "qcom,spmi-flash-led"; status = "disabled"; }` |
| LED | `led:flash_0`（0-1500）、`led:flash_1`、`led:flash_2` |
| 手电筒 | `led:torch_0`、`led:torch_1`、`led:torch_2`、`torch-light0`、`torch-light1` |
| 开关 | `led:switch_0`、`led:switch_1` |
| Android 驱动 | `CONFIG_LEDS_QPNP_FLASH_V2=y` |
| **pmOS** | ⚠️ 有 `leds-qcom-flash.c` 但 `# CONFIG_LEDS_QCOM_FLASH is not set`；DT 节点默认 disabled |

---

## 三、输入设备

### 3.1 触摸屏

| 项 | 值 |
|---|---|
| 芯片 | **Goodix GT9110**（`gt9xx`，兼容 ID `gt9110`） |
| I2C | `i2c-3`（Android）/ `i2c-0`（pmOS）@ **0x5d** |
| 中断 | GPIO 相关（见 `/proc/bus/input/devices`） |
| input 名 | `goodix-ts`，`Bus=0018 Vendor=dead Product=beef` |
| 能力 | `PROP=2`（直接输入），`EV=b`（SYN+KEY+ABS） |
| 固件 | `/persist` 里有校准；`File VID == Ic VID, update aborted` |
| **备选芯片** | FocalTech `fts` @ i2c-3 **0x38**（本机未使用） |
| pmOS | ✅ 已支持（`goodix.c`） |

### 3.2 实体按键（gpio-keys）

| 按键 | GPIO 编码 | 键码 | sysfs 名 |
|---|---|---|---|
| **音量+** | `<0x1d2 0x07 1>` = GPIO **466**, pin 7, active-low | **115**（KEY_VOLUMEUP） | `vol_up` |
| **相机对焦** | `<0x0e8 0x40 1>` = GPIO **232**, pin 64 | **528**（KEY_CAMERA_FOCUS） | `camera_focus` |
| **相机快门** | `<0x0e8 0x71 1>` = GPIO **232**, pin 113 | **766**（KEY_CAMERA_SNAPSHOT） | `camera_snapshot` |

**共同属性**：
```
compatible          = "gpio-keys"
input-name          = "gpio-keys"
debounce-interval   = <15>          ← 15 ms
pinctrl-names       = "tlmm_gpio_key_active", "tlmm_gpio_key_suspend"
vol_up 有 gpio-key,wakeup           ← 可唤醒
status              = "okay"
```

**电源键**：走 **`qpnp_pon`**（PM660 PON），不在 gpio-keys
```
N: Name="qpnp_pon"
H: Handlers=event0 cpufreq
B: KEY=14000000000000 0
```

> **注意**：这台平板**没有独立音量减键**。`vol_up` 是 gpio-keys，
> 音量减可能通过 `qpnp_pon` 的 resin（长按电源）实现，或根本不存在。

**pmOS 现状**：`gpio_keys` 节点存在，但需确认是否有 `camera_focus` / `camera_snapshot`。

### 3.3 耳机 / 按键 Jack

| 项 | 值 |
|---|---|
| 耳机检测 | `sdm660-snd-card Headset Jack`（ALSA），`EV=21 SW=780d4` |
| 按键 Jack | `sdm660-snd-card Button Jack`，`PROP=40`，`KEY=3e 400000000` |
| MBHC | `wcd_mbhc_start`，`qcom,msm-mbhc-usbc-audio-supported` 缺失（跳过 USB-C 模拟音频） |

---

## 四、音频

### 4.1 内部 codec

| 项 | 值 |
|---|---|
| 模拟 codec | **PM660L WCD**（`qcom,pm8916-wcd-analog-codec`） |
| SPMI | `pmic@3` `audio-codec@f000`，reg **0xf000** |
| 数字 codec | `qcom,msm8916-wcd-digital-codec`，reg **0x152c0000** |
| 数字 codec phandle | `0x9e`，`sound-name-prefix = "Digital"` |
| 模拟 codec phandle | `0x9d` |
| 供电 | `vdd-micbias-supply = <&vreg_l7b_3p125>`，`qcom,micbias-lvl = <2600>`，`qcom,micbias1-ext-cap` |
| pmOS | ✅ 已支持（`msm8916-wcd-analog.c` / `-digital.c`） |

**关键寄存器（pmOS 实测，音频正常时）**：
```
f049 ANA_CLK_CTL     = 0x10   （SPKR_CLK_EN bit4）
f1b0 SPKR_DAC_CTL    = 0x83   （DAC_EN bit7）
f1b2 SPKR_DRV_CTL    = 0xef   （CLASS_D_PA_EN bit7）
f1b5 SPKR_PWRSTG_CTL = 0xff   （功率级全开）
f19E RX_EAR_CTL      = 0x13   （SPK_VBAT_LDO_EN bit0）
f193 RX_COM_BIAS_DAC = 0x99
```

### 4.2 扬声器功放：TI TAS2557（关键！）

| 项 | 值 |
|---|---|
| 芯片 | **TI TAS2557 智能功放**（`tas2557s`，DDC Name = D9） |
| I2C | **`i2c-6`（`c1b6000`）@ 0x4c（左）/ 0x4e（右）** |
| 版本 | `PG2.1 found` |
| hw_id | `D9P_LTE` |
| IRQ | 226（左），253（右） |
| **复位 GPIO** | **左 GPIO 80，右 GPIO 48** |
| 固件 | `/vendor/firmware/tas2557s_uCDSP_d9p.bin`（39,615 B）<br>`/vendor/firmware/tas2557s_uCDSP.bin`（39,615 B） |
| 调音 | `/system/etc/tas2557_stereo_TAS2557_d9p.ftcfg` 等 4 个 |
| 校准 | `/persist/audio/tas2557_cal.bin`（本机不存在，`Calibration 0 doesn't exist`） |
| 用户态 | `/dev/tas2557s`（misc，主设备号 229） |
| 驱动 | `/sys/bus/i2c/drivers/tas2557s` |
| 供电 regulator | **`cdc-vdd-spkdrv`**（Android 报 `regulator not found`，它自己硬编码找） |
| 芯片温度 | `Die=0x116a2aaa, degree=34` |

**Android 播放时的初始化序列**：
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

**主线驱动现状**：✅ **`CONFIG_SND_SOC_TAS2557=m` 已编译！**
```
sound/soc/codecs/tas2557.c
sound/soc/codecs/tas2557.h
Documentation/devicetree/bindings/sound/ti,tas2557.yaml
模块文件：lib/modules/7.0.14-sdm660/kernel/sound/soc/codecs/snd-soc-tas2557.ko.zst
```

**主线 DT 绑定要求**：
```yaml
compatible: "ti,tas2557"        # 注意：主线用 ti,tas2557，小米用 ti,tas2557s
reg: <0x4c>                      # 左，另一个 <0x4e> 右
reset-gpios: GPIO 80 / 48
vbat-supply / iovdd-supply / avdd-supply / dvdd-supply
ti,channel: 0 (左) / 1 (右)
ti,imon-slot-no: 默认 0
ti,vmon-slot-no: 默认 2
firmware-name: 可选，默认 tas2557_uCDSP.bin
```

**TAS2557 的 mixer 控件（Android，pmOS 没有）**：
```
74  ENUM  EAR PA Boost     ENABLE
75  ENUM  EAR PA Gain      POS_1P5_DB
77  ENUM  Ext Spk Boost    DISABLE
102 ENUM  SPK              ZERO
106 ENUM  WSA Spk Switch   ZERO
107 ENUM  Ext Spk Switch   Off
```

### 4.3 Android 的扬声器路由

```xml
<path name="compress-offload-playback speaker">
    <ctl name="PRI_MI2S_RX Audio Mixer MultiMedia4" value="1" />
</path>
<path name="deep-buffer-playback speaker">
    <ctl name="PRI_MI2S_RX Audio Mixer MultiMedia1" value="1" />
</path>
```

**Android 用 `PRI_MI2S_RX`，pmOS 用 `INT0_MI2S_RX`。** 但实际音频路径是：
```
AP -> DSP(ASM) -> AFE(某 MI2S) -> I2S 总线 -> TAS2557 -> 扬声器
                                              ↑
                                    pmOS 在这里断了（无 DTS 节点）
```

### 4.4 麦克风

| 项 | 值 |
|---|---|
| 模拟 | AMIC1 / AMIC2（`MIC BIAS External1/2`） |
| 数字 | DMIC1 - DMIC4 |
| ADC | ADC1 / ADC2 / ADC3 |
| PDM | PDM_RX1 / PDM_RX2 / PDM_RX3 |
| 耳机麦克风 | 经 MBHC 检测 |

### 4.5 音频 DSP

| 项 | 值 |
|---|---|
| ADSP | `15700000.remoteproc`（glink-edge） |
| APR 服务 | `apr_audio_svc`，service 4、7、8 |
| 前端 | MultiMedia1-16、VoiceMMode1/2、VoIP、ULL、MM_NOIRQ |
| 后端 | INT0-INT5 MI2S_RX、PRI/SEC/TER/QUAT MI2S_RX、PRI/SEC/TER/QUAT TDM、SLIMBUS_0-8、HDMI、DISPLAY_PORT、AUXPCM、AFE-PROXY |
| pmOS | ✅ 已支持（`q6asm` / `q6afe` / `q6routing`） |

---

## 五、摄像头

### 5.1 硬件配置（从 vendor.img 的 camera_config.xml）

**CameraId 0 — 后置主摄**

| 项 | 值 |
|---|---|
| Sensor | **OV13855**（`ov13855_f13v10l`），13MP |
| Actuator | `bu64297_f13v10l`（VCM 对焦） |
| EEPROM | `qtech_ov13855` |
| Chromatix | `ov13855_f13v10l_chromatix` |
| Position | **BACK** |
| MountAngle | **90** |
| CSI | csiphy0 / csid0，`CSIDCore=0` |
| LaneMask | **0x1F**（4 lane） |
| LaneAssign | **0x4320** |
| LensInfo | 3.44mm, f/2.0, 67.8°×53.1°, 最近 0.1m |

**CameraId 2 — 前置**

| 项 | 值 |
|---|---|
| Sensor | **S5K5E8**（`s5k5e8`），5MP |
| EEPROM | `qtech_s5k5e8` |
| Chromatix | `s5k5e8_chromatix` |
| Position | **FRONT** |
| MountAngle | **270** |
| CSI | csiphy2 / csid2，`CSIDCore=2` |
| LaneMask | **0x7**（2 lane） |
| LaneAssign | **0x4320** |
| LensInfo | 2.639mm, f/2.0, 57.5°×44.8° |

> 还有一个 `s5k3p8sp_chromatix.xml` 存在但配置里未启用（别的机型或备选）。

### 5.2 设备树节点（MIUI 原厂 DTB 实测）

| 节点 | csiphy | csid | CCI master | 复位/待机 | MCLK |
|---|---|---|---|---|---|
| `qcom,camera@0` | 0 | 0 | 0 | `CAM_RESET0`, `CAM_STANDBY0` | `CAMIF_MCLK2` |
| `qcom,camera@1` | 1 | 1 | 1 | `CAM_RESET1` | `CAMIF_MCLK1` |
| `qcom,camera@2` | 2 | 2 | — | — | — |

**电源**：`cam_vio`（固定）、`cam_vana`、`cam_vdig`，均为固定稳压器：
```
cam_avdd_fixed_regulator          = 2,800,000 µV
cam_avdd_front_fixed_regulator    = 2,800,000 µV
cam_vaf_fixed_regulator           = 2,800,000 µV
cam_rear_dvdd_fixed_regulator     = 1,200,000 µV
```

**其他**：`qcom,actuator@0`、`qcom,eeprom@0/1/2`、`qcom,camera-flash@0`、`qcom,csiphy@c824000/c825000/c826000`、`qcom,cci@ca0c000`

### 5.3 主线支持

| 项 | 状态 |
|---|---|
| camss 驱动 | ✅ `camss.c:5328 { .compatible = "qcom,sdm660-camss", .data = &sdm660_resources }` |
| 上游 DTS | ✅ `sdm630.dtsi:2061 camss: camss@ca00020` + `cci: cci@ca0c000` |
| OV13855 驱动 | ❌ **无**（有 `ov13858.c`，同系列可派生） |
| S5K5E8 驱动 | ❌ **无**（有 `s5k5baf.c`，不同代） |
| BU64297 VCM | ❌ 无（有 `dw9807-vcm.c`） |
| 板级 DTS | ❌ 完全没有摄像头节点 |
| pmOS 现状 | 只有 `/dev/video0,1`（venus 视频解码），无 `/dev/media*` |

---

## 六、指纹

| 项 | 值 |
|---|---|
| 芯片 | **FPC1020**（`fpc,fpc1020`） |
| 接口 | **SPI**（`spi-max-frequency = <1000000>`，1 MHz） |
| IRQ | GPIO **232**, pin 71 → IRQ **269** |
| RST | GPIO **232**, pin 108 |
| 时钟 | `iface_clk` (gcc 0x2e), `core_clk` (gcc 0x34) |
| pinctrl | 8 组：`fpc1020_avdd_active/suspend`、`_vddio_active/suspend`、`_reset_reset/active`、`_irq_active/suspend` |
| input 名 | `fpc1020` → `uinput-fpc`（input6） |
| HAL | `/vendor/lib64/hw/fingerprint.fpc.so`（143,624 B） |
| 服务 | `android.hardware.biometrics.fingerprint@2.1-service`（28,168 B） |
| **TEE 固件** | `/firmware/image/fpctzapp.{mdt,b00..b07}`（约 657 KB） |
| TEE 加载 | `QSEECOM: App with id 393221 (fpctzapp) now loaded` |
| 属性 | `ro.hardware.fingerprint = fpc` |
| pmOS | ❌ **无驱动 + 无 TEE（QSEECOM）** |

**评估**：指纹匹配在 **TEE（Qualcomm QSEECOM）** 里跑，`fpctzapp` 是闭源固件。
mainline 只有 `optee` 和 `qcom_qseecom.c`（UEFI 用），**无法运行 fpctzapp**。
**短期内不可能实现。**

---

## 七、传感器

### 7.1 pmOS 侧（IIO，已支持 5 个）

pmOS 通过 `qcom_smgr` 驱动走 **QRTR/glink → ADSP**，直接读 SMGR 服务：

| 传感器 | 说明 |
|---|---|
| 加速度计 | `in_accel_*` |
| 陀螺仪 | `in_anglvel_*` |
| 磁力计 | `in_magn_*` |
| 接近 | `in_proximity_*` |
| **环境光（ALS）** | 已修好（需两个内核补丁，见 doc 13/15） |

### 7.2 Android 侧（不同栈）

**Android 的 IIO 只有 1 个设备**（PM660 RRADC，充电监测）：
```
iio:device0 = 800f000.qcom,spmi:qcom,pm660@0:rradc@4500
  in_current_usbin_i_raw = 91
  in_voltage_usbin_v_raw = 220
  in_temp_skin_temp_raw  = 1206      ← 皮肤温度
```

**运动传感器走 SLPI（ADSP）**，通过 QMI/SNS，**不走 IIO**：
```
/vendor/etc/sensors/sensor_def_qcomdev.conf
/sys/class/ssc/
```

> **pmOS 的传感器支持其实比 Android 的 IIO 更完整。**
> Android 的 `/sys/class/ssc` 和 pmOS 的 `qcom_smgr` 是同一个 ADSP 子系统的两种访问方式。

### 7.3 霍尔传感器（合盖检测）

**未找到独立霍尔节点。** 之前 doc 09 分析过：可能复用磁力计的 Z 轴做合盖检测。
**用户没有磁铁，仍未实测。**

---

## 八、无线

### 8.1 WiFi

| 项 | 值 |
|---|---|
| 芯片 | **Qualcomm WCN3990**（SDM660 内置） |
| pmOS 驱动 | ✅ `ath10k_snoc` |
| MAC | **`00:0a:f5:7b:1d:93`** |
| MAC 存储 | `/persist/wlan_mac.clover`（33 字节） |
| 校准文件 | `/firmware/image/bdwlan.b0a / b0b / b0d / b0e / b30` |
| 配置文件 | `/vendor/etc/wifi/WCNSS_qcom_cfg.ini` |
| 固件目录 | `/vendor/firmware/wlan/qca_cld` |
| pmOS 状态 | ✅ 工作正常（`wlan0 = 192.168.1.123`） |

### 8.2 蓝牙

| 项 | 值 |
|---|---|
| 芯片 | WCN3990 的 BT 部分（`BTFM.bin`） |
| pmOS 驱动 | ✅ BTFM（`btqca`） |
| MAC | 从 `/persist/bluetooth/` 读 |
| 固件 | `/vendor/firmware/*btf*`、`*.tlz` |

### 8.3 FM 收音（不存在）

```
/Vendor/bin/fm_qsoc_patches       36,096 B   ← 二进制存在
/vendor/bin/init.qti.fm.sh         2,748 B
getprop: [vendor.fm.a2dp.conc.disabled] = [true]

❌ /dev/radio0 不存在
❌ /sys/class/ 里无 fm / dvb 类
❌ dmesg 无 fm/iris 日志
```

**判定**：FM 芯片可能在（WCN3990 里有 FM 功能），但**没有暴露 `/dev/radio0`**，
这个第三方 ROM 可能裁剪了 FM 驱动。

### 8.4 GPS / GNSS

| 项 | 值 |
|---|---|
| 服务 | `qti_gnss_service`、`loc_launcher`（83,440 B） |
| 接口 | **全走 QMI（ADSP 里的 GNSS 子系统）** |
| `/dev/gnss` | ❌ 不存在 |
| `/dev/gps` | ❌ 不存在 |
| memshare | `memshare_GPS segments` |
| 缺陷 | `init: cannot find '/system/bin/tloc_daemon'`（ROM 不完整） |
| pmOS | ❌ 缺 ADSP GNSS QMI 支持 |

### 8.5 Modem / 基带

| 项 | 值 |
|---|---|
| 基带 | SDM660 内置 |
| 固件 | `NON-HLOS.bin`（112 MB）→ `modem` 分区 |
| pmOS | 部分支持（`rmnet`），但无 SIM 卡（WiFi 版） |

---

## 九、电源

### 9.1 电池

| 项 | 值 |
|---|---|
| 化学 | **Li-poly** |
| 设计容量 | **8,620 mAh**（`charge_full_design = 8620`） |
| 实测 | capacity 62%，4,027,089 µV，-118,652 µA（放电），23.0°C |
| health | Good |
| Android 独有属性 | `qnovo`（寿命优化）、`sw_jeita_enabled`（温度保护）、`step_charging_enabled`、`dp_dm`（QC 快充协商）、`resistance_id`、`rerun_aicl`、`input_current_limited`、`die_health`、`charge_type` |
| pmOS | ✅ 基本支持（`qpnp-smb2`），但缺 Qnovo/JEITA |

### 9.2 充电器

| 芯片 | 接口 | 说明 |
|---|---|---|
| **SMB1351** | `i2c-2`（`c176000`）@ **0x1d** | 并充/快充识别，`smb1351_parallel_charger_probe: successfully probed` |
| **PM660 SMB2** | SPMI `pmic@0` | 主充电器，`QPNP SMB2 probed successfully` |
| **SMB138X** | — | 模块 `smb138x_charger` 已加载 |

**USB-PD 完整支持**：
```
type                    = USB_PD
typec_mode              = Source attached (default current)
typec_power_role        = dual power role    ← 双角色
typec_cc_orientation    = 2
pd_allowed / pd_active  = 0 / 0
voltage_now             = 4,785,156 µV
current_max             = 500,000 µA
input_current_now       = 468,730 µA
real_type               = USB
sdp_current_max         = 500,000
```

**pmOS 现状**：`usb_type = Unknown SDP [DCP] CDP`，只支持基本充电器类型，
**缺 SMB1351 驱动 → 不支持 QC 快充协商**（08 文档的"充电器 DCP 识别"问题）。

### 9.3 关机充电（支持）

| 项 | 值 |
|---|---|
| charger 可执行 | `/sbin/charger`（→ `/root/charger`） |
| init service | `service charger /charger`，`class charger`，`seclabel u:r:healthd:s0` |
| 快速充电监控 | `service qbcharger /charger -m 1`（`sys.qbcharger.enable=true` 触发） |
| charger_monitor | `/system/bin/charger_monitor` |
| **trigger** | **`on charger`** → `setprop persist.sys.usb.config mass_storage`、`start qcom-post-boot` |
| 电池图标 | `/res/images/charger/` 下 **9 张 PNG**：<br>`battery_scale.png`、`battery_fail.png`、<br>`Battery_red1/red2.png`、`Battery_green1/2/3.png`、<br>`Battery_0.png`、`Battery.png` |
| 电源原因 | PON 能报 `Hard Reset and 'cold' boot`、`PS_HOLD`、`GP1 (Keypad_Reset1)` |
| pmOS | ⚠️ 用 `msm_poweroff` 直接关机，**关机后插电不显示电池图标**（需专门实现） |

### 9.4 PON（电源键）

```
PMIC@SID0 (pm660)   Power-on:  Hard Reset and 'cold' boot
                    Power-off: PS_HOLD (MSM controlled shutdown)
PMIC@SID2 (pm660l)  Power-off: GP1 (Keypad_Reset1)
input 名: qpnp_pon, Handlers = event0, KEY=14000000000000
```

---

## 十、USB / OTG（完整支持）

| 项 | 值 |
|---|---|
| 控制器 | **`a800000.dwc3`**（Android）/ `a800000.usb`（pmOS，同一硬件） |
| state | `configured` |
| maximum_speed | `high-speed` |
| is_otg | `0`（当前非 OTG） |
| **双角色** | **`supported_modes = ufp dfp`** ✅ |
| 当前角色 | `mode = ufp`, `power_role = sink`, `data_role = device` |

**extcon（2 个）**：
```
extcon0 = qpnp-smb2     state: USB=0  USB-HOST=0  USB-CC=0  USB-SPEED=0
extcon1 = usb-pdphy     state: USB=1  USB-HOST=0  USB-CC=1  USB-SPEED=1
                                   ↑ USB-HOST 状态项存在
```

**内核模块**：`lpm_levels`、`lpm_stats`、`msm_poweroff`、`smb138x_charger`

**pmOS 现状**：`udc = a800000.usb`，`usb0 = 172.16.42.1/16`（gadget 已工作），
`usb_f_ncm` + `u_ether` + `libcomposite` 已加载。
**OTG 主机模式未实测**，但 DWC3 主线驱动成熟，大概率可用。

---

## 十一、其他

### 11.1 存储

| 项 | 值 |
|---|---|
| 内置 | eMMC，56 个分区，`userdata` 111,563 MB |
| 控制器 | `c0c4000.sdhci`（eMMC）、`c084000.sdhci`（SD） |
| SD 卡槽 | `/sys/class/mmc_host/` 有 mmc0 + mmc1 |
| pmOS | ✅ 已支持 |

### 11.2 GPU

| 项 | 值 |
|---|---|
| 型号 | **Adreno 512**（`kgsl-3d0`） |
| pmOS | ✅ 已支持（但 glamor 会触发 GPU hang，见 doc 07） |

### 11.3 视频编解码

| 项 | 值 |
|---|---|
| 硬件 | Venus（`cc00000.video-codec`） |
| pmOS | ✅ `/dev/video0,1` |

### 11.4 热管理

12 个 thermal zone（实测）：
```
aoss-thermal / cpuss0-thermal / cpuss1-thermal / cpu0/1/2/3-thermal
pwr-cluster-thermal / gpu-thermal / qcom-battery / pm660-thermal / pm660l-thermal
```

---

## 十二、确认不存在的硬件（3 项）

| 项目 | 判定依据 |
|---|---|
| **振动马达** | `/sys/class/timed_output/` 空<br>`/sys/class/leds/vibrator` 不存在<br>`init: Unable to open '/sys/class/leds/vibrator/trigger'`<br>`/proc/device-tree` 无 vib/haptics 节点 |
| **按键背光** | `/sys/class/leds/` 里只有 red/green/blue/wled/flash/torch，无 button/kbd 类<br>DT 里无 `*button*backlight*` |
| **FM 收音** | 有 `/vendor/bin/fm_qsoc_patches` 但 **`/dev/radio0` 不存在**<br>`/sys/class/` 无 fm/dvb 类<br>dmesg 无 fm 日志 |

---

## 十三、pmOS 待补齐优先级

| 优先级 | 设备 | 缺失 | 难度 | 可行性 |
|---|---|---|---|---|
| **1** | **扬声器（TAS2557）** | **只需 DTS 节点**（驱动已编译） | **低** | ⭐⭐⭐⭐⭐ |
| **2** | **实体按键** | camera_focus / snapshot | 低 | ⭐⭐⭐⭐⭐ |
| **3** | **摄像头** | OV13855/S5K5E8 驱动 + camss DTS | 中 | ⭐⭐⭐⭐ |
| **4** | **RGB 呼吸灯** | leds-qpnp 或 LPG | 中 | ⭐⭐⭐ |
| **5** | **快充/QC** | SMB1351 驱动 | 中 | ⭐⭐⭐ |
| **6** | **闪光灯** | 开 `CONFIG_LEDS_QCOM_FLASH` + DTS | 低 | ⭐⭐⭐⭐ |
| **7** | **关机充电** | 实现 charger 模式 | 中 | ⭐⭐ |
| **8** | **GPS** | ADSP GNSS QMI | 中 | ⭐⭐ |
| **9** | **睡眠** | DPU suspend 死锁 | 高 | ⭐⭐ |
| **10** | **指纹** | TEE + QSEECOM | 极高 | ⭐ |
| — | 振动/按键背光/FM | 硬件不存在 | — | — |

---

## 十四、数据文件索引

| 文件 | 大小 | 内容 |
|---|---|---|
| `evidence/android-v1032-hw.txt` | 61.7 KB | 第1轮 39 章节（音频/摄像头/传感器/显示/电源/存储/GPU/CPU/props/features） |
| `evidence/android-v1032-hw2.txt` | 72.0 KB | 第2轮 32 章节（指纹/按键/网络/GPS/霍尔/DT/充电/eMMC） |
| `evidence/android-v1032-hw3.txt` | 8.2 KB | 第3轮（按键 GPIO 键码、TAS2557、FPC1020、I2C 地图） |
| `evidence/android-v1032-dt.txt` | 8.5 KB | 设备树顶层节点 |
| `evidence/android-v1032-reg.txt` | 16.0 KB | 73 个 regulator 状态 |
| `evidence/android-v1032-led3.txt` | 8.5 KB | RGB 呼吸灯详情（trigger/呼吸参数） |
| `evidence/android-v1032-e2.txt` | 11.3 KB | 最终补采（soc 节点全列表、电池、persist） |
| `evidence/android-v1032-otg.txt` | 14.2 KB | **OTG + 关机充电** |
| `evidence/android-v1032-extra.txt` | 3.9 KB | 补采（persist 目录、WiFi 校准） |
| `evidence/hw-full-preflash-20261024.txt` | 23.2 KB | **pmOS 侧全量对照** |
| `artifacts/rom/vendor-camera/camera_config.xml` | 5.0 KB | 摄像头 sensor 配置 |
| `artifacts/rom/vendor-audio/mixer_paths.xml` | 104.9 KB | Android 音频路由 |
| `artifacts/rom/miui-dtb-0.dtb` | 346 KB | MIUI 原厂 DTB |

---

## 十五、复现命令

```powershell
# 前提：设备已 root（Magisk 26.4，用当前 ROM 的 boot.img 现打补丁）
# 关键：必须用 /sbin/magisk su，不能用 su 符号链接（会 Permission denied）

adb push tools/android_dump_light.sh /data/local/tmp/dump.sh
adb shell "/sbin/magisk su -c 'mkdir -p /sdcard/hw; sh /data/local/tmp/dump.sh'"
adb pull /sdcard/hw/dump.txt evidence/android-v1032-hw.txt
```

**踩过的坑**：
1. `su -c` 会 Permission denied → **必须用 `/sbin/magisk su -c`**
2. 采集脚本每段之间要 `sleep 1`，否则系统过载重启（load average 冲到 5.7）
3. 输出目录要先 `mkdir -p /sdcard/hw`（刷机后会被清）
4. 不要在 PowerShell 字符串里嵌 shell 的 `$(...)` 或反引号，会被 PS 抢先解析
5. 设备会不定期重启（这个第三方 ROM 不稳定），单条命令采集比长脚本可靠
6. `dumpsys sensorservice` 有时返回 "No Sensors on the device"（ROM 缺陷）
