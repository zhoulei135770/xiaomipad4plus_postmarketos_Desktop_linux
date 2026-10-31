# 09 · P0-1 传感器 raw 通道 · 完整调查与结论（2026-10-24）

> **本文推翻了 `08-HARDWARE-AUDIT.md` 第二节的结论。**
> 08 文档说「`scan_elements` 为空、驱动在但读不到数据」。
> **实测证明：这个判断是错的。** 加速度计、陀螺仪、磁力计**一直都能读出真实数据**。
>
> ⚠️ **2026-10-24 10:55 更新：本文 §3 关于 ALS 的根因判断也被推翻了。**
> 不是"缺 registry JSON"，而是**内核驱动的 `data_type` 硬编码**。
> 详见 **`11-REGISTRY-EXPERIMENT.md`**（含可直接用的补丁草案）。
> 本文 §3 保留作为"错误假设的记录"，不要照它执行。
>
> 本文档是 P0-1 的权威记录，含全部实测证据、真正的根因、以及下一步（改驱动源码 / 重编内核）的精确指令。

---

## 零、一句话结论

```
传感器不是"全都废"。五个传感器的真实状态：

    加速度计 BMI120   ✅ 能读（实测 9.81 m/s² 重力）  → 方向已修，只差 daemon
    陀螺仪   BMI120   ✅ 能读（实测静态 ~0.02 rad/s）
    磁力计   AK09918  ✅ 能读（实测 117 µT 地磁）
    环境光   CM3232   ⚠️ DSP 拒绝 0x501
                        └─ DSP 里驱动齐全（104 符号），只缺一份 registry JSON
    霍尔     BU52061  ✅ 硬件可用
                        └─ DSP 和内核都没有驱动，但 gpio-keys 的 SW_LID 一直工作
```

**四件事，各有各的解，而且三件不用编内核：**

| 需求 | 解法 | 要编内核？ |
|---|---|---|
| 自动旋转 | udev 修方向（✅已完成）+ 一个 daemon | ❌ |
| 自动亮度 | 补 `cm3232.json` 到 DSP registry | ❌ |
| 合盖休眠/开盖唤醒 | 监听 `gpio-keys` 的 `SW_LID` | ❌ |
| ALS 语义正确（lux 而非 proximity） | 改 `qcom_smgr_prox.c` 通道类型 | ✅ **要** |

> **本文的关键价值：30 分钟固件验尸，避免了写一个注定读不到数据的 hall 内核驱动。
> 详见 §3.4 和 §4.3。**

---

## 一、08 审计文档错在哪（必须先纠正）

| 08 文档原话 | 实测真相 | 证据 |
|---|---|---|
| "`scan_elements` 全为空" | **4 个设备每个都有 12 或 6 个 scan_elements** | `p0_1_sensors_probe.sh` 输出 |
| "没有 `in_accel_x_raw` 通道" | SMGR 是**纯 buffer 型**设备，本来就没有 `*_raw` sysfs 属性，通道在 `scan_elements/` 里 | 同上 |
| "buffer/enable 只有 accel 能写" | **accel / gyro / mag 三个都能写成功**，只有 prox 失败 | `p0_1_buffer_test.sh` |
| "用户态读不到数据" | `/dev/iio:device2` 读出 768 字节/秒真实样本 | `p0_1_dsp_probe.sh` D 段 |
| "驱动 `qcom_smgr` probe 逻辑有问题" | 驱动完全正常，probe 正常，4 个 IIO 设备全注册 | dmesg 干净，无 probe 错误 |

**怎么错的**：只看了 `ls /sys/bus/iio/devices/iio:device2/`（顶层属性），
没看 `scan_elements/` 子目录，也没真的去 `/dev/iio:deviceN` 读。

### 真正的原始症状（应该这么描述）

```
✅ 数据通道存在且工作
❌ iio-sensor-proxy 报 "No ambient light sensor / No proximity / No compass"
❌ 桌面上没有自动旋转、没有自动亮度、没有合盖休眠
```

也就是说：**问题不在内核采数据，而在"用户态拿不到/没消费"这两个环节。**

---

## 二、五个传感器的完整体检表

| # | 芯片 | I2C/SUID | IIO 设备 | buffer enable | 真实数据 | 结论 |
|---|---|---|---|---|---|---|
| 1 | BOSCH BMI120 加速度计 | `0x00` | `iio:device2` `qcom-smgr-accel` | ✅ 成功 | ✅ `z = -9.81 m/s²` | **可用** |
| 2 | BOSCH BMI120 陀螺仪 | `0x0a` | `iio:device4` `qcom-smgr-gyro` | ✅ 成功 | ✅ `~0.02 rad/s`（静止） | **可用** |
| 3 | AKM AK09918 磁力计 | `0x14` | `iio:device5` `qcom-smgr-mag` | ✅ 成功 | ✅ `117 µT`（地磁正确） | **可用** |
| 4 | Capella CM3232 环境光 | `0x28` | `iio:device3` `qcom-smgr-prox` | ❌ **失败 `0x501`** | ❌ 无 | **DSP 拒绝** |
| 5 | ROHM BU52061NVX 霍尔 | `0x50` | 无（`qcom-smgr-hall-effect` 未绑定） | — | — | **无驱动** |

### 2.1 加速度计原始数据（`evidence/P0-1-evidence.txt` 第 2 段）

```
x=   0.153 y=   0.369 z=  -9.816 m/s2  ts=51775112
x=   0.177 y=   0.388 z=  -9.821 m/s2  ts=51775278
x=   0.187 y=   0.388 z=  -9.787 m/s2  ts=51775445
...
```
**tan(z) 稳定在 -9.8** —— 平板平放，重力沿 -Z。物理完全正确。

### 2.2 陀螺仪（静止）

```
gx=  0.0309 gy=  0.0186 gz=  0.0005 rad/s
gx= -0.0080 gy=  0.0176 gz= -0.0085 rad/s
```
静止时接近 0，噪声水平正常（BMI120 零偏）。

### 2.3 磁力计

```
mx=  0.9255 my= -0.2610 mz=  0.6750 |B|= 117.48 uT
```
**117 µT ≈ 地球磁场（25–65 µT）+ 平板内部磁体**。数据有效。

### 2.4 采样率与缓冲

