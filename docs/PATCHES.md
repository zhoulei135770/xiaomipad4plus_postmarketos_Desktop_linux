# 内核补丁说明（linux-postmarketos-qcom-sdm660）

> 目录里堆了 30+ 个 `.patch`，但 `APKBUILD` 的 `source=` 里**只应用 18 个**。
> 本文说明每个补丁做什么、能不能上游化。

---

## 一、实际应用的补丁（按 APKBUILD 顺序）

| # | 补丁 | 作用 | 上游化 |
|---|---|---|---|
| 1 | `0001-iio-qcom-smgr-use-per-sensor-data-type` | **ALS 修复核心**：`qcom_smgr.c` 把 `data_type` 硬编码为 0，环境光需要 1，否则 buffer 无法 enable | ✅ 应该上游 |
| 2 | `0002-dts-tas2557` | 扬声器功放 TAS2557 的设备树 | ✅ 应该上游 |
| 3 | `0003-ASoC-tas2557-unique-names` | TAS2557 多实例时控件/DAI 重名 | ✅ 应该上游 |
| 4 | `0005-ASoC-tas2557-16bit-slot` | TAS2557 匹配 16bit I2S 与右槽偏移 | ✅ 应该上游 |
| 5 | `0006-media-i2c-ov13855` | **新增 OV13855 后摄驱动**（13MP）| ✅ 值得上游（大贡献）|
| 6 | `0011-media-camss-ispif-clean` | ISPIF 清理/修复 | ✅ 候选 |
| 7 | `0015-media-camss-csid-phy-first` | CSID PHY 先于 ISPIF 使能 | ✅ 候选 |
| 8 | `0029-media-i2c-s5k5e8` | 新增 S5K5E8 前摄驱动 | ⚠️ 硬件未验证 |
| 9 | `0007-dts-camera` | 摄像头设备树（OV13855 + S5K5E8 + CCI）| ✅ 应该上游 |
| 10 | `0008-dts-usb-host` | USB host 模式 | ✅ 应该上游 |
| 11 | `0033-dts-fingerprint-spi` | FPC1020 指纹 SPI 设备树 | ✅ 应该上游 |
| 12 | `0034-dts-slow-i2c` | CCI master 1 降到 100 kHz | ⚠️ 本地变通（前摄调试遗留）|
| 13 | `0035-fpc1020-driver` | **新增 FPC1020 指纹驱动**（含取像协议）| ✅ 值得上游 |
| 14 | `0036-dts-venus-memory` | 给 venus 补 `memory-region` + `vcodec0_core` 时钟 | ⚠️ 必要但不充分（venus 仍不工作）|
| 15 | `0037-dts-disable-frontcam` | 禁用无电的前摄节点 | ❌ 仅本地（硬件问题）|
| 16 | `0038-dts-disable-venus` | 禁用不工作的 venus | ❌ 仅本地（临时）|
| 17 | `0010-smbx-otg-vbus` | SMBx 充电器加 OTG VBUS 控制 | ✅ 应该上游 |
| 18 | `0025-camss-cphy-csid-clk` | CPHY/CSID 时钟 | ✅ 候选 |

---

## 二、目录里有但**没有**应用的补丁（调试遗留）

这些是摄像头 bring-up 期间写的寄存器转储/诊断补丁，**不要应用**：

```
0011-media-camss-csiphy-debug-dump     CSIPHY 寄存器转储
0012-media-camss-csiphy-660-vendor-init 厂商初始化序列实验
0014-media-camss-csid-irq-diag          CSID 中断诊断
0016-media-camss-csiphy-status-dump     CSIPHY 状态转储
0019-media-camss-csid-hw-version        硬件版本探测
0021-media-camss-csid-lane-assign       通道分配实验
0024-media-camss-full-reg-dump          全寄存器转储
0028-media-camss-vfe-reset-dbg          VFE 复位调试
0031-arm64-dts-qcom-clover-enable-modem modem 使能（已存在于 board dts）
0032-arm64-dts-clover-i2c-gpio-front-camera  i2c-gpio 前摄（会抢 CCI 引脚，已废弃）
```

---

## 三、上游化建议

### 最容易推进的三个（改动小、影响明确）
1. **`0001` SMGR data_type** —— 一行修复，解决了 sdm660 的 ALS 完全不可用
2. **`0033`+`0035` FPC1020** —— 新驱动 + DT，指纹在 sdm660 平板上很常见
3. **`0010` SMBx OTG VBUS** —— 让 OTG 供电可控

### 最有价值的
- **`0006` OV13855 驱动** —— sdm660 平台上 13MP 主摄，目前 mainline 没有支持

### 需要更多验证才能提交
- `0029` S5K5E8（我们的硬件没电，从未真正 probe 成功过）
- `0036` venus（我们这边固件仍起不来）
- `0034` 降速 I2C（可能是本地硬件问题，不是通用修复）

### 仅本地保留
- `0037` / `0038`（禁用前摄 / 禁用 venus）—— 换成硬件修复或 venus 修好后应删除

---

## 四、维护提示

新增补丁时必须遵守的顺序规则（踩过的坑）：
1. 补丁按 `APKBUILD` 的 `source=` 顺序应用，**同文件的多补丁必须按此顺序生成**
2. `.dts` 里不能出现裸的顶层节点，必须包在 `/ { ... };` 里，或只用 `&label { }`
3. 改完跑 `pmbootstrap checksum`，再 `pmbootstrap chroot -b -- sh -c "rm -rf /home/pmos/build/*"`
   （不清构建目录会用到旧的 dts 副本，报奇怪的语法错）
