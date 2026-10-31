# 23 · CPU/GPU/温控/音频校准 —— Android 真值 vs pmOS 现状

> 2026-10-28 21:22 从运行中的 MoKee 采集，产物：`artifacts/mokee-20261028/hwdata.tgz`
> 解包后：`acdbdata.tgz`（513 KB 音频校准）、`persist.tgz`（设备唯一校准）、
> `thermal-engine-*.conf`、`cpugpu_thermal.txt`。

---

## 1. CPU 频点（Android 实测）

| 簇 | CPU | 范围 | 可用频点 |
|---|---|---|---|
| cluster0（Silver）| cpu0–3 | 633.6 – 1843.2 MHz | 633600 / 902400 / 1113600 / 1401600 / 1536000 / 1747200 / 1843200 |
| cluster1（Gold）| cpu4–7 | 1113.6 – 2208 MHz | 1113600 / 1401600 / 1747200 / 1958400 / 2150400 / 2208000 |

governor = `interactive`（msm-cpufreq 驱动）。

## 2. GPU

| 项 | 值 |
|---|---|
| 型号 | **Adreno512v1** |
| 频点 | 160 / 266 / 370 / 465 / 588 / **647** MHz |
| governor | `msm-adreno-tz` |

## 3. 温控策略（thermal-engine-normal.conf，节选）

| sensor | 阈值 | cluster0 上限 | cluster1 上限 |
|---|---|---|---|
| msm_therm | 39 °C | 1747.2 MHz | 2150.4 MHz |
| msm_therm | 41 °C | 1536 MHz | 1958.4 MHz |
| msm_therm | 43 °C | 1401.6 MHz | 1747.2 MHz |
| msm_therm | 45 °C | 1113.6 MHz | 1401.6 MHz |
| quiet_therm | 55 °C | `temp_state` 动作 | — |

另有 `thermal-engine-high / -nolimits / -map / -engine.conf` 四套档位配置。

## 4. pmOS 现状（现役 DTB 实测，`sdm660-xiaomi-clover-plus.dtb`）

| 项 | 现状 | 差距 |
|---|---|---|
| CPU OPP | `/cpus/cpu@*` **没有 `operating-points-v2`** | 无调频表 ⇒ 大概率跑固定频率 |
| thermal-zones | DTB 里**没有 `/thermal-zones` 节点**（只有 `thermal-sensor@10ae000`）| 无 trips、无 cooling-device ⇒ 无温控降频 |
| GPU OPP | 只有 **160 / 370 / 465 / 588 MHz** 四档 | 缺 **266** 与 **647** 两档（647 是 Android 的最高频）|
| CPU cooling | cpu@* 有 `#cooling-cells = <2>` | 但没有 thermal zone 引用它，等于没用上 |

⇒ **"CPU 调优"在 pmOS 上目前基本是空白**：没调频、没温控、GPU 少两档。
这一块的收益（续航 / 发热 / 峰值性能）比摄像头调色大得多，而且数据现在已经齐了。

## 5. 音频校准（ACDB）

`/vendor/etc/acdbdata/` 全套（`MTP/` 与 `QRD/sdm660-snd-card-d9p/`）：

```
Speaker_cal / Headset_cal / Handset_cal / Bluetooth_cal /
Global_cal / General_cal / Hdmi_cal .acdb   +  adsp_avs_config.acdb
```

`mixer_paths.xml` 只描述路由；**音色、扬声器保护、增益补偿都在 ACDB 里**。
mainline 的 ALSA 驱动不读 ACDB，但这些数值可以作为对照/移植参考
（尤其扬声器保护参数，直接影响"能不能开大音量而不炸"）。

## 6. 设备唯一校准（/persist，已打包 13 KB）

| 路径 | 内容 |
|---|---|
| `sensors/sns.reg` (25 KB) | 传感器 registry blob（含校准结果）|
| `sensors/registry/config/*.json` | bmi160（加速度/陀螺）、ak991x（磁力）、adux1050、tmd2725（ALS）配置 |
| `display/`、`bms/` | 面板/电池管理相关 |
| `wlan_mac.clover` | WiFi MAC（33 B）|