| 设备 | `buffer/length` | `data_available` 增长 | 说明 |
|---|---|---|---|
| accel | 128（默认） | 0 → 64（1 秒内） | 正常灌入 kfifo |
| gyro | 2 | 有数据 | 正常 |
| mag | 2 | 有数据 | 正常 |
| prox | 2 | 0 | enable 就失败，灌不进 |

### 2.5 采样率数值是 0 的含义（不要误解）

```
in_accel_sampling_frequency = 0
in_anglvel_sampling_frequency = 0
in_magn_sampling_frequency = 0
in_proximity_sampling_frequency = 5
```
`0` **不代表没数据**。数据实测是流动的（见 2.1）。
`0` 是驱动里 `data_type_count` 相关的默认值，读起来像"未设置"。
**教训：不要用 sysfs 的采样率判断有没有数据流。**

---

## 三、环境光（CM3232）失败的真正根因

> **⚠️ 本节的核心结论已被 `11-REGISTRY-EXPERIMENT.md` 推翻。**
> 真实根因：**内核把 `data_type` 硬编码为 0，而 ALS 需要 1**。
> 下面保留原始调查过程（很多证据仍然有效），但**结论读 11 文档**。
>
> 仍然有效的部分：
> - `0x501` 是 DSP 返回的 result code（§3.1、§3.2）
> - `5-60` 是 QRTR node/port 不是 I2C（§6.2 更正）
> - prox 驱动用错了 IIO 通道名（§3.8）
> - DSP 输出的单位是 mlux（§3.6）
>
> 被推翻的部分：
> - ~~"registry 是 SDM845 的，缺 CM3232"~~ → CM3232 一直在
>   `sensor_def_qcomdev.conf` 的 sdm660 段（config 2300-2312），
>   `sns.reg` 里也有它的 UUID（offset 6048）
> - ~~"补 cm3232.json 就能修"~~ → 不用补，registry 本来就是对的

### 3.1 现象

```bash
# echo 1 > /sys/bus/iio/devices/iio:device3/buffer/enable
# 失败，dmesg 出现：
[ 1853.063613] qcom_smgr 5-60: Buffering request failed: 0x501
```

`0x501` 是 **QMI/SNS 响应里的错误码**，不是 Linux errno。
它来自 SLPI（Sensor Low Power Island）固件，含义是"该传感器不支持这个 buffering 请求"。

### 3.2 驱动层完全正常（已用反汇编层证据确认）

从 `qcom_smgr.ko` 解压后 strings：

```
qcom_smgr_buffer_ops                    ← buffer 回调已注册
qcom_smgr_request_buffering             ← 请求函数存在
sns_smgr_buffering_req_ei               ← QMI 编码器存在
sns_smgr_buffering_resp_ei              ← QMI 解码器存在
"Buffering request failed: 0x%x"        ← 就是这条日志
SNS_SMGR_SENSOR_TYPE_PROX_LIGHT         ← prox 驱动请求的类型正确
```

**结论：Linux 侧请求格式正确，是 DSP 侧拒绝了。**

### 3.3 决定性证据：sensor registry 是 SDM845 的，不是 SDM660 的

固件 registry 在：
```
/run/msm-firmware-loader/mnt/persist/sensors/registry/config/
```

里面 24 个 `config_list.txt` 条目：
```
ak991x_dri_0.json        sdm845_ak991x_0.json
bmi160_0.json            sdm845_bmi160_0.json
adux1050_0.json          sdm845_adux1050_0.json
tmd2725.json             sdm845_tmd2725.json
sns_*.json ...
```

**每个文件的 `soc_id` 白名单：**
```json
"config": { "soc_id": [ "291", "246", "305", "321" ] }
```

**本机实测：**
```bash
$ cat /sys/devices/soc0/soc_id
317
$ cat /sys/devices/soc0/machine
SDM660
```

| 项 | 值 |
|---|---|
| registry 支持的 soc_id | 291（SDM845）、246、305、321 |
| **本机 soc_id** | **317（SDM660）** |
| 匹配结果 | ❌ **一个都不匹配** |

**而且 registry 里 `grep -ril 'cm32\|capella'` → 完全找不到。**

**这就是 0x501 的根因：**
- accel/gyro/mag 还能工作，因为 SLPI 对 BMI120 / AK09918 有**内置默认**驱动配置
- CM3232 是**冷门芯片**，必须靠 registry JSON 描述（`owner: sns_cm3232`、`.als.config`、I2C 地址、中断号、量程）
- registry 里没有 → SLPI 没有这个 sensor 的实例 → buffering 请求被拒 → `0x501`

### 3.4 ★ 固件验尸结果（已完成，这一节回答"改哪里"）

```
$ 逐文件扫描 /run/msm-firmware-loader/target/adsp.b*
FILE          SIZE      cm3232   capella   bu5206
adsp.b11      687460       1        1        1
adsp.b13       50720      104        0        0
```

**`adsp.b13` 里有一整个完整的 CM3232 驱动（104 个符号，含源码文件名）。**

存在的符号（节选）：
```
sns_dd_cm3232.c                        ← 源文件名
sns_dd_cm3232_uimg.c
sns_dd_cm3232_probe                    ← 有 probe
sns_dd_cm3232_init                     ← 有 init
sns_dd_cm3232_als_report_data          ← 有数据上报
sns_dd_cm3232_raw_convert_to_mlux      ← 有 lux 换算（单位是 mlux！）
sns_dd_cm3232_change_resolution        ← 有量程切换
sns_dd_cm3232_do_calibration           ← 有校准
sns_dd_cm3232_get_data
sns_dd_cm3232_set_attrib / get_attrib  ← 有 registry 属性读写
sns_dd_cm3232_get_attrib: no reg group
sns_dd_cm3232_init: registry params available
sns_dd_cm3232_init: no registry data
sns_dd_cm3232_init: notify SMGR to update registry with default values
```

**关键日志字符串 `sns_dd_cm3232_init: no registry data` 证明：**
驱动在，但**找不到自己的 registry 配置**，于是走了 fallback。
`0x501` 就是这条 fallback 路径的后果。

**同时确认（adsp.b13 里 DSP 侧完整的 sensor 驱动清单）：**
```
sns_dd_cm3232.c        ← 环境光（有！）
sns_dd_mag_fifo_akm099xx.c  ← 磁力计（有）
sns_dd_inertial_test.c
sns_batchbuff.c / sns_em.c / sns_ddf_timer.c / sns_ddf_uimg_comm_bus_i2c.c
```
**没有任何 hall 驱动**（`sns_dd_hall` / `sns_dd_rohm` 全 0 命中）。
`adsp.b11` 里只有字符串 `BU52061NVX` / `ROHM_Hall_Effect` / `HALL_EFFECT`（只是名字表，不是驱动）。

