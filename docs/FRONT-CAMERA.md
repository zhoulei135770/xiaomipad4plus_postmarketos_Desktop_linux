# 前摄 S5K5E8 资料（2026-10-25 更新）

## 0. 结论

- **魔趣上确认可用**：camera device 1 = 前摄（s5k5e8），`s5k5e8 probe succeeded`，
  会话打开后走 **CSID2 + ISPIF + VFE1（PIX0 接口）**，dmesg 有
  `msm_ispif_read_irq_status: VFE1 pix0 overflow.`（说明帧真的在流，只是被窗口/带宽限制溢出）。
- **之前笔记里「前摄 = csiphy1 / MCLK1 GPIO34 / RESET GPIO77」是错的**，
  那是 MIUI DT 的 `camera@1`（另一路，机身上没装）。真正的前摄是 **`camera@2`**。
- mainline 7.0.14 **没有 s5k5e8 驱动**（只有 s5k3m5/hi846；`s5k5baf` 是另一个老芯片，不能用）。
- 前摄同样**必须经过 ISPIF**，所以它的出图排在 ISPIF 修复之后。

## 1. 正确的硬件参数（来自 MIUI `camera@2` 节点）

> **2026-10-28 用运行中的 MoKee Android 11 `/sys/firmware/fdt` 复核过一遍**，以 DT 为准，
> 与下表有两处需要修正（见文末"复核修正"）。

| 项目 | 值 |
|---|---|
| CSIPHY / CSID | **csiphy2 / csid2** |
| VFE | **VFE1**（ISPIF → VFE1，PIX0 接口） |
| CCI | **master 1** → i2c-4 |
| I2C 地址 | 0x10（7 位，`front_probe` 里已按此挂） |
| MCLK | **GPIO33**（CAMIF_MCLK2），24 MHz，对应 `CAMSS_MCLK2_CLK` |
| RESET | **GPIO52**（`CAM_RESET2`，低有效） |
| VANA 2.8V 使能 | **TLMM GPIO49**（`CAM_VANA`，与后摄的 GPIO51 不同） |
| VDIG 1.2V 使能 | **PM660L GPIO3**（后摄是 PM660L GPIO4） |
| VIO 1.8V | `vreg_l11a_1p8`（与后摄共用） |
| sensor-position | 1（前置），mount-angle 270 |

MIUI 原始条目：

```
qcom,csiphy-sd-index = <2>;  qcom,csid-sd-index = <2>;
qcom,cci-master = <1>;
gpios = <&tlmm 33 0>, <&tlmm 52 0>, <&tlmm 49 0>, <&pm660l_gpios 3 0>;
gpio-req-tbl-label = "CAMIF_MCLK2", "CAM_RESET2", "CAM_VANA", "CAM_VDIG";
qcom,gpio-reset = <1>;  qcom,gpio-vana = <2>;  qcom,gpio-vdig = <3>;
clocks/<... 0x1d(cam_src_clk) 0x83(cam_clk)>, clock-rates = <24000000>;
```

## 2. 魔趣侧的证据

```
[   7.587291] Eeprom userspace probe for qtech_s5k5e8
[   7.602361] s5k5e8 probe succeeded
...
[ 832.692611] msm_csid_init: CSID_VERSION = 0x30050000
[ 832.693581] msm_csid_irq CSID2_IRQ_STATUS_ADDR = 0x800     ← 前摄用 CSID2
[ 860.418191] msm_ispif_read_irq_status: VFE1 pix0 overflow. ← 走 ISPIF → VFE1
[ 860.530340] slot0: sensor name: ov13855_f13v10l sensor id55381 already probed
[ 860.531733] slot2: sensor name: s5k5e8 sensor id24192 already probed
```

`slot2` 也印证了：前摄在 sensor slot 2（csiphy2/csid2）。

## 3. 要写驱动还缺什么

已有：

- 硬件参数（上表）——DT 可直接写
- 供电/时钟拓扑（VANA GPIO49、VDIG PM660L GPIO3、MCLK2=GPIO33、RESET GPIO52）
- 从厂商 `libmmcamera_s5k5e8.so` 提取的 **5 个模式表**（mode_a..e，各 60 条，16 位寄存器）
  → `camdump/s5k5e8_tables.json`（PC 侧：问 VM 要 `~/camdump/`）

还缺：

1. **完整 init 表**（PLL/模拟/全局），当前只抓到 5 个 mode 表；
   需要改进 .so 扫描脚本，把长度不固定的 init 表也抠出来
2. **CHIP_ID 寄存器与期望值**（S5K5E8 一般是 `0x0000 = 0x05E8` 之类，需实测确认）
3. 流控寄存器（Samsung 系一般 `0x0100 = 1/0` 开/停流）
4. 驱动本体（`drivers/media/i2c/s5k5e8.c`）+ DT 节点（csiphy2/csid2）

## 4. 顺序

1. 先修 ISPIF（后摄出图）—— 前后摄共用，是硬前提
2. 再写 s5k5e8 驱动（可复用 ov13855 驱动的骨架）
3. DT 里把 `front_probe`（现在用 ov13855 占位、只上电）替换成真正的 s5k5e8 节点，
   接到 csiphy2/csid2，并修正 VANA/VDIG 使能脚（GPIO49 / PM660L GPIO3）

## 5. 注意

- 前摄 5MP（2592x1944 左右），一般是 **2 lane**，管线带宽比后摄小得多，配置更容易。
- 后摄 DT 里现在的 `front_probe` 用的是后摄的供电 enable（GPIO51/PM660L GPIO4），
  **对前摄是错的**——真正写驱动时必须换成 GPIO49 / PM660L GPIO3，
  否则前摄上电时序不对（这也是之前 i2c-4 上扫不到任何设备的原因之一）。


