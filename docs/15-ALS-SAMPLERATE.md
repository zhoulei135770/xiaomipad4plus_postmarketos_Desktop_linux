# 15 · ALS 修复的第二块拼图：采样率（2026-10-24）

> 前置：`13-ALS-SUCCESS.md`（补丁 1：data_type = 1，让 buffer 能 enable）
> 前置：`14-AUTO-BRIGHTNESS.md`（自动亮度）
> **本文记录：为什么 13 文档"成功"之后 ALS 又变成恒为 0，以及第二个补丁。**

---

## 零、一句话结论

```
13 文档的补丁 1 只解决了"buffer 能 enable"（0x501 消失）。
但 ALS 随后返回的每一个样本都是 0 —— 因为驱动从不使用 cur_sample_rate：

    qcom_smgr_request_buffering():
        u16 sample_rate = 0;                        // 局部变量，从 0 开始
        if (native_sample_rates) sample_rate = ...; // CM3232 这里是空的
        if (sample_rate == 0 || > max) sample_rate = max_sample_rate;
                                                    // CM3232 的 max 也是 0
        req.report_rate            = sample_rate * 65536;   // => 0
        req.items[0].sampling_rate = sample_rate;           // => 0

    report_rate == 0 时，DSP 接受请求但【一个样本都不产生】。

补丁 2：sample_rate 为 0 时回退到 cur_sample_rate，再回退到默认 10 Hz。
```

**两个补丁合起来，ALS 才真正可用。**

---

## 一、症状与时间线

| 时间 | 事件 |
|---|---|
| 14:29 | 补丁 1 刷入，ALS buffer 首次 enable 成功，读到 `141558` (141.6 lx) |
| 14:46 | 读到 `29622` (29.6 lx) |
| 14:51 | 读到 `39518` (39.5 lx) |
| **14:57** | **开始恒为 0** |
| 15:00+ | 重载模块、ADSP 重启、干净采样，全部仍为 0 |

**关键困惑**：同一个内核、同一个补丁，为什么会"先能用后不能用"？

后来的分析表明：早期那几个读数很可能是**增益切换的瞬间残留**，
而不是稳态数据。真正稳态下 `report_rate=0` ⇒ 没有样本。
（也可能是 DSP 早期用了一个临时默认值，之后按 0 处理。）

无论哪种解释，**根因是确定的**：`report_rate` 为 0。

---

## 二、排查过程（记录了 6 个被排除的假设）

### 排除 1：传感器硬件坏了

| 检查 | 结果 |
|---|---|
| `accel` / `gyro` / `mag` | 全部正常返回数据 |
| ADSP remoteproc | `state=running` |
| 卸载 DSP + 15 秒 + ADSP unbind/bind + 重载 | 无效，仍为 0 |
| 强光直照传感器 30 秒 | 156 次采样全 0 |

**结论**：不是硬件。

### 排除 2：buffer enable/disable 太频繁导致资源耗尽

`tablet-autobright` 每 6 秒开关一次 buffer，`tablet-orientd` 也频繁读 accel。

**测试**：停掉两个守护进程，卸载模块，等 15 秒，重载，
**只 enable 一次 ALS 且保持 20 秒不 churn**：

```
样本 111，唯一值 1
raw=0 x111
```

**结论**：不是 churn 问题。

### 排除 3：`data_type=1` 选错了通道

重新反汇编 `sensors.ssc.so`（这次用正确的方式，逐条指令）：

```
Light::prepareAddMsg @0x1e854:        Proximity::prepareAddMsg @0x259a0:
  LDR  x8, [x1]                         LDR  x8, [x1]
  ORR  w9, wzr, #1                      MOVZ w9, #40          (0x28)
  STRB w9, [x8, #0x0d]   ← data_type=1  STRB w9, [x8, #0x0c]
  LDR  x8, [x1]                         RET
  MOVZ w9, #40           (0x28)
  STRB w9, [x8, #0x0c]   ← sensor_id
  RET
```

