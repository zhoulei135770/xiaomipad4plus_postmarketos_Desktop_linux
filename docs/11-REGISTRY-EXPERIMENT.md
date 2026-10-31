# 11 · cm3232 registry 实验：**假设被推翻**，真因在驱动 units bug

> 创建：2026-10-24 10:50（Asia/Shanghai）
> 前置：`09-P0-1-SENSORS.md`（P0-1 调查）、`10-AUTOROTATE.md`（自动旋转）
> **本文记录一次"计划执行后被证据推翻"的完整过程。结论与 09 文档的假设相反。**

---

## 零、一句话结论

```
❌ 09 文档的假设「ALS 缺 registry JSON」是错的。实测四步全部推翻：
  1. sensor_def_qcomdev.conf 里 CM3232 的 sdm660 配置一直存在（config 2300-2312，enable=2）
  2. 生成的 sns.reg 里 CM3232 的 UUID 确实在（offset 6048）
  3. DSP 直接回话：result=0x0000，sensor 列表含 0x28 PROX_LIGHT 和 0x50 HALL_EFFECT
  4. Android HAL 的 Light 类写 sensor_id=0x28 + data_type=1；Accel 写 0 + 0

✅ 真因是内核驱动的 data_type 硬编码：
  qcom_smgr.c 对【所有】传感器固定发 data_type = SNS_SMGR_DATA_TYPE_PRIMARY (0)，
  但 DSP 要求 ALS 用 data_type = 1。
  → 修复 = 一个 enum + 一个 if，不需要碰 registry。
```

**所以不应该补 JSON（那是白做），应该改驱动源码。这正好回到你原本的判断。**

### 已确证的 data_type 对照表（反汇编 Android HAL + DSP 交叉验证）

| 传感器 | sensor_id | Android 的 data_type | 内核发的 | 结果 |
|---|---|---|---|---|
| ACCEL | 0x00 | 0 | 0 | ✅ |
| GYRO | 0x0a | 0 | 0 | ✅ |
| MAG | 0x14 | 0 | 0 | ✅ |
| **PROX_LIGHT (ALS)** | **0x28** | **1** | **0** | ❌ `0x501` |
| HALL_EFFECT | 0x50 | 0 | （无驱动） | — |

**只有 ALS 需要非零的 data_type。这让补丁只有 3 行。**

---

## 一、我原本的计划，以及它是怎么被一步步推翻的

### 步骤 0：备份（做了，有用）

```bash
/root/sensor-registry-backup-20261024-102514/     # 172 KB，含 registry + sns.reg + settings
```

### 步骤 1：发现 persist 只读 → 但这不是障碍

```bash
$ mount | grep persist
/dev/mmcblk1p48 on /run/msm-firmware-loader/mnt/persist type ext4 (ro,nosuid,nodev,noexec,relatime)
```
`ro` 挂载。但 `sns.reg` 是从 `persist/sensors/registry/config/*.json` **生成**的，
所以真正要改的是生成输入，不是二进制。

### 步骤 2：找到生成机制的源文件（关键发现）

```
/run/msm-firmware-loader/mnt/persist/sensors/registry/sns_reg_config
```
```ini
version=1
file=hw_platform=/sys/devices/soc0/hw_platform
file=soc_id=/sys/devices/soc0/soc_id
file=output=/mnt/vendor/persist/sensors/registry/registry
```

这说明：**JSON 是编译期输入，`sensors_registry` 是生成产物**。
而产物是 **0 字节**（从未在设备上生成过）—— 设备用的是预置的 `sns.reg`。

### 步骤 3：`sensor_def_qcomdev.conf` —— CM3232 早就在里面

`/vendor/etc/sensors/sensor_def_qcomdev.conf`（22 万字节，5816 行，多平台定义库）
里有明确的 sdm660 段（第 5158 行起）：

```
:hardware sdm660
...
# DEVINFO: CM3232 ALS
2300 2                  0x00010001 # set to 2 to enable on sdm660 platform
2301 1                  0x00010001 # the number of sensors you want to auto-detect
2302 0x964050b41551f40c 0x00010001 # uid_high
2303 0x914a9e21d8db6091 0x00010001 # uuid_low
2304 3000               0x00010001 # off_to_idle
2305 150000             0x00010001 # idle_to_ready
2306 0xFFFF             0x00010001 # gpio1
2307 1040               0x00010001 # reg_group_id
2308 0xFFFF             0x00010001 # cal_pri_grp_id
2309 3                  0x00010001 # i2c_bus
2310 0x10               0x00010001 # i2c_address     ← 注意：0x10，不是 dmesg 的 0x28
2311 0                  0x00010001 # sens_default
2312 0                  0x00010001 # flags
2368 0x83               0x00010001 # vdd
2369 0x83               0x00010001 # vddio
```