### 3.5 三条修复路线（按验尸结果重排）

> **⚠️ 这一节已过时。** 固件验尸之后又做了 registry 验证，结论已变：
> - 路线 A（补 JSON）：**取消**，registry 本来就有 CM3232
> - 真实修复：改 `qcom_smgr.c` 的 `data_type`（见 `11-REGISTRY-EXPERIMENT.md` §9）
>
> 下表保留作为决策过程记录。

| 路线 | 做法 | 难度 | 现在可行性 |
|---|---|---|---|
| **A. 补 registry JSON** ★推荐 | 写 `cm3232.json`，`owner` 必须是 **`sns_cm3232`**（不是 `sns_dd_cm3232`），照 `tmd2725.json` 的 `.als` 结构，加进 `config_list.txt`，push 到 persist | 中 | ✅ **可行**（驱动确认存在） |
| B. SSC/libssc 路径 | 走 `service 256 "Sensor Manager service"`（node 5 port 60） | 中高 | ⚠️ 需要改 libssc（只认 node 1） |
| C. 编内核 + 独立 I2C 驱动 | 写 `drivers/iio/light/cm3232.c` 直读 I2C | 高 | ⚠️ 会与 DSP 争 I2C，不推荐 |

**路线 A 的必要性现在很明确**：驱动有、硬件有、只缺一份配置。
这是**整个项目性价比最高的一处修复** —— 一份 JSON 换来自动亮度。

> **⚠️ 注意 registry 的 `soc_id` 过滤**：
> 现有 JSON 都是 `"soc_id": ["291","246","305","321"]`（SDM845 系），本机是 **317（SDM660）**。
> 所以新写的 `cm3232.json` 必须：
> - 要么把 `soc_id` 写成 `["317"]`
> - 要么**完全省略 `config.soc_id` 字段**（若 SLPI 允许无条件匹配）
>
> 这需要先做一次对照实验：把 `bmi160_0.json` 复制成测试文件，改 soc_id 看行为。
> **不确定点已明确，下一步是实验而非猜测。**

### 3.6 一个反直觉的细节：DSP 输出的单位是 mlux

```
sns_dd_cm3232_raw_convert_to_mlux: als_data = %d, als_it = %d, mlux = %d
```

DSP 侧算出的是 **milli-lux**（千分之一 lux）。
而内核 `qcom_smgr_prox` 报的 `scale = -0.099990844`、`offset = 6553`
正好对应 `raw × 0.1 → lux`（即 raw 是**厘 lux**，不是标准 IIO 的 lux）。

**这进一步证明：内核侧的通道语义是错的**（把它当 proximity，还用了错的 scale）。
修好 DSP 之后，内核通道也得一起改（见 §6.2 改动 1）。

### 3.7 SSC 路径的实测状态（重要：不能直接用）

```bash
$ qrtr-lookup | grep -i sensor
  271  2  0  1  16413  Sensor Registry service
  256  1 50  5     60  Sensor Manager service     ← SSC 在这里
  43   2 18  0      4  Subsystem control service
  43   2 20  5      6  Subsystem control service
```

`iio-sensor-proxy` 的 SSC 部分日志：
```
DEBUG: Service SSC not found
DEBUG: No SSC QMI client to release.
```

**原因**：libssc 只在 **QRTR node 1** 找 SSC，而本机 ADSP 是 **node 0**，
传感器管理服务在 **node 5**（SLPI）。libssc 0.4.4 不支持这种拓扑。

**所以 SSC 路线需要改 libssc（或自己写 QRTR 客户端），不是 zram 一个包能解决的。**

### 3.8 另一个真实缺陷：prox 驱动用错了通道名

`qcom_smgr_prox` 把 ALS 注册成了 **`in_proximity`**，不是 `in_illuminance`：

```
scan_elements/in_proximity_en
in_proximity_scale  = -0.099990844
in_proximity_offset = 6553.0
```

**这会带来两个问题：**

1. **iio-sensor-proxy 的 udev 规则不认它**
   `/usr/lib/udev/rules.d/80-iio-sensor-proxy.rules` 要求
   `TEST=="in_proximity_raw"`（poll 型）或 `scan_elements/in_intensity_both_en`（buffer 型 ALS）。
   本设备只有 `scan_elements/in_proximity_en`，**两条都不匹配** →
   `IIO_SENSOR_PROXY_TYPE` 为空 → **proxy 永远不会尝试它**。

2. **即使 data 出来了，语义也是错的**
   `scale = -0.1`、`offset = 6553` 说明原始值按 **16 位 lux 量程**映射
   （0→6553 lux，6553→5898 lux）。当成 "proximity" 用会得到荒谬值。

**结论：环境光想真正可用，必须让驱动暴露 `in_illuminance` 或者自己写消费者。**
这是一处**确定的驱动源码缺陷**，可以改（见 §6.2）。

---

## 四、霍尔传感器：内核里根本没有驱动

### 4.1 现状

```bash
$ ls /sys/bus/platform/devices/ | grep hall
qcom-smgr-hall-effect.80
$ cat .../qcom-smgr-hall-effect.80/modalias
platform:qcom-smgr-hall-effect
$ ls -l .../qcom-smgr-hall-effect.80/driver
(不存在 → 未绑定)
```

### 4.2 为什么未绑定：驱动模块不存在

```bash
$ modinfo qcom_smgr_hall
modinfo: ERROR: Module qcom_smgr_hall not found.

$ zcat /proc/config.gz | grep SMGR
CONFIG_IIO_QCOM_SMGR=m
CONFIG_IIO_QCOM_SMGR_ACCEL=m
CONFIG_IIO_QCOM_SMGR_GYRO=m
CONFIG_IIO_QCOM_SMGR_MAG=m
CONFIG_IIO_QCOM_SMGR_PRESSURE=m
CONFIG_IIO_QCOM_SMGR_PROX=m
# ← 没有 CONFIG_IIO_QCOM_SMGR_HALL
```

**上游内核根本没有 hall-effect 这个 Kconfig 选项。**
`qcom_smgr.ko` 里虽然有 `SNS_SMGR_SENSOR_TYPE_HALL_EFFECT` 枚举和
`"qcom-smgr-hall-effect"` 字符串（说明 API 预留了），
**但没有对应的 platform_driver 实现。**

