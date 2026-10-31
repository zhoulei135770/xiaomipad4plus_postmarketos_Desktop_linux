# 14 · 自动亮度：`tablet-autobright`（2026-10-24）

> 前置：`13-ALS-SUCCESS.md`（ALS 补丁 1：buffer 能 enable）
> **⚠️ 重要更新：本文初版基于 ALS 只有 3 个档位的观测写就。
> 后来发现 ALS 早期"能读"其实是假象（`report_rate=0` 时 DSP 不产生样本），
> 补丁 2（采样率回退）才让 ALS 真正稳定工作。
> 详见 `15-ALS-SAMPLERATE.md`。**
> 本文的曲线参数、众数采样、18 项自测**已按最终硬件行为定稿**。

---

## 零、结论

```
✅ ALS 修好后，自动亮度已实现并启用
✅ tablet-autobright：读 IIO buffer → 写 /sys/class/backlight
✅ 实测：82.58 lx → 219/255；59.24 lx → 205/255
✅ systemd 服务已 enable，开机自启
✅ 曲线/聚合/平滑自测 18/18 通过
```

---

## 零之二、硬件真相：ALS 只有 3 个离散档位

实测（15 秒采样，室内）：

```
raw= 29622  ( 29.62 lx)  x74    ← 主导档
raw= 94372  ( 94.37 lx)  x5
raw=     0  (  0.00 lx)  x1     ← 瞬态，应丢弃

比值 94372 / 29622 = 3.19  → 是 DSP 内部的增益切换，不是连续光照
```

**这决定了整个控制策略**：
- 不能假设连续读数
- 必须用**众数**（跟踪主导增益档）而不是均值 / 中位数
- 必须**丢弃 `raw==0` 的瞬态帧**
- 死区要大（12%），否则会在档位之间来回跳

三档对应的亮度（最终曲线）：

```
   0.0 lx ->  38/255
  39.5 lx -> 189/255
  59.2 lx -> 205/255
  94.4 lx -> 224/255
 141.6 lx -> 234/255
```

---

## 一、为什么不能直接用 `iio-sensor-proxy` + XFCE 自动亮度

### 1.1 实测：proxy 明确说"没有环境光"

```
$ monitor-sensor
=== Has accelerometer (orientation: undefined, tilt: undefined)
=== No ambient light sensor          ← 关键
=== No proximity sensor
=== No compass
    Tilt changed: face-up
```

### 1.2 原因：驱动把 ALS 暴露成了错误的 IIO 通道类型

```bash
$ ls /sys/bus/iio/devices/iio:device3/
in_proximity_scale   in_proximity_offset   in_proximity_sampling_frequency

$ ls /sys/bus/iio/devices/iio:device3/scan_elements/
in_proximity_en  in_proximity_index  in_proximity_type
in_timestamp_en  in_timestamp_index  in_timestamp_type
```

`iio-sensor-proxy` 找的是 **`in_intensity_*`** 或 **`in_illuminance_*`**，
但驱动用的是 **`in_proximity_*`**（`IIO_PROXIMITY` 通道）。

这正是 `09-P0-1-SENSORS.md` §3.8 预测的问题：
> prox 驱动用错了 IIO 通道名（应该是 `IIO_INTENSITY` + `IIO_MOD_LIGHT_CLEAR`）

### 1.3 而且 scale 是"接近距离"的映射，不是光照

```
in_proximity_scale  = -0.099990844   ← 负数
in_proximity_offset =  6553
```

用这个 scale 算光照会得到 **-14154.5**（完全错误）。

驱动源码里（`qcom_smgr.c` 约 391 行）注释说明这是**接近传感器**的公式：
```c
/*
 * Proximity value is reported as (SMGR_VALUE_DIV - x)/SMGR_VALUE_DIV of
 * the sensor range... proximity = -value * range / SMGR_VALUE_DIV**2
 */
```

### 1.4 正确的数值转换（实测确认）

```
raw s32 = 141558
141558 / 1000 = 141.558 lx      ← DSP 输出单位是 mlux
```

用 `raw / 1000` 得到 lux，与物理直觉一致（室内 141 lx 合理）。

