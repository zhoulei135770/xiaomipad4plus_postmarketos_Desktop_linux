# 前摄 S5K5E8 诊断（2026-10-29 凌晨）

> 目标：让 Mi Pad 4 Plus 的前摄在 pmOS 下工作。

---

## 1. 现状

```
DT:   /soc@0/cci@ca0c000/i2c-bus@1/camera@10
      compatible = "samsung,s5k5e8", reg = <0x10>, status = "okay"
驱动: /lib/modules/7.0.14-sdm660/kernel/drivers/media/i2c/s5k5e8.ko
绑定: ✗ 失败
```

内核日志（每次开机都一样）：

```
s5k5e8 4-0010: S5K5E8 probe: chip id = 0x0 (read ret -6)
s5k5e8 4-0010: Error reading reg 0x0000: -6
s5k5e8 4-0010: S5K5E8 not responding (err -6), failing probe
```

`-6 = -ENXIO` → **i2c 无应答**（传感器没 ACK）。

---

## 2. 已排除

| 假设 | 实验 | 结果 |
|---|---|---|
| 复位极性/时序 | `reset_mode=0/1/2` × `delay_ms=20/100/300` 逐一 insmod | 全部 `-6`，无变化 |
| 供电缺失 | 读 `/sys/class/regulator/*` | `cam_avdd_front_2v8` enabled 2.8V、`cam_front_dvdd_1v8` enabled 1.8V |
| 缺 supplier | `waiting_for_supplier = 0`，所有 supplier 已注册 | 不是延迟探测 |
| 驱动没加载 | `modinfo` + kallsyms 有 81 个符号 | 驱动正常加载 |

额外的次要 bug：probe 失败清理时触发内核 WARNING：

```
WARNING: drivers/regulator/core.c:2657 at regulator_bulk_free+0x9c/0xc0
  devm_regulator_bulk_release -> i2c_device_probe -> ...
```

（`regulator_bulk_free` 在已经 disable 的状态下再释放，属于驱动自身的清理缺陷，不影响主故障。）

---

## 3. DT 与厂商的差异（可疑点）

pmOS 的 `0007-...-camera.patch` 里前摄节点：

```dts
vanA-supply  = <&cam_avdd_2v8>;        /* 后摄的 2.8V */
vdig-supply  = <&cam_rear_dvdd_1v2>;   /* 后摄的 1.2V */
vddio-supply = <&vreg_l11a_1p8>;
```

补丁注释写的是“vendor 从不使能 cam_avdd_front”。

但**厂商 DT（MIUI dump）明确是**：

```
cam_vio-supply  = <0x18b>   (l11 1.8V)
cam_vana-supply = <0x1da>   (fixed regulator, 2.8V)
cam_vdig-supply = <0x1db>   (fixed regulator, 1.2V/1.8V)
gpios: CAMIF_MCLK2(GPIO33)  CAM_RESET2(GPIO52)  CAM_VANA(GPIO49)  CAM_VDIG(pmic gpio3)
```

也就是说前摄有自己的 VANA/VDIG 开关（GPIO49 + PMIC GPIO3），
pmOS 却把前摄的 VANA 接到了**后摄的** `cam_avdd_2v8`、VDIG 接到**后摄的** `cam_rear_dvdd_1v2`。

这两个 regulator 当前状态都是 **disabled**：

```
cam_avdd_2v8:       disabled  2800000uV
cam_rear_dvdd_1v2:  disabled  1200000uV
cam_avdd_front_2v8: enabled   2800000uV   ← 真正该用的
cam_front_dvdd_1v8: enabled   1800000uV   ← 真正该用的
```

虽然驱动 probe 时会 `regulator_bulk_enable`，但把前摄接到后摄的开关上，
物理上很可能根本没有连接到前摄的供电脚 → 传感器不上电 → i2c 无 ACK。

**这是当前最可疑的一条。**

---

## 4. 下一步实验（按性价比）

1. **改 DT 供电**（最可能一次解决）：

   ```dts
   vana-supply  = <&cam_avdd_front_2v8>;
   vdig-supply  = <&cam_front_dvdd_1v8>;
   vddio-supply = <&vreg_l11a_1p8>;
   ```
   改 `0007-...-camera.patch` 后在 VM 上 `pmbootstrap build linux-...`（或本地重编 dtb）
   然后刷 boot 分区，观察 `dmesg | grep s5k5e8`。

2. **i2c 地址**：S5K5E8 的 7bit 地址可能是 `0x20` 而不是 `0x10`。
   改 DT 的 `reg = <0x20>` 试一次。
   （运行时 `new_device` 测不了：动态实例化没有 of_node，拿不到供电，直接 -2。）

3. **MCLK2 是否真的在跑**：需要示波器量 GPIO33 上的 24 MHz。
   软件侧可以先看 `clk_summary`（**注意：这台机器的 4.4 内核读 clk_summary 会死锁，
   在 pmOS 7.0.14 上没试过，谨慎**）。

---

## 5. 参考：设备树里的前摄节点（pmOS 侧）

```
/soc@0/cci@ca0c000/i2c-bus@1/camera@10
  compatible     samsung,s5k5e8
  reg            0x10
  status         okay
  reset-gpios    phandle 0x29 pin 52 flags 1 (ACTIVE_LOW)
  clocks         phandle 0x2 id 0x52 (CAMSS_MCLK2)
  clock-names    xvclk
  vana-supply    0x93      ← 待确认（应为 cam_avdd_front_2v8）
  vddio-supply   0x6e      (l11 1.8V ✓)
```

---

## 6. 记录时间

2026-10-29 00:35，设备 v10 指纹模块在跑，电量约 50%，充电中。

---

## 7. ~~已定位的具体 BUG：前摄接在后摄的供电轨上~~ ⚠️ 已过时 —— 见 §8 的更正

pmaports 补丁 `0007-...-camera.patch` 的原文（第 156–158 行）：

```dts
+		vana-supply = <&cam_avdd_2v8>;        /* ← 后摄的 2.8V */
+		vdig-supply = <&cam_rear_dvdd_1v2>;   /* ← 后摄的 1.2V */
+		vddio-supply = <&vreg_l11a_1p8>;
```

而后摄（ov13855）自己用的是同一对：`avdd = cam_avdd_2v8`、`dvdd = cam_rear_dvdd_1v2`。