**而且 `2300 = 2` 就是 "enabled on sdm660"。**

同一段里还有：
```
# DEVINFO: AKM099XX MAG DRI/FIFO      2200-2212   enable=2
# DEVINFO: BU52061NVX HALL DRI        4700-4712   enable=2
# DEVINFO: CM3232 ALS                 2300-2312   enable=2
```
**霍尔也有配置（`enable=2`）！** 这暗示 Android 侧霍尔是走 SMGR 的。

### 步骤 4：决定性验证 —— UUID 在生成的 sns.reg 里

用 conf 里的 128-bit UUID 做指纹，在 25468 字节的 `sns.reg` 里搜：

```
sns.reg: 25468 bytes

=== UUID search in sns.reg ===
  CM3232 ALS  : PRESENT
       hi/LE at offset 6048
       lo/LE at offset 6056
  AKM099XX MAG: PRESENT
       hi/LE at offset 6000
       lo/LE at offset 6008
  BU52061 HALL: PRESENT
       hi/LE at offset 9744
       lo/LE at offset 9752
```

**三个都在。** 我之前在 09 文档里写"registry 里 grep 不到 cm3232"——
那是因为我只 grep 了 `registry/config/*.json`（那些是 SDM845 的样例），
**没看 `sns.reg` 二进制本身，也没看 `sensor_def_qcomdev.conf`。**

### 步骤 5：DSP 直接回话，彻底定案

用 Python 直接对 QRTR 发 QMI 请求（`AF_QIPCRTR`, node 5 port 60）：

```
reached SNS_SMGR at qrtr node 5 port 60
raw: 02 0100 0500 3400 | 02 02 0000 | 03 2c00 00 05 00 05 414343454c ...

result = 0x0000  (SUCCESS)
sensor list:
   sensor_id = 0x00   type = ACCEL
   sensor_id = 0x0a   type = GYRO
   sensor_id = 0x14   type = MAG
   sensor_id = 0x28   type = PROX_LIGHT
   sensor_id = 0x50   type = HALL_EFFECT
```

**DSP 明确承认 5 个传感器，包括 `0x28 PROX_LIGHT` 和 `0x50 HALL_EFFECT`。**

**结论：registry 完全正常，一个字节都不用改。**

---

## 二、真正的根因（三条独立证据指向同一处）

### 2.1 证据 A：内核硬编码 `data_type = 0`

`drivers/iio/common/qcom_smgr/qcom_smgr.c` 第 257-268 行：

```c
req.item_len = 1;
req.items[0].sensor_id = sensor->id;
req.items[0].data_type = SNS_SMGR_DATA_TYPE_PRIMARY;   /* ← 永远是 0 */
req.items[0].sampling_rate = sample_rate;
...
req.items[0].val1 = 3;
req.items[0].val2 = 1;
```

`include/linux/iio/common/qcom_smgr.h`：
```c
enum qcom_smgr_data_type {
	SNS_SMGR_DATA_TYPE_PRIMARY,     /* = 0 */
	SNS_SMGR_DATA_TYPE_SECONDARY,   /* = 1 */
	SNS_SMGR_DATA_TYPE_COUNT
};
```

**注释还承认了这一点**：
> `Only SNS_SMGR_DATA_TYPE_PRIMARY is used at the moment`

### 2.2 证据 B：Android HAL 对 ALS 用的是 `data_type = 1`

反汇编 `sensors.ssc.so`（Android 的 SSC sensor HAL）。
先确认字段布局：所有 `*::prepareAddMsg` 都往两个固定偏移写字节：

```
offset 0x0c = sensor_id
offset 0x0d = data_type
```

**字段归属是硬证据**（值必须等于 DSP 报的 sensor id）：

| Android 类 | 写 offset 0x0c | 写 offset 0x0d | DSP 是否承认 |
|---|---|---|---|
| `Accelerometer` | `0x00`（`STRB wzr`） | 不写（默认 0） | ✅ ACCEL |
| `Gyroscope` | `0x0a` | 不写 | ✅ GYRO |
| `Magnetic` | `0x14` | 不写 | ✅ MAG |
| **`Light`** | **`0x28`** | **`1`** | ✅ **PROX_LIGHT** |
| **`HallEffect`** | **`0x50`** | 不写 | ✅ **HALL_EFFECT** |
| `Proximity` | `0x28` | 不写 | ✅ PROX_LIGHT |
| `SAR` | `0x46` | 不写 | — |
| `Humidity` | `0x32` | 不写 | — |

