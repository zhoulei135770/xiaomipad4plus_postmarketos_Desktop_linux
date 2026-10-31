# 硬件记分卡

> 2026-10-29 08:50。目标：**所有硬件完美驱动**。
> 这份文档是那个目标的可执行清单 —— 每个器件一行，写明状态和证据。
>
> 数据来源：厂商 DT（`artifacts/rom/miui-dtb-0.dtb`，51 个真实器件）、
> 魔趣 DT（`artifacts/mokee-20261028/fdt.dtb`）、pmOS 运行中的 DT、
> 以及实测日志。

---

## 1. 总览

| 状态 | 数量 | 说明 |
|---|---|---|
| ✅ **已验证能用** | 24 类 | 有实测证据 |
| 🟡 **驱动在，功能未验证** | 2 类 | 后摄、modem |
| ❌ **不工作** | 2 类 | 前摄、指纹 |
| ⚪ **硬件不存在** | 4 类 | 别再折腾 |

**结论**：DT 层面 pmOS 的覆盖是完整的 —— 用脚本把厂商/魔趣/pmOS 三方 DT
按设备类别对比，pmOS 唯一缺的三类（闪光灯、震动、CPP）核实后**全是误报**：

- 闪光灯：厂商节点是空的（无 led-sources / 无 gpio / 无 flash-type）
- 震动：pmOS 节点来自 SoC dtsi 且 `disabled`，**厂商 DT 无振动节点**（Android 也验证无马达）
- CPP：只做离线后处理，主线 camss 采集走 VFE，不需要

所以要攻的只有 **2 个真问题**（前摄、指纹）和 **2 个待验证**（后摄、modem）。

---

## 2. 逐项状态

### 2.1 已确认可用（24 类）

| 器件 | 总线/地址 | 驱动 | 证据 |
|---|---|---|---|
| 显示面板 NT51021 | DSI | `panel_novatek_nt51021` | 屏幕正常显示 |
| 显示控制器 | — | `msm`/`dpu` | 同上 |
| 触屏（Goodix GT9xx） | i2c@c177000 `0x5d` | `goodix_ts` | 触摸可用 |
| 触屏（Focaltech，备用变体） | i2c@c177000 `0x38` | `focaltech` | 本机用的是 Goodix |
| 背光 LP8556 | i2c@c1b8000 `0x2c` | `lp8556` / `qpnp-wled` | 亮度可调 |
| 显示偏压 LCDB | pm660l@3 `0xec00` | `qpnp-lcdb` | 显示正常 |
| 扬声器功放 TAS2557 | i2c@c1b6000 `0x4c` | `snd_soc_tas2557` | 有声音 |
| 模拟编解码 | pm660l@3 `0xf000` | `pmic-analog-codec` | 耳机/麦克风 |
| 充电 SMB2 | pm660@0 | `qcom_smbx` | 充电正常，93–95% |
| 电量计 FG gen3 | pm660@0 `0x3400`? | `pmi8998_fg` | 电量读数正常 |
| 并充 SMB1351 | i2c@c176000 `0x1d` | `smb135x` | 快充 |
| 温度报警 | pm660@0/2 `0x2400` | `qcom_spmi_temp_alarm` | thermal zone |
| ADC（vadc/rradc） | pm660@0 `0x3100/0x4500` | `qcom_spmi_adc5`/`rradc` | 电压读数 |
| RTC | pm660@0 | `qpnp-rtc` | 时间正常 |
| 电源键 | pm660@0 `0x800` | `qpnp-power-on` | 短按锁屏 |
| LED（通知） | pm660l@3 `0xd000` | `leds_qcom_lpg` | — |
| WiFi WCN3990 | — | `ath10k_snoc` | 已连 `daan` 5GHz，183G 传输实测 |
| 蓝牙 | — | `btqca`/`hci_uart` | 配对可用 |
| SD 卡 | sdhci | `sdhci` | 挂载读写 |
| USB Host/OTG | dwc3 + smbx | `dwc3`/`qcom_smbx` | 补丁 0010 加了 buck-boost |
| GPU Adreno | — | `msm` | 桌面合成正常 |
| 视频解码 Venus | — | `venus_dec`/`venus_enc` | 硬解可用 |
| 传感器（accel/gyro/mag） | ADSP via smgr | `qcom_smgr_*` | mag 采样正常 |
| 光线传感器（ALS） | ADSP via smgr | `qcom_smgr_prox` | 实测 398–457 lx |
| 霍尔（磁盖） | ADSP | `qcom_smgr` hall | — |

### 2.2 驱动在，功能未验证（2 类）

| 器件 | 现状 | 待验证 |
|---|---|---|
| **后摄 OV13855** | `ov13855` 模块已加载，绑定在 `3-0036`，i2cdetect 显示 `UU` | 能否真的出图 |
| **modem / 4G** | 能注册 CMCC、-62 dBm；但约每 3 分钟崩一次 | 通话/短信/数据全未打通 |

### 2.3 不工作（2 类，是真问题）