**厂商 DT 明确显示前后摄是两套独立的开关**：

| 摄像头 | cam_vana | cam_vdig |
|---|---|---|
| camera@1（后）| 0x1cc | 0x1cd |
| camera@2（前）| **0x1d6** | **0x1d7** |

在 pmOS DTS 里对应的就是已经存在的两个 fixed regulator：

```
cam_avdd_front_2v8    enabled  2800000uV
cam_front_dvdd_1v8    enabled  1800000uV
```

**前摄被接到后摄的开关上 → 前摄的 VANA/VDIG 实际没有供电 → i2c 无 ACK（-6）。**

### 修复（一条命令，已写成脚本）

```sh
sh patches/fix-front-camera-rails.sh
# 把两行改成：
#   vana-supply = <&cam_avdd_front_2v8>;
#   vdig-supply = <&cam_front_dvdd_1v8>;
# 然后重编内核包并刷 boot
```

### 顺带说明

即使供电修好、i2c 能通，前摄要出图还需要：
1. **media graph**：目前前摄节点是故意**不接进 media graph** 的
   （补丁注释：“Kept out of the media graph so camss's .complete callback still
   fires for the rear camera”）。要让前摄出流，得把它接进 `csiphy2/csid2` 的 port 图，
   同时保证 camss 的 `.complete` 仍然满足。
2. **sensor mode 表**：驱动里需要有 2592x1944 的 mode（FRONT-CAMERA.md §1c 已有实测参数
   `167.2MHz / FLL 1968 / LLPCK 2856`）。

所以前摄是“三步走”：**供电 → i2c 通 → 接进 media graph**。第一步今天已经定位到具体行。

---

## 8. ⚠️ 重要更正（2026-10-29 01:40）：供电轨**早就修好了**

夜里我一度认为"前摄接在后摄供电轨上"是 bug，**这个结论是错的**。

### 8.1 证据

pmaports 里**已经存在** `0039-arm64-dts-clover-fix-frontcam-supplies.patch`，
并且它在 `APKBUILD` 的 source 列表里（第 69 行）。补丁原文：

```
The S5K5E8 was described with the rear camera's regulators: VANA was the
gpio51 load switch and VDIG the rear 1.2 V DVDD.  The vendor camera@2 node
uses cam_avdd_front (gpio49, 2.8 V) for VANA and pm660_l13 (1.8 V, gated by
the pm660l gpio3 load switch) for VDIG, with cam_vio from pm660_l11.
Feeding it the rear rails leaves it unpowered, so it never acknowledged on
CCI master 1.
```

设备上的实时证据（`/sys/bus/i2c/devices/4-0010/`）：

```
supplier:platform:cam-avdd-front-2v8   -> ...   2.8V enabled
supplier:platform:cam-front-dvdd-1v8   -> ...   1.8V enabled
```

⇒ **前摄的 VANA/VDIG 已经接在自己的开关上，而且都是 enabled。**

### 8.2 那为什么还是 -6？

排除掉供电后，剩下三个嫌疑（按可能性）：

1. **MCLK2 没跑**（GPIO33 的 cam_mclk 功能 / `CAMSS_MCLK2_CLK` 没真正输出 24 MHz）
   —— 传感器没有参考时钟就不会应答 i2c
2. **i2c 地址不是 0x10**（S5K5E8 可能是 0x20）
3. **上电顺序**：厂商可能是 VANA → VDIG → VIO → 释放复位，驱动是同时使能

### 8.3 我写的修复脚本

`patches/fix-front-camera-rails.sh` **不需要执行了**（问题已修）。
保留它是作为记录 —— 但它改的东西 0039 已经做了。

### 8.4 下一步（明天，需要设备）

```sh
# 1) 看 MCLK2 是否在跑（注意：4.4 内核读 clk_summary 会死锁，pmOS 上没试过，谨慎）
sudo cat /sys/kernel/debug/clk/clk_summary | grep -i mclk2

# 2) 试另一个 i2c 地址（改 DT 的 reg = <0x20> 重编 dtb）

# 3) 用示波器量 GPIO33（最优，但需要硬件）
```

### 8.5 还有一个未确认的点：`power_on()` 到底跑没跑

驱动的 `power_on()` 里每一行都有 `dev_err`：

```
S5K5E8: enable supply %u (%s)
S5K5E8: supply %u -> %d
S5K5E8: setting MCLK to 24 MHz
S5K5E8: enabling MCLK
S5K5E8: MCLK -> %d rate=%lu
S5K5E8: reset released (logical=%d)
```

之前抓 dmesg 用的是 `grep s5k5e8 | tail -20`，**这些行可能在 tail 之外被截掉了**，
所以"power_on 没跑"这个判断**尚未确认**。

明天第一件事（10 秒）：

```sh
dmesg | grep -E 'S5K5E8: (enable supply|supply |setting MCLK|enabling MCLK|MCLK ->|reset released)'
```

- **有输出** ⇒ 供电和 MCLK 都正常执行了，问题在别处（地址/时序）
- **没输出** ⇒ `pm_runtime_resume_and_get()` 没触发 `runtime_resume`，
  或者跑的驱动版本比 pmaports 里的旧（缺这些打印）→ 那才是真 BUG

---

## 9. 2026-10-29 01:55 决定性证据：**i2c 总线上根本没有设备**

### 9.1 全总线扫描（i2cdetect，i2c-dev 可用）

```
bus 3（后摄，能工作）:  0x36 = UU（ov13855 已绑定）  0x50 = 有设备
bus 4（前摄）:          全部 --，包括 0x10，一个都没有
```

⇒ **不是地址问题**（0x10 不对的话至少别的地址可能应答，这里全空）。
⇒ **扫描方法有效**（bus 3 能看到设备）。

### 9.2 引脚和电源全部正常

```
gpio33 (MCLK2)  : in low func1 2mA no pull     ← 已切到 cam_mclk 功能
gpio49 (VANA)   : out high func0               ← 2.8V 开关已打开
gpio52 (RESET2) : out high func0               ← active-low，高 = 已释放
```

驱动日志（这次完整拿到）：

```
S5K5E8: enable supply 0 (vddio) → 0
S5K5E8: enable supply 1 (vana)  → 0
S5K5E8: enable supply 2 (vdig)  → 0
S5K5E8: setting MCLK to 24 MHz
S5K5E8: enabling MCLK
S5K5E8: MCLK -> 0 rate=24000000
S5K5E8: reset released (logical=0)
```