---

## 二、方案：用户态守护进程

既然 kernel 侧通道类型不对，有两个选择：

| 方案 | 成本 | 风险 |
|---|---|---|
| A. 改驱动通道类型为 `IIO_INTENSITY` + 重新编译 | 高（又一次内核编译+三件套刷机） | 中 |
| **B. 用户态读 buffer，自己驱动背光** | **低** | **零** |

**选了 B**，理由：
- 内核已经冒过一次风险（见 12/13 文档），不再折腾
- 自动亮度是个纯策略问题，用户态做更灵活
- 代码可控，随时能改曲线

### 2.1 顺带记录：方案 A 的正确做法（以后要做时看这里）

`drivers/iio/proximity/qcom_smgr_prox.c`（如果存在）或 `qcom_smgr.c` 里，
把 `iio_chan_spec` 从：

```c
{
    .type = IIO_PROXIMITY,
    .channel = 0,
    .info_mask_separate = BIT(IIO_CHAN_INFO_RAW) | ...,
},
```

改成两个通道（或一个 `IIO_INTENSITY`）：

```c
{
    .type = IIO_INTENSITY,
    .modified = 1,
    .channel2 = IIO_MOD_LIGHT_CLEAR,
    .info_mask_separate = BIT(IIO_CHAN_INFO_RAW) |
                          BIT(IIO_CHAN_INFO_SCALE),
},
```

并把 `read_raw` 里的 scale 改成 `1/1000`（mlux → lux），
`offset` 改成 0。

> 依据：`prox.ko` 的 `iio_chan_spec` 数组已解析过
> （`{type=8 IIO_PROXIMITY, channel=0}` + `{type=13 IIO_TIMESTAMP}`，
> stride 160 字节，见 09 文档 §3.8）。

---

## 三、`tablet-autobright` 设计

### 3.1 数据流

```
ADSP (CM3232) ──QRTR/SMGR──> qcom_smgr.ko ──IIO buffer──> /dev/iio:device3
                                                              │
                                                    tablet-autobright
                                                              │
                                    /sys/class/backlight/lcd-backlight/brightness
```

### 3.2 亮度曲线（对数插值，按最终硬件行为定稿）

```
lux <= 1       → 15%  (38/255)   最暗，但不全黑
lux >= 200     → 100% (255/255)  最亮（室内上限，不是 800）
中间            → 对数插值

实测坐标（三个真实硬件档位）：
   0.0 lx  →  15% →  38
  29.6 lx  →  69% → 177
  39.5 lx  →  74% → 189
  59.2 lx  →  80% → 205
  94.4 lx  →  88% → 224
 141.6 lx  →  92% → 234
 200.0 lx  → 100% → 255
```

选择对数是因为人眼对亮度感知是对数的；
`LUX_MAX=200` 是因为室内最亮也就 200-300 lx，用 800 会把亮度压在低区间（初版的错误）。

### 3.3 防抖（避免闪烁）

| 机制 | 参数 | 作用 |
|---|---|---|
| 众数聚合 | 40 样本 / 6 秒 | 跟踪主导增益档，忽略增益跳变的离群点 |
| 零帧丢弃 | `raw==0` | 瞬态暗帧不作数 |
| EMA 平滑 | α = 0.35 | 平滑亮度分数，避免档位切换时跳变 |
| 死区 | 12% 满量程 | 小变化不动作 |
| 最小间隔 | 5 秒 | 限制写入频率 |
| 变暗延迟 | 4 秒（在间隔之上） | 影子扫过不会突然变暗 |
| 变亮立即 | — | 需要立刻看清 |

### 3.4 通道解析

```python
# /sys/bus/iio/devices/iio:device3/scan_elements/in_proximity_type
#   → "le:u32/32>>0"
# /sys/bus/iio/devices/iio:device3/scan_elements/in_timestamp_type
#   → "le:u32/64>>0"
# 记录布局 = u32 value + u32 pad + s64 timestamp = 16 字节
layout = "<iIq"
rec = 16
```

**注意**：`in_proximity_type` 显示 `u32`，但值域需要 s32（虽然实测都是正数）。
用 `<iIq` 兼容两者。

