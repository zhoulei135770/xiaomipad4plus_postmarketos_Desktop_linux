# 53 — 其他未解决硬件的反编译结果（GPU/SD/振动/前摄/指纹）

- 日期：2026-10-30 15:00
- 方法：VM `192.168.1.200` 上挂载 MIUI `vendor.img`（ext4），反编译厂商 DTB（`miui.dts`），
  对照主线 `stock.dts` 和主线驱动源码。
- **最大发现：GPU 的 zap 固件其实就在厂商镜像里，缺的只是文件。**

---

## 0. 17:10 GPU 实测结论（重要）

### 做过的
1. 从 `vendor.img:/firmware/` 取出 `a512_zap.*` + `a530_*`，加进 **boot 的 initramfs**
   （`usr/lib/firmware/` 和 `usr/lib/firmware/qcom/`），重打包刷入 p12。
2. 又在 GPU 节点加了 `power-domains = <&rpmpd VDDMX>, <&gpucc GPU_CX_GDSC>, <&gpucc GPU_GX_GDSC>`。

### 结果（最终：成功）
- ✅ zap 固件加载成功，不再报 `Unable to load a512_zap.mdt`；
- ✅ `a530_pm4.fw` / `a530_pfp.fw` 从新位置加载；
- ✅ devfreq 注册出完整 OPP（19.2–588MHz），GPU 驱动初始化完成；
- ✅ **`eglinfo`（surfaceless）实测通过**：
  ```
  OpenGL core profile vendor: freedreno
  OpenGL core profile renderer: FD512
  OpenGL core profile version: 3.1 Mesa 26.2.6
  OpenGL ES profile version: OpenGL ES 3.1 Mesa 26.2.6
  ```
  **GPU 可以正常跑 GL/GLES！**
- ⚠️ 之前几次“挂死”是**读 `/sys/kernel/debug/dri/1/gpu`** 触发的——这个 debugfs 读取在
  本内核上会卡住整机，与 GPU 是否可用无关。**以后不要读它。**

### 必做的配套
```sh
# 与 pmOS soc-qcom-sdm660 相同的 mesa quirk（已在设备上写入）
/etc/profile.d/sdm660-adreno.sh:
  export FD_MESA_DEBUG=noblit
```

### 持久化
- zap + a530 固件在 **boot 镜像的 initramfs** 里（p12 已刷），重启不会丢；
- GPU 节点 power-domains 的 DT 改动也在 p12 里；
- `/etc/profile.d/sdm660-adreno.sh` 在 rootfs。

### 结论
**GPU（Adreno 512）已解决。** 不要再读 GPU debugfs；正常跑 GL/GLES 没问题。
如果以后出现个别应用渲染异常，先试 `FD_MESA_DEBUG=noblit`（已全局设置）。

---

## 1. GPU（Adreno 512）—— 很可能只差固件

### 厂商事实
- MIUI DTB：`qcom,kgsl-hyp { compatible = "qcom,pil-tz-generic"; qcom,pas-id = <0x0d>; qcom,firmware-name = "a512_zap"; }`
- `vendor.img:/firmware/` 里有：
  ```
  a512_zap.mdt (6684)  a512_zap.b00 (148)  a512_zap.b01 (6536)
  a512_zap.b02 (4916)  a512_zap.elf (17204)
  a530_pfp.fw (16820)  a530_pm4.fw (19652)  a530_gpmu.fw2 (8052)
  ```
- 我们当前 DTB 里 **zap-shader 节点是完整的**：
  ```
  zap-shader { memory-region = <0x35>; firmware-name = "a512_zap.mdt"; };
  ```
- 启动日志的 `Unable to load a512_zap.mdt` 就是 `request_firmware` 返回 -2（文件不存在）。

### 修复（不用刷机、不用改 DT）
把 8 个文件放到设备 `/lib/firmware/`（再补一份到 `/lib/firmware/qcom/` 以防路径前缀），重启。
预期：`adreno_zap_shader_load` 成功 → `gpu hw init` 通过 → GPU 可用。

文件已备好在 `build/vendor-fw/`（本地）和 VM `~/vendor-fw/`。

### 风险
低。只是加固件文件；失败也不影响启动（zap 失败和现在一样）。
成功后可谨慎验证（先看 dmesg，不要一上来就读 GPU debugfs/GL——之前那样会整机卡死）。

---

## 2. SD 卡 —— 主设备树里根本没有控制器节点