**供电、时钟、复位全部成功，传感器还是不应答。**

### 9.3 最可能的原因：**前摄被故意排除在 media graph 之外**

pmOS 补丁 0007 里的注释（原文）：

```
/* Front camera: Samsung S5K5E8 — I2C node only (no media-graph port).
 * ...
 * Kept out of the media graph so camss's .complete callback still fires for
 * the rear camera. */
```

后果：camss 只会为 media graph 里引用到的 csiphy/csid 上电。
前摄没有 port 链接 ⇒ **csiphy2 / csid2 / CCI master 1 可能根本没有被上电或使能**
⇒ 整条总线（bus 4）都不工作 ⇒ 任何地址都不会应答。

这与"bus 4 一个设备都没有"完全吻合，也解释了为什么把供电/时钟都修好也没用。

### 9.4 下一步（需要改 DT + 重编）

1. 给 `s5k5e8` 节点加 `port` / `endpoint`，链到 `csiphy2` 的 port
2. 同时保证 csi2 / csid2 的 port 配置正确
3. 处理 `camss .complete` 的问题（原来排除它的原因就是这个 —— 需要让两条链路都能完成）

**这是目前最可信的方向。** 不是电源，不是地址，是"整条 CSI/CCI 通路没被启用"。

### 9.5 DT 侧的最终确认

```
/proc/device-tree/soc@0/camss@ca00020/ports/  →  只有 port@0
```

**camss 只接了一个 port**（后摄那条），前摄完全没有 port 链接。

⇒ 假设成立：**csiphy2 / csid2 / CCI master 1 从未被启用过。**
这就解释了为什么总线上一个设备都没有 —— 那条总线根本没被上电。

### 9.6 修法（明天可做，需要重编内核）

在 `sdm660-xiaomi-clover.dtsi` 里：

```dts
&camss {
	ports {
		#address-cells = <1>;
		#size-cells = <0>;

		/* 现有 port@0（后摄，别动）*/

		port@2 {
			reg = <2>;
			csiphy2_ep: endpoint {
				clock-lanes = <7>;
				data-lanes = <0 1>;
				remote-endpoint = <&s5k5e8_ep>;
			};
		};
	};
};

&s5k5e8 {
	port {
		s5k5e8_ep: endpoint {
			clock-lanes = <0>;
			data-lanes = <1 2>;
			remote-endpoint = <&csiphy2_ep>;
		};
	};
};
```

并且 csid2 也要接上（`&csi2` / csid 的 port）。

⚠️ 原来是**故意**排除它的（为了让 camss 的 `.complete` 仍能为后摄触发），
所以接回去之后要确认后摄还能启动 —— 可能需要改成"两个 sensor 都 link 时才 complete"
或者用 `status = "okay"` 分别控制。

---

## 10. 🎯 真正的根因（2026-10-29 02:10）：**两个修好的补丁从来没被编进内核**

### 10.1 铁证

pmaports 目录里存在这两个补丁：

```
0032-arm64-dts-clover-i2c-gpio-front-camera.patch    ← bit-bang i2c，专门用来测前摄
0048-arm64-dts-clover-front-camera-endpoint.patch    ← 把前摄接进 camss（port@2 → csiphy2）
```

但是 **APKBUILD 的 source 列表里没有它们**：

```
$ grep -n '0032\|0048' APKBUILD
（无输出）
$ grep -c '\.patch' APKBUILD
84
```

⇒ **这两个补丁从未参与编译。**

设备上的实时证据完全吻合：

```
/proc/device-tree/soc@0/camss@ca00020/ports/   →  只有 port@0     （0048 没应用）
/proc/device-tree/ 下没有 i2c-gpio 节点                          （0032 没应用）
/sys/class/i2c-dev/ 只有 i2c-0..4（2 个 QUP + 2 个 CCI）          （没有 bit-bang 总线）
```

### 10.2 0048 干的事（和我之前想的一样，但早就写好了）

```dts
&camss {
	ports {
		port@2 {
			csiphy2_ep: endpoint {
				data-lanes = <0 1>;
				remote-endpoint = <&s5k5e8_ep>;
			};
		};
	};
};

&cci_i2c1 {
	camera@10 {
		assigned-clocks = <&mmcc 82>;
		assigned-clock-rates = <24000000>;
		port {
			s5k5e8_ep: endpoint {
				remote-endpoint = <&csiphy2_ep>;
				data-lanes = <1 2>;
				clock-lanes = <0>;
				link-frequencies = /bits/ 64 <540000000>;
			};
		};
	};
};
```

### 10.3 0032 干的事（正是现在需要的诊断工具）

```dts
i2c_gpio1: i2c-gpio-1 {
	compatible = "i2c-gpio";
	sda-gpios = <&tlmm 38 2>;     /* 前摄 CCI 的两根线 */
	scl-gpios = <&tlmm 39 2>;
	i2c-gpio,delay-us = <100>;
};
```

⇒ 有了它就能**绕开 CCI 控制器**，直接看传感器到底应不应答。

### 10.4 修复步骤（明天，约 40 分钟含编译）

```sh
# 1. 把两个补丁接进构建（脚本已写好）
sh patches/enable-frontcam-patches.sh

# 2. 编译内核包
pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660

# 3. 刷 boot 分区，重启

# 4. 关键验证（三选一，按信息量排序）
i2cdetect -l                        # 看有没有新的 i2c-gpio 总线
i2cdetect -y -r <新的总线号>         # 传感器应答吗？
dmesg | grep -i s5k5e8              # 驱动这次能读到 chip id 吗？
```

### 10.5 结果怎么解读

| 现象 | 结论 |
|---|---|
| bit-bang 总线上**能**扫到 0x10 | CCI 控制器的问题是主因，传感器是好的 → 修 CCI/时钟 |
| bit-bang 总线上**也扫不到** | 传感器没上电或已损坏 → 查 VANA/VDIG 实际电压、或模块排线 |
| 0048 生效后驱动能读到 chip id | 之前就是 camss 没给 CCI 上电，接上就好 |

### 10.6 风险评估

0048 把传感器接回 media graph 后，**后摄可能受影响**（当初排除它的原因就是这个）。
刷之前先确认能回滚：boot 分区有备份（见 RESTORE-GUIDE.md）。

### 10.7 顺手做的系统检查：所有"孤儿补丁"

