# 音频校准（ACDB）与摄像头调色 —— 采集数据的实际价值分析

> 2026-10-29 01:10，离线分析 `artifacts/mokee-20261028/hwdata/` + `artifacts/rom/vendor-audio/`

---

## 1. 采到了什么

```
acdbdata.tgz (513 KB)
├── MTP/                        ← 本机（平板）用的这一套
│   ├── MTP_Speaker_cal.acdb      372 537 B
│   ├── MTP_Handset_cal.acdb      283 335 B
│   ├── MTP_Headset_cal.acdb      145 140 B
│   ├── MTP_Bluetooth_cal.acdb     67 522 B
│   ├── MTP_General_cal.acdb       19 353 B
│   ├── MTP_Global_cal.acdb         9 703 B
│   ├── MTP_Hdmi_cal.acdb           4 302 B
│   └── MTP_workspaceFile.qwsp      6 696 B
├── QRD/sdm660-snd-card-d9p/    ← 参考板，本机不用
├── QRD/sdm660-snd-card-skush/  ← 参考板，本机不用
└── adsp_avs_config.acdb          392 B
```

**为什么确定是 MTP**：`audio_platform_info_intcodec.xml` 里只有 `MTP` 这一套声卡名。

---

## 2. ACDB 文件格式（已验证）

```
偏移 0:  51 43 4d 53 4e 44 44 42   "QCMSNDDB"
偏移 16: 41 56 44 42               "AVDB"
之后是标签化的表：MODIFIED / SWPNAME / SWPVERS / OEMINFO /
                  ACGILUT0 / ACGICDFT / ACGICDOT / ACGDLUT0 / AVOLLUT0 …
```

是 Qualcomm 的私有二进制格式，**没有公开的完整解析器**，
但标签可见、可以按标签定位表。

---

## 3. 设备 → 校准 ID 映射（从 `audio_platform_info_intcodec.xml` 提取）

| 设备 | acdb_id | 说明 |
|---|---|---|
| `SND_DEVICE_OUT_SPEAKER` | **15** | 普通扬声器 |
| `SND_DEVICE_OUT_SPEAKER_PROTECTED` | **124** | **带保护的扬声器**（限幅/温漂补偿）|
| `SND_DEVICE_OUT_VOICE_SPEAKER_PROTECTED` | 101 | 通话时扬声器（带保护）|
| `SND_DEVICE_OUT_SPEAKER_PROTECTED_VBAT` | 124 | 同上（按电池电压）|
| `SND_DEVICE_IN_CAPTURE_VI_FEEDBACK` | **102** | **扬声器回采**（保护环路的反馈麦克风）|
| `SND_DEVICE_OUT_SPEAKER_EXTERNAL_1/2` | 14 | 外接 |
| `SND_DEVICE_OUT_SPEAKER_VBAT` | 135 | 按电池电压补偿 |

文件里共 **141 个 device 条目**。

---

## 4. 关键结论：**主线不加载 ACDB ⇒ 没有扬声器保护**

- Android 的音频 HAL 会把 `acdb_id` 通过 APR 发给 ADSP，ADSP 里的音频固件据此加载
  校准（频响补偿、**扬声器保护限幅**、VI 反馈闭环）。
- mainline/pmOS 的 `q6asm` / `q6afe` 驱动**不发这些校准**，ADSP 用默认参数跑。
- 后果：
  1. 音色没有频响补偿（可能偏薄/偏亮）
  2. **没有扬声器保护** —— 大音量长时间播放有烧喇叭的风险
  3. 没有 VI 反馈闭环（`acdb_id=102` 那条）

### 4.1 缓解建议（不需要实现 ACDB）

在用户态加一个软限幅（PipeWire / ALSA plugin）：

```
# /etc/pipewire/pipewire.conf.d/99-limiter.conf 里挂一个 limiter 节点，
# 或者在 ALSA 层用 softvol + 上限
```

并把默认音量上限压到 80% 左右。这是**工程上最划算的做法** ——
要真做 ACDB 加载，得改 ADSP 通信（APR 包构造），工作量很大。

---

## 5. 摄像头 chromatix：确认"没用"

`s5k5e8_chromatix.xml`（6.9 KB）的实际内容：

```
ChromatixName / ISPPreview / ISPSnapshot / ISPVideo
CPPPreview / CPPSnapshot / CPPVideo / CPPLiveshot
A3Preview / A3Video / CPPHht / CommonChromatixInfo
```

**全部是 ISP 调优参数**（去噪、锐化、色彩矩阵），
**没有任何 sensor 侧信息**（没有分辨率、没有 mode 表、没有 PLL）。

⇒ 对主线 bring-up **完全没用**（主线 CAMSS 不读 chromatix）。
前摄真正缺的是 sensor 的 **i2c 初始化序列/mode 表**，
那东西在 `libmmcamera_s5k5e8.so` 里（我们没采到），或者只能按数据手册写。

**结论：不要再花时间在 chromatix 上。**

---

## 6. 本次分析产出的工具

| 文件 | 用途 |
|---|---|
| `tools/acdb_map.py` | 从 `audio_platform_info_intcodec.xml` 提取 device→acdb_id 映射 |
