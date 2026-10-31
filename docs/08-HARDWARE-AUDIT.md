# 08 · 硬件完整清单与缺陷（2026-10-24 全量审计）

> 本文是**全硬件普查结果**，不是猜测。每一条都附实测证据。
> 之前的交接只列了 3 个问题（扬声器/休眠/蓝牙），**实际有 9 项缺陷**。

---

## ⚠️ 重大更正（2026-10-24 09:40）：第二节的传感器结论是错的

**本文第二节说「`scan_elements` 为空、传感器全废」，这个判断已被实测推翻。**

| 本文原话 | 实测真相 |
|---|---|
| "`scan_elements` 全为空" | 4 个设备每个都有 12 或 6 个 scan_elements |
| "没有 `in_accel_x_raw`" | SMGR 是**纯 buffer 型**设备，本来就没有 `*_raw` 属性 |
| "buffer/enable 只有 accel 能写" | **accel/gyro/mag 三个都能写**，只有 prox 失败 |
| "用户态读不到数据" | `/dev/iio:device2` 读出 **768 字节/秒**真实样本 |

**五个传感器的真实状态（全部实测）：**

| 芯片 | 状态 | 证据 |
|---|---|---|
| BOSCH BMI120 加速度计 | ✅ **能读** | `z = -9.81 m/s²` |
| BOSCH BMI120 陀螺仪 | ✅ **能读** | 静态 `~0.02 rad/s` |
| AKM AK09918 磁力计 | ✅ **能读** | `117 µT` 地磁 |
| Capella CM3232 环境光 | ⚠️ DSP 拒绝 `0x501` | **DSP 里有完整驱动，只缺 registry JSON** |
| ROHM BU52061NVX 霍尔 | ✅ 硬件可用 | **走 gpio-keys SW_LID，不用 SMGR** |

**顺带修好一个真 bug**：accel 的 mount matrix 是镜面（det=-1），
导致平放时判定 `face-down`。已用 udev 覆盖修好 → `face-up`。

**完整证据、根因、改动清单 → `09-P0-1-SENSORS.md`（权威）。**

**本文第二节保留原文，仅作为「错误判断的记录」参考。请不要照它执行。**

---

## 一、总览

| 分类 | 数量 |
|---|---|
| 已识别硬件 | 25+ |
| ✅ 完全可用 | 11 |
| ⚠️ 部分可用（有缺陷） | 5 |
| ❌ 完全不可用 | 4 |
| ❓ 待确认（硬件是否存在） | 3 |

---

## 二、传感器中枢 SMGR 的全部身份（重大发现）

> **⚠️ 本节末尾的「用户态读不到数据」结论已被推翻，见文首更正与 `09-P0-1-SENSORS.md`。
> 下面保留硬件的真实身份信息（这部分是对的），但不要相信"读不到数据"的判断。**

用 `sudo dmesg | grep qcom_smgr` 得到的**真实硬件清单**（注意：`5-60` 是 QRTR node-port，**不是 I2C 地址**，见 `09-P0-1-SENSORS.md` §6.2）：

```
qcom_smgr 5-60: 0x00,0: BOSCH BMI120 Accelerometer
qcom_smgr 5-60: 0x00,1: BOSCH BMI120 Temperature
qcom_smgr 5-60: 0x0a,0: BOSCH BMI120 Gyroscope
qcom_smgr 5-60: 0x0a,1: BOSCH BMI120 Temperature
qcom_smgr 5-60: 0x14,0: AKM AK09918 Magnetometer
qcom_smgr 5-60: 0x28,0: Capella CM3232 ALS
qcom_smgr 5-60: 0x50,0: ROHM_SEMICONDUCTOR BU52061NVX ROHM_Hall_Effect
```

**翻译：**

| 芯片 | 功能 | 办公电脑用途 |
|---|---|---|
| BOSCH BMI120 (0x00) | 加速度计 + 温度 | 屏幕自动旋转 |
| BOSCH BMI120 (0x0a) | 陀螺仪 + 温度 | 屏幕自动旋转 |
| AKM AK09918 (0x14) | 磁力计（电子罗盘） | 方向参考 |
| **Capella CM3232 (0x28)** | **环境光传感器** | **自动亮度调节** |
| **ROHM BU52061NVX (0x50)** | **霍尔传感器** | **智能保护套自动唤醒/休眠** |