pmaports 目录里 58 个补丁文件，APKBUILD 里 84 条 —— 差集就是没被编进去的：

```
0011/0012/0014/0016/0019/0021/0024/0028  media-camss-*  （调试用，8 个）
0031-arm64-dts-qcom-clover-enable-modem.patch
0032-arm64-dts-clover-i2c-gpio-front-camera.patch        ← 有用
0047-media-venus-sdm660-use-hfi-v4-pm.patch
0048-arm64-dts-clover-front-camera-endpoint.patch        ← 有用
0072/0073/0077  venus 系列
0076-iio-smgr-hall-effect.patch     （已被 0076-iio-smgr-hall.patch 取代）
```

判断：

| 补丁 | 结论 |
|---|---|
| **0032、0048** | ✅ **必须接回来**（前摄就靠它们）|
| 0012、0016（csiphy init/status dump）| 🟡 如果 0048 之后还是出不了流，接回来做诊断 |
| 0031（enable modem）| ❌ 冗余：设备上 modem 已经在跑（remoteproc0 running）|
| 0047/0072/0073/0077（venus）| ❌ 已被后续 0078–0051 系列取代 |
| 0076-hall-effect | ❌ 已改名成 0076-iio-smgr-hall.patch（在列表里）|

---

## 11. 驱动就绪度检查（2026-10-29 03:05）

结论：**驱动本身是完整的，不缺数据，只缺 media graph。**

| 检查项 | 结果 |
|---|---|
| 模式表 | ✅ 三组真实分辨率：2592×1944 / 1296×972 / 1304×980 |
| 初始化序列 | ✅ `s5k5e8_a_regs` / `b_regs` / `c_regs` 各 **60+ 条真实寄存器写** |
| PLL 配置 | ✅ 含 `0x0305–0x0309`（MIPI PLL）等关键寄存器 |
| 供电/复位/时钟 | ✅ 三路 regulator、reset gpio、MCLK 24 MHz 全正常 |
| 上电时序 | ✅ `power_on()` 执行成功（日志已确认）|
| **media graph** | ❌ **缺**（补丁 0048 没进构建）|
| **CCI 总线供电** | ❌ **缺**（同上，camss 从未启用 csiphy2/csid2）|

初始化序列示例（前 8 条）：

```c
{ CCI_REG16(0x0136), 0x18 },   /* PLL 分频 */
{ CCI_REG16(0x0137), 0x00 },
{ CCI_REG16(0x0305), 0x06 },   /* MIPI PLL 配置 */
{ CCI_REG16(0x0306), 0x18 },
{ CCI_REG16(0x0307), 0xa8 },
{ CCI_REG16(0x0308), 0x34 },
{ CCI_REG16(0x0309), 0x42 },
{ CCI_REG16(0x3c1f), 0x00 },
```

⇒ **不需要再从 `libmmcamera_s5k5e8.so` 里挖模式表了** —— 已经在驱动里。

所以前摄的修复路径非常明确：把 0032/0048 接进构建，重编，刷机。

---

## 12. ✅ 2026-10-29 03:30：补丁已经**实际接进构建并验证结构**

### 12.1 做了什么

1. 在**完整补丁系列**上验证：
   - `0048` ✅ 干净应用（`port@2` 出现）
   - `0032` ❌ **应用失败**（hunk 1 @183 冲突，上下文早变了）
2. 因此**重做了 0032**：改成"追加到文件末尾"的形式（和 0048 一样的风格），
   生成为 `patches/0053-frontcam-i2c-gpio.patch`，实测干净应用
3. 用 `patches/enable-frontcam-patches.sh` 同时改 **source 列表**和 **sha512sums**
4. 结构校验：

```
source 条目   42 → 44   （新增 0048、0053）
校验条目      44 → 46
每条 source 都有对应校验：missing = 0
```

### 12.2 踩到的坑（记下来免得下次再犯）

第一版脚本用 `grep '\.patch$'` 找 source 列表末尾 —— 结果**匹配到了校验行**
（校验行也是 `<hash>  xxx.patch` 结尾），把条目插进了 sha512sums 块里，
APKBUILD 直接被写坏。

正确做法：source 条目是 **tab 缩进**的，要用
`grep '^	[0-9][0-9][0-9][0-9]-.*\.patch$'`。

（已从 `APKBUILD.bak.*` 恢复，然后重跑修正版。）

### 12.3 现在的状态

**VM 上的 APKBUILD 已经改好了**，明天不用再跑 enable 脚本，直接编译：

```sh
pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660
```

回滚：`cp APKBUILD.bak.<时间戳> APKBUILD`（备份在同一个目录）。

### 12.4 编译后怎么验

```sh
i2cdetect -l                       # 应多出一条 i2c-gpio 总线
i2cdetect -y -r <那条总线>          # 前摄在 0x10 应答吗
dmesg | grep -i s5k5e8             # 驱动能读到 chip id 吗
```

### 12.5 顺带查清：`0035` 的"失败"是**误报**

在验证脚本里 `0035-fpc1020-driver.patch` 也报了失败，一度以为构建会炸。查清了：

```
$T/drivers/input/misc/fpc1020.c      存在（34954 字节，Oct 28 16:53）
$T/drivers/input/misc/Makefile:100   obj-m += fpc1020.o
```

即**构建树不是干净的** —— 之前为了编指纹模块，手动放过 `fpc1020.c` 和 Makefile 条目。
`0035` 是"新建文件"补丁，文件已存在自然失败。

**pmbootstrap 真正的构建会重新解压 tarball**，那里是干净的，`0035` 能正常应用。
所以这是误报，不影响明天的构建。

（结论：以后在这棵 `~/kbuild/...` 树上做"补丁能否应用"的验证时，要先记住它已被污染，
只有 dts 那几个文件是干净的。）

### 12.6 实跑了一次完整编译（2026-10-29 03:50）

在 VM 上 `pmbootstrap build --arch aarch64 --force linux-postmarketos-qcom-sdm660`：

**✅ 补丁全部正常应用**（构建日志原文）：

```
>>> linux-postmarketos-qcom-sdm660: 0048-arm64-dts-clover-front-camera-endpoint.patch
patching file arch/arm64/boot/dts/qcom/sdm660-xiaomi-clover-plus.dts
>>> linux-postmarketos-qcom-sdm660: 0053-frontcam-i2c-gpio.patch
patching file arch/arm64/boot/dts/qcom/sdm660-xiaomi-clover-plus.dts
```