**`sensor_id` 全部和 DSP 的清单一一对上**，这证明我的字段解析是对的。

三条关键指令（`Light::prepareAddMsg`）：

```
0x1e854: f9400028   ldr  x8, [x1]          ; x8 = *req_out
0x1e858: 320003e9   orr  w9, wzr, #1       ; w9 = 1
0x1e85c: 39003509   strb w9, [x8, #0xd]    ; data_type = 1        ← ★
0x1e860: f9400028   ldr  x8, [x1]
0x1e864: 52800509   movz w9, #0x28         ; 0x28 = 40
0x1e868: 39003109   strb w9, [x8, #0xc]    ; sensor_id = 0x28     ← ALS
0x1e86c: d65f03c0   ret
```

对比 `Accelerometer::prepareAddMsg`：

```
0x16734: f9400028   ldr  x8, [x1]
0x16738: 3900311f   strb wzr, [x8, #0xc]   ; sensor_id = 0, data_type 保持 0
0x1673c: d65f03c0   ret
```

**结论：`Light` 用 `data_type = 1`，`Accelerometer`/`Magnetic`/`HallEffect` 用 0
（后两者干脆不写）。**

而内核 `qcom_smgr.c` 对**所有**传感器一律硬编码 `PRIMARY = 0`。

### 2.3 证据 B-2：霍尔在 Android 侧确实走 SMGR

`sensors.ssc.so` 里有完整的 `HallEffect::prepareAddMsg`，写 `sensor_id = 0x50`。
这推翻了 09 文档里"DSP 没有 hall 驱动 = 死路"的判断：
**DSP 侧 hall 完全可用，缺的只是内核的 `qcom_smgr_hall.c`。**

### 2.4 证据 C：加速度计能过、ALS 不能过的分界线

```bash
# 三个能 enable 的：采样率读回都是 0
qcom-smgr-accel: sampling_freq=0  enable=OK
qcom-smgr-gyro:  sampling_freq=0  enable=OK
qcom-smgr-mag:   sampling_freq=0  enable=OK
# ALS 读回 100，enable 失败
qcom-smgr-prox:  sampling_freq=100  enable=FAIL -> 0x501
```

`qcom_smgr_probe()` 第 550 行：
```c
/* Default to maximum sample rate */
smgr->sensors[i].data_types->cur_sample_rate =
        smgr->sensors[i].data_types->max_sample_rate;
```

所以读回的 `sampling_frequency` **就是 DSP 报的 `max_sample_rate`**。
accel/gyro/mag 报 **0**，ALS 报 **100**。

### 2.4 还有第二个 units bug

```c
#define SMGR_TICKS_PER_SECOND   32768
#define SMGR_REPORT_RATE_HZ     (SMGR_TICKS_PER_SECOND * 2)   /* = 65536 */

req.report_rate = sample_rate * SMGR_REPORT_RATE_HZ;
req.items[0].sampling_rate = sample_rate;
```

`struct sns_smgr_buffering_req`：`u32 report_rate`
`struct sns_smgr_buffering_req_item`：`u16 sampling_rate`

| sample_rate | report_rate (u32) | sampling_rate (u16) |
|---|---|---|
| 0（accel） | 0 | 0 |
| 100（ALS） | 6,553,600 | 100 |

`report_rate` 看起来按 **Q16 定点**编码（`sample_rate << 16`），
但 `sampling_rate` 是**裸 Hz**。两者单位不一致。
`libsensor1.so` 里有 `sns_em_convert_sec_in_q16_to_localtick`
——**确认这个协议体系用的是 Q16**。

```c
/* 可能的正确写法 */
req.report_rate = sample_rate * SMGR_TICKS_PER_SECOND;   /* 32768? */
req.items[0].sampling_rate = sample_rate;                 /* 或 <<16 但要改类型 */
```

**这一点我不能确定**（需要抓一次 Android 的真实请求），
所以**列成待验证项，不作为结论**。

---

## 三、为什么 `0x501` 具体是哪个错，仍不能 100% 确定

我尝试直接从用户态伪造请求来验证 `data_type=5` 是否可行，但失败：

```
[FAIL] sid=0x28 data_type=0 sampling=0     report_rate=0        -> result=0x0402
[FAIL] sid=0x28 data_type=5 sampling=100   report_rate=6553600  -> result=0x0402
... 全部 0x0402
```

