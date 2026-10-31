
---

# 附录 A：完整器件清单（含"辅助"器件）

> 数据来源：厂商 DT（`miui-dtb`，51 个真实器件节点）、pmOS 运行中的 DT、实测日志。
> 这张表把**每一个能点名的器件**都列出来，包括不显眼但会影响体验的
> RTC、LED、热区、霍尔、SD 卡控制器等。

## A.1 显示与输入

| 器件 | 地址/总线 | 驱动 | 状态 | 说明 |
|---|---|---|---|---|
| 面板 NT51021（BOE 10.1" 1200×1920） | DSI0 | `panel_novatek_nt51021` | ✅ | 原生竖屏，靠 transform 90 转横屏 |
| 显示控制器 DPU | `c901000.display-controller` | `msm`/`dpu` | ✅ | 需要"pin MDSS/DSI"防挂起死锁 |
| 背光 LP8556 / WLED | i2c@c1b8000 `0x2c` | `lp8556` | ✅ | 亮度 0–255 可调 |
| 显示偏压 LCDB | pm660l@3 `0xec00` | `qpnp-lcdb` | ✅ | — |
| 触屏 Goodix GT9xx | i2c@c177000 `0x5d` | `goodix_ts` | ✅ | 需标定矩阵（见第 2 节） |
| 触屏 Focaltech（备用变体） | i2c@c177000 `0x38` | `focaltech` | — | 本机未使用 |
| 电源键 | pm660@0 `0x800` | `qpnp-power-on` | ✅ | 由 `tablet-powerkeyd` 处理 |
| 音量键 | GPIO / pm8941_resin | `gpio-keys` / `pm8941-pwrkey` | ✅ | 同上 |

## A.2 计算与视频

| 器件 | 驱动 | 状态 | 说明 |
|---|---|---|---|
| CPU 8×Cortex-A73/A53 | `qcom-cpufreq` | ✅ | 频率/热区正常 |
| GPU Adreno 512 | `msm`（a512） | 🔧 | 需四层加固（见第 3 节） |
| 视频解码 Venus | `venus_dec`/`venus_enc` | ✅ | mpv `v4l2m2m` 可用 |
| 相机 ISP（VFE/CSIPHY/CCI） | `qcom_camss` | ✅ | 后摄 raw 采集 |
| 后摄 OV13855 | `ov13855` + camss | ✅ | 自研 ISP 预览 |
| 前摄 S5K5E8 | `qcom_camss` i2c | ❌ | CCI 无 ACK（见第 13 节） |

## A.3 音频

| 器件 | 地址 | 驱动 | 状态 |
|---|---|---|---|
| 扬声器功放 TAS2557 | i2c@c1b6000 `0x4c` | `snd_soc_tas2557` | ✅ |
| 模拟编解码 WCD | pm660l@3 `0xf000` | `pmic-analog-codec` | ✅ |
| 数字编解码 | `152c0000.audio-codec` | `msm8916-wcd-digital-codec` | ✅ |
| ADSP 音频（q6afe/q6asm） | remoteproc | `q6afe`/`q6asm` | ✅ |
| 耳机检测 / 麦克风 | WCD | 同上 | ✅ |

## A.4 连接

| 器件 | 驱动 | 状态 | 说明 |
|---|---|---|---|
| Wi-Fi WCN3990 | `ath10k_snoc` | 🔧 | 稳，但受 modem 影响 |
| 蓝牙 WCN3990 | `btqca`/`hci_uart` | ✅ | — |
| 调制解调器 SDM660 | `qcom_q6v5_mss` + `qmi_helpers` | ⚠️ | 注网 3 分钟 assert（第 10 节） |
| IPA（数据面） | — | ❌ | 主线无 SDM660 IPA 驱动 |
| GPS/GNSS | QMI LOC | ⚠️ | 有响应无 fix（第 11 节） |
| QRTR | `qrtr_smd` | ✅ | `qrtr://0` 是正确节点 |

## A.5 电源与充电

| 器件 | 驱动 | 状态 |
|---|---|---|
| 主充电 SMB2 | `qcom_smbx` | ✅ |
| 并充 SMB1351 | `smb135x` | ✅ |
| 电量计 PMI8998 FG gen3 | `pmi8998_fg` | ✅ |
| 温度报警 / 热区 | `qcom_spmi_temp_alarm` | ✅ |
| ADC（VADC/RRADC） | `qcom_spmi_adc5` / `rradc` | ✅ |
| RTC | `qpnp-rtc` | ✅ |
| 通知 LED | `leds_qcom_lpg` | ✅（未做用户态策略） |

## A.6 传感器与其它

| 器件 | 通路 | 驱动 | 状态 |
|---|---|---|---|
| 加速度计 / 陀螺仪 / 磁力计 | ADSP (smgr) | `qcom_smgr_accel/gyro/mag` | ✅ |
| 环境光 ALS | ADSP (smgr) | `qcom_smgr` | ✅ 自动背光 |
| 距离传感器 | ADSP (smgr) | `qcom_smgr_prox` | ✅ |
| 霍尔（保护套） | GPIO | `gpio-keys` | ✅ 上报为按键 |
| 指纹 FPC1020 | SPI | `fpc1020` | ❌ 成像在闭源 TA（第 14 节） |
| SD 卡 | `sdhci` | `sdhci-msm` | ✅ |
| eMMC（系统盘） | `sdhci` | `sdhci-msm` | ✅ `/dev/mmcblk1` |
| USB 3.0 控制器 | dwc3 | `dwc3` | ✅ |
| USB-C 角色/充电检测 | SMB2 | `qcom_smbx` | 🔧 硬复位后失效（第 9 节） |
| 振动马达 | — | — | ⚪ **硬件不存在**（厂商 DT 无节点） |
| 闪光灯 | — | — | ⚪ **硬件不存在**（厂商节点为空） |

> ⚪ = 确认硬件不存在，不要浪费时间。

## A.7 未解决项一览（为什么）

| 项 | 卡在哪 | 需要什么才能解决 |
|---|---|---|
| 前摄 S5K5E8 | CCI 无 ACK，Android 下正常 | 示波器核对上电/时钟时序 |
| 指纹 FPC1020 | 成像与匹配在闭源 TEE TA | 官方 TA 或算法文档 |
| LTE 数据 | 缺 IPA 驱动 + modem assert | SDM660 IPA 上游驱动 + 厂商基带修复 |
| GPS | 依赖 modem 的 LOC 上报 | 同上（modem 稳定后才可能） |
| 真 suspend | `mdss_runtime_suspend` 死锁 | DPU/DSI 运行时 PM 修复 |
| GPU 满性能 | 下游内核 + 上游 Mesa 不匹配 | 内核与 Mesa 版本对齐 |
| OTG 硬复位后失效 | SMB2 CC 状态不一致 | PMIC 复位序列（无公开文档） |