### 4.3 但霍尔硬件其实是可用的（两条路）

**★ 固件验尸结论：DSP 侧也没有 hall 驱动。**
```
adsp.b13 的 sns_dd_*.c 清单：cm3232 / akm099xx / inertial_test —— 无 hall
adsp.b11 里只有字符串 BU52061NVX / ROHM_Hall_Effect / HALL_EFFECT（名字表，非驱动）
```
**所以「写驱动绑 `qcom-smgr-hall-effect`」这条路是死路**：
DSP 没有对应的 sensor driver，绑定成功也拿不到数据（必然也是 0x501）。

**结论：霍尔只能走 gpio-keys。**

**路 A：保护套检测已经能用（走 gpio-keys，不用 SMGR）★ 唯一可行路线**

```bash
$ cat /sys/devices/platform/gpio-hall-sensor/wakeup/wakeup3/name
gpio-hall-sensor
$ cat /sys/devices/platform/gpio-hall-sensor/power/wakeup
enabled
$ python3 (EVIOCGSW) -> SW bitmask = 0x0   (当前：盖子打开)
```

DTS 里定义得很清楚（`/tmp/live.dts` 第 2315 行）：
```dts
gpio-hall-sensor {
    pinctrl-names = "default";
    pinctrl-0 = <0xa6>;              /* gpio75, bias-pull-up */
    compatible = "gpio-keys";

    switch {
        wakeup-source;
        linux,can-disable;
        label = "Hall Effect Sensor";
        linux,input-type = <0x05>;   /* EV_SW */
        linux,code = <0x00>;         /* SW_LID */
        gpios = <0x29 0x4b 0x01>;    /* gpio 75, active high */
    };
};
```

**这意味着"合上保护套 → 自动休眠 / 打开 → 唤醒"今天就能实现，
完全不需要 SMGR，也不需要编内核。**
只需要一个监听 `/dev/input/event3` 的 `SW_LID` 的小 daemon。

> ⚠️ 待验证：需要一个磁铁贴到平板左侧看 `SW_LID` 是否翻转。
> 因为 `event_count = 0`，从未触发过。**这是唯一还没实测的环节。**

**路 B（已否决）：SMGR 的 IIO 通道**

原计划写 `qcom_smgr_hall.c` 让 `qcom-smgr-hall-effect.80` 绑定。
**固件验尸证明此路不通**：DSP 没有 hall 的 `sns_dd_*` 驱动，
即使内核绑定成功，buffering 请求也会被 DSP 拒绝（同 CM3232 的 0x501）。

| 方案 | 代价 | 收益 | 结论 |
|---|---|---|---|
| A. gpio-keys SW_LID | 一个 daemon（~50 行） | 合盖休眠/开盖唤醒 | ✅ **做这个** |
| B. 写内核 hall 驱动 | 编内核 + DSP 仍无数据 | 几乎没有 | ❌ 放弃 |
| C. 从 Android 移植 DSP hall 驱动 | 需改 ADSP 固件（签名） | 极小 | ❌ 不可能 |

---

## 五、自动旋转：真正的阻塞点已解决

### 5.1 阻塞点一：方向算反了（已修复 ✅）

**现象**：平板平放，`monitor-sensor` 报 `tilt: face-down`（实际是 face-up）。

**根因**：driver 内置的 mount matrix 是一个**镜面反射**，行列式 = -1，不是合法旋转矩阵。

```bash
$ cat /sys/bus/iio/devices/iio:device2/in_mount_matrix
0, -1, 0; -1, 0, 0; 0, 0, 1
```

```
det = -1    ← 镜面，不是旋转
```

原始加速度 `z = -9.81`（平放屏幕朝上），经过这个矩阵变成 `z = -9.75`，
iio-sensor-proxy 用 `accel.z > 0` 判断 face-up → 得到 face-down。**全反。**

**修复（纯用户态，已完成并验证）**：
```bash
# /etc/udev/rules.d/99-tablet-accel-matrix.rules
ACTION=="remove", GOTO="tablet_accel_matrix_end"
SUBSYSTEM=="iio", ATTR{name}=="qcom-smgr-accel", \
  ENV{ACCEL_MOUNT_MATRIX}="0,-1,0;-1,0,0;0,0,-1"
LABEL="tablet_accel_matrix_end"
```

**原理**：`in_mount_matrix` 是只读的（`-r--r--r--`），但 iio-sensor-proxy 会优先读
udev 的 `ACCEL_MOUNT_MATRIX` 环境变量（binary strings 里有
`Failed to parse ACCEL_MOUNT_MATRIX ('%s') from udev`）。第 3 行取反后 `det = +1`。

**验证**：
```
修复前: tilt: face-down   ← 错
修复后: tilt: face-up     ← 对 ✅
```

**六种姿态的数学验证**（矩阵求逆算过）：
| 原始 | 修正后 | 判定 |
|---|---|---|
| `(0,0,-9.81)` 屏幕朝上 | `(0,0,+9.81)` | face-up ✅ |
| `(0,0,+9.81)` 屏幕朝下 | `(0,0,-9.81)` | face-down ✅ |
| `(9.81,0,0)` | `(0,-9.81,0)` | 右边低 ✅ |
| ... | ... | 全部正确 |

### 5.2 阻塞点二：`iio-sensor-proxy` 报 "No compass"

即使 mag 通道正常，proxy 也不认为有罗盘。原因在 udev 规则：

```bash
# /usr/lib/udev/rules.d/80-iio-sensor-proxy.rules
SUBSYSTEM=="iio", TEST=="scan_elements/in_rot_from_north_magnetic_tilt_comp_en", \
  ENV{IIO_SENSOR_PROXY_TYPE}+="iio-buffer-compass"
```

它要的是 **`in_rot_from_north_magnetic_tilt_comp_en`**（融合后的旋转矢量），
不是原始的 `in_magn_x_en`。**SMGR 只提供原始磁力计，不提供融合量。**

**结论：compass 这一项在纯 SMGR 路线上无解**（要么 DSP 侧开 fusion，要么自己算）。
但**罗盘对"办公电脑"不是必需品，自动旋转只需要加速度计。**

### 5.3 自动旋转还差什么