`0x0402` 是**我构造的 QMI TLV 格式不对**（tag 编号猜错），
不是 DSP 的真实答复。真实答复必须由内核按正确格式发出。

**所以最后一环只能靠改内核 + 重编来验证。** 这恰好就是你要做的事。

---

## 四、修正后的改动清单（替代 09 文档 §6.2 的改动 1 和 3）

### ❌ 改动 3（补 cm3232.json）—— **取消，不要做**

证据：`sensor_def_qcomdev.conf` 有 CM3232（enable=2）、
`sns.reg` 有 CM3232 UUID（offset 6048）、DSP 报 `0x28 PROX_LIGHT`、`result=0`。

**补 JSON 是白做，而且 persist 是只读的，改它还有风险。**

### ✅ 改动 1（改驱动）—— **这才是真正要做的，且比我原先写的更明确**

文件：`drivers/iio/common/qcom_smgr/qcom_smgr.c`
（注意：不是 `qcom_smgr_prox.c`，问题在**共用的 core**，不在 prox 驱动）

**改动 1a：`data_type` 要按传感器类型决定（最关键，已确证）**

```c
/* 现状 258 行 */
req.items[0].data_type = SNS_SMGR_DATA_TYPE_PRIMARY;   /* 永远 0 */
```

**Android 的权威对照表（反汇编 `sensors.ssc.so` 得到，已与 DSP 清单交叉验证）：**

| sensor type | 内核 sensor_id | Android 写的 data_type |
|---|---|---|
| ACCEL | 0x00 | **0** |
| GYRO | 0x0a | **0** |
| MAG | 0x14 | **0** |
| **PROX_LIGHT (ALS)** | **0x28** | **1** ← 唯一非零 |
| HALL_EFFECT | 0x50 | **0** |
| SAR | 0x46 | 0 |
| HUMIDITY | 0x32 | 0 |

**只有 ALS 需要 `data_type = 1`，其他全是 0。** 这让补丁变得很小：

```c
/*
 * The Light/Proximity sensor class in Android's SSC HAL sets data_type = 1
 * (see Light::prepareAddMsg in sensors.ssc.so). The DSP rejects the
 * buffering request with result 0x501 if the ALS is requested with
 * SNS_SMGR_DATA_TYPE_PRIMARY like every other sensor.
 */
static u8 qcom_smgr_data_type_for(struct qcom_smgr_sensor *sensor)
{
	if (sensor->type == SNS_SMGR_SENSOR_TYPE_PROX_LIGHT)
		return SNS_SMGR_DATA_TYPE_SECONDARY;   /* 1 */

	return SNS_SMGR_DATA_TYPE_PRIMARY;         /* 0 */
}
...
req.items[0].data_type = qcom_smgr_data_type_for(sensor);
```

> **`SNS_SMGR_DATA_TYPE_SECONDARY` 就是 1**（enum 第 2 项），
> 所以补丁甚至不需要新增枚举值，语义上也能自圆其说：
> ALS 的 lux 数据在 DSP 侧是第二个 data type。

**这是本次最重要的可执行结论：一个 enum + 一个 if 就能修 ALS。**

**改动 1b：`report_rate` / `sampling_rate` 的单位（次关键，待验证）**

```c
/* 现状 254 行 */
req.report_rate = sample_rate * SMGR_REPORT_RATE_HZ;   /* 65536 */
req.items[0].sampling_rate = sample_rate;               /* 裸 Hz ← 可疑 */
```

`struct sns_smgr_buffering_req_item`：`u16 sampling_rate`

| sensor | max_sample_rate | report_rate (u32) | sampling_rate (u16) | 结果 |
|---|---|---|---|---|
| accel/gyro/mag | 0 | 0 | 0 | ✅ DSP 接受 |
| ALS | 100 | 6,553,600 | 100 | ❌ `0x501` |

`report_rate` 看起来是按 **Q16 定点**编码（`sample_rate << 16`），
而 `sampling_rate` 是**裸 Hz**。`libsensor1.so` 里有
`sns_em_convert_sec_in_q16_to_localtick` —— 确认这个协议体系用 Q16。

**但我不能确定 DSP 是否在意这个不一致。**
**建议：先只改 1a，如果 ALS 能过，就不用碰 1b。**
这样改动最小、风险最低。

**改动 1c：`probe()` 里的循环 bug（顺带修，非阻塞）**