pmOS 的传感器现在能出数，但这些校准值没被使用 —— 磁力计/ALS 的偏差可能就来自这里。

## 7. 摄像色彩/清晰度：采了也没用（明确结论）

- 手机上"色彩好、清晰"来自 **QC 私有 ISP（VFE/CPP）+ 用户态 chromatix 调优库**，
  我们在 8.1 已经把 `*_chromatix.xml` / `chromatix_*.so` 抓下来了。
- **mainline CAMSS 不加载 chromatix**，出的是 sensor 原始 Bayer + 主线 ISP 处理链，
  参数体系完全不同（主线走 libcamera/soft-ISP 那套 tuning）。
- 真正对主线有用的 sensor 侧参数（mode 表、PLL）已经从 HAL 拿到：
  `167.2 MHz / FLL 1968 / LLPCK 2856 / 2592x1944@30`（见 FRONT-CAMERA.md §1c）。
- 结论：**不要在这上面花采集时间**；颜色/锐度只能在 mainline 出图后自己调。

---

## 8. 2026-10-29 凌晨复核：实际情况比之前记的更细致

### 8.1 CPU：确实完全没有 cpufreq

```
/sys/devices/system/cpu/cpu0/cpufreq/   → 不存在
/sys/kernel 里没有 cpufreq_driver
```

`arch/arm64/boot/dts/qcom/sdm660.dtsi` 里**没有 CPU 的 `operating-points-v2`**，
内核里虽然有 `cpufreq-dt.c` 和 `qcom-cpufreq-hw.c`，但 DT 没给任何一个 CPU 提供 OPP 表，
所以 CPU 一直跑在 bootloader 设的固定频率。

要做成，需要：
1. 每个 `cpu@N` 加 `operating-points-v2 = <&cpu_opp_table>`
2. OPP 表里填 **频率 + 电压**（这个数据目前没有：需要从厂商 kernel 的 CPR/clock 表反推，
   或者从 sdm660 的 vendor `cpufreq` 表里挖）
3. 让 `cpufreq-dt` 绑定（sdm660 不在 cpufreq-dt-platdev 的白名单里的话，得显式建 platform device）

⚠️ **电压填错会烧硬件/死机**，这一步必须谨慎，不能靠猜。

### 8.2 GPU：647/700/750 是**被主动注释掉**的，不是漏了

`sdm660.dtsi` 里的原注释（作者写的）：

```c
/* 750 MHz is only available on the highest speed bin
 * Though it cannot be used for now due to interconnect framework not
 * supporting multiple frequencies at the same opp-level.
 * These OPPs are correct, but we are lacking support for the GPU regulator.
 * Hence, disable them for now to prevent the platform from hanging on high
 * graphics loads. */
```

即：**647/700/750 的 OPP 数据是对的，但主线没有 GPU regulator 驱动**，
强行开会在高负载时挂死。所以：

```
运行中的 GPU 频点: 19.2M(idle) / 160 / 266 / 370 / 465 / 588 MHz
```

`266` 其实在表里且未注释（我们之前记"缺 266"是错的）。

⇒ 想上 647 MHz，正确做法是**实现 GPU 电压调节**（qcom 的 gpucc + CPR），
而不是简单把注释去掉。

### 8.3 温控

`/sys/class/thermal/` 下有 `thermal_zone0..11`（传感器都在），
但**没有 cooling_device 关联到 cpufreq**（因为压根没有 cpufreq）。
所以现在的"温控"只有被动读数，没有降频动作。

CPU cpufreq 一旦做出来，thermal zone 的 trips 才有意义；
两者的正确顺序是：先 CPU OPP → 再 thermal-zones + cooling-maps。

### 8.4 结论（优先级重排）