**❌ 但构建在最后一步失败**：

```
LD      .tmp_vmlinux2
Bus error (core dumped)
make[2]: *** [scripts/Makefile.vmlinux:72: vmlinux.unstripped] Error 135
```

**原因：VM 磁盘 100% 满（0 字节可用）**

```
/dev/mapper/ubuntu--vg-ubuntu--lv   77G   74G   0   100% /
```

占用分布：

| 目录 | 大小 |
|---|---|
| `~/.local/var/pmbootstrap/chroot_native` | **14 G** |
| `chroot_rootfs_xiaomi-clover` | 7.3 G |
| `cache_ccache_x86_64` | 1.3 G |
| `cache_apk_*` | 1.2 G |

⇒ **不是补丁的问题，是磁盘满了**。明天编译前必须先腾空间：

```sh
pmbootstrap zap -n        # 删掉 native chroot（14 G），下次构建会自动重建
# 或者
rm -rf ~/.local/var/pmbootstrap/chroot_native
pmbootstrap zap -c        # 清 ccache（1.3 G）
```

腾出 15 G 以上再编。**补丁这一侧已经证明是可用的。**

### 12.7 刷完机后：一条命令出结论

```sh
python tools/pad_run.py scripts/frontcam_verify.sh --sudo
```

脚本会依次检查并**直接给结论**：

1. 有没有 `i2c-gpio` 总线（补丁 0053 是否生效）
2. `camss/ports/` 里有没有 `port@2`（补丁 0048 是否生效）
3. 在 bit-bang 总线上扫设备（传感器是否活着）
4. `dmesg` 里驱动有没有 probe 成功
5. 最后按结果给出下一步

已在**修复前的设备**上验证过脚本逻辑，输出（节选）：

```
== 1. i2c 总线 ==
   i2c-0..4 （只有 QUP 和 CCI）
   → 没有 i2c-gpio 总线  ❌ 补丁 0053 没生效

== 2. camss ports ==
   port@0
   → 没有 port@2  ❌ 补丁 0048 没生效

== 4. 驱动读 chip id ==
   s5k5e8 4-0010: S5K5E8 not responding (err -6), failing probe

==============================================
 结论
==============================================
 补丁没生效 —— 先确认刷的是新内核：
   uname -v    （应包含 -r254 或更新）
```

**三种可能结果对应的判断**：

| 现象 | 结论 | 下一步 |
|---|---|---|
| 有 bit-bang 总线 + 能扫到设备 | 传感器是好的，问题在 CCI/csiphy2 | 继续查 camss |
| 有 bit-bang 总线 + 扫不到 | 传感器没电/坏/排线松 | 量 VANA 2.8V、VDIG 1.8V、MCLK2 24MHz |
| 没有 bit-bang 总线 | 刷的不是新内核 | 检查 `uname -v` |

---

## 13. 🚀 2026-10-29 08:10：DTB 直接改 boot.img（**不用重编内核**）

这一节的发现改变了工作方式：以后改设备树**不需要内核源码、不需要 pmaports、不需要刷 fastboot**。

### 13.1 启动路径搞清楚了

| 调查 | 结果 |
|---|---|
| `/boot` 是独立分区吗 | ❌ **不是**，只是根分区上的普通目录 |
| 那 84 个补丁的 DTB 在哪 | 在 **`/dev/mmcblk1p12`（64 MB boot 分区）里的 `boot.img`** 内 |
| 怎么确认的 | `boot.img` 与分区前 25 829 376 字节 **md5 完全相同** |
| extlinux 呢 | `/boot/extlinux/extlinux.conf` 只是产物，aboot 不读它 |

boot.img 结构（Android boot image）：

```
ANDROID! 头
kernel_size = 13031313       ← 内核 gzip + 末尾追加的 DTB
kernel 载荷: 1f 8b 08 ...    ← gzip
   DTB 在载荷偏移 0xc5d571，66080 字节
ramdisk 12790656
```

### 13.2 工作流（已验证可用）

```sh
# 1) 从分区取出当前镜像（含所有已应用的 DT 补丁）
dd if=/dev/mmcblk1p12 of=/tmp/base.img bs=1M count=25
head -c <原boot.img大小> /tmp/base.img > x && mv x /tmp/base.img

# 2) 抠出 DTB、反编译
python3 取出 dtb → cur.dtb
dtc -I dtb -O dts -o cur.dts cur.dtb

# 3) 改 DTS（加节点/改属性）
#    注意：反编译后**标签全丢了**，只能用 phandle 数值互相引用
#    当前最大 phandle 是 0xb6，新节点用 0xf0 以上

# 4) 编译回去
dtc -I dts -O dtb -o new.dtb new.dts

# 5) 换进 boot.img（保留原内核和 ramdisk）
python3 tools/boot_swap_dtb.py base.img new.dtb out.img

# 6) 写回分区 + 重启
dd if=out.img of=/dev/mmcblk1p12 bs=1M conv=fsync
reboot
```

全程**在平板上就能做**（平板自带 `dtc` 和 `python3`）。

### 13.3 已经验证成功的改动

**加了 `camss/ports/port@2`**（等价于补丁 0048）：

```
$ ls /proc/device-tree/soc@0/camss@ca00020/ports/
port@0  port@2        ← 重启后确实在
```

即"前摄接入 media graph"这一项**真的生效了**。

### 13.4 但 i2c 仍然不通 —— 证据链

```
CCI master 0 (i2c-3): 0x36 = UU（后摄已绑定）  + 0x50      ← 控制器正常
CCI master 1 (i2c-4): 一个设备都没有                        ← 前摄无应答
```

驱动 probe 时：

```
S5K5E8: enable supply 0 (vddio) → 0
S5K5E8: enable supply 1 (vana)  → 0
S5K5E8: enable supply 2 (vdig)  → 0
S5K5E8: setting MCLK to 24 MHz → MCLK -> 0 rate=24000000
S5K5E8: reset released (logical=0)
Error reading reg 0x0000: -6        ← i2c 无应答
```

**供电、时钟、复位全部成功，CCI 控制器本身也正常（master 0 能用），
但前摄在 master 1 上任何地址都不应答。**

### 13.5 试过的 bit-bang 方案（无效，已撤）