---

## 1b. 2026-10-28 Android 11 复核（以 DT 为准，修正两处）

从运行中的 MoKee 直接 `adb pull /sys/firmware/fdt` 后解析 `/soc/qcom,cci@ca0c000/qcom,camera@2`：

| 属性 | 值 |
|---|---|
| `cell-index` / `reg` | 2 |
| `qcom,csiphy-sd-index` / `qcom,csid-sd-index` | 2 / 2 |
| `qcom,cci-master` | 1 |
| `clocks` | `cam_src_clk = 0x1d`, `cam_clk = 0x83`，`clock-rates = 24000000` |
| `gpios` | tlmm **33**(CAMIF_MCLK2), tlmm **52**(CAM_RESET2, 低有效), tlmm **49**(CAM_VANA), **pm660l_gpios 3**(CAM_VDIG) |
| `cam_vio-supply` | `pm660_l11` 1.8 V（与后摄/触摸共用） |
| `cam_vana-supply` | `cam_avdd_front_gpio_regulator`：regulator-fixed，**2.8 V 标称**，`enable-active-high`，`gpio = <&tlmm 49>`，`vin-supply = pm660l_bob` |
| `cam_vdig-supply` | **`pm660_l13`（1.8 V）** ← 修正点 ① |
| `qcom,cam-vreg-*` | min/max = {1.8 V, 0, 1.8 V}（顺序 vio/vana/vdig），op-mode = {105 mA, 0, 105 mA} |

boot dmesg 佐证（本次开机）：

```
cam_avdd_front_gpio_regulator: supplied by pm660l_bob
cam_rear_dvdd_gpio_regulator: supplied by pm660_l13
[eeprom] Eeprom userspace probe for qtech_s5k5e8   → 7.39 s "s5k5e8 probe succeeded"
```

### 两处修正

1. **VDIG 不是"1.2 V / 仅 PM660L GPIO3"**：DT 里 `cam_vdig-supply = pm660_l13`（1.8 V）。
   1.2 V 的那个是**后摄**的 `cam_rear_dvdd_gpio_regulator`（同样由 `l13` 供电、GPIO 开关）。
   前摄的 PM660L GPIO3 仍出现在 `gpio-req-tbl` 里（标 `CAM_VDIG`，`qcom,gpio-vdig = <3>`），
   所以厂商驱动**会同时拉这个脚**，但它不是一条独立的 1.2 V 轨。
2. **`l13` 在 Android 里相机不开时是关的**（本次实测 `state=disabled, users=0`），
   而 pmOS 的 `sdm660-xiaomi-clover-common.dtsi` 把 `vreg_l13a_1p8` 标成 `regulator-always-on`
   并注释"给 LPDDR4 供电"——**这个认知可能错了**，`l13` 是相机 DVDD 的源。回 pmOS 后要核对，
   否则前摄上电时 `l13` 可能被人为常开而掩盖真实时序（一般不致命，但注释是错的）。

### pmOS 侧现状（对照）

* 现役 DTB（`artifacts/kernel/built/*.dtb`，含 working-62664/good-62664/patched-62664）
  **一个 camera 子节点都没有**，只有 `cci@ca0c000` + `i2c-bus@0/1`。
  ⇒ 后摄/前摄都是**运行时 `new_device` + 占位驱动**在跑，不是 DT 描述。
* 所以上面这张表可以直接翻译成一个正式的 `qcom,camera@2` DT 节点 + 两个
  `regulator-fixed`（`cam_avdd_front`、`cam_avdd`），替换掉现在的占位做法。

### 1c. 运行态实测（2026-10-28 21:15，前摄正在出流时抓的）

`dumpsys media.camera`：`Active Camera Client: Camera ID 1, org.mokee.snap` ⇒ 确实开的是前摄。
dmesg：`21:15:17 msm_csid_init CSID_VERSION=0x30050000` → `CSID2_IRQ_STATUS_ADDR = 0x800`。

**关键结论：整条链路在跑，但 PMIC regulator 一个都没变。**

```
pm660_l11   enabled  1.800 V users=2      ← 前后摄共用 VIO，一直开
pm660_l13   disabled           users=0    ← 出流时依然是关的（DT 里的 cam_vdig-supply 是幽灵引用）
pm660l_bob  disabled  / bob_pin1 enabled 3.600 V users=1
cam_avdd_front_gpio_regulator  2.800 V users=0   ← 没被 regulator API enable
cam_avdd / cam_vaf / cam_rear_dvdd              users=0
```

⇒ 前摄的 VANA/VDIG 在 Android 里是**纯 GPIO 开关**（`tlmm 49` 与 `pm660l_gpios 3`），
不走 regulator 框架。pmOS 侧应当用两个 `regulator-fixed { gpio = <...>; enable-active-high; }`
来建模，而不是去动 PMIC 电压。

**前摄时序参数（厂商 HAL 亲口打印）**：

```
<SENSOR> sensor info: name: s5k5e8, res: 0, max_fps: 30.000000,
         w: 2592, h: 1944, op pix clk: 167200000,
         FLL: 1968, LLPCK: 2856, mode: 1, PDAF support: 0
<ISP>    Stream type 1  Resolution: 1440x1080   ← 预览
<ISP>    Stream type 11 Resolution: 640x480     ← 缩略图
```

这组 `167.2 MHz / FLL 1968 / LLPCK 2856` 是写 s5k5e8 驱动时校核 PLL 的硬指标，
可以和 `libmmcamera_s5k5e8.so` 里抠出来的 mode 表逐项对齐。