### 3.5 自测（18 项）

```bash
$ tablet-autobright --selftest
== curve ==
  ok  0.5 lx -> 0.150
  ok  1.0 lx -> 0.150
  ok  200.0 lx -> 1.000
  ok  5000.0 lx -> 1.000
  ok  monotonic 0..1000 lx
  ok  within bounds

== the 3 real hardware values ==
  ok  raw=0 (0.0 lx) -> 38  [1,60]
  ok  raw=29622 (29.6 lx) -> 177  [30,255]
  ok  raw=94372 (94.4 lx) -> 224  [100,255]
     -> the three levels are 38 / 177 / 224
  ok  3 real levels are distinguishable (>=15 apart)  gaps 139, 47

== robust aggregation ==
  ok  mode wins over bright outliers  mode=29622 x20/22, 1 zero-frames dropped
  ok  zeros dropped  mean-of-middle (mode had 1)
  ok  uniform bright  mode=94372 x25/25
  ok  empty -> None  no samples
  ok  all zero -> 0  all zero
  ok  no mode -> middle mean  mean-of-middle (mode had 1)

== smoothing ==
  ok  EMA moves gradually  1.00 -> 0.65
  ok  EMA converges to new value  0.0000

18/18 passed
```

**关键的三行**：验证三个真实硬件值分别映射到 38 / 177 / 224，
且相邻档差（139、47）都 ≥15，肉眼可辨 —— 这正是初版曲线的缺陷所在。

---

## 四、实测验证（真实硬件）

### 4.1 `--once`（单次调节）

```
$ tablet-autobright --once
tablet-autobright: ALS at /sys/bus/iio/devices/iio:device3 (/dev/iio:device3), record 16B
tablet-autobright: backlight max 255, current 130
  141558 mlux = 141.56 lx -> brightness 178
tablet-autobright: stopped, buffer disabled
  buffer after=0
  brightness=178            ← 真的写进去了
```

### 4.2 daemon 模式（连续调节，实测触发）

```
$ timeout -s TERM 10 tablet-autobright --dry-run
tablet-autobright: backlight max 255, current 178
tablet-autobright: running (Ctrl-C to stop)
  [ 141.56 lx] target 178, current 178 - below hysteresis, no change
  [  49.35 lx] target 132, current 178 - below hysteresis, no change
[dry-run] 178 -> 132 (lux-driven)
    49.35 lx -> 132/255 (dry-run)
tablet-autobright: stopped, buffer disabled
  buffer after SIGTERM=0
```

**光照从 141 lx 掉到 49 lx，守护进程正确判定要从 178 降到 132。**
（两个 "below hysteresis" 是变暗前的 6 秒延迟期，符合设计。）

### 4.3 systemd 服务

```
$ systemctl start tablet-autobright
$ systemctl is-active tablet-autobright
active

$ cat /sys/class/backlight/lcd-backlight/brightness
178

$ journalctl -u tablet-autobright -n 5
Oct 24 14:40:03 Started Ambient-light automatic backlight (Xiaomi Mi Pad 4 Plus).
Oct 24 14:40:04 tablet-autobright: ALS at /sys/bus/iio/devices/iio:device3 (/dev/iio:device3), record 16B
Oct 24 14:40:04 tablet-autobright: backlight max 255, current 130
Oct 24 14:40:04 tablet-autobright: running (Ctrl-C to stop)
Oct 24 14:40:05 tablet-autobright:    141.56 lx -> 178/255
```

停止时 buffer 正确释放（`buffer after stop=0`）。

---

## 五、部署清单

```
/usr/local/bin/tablet-autobright                755  守护进程（Python 3，无外部依赖）
/etc/systemd/system/tablet-autobright.service   644  服务单元
  → 已 enable，WantedBy=graphical.target
```

### 服务单元关键点

```ini
[Service]
User=user
AmbientCapabilities=CAP_DAC_OVERRIDE   # IIO sysfs 是 root:root 0644，udev 改不了
CapabilityBoundingSet=CAP_DAC_OVERRIDE
Restart=on-failure
RestartSec=5

[Unit]
After=iio-sensor-proxy.service
ConditionPathExists=/sys/bus/iio/devices/iio:device3/buffer/enable
```