- 厂商：`sdhci@c084000`（SD 槽），`cd-gpios = <&tlmm 0x36>`，`vdd-supply`/`vdd-io-supply`，
  `qcom,bus-speed-mode = "SDR12/SDR25/SDR50/DDR50/SDR104"`，pinctrl active/sleep。
- 主线 `stock.dts`：**没有 `sdhci@c084000` 节点**（只有 eMMC 的 sdhci@c0c4000）。
- ⇒ 要支持 SD 卡，需要在 DTS 里补一个 mainline 风格的 SDHCI 节点：
  - `compatible = "qcom,sdhci-msm-v5"`（或主线 sdm660 用的 v5）
  - reg/irq、`clocks = <&gcc GCC_SDCC2_AHB_CLK>, <&gcc GCC_SDCC2_APPS_CLK>`
  - `vmmc-supply`/`vqmmc-supply`（pm660 LDO）
  - `cd-gpios = <&tlmm 54 GPIO_ACTIVE_HIGH>`（0x36=54）
  - pinctrl（sdc2 的 clk/cmd/data/cd）
- 需要刷 boot。中等工作量。

---

## 3. 振动马达 —— 主线没有驱动

- 厂商：`pm660@1` 下 `qcom,haptic@c000`，`compatible = "qcom,qpnp-haptic"`，
  参数一应俱全（LRA、play-mode direct、vmax 3200mV、ilim 800mA 等）。
- 主线 `drivers/input/misc/` 里 **没有 qpnp-haptic 驱动**（grep 为空）。
- ⇒ 要么移植下游 `qpnp-haptic` 驱动（约 1–2k 行，涉及 SPMI/PMIC revid/misc），
  要么放弃。工作量大，优先级低。

---

## 4. 前摄 —— 在 CCI master 1 上，可能缺电/缺 GPIO

厂商 DTB 的三路相机：
| 节点 | 位置 | CCI | CSID | MCLK | reset GPIO | 备注 |
|---|---|---|---|---|---|---|
| camera@0 | 后 | 0 | 0 | MCLK2 | 0x2e | 有 standby 0x2c |
| camera@1 | 后辅 | 1 | 1 | MCLK1 | 0x4d | |
| camera@2 | **前** | **1** | 2 | MCLK2 | 0x34 | `CAM_VANA`=0x31、`CAM_VDIG`=0x33 |

前摄关键点：
- 和 camera@1 共用 **CCI master 1**；我们现在的故障正是“CCI master1 无应答”。
- 前摄还有独立的 `CAM_VANA`/`CAM_VDIG` GPIO 控制（0x31/0x33）和 MCLK2。
- 如果主线的 camera 节点没有这两个 GPIO 稳压器/pinctrl，前摄就没上电 → NACK。

下一步：把 `stock.dts` 里前摄节点和厂商的 gpio/regulator 对照，补上 VANA/VDIG 和 MCLK2；
若 CCI1 本身在主线驱动里有问题，再查 cci 驱动。需要刷 boot。

---

## 5. 指纹 —— 节点已有，差异在时钟/pinctrl

厂商 `fpc1020` 节点：
```
spi-max-frequency = <1000000>;
interrupts = <0x47 0>;  interrupt-parent = <&tlmm>;
fpc,gpio_rst = <&tlmm 0x6c 0>;  fpc,gpio_irq = <&tlmm 0x47 0>;
clocks = <&gcc GCC_... 0x2e>, <&gcc ... 0x34>;  clock-names = "iface_clk","core_clk";
pinctrl-names = avdd/vddio/spi/reset/irq 共 8 个状态;
```
我们的 `stock.dts` 里 `fpc1020@0` 节点存在，但没有 vendor 的 clocks/pinctrl 组。
“能出中断、阵列不成像”更像是 SPI 时序/复位/供电问题，而不是 DT 缺节点；
下一步对照 pinctrl（reset/irq 电平）和 SPI mode，再决定是否改 DT。

---

## 6. 手写笔

厂商 DTB 里没有 stylus/pen 相关节点（grep 无结果）——这台机器大概率没有主动笔硬件，
或者笔走的是触摸屏协议（不需要单独驱动）。**可以先排除。**

---

## 7. 优先级

1. **GPU 固件**（零刷机、成功率高）——设备回来第一件事。
2. SD 卡 DT 节点（一次刷机，中等）。
3. 前摄 VANA/VDIG + CCI1（一次刷机，中等）。
4. 指纹 pinctrl/SPI 对照（先只读分析）。
5. 振动马达（驱动移植，低优先）。
6. 手写笔（排除）。

所有固件已备份在 `build/vendor-fw/`。