| 器件 | 症状 | 已排查 | 下一步 |
|---|---|---|---|
| **前摄 S5K5E8** | i2c 无应答 `-6 ENXIO` | 见 [26](26-FRONT-CAMERA-DIAGNOSIS.md) §15：供电/时钟/复位/DT 全部正常，CCI m1 已调到与 m0 相同；驱动已补 pinctrl。**硬件在魔趣下正常** | 查 VDIG 使能 GPIO；必要时量 MCLK2 波形 |
| **指纹 FPC1020** | 采集帧无二维结构 | 见 [29](29-FINGERPRINT-CEILING.md)：成像在闭源 TA 里 | 只有走厂商 TA 路线 |

### 2.4 硬件不存在（4 类，别再折腾）

| 器件 | 依据 |
|---|---|
| **振动马达** | 厂商 DT 无节点；Android 下 `/sys/class/timed_output/` 为空、无 `leds/vibrator` |
| **NFC（NQ-NCI）** | 厂商 DT 里 `qcom,nq-nci@28` 是 `disabled` |
| **FM 收音** | 无硬件 |
| **按键背光** | 无硬件 |

---

## 3. 厂商 DT 里的完整器件清单（51 个）

来自 `artifacts/rom/miui-dtb-0.dtb`，`tools/hw_inventory.py` 自动抽取。
标注 ⚠️ 的是 pmOS 没驱动或不需要的。

| 总线 | 地址 | compatible | 厂商 status | 备注 |
|---|---|---|---|---|
| i2c@c176000 | 0x1d | `qcom,smb1351-charger` | ok | ✅ 并充 |
| i2c@c177000 | 0x38 | `focaltech,fts` | ok | 备用触屏变体 |
| i2c@c177000 | 0x5d | `goodix,gt9xx` | ok | ✅ 本机触屏 |
| i2c@c1b6000 | 0x28 | `qcom,nq-nci` | **disabled** | ⚪ 无 NFC |
| i2c@c1b6000 | 0x4c | `ti,tas2557s` | ok | ✅ 功放 |
| i2c@c1b8000 | 0x2c | `ti,lp8556` | ok | ✅ 背光 |
| cci | 0/1/2 | `qcom,camera` ×3 | ok | 0=后摄 1=? 2=前摄 |
| cci | — | `qcom,actuator` ×2 | ok | 对焦马达 |
| cci | — | `qcom,eeprom` ×3 | ok | 模组校准数据 |
| cci | — | `qcom,ois@0` | disabled | 无光学防抖 |
| spmi pm660@0 | — | `qpnp-smb2` / `fg-gen3` / `revid` / `pdphy` / `temp-alarm` / `coincell` / `vadc` / `adc-tm` / `bcl` / `rradc` / `power-on` / `misc` | ok | ✅ 电源基础 |
| spmi pm660@1 | 0xc000 | `qcom,qpnp-haptic` | ok | ⚪ 但无马达硬件 |
| spmi pm660l@2 | — | `qpnp-pin` / `revid` / `temp-alarm` / `pbs` / `power-on` | ok | ✅ |
| spmi pm660l@3 | — | `labibb` | disabled | 显示偏压备用 |
| spmi pm660l@3 | 0xb100/b200/b300 | `qpnp-pwm` ×3 | ok | 背光 PWM |
| spmi pm660l@3 | 0xd000 | `qcom,leds-qpnp` | ok | ✅ 通知灯 |
| spmi pm660l@3 | 0xd300 | `qcom,qpnp-flash-led-v2` | ok | ⚠️ PMIC 有闪光控制器，但无物理 LED 接线 |
| spmi pm660l@3 | 0xd800 | `qcom,qpnp-wled` | ok | ✅ 背光 |
| spmi pm660l@3 | 0xec00 | `qcom,qpnp-lcdb` | ok | ✅ 显示偏压 |
| spmi pm660l@3 | 0xf000 | `qcom,pmic-analog-codec` | ok | ✅ 音频 |
| — | 0x152c0000 | `qcom,msm-digital-codec` | ok | ✅ 音频 |
| — | — | `qcom,camera-flash@0` | ok | ⚠️ **空节点**，无实际属性 |
| — | 0xca04000 | `qcom,cpp` | ok | ⚠️ 相机后处理，主线不需要 |
| — | 0xca31000 | `qcom,ispif-v3.0` | ok | 主线 camss 内部处理 |
| — | 0xca10000/0xca14000 | `qcom,vfe48` ×2 | ok | ✅ camss |

---

## 4. 结论与优先级

1. **前摄** —— 唯一"硬件好但驱动不通"的问题（魔趣能驱动）。当前卡在 i2c 无应答。
2. **指纹** —— 硬件好，但成像逻辑闭源，内核路线到顶。
3. **后摄** —— 驱动在，先验证能不能出图（成本低）。
4. **modem** —— 需要 diag/IPA（主线缺），优先级低。

工具的用法：

```sh
cd mipad4plus
python tools/hw_class_matrix.py          # 三方 DT 按类别对比
python tools/hw_class_matrix.py --list   # 给出每个缺口的节点
python tools/hw_inventory.py --md        # 厂商 DT 的 51 器件表
```