在 DTS 里加 `i2c-gpio`（GPIO38/39）想绕开 CCI：

```
i2c-0  i2c-gpio-1  ✅ 总线创建成功
```

但：

```
gpio38: ... function cci_i2c     ← mux 仍是 CCI 功能，没切到 GPIO
gpio39: ... function cci_i2c
```

`i2c-gpio` 认领了引脚但 **mux 没变**（CCI 驱动持有 pinctrl），
所以这条总线扫出来永远全空，结果不可信。**已把设备恢复到只加 port@2 的版本。**

### 13.6 结论

前摄的问题**不在设备树**：DT 改动已生效（port@2 在运行中的 DT 里）。
剩下的可能：

1. **前摄模组没装 / 坏了 / 排线松**（最可能）
2. 传感器 i2c 地址不是 0x10
3. 前摄实际接的不是 GPIO38/39（与厂商 DT 不符的硬件变体）

要再往前走需要**硬件测量**：量 VANA(2.8V)、VDIG(1.8V)、MCLK2(24MHz 方波)、
以及 i2c 线上有没有波形。这需要万用表/示波器。

### 13.7 副作用提醒

加 `i2c-gpio` 那版会把 CCI 总线号从 `i2c-3/4` 挤到 `i2c-4/5`，
影响按总线号写死的脚本。**现在已恢复成 i2c-3/4。**

---

## 14. 2026-10-29 08:20：硬件确认是好的，问题锁定在**驱动没申请 pinctrl**

### 14.1 前提变了

你说**前摄在魔趣下能正常驱动** —— 那硬件（模组、排线）没问题，
问题一定在软件侧。这条排除掉了之前"模组坏了"的猜测。

### 14.2 三份 DT 的前摄节点完全一致

对比 `artifacts/rom/miui-dtb-0.dtb`（MIUI）、`artifacts/mokee-20261028/fdt.dtb`（魔趣）：

| 项 | 厂商 / 魔趣 | pmOS | 结论 |
|---|---|---|---|
| cci-master | 1 | 1 | ✓ |
| csiphy / csid | 2 / 2 | 2 / 2 | ✓ |
| MCLK2 | gpio33 | gpio33 | ✓ |
| RESET2 | gpio52 | gpio52 | ✓ |
| VANA | gpio49 使能的 2.8V | 同 | ✓ |
| VDIG | pm660_l13 1.8V | 同 | ✓ |
| VIO | pm660_l11 1.8V | 同 | ✓ |

⇒ **DT 参数没有一处错**。（魔趣和厂商的节点连 gpio 编号都一样。）

### 14.3 真正的差异：驱动没申请 pinctrl

```
pin 32 (GPIO_32): device 3-0036     function cam_mclk   ← 后摄驱动认领了
pin 33 (GPIO_33): UNCLAIMED                             ← 前摄驱动没认领
```

后摄 `ov13855` 驱动会 `pinctrl_select_state("default")`，
前摄 `s5k5e8` 驱动**完全不申请 pinctrl**（日志里连 "Error applying setting" 都没有，
说明它压根没调用）。

于是 gpio33 的复用只能靠 bootloader 遗留状态 —— 不可靠，
MCLK2 可能没真正输出到传感器 → 传感器拿不到参考时钟 → **i2c 不应答**。

### 14.4 试过的"绕过驱动"办法（失败，已回退）

想把 `cam-mclk2-default` 组挂到 CCI 节点的 pinctrl-0 上，让 CCI 驱动顺带复用：

```
cci pinctrl-0: <0x89 0x8a>  →  <0x89 0x8a 0x91>
```

结果：

```
s5k5e8 4-0010: Error applying setting, reverse things back
```

两个驱动抢同一个引脚，前摄驱动申请 pinctrl 直接失败，probe 更早中止。
**已回退到 port@2 版本。**

### 14.5 现在的状态

```
启动镜像     port@2 版本（无 i2c-gpio、无 CCI 抢引脚）
供电         cam_avdd_front_2v8 = 2.8V enabled, users=2
             cam_front_dvdd_1v8  = 1.8V enabled, users=1
pin 33       UNCLAIMED（驱动没申请）
CCI master 1 无设备应答（i2c-4 全空）
CCI master 0 正常（0x36 = 后摄）
```

### 14.6 下一步：改驱动（需要 VM）

唯一正道是让 `s5k5e8` 驱动在 probe 时申请 pinctrl：

```c
/* 在 probe 里，power_on 之前 */
priv->pinctrl = devm_pinctrl_get(dev);
priv->pins_default = pinctrl_lookup_state(priv->pinctrl, "default");
pinctrl_select_state(priv->pinctrl, priv->pins_default);
```

这是**模块级改动**，可以从 `~/kbuild` 单独编 `s5k5e8.ko` 替换，
不需要重编整个内核、不需要 pmaports。

**等 VM 扩容完成就能做。**

---

## 15. 2026-10-29 08:35：驱动加了 pinctrl、CCI 改 400 kHz —— 传感器仍不应答

### 15.1 做了两件事

**A. 给 `s5k5e8` 驱动加 pinctrl（已编好并部署）**

之前驱动完全没处理 pinctrl（源码里 `pinctrl` 出现 0 次）。改动：

```c
struct pinctrl *pinctrl;
struct pinctrl_state *pins_default;
...
s5k5e8->pinctrl = devm_pinctrl_get(&client->dev);
s5k5e8->pins_default = pinctrl_lookup_state(s5k5e8->pinctrl, "default");
pinctrl_select_state(s5k5e8->pinctrl, s5k5e8->pins_default);
/* power_on 里再 select 一次，确保 MCLK 启动前引脚已复用 */
```

编译：`make -C ~/kbuild/linux-7.0.14-sdm660 ARCH=arm64 LLVM=-18 M=... KBUILD_MODPOST_WARN=1`

```
s5k5e8.ko  460064 字节
vermagic:  7.0.14-sdm660 SMP preempt mod_unload aarch64   ← 与设备一致
```

部署后日志确认：

```
[620.677705] s5k5e8 4-0010: S5K5E8: pinctrl "default" applied
```

**B. 把前摄 CCI 总线改成 400 kHz**

原来 `i2c-bus@1` 是 100 kHz，CCI 驱动给它配成 `mode 0`：