**关键**：`Light` 就是 `sensor_id=0x28` + `data_type=1`，只有 3 条有效指令。
**没有** offset 0x35（我之前把下一个函数的指令误当成了它的一部分）。

**结论**：`data_type=1` 是对的，补丁 1 方向正确。

### 排除 4：buffer 参数（length / watermark）

测了 `len=4/16/64` × `wm=1/2` 六种组合：

```
len=4   wm=1 -> 0x10   (全部 0)
len=16  wm=1 -> 0x10
len=64  wm=1 -> 0x11
...
```

**结论**：无关。

### 排除 5：`xfce4-power-manager` 覆盖背光

之前实测"写 60，5 秒后变 165"。

**后来复测**：写 70，观察 8 秒，**一直是 70**。

**结论**：那个 165 是 `tablet-autobright` 自己调的，不是 xfce 覆盖。误判。

### 排除 6：`sampling_frequency` 不可写

```
写入 1   -> 读回 1
写入 5   -> 读回 5
写入 100 -> 读回 100
```

**可写！但写完 ALS 仍然是 0。**

这就指向真正的答案了 —— 见下一节。

---

## 三、真正的根因（读内核源码才发现）

`drivers/iio/common/qcom_smgr/qcom_smgr.c`：

### 写路径（能改的变量）

```c
static int qcom_smgr_iio_write_raw(..., long mask)
{
	case IIO_CHAN_INFO_SAMP_FREQ:
		priv->sensor->data_types[0].cur_sample_rate = val;   // ← 只改这个
		if (iio_buffer_enabled(iio_dev))
			return iio_dev->setup_ops->postenable(iio_dev);
		return 0;
```

### 读路径（用户看到的）

```c
	case IIO_CHAN_INFO_SAMP_FREQ:
		*val = priv->sensor->data_types[0].cur_sample_rate;
```

### 请求路径（真正发给 DSP 的）—— **问题在这里**

```c
static int qcom_smgr_request_buffering(struct qcom_smgr *smgr,
				       struct qcom_smgr_sensor *sensor,
				       bool enable)
{
	u16 sample_rate = 0;                       // ★ 从 0 开始

	if (enable) {
		if (sensor->data_types[0].native_sample_rates)
			sample_rate = native_sample_rates[count - 1];
		// CM3232: native_sample_rates 为空 → 保持 0

		if (sample_rate == 0 ||
		    sample_rate > sensor->data_types[0].max_sample_rate)
			sample_rate = sensor->data_types[0].max_sample_rate;
		// CM3232: max_sample_rate 也是 0 → 仍然是 0

		req.report_rate            = sample_rate * SMGR_REPORT_RATE_HZ;  // 0
		req.items[0].sampling_rate = sample_rate;                        // 0
		...
```

**`cur_sample_rate` 在整个函数里一次都没被读过。**

所以：
- 用户在 `in_proximity_sampling_frequency` 写 5 → 只改了 `cur_sample_rate`
- 真正发出去的 `report_rate` 永远是 `0 * 65536 = 0`
- DSP 收到 `report_rate=0` → **接受请求（所以没有 0x501），但不产生样本**

**这解释了全部现象**，包括"buffer 能 enable 但读不到数据"。

### 对比：为什么 accel/gyro/mag 正常

它们的 `max_sample_rate` 也是 0（读回 `sampling_frequency=0`），
但它们的 `native_sample_rates` 非空，所以 `sample_rate = native_sample_rates[last]` 拿到真实值。

只有 ALS 是**两者都为空**的特例。

---

## 四、补丁 2

```diff
 #define SMGR_VALUE_DIV			65536
+
+/* Used when the DSP reports no usable sample rate for a sensor. */
+#define QCOM_SMGR_DEFAULT_SAMPLE_RATE	10
```