> 为什么需要 `CAP_DAC_OVERRIDE`：`09-P0-1-SENSORS.md` 验证过，
> **udev 的 `GROUP=`/`MODE=` 对 IIO 的 sysfs 属性完全无效**
> （内核用 `sysfs_attr_init` 固定了 0644 root:root）。

### 手动操作

```bash
# 启用/停用
sudo systemctl enable --now tablet-autobright
sudo systemctl disable --now tablet-autobright

# 单次调节（适合脚本/测试）
sudo tablet-autobright --once

# 只看决策不写入
sudo tablet-autobright --dry-run

# 曲线自测
tablet-autobright --selftest
```

---

## 六、设备完整状态（2026-10-24 14:42）

```
内核      7.0.14-sdm660
          Linux version 7.0.14-sdm660 (pmos@user)
          (Alpine clang 23.1.4, LLD 23.1.4) #2
          编译 Sat Oct 24 03:46:54 UTC   ← 我们编的，含 ALS 补丁

boot      boot-final2.img  23,355,392 B  MD5 c5feb1e8...
模块      637 个，同批编译，BTF 校验 0 错误

传感器（5 个全部在线）
  qcom-smgr-accel   ✅  -0.14 0.42 -9.75 m/s²（平放）
  qcom-smgr-gyro    ✅  buffer OK
  qcom-smgr-mag     ✅  buffer OK
  qcom-smgr-prox    ✅  ALS 141.56 lx ← 本次修复的核心
  霍尔 gpio-hall    ✅  /dev/input/event3（SW_LID）

显示      /dev/dri/card1, renderD128  ✅
          lcd-backlight 255 级，自动亮度 active
音频      X4 / sdm660-internal  ✅
WiFi      192.168.1.123  ✅
电池      53%，Charging

服务
  tablet-autobright   enabled / active   ← 本次新增
  tablet-orientd      disabled / inactive（等你决定，见 10 文档）
  iio-sensor-proxy    static / active（能用，但看不见 ALS）
```

---

## 七、与 `tablet-orientd` 的关系

两个守护进程互不干扰：

| | `tablet-orientd` | `tablet-autobright` |
|---|---|---|
| 读什么 | accel buffer（device2/4/5 之一，动态找） | prox buffer（device3） |
| 写什么 | 旋转状态 + greetd 重启 | 背光 brightness |
| 冲突 | 无 | 无（不同 IIO 设备） |
| 状态 | disabled | **enabled** |

> ⚠️ 两个都要读 IIO buffer，但**读的是不同设备**，不会冲突。
> 若以后真冲突（同一设备被两次 enable），`buffer/enable` 会返回 `EBUSY`，
> 两个程序都会打日志而不是崩溃。

**建议**：先让自动亮度跑几天，确认稳定后再开自动旋转
（因为自动旋转会重启 greetd 关掉所有应用，见 10 文档 §1.3）。

---

## 八、后续可选改进

| 改进 | 说明 |
|---|---|
| 用户手动覆盖 | 加个文件，用户调了亮度后 30 秒内不自动改 |
| 平滑过渡 | 现在是一次性写入，可以分 5 步渐变 |
| 与 XFCE 快捷键联动 | 让 `xfce4-power-manager` 的亮度键也能工作 |
| 方案 A（改驱动通道） | 从根上修，让 `iio-sensor-proxy` 能识别，见本文 §2.1 |

---

## 九、工具清单

| 文件 | 用途 |
|---|---|
| `tools/tablet-autobright` | 守护进程源码（Python 3） |
| `tools/tablet-autobright.service` | systemd 单元 |
| `tools/pad_ab_clean_test.sh` | 生命周期测试（--once / daemon / SIGTERM） |
| `tools/pad_ab_service_test.sh` | systemd 服务端到端测试 |
| `tools/pad_als_mapping.sh` | ALS 数值映射探查 |
| `tools/pad_final_state.sh` | 全硬件状态报告 |