```c
/* 现状 550 行：缺 [j] 索引 */
for (j = 0; j < smgr->sensors[i].data_type_count; j++) {
        smgr->sensors[i].data_types->cur_sample_rate =
                smgr->sensors[i].data_types->max_sample_rate;
        /* ↑ 永远写 data_types[0]，应该是 data_types[j] */
```
不致命（`data_type_count` 多为 1~2），但确实不对。

### 改动 2（hall 驱动）—— **从"死路"改判为"可行"**

09 文档说"DSP 没有 hall 驱动，这条路是死的"。**新证据全部推翻：**

| 证据 | 结果 |
|---|---|
| `sensor_def_qcomdev.conf` | `# DEVINFO: BU52061NVX HALL DRI`，4700-4712，`enable=2` |
| `sns.reg` UUID 搜索 | `BU52061 HALL` PRESENT（offset 9744） |
| DSP sensor 列表 | `0x50 HALL_EFFECT` |
| Android HAL | `HallEffect::prepareAddMsg` 写 `sensor_id=0x50`，`data_type=0` |

**所以 DSP 侧 hall 完全可用。缺的只有内核的 `qcom_smgr_hall.c` + Kconfig。**
（09 文档说"adsp 里搜不到 sns_dd_hall"没错 —— 因为 DSP 的驱动叫
`sns_dd_rohm` 或类似名字，我搜的关键词太窄。）

**但仍不建议现在做**：
1. gpio-keys 的 `SW_LID` 已能满足合盖休眠，零成本
2. 写驱动 + 编内核的工作量 > 收益
3. 等 1a 验证成功后再评估（如果 data_type=0 对 hall 也成立，写驱动就是纯收益）

**结论：可行，优先级低，不是死路。**

---

## 五、这次实验的真正价值

### 5.1 避免了一次白做

原计划：写 `cm3232.json` → push 到只读 persist → 重启 → 期望生效。
**实际会发生**：
1. persist 只读，得先 remount rw（有风险）
2. 写了也没用（registry 本来就对）
3. 白折腾，还可能破坏现有正常工作的 registry

**被三步证据拦住了：UUID 搜索、conf 段落、DSP 直连。**

### 5.2 找到了真正的 bug，而且它解释了所有现象

| 现象 | units bug 的解释 |
|---|---|
| accel/gyro/mag 能读 | `max_sample_rate=0` → `report_rate=0` → DSP 用默认值 → 过 |
| ALS 不能读 `0x501` | `max_sample_rate=100` → `report_rate=6553600` → 超出范围 → 拒 |
| `scan_elements` 都正常 | 通道注册与 buffering 是两条路径，前者与 data_type 无关 |
| 方向修好后 accel 完全可用 | 同第一条 |

**一个 bug 解释全部现象，这是判断根因正确的重要标志。**

### 5.3 方法论：假设必须用"能证伪"的方式验证

09 文档里我写"registry 里 grep 不到 cm3232"。这句话**技术上没错**
（`registry/config/*.json` 里确实没有），但**结论错了**
——因为我没有检查：
- `sensor_def_qcomdev.conf`（22 万字节的定义库）
- `sns.reg` 二进制本身
- DSP 的实际回话

**教训：**
> **"在某个文件里搜不到" ≠ "系统缺这个"。**
> 穷举搜索范围前，必须先搞清楚"谁消费谁"（依赖方向）。
> 这次的关键是先读了 `sns_reg_config` 才知道 JSON 是输入、sns.reg 是产物。

---

## 六、当前状态与下一步

### 6.1 设备状态（未做任何修改）

```
persist 分区   : 未动（本来只读）
sns.reg        : 未动（本来就不缺 CM3232）
boot 分区      : 未动（0 文件）
内核           : 7.0.14-sdm660（未重编）
桌面           : Xorg + XFCE 正常
tablet-orientd : 已装，disabled
备份           : /root/sensor-registry-backup-20261024-102514（172 KB）
```

**本次实验唯一的写操作是备份文件。**

### 6.2 下一步

| # | 动作 | 要编内核 | 状态 |
|---|---|---|---|
| 1 | 反汇编全部 `prepareAddMsg`，补齐 data_type 表 | ❌ | ✅ **本轮完成** |
| 2 | 写内核补丁（`data_type` 按 sensor type） | ✅ | 待做，补丁内容已明确 |
| 3 | 重编内核 → 刷 boot → 验证 ALS | ✅ | 需要你同意 |
| 4 | 若成功，考虑写 `qcom_smgr_hall.c` | ✅ | 已从"死路"改判"可行" |