| 项 | 状态 |
|---|---|
| 加速度计数据 | ✅ 有 |
| 方向判断正确 | ✅ 已修（udev matrix） |
| proxy 输出 orientation | ✅ `monitor-sensor` 能收到 tilt 变化 |
| **一个监听 orientation 并调用旋转的 daemon** | ❌ **还没有** |
| **旋转时 GPU 不挂死** | ⚠️ 已有约束：横屏 llvmpipe，竖屏 GPU |

**桌面是原生 Xorg（不是 Wayland）**，没有 wlroots 的自动旋转。
可选实现：
- `monitor-sensor --accel` 输出 `orientation: left-up` 等，脚本解析 → 调 `tablet-display-mode`
- 或者直接读 `/sys/bus/iio/devices/iio:device2` 自己算，不依赖 proxy

> **注意现有约束（`07-xorg-xfce.md` §3）**：
> `xrandr --rotate` + glamor 会硬挂死 Adreno 512（已发生一次，需物理重启）。
> 现有方案是横屏切 `AccelMethod "none"`（llvmpipe）。
> **自动旋转必须复用 `tablet-display-mode` 已经验证过的路径，不能在固定 glamor 下直接转。**

---

## 六、下一步：改驱动源码 / 重编内核（精确指令）

> 用户明确要求："接下来是改驱动源码，重编内核"。
> 本节给出**必须改什么、在哪改、怎么验证**。不确定的地方明确标出来。

### 6.1 构建环境（已验证可用）

```
VM:       ssh user@192.168.1.200   密码 <VM_PASSWORD>   ← 实测在线
pmaports: ~/.local/var/pmbootstrap/cache_git/pmaports
内核包:   device/testing/linux-postmarketos-qcom-sdm660/
配置文件: config-postmarketos-qcom-sdm660.aarch64
设备包:   device/testing/device-xiaomi-clover/
```

**当前内核**：`7.0.14-sdm660 #2-postmarketos-qcom-sdm660`，构建日期 `Sun Oct 11 18:34:49 UTC`。

### 6.2 改动清单（按优先级）

#### 改动 1：给 prox 驱动补 `in_illuminance` 通道 ★★★ 最确定

**为什么**：现在 ALS 被注册成 `in_proximity`，导致
(a) udev 规则不认、(b) 语义错误。这是**纯源码问题**，与 DSP 的 0x501 无关。

**文件**：`drivers/iio/proximity/qcom_smgr_prox.c`
（或上游 `drivers/iio/light/`，需在源码树里确认实际路径）

**改什么**：
```c
/* 现在（推测结构，需对照源码确认） */
static const struct iio_chan_spec qcom_smgr_prox_iio_channels[] = {
    {
        .type = IIO_PROXIMITY,
        .info_mask_separate = BIT(IIO_CHAN_INFO_SCALE) | BIT(IIO_CHAN_INFO_OFFSET),
        ...
    },
    IIO_CHAN_SOFT_TIMESTAMP(1),
};
```

**要改成**（照 `drivers/iio/light/` 里同类驱动）：
```c
static const struct iio_chan_spec qcom_smgr_prox_iio_channels[] = {
    {
        .type = IIO_INTENSITY,              /* ← ALS 用 intensity/illuminance */
        .modified = 1,
        .channel2 = IIO_MOD_LIGHT_CLEAR,
        .info_mask_separate = BIT(IIO_CHAN_INFO_RAW) | BIT(IIO_CHAN_INFO_SCALE),
        .scan_index = 0,
        .scan_type = { .sign = 'u', .realbits = 32, .storagebits = 32 },
    },
    IIO_CHAN_SOFT_TIMESTAMP(3),
};
```

**同时要改**：
- udev 规则期望 `in_intensity_clear_raw`（poll）或 `scan_elements/in_intensity_both_en`（buffer）
- **scale 必须改成 0.001**（DSP 输出 mlux，见 §3.4 末尾与 §3.8），不是现在的 `-0.09999`
- 保留 `offset = 0`（现在的 6553 是中点映射的遗留，lux 不需要）

**验证**：
```bash
ls /sys/bus/iio/devices/iio:device3/scan_elements/   # 应出现 in_intensity_clear_en
udevadm info -q env -p /sys/bus/iio/devices/iio:device3 | grep IIO_SENSOR
#   期望: IIO_SENSOR_PROXY_TYPE=iio-buffer-als
timeout 5 monitor-sensor    # 期望: "Has ambient light sensor"
```

> ⚠️ **但注意**：这一项**只在 DSP 的 0x501 也解决之后才有数据**。
> 改通道名只是让用户态能认出来。真正的 0x501 在 DSP 侧（见改动 3）。

#### 改动 2：~~新增 hall-effect 驱动~~ ❌ **已否决，不要做**

原计划写 `drivers/iio/magnetometer/qcom_smgr_hall.c`。

**固件验尸证明这条路是死路**（§4.3、§3.4）：

| 层 | hall 状态 |
|---|---|
| 硬件（ROHM BU52061NVX） | ✅ 有（I2C 5-0x50，SMGR 枚举到了） |
| **DSP 驱动（adsp.b13）** | ❌ **不存在**（无 `sns_dd_hall` / `sns_dd_rohm`） |
| 内核驱动 | ❌ 不存在（无 `CONFIG_IIO_QCOM_SMGR_HALL`） |

三层缺两层，且 DSP 固件有签名、无法补。
**即使写了内核驱动，DSP 也会拒绝 buffering（同 0x501）。**

**正确做法：用 gpio-keys 的 SW_LID**（硬件已经跑通的 independent 路径），
写一个监听 `/dev/input/event3` 的 daemon，不需要编内核。

#### 改动 3：ALS 的 `0x501` —— 补 DSP registry JSON ★★★ 最高性价比

**验尸结论已明确**：`adsp.b13` 里有完整的 `sns_dd_cm3232` 驱动（104 符号），
日志字符串明确说 `sns_dd_cm3232_init: no registry data`。
**只缺一份配置。**

**做法**：

1. 备份现有 registry：
```bash
cp -a /run/msm-firmware-loader/mnt/persist/sensors/registry \
      /run/msm-firmware-loader/mnt/persist/sensors/registry.bak-$(date +%s)
```