### 关键：硬件是好的，驱动加载了，用户态也能读（原判断错误，见文首）

> 下面这段是最初的错误取证方式，保留作为教训。

```bash
$ ls /sys/bus/iio/devices/iio:device2/
in_accel_scale          ← 只有 scale
in_accel_sampling_frequency
in_mount_matrix
# 没有 in_accel_x_raw / in_accel_y_raw / in_accel_z_raw！
```

**这不是"没通道"，这是 buffer 型 IIO 设备的正常形态。**
`scan_elements/` 里有全部 12 个通道描述，`/dev/iio:device2` 能读出真实数据。

尝试开启 buffer：

```
accel : buffer/enable 写入成功
prox  : ✗ 写不进去（真实原因：DSP 返回 0x501，不是内核问题）
gyro  : ✓ 能写（原文误记为失败）
mag   : ✓ 能写（原文误记为失败）
```

### 已加载的驱动链
```
qcom_smgr_accel   12288  0
qcom_smgr_gyro    12288  0
qcom_smgr_prox    12288  0
qcom_smgr_mag     12288  0
qcom_smgr         20480  4   (被上面四个引用)
sns_smgr          16384  1
qrtr_smd          20480  1
```

### 固件警告（关键线索）

> **⚠️ 这段的推断错了。** 详见 `09-P0-1-SENSORS.md` §3.3 / §3.4。

```
qcom_sns_reg: Direct firmware load for qcom/sensors/sns.reg-xiaomi,clover-plus failed with error -2
qcom_sns_reg: firmware loaded, error above can be ignored.
```

**真实情况（已验尸）：**
- fallback 的 `sns.reg` **存在且被加载**（25,468 字节）
- 但它的配套 registry JSON **全是 SDM845 的**（`soc_id: 291/246/305/321`，本机是 **317**）
- 这导致只有 **ALS（CM3232）** 失效（DSP 里驱动齐全，只缺它的 JSON）
- accel/gyro/mag 因为 DSP 有内置默认而侥幸可用

**ALS 失效不是"缺 sns.reg"，而是"缺 cm3232 的 registry 条目"。**

### 要做的事（已修正）

1. ~~找 `sns.reg-xiaomi,clover-plus`~~ —— **不需要**，fallback 已经够用
2. ✅ 给 DSP 补一份 `cm3232.json`（见 `09-P0-1-SENSORS.md` §6 改动 3）
3. ✅ 内核侧把 ALS 从 `IIO_PROXIMITY` 改成 `IIO_INTENSITY`
4. 霍尔**不用 SMGR**，走 gpio-keys 的 `SW_LID`

---

## 三、完整硬件清单

### ✅ 完全可用（11 项 + 传感器 4 项，2026-10-24 09:40 更正）

| 硬件 | 证据 |
|---|---|
| CPU (SDM660, 8核) | `uname` 正常，8 核都在 |
| 内存 3.5GB | `free` 正常 |
| 存储 116.5GB eMMC | `lsblk` 正常 |
| 屏幕 BOE TV101WUM (1920×1200) | `xrandr` + 实际显示 |
| 触屏 Goodix GT9110 | `i2c 0-005d`，打字测试通过 |
| 背光 TI LP8556 | `i2c 1-002c`，brightness 0-255 可调 |
| Wi-Fi (ath10k / WCN3990) | `wlan0` up，SSH 工作 |
| 蓝牙 (QCA / hci0) | `UP RUNNING`，`PSCAN ISCAN` |
| 电源键 / 音量键 | `pm8941_pwrkey` / `gpio-keys` |
| 麦克风 | `hw:0,1` + 400% 增益 = 13% FS |
| 电池电量计 (pmi8998-FG) | 电压/电流/温度/百分比都准 |
| **加速度计 BMI120** | ✅ `z = -9.81 m/s²`（方向已用 udev 修正） |
| **陀螺仪 BMI120** | ✅ 静态 `~0.02 rad/s` |
| **磁力计 AK09918** | ✅ `117 µT` 地磁 |
| **霍尔 BU52061NVX** | ✅ 走 `gpio-keys` SW_LID（event3，wakeup enabled） |

