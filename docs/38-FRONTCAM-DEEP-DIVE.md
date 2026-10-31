# 前摄深挖（S5K5E8）—— 2026-10-29 12:20

> 结论先说：**软件层面能查的全部通过了，传感器仍然对所有地址 NACK。**
> 剩下两个可能：① MCLK2/复位**没有真正到达连接器**（SoC 侧一切正常但链路断了）；
> ② 传感器模块/排线实际有问题。

---

## 1. 本轮新确认的事实

### 1.1 厂商 DT 的硬件定义（从 miui-dtb-0.dtb 解出）

| 信号 | 引脚 | 控制器 |
|---|---|---|
| CAMIF_MCLK2 | GPIO 33 | TLMM，功能 cam_mclk |
| CAM_RESET2 | GPIO 52 | TLMM |
| CAM_VANA | GPIO 49 | TLMM（gpio-regulator 2.8V） |
| CAM_VDIG | **GPIO 3** | **pm660L** 的 GPIO |
| MCLK 频率 | 24 MHz | CAMSS（vendor id 29 / 131） |
| CCI master | 1 | — |

三路电压（厂商）：`cam_vio 1.8V`、`cam_vana`（不指定）、`cam_vdig 1.8V`。

### 1.2 我们 DT 的对照 —— 全部一致

```
camera@10 pinctrl-0 = cam-mclk2-default(gpio33, cam_mclk) + cam-reset2-default(gpio52)
cci1-default-state  = gpio38/39, function cci_i2c
vddio-supply = l11               1784 mV   ✓
vana-supply  = cam-avdd-front-2v8 2800 mV  ✓
vdig-supply  = cam-front-dvdd-1v8 1800 mV  ✓
cam_front_dvdd_1v8 的 gpio = <&pm660l gpio 3>  ✓  （不是 pm660！）
```

### 1.3 运行时实测（hold=1 保持供电）

```
cam_front_dvdd_1v8   enabled  1800 mV
cam_avdd_front_2v8   enabled  2800 mV
l11                  enabled  1784 mV   (VIO)
l13                  enabled  1780 mV   (VDIG 上游)
camss_mclk2_clk      enable=3 rate=24000000  consumer=4-0010 (xvclk)  ✓
reset                released
```

### 1.4 I2C 行为

```
i2cget  -y 4 0x10 0x0000 w   -> Error: Read failed
i2ctransfer -f -y 4 ...      -> ENXIO (No such device or address)
驱动自身全地址扫描            -> 每个地址 ret = -6 (ENXIO)
```

**`-6 = ENXIO` 表示 NACK**（地址发出去了、没人应答），不是超时。
说明 CCI master 1 **确实在驱动总线**，是传感器没反应。

---

## 2. 已排除的可能（逐项有实测证据）

| 假设 | 验证方式 | 结果 |
|---|---|---|
| 供电缺失 | regulator_summary 实测 | ❌ 三路全在，电压正确 |
| VDIG 接错 PMIC | DT phandle 解析 | ❌ 指向 pm660L GPIO3，与厂商一致 |
| MCLK 频率错 | clk_summary | ❌ 24 MHz，enable=3 |
| MCLK 引脚复用缺失 | pinctrl 组解析 | ❌ cam-mclk2-default 含 gpio33 |
| 复位脚错 | pinctrl / DT | ❌ gpio52，CAM_RESET2 |
| CCI master 1 未实现 | 内核源码 + 寄存器 | ❌ NUM_MASTERS=2，M1 中断全使能，SCL_CTL 已编程 |
| CCI 引脚错 | cci1 组 | ❌ gpio38/39，cci_i2c |
| 从机地址错 | 全地址扫描 0x00-0x77 | ❌ 无一应答 |
| 时序/延迟不足 | 14 组 reset_mode × delay 组合 | ❌ 全部 NACK |
| 板级 EEPROM | 厂商 DT | ⚠️ 前摄 EEPROM 也在 master 1，同样无响应 |

---

## 3. 唯一剩下的差异（值得一试）

```
master 0（后摄，工作正常）: clock-frequency = 400000  → CCI mode 1
master 1（前摄，不应答）  : clock-frequency = 100000  → CCI mode 0
```

主线的 CCI 驱动对 100 kHz 用的是另一套分频寄存器值
（`SCL_CTL=0x00c900ae` vs 400k 的 `0x00260038`）。
如果该 HW 版本的 100k 分频配置有问题，就会表现为"地址发出去但采样点错"→ NACK。

**试验方案**：把 `i2c-bus@1` 改成 400000（与 master 0 一致）。
只需改一个 DTB 属性，失败也只是前摄继续不可用，不影响其他功能。

---

## 4. 下一步建议（按成本排序）

1. **【零成本】把 master 1 改成 400 kHz** 再试一次
2. **【需工具】示波器/万用表测连接器**：
   - GPIO33 是否有 24 MHz 方波
   - VANA 是否有 2.8V、VDIG 是否有 1.8V（在排线端测，不是 PMIC 端）
   - RESET 释放后是否为 1.8V
3. **【需拆机】检查前摄排线**是否插好、有无氧化

> 如果第 2 步发现 SoC 侧有波形但连接器侧没有，就是排线/座子问题；
> 如果连接器侧也有信号，那才是传感器模块本身。

---

## 5. 顺带发现（对以后有用）

- 厂商 DT 里 CCI master 1 上挂了 **3 个设备**：
  `camera@1`(pos=0)、`camera@2`(pos=1，前摄)、以及对应 eeprom
- 厂商内核日志有 `stmvl53l0_init_cci`——CCI 上还有一颗 ST 激光测距（可能未装）
- 厂商前摄 `probe succeeded` 证明**硬件在 Android 下是活的**
- 厂商上电顺序：`cam_vio → cam_vana → cam_vdig`，与我们驱动一致