2. 照 `tmd2725.json` 的格式写 `cm3232.json`：
```json
{
  "config": {
    "hw_platform": [ "MTP", "Dragon", "Surf", "QRD" ],
    "soc_id": [ "317" ]
  },
  "cm3232_0": {
    "owner": "sns_cm3232",
    ".als": {
      "owner": "sns_cm3232",
      ".config": {
        "owner": "sns_cm3232",
        "is_dri":{ "type": "int", "ver": "0", "data": "0" },
        "hw_id":{ "type": "int", "ver": "0", "data": "0" },
        "res_idx":{ "type": "int", "ver": "0", "data": "0" },
        "sync_stream":{ "type": "int", "ver": "0", "data": "0" }
      }
    }
  }
}
```

3. **平台配置（总线/地址/中断）**

> **⚠️ 重要更正（09:55 实测）：`5-60` 不是 I2C 地址，是 QRTR node 5 port 60。**
>
> ```bash
> $ ls /sys/bus/i2c/devices/
> 0-005d  1-002c   i2c-0   i2c-1        # 只有 i2c-0 / i2c-1，没有 i2c-5
> $ ls /sys/bus/i2c/devices/5-0060
> No such file or directory
> $ readlink -f /sys/bus/iio/devices/iio:device2
> .../glink-edge.IPCRTR.-1.-1/5-60/qcom-smgr-accel.0/iio:device2
> ```
>
> `5-60` 是 **ADSP glink 上的 QRTR 设备**（node 5, port 60），
> 对应 `qrtr-lookup` 里的 `256  1  50  5  60  Sensor Manager service`。
> **传感器芯片的 I2C 是 DSP 内部自己走的**（`sns_ddf_uimg_comm_bus_i2c.c`），
> 内核完全看不到那条总线。

**这带来一个严重后果**：`bus_instance` / `slave_config` / `dri_irq_num`
**不能照抄 `sdm845_tmd2725.json` 的值**——那套值是 SDM845 的 I2C 拓扑。

本机该怎么填，**目前未知**，有两个可能：

| 可能 | 含义 | 怎么判断 |
|---|---|---|
| **A. 不用填平台配置** | DSP 内部已有 CM3232 的 I2C 连接信息（编译进驱动或从别处读） | 只写 `.als.config` 部分，不写 `_platform` 节点，看是否生效 |
| **B. 必须填** | DSP 需要 registry 告诉它 I2C 总线号/地址 | 需要找到 SDM660 clover 的真实 I2C 编号 |

**这个不确定点比之前的三个都关键。**
建议实验顺序：
1. 先试**只写 `.als.config`**（不含 `_platform`）—— 最简单，若 DSP 有内置连接信息就能成
2. 不行再加 `_platform`，从 `bus_instance = 0` 开始逐个试（DSP 的 I2C 编号与内核不同）

`slave_config = 40`（0x28）这个值来自 dmesg 的 SMGR 枚举，**这个是对的**。
`dri_irq_num` 完全未知，如果 CM3232 走轮询（driver 里有 `handle_timer`），
可能根本不需要中断。

4. 加进 `config_list.txt`（追加一行 `cm3232.json,`）

5. 重启传感器栈：
```bash
systemctl restart iio-sensor-proxy
# registry 是 DSP 启动时读的，真正生效大概率要：
reboot
```

**验证**：
```bash
echo 1 > /sys/bus/iio/devices/iio:device3/buffer/enable   # 期望：成功
dmesg | grep -i smgr                                     # 期望：无 0x501
```

**⚠️ 三个不确定点（必须实验确认，不要盲试）**：

| # | 不确定点 | 怎么确认 |
|---|---|---|
| 1 | `soc_id` 该写 `317` 还是省略 | 复制 `bmi160_0.json` 做对照实验，看哪个能生效 |
| 2 | `owner` 是 `sns_cm3232` 还是 `sns_dd_cm3232` | 从 adsp.b13 的字符串看是 `sns_dd_cm3232`，但 registry 惯例是 `sns_<chip>`（如 `sns_bmi160`、`sns_ak0991x`）→ **优先试 `sns_cm3232`** |
| 3 | `dri_irq_num` 是多少 | 查 `/proc/device-tree` 的 i2c5 子节点，或 dmesg 里的 irq 分配 |

**风险**：低。persist 分区可备份，写错最多传感器失效，不影响启动。
**必须做备份**（第 1 步）。

#### 改动 4：accel mount matrix 改到驱动里（可选，锦上添花）

**现状**：已用 udev 修好，工作正常。
**但**：`in_mount_matrix` 是硬编码在驱动里的（`strings` 确认：driver 里**没有** `mount-matrix` 字符串，
不读 DT）。如果想让改动更"正统"，可以：
```c
/* qcom_smgr_accel.c，把内置矩阵改对 */
{ 0, -1, 0, -1, 0, 0, 0, 0, -1 },   /* 原: 第三行是 +1 */
```
**收益低**（udev 已经解决），**优先级最后**。

### 6.3 重编内核的标准流程

```bash
# 1. 进 VM
ssh user@192.168.1.200

# 2. 改 pmaports 里的源码/配置
cd ~/.local/var/pmbootstrap/cache_git/pmaports/device/testing/linux-postmarketos-qcom-sdm660
#   内核源码由 APKBUILD 下载到 chroot，改 driver 源码要用 patch 或改 APKBUILD 的 source

# 3. 强制重编内核（不要用 --build_pkgs_on_install，那是给安装用的）
export PATH=$PATH:$HOME/.local/bin
pmbootstrap build --force linux-postmarketos-qcom-sdm660

# 4. 重新打包 boot 镜像
pmbootstrap install --password <SUDO_PASSWORD>
pmbootstrap export
# 产物: /tmp/postmarketOS-export/boot.img

# 5. 拉回 Windows
python get_vm.py /tmp/postmarketOS-export/boot.img ./boot-p01.img

# 6. 刷入（注意：这是危险操作，先确认 pmos-boot2.img 在手）
& "D:\APPS\platform-tools\fastboot.exe" flash boot boot-p01.img
& "D:\APPS\platform-tools\fastboot.exe" reboot
```

**风险控制**：
- 基线镜像 `tools/pmos-boot2.img`（25,653,248 B）必须保留
- 刷坏后恢复：`fastboot flash boot pmos-boot2.img`
- **不要动 userdata**（rootfs 里有关卡好的桌面）

### 6.4 改动优先顺序（固件验尸完成后重排）

> **⚠️ 2026-10-24 10:55 再次重排。** 第 3 项（补 JSON）已取消，
> 因为 registry 本来就是对的。详见 `11-REGISTRY-EXPERIMENT.md`。