| 任务 | 价值 | 风险 | 前置 |
|---|---|---|---|
| CPU OPP + cpufreq | ★★★（续航/发热/性能）| 高（电压错会烧）| 需要厂商 CPR 电压表 |
| thermal-zones + cooling-maps | ★★ | 低 | 依赖 CPU cpufreq |
| GPU 647 MHz | ★ | 高 | 需要 GPU regulator 驱动 |

---

## 9. 传感器校准（/persist）—— 主线同样没有加载

### 9.1 内核侧结构

```
drivers/iio/accel/qcom_smgr_accel.c
drivers/iio/gyro/qcom_smgr_gyro.c
drivers/iio/proximity/qcom_smgr_prox.c
drivers/iio/pressure/qcom_smgr_pressure.c
        ↓ 通过 ADSP 的 SNS_SMGR 服务取数
drivers/remoteproc/qcom_common.c   ← sns-reg 子设备（传感器 registry 服务）
```

### 9.2 校准数据在哪

Android 侧：`/persist/sensors/sns.reg`（我们已打包，25 KB）+ `registry/config/*.json`。
这些由 Android 的用户态传感器守护进程喂给 ADSP。

**mainline 里没有任何代码读 `/persist/sensors`**（grep 全树只有 rproc 的 `sns-reg` 子设备名）。

⇒ **磁力计/ALS 的出厂校准在 pmOS 上没有生效**，这就是之前观察到"数值有偏差"的原因。
要修得通过 `sns-reg` 那条 rproc 通道把 registry 写进 ADSP —— 属于要单独研究的活，
优先级低（不影响主要功能）。

### 9.3 同类结论汇总（本次夜间复核）

| 数据 | 采集了 | mainline 能用吗 | 结论 |
|---|---|---|---|
| ACDB 音频校准 | ✅ | ❌ | 没扬声器保护，建议用户态加软限幅（见 28 号文档）|
| chromatix 摄像头调优 | ✅ | ❌ | 主线不读，且**不含 sensor 侧信息**，无用 |
| /persist 传感器校准 | ✅ | ❌ | 没有加载通道，磁力/ALS 有偏差 |
| thermal-engine 配置 | ✅ | 部分（数值可参考）| 但要先有 CPU cpufreq |
| CPU/GPU 频点 | ✅ | ✅ | 已用于修正文档结论 |

---

## 10. 🎯 2026-10-29 02:50：从厂商 DTB 里挖到了**完整的 CPU 频率/电压表**

之前说"需要 CPR 电压表，不能猜" —— 现在**不用猜了，数据在 `miui-dtb-0.dtb` 里**。

### 10.1 厂商的实现方式

```
/soc/cprh-ctrl@179c4000/thread@0/regulator    regulator-name = "apc0_pwrcl_corner"  ← silver (cpu0-3)
/soc/cprh-ctrl@179c8000/thread@0/regulator    regulator-name = "apc1_perfcl_corner" ← gold  (cpu4-7)
/soc/clk-cpu-660@179c0000                     CPU 时钟控制器
/soc/.../qcom,msm-cpufreq                     CPUFreq 驱动（cpu0_clk / cpu4_clk）
/soc/cpr4-ctrl@05061000                       CPR（图形/其他域）
```

### 10.2 SILVER 簇（cpu0–3，`apc0_pwrcl_corner`）

| corner | 频率 | 电压下限 | 电压上限 |
|---|---|---|---|
| 0 | 300.0 MHz | 588 mV | 724 mV |
| 1 | 633.6 MHz | 588 mV | 724 mV |
| 2 | 902.4 MHz | 596 mV | 724 mV |
| 3 | 1113.6 MHz | 652 mV | 788 mV |
| 4 | 1401.6 MHz | 712 mV | 868 mV |
| 5 | 1536.0 MHz | 744 mV | 1068 mV |
| 6 | 1747.2 MHz | 784 mV | 1068 mV |
| 7 | 1843.2 MHz | 844 mV | 1068 mV |

### 10.3 GOLD 簇（cpu4–7，`apc1_perfcl_corner`）