```diff
 		if (sample_rate == 0 ||
 		    sample_rate > sensor->data_types[0].max_sample_rate)
 			sample_rate = sensor->data_types[0].max_sample_rate;
 
+		/*
+		 * Some sensors (the Capella CM3232 ambient light sensor is one)
+		 * report native_sample_rate_count == 0 and max_sample_rate == 0
+		 * through SMGR, yet still need a non-zero rate in the buffering
+		 * request: with report_rate == 0 the DSP accepts the request but
+		 * never emits a single sample.
+		 *
+		 * Fall back to the rate configured through
+		 * in_<type>_sampling_frequency, then to a sane default.
+		 */
+		if (sample_rate == 0)
+			sample_rate = sensor->data_types[0].cur_sample_rate;
+		if (sample_rate == 0)
+			sample_rate = QCOM_SMGR_DEFAULT_SAMPLE_RATE;
+
 		req.report_rate = sample_rate * SMGR_REPORT_RATE_HZ;
```

**两级回退**：
1. `cur_sample_rate` —— 尊重用户通过 sysfs 设的采样率
2. `10 Hz` —— 兜底（ALS 不需要高频，10 Hz 足够且省电）

---

## 五、验证结果

### 5.1 编译产物（r3）

```
r3.apk  39,957,103 字节
kernel.release = 7.0.14-sdm660
vmlinuz = 12,773,144   ← 与 r1 (CFI 开) 的 12,773,138 接近，确认 CFI 保留
qcom_smgr.ko: request_buffering 大小 = 508
  (476 = 未打补丁, 488 = 只打补丁 1, 508 = 补丁 1+2)
```

### 5.2 刷入后（决定性测试）

```
内核: Linux version 7.0.14-sdm660 (pmos@user) (Alpine clang 23.1.4) #4
BTF 错误: 0
0x501   : 0

ALS 采样 12 秒:
  样本=71  唯一值=3
    raw=    59245  (    59.24 lx)  x65
    raw=    94372  (    94.37 lx)  x5
    raw=    39518  (    39.52 lx)  x1
  变化序列: [94372, 39518, 59245]

✅ 有非零数据 —— 补丁 2 生效！
```

### 5.3 无回归

```
加速度: (-0.206, +0.464, -9.758) m/s²
陀螺仪: (+0.022, +0.020, -0.003) rad/s
磁力计: (+0.678, +0.231, +0.621)
桌面:   Xorg=1 xfwm4=1 panel=2, /dev/dri/card1
音频:   Xiaomi Mi Pad 4 (X4 / sdm660-internal)
WiFi:   192.168.1.123
```

### 5.4 自动亮度端到端

```
tablet-autobright: backlight 219/255, curve 1.0-200.0 lx -> 15%-100%
    82.58 lx -> 219/255 (mode=82575 x24/25, 5 zero-frames dropped)

早前: 59.24 lx -> 205/255 (mode=59245 x25/31)
```

三档亮度映射：
```
   0.0 lx ->  38/255
  39.5 lx -> 189/255
  59.2 lx -> 205/255
  94.4 lx -> 224/255
```

---

## 六、`tablet-autobright` 的相应改进（14 文档的更新）

发现 ALS 只有 **3 个离散档位**（DSP 内部增益切换，比值 94372/29622 = 3.19），
原来的曲线不适用，已重写：

| 项 | 旧 | 新 |
|---|---|---|
| `LUX_MAX` | 800 | **200**（室内上限） |
| `FRAC_MIN` | 0.12 | **0.15** |
| 采样聚合 | 中位数 | **众数**（跟踪主导增益档） |
| 采样窗口 | 2 秒 | **6 秒** |
| 死区 | 6% | **12%** |
| 零帧 | 不处理 | **丢弃**（`raw==0` 是瞬态） |
| 平滑 | 无 | **EMA α=0.35** |
| 自测 | 11 项 | **18 项** |

新自测（18/18 通过）专门验证了三个真实硬件值：

```
  ok  raw=0 (0.0 lx) -> 38  [1,60]
  ok  raw=29622 (29.6 lx) -> 177  [30,255]
  ok  raw=94372 (94.4 lx) -> 224  [100,255]
     -> the three levels are 38 / 177 / 224
  ok  3 real levels are distinguishable (>=15 apart)  gaps 139, 47
```

---

## 七、当前设备状态

