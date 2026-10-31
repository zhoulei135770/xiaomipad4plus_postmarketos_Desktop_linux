# 40 — 前摄（S5K5E8）电气验证：软件侧全部正确，模块不响应

- 日期：2026-10-29
- 结论：**软件/设备树/供电/时钟/总线全部验证正确，传感器依然全地址 NACK。判定为硬件（模组或排线）问题。**

---

## 1. 为什么写这份文档

前摄从项目开始就没工作过。今天把能查的每一项都查到了寄存器级，
并且**推翻了我自己先前提出的两个错误结论**（记录在 §7，避免以后重犯）。

---

## 2. 逐一验证的正确项

### 2.1 供电（实测电压）

```
vddio-supply → PMIC RPM regulators-1/l11      1.8 V   I/O
vana-supply  → cam_avdd_front_2v8             2800 mV  enabled  users=2
vdig-supply  → cam_front_dvdd_1v8             1800 mV  enabled  users=1
```

驱动 `power_on()` 依次 enable 三路，返回全部为 0；
`/sys/class/regulator/*/state` 读数均为 `enabled`。

### 2.2 时钟

```
DT:      clocks = <&camss 0x52>;      /* = CAMSS_MCLK2_CLK (82) */
日志:     S5K5E8: setting MCLK to 24 MHz
         S5K5E8: MCLK -> 0 rate=24000000
```

`camss_mclk2_clk` 输出 24 MHz，符合 S5K5E8 要求。

### 2.3 复位

```
DT:      reset-gpios = <&tlmm 52 GPIO_ACTIVE_LOW>;
运行时:   gpio52 : out high          ← active-low，高电平 = 已释放
驱动日志: reset released (logical=0)
```

### 2.4 pinctrl

```
camera@10 pinctrl-0 = <0x91 0x92>
  0x91 → cam-mclk2-default   function=cam_mclk  pins=gpio33  drive=2mA
  0x92 → cam-reset2-default  function=gpio      pins=gpio52  drive=2mA
```

两组定义正确，驱动日志 `pinctrl "default" applied`。

### 2.5 CCI 总线

```
pin 36..39 (GPIO_36..39): device ca0c000.cci function cci_i2c
CCI master 0 mode 1: SCL_CTL=00260038 ...
CCI master 1 mode 0: SCL_CTL=00c900ae ...   ← master 1 已初始化
i2c-4 上挂着 4-0010
```

四个引脚全部 mux 成 `cci_i2c`，两个 master 都初始化完成。

### 2.6 从机地址

S5K5E8 的 7 位地址是 **0x10**，DT 中 `reg = <0x10>`，与手册一致。

---

## 3. 唯一失败项

```
S5K5E8: full sweep done
S5K5E8: Error reading reg 0x0000: -6      ← ENXIO = NACK
S5K5E8 probe: chip id = 0x0 (read ret -6)
```

**全地址扫描（0x08–0x77）无一 ACK。**

`-6`（ENXIO）表示从机明确 NACK，而不是超时——说明 CCI 总线本身工作正常
（它确实发出了 START + 地址，没有设备应答）。

---

## 4. 判定

电气条件全部满足仍无应答，只剩三种可能：

1. **模组未连接/排线松脱**（换过屏幕总成的机器常见）
2. **模组损坏**
3. **实际装配的是另一颗传感器**（与厂商 DT 的 S5K5E8 不符）

三者都需要拆机才能区分，软件侧无法进一步推进。

---

## 5. 若要继续，需要的动作

| 动作 | 说明 |
|---|---|
| 拆机检查前摄排线 | 最直接；确认 FPC 是否插到位 |
| 用 Android 验证同一颗前摄 | 若 Android 下也不出图 → 硬件确定损坏 |
| 若换过屏幕总成 | 确认新总成是否带前摄模组 |

---

## 6. 当前的处置

`/etc/modprobe.d/blacklist-s5k5e8.conf` 保留黑名单：

```conf
blacklist s5k5e8
```

理由：驱动 probe 失败会在每次启动占用 CAMSS_MCLK2 并打印大量日志，
且失败路径会 WARNING（`regulator_bulk_free`）。等硬件确认后再启用。

---

## 7. 两个被推翻的错误结论（重要）

### 7.1 ❌ "DT 时钟配错，应为 0x54"

我曾判断 `clocks = <&camss 0x52>` 是错的、应该改成 `0x54`。
实际查 `include/dt-bindings/clock/qcom,mmcc-sdm660.h`：

```c
#define CAMSS_MCLK0_CLK   80   /* 0x50 */
#define CAMSS_MCLK1_CLK   81   /* 0x51 */
#define CAMSS_MCLK2_CLK   82   /* 0x52  ← 原值就是 MCLK2，本来正确 */
#define CAMSS_MCLK3_CLK   83   /* 0x53 */
```

改成 0x54 后实测时钟变成 **80.8 MHz**（那是别的时钟），反而更错。
已把 boot 镜像回滚到原始 `55c7bce4`。

**教训**：改设备树前必须先在头文件里核对常量，不能靠推断。

### 7.2 ❌ "vana/vdig 是 dummy regulator，模拟电源没供上"

一度根据 regulator 汇总里只看到一个 cam_front 条目判断其余是 dummy。
实际用 phandle 反查后确认三路全部是真实 regulator 且已使能（见 §2.1）。
汇总里条目少是因为 probe 失败后驱动把电源关了。

---

## 8. 复现命令

```sh
# 电压
for r in /sys/class/regulator/regulator.*; do
    echo "$(cat $r/name) $(cat $r/microvolts) $(cat $r/state)"; done | grep cam

# 时钟
grep camss_mclk /sys/kernel/debug/clk/clk_summary

# CCI 引脚
grep -E 'cci_i2c' /sys/kernel/debug/pinctrl/*/pinmux-pins

# 复位脚
cat /sys/kernel/debug/gpio | grep gpio52

# 触发一次 probe 看完整日志
sudo modprobe -r s5k5e8; sudo dmesg -C; sudo modprobe s5k5e8; dmesg | grep s5k5e8
```
