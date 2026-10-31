# 前摄 S5K5E8 —— 硬件测量指南（给你动手用）

> 这是唯一还挡着前摄的关卡：**软件侧已全部就绪，传感器就是不应答 I2C**。
> 需要你拿万用表量几个电压，确认模组到底有没有电。

---

## ⚠️ 2026-10-27 更新：只要先量 **VIO** 这一个点

本轮用「r143 内核 + 只改设备树」实测，内核侧三路电全部 `enabled`、MCLK 24 MHz、复位已释放、
CCI master1 两条线空闲高电平，但 **0x08–0x77 全部 NACK**（后摄总线同时 ACK 0x50/0x58）。

对照 Android 侧日志（`tools/android-cam-data/dmesg-boot.txt`）：

```
[7.645263] s5k5e8 probe succeeded            ← Android 上前摄 probe 是成功的
cam_avdd_front_gpio_regulator use=0          ← 当时 VANA 开关是关的
pm660_l11 → qcom,camera@2  1800mV            ← 只有 VIO 开着
```

**结论：传感器只要 VIO = 1.8 V 就能应答 I2C，VANA/VDIG 是成像时才需要。**

所以测量顺序改成：

1. `sudo python3 pad_campower2.py high`（先把电打开）
2. **先量 VIO/DOVDD 是否有 1.8 V**（来自 pm660_l11，模组座上的 I/O 电源脚）
   - **有** ⇒ 模组/排线/CCI 走线问题（模组座虚焊、排线断、或模组坏）
   - **没有** ⇒ l11 → 模组座的通路断了（量模组座与后摄座同位置对照）
3. 再量 VANA 2.8 V / VDIG 1.8 V / RESET 1.8 V / MCLK（直流约 0.9 V）

下面的完整测量表仍然有效，只是 **VIO 的优先级最高**。

---

## 一、先理解现状

| 事实 | 证据 |
|---|---|
| 传感器地址 0x10，在 CCI master 1（GPIO38/39）| 厂商 DT `camera@10` |
| 驱动能加载、能探测 | `s5k5e8` 模块 probe 时 I2C 传输返回 **-ENXIO（无应答）** |
| 所有已知电源/时钟/复位脚都驱动过了 | GPIO49(VANA)、PM660L LDO3(VDIG)、GPIO33(MCLK)、GPIO52(RESET) |
| 后摄同样方法一次成功 | 说明方法本身没问题 |

**结论**：不是 I2C 时序/驱动问题，是传感器**没被供电**（或没被正确复位）。

---

## 二、测量前必须先把电打开

⚠️ **重要**：我在补丁 0037 里把前摄节点禁用了，所以开机后这些电源**默认是关的**，
直接量会全是 0V。必须先手动打开：

```bash
# 在平板上执行：打开 VANA(GPIO49) 和 VDIG(PM660L GPIO3)
sudo python3 pad_campower2.py high

# 用完关掉
sudo python3 pad_campower2.py low
```

（脚本已修好 ioctl，之前那个版本实际是失效的。）

---

## 三、量哪里

**位置**：前摄模组的 FPC 排线座（主板一侧），或模组背面的测试点。
在平板**竖屏朝上**、摄像头位于顶部时，前摄座一般在主板**顶部中间偏左**。

**对照法（最稳妥）**：后摄是好的，所以先量后摄座的对应脚，再量前摄座的，
**同位置的电压应该基本一致**。

---

## 四、要量的 5 个点

| 信号 | 典型值 | 在哪里 | 说明 |
|---|---|---|---|
| **VANA / AVDD** | **2.8 V** | 模组座上的模拟电源脚 | 由 GPIO49 使能 |
| **VDIG / DOVDD** | **1.8 V** | 数字 IO 电源 | 由 PM660L GPIO3 使能 |
| **VCORE / DVDD** | **1.2 V** | 内核电源（部分模组内部产生）| 若没有可能是正常 |
| **RESET** | 平时 **1.8 V**，复位时拉低 | GPIO52 | 应被拉高（释放复位）|
| **MCLK** | 24 MHz 方波，直流约 **0.9 V** | GPIO33 | 万用表测不到波形，只看有没有电压 |

参照：S5K5E8 数据手册典型供电 **AVDD 2.8V / DOVDD 1.8V / DVDD 1.2V**。

---

## 五、怎么判断

| 测量结果 | 结论 | 下一步 |
|---|---|---|
| VANA 和 VDIG 都正常（2.8V / 1.8V）| 模组有电，问题在别处 | 量 MCLK/RESET；再查排线是否接触不良 |
| **VANA = 0V** | VANA 供电没到模组 | 检查 GPIO49 到模组的通路、模组座虚焊 |
| **VDIG = 0V** | PM660L LDO3 没输出 | 检查 LDO3 配置、负载短路 |
| 两个都是 0V | 模组完全没电 | **排线没插好/断裂**，或模组已损坏 |
| 电压正常但 MCLK = 0V | 时钟没送到 | 查 GPIO33 通路 |

**特别注意**：如果 VANA/VDIG 有电压但**明显偏低**（比如 1.2V 而不是 2.8V），
说明该电源被**短路拉低**了 —— 那基本就是模组坏了。

---

## 六、万用表没有也能做的两个检查

### 1. 用平板自己量 I2C 上拉
```bash
# 打开电源后，看 CCI master 1 的 SDA/SCL 是否被拉高
sudo i2cdetect -y 5
# 如果整行都是 "--"，说明总线没有上拉或被拉死
```