```
CCI master 1 mode 0: SCL_CTL=00c900ae SDA0=00cc00e7 ...   ← 原来
CCI master 0 mode 1: SCL_CTL=00260038 SDA0=00280028 ...   ← 后摄（能用）
```

改成 400 kHz 后：

```
CCI master 1 mode 1: SCL_CTL=00260038 SDA0=00280028 ...   ← 现在与 master 0 完全相同
```

### 15.2 但还是不行

```
i2cdetect -y -r 4     → 全空
s5k5e8 probe          → chip id 0x0, ret -6 (ENXIO)
pin 33                → 仍 UNCLAIMED（pinctrl select 成功但引脚没被 claim）
```

### 15.3 下一步待查

1. **VDIG 的使能 GPIO**：厂商 DT 里 `camera@2` 的 gpios 表有 `(pmic, gpio 3)` = CAM_VDIG。
   如果 pmOS 的 `cam_front_dvdd_1v8` 没有这个 enable-gpio，VDIG 实际没上电。
   （断电前正要查这一项）
2. 手工确认 MCLK2 是否真的在跑（需要示波器）

### 15.4 当前设备状态

```
启动镜像   port@2 + CCI master1 @400kHz
模块       s5k5e8.ko 带 pinctrl（.ko.zst.orig 已备份）
CCI m1     mode 1（与 m0 配置相同）
传感器     仍不应答
```

---

## 16. 2026-10-29 08:45：供电/时钟全部实测到位，锁定**复位极性**

### 16.1 一条条排除（这轮把能测的都测了）

| 检查 | 结果 |
|---|---|
| VANA `cam_avdd_front_2v8` | ✅ 2.8V enabled，由 GPIO49 使能 |
| VDIG `cam_front_dvdd_1v8` | ✅ 1.8V enabled，**带使能 GPIO** `gpio = <&pmic 3 0>`（PMIC GPIO3），与厂商 CAM_VDIG 一致 |
| VIO `vreg_l11a_1p8` | ✅ 与厂商 `pm660_l11` 一致 |
| **MCLK2 时钟** | ✅ **实测在跑**：`camss_mclk2_clk rate=24000000 enable=2 prepare=2`（失败 probe 有泄漏，一直没关）|
| CCI 引脚 | ✅ cci1 = gpio38/39，与厂商 `cci1_active` **完全一致** |
| CCI 电气配置 | ✅ `bias-pull-up` + `drive-strength = 2`，与厂商**完全一致** |
| CCI 模式 | ✅ 已从 mode 0(100k) 改成 mode 1(400k)，寄存器值与能用的 master 0 完全相同 |
| pinctrl | ✅ 驱动已补 `pinctrl_select_state`，日志确认 `pinctrl "default" applied` |

**结论：总线、时钟、供电、引脚、电气特性，全部与厂商一致。**

### 16.2 唯一剩下的差异：复位极性

| | 厂商 | pmOS（改前）|
|---|---|---|
| `camera@2` 的 gpios 表 | flags = **0**（ACTIVE_HIGH）| — |
| `reset-gpios` | — | `<&tlmm 52 **0x01**>`（ACTIVE_LOW）|

驱动 `power_on()` 最后把逻辑值设成 **0**：

- 声明 ACTIVE_LOW → 物理**高** → 若传感器 XSHUTDOWN 是高有效，则**一直按在复位里**
- 声明 ACTIVE_HIGH → 物理**低** → 正常工作

已改：`reset-gpios = <&tlmm 52 0x00>`，生成 `boot-resetpol.img` 并**已写入 boot 分区**
（不重启，下次开机生效）。

### 16.3 万一极性猜错，还有不用重启的后手

驱动有现成模块参数（改完 `rmmod`/`modprobe` 即可，不用重启）：

```sh
sudo modprobe -r s5k5e8
sudo modprobe s5k5e8 reset_mode=1 delay_ms=50     # 只释放不复位
sudo modprobe s5k5e8 reset_mode=2 delay_ms=50     # 只复位不释放
sudo modprobe s5k5e8 hold=1                        # 保持供电（便于测量）
```

### 16.4 下次开机第一件事

```sh
cd mipad4plus
python tools/pad_run.py scripts/frontcam_verify.sh --sudo
```

看三件事：`port@2` 在不在、CCI master 1 有没有设备、驱动有没有读到 chip id。

---

## 17. 2026-10-29 08:55：复位极性翻转**无效**，改为系统化扫参数

### 17.1 试了什么

把 `camera@10` 的 `reset-gpios` 从 `GPIO_ACTIVE_LOW`（0x01）改成 `GPIO_ACTIVE_HIGH`（0x00），
生成镜像刷入并重启。

结果：

```
port@2            ✅ 在
CCI master 0      2 个设备（后摄 0x36 + 0x50）
CCI master 1      0 个设备          ← 仍然无应答
```

⇒ **复位极性不是原因。**（也可能是两个极性都不对，但至少这一条排除了）

### 17.2 现在能确认的完整清单

| 项 | 状态 | 怎么确认的 |
|---|---|---|
| VANA 2.8V | ✅ 在 | regulator 状态 + GPIO49 使能 |
| VDIG 1.8V | ✅ 在 | regulator + **带使能 GPIO**（PMIC GPIO3）|
| VIO 1.8V | ✅ 在 | regulator |
| MCLK2 24MHz | ✅ **在跑** | `camss_mclk2_clk rate=24000000 enable=2` |
| CCI 引脚 | ✅ 38/39 | 与厂商 `cci1_active` 逐字节一致 |
| CCI 上拉/驱动强度 | ✅ | 与厂商一致（bias-pull-up，drive 2）|
| CCI 模式 | ✅ mode 1 | 寄存器值与能用的 master 0 相同 |
| pinctrl | ✅ 已应用 | 驱动日志 `pinctrl "default" applied` |
| 复位极性 | 已试两种 | 都无应答 |

**软件侧能做的检查已经做到头了。**

### 17.3 交付：自动扫参数脚本

`scripts/frontcam_sweep.sh` —— 不用重启，遍历 `reset_mode × delay_ms × hold`
共 18 种组合，每次重新加载模块并扫描前摄 CCI 总线，命中即停：

```sh
cd mipad4plus
python tools/pad_run.py scripts/frontcam_sweep.sh --sudo
```

输出示例：

```
  reset_mode=0 delay_ms=5    hold=1 -> 设备数 0  无 chip id
  reset_mode=0 delay_ms=20   hold=1 -> 设备数 0  无 chip id
  ...
```