```
1. 自动旋转 daemon（纯用户态）                        ← ✅ 已完成，见 10-AUTOROTATE.md
2. 保护套休眠（监听 SW_LID，纯用户态）                ← ✅ 代码就绪，待磁铁实测
3. ~~补 cm3232.json 到 DSP registry~~                 ← ❌ 取消（registry 本来就对）
4. 改 qcom_smgr.c 的 data_type（ALS 用 1）            ← ★ 唯一真正的修复，3 行补丁
5. 写 qcom_smgr_hall.c + 编内核                       ← 已从"死路"改判"可行"，优先级低
6. mount matrix 改进驱动（可选）                      ← 收益最低
```

**第 3 项为什么取消**：实测证明
- `sensor_def_qcomdev.conf` 的 sdm660 段有 CM3232（`enable=2`）
- `sns.reg` 里有 CM3232 的 UUID（offset 6048）
- DSP 回话 `result=0x0000`，列了 `0x28 PROX_LIGHT`

**第 4 项才是答案**：Android HAL 的 `Light` 类写 `data_type=1`，
内核却对**所有**传感器硬编码 `0`。

**第 1、2 项已完成** → 详情见 **`10-AUTOROTATE.md`**
**第 4 项补丁草案** → 见 **`11-REGISTRY-EXPERIMENT.md` §9**

**关键认知变化**：
- 固件验尸**推翻**了"要写 hall 驱动"的原计划 → **11 文档又改回"可行"**
  （因为 `sensor_def_qcomdev.conf` 有 hall、`sns.reg` 有 hall UUID、
  DSP 报 `0x50 HALL_EFFECT`、Android 有 `HallEffect::prepareAddMsg`）
- registry 验证**推翻**了"缺 CM3232 配置"的假设
- **第 1、2 项完全不需要编内核**，却解决了用户最直观的两个体验问题

**为什么第 3 项排在第 4 项前面**：
先让 DSP 吐出数据，再改内核通道名。
反过来做的话，改完内核还是拿不到数据，无法验证改动是否正确。

---

## 七、本次会话的实际改动（可回滚）

| 改动 | 路径 | 回滚 |
|---|---|---|
| **新增 udev 规则（修方向）** | `/etc/udev/rules.d/99-tablet-accel-matrix.rules` | `rm` 后 `udevadm control --reload-rules && udevadm trigger` |
| 装了 `qrtr` 工具 | apk | `apk del qrtr`（可选，很小） |
| 装了 `libssc` / `libssc-pyc` | apk | `apk del libssc-pyc`（注意 iio-sensor-proxy 依赖 libssc，**不要删 libssc**） |
| 加载了 `iio-trig-sysfs` | 运行时 | 重启即消失（未写入 modules-load） |

**没有改动**：boot 分区、rootfs 关键文件、任何驱动源码、任何 DT。

**当前 boot 分区**仍是 `boot-pri-mi2s.img`（见 00-GOAL §4.1 补丁版，无害）。

### 回滚验证

```bash
# 确认 udev 规则能被正确移除
rm -f /etc/udev/rules.d/99-tablet-accel-matrix.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=iio --action=change
udevadm info -q env -p /sys/bus/iio/devices/iio:device2 | grep MOUNT
#   期望：无输出（回到 face-down 的错误状态）
```

---

## 八、给下一个会话的原始命令（复现全部证据）

### 最快路径：一条命令拿到全部决定性证据

```powershell
cd C:\Users\zl\Documents\deepseek-harness\default-workspace\mipad4plus\tools
python run_sudo.py p0_1_evidence_snapshot.sh
```

输出已存 **`mipad4plus/evidence/P0-1-evidence.txt`**（13 段，本次实测）。
新会话如果只想快速复核"09 文档说的对不对"，跑这一条就够。

### 本次会话写过的全部探针（23 个，按主题）

| 脚本 | 产出 |
|---|---|
| `p0_1_evidence_snapshot.sh` | **★ 合并快照，13 段决定性证据** |
| `p0_1_sensors_probe.sh` | IIO 设备/通道/模块/固件/DTS 全景 |
| `p0_1_buffer_test.sh` | buffer enable 逐设备测试 + errno |
| `p0_1_dsp_probe.sh` | remoteproc 状态、chardev 读、0x501 复现 |
| `p0_1_hall_prox.sh` | 霍尔 event3、prox 深挖、accel/gyro/mag 解码 |
| `p0_1_proxy_hall.sh` | iio-sensor-proxy 状态、SW_LID、udev |
| `p0_1_matrix_als.sh` | mount matrix、ALS 各种频率重试、registry 目录 |
| `p0_1_decisive.sh` | 矩阵行列式、soc_id、registry 内容 |
| `p0_1_modules.sh` | 解压 `.ko.zst` 做 strings 分析 |
| `p0_1_mount_als.sh` | 驱动是否读 DT 的 mount-matrix |
| `p0_1_udev_als.sh` | udev 属性、ALS 注册成 proximity 的证据 |
| `p0_1_udev_fix.sh` | **首次验证 udev 覆盖矩阵有效** |
| `p0_1_ssc.sh` / `p0_1_ssc2.sh` | libssc/QRTR 路线可行性 |
| `p0_1_qrtr.sh` | QRTR 服务发现、Service SSC not found |
| `p0_1_registry.sh` | registry soc_id、平台配置格式 |
| `p0_1_trigger.sh` | IIO trigger 缺失、soc_id 确认 |
| `p0_1_ssc_verify.sh` | Sensor Manager service 定位 |
| `p0_1_firmware_autopsy.sh` | **★ 首次发现 cm3232 在固件里** |
| `p0_1_fw_detail.sh` | **★ 定位到 adsp.b13 的 104 个符号** |
| `p0_1_driver_census.sh` | **★ 全 DSP 驱动普查，确认无 hall** |
| `p0_1_why501.sh` | 0x501 机制、通道类型 |
| `p0_1_verify_state.sh` | 收尾状态核验 |

**注意**：`run_sudo.py` 是本次新增的（`ssh_pad.py` 不能正确传 sudo 密码，
会卡在 `sudo: Authentication failed`）。

### 关键单条命令