```
内核      7.0.14-sdm660 #4 (pmos@user, Alpine clang 23.1.4, CFI=y)
          编译 Sat Oct 24 07:20:56 UTC
          补丁 1 (data_type) + 补丁 2 (sampling rate)
boot      boot-r3.img  23,351,296 字节  MD5 1ad76bd9320bbc18681896a00978d7ef
模块      637 个，同批编译，BTF 错误 0

环境光    ✅ 39~141 lx，真实变化
加速度    ✅ (-0.21, +0.46, -9.76) m/s²
陀螺仪    ✅
磁力计    ✅
霍尔      ✅ event3 (SW_LID)
音频      ✅ X4 / sdm660-internal
显示      ✅ /dev/dri/card1
桌面      ✅ Xorg + XFCE
WiFi      ✅ 192.168.1.123

服务
  tablet-autobright   enabled / active   自动亮度
  tablet-orientd      enabled / active   自动旋转 + 合盖休眠
  iio-sensor-proxy    static  / active   （看不见 ALS，因为通道类型是 proximity）
```

---

## 八、完整补丁清单（两个改动，一个文件）

文件：`drivers/iio/common/qcom_smgr/qcom_smgr.c`

| # | 改动 | 解决 |
|---|---|---|
| 1 | `req.items[0].data_type` 按传感器类型选择（ALS → `SECONDARY`=1） | `0x501`，buffer 无法 enable |
| 2 | `sample_rate` 为 0 时回退到 `cur_sample_rate` → 默认 10 Hz | 数据恒为 0 |

**补丁文件**：`artifacts/kernel/0001-iio-qcom-smgr-use-per-sensor-data-type.patch`
（3 个 hunk，71 行，能干净应用到 pristine 源码）

---

## 九、方法论总结

### 这次最容易走错的地方

| 弯路 | 教训 |
|---|---|
| 看到"恒为 0"就先怀疑硬件 / DSP 崩溃 | **先看内核源码的写入路径**，10 分钟就能定位 |
| 以为 `sampling_frequency` 可写就等于生效 | **sysfs 可写 ≠ 变量被使用**。要追到真正发出去的那一行 |
| 把 `xfce4-power-manager` 当覆盖源 | 复测证伪。**一次观测不能定因果** |
| 反汇编时把下一个函数当成当前函数的尾部 | 必须看 `RET` 截止；`Light` 只有 3 条有效指令 |
| 反复 enable/disable buffer | 这确实不是原因，但**先排除它是对的** |

### 最有效的两个动作

1. **读内核源码的 `request_buffering()`** —— 直接看到 `sample_rate` 从 0 开始且不回退
2. **对比能工作的传感器（mag）和不能工作的（prox）的属性** —— 发现 `sampling_frequency` 一个 100 一个 0

### 一句话

> **"设备能 enable 但读不到数据"** 这类问题，
> 八成是**请求里的某个字段是 0**，而不是硬件坏。
> 顺着"用户能改的变量 → 真正发出去的字段"这条链走一遍，就能找到断点。

---

## 十、工具

| 文件 | 用途 |
|---|---|
| `tools/vm_patch_both.sh` | **★ 一次生成两个补丁 + 修 APKBUILD**（含校验和自检） |
| `tools/vm_rate_path.sh` | 追溯 `sampling_frequency` 的读写路径 |
| `tools/vm_verify_r3.sh` | 验证编译产物（函数大小间接证明补丁） |
| `tools/pad_install_r3.sh` | 装模块 + 重建 initramfs + 组 boot.img |
| `tools/pad_als_r3_test.sh` | **★ ALS 决定性测试** |
| `tools/pad_als_clean_room.sh` | 无 churn 的干净采样 |
| `tools/pad_als_dsp_restart.sh` | ADSP unbind/bind |
| `tools/decode_light3.py` | 正确的 `prepareAddMsg` 反汇编 |
| `tools/pad_fix_override.sh` | 排除"谁覆盖背光" |

证据：`evidence/` 下本轮新增的 ALS 采样输出。