全部失败时会直接给出**硬件测量清单**（VANA/VDIG 焊盘电压、MCLK2 波形、SDA/SCL 通断）。

### 17.4 结论

前摄的排查已经从"猜"变成"穷举"。软件侧所有可变量（供电、时钟、引脚、
电气、时序、极性）都试过了，如果 18 种组合仍无应答，就只剩**硬件测量**一途。

考虑到**魔趣能正常驱动**这个事实，最可能的残余解释是：
这颗平板的前摄模组在 pmOS 的某个硬件初始化差异下没被唤醒
（例如需要某个 PMIC GPIO 或 LDO 的额外时序），只能靠实测波形定位。

---

## 18. 2026-10-29 09:05：扫完 14 种组合，全部失败 —— 软件侧到底了

### 18.1 结果

```
reset_mode=0 delay_ms=1/2/3/5/8/12/20/50  -> 全部读不到 chip id
reset_mode=1 delay_ms=1/5/20              -> 全部失败
reset_mode=2 delay_ms=1/5/20              -> 全部失败
```

**14 种组合无一成功**，`chip id` 始终是 `0x0, ret -6`。

### 18.2 ⚠️ 这次踩了两个假阳性，写下来免得再犯

**假阳性 1：i2cdetect 显示 `0x10: UU`**

`UU` 的含义是"这个地址**被某个驱动占用**"，不是"设备有应答"。
我们自己的 `s5k5e8` 正在 probe 时就会占住 0x10，看起来像成功。

⇒ **判断传感器活没活，只能看驱动日志里的 chip id，不能看 i2cdetect。**

**假阳性 2：`/sys/bus/i2c/devices/4-0010/driver` 存在**

驱动里有个 bring-up 钩子 `hold=1`：

```
s5k5e8 4-0010: S5K5E8 hold=1: staying bound and powered for bring-up
```

**即使 probe 失败，它也会保持绑定**。所以"已绑定"同样不能当成功判据。

⇒ 唯一可信判据：`dmesg | grep 's5k5e8.*chip id'` 出现非零值。

### 18.3 现在的结论

前摄在软件侧已经**穷尽**：

| 已排除 | |
|---|---|
| 供电 | VANA 2.8V / VDIG 1.8V（含 PMIC GPIO3 使能）/ VIO 1.8V 全在 |
| 时钟 | MCLK2 实测 24 MHz（`clk_enable_count=2`）|
| 引脚 | gpio38/39，mux 与电气配置与厂商逐字节一致 |
| 控制器 | CCI master 1 配置与能用的 master 0 完全相同（mode 1, 400k）|
| pinctrl | 驱动已申请并应用 |
| 复位 | 两种极性 × 三种模式 × 八种延时，全部试过 |
| 地址 | 0x00–0x7f 全扫，无任何应答 |

**⇒ 再往下只能硬件测量**：

1. 万用表量模组焊盘：VANA 是否 2.8V、VDIG 是否 1.8V
2. 示波器量 gpio33（MCLK2）是否有 24 MHz 方波
3. 通断档量 gpio38/39 到模组 SDA/SCL 是否导通、有无上拉

### 18.4 交付

`scripts/frontcam_sweep.sh` 已修正（只认 chip id，排除 `hold` 干扰），
以后改完任何东西都可以一条命令重跑：

```sh
cd mipad4plus
python tools/pad_run.py scripts/frontcam_sweep.sh --sudo
```

---

## 19. 2026-10-31 14:45：按厂商 pinctrl 改复位/待机脚 —— 仍然 -6

### 19.1 新线索：厂商前摄 pinctrl 用的是 gpio47 + gpio44

从原厂 DTB（`artifacts/vendor-clover.dtb`）反编译得到 `qcom,camera@2`（前摄）：

```
gpios = <0xe9 0x21 0 0xe9 0x2f 0 0x1c3 0x03 0 0xe9 0x33 0>
        (gpio33)    (gpio47)    (pmic gpio3)  (gpio51)
qcom,gpio-reset = <1>   → GPIO 47
qcom,gpio-vdig  = <2>   → PMIC GPIO3
qcom,gpio-vana  = <3>   → GPIO 51
pinctrl-0 = cam_sensor_mclk1_active (gpio33) + cam_sensor_front_active (gpio47 + gpio44)
```

而我们的 DT 用的是 **reset = GPIO52**，而且**没有 standby-gpios**。

### 19.2 实验

改 DT（直接改 boot 里的 DTB，不重编内核）：

| 项目 | 改前 | 改后 |
|---|---|---|
| `reset-gpios` | gpio52 | **gpio47** |
| `standby-gpios` | 无 | **gpio44**（active-high） |
| `cam-reset2-default.pins` | gpio52 | **gpio47** |

刷入后确认 DT 已生效（`reset-gpios = <0x29 0x2f 0x01>`、`standby-gpios = <0x29 0x2c 0x00>`）。

### 19.3 结果

```
S5K5E8 reg 0x034e = 0x0 (ret -6)
S5K5E8 chip id reset HIGH = 0x0 (ret -6)
S5K5E8 chip id reset LOW  = 0x0 (ret -6)
S5K5E8 not responding (err -6), failing probe
```

**仍然 -6**。同时确认：

- 三路供电全部 enabled：`cam_avdd_front_2v8` 2.8V、`cam_front_dvdd_1v8` 1.8V、`cam_avdd_2v8` 2.8V、`cam_rear_dvdd_1v2` 1.2V；
- **后摄不受影响**，照常出图（`tablet-cam` 实拍成功）。

### 19.4 现在的判断

软件侧又排除了两项（复位脚、待机脚），剩余可能：

1. **硬件**：前摄排线/连接器接触不良或损坏（最可能）；
2. CCI master 1 的电气问题（但同一控制器下 master 0 工作正常）；
3. 传感器本身故障。

### 19.5 决定性验证建议

- 拆机重新插一次前摄排线（最直接）；
- 或刷回 Android/MoKee 看前摄是否还能用 —— 能则说明硬件好、是 Linux 侧更深的问题；不能则基本确定硬件。

### 19.6 当前设备状态

- boot 用的是带本次改动的 DTB（`build/boot-front.img`），**后摄正常**；
- 想恢复原样：刷回 `build/boot-avail2.img`（前摄节点 reset=gpio52）。