```bash
# 传感器全状态
for i in 2 3 4 5; do d=/sys/bus/iio/devices/iio:device$i; \
  echo "$(cat $d/name): enable=$(cat $d/buffer/enable)"; done

# 看真实数据（会打印 m/s²）
python3 -c "..."   # 见 p0_1_evidence_snapshot.sh 第 2 段

# 方向是否修好
timeout 6 monitor-sensor | tail -5     # 期望 tilt: face-up

# 0x501 复现
echo 1 > /sys/bus/iio/devices/iio:device3/scan_elements/in_proximity_en
echo 1 > /sys/bus/iio/devices/iio:device3/buffer/enable   # 失败 + dmesg 0x501

# soc_id（证明 registry 不匹配）
cat /sys/devices/soc0/soc_id          # 317
grep -ho '"soc_id":[^]]*]' /run/msm-firmware-loader/mnt/persist/sensors/registry/config/*.json | sort -u

# DSP 里有哪些传感器驱动（决定改内核还是改 JSON）
for f in /run/msm-firmware-loader/target/adsp.b*; do
  strings -a "$f" | grep -oE 'sns_dd_[a-z0-9_]+\.c' | sed "s|^|$(basename $f) |"
done | sort -u
```

---

## 九、方法论教训（补充到 00-GOAL §九）

### 6. 不要用"顶层 sysfs 列表"判断驱动是否工作

08 文档的错误是看 `ls /sys/bus/iio/devices/iio:device2/` 没看到 `in_accel_x_raw` 就下结论
"没通道"。**IIO 有两类设备：**

| 类型 | 特征 | 怎么读 |
|---|---|---|
| poll 型 | 有 `in_*_raw` sysfs 属性 | `cat in_accel_x_raw` |
| **buffer 型（本机）** | 有 `scan_elements/` + `buffer/`，**无 `*_raw`** | 读 `/dev/iio:deviceN` 字符设备 |

**正确判断法**：
```bash
ls scan_elements/            # 有 *_en / *_index / *_type 就是有通道
echo 1 > buffer/enable       # 能写成功就是能用
dd if=/dev/iio:deviceN bs=1 count=512   # 能读出字节就是有数据
```

### 7. `buffer/enable` 失败要先区分"本地错"还是"DSP 错"

```
写 /sys/.../buffer/enable 失败
  ├─ 有 dmesg "Buffering request failed: 0xNNN"  → DSP 侧拒绝，改内核无用
  └─ 无 dmesg，只有 EINVAL                        → 本地内核/clamp 问题，可以改
```

**0x501 属于前者。改内核救不了，必须动 DSP 的 registry 或绕开 DSP。**

### 8. 固件版本不匹配要看 `soc_id`，不要只看文件名

`snss.reg-xiaomi,clover-plus` 缺失时驱动会 fallback 到通用 `sns.reg`，
**但 fallback 的 registry 是 SDM845 的**（soc_id 291/246/305/321，本机 317）。
这导致部分传感器（ALS）失效，而 accel/gyro/mag 因为 DSP 有内置默认而侥幸可用。

**验尸命令**：
```bash
cat /sys/devices/soc0/soc_id
grep -o '"soc_id":[^]]*]' /run/msm-firmware-loader/mnt/persist/sensors/registry/config/*.json | head
```

### 9. udev 可以覆盖驱动的错误矩阵，不用改内核

`in_mount_matrix` 只读，但 `ACCEL_MOUNT_MATRIX` 环境变量可写，且 iio-sensor-proxy 优先用它。
**任何"方向反了"的问题，先试 udev，再想编内核。**

### 10. IIO 通道名决定用户态能不能看见

驱动把 ALS 注册成 `IIO_PROXIMITY`，`iio-sensor-proxy` 的 udev 规则就认不出来。
**通道名不是随便取的**：`IIO_INTENSITY`+`IIO_MOD_LIGHT_CLEAR` 才会生成
`in_intensity_clear_raw`，才会匹配 ALS 规则。

---

## 十、待用户决策 / 待物理验证

| # | 事项 | 需要什么 |
|---|---|---|
| 1 | 霍尔 `SW_LID` 是否真的随磁铁翻转 | **一块磁铁**，贴平板左侧，看 `event3` 有没有事件 |
| 2 | 自动旋转用哪种触发 | 决定：`monitor-sensor` 还是自己读 IIO |
| 3 | boot 是否刷回 `pmos-boot2.img` | 当前补丁版无害，可不刷 |
| 4 | ALS 走 registry 还是自写驱动 | 取决于 §6.2 改动 3 的固件验尸结果 |

---

## 十一、总结：P0-1 的真实进度

```
P0-1 原定目标：修复传感器 raw 通道
     ↓
    实际发现：raw 通道从来没坏过（3/5 传感器一直能用）
     ↓
    真正的问题是四件不同的事，各有各的解：
       1. 方向矩阵是镜面（已用 udev 修好 ✅，纯用户态）
       2. ALS 缺 DSP registry 配置（DSP 有完整驱动，只需补一份 JSON）
       3. 内核把 ALS 注册成了 proximity（改源码 + 编内核）
       4. 霍尔三层缺两层（DSP 无驱动 + 内核无驱动 → 只能走 gpio-keys）

P0-1 完成度：
    加速度计  ✅ 数据可用 + 方向已修正  →  自动旋转只差一个 daemon（零风险）
    陀螺仪    ✅ 数据可用
    磁力计    ✅ 数据可用（proxy 认不出 = 罗盘无解，但非必需）
    环境光    ⚠️ DSP 有驱动只缺配置（路线已明确，非内核问题）
    霍尔      ✅ 硬件可用（走 gpio-keys，不需要 DSP/Kernel 驱动）
```

### 这一轮最重要的三个认知

1. **DSP 固件验尸改变了整个计划。**
   原来打算写 hall 驱动 → 验尸发现 DSP 没有 hall driver，**这条路是死的**。
   原来以为 ALS 要写 I2C 驱动 → 验尸发现 DSP 有完整 `sns_dd_cm3232`，**只需补 JSON**。
   **30 分钟的 strings 扫描，避免了几天白费的内核开发。**

2. **"改驱动源码 + 重编内核"不是所有问题的答案。**
   自动旋转（udev 矩阵）、保护套休眠（gpio-keys）、ALS（DSP registry）
   —— 这三件都不需要编内核。
   **只有"内核把 ALS 注册成 proximity"这一件真的需要改源码。**

3. **08 审计文档的"传感器全废"是误判。**
   错在只看顶层 sysfs、没读字符设备。
   真实状态是 3/5 可用、2/5 有明确解法。
   **教训：判断 IIO 设备必须读 `/dev/iio:deviceN`，不能只看 sysfs 属性。**
