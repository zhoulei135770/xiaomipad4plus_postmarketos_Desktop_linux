# 前摄 S5K5E8 —— Android (MoKee) 侧数据与结论

采集时间：2026-10-26 19:40
设备：MI PAD 4 PLUS (clover)，MoKee 11 (RQ3A.210805.001.A1, userdebug)，内核 4.4.205-perf+
原始数据：`tools/android-cam-data/`

---

## 1. 最重要结论：**前摄硬件完全正常**

厂商内核启动时就探测成功：

```
[    7.660926] msm_sensor_fill_eeprom_subdevid_by_name:223 Eeprom userspace probe for qtech_s5k5e8
[    7.678892] msm_cci_init:1439: hw_version = 0x10060000
[    7.679558] s5k5e8 probe succeeded          ← 前摄探针成功
[    7.699381] msm_csid_init: CSID_VERSION = 0x30050000
[    7.706917] msm_csid_irq CSID2_IRQ_STATUS_ADDR = 0x800   ← 前摄走 CSID2
```

实际打开相机也成功（camera id 1 = 前摄）：

```
I/CameraHardwareInterface: Opening camera 1
I/QCamera: openCamera: [KPI Perf]: X PROFILE_OPEN_CAMERA camera id 1, rc: 0
I/mm-camera <SENSOR>: sensor info: name: s5k5e8, res: 0, max_fps: 30.000000,
    w: 2592, h: 1944, op pix clk: 167200000, FLL: 1968, LLPCK: 2856, mode: 1
```

⇒ **硬件、排线、供电都没问题。Linux 侧的问题是配置，不是器件。**

## 2. 厂商配置（`/vendor/etc/camera/camera_config.xml`）

| 字段 | 前摄 (CameraId=2) | 后摄 (CameraId=0) |
|---|---|---|
| SensorName | **s5k5e8** | ov13855_f13v10l |
| EepromName | qtech_s5k5e8 | qtech_ov13855 |
| Position | **FRONT** | BACK |
| CSIDCore | **2** | 0 |
| LaneMask | **0x7**（DL0+CLK+DL1 → **2 数据 lane**） | 0x1F（4 lane） |
| LaneAssign | 0x4320 | 0x4320 |
| MountAngle | **270** | 90 |
| Chromatix | s5k5e8_chromatix | ov13855_f13v10l_chromatix |

我们 DTB 用的 **csiphy2 / csid2 / 2 lane** 判断得到厂商配置确认 ✅

## 3. 关键时序参数（可直接校验驱动模式表）

```
分辨率      : 2592 x 1944
帧率        : 30 fps
op pix clk  : 167,200,000 Hz
FLL (VTS)   : 1968 行
LLPCK (HTS) : 2856 像素时钟
```

## 4. I2C 地址：仍未确定（这是最后一个未知量）

- HAL 日志（`persist.camera.sensor.debug=5`）**不打印 I2C 地址**
- 厂商内核 dmesg 也不打印
- Linux 侧已实测无应答的 7 位地址：**0x10、0x20、0x2D、0x5A、0x6C**
- 传感器库 `libmmcamera_s5k5e8.so` 里 `sensor_name` 结构体（偏移 0x3008）后紧跟着值
  `0x30`（可疑：**8 位 0x30 → 7 位 0x18**）、`1`、`2`……

**下次在 Linux 侧要试**：
1. 7 位地址 **0x18**（最可疑的新候选）
2. 上电后扫描 CCI master 1 上的 **0x50**（前摄 EEPROM）—— 这是一条决定性的"总线是否活着"测试：
   - 若 EEPROM 应答 → 供电和总线都正常，问题只在传感器地址
   - 若不应答 → 供电/时钟链路仍有问题

## 5. 已确认与 Linux 一致的点

| 项目 | 厂商 | 我们 |
|---|---|---|
| CSID 版本 | 0x30050000 (CSID 5.0) | ✔ 相同 |
| 前摄 CSID | CSID2 | ✔ csid2 |
| lane 数 | 2 | ✔ 2 |
| CSIPHY | csiphy2（vendor DT camera@2） | ✔ |
| CCI master | 1 | ✔ i2c-bus@1 |
| 电源 | vio + vana + vdig（3 路）+ VANA(GPIO49)/VDIG(PM660L3) GPIO 使能 | ✔ |
| MCLK | MCLK2 = GPIO33, 24 MHz | ✔ 实测 24 MHz |
| RESET | RESET2 = GPIO52 | ✔ 两种极性都试过 |

## 6. 采集到的文件

| 文件 | 内容 |
|---|---|
| `camera_config.xml` | 厂商相机配置（上表来源） |
| `dmesg-boot.txt` | 完整启动日志（含两路 sensor 探测） |
| `dmesg-camera.txt` | 相机相关日志筛选 |
| `logcat-full.txt` | 完整 logcat |
| `logcat-sensor.txt` | `s5k5e8` / 分辨率信息 |
| `libmmcamera_s5k5e8.so` | 前摄传感器库（779 KB，含模式表与时钟配置） |
| `libmmcamera_qtech_s5k5e8_eeprom.so` | 前摄 EEPROM 库 |
| `libmmcamera_dbg.so` | HAL 调试库（含所有 `persist.camera.*` 属性名） |
| `getprop.txt` | 全部系统属性 |