### 2. 看 I2C 总线是否被"卡住"
如果 SDA 被某个设备拉低不放，整条总线会失效：
```bash
# 探测后摄（0x36，已知好的）是否还能应答
sudo i2ctransfer -y -f 4 w2@0x36 0x00 0x00 r2
```
- 后摄能应答 ⇒ CCI 总线本身没问题，是前摄自己不应答
- 后摄也不能应答 ⇒ 总线被拉死（可能是前摄模组短路）

---

## 七、如果确认模组没电且通路正常

那就要回到"**是不是这个型号根本没有前摄**"这个可能性。

可以对照 `18-HARDWARE-COMPLETE.md`（48 项硬件清单）确认：
- 设备型号是 **clover-plus**（Mi Pad 4 Plus），主板 DTS 里确实有前摄节点
- 但如果实物没有前摄模组，那这个节点就是"有定义无硬件"

**最简单的确认方法**：看平板正面顶部**有没有摄像头开孔和镜头**。
有开孔 + 镜片 ⇒ 有模组；只有一个黑点或没有开孔 ⇒ 可能真没有。

---

## 八、量完之后

把结果告诉我（几个电压值），我就能判断是：
1. 硬件坏了 → 结束，软件侧已尽力
2. 供电通路问题 → 修硬件
3. 软件还有没驱动到的使能 → 继续找

---

## 附：当前软件侧已完成的全部工作

```
✅ 驱动 s5k5e8.c（probe / 上电序列 / 时钟 / 复位 / 寄存器配置）
✅ DT 节点 camera@10（CCI master 1，GPIO33/52，VANA=GPIO49，VDIG=PM660L LDO3）
✅ I2C 探测工具链（i2ctransfer / 寄存器扫描脚本）
✅ GPIO 电源控制脚本（已修 ioctl）
✅ 电源时序多次调整（先电后钟 / 先钟后电 / 反相位 reset）
❌ 传感器始终不 ACK —— 缺的只是"电"
```

---

## 九、测量时让前摄"保持上电"（2026-10-27 新增）

模块有 `hold` 参数，加载后**不会释放电源**，方便慢慢量：

```bash
sudo modprobe -r s5k5e8 2>/dev/null
sudo modprobe s5k5e8 hold=1 read_id=0      # 上电并保持（read_id=0 跳过 I2C 扫描）
```

确认状态（都应如下）：

```bash
for r in /sys/class/regulator/*/; do n=$(cat $r/name); case $n in
  *avdd_front*|*front_dvdd*|*l11*|*l13*) echo "$n $(cat $r/state)";; esac; done
# cam_avdd_front_2v8 enabled / cam_front_dvdd_1v8 enabled / l11 enabled / l13 enabled

grep -E "gpio(33|49|52) " /sys/kernel/debug/gpio
# gpio49 out high（VANA 开关合上）、gpio52 out high（复位已释放）、gpio33 func1（MCLK）
```

本轮实测就是这个状态，但 I2C 仍然全 NACK ⇒ **接下来只需量电压**。
量完执行 `sudo modprobe -r s5k5e8` 释放电源即可。

---

## 十、没有万用表时：软件侧已排除的全部项（2026-10-27）

用户没有测量工具，所以本轮把所有能"用软件推断电气状态"的路子都跑了一遍：

| 测试 | 命令/方法 | 结果 |
|---|---|---|
| 复位极性（正常释放 = 物理高）| `modprobe s5k5e8 read_id=1` | NACK |
| 复位极性（反相，停在物理低）| `modprobe s5k5e8 reset_mode=2 read_id=1` | NACK |
| 换到 CCI master 0 读 | `i2ctransfer -y -f 3 w2@0x10 ...` | NACK |
| 8 位地址形式 0x20 | bus3/bus4 各测 | NACK |
| 上电后延迟 100/300/800 ms | `delay_ms=N` | NACK |
| 三路电保持开启 | `hold=1` + regulator state | 全部 `enabled` |
| 电池电流差（判断是否吃电）| rails off/on 各采样 15 次 | 差值落在噪声内（±50 mA），不可判 |
| CCI 适配器映射确认 | `/sys/bus/i2c/devices/i2c-*` | i2c-3 = master0（后摄 0x36）✓，i2c-4 = master1（前摄 0x10）✓ |
| 同总线参考器件 | 后摄 EEPROM 0x50 | ACK，返回 `0x01 0x06` ⇒ 总线健康 |

**结论：主机侧（电源使能、时钟、复位、总线、地址、时序）已全部正确，模组仍不应答。**
剩下只能是模组侧的电/连接问题 —— 需要物理手段（万用表或换模组）。

### 没有万用表时，唯一能做的决定性验证：回 MIUI 试前摄
之前采集的 Android dmesg 里确实有 `s5k5e8 probe succeeded`（来自本机 MoKee），
说明**当时**硬件是好的。若现在 MIUI 相机里前摄也不出图 ⇒ 模组/排线在这段时间里坏了或松了。
刷 MIUI 与恢复 pmOS 的流程见 `16-FLASH-TO-MIUI.md` / `RESTORE-PROCEDURE.md`（有风险，需要时再做）。

### 另一个免费的检查
正面顶部中间是否能看到**摄像头镜片**（有镜片=有模组；只有黑点/没开孔=可能没装）。