### ⚠️ 部分可用（5 项，有缺陷）

| 硬件 | 缺陷 |
|---|---|
| **GPU Adreno 512** | 能工作，但**只在竖屏**；横屏强制 llvmpipe（绕 GPU 硬挂死）。`/dev/dri/renderD128` 存在 |
| **电池** | 缺 `health` / `cycle_count` / `charge_counter` 三个字段 |
| **充电器** | `usb_type` 识别为 `Unknown [SDP] DCP CDP`，`current_max` 常在 500mA 而非 1.5A |
| **扬声器** | 数字链路全通，无声。**已证明改 DTB 无效**，需改驱动源码 |
| **耳机检测** | `Xiaomi Mi Pad 4 Headset Jack` (event5) 存在，未测插拔 |
| **环境光 CM3232** | DSP 拒绝 buffering `0x501`（DSP 有驱动，缺 registry JSON） |

### ❌ 完全不可用（3 项）

| 硬件 | 状态 | 证据 |
|---|---|---|
| **摄像头** | **无驱动** | `/dev/video0-1` 是 `qcom-venus-decoder/encoder`（编解码器，不是摄像头）；DT 里无 camera/cci/csiphy 节点；无 camss 模块 |
| **GPS** | **无驱动** | 无 `/dev/gnss*`；DT 里无 gnss 节点 |
| ~~传感器（5 个芯片）~~ | **已撤回，见上方"完全可用"** | 原判断错误 |

### ❓ 待确认（3 项）

| 硬件 | 疑问 |
|---|---|
| **振动马达** | `gpio-keys` 无 vibrator，`/sys/class/leds` 无 haptic，DT 里搜不到 —— **可能这颗平板根本没有马达** |
| **SD 卡槽** | `mmc1:0001 DV6DMB` 是 eMMC；`mmc2` 存在但无设备。**需插卡实测** |
| **USB OTG host** | 无 `/sys/class/usb_role/*` 接口；`lsusb` 无输出。**需接 U 盘实测** |

---

## 四、按"办公电脑"目标重排优先级

### P0 — 阻塞办公（必须解决）

| 项 | 现状 | 下一步 |
|---|---|---|
| **扬声器** | 无声 | **改 `snd-soc-sdm660-int` 源码 + 重编内核**（已证明改 DTB 无效） |
| **自动旋转** | ⚠️ 数据已有，只差 daemon | **写一个监听 orientation 的 daemon**（不用编内核，见 09 §5.3） |
| **摄像头** | 无驱动 | 上游 mainline 是否有 camss 支持？需查；可能只能放弃 |
| **蓝牙键鼠** | 未配对 | 主机侧就绪，需用户操作 |

### P1 — 明显影响体验

| 项 | 现状 | 下一步 |
|---|---|---|
| **自动亮度** | DSP 拒绝 0x501 | **补 `cm3232.json` 到 DSP registry**（不用编内核，见 09 §6 改动 3） |
| **智能保护套** | 硬件可用，无 daemon | **监听 `event3` 的 SW_LID**（不用编内核，见 09 §4.3） |
| **休眠** | 死锁 | 内核 `mdss_runtime_suspend` bug |
| **GPU 加速（横屏）** | 走 llvmpipe | 已知 `xrandr --rotate` + glamor 会硬挂死，需另寻方案 |

### P2 — 锦上添花

| 项 | 现状 |
|---|---|
| 电池 health / cycle_count | 缺字段，影响电池健康监测 |
| 快充识别（DCP 1.5A） | 常退回 SDP 500mA |
| SD 卡槽 | 待测 |
| USB OTG | 待测 |

---

## 五、办公软件生态缺口（尚未评估）

目前**未确认**已安装什么。下次会话需要盘点：
- [ ] 浏览器（Firefox / Chromium）
- [ ] 办公套件（LibreOffice Writer/Calc/Impress）
- [ ] PDF 阅读器
- [ ] 邮件客户端
- [ ] 输入法词库质量
- [ ] 打印/扫描支持
- [ ] 文件同步（Nextcloud 等）
- [ ] 视频会议（摄像头不可用则是硬伤）

---

## 六、关键命令备忘