| corner | 频率 | 电压下限 | 电压上限 |
|---|---|---|---|
| 0 | 300.0 MHz | 588 mV | 724 mV |
| 1 | 1113.6 MHz | 596 mV | 724 mV |
| 2 | 1401.6 MHz | 652 mV | 788 mV |
| 3 | 1747.2 MHz | 712 mV | 868 mV |
| 4 | 1958.4 MHz | 744 mV | 988 mV |
| 5 | 2150.4 MHz | 784 mV | 988 mV |
| 6 | 2208.0 MHz | 844 mV | 1068 mV |

（`qcom,corner-frequencies` 里还有第二组速度档，gold 最高 2457.6 MHz、
silver 最高 1843.2 MHz —— 那是更高速度分档的 SKU，本机不用。）

### 10.4 但驱动仍然缺两块

| 需要 | 主线现状 | 工作量 |
|---|---|---|
| `clk-cpu-660`（CPU 时钟控制器 0x179c0000）| 只有 `clk-cpu-8996.c`，**没有 660 版本** | 中（新驱动，需 HFPLL/MUX 布局）|
| CPR/CPRH 稳压器（0x179c4000/0x179c8000）| `drivers/regulator` 里**没有 cpr** | 大（电压角 → 实际电压的换算 + fuse 校准）|
| OPP 表（频率/电压）| ❌ 无 | ✅ **数据已拿到（见上表）** |

### 10.5 可行的"降级方案"（不用写 CPR）

CPR 的作用是"按芯片个体差异微调电压"。如果**直接用电压上限**作为固定 OPP 电压：

```dts
cpu_opp: opp-table {
	compatible = "operating-points-v2";

	opp-300000000   { opp-hz = /bits/ 64 <300000000>;   opp-microvolt = <724000>; };
	opp-633600000   { opp-hz = /bits/ 64 <633600000>;   opp-microvolt = <724000>; };
	...
	opp-1843200000  { opp-hz = /bits/ 64 <1843200000>;  opp-microvolt = <1068000>; };
};
```

这就是**开环模式**（厂商 CPR 也支持 `qcom,cpr-scaled-open-loop-voltage-as-ceiling`）。
风险：电压偏高 → 功耗略大、发热略多，但**不会烧**（上限就是厂商的安全上限）。

**仍然需要 `clk-cpu-660` 驱动**，否则 `cpufreq-dt` 没有可调时钟。

### 10.6 结论

- 数据问题**解决了**（不用再从 vendor kernel 反推）
- 剩下的是**纯驱动工程量**：`clk-cpu-660`（中等）+ 可选 CPR（大）
- 如果只想要"能降频省电"，`clk-cpu-660` + 开环 OPP 表就够了

---

## 11. `clk-cpu-660` 的真实结构：是 **OSM/APM**，不是 HFPLL

### 11.1 厂商 DTB 里的节点（`/soc/qcom,clk-cpu-660@179c0000`）

```
compatible          qcom,clk-cpu-osm        ← OSM = Operating State Manager
#clock-cells        1
clocks              aux_clk, xo_a
interrupt-names     pwrcl-irq, perfcl-irq
qcom,apcs-cmd-rcgr  0x17911050, 0x17811050   ← 两个簇的 APCS 命令寄存器
qcom,apcs-cfg-rcgr  0x17911054, 0x17811054
qcom,l-val-base     0x17916004, 0x17816004   ← "L value"（电压请求编码）基址
qcom,apm-mode-ctl   0x179d0004, 0x179d0010   ← APM（自适应电源管理）
qcom,apm-ctrl-status 0x179d000c, 0x179d0018
qcom,apm-threshold-voltage  0x0d4e40 = 871 兆? (0x0d4e40 = 872000 µV)
qcom,osm-clk-rate   0x0bebc200 = 200 MHz     ← OSM 自身时钟
qcom,boost-fsm-en / droop-fsm-en / enable-llm-freq-vote / enable-llm-volt-vote
qcom,cc-reads/cc-delay/cc-factor  CC = cycle counter 校准
qcom,down-timer / llm-*-timer     限流定时器
```