**第 1 步已完成**，得到的表让第 2 步的补丁非常小（3 行）。

### 6.3 什么时候需要你的许可

- **刷 boot**（第 3 步）—— 会改启动分区。有 `tools/pmos-boot2.img` 回退。
- **重编内核**（第 2 步）—— 在 VM 上做，不碰平板。

**注意**：你已经说过"boot 暂不刷"。所以我可以先把补丁写好、在 VM 上编好，
**产出一个 boot.img 放在那里待用，但不刷入**。你什么时候想试再刷。

---

## 九、补丁草案（可直接用）

文件：`drivers/iio/common/qcom_smgr/qcom_smgr.c`

```diff
--- a/drivers/iio/common/qcom_smgr/qcom_smgr.c
+++ b/drivers/iio/common/qcom_smgr/qcom_smgr.c
@@
+/*
+ * The DSP expects a different "data type" per sensor class.
+ * Android's SSC HAL hardcodes these in each sensor class'
+ * prepareAddMsg() (see Light::prepareAddMsg in sensors.ssc.so):
+ *
+ *   Accelerometer  sensor_id 0x00  data_type 0
+ *   Gyroscope      sensor_id 0x0a  data_type 0
+ *   Magnetic       sensor_id 0x14  data_type 0
+ *   Light          sensor_id 0x28  data_type 1   <-- only non-zero
+ *   HallEffect     sensor_id 0x50  data_type 0
+ *
+ * Requesting ALS with data_type 0 makes the DSP answer 0x501.
+ */
+static u8 qcom_smgr_data_type_for(struct qcom_smgr_sensor *sensor)
+{
+	if (sensor->type == SNS_SMGR_SENSOR_TYPE_PROX_LIGHT)
+		return SNS_SMGR_DATA_TYPE_SECONDARY;
+
+	return SNS_SMGR_DATA_TYPE_PRIMARY;
+}
+
 static int qcom_smgr_request_buffering(struct qcom_smgr *smgr,
 				       struct qcom_smgr_sensor *sensor,
 				       bool enable)
@@
 		req.item_len = 1;
 		req.items[0].sensor_id = sensor->id;
-		req.items[0].data_type = SNS_SMGR_DATA_TYPE_PRIMARY;
+		req.items[0].data_type = qcom_smgr_data_type_for(sensor);
 
 		req.items[0].sampling_rate = sample_rate;
```

**改动量：+15 行（含注释），1 行实质逻辑。**

### 9.1 验证方法

```bash
# 刷入后（或先在 VM 上交叉编译验证）
echo 1 > /sys/bus/iio/devices/iio:device3/buffer/enable
# 期望：写入成功，dmesg 无 0x501

cat /sys/bus/iio/devices/iio:device3/buffer/data_available
# 期望：> 0

# 然后验证数值合理性（应该随光照变化）
# 用手遮住屏幕上方 / 拉开窗帘，看 in_proximity 值变化
```

### 9.2 但如果 1a 不够（备选：1b units）

若改完 `data_type` 仍失败，则问题在 `report_rate`/`sampling_rate` 单位。
那时再考虑：
```c
/* 可能是 */
req.report_rate = sample_rate * SMGR_TICKS_PER_SECOND;   /* 32768 vs 65536 */
req.items[0].sampling_rate = sample_rate;                 /* 保持裸 Hz */
```
**但这是猜的，不能盲改。优先验证 1a。**

---

## 十、本轮新增工具

| 文件 | 用途 |
|---|---|
| `tools/qmi_als_probe.py` | 直接对 DSP 发 QMI，读 sensor 列表（**已证明有用**） |
| `tools/decode_qmi.py` | 解码 QMI 响应 TLV |
| `tools/decode_list.py` | 解码 sensor 列表（对齐） |
| `tools/definitive_datatypes.py` | **★ 从 .so 提取全部 sensor_id/data_type** |
| `tools/verify_fields.py` | 校验 aarch64 指令字段编码 |
| `tools/decode_aarch64.py` | 手写 aarch64 解码器 |
| `tools/parse_prox_channels.py` | 解析 `.ko` 的 IIO channel 数组 |
| `tools/reg_uuid_probe.py` | **★ 在 sns.reg 里搜 UUID（推翻假设的关键）** |

证据：`evidence/reg-step0..6.txt`、`evidence/src-probe*.txt`、
`evidence/disasm-*.txt`、`evidence/test-*.txt`、
`evidence/definitive_datatypes.txt`