```bash
# 传感器全清单（最重要的一条）
echo '<SUDO_PASSWORD>' | sudo -S dmesg | grep qcom_smgr

# 传感器正确的检查法（2026-10-24 更正）
for i in 2 3 4 5; do
  d=/sys/bus/iio/devices/iio:device$i
  echo "$(cat $d/name): scan=$(ls $d/scan_elements | wc -l) 通道"
done
# 真读数据（buffer 型设备必须读字符设备，不是 sysfs）
echo 1 > /sys/bus/iio/devices/iio:device2/scan_elements/in_accel_x_en
echo 1 > /sys/bus/iio/devices/iio:device2/buffer/enable
dd if=/dev/iio:device2 bs=1 count=512 2>/dev/null | od -An -tx1 | head -4

# 无驱动设备列表
for d in /sys/bus/platform/devices/*; do
  [ -e "$d/driver" ] || basename "$d"
done

# 摄像头真相（video0-1 是 venus 不是摄像头）
cat /sys/class/video4linux/video0/name

# 霍尔传感器（正确路径是 gpio-keys，不是 SMGR）
python3 -c "import fcntl,struct,os; fd=os.open('/dev/input/event3',os.O_RDONLY); b=bytearray(8); fcntl.ioctl(fd,0x8008451b,b,True); print('SW=0x%x'%struct.unpack('<Q',bytes(b))[0])"

# DSP 传感器驱动验尸（决定改内核还是改 registry）
for f in /run/msm-firmware-loader/target/adsp.b*; do
  strings -a "$f" | grep -oE 'sns_dd_[a-z0-9_]+' | sed "s|^|$(basename $f) |"
done | sort -u

# GPU 设备
ls /dev/dri/    # card1 + renderD128
```

---

## 七、这次审计纠正了什么

**我之前对用户说"只剩三个硬件问题"，这是错的。** 因为我只盯着已知的扬声器，没有系统普查。

| 我之前说 | 实际 |
|---|---|
| 只差扬声器/休眠/蓝牙 | **还有传感器全废、摄像头无驱动、GPS 无驱动、霍尔无驱动** |
| 麦克风可用 | ✓ 正确 |
| 触屏可用 | ✓ 正确 |
| 电池显示可用 | ✓ 正确，但底层缺 health/cycles 字段 |

**教训：接手一个平台移植项目，第一步必须做全硬件普查，而不是从报错日志倒推。**

---

## 八、第二次纠正（2026-10-24 09:40）：从"9 项"里撤回 2 项误判

**本文说"传感器全废、霍尔无驱动"，这也是错的。**
错在只看顶层 sysfs、没读字符设备、没验尸固件。

| 本文说 | 实测 |
|---|---|
| `scan_elements` 为空 | ❌ 12/6 个通道都在 |
| 传感器读不到数据 | ❌ accel `9.81 m/s²`、gyro `0.02 rad/s`、mag `117 µT` 全部实测 |
| 霍尔"无驱动绑定"= 不可用 | ⚠️ SMGR 路确实不通，但 **gpio-keys 的 SW_LID 一直可用** |
| ALX 缺 `sns.reg-xiaomi,clover-plus` 固件 | ⚠️ 不是缺固件，是**缺 cm3232 的 registry 条目**（DSP 驱动本身齐全） |

### 两次错误的共同根因

1. **第一次**：只看已知问题，没普查 → 漏了 6 项
2. **第二次**：普查了，但**取证方法错**（看 sysfs 顶层，没读 `/dev/*`）

### 最终教训（最重要）

> **"驱动加载了" ≠ "数据可用"，"sysfs 有属性" ≠ "通道存在"。**
>
> 判断 IIO 必须三步都过：
> 1. `ls scan_elements/` —— 有 `*_en` / `*_index` / `*_type`
> 2. `echo 1 > buffer/enable` —— 能写成功
> 3. `dd if=/dev/iio:deviceN` —— 能读出字节
>
> 判断"能不能修"，必须**验尸 DSP 固件**（有没有 `sns_dd_<chip>`），
> 否则会花几天写一个注定读不到数据的内核驱动。
>
> **霍尔就是活例子**：内核没有驱动、DSP 也没有驱动。
> 如果照原计划写内核 hall 驱动，结果是"绑定成功、数据永远不来"。