### 11.2 主线的差距

| 项 | 主线现状 |
|---|---|
| OSM 时钟驱动（`qcom,clk-cpu-osm`）| ❌ **完全没有**（`drivers/clk/qcom` 只有 `clk-cpu-8996.c`）|
| `qcom,cpufreq-hw` | ✅ 有驱动，但用于 **sdm845/sdm670/sc7180/sm8250…**，DT 里没有 sdm660 入口 |
| APM（自适应电源管理）| ❌ 无 |

### 11.3 这意味着什么

CPU 调频在 SDM660 上**不是"补个 OPP 表"就能开的**，需要：

1. **写 OSM/APM 驱动**（新文件，参考 sdm845 的 cpufreq-hw 与下游
   `drivers/clk/qcom/clk-cpu-osm.c` 的 vendor 实现）
   - 关键寄存器：APCS cmd/cfg rcgr、L-val base、APM mode/status
   - 需要正确处理 OSM 的 mailbox/握手序列（`qcom,cc-*` 那组校准参数）
2. 或者**改用 `qcom-cpufreq-hw`**：如果 SDM660 的 APM 暴露了 sdm845 那样的
   `VOLTAGE_FLOOR/CEILING` 表，理论上可以复用驱动 + 加一个 sdm660 compatible
3. 电压：用我们已经解出来的开环表（§10）足够

### 11.4 工作量重估

| 方案 | 工作量 | 风险 |
|---|---|---|
| 复用 `qcom-cpufreq-hw` + sdm660 compatible | 几天（如果 APM 表格式兼容）| 中：寄存器布局未知，需要试 |
| 自己写 OSM 驱动 | 2–4 周 | 高：握手序列复杂，容易把 CPU 锁死 |
| 不碰 CPU 调频 | 0 | 保持现状（固定频率，热但稳）|

### 11.5 结论

- **数据侧已经完成**（频率/电压表 + DTS 片段 `patches/cpu-opp-tables.dtsi`）
- **驱动侧是真正的门槛**，而且比之前估计的"纯 DT 收益立现"要重得多
- 建议：**先做前摄和 modem 这些有现成补丁的**，CPU 调频放到后面当独立项目

### 10.7 自查：数值已用独立实现复核（2026-10-29）

用另一段代码（`tools/verify_cpr.py` / `verify_cpr_gold.py`）把 DTB 的原始字节
手工解码了一遍，和上面的表格**逐项吻合**：

```
银簇 apc0_pwrcl_corner
freq  : 300 / 633.6 / 902.4 / 1113.6 / 1401.6 / 1536 / 1747.2 / 1843.2 MHz
floor : 588 / 588 / 596 / 652 / 712 / 744 / 784 / 844 mV
ceil  : 724 / 724 / 724 / 788 / 868 / 1068 / 1068 / 1068 mV

金簇 apc1_perfcl_corner
freq  : 300 / 1113.6 / 1401.6 / 1747.2 / 1958.4 / 2150.4 / 2208 MHz
floor : 588 / 596 / 652 / 712 / 744 / 784 / 844 mV
ceil  : 724 / 724 / 788 / 868 / 988 / 988 / 1068 mV
```

### 10.8 一个容易踩的坑：金簇有三个速度档

`qcom,corner-frequencies` 金簇有 16 个 u32，实际是：

| 档 | 最高频 |
|---|---|
| bin0 | **2457.6 MHz** |
| bin1 | **2208.0 MHz** |
| bin2 | （截断，只有 2 项）|

**本机该用哪个？** 官方规格写的是"最高主频 2.2GHz"
（[IT之家](https://www.ithome.com/0/376/666.htm)），
⇒ **bin1（2208 MHz）才是这颗 SKU 的**，2457.6 是更高分档的 SKU。

`patches/cpu-opp-tables.dtsi` 里用的就是 2208 —— 这是对的。
