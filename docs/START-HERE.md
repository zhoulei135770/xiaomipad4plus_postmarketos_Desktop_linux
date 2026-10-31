# 📌 新会话起点（2026-10-30 20:50）

> **读这个文件就够开始了。** 详细历史在 `RESUME-HERE.md`（126 节）。
> 📚 **找不到某份文档？看 [INDEX.md](INDEX.md)** —— 它区分了"当前有效"和"历史归档"。

---

## 一句话现状

小米平板4 Plus（clover-plus / SDM660）跑 postmarketOS 主线内核 **7.0.14-sdm660 r253**，
**28 项自检全通过**，USB OTG / 千兆网 / 蓝牙音频 / GPS / LTE 射频 / 充电自适应全部工作。

还差三件事，**性质完全不同**：

| 事项 | 状态 |
|---|---|
| **指纹成像** | 🔚 **已到天花板**：我们的采集和 Android 完全等价，但原始帧里没有图像信号，成像在闭源 TA 里（[29](29-FINGERPRINT-CEILING.md)）|
| **前摄** | 🎯 **就差一步**：根因是两个补丁（0032/0048）没进构建，接回去重编即可（[26](26-FRONT-CAMERA-DIAGNOSIS.md)）|
| **CPU 调频** | 🟡 数据已齐（频率/电压表已解出），缺 `clk-cpu-660`/OSM 驱动（[23](23-PERF-THERMAL.md)）|

---

## ✅ 当前状态：设备已恢复回 pmOS（2026-10-28 21:42）

MoKee 侦察阶段结束，已按 [RESTORE-GUIDE.md](RESTORE-GUIDE.md) 第七节完整恢复：
**`pad_selftest` 28 passed / 0 failed / 0 skipped**，指纹 HWID 0x0341 应答，后摄出帧，
WiFi 5 GHz / modem QMI / GNSS / BT / OTG 全通。

### 怎么连
```powershell
ssh user@192.168.1.29     # 密码 <SUDO_PASSWORD>，pmOS，sudo 同密码
```
千兆 USB 网卡：`192.168.1.101`（需插 hub）。

### 📦 MoKee 阶段的全部战果（都在 `artifacts/mokee-20261028/`）

| 产物 | 内容 |
|---|---|
| `fdt.dtb` | 运行中的完整厂商 DT（341 767 B） |
| `c2/` | dmesg / kallsyms / config.gz / 78 个 regulator / fpc sysfs / DT hex / logcat |
| `fpc-blobs/` | `fpctzapp` TA 全 8 段 + 3 个 HAL so |
| `mokee-boot.img` | MoKee boot 分区 64 MiB |
| `hwdata/` | ACDB 音频校准、thermal-engine 配置、/persist 校准、CPU/GPU 频点 |
| `telephony.db` | CMCC 的 APN 表 |
| `cam-before/` `cam-after/` | 前摄开/关两态快照 |

---

## 🔴 现在最该做的事（按证据重排，见文末"下次开工建议顺序"）


### 🎯 已发现的重大线索（新会话从这里继续）

**1. 指纹的供电挂在一个意想不到的地方**
```
/sys/firmware/devicetree/base/soc/ssphy@c010000/fpc-redrive-supply
```
⇒ ~~这可能是 pmOS 下指纹不工作的根因~~ **已证伪（2026-10-28）**：

> 该属性挂在 `ssphy@c010000` 上，而这个节点在**厂商 DT 里就是 `status = "disabled"`**，
> 驱动从不 probe，属性从未被消费；它指向的 `pm660_l11` 是触摸/相机/DSI 共用的常开 1.8V 轨。
> pmOS 内核里也**没有任何代码读 `redrive`**。⇒ 加进 DT 不会有任何效果。
>
> 更关键的：厂商平台驱动 `fpc1020_platform_tee.c` **只 lookup reset/irq 三个 pinctrl 状态**，
> DT 里的 `fpc_avdd_active`(gpio98) / `fpc_vddio_active`(gpio92) **它根本不碰**，
> 而且**内核侧完全不做 SPI**（全部在 TEE 的 `fpctzapp` 里）。
> **详见 [21-FPC-POWER-FINDINGS.md](21-FPC-POWER-FINDINGS.md)。**

**2. 驱动是 platform driver，不是 SPI 设备**
```
/sys/bus/platform/drivers/fpc1020/soc:fpc1020
/sys/devices/soc/soc:fpc1020/
/sys/bus/spi/devices/   ← 空的！
```
⇒ MoKee 下驱动注册为 platform driver，SPI 传输由驱动内部直接操作 `c1b7000.spi`。

**3. SPI 控制器和 pmOS 一致**
```
spi7 -> ../../devices/soc/c1b7000.spi/spi_master/spi7
```

**4. 驱动和 HAL 都在跑**
```
irq/269-soc:fpc                                      ← 驱动的中断线程
android.hardware.biometrics.fingerprint@2.1-service  ← FPC HAL
com.qualcomm.qti.biometrics.fingerprint.service      ← QTI 服务
```

**5. 完整 DT 节点位置**
```
/sys/firmware/devicetree/base/soc/fpc1020/
  fpc,gpio_irq
  fpc,gpio_rst
/sys/firmware/devicetree/base/soc/pinctrl@03000000/
  fpc_avdd_active / fpc_avdd_suspend
  fpc_vddio_active / fpc_vddio_suspend
  fpc_spi_active
  fpc_reset_active / fpc_reset_reset
  fpc_irq_active
```

### 下一步该做的（2026-10-28 修订）
1. 回 pmOS 后跑 [21-FPC-POWER-FINDINGS.md](21-FPC-POWER-FINDINGS.md) 第 4 节的寄存器实验：
   **先补写 `0xA0=0x0B01` / `0xA8=0x0f0b`**（我们故意跳过、厂商参考驱动必写的两个寄存器），
   再把 `read_len` 改成 28728 抓图 —— 恒定 153/154/155 的最可能原因。
2. 若仍恒定 ⇒ 查 `0x14` 状态位 / `0xD4` finger-present / `0xFC` HWID（表可能选错）。
3. ❌ 不要再往 DT 加 `fpc-redrive-supply`；❌ 不要再纠结 GPIO 92/98 电平；
   ❌ 不要读 `regulator_summary` / `clk_summary`（会让 4.4 内核死锁）。
4. ~~用 `c1b7000.spi_dbg` 观察 MoKee 下真实的 SPI 通信~~ ⇒ **不可行**：SPI 在 TEE 里，
   内核侧没有报文可看。

---

## 恢复回 pmOS 的完整步骤

**文档：`RESTORE-GUIDE.md`**

备份三份（全部已验证）：
| 位置 | 内容 |
|---|---|
| PC `backup/preflash/` | 27 文件 3.41 GB，含完整 rootfs |
| U 盘 `G:\pmos-preflash-20261030\` | 28 文件 3.42 GB（26/26 MD5 与 PC 一致）|
| 平板 `/root/preflash-*/` | 已在刷机时丢失 |

关键文件：
```
persist.img 32MB        ← 设备唯一（指纹/传感器校准）
modemst1/2.img 4MB      ← 设备唯一（射频校准）
fsg.img fsc.img         ← 设备唯一
rootfs-full.tar.gz 2.9GB
vendor-content.tar.gz 167MB
rootfs-etc-home.tar.gz 153MB
boot.img（pmOS r253）  recovery.img（TWRP）
xbl/abl/tz/hyp/rpm/pmic/devcfg/logo/splash/vbmeta
```

---

## 硬件状态总表

### ✅ 完全可用（14 项）
| 硬件 | 验证 |
|---|---|
| 屏幕 + 触摸 | 自检 + 实拍 |
| **USB OTG host** | hub + USB 键盘 + 千兆网卡全部枚举（补丁 0085/0086/0088，**已收工**）|
| USB 键盘 | 3 个输入设备 |
| **有线千兆网** | 1000Mb/s，外网 0% 丢包 |
| **WiFi 5GHz** | 5745MHz |
| **蓝牙** | 扫描 14 设备，HID 键鼠可用 |
| **蓝牙音频 A2DP** | PulseAudio 3 模块 + 1 sink |
| **LTE 射频** | 注册中国移动 46000，B3 EARFCN 38950，RSSI -63dBm |
| SIM | present |
| **GPS** | QMI LOC standalone |
| **充电自适应** | TypeC CC 检测，自动切 host/charge |
| 后摄 | 拍照正常 |
| 加速度/陀螺/磁力 | Z 轴 -9.79 m/s² |
| ALS / 霍尔 / 电池 / GPU / modem / venus | 自检通过 |

**自检：28 passed / 0 failed / 0 skipped**

### 🔴 未通 / 未验证（按 2026-10-28 证据重排）

| 项目 | 卡点（已核实的结论） | 优先级 |
|---|---|---|
| **指纹成像** | **已查明不是驱动问题**：我们抓的原始帧和 Android 抓的**统计上完全一样**（min/max/spread 一致），但原始帧里**没有脊线信号**（逐像素标准差 0.75）—— 成像算法在闭源 TA 里。详见 [29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md) | ★ 已到天花板 |
| **温控 / CPU·GPU 调优** | **数据已齐**：从厂商 DTB 解出完整 CPU 频率/电压表（silver 8 档 / gold 7 档，见 [23-PERF-THERMAL.md](23-PERF-THERMAL.md) §10，DTS 片段 `patches/cpu-opp-tables.dtsi`）。剩下是驱动工程：主线**没有 `clk-cpu-660`**、**没有 CPR 稳压器**；GPU 647 MHz 是作者主动注释（缺 GPU regulator）| 🟡 数据齐、缺驱动 |
| **短信** | **未测**。SMS 走 QMI WMS，不过 IPA 也不过 IMS ⇒ 很可能本来就通 | ★ 先验证（5 分钟）|
| **4G 数据** | 需 IPA。设备上**没有独立 ipa_fws 固件**（打进了 modem 镜像）；主线只支持 IPA 4.x，SDM660 是 3.x | 大工程 |
| **前摄** | 🎯 **根因已找到**：`0032`（bit-bang i2c）和 `0048`（csiphy2 endpoint）两个补丁**存在于 pmaports 但没进 APKBUILD**，所以从来没被编译 —— 设备上 camss 只有 `port@0`、也没有 i2c-gpio 总线。用 `patches/enable-frontcam-patches.sh` 接回来重编即可（[26-FRONT-CAMERA-DIAGNOSIS.md](26-FRONT-CAMERA-DIAGNOSIS.md) §10）| ★ 高（有现成补丁）|
| **通话** | Android 上走 **VoLTE/SGs**（CS 域注册在 LTE）；pmOS 无 IMS 栈，只能 CS fallback，国内 2G 退网 | ⛔ 已知不可达 |
| DisplayPort | 无 DT 节点、驱动未启用 | 低 |


---

## 关键环境

> ⚠️ **本文档里所有 `python tools/...`、`sh patches/...` 之类的命令，
> 都要先 `cd mipad4plus`**（路径是相对这个目录的）。

### 构建机（VM）
```
192.168.1.200   user / <VM_PASSWORD>
~/.local/var/pmbootstrap/          ← pmbootstrap 工作区
~/.local/var/pmbootstrap/cache_git/pmaports/device/testing/linux-postmarketos-qcom-sdm660/
  APKBUILD (pkgrel=253), 0035-fpc1020-driver.patch, 0085~0088
~/realsrc/linux-7.0.14-sdm660/     ← 内核源码
/tmp/fpc_decomp.c                  ← TA 反编译（指纹核心逻辑）
/tmp/fpc1020_common.c              ← 厂商驱动源码
/tmp/fpc1020_regs.h                ← 寄存器表
```
**REA 在 VM 里可用**（Windows 版不支持 ELF/ARM64）：
```sh
export GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC
rea analyze /path/to/binary
```

### 平板（pmOS 时）
```
192.168.1.29   user / <SUDO_PASSWORD>     （WiFi；root 用 sudo，密码 <SUDO_PASSWORD>）
192.168.1.101                          （千兆 USB 网卡，需插 hub）
```

### 辅助脚本（`tools/`）
```
ssh_pad.py / put_pad.py / get_pad2.py   ← 注意用 get_pad2.py（get_pad.py 有 bug）
ssh_vm.py / scp_vm.py / get_vm.py
rebuild_driver_patch.py / use_lo_tables.py
```
⚠️ `ssh_pad.py` 有 60 秒超时，长命令必须用 `systemd-run` 后台跑。

---

## 本项目累计内核补丁（39 个）

| 编号 | 作用 |
|---|---|
| 0035 | **fpc1020 驱动**（指纹，我们写的）|
| **0085** | **OTG buck-boost 使能**（修复 USB OTG 不工作）|
| **0086** | **OTG 电流限制 1.5A**（修复带载崩溃）|
| **0087** | **电池状态判断修复**（充电时误报）|
| **0088** | **TypeC CC 状态读取**（自动 host/charge 切换）|
| 其它 | 屏幕/触摸/音频/相机/传感器/充电等 |

---

## 指纹：已知的全部技术细节

### 参数表（★ 我们原来用错，已修正为 LO）
```c
// fpc1020_setup_default_LO_a3a4（正确）
.adc_gain  = {8, 0, 1},          /* Dry, Wet, Normal */
.adc_shift = {4, 6, 11},
.pxl_ctrl  = {0x0f0a, 0x0f1f, 0x0f0B},
.capture_row_start = 19,
```
**依据**：厂商 `fpc1020_setup_defaults()` 在 `moduleID_gpio` 无效时默认选 LO，
而厂商 DT 里确实没有 moduleID GPIO。

### 寄存器表
| 地址 | 名称 | 宽 | 值/状态 |
|---|---|---|---|
| 0x14 | FPC_STATUS | RO 1B | |
| 0x1C | READ_INTERRUPT_CLEAR | RO 1B | （我们曾误用作手指判据）|
| 0x40 | MISO_EDGE_RIS_EN | WO 1B | |
| 0x4C | IMG_SMPL_SETUP | RW 3B | |
| 0x54 | IMG_CAPT_SIZE | RW 4B | **0x4000B000**（= 0x00B00040，**已在 TA 镜像里直接找到**，见 [25](25-TA-REVERSE-ENGINEERING.md) §12）|
| 0x5C | IMAGE_SETUP | RW 1B | 0x0B |
| 0x68 | SAMPLE_PX_DLY | RW 8B | |
| 0x8C | FINGER_DRIVE_CONF | RW 1B | 0x02 |
| 0x90 | FINGER_DRIVE_DLY | RW 1B | 0x09 |
| 0x94 | OSC_TRIM | RW 2B | 0x1a07 |
| 0x9C | ADC_SETUP | RW 5B | |
| 0xA0 | ADC_SHIFT_GAIN | RW 2B | (shift<<8)\|gain |
| 0xA8 | PXL_CTRL | RW 2B | |
| **0xD4** | **FINGER_PRESENT_STATUS** | **RO 2B** | **真正的手指状态！** |
| 0xD8 | 阈值块 | RW **10B** | 读-改-写 |
| 0xDC | 配置块 | RW **7B** | 读-改-写 |
| 0xEC | 配置块 | RW 5B | |
| 0xFC | HWID | RO 2B | 0x0341 |

### 已排除的 13 项
① GPIO 中断 ② 0x1C bit0 判据 ③ 轮询 FINGER_PRESENT_QUERY
④ AVDD 供电（gpio98 out high ✓）⑤ VDDIO（gpio92 out high ✓）⑥ RESET（gpio108 out high ✓）
⑦ 几何参数（已修正）⑧ SPI 读写（0x54 能正确回读）⑨ 命令集（完整）
⑩ 校准（64/64 samples）⑪ 采集路径（有数据时出 11266 字节）
⑫ ADC 配置寄存器 ⑬ 手指检测阈值寄存器

### 决定性现象
```
无手指:  calibration codes 15 14 13 11    capture_now: no image (intr=0x00)
有手指:  calibration codes 15 14 13 11    capture_now: no image (intr=0x00)
图像:    恒定 153/154/155（64×176 = 11264 字节，无脊线）
```

**2026-10-29 定性（重要）**：这**不是驱动没调好**。
我们抓的原始帧和 Android 抓的统计上完全等价（水平相关 0.81 / 垂直 0.02），
原始帧里没有二维结构；而 0x54/0x5C 等寄存器值已在 TA 镜像里验证过与我们一致。
⇒ **成像逻辑在闭源 TA 里，内核驱动这条路拿不到图像。**
详见 [29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md) 和 [25](25-TA-REVERSE-ENGINEERING.md) §12。

> 📋 TA 寄存器表的**未完成部分**（条目格式、消费者代码）整理在
> [30-TA-TABLE-HANDOFF.md](30-TA-TABLE-HANDOFF.md)，下次要接着挖就看它。

---

## ⚠️ 血泪教训（绝对不要再犯）

1. **绝不**读 `/sys/kernel/debug/c1b7000.spi_dbg/*` —— 会卡死平板
2. **绝不**在相机 i2c 总线上 `new_device` —— 会崩溃
3. **绝不**远程测试 suspend/resume
4. **绝不**卸载 `fpc1020` 模块
5. **绝不**热重载 `qcom_smbx`
6. **绝不**用 `/dev/mem` 读设备寄存器（曾导致 bus hang 需硬重启）
7. **绝不**在无人值守时刷机
8. `get_pad.py` 有 bug（paramiko 本地写入被拦）→ **用 `get_pad2.py`**
9. **绝不**在 4.4 内核上读 `/sys/kernel/debug/regulator/regulator_summary` 或 `clk_summary`
   —— 2026-10-28 实测直接死锁，只能长按电源 15 秒强制重启（想拿 regulator 状态请读
   `/sys/class/regulator/regulator.*/{name,state,num_users,microvolts}`，安全）
10. **清理 chroot 前必须先查 bind mount**（2026-10-29 事故）
    `rm -rf ~/.local/var/pmbootstrap/chroot_native` 会**删掉真实文件** ——
    `pmaports`、`packages` 等都 bind mount 在 `chroot_native/mnt/` 下。
    正确做法：用 `pmbootstrap zap -n`（会自己先 umount），
    或先 `umount -R chroot_native` 再删。
    本次事故导致定制 APKBUILD（pkgrel 253）+ 约 72 个补丁丢失，
    详见 [31-INCIDENT-PMAPORTS-LOST.md](31-INCIDENT-PMAPORTS-LOST.md)
11. **绝不**用伪造的 src/dst 创建 rpmsg 端点（2026-10-29 07:40 实测）
    `python3 rpmsg_drain.py drain DIAG 0 0` 会让整个系统死锁 ——
    黑屏、ping 不通、只能长按电源 15 秒强重启。
    rpmsg/glink 的端点地址必须来自**已存在的通道**（`/sys/bus/rpmsg/devices/*/{src,dst}`），
    不能猜。而且 `rpmsg_ctrl` 的 ioctl 一旦阻塞就是内核级 hang。
    **要做 DIAG 实验请改用 QMI 或真正的 diag 驱动，别碰 rpmsg_ctrl。**

---

## 下次开工建议顺序（2026-10-28 重写）

1. **确认设备状态**：`adb devices` / `ssh user@192.168.1.29`
2. **短信**：`mmcli -m 0 --messaging-create-sms=...` —— 5 分钟，很可能本来就通
3. **温控 + OPP**：照 [23-PERF-THERMAL.md](23-PERF-THERMAL.md) 的表补 DT
   （CPU OPP 两簇、GPU 补 266/647、thermal-zones + cooling-device）
4. **指纹**：跑 [scripts/fpc_regtest.sh](scripts/fpc_regtest.sh)（免重编），
   按 [21-FPC-POWER-FINDINGS.md](21-FPC-POWER-FINDINGS.md) §4 判读
5. **前摄**：先挖 `libmmcamera_s5k5e8.so` 的 init 表，再等 ISPIF
6. ❌ **不要再**：查 `fpc-redrive-supply`、纠结 GPIO92/98、读 `spi_dbg` /
   `regulator_summary` / `clk_summary`、试图在 Android 侧抓 SPI

---

## 🌙 夜间自主工作记录（2026-10-29 00:00–00:45）

用户睡觉期间，在**不依赖手指输入**的前提下做了三件事：

### 1. 指纹：TA 反编译环境彻底打通（重大）

- 发现 **TA 是 32 位 ARM**（不是 aarch64）→ 换 `--architecture arm` 后从 1 个函数变成 **1513 个**
- 构造了**多段 ELF**（`tools/ta_elf.py`），把 b02/b03/b04/b05/b07 全部装进 Ghidra → 字符串 xref 全部可解析
- 挖出厂商完整 API 名表（`fpc_ta_capture_image` 等 40 个）
- **反编译出采集函数 `FUN_00045654`**，得到三条关键事实：
  1. 采集 = 单字节 `0xC0` + 等 IRQ `0x20`
  2. 读图 = 2 字节 `{0xC4, 0}` 再读 `行×列+2` 字节
  3. **图像从 `buf+2` 开始**（前 2 字节不是像素）→ 已做成驱动参数 `img_skip`（v10，已部署）
- 详见 [25-TA-REVERSE-ENGINEERING.md](25-TA-REVERSE-ENGINEERING.md)

### 2. 前摄：根因是**两个补丁没进构建**（夜里两次更正后的最终结论）

`0032`（bit-bang i2c）和 `0048`（前摄接进 camss）两个补丁文件在 pmaports 里，
但**不在 APKBUILD 的 source 列表**里 → 从来没被编译。

设备证据：`camss/ports/` 只有 `port@0`、DT 里没有 `i2c-gpio`、`i2cdetect` 扫 bus 4 全空。

```sh
# ✅ 补丁已经接进 APKBUILD（source + sha512sums 都改好并校验过），直接编译：
pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660
```

（供电轨早就被 `0039` 修好了 —— 我夜里一开始说"接在后摄供电轨上"是过时结论。）

详见 [26-FRONT-CAMERA-DIAGNOSIS.md](26-FRONT-CAMERA-DIAGNOSIS.md) §10

### 3. modem 开机自动上线（已装好并验证）

装了一个 systemd oneshot：

```
/usr/local/bin/modem-online.sh
/etc/systemd/system/modem-online.service   (enabled)
```

实测：`Mode: 'online'`、注册 `CMCC 460/0`、`LTE -62 dBm`。

卸载：`sudo sh patches/install-modem-online.sh --remove`

### 4. CPU/GPU 调优：修正了之前的两个错误结论

- CPU **确实完全没有 cpufreq**（固定频率跑），需要 OPP + 电压表（数据缺，不能猜）
- GPU 的 647/700/750 MHz **不是漏了，是作者主动注释掉的**（缺 GPU regulator，开高负载会挂）
- 详见 [23-PERF-THERMAL.md](23-PERF-THERMAL.md) §8

### 设备状态（夜间未做耗电实验）

```
指纹模块 v10（img_skip=2），参数默认，采集正常
CPU 未动、没有重启循环
```

---

## 📚 文档索引

| 文件 | 内容 |
|---|---|
| [START-HERE.md](START-HERE.md) | 本文，总状态与硬件清单 |
| [RESTORE-GUIDE.md](RESTORE-GUIDE.md) | Android/pmOS 互刷与备份恢复 |
| [21-FPC-POWER-FINDINGS.md](21-FPC-POWER-FINDINGS.md) | 指纹供电/协议调查全过程（§1–§17）|
| [22-LTE-CALL-SMS-OTG.md](22-LTE-CALL-SMS-OTG.md) | 4G / 通话 / 短信 / OTG，含 modem 上线命令 |
| [23-PERF-THERMAL.md](23-PERF-THERMAL.md) | CPU/GPU 频点、温控策略、ACDB 音频、传感器校准 |
| [24-FPC-NEXT-STEPS.md](24-FPC-NEXT-STEPS.md) | **指纹攻坚手册**：环境、编译、参数、实验计划 |
| [25-TA-REVERSE-ENGINEERING.md](25-TA-REVERSE-ENGINEERING.md) | **TA 反编译笔记**：环境搭建、API、采集调用链、寄存器表 |
| [26-FRONT-CAMERA-DIAGNOSIS.md](26-FRONT-CAMERA-DIAGNOSIS.md) | 前摄诊断与供电轨 BUG |
| [27-OVERNIGHT-REPORT.md](27-OVERNIGHT-REPORT.md) | 2026-10-29 夜间工作报告 |
| [28-AUDIO-ACDB.md](28-AUDIO-ACDB.md) | ACDB 音频校准分析、扬声器保护风险、chromatix 无用结论 |
| [29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md) | **指纹天花板分析**：原始帧无信号、成像在 TA 里、QSEECOM 路线评估 |

**工具 / 脚本**

| 路径 | 用途 |
|---|---|
| `tools/pad_run.py` | 在平板上跑脚本（自动 sudo）|
| `scripts/vm_build_v2.sh` | VM 上编指纹模块（改一个 .c → 3 分钟出 .ko）|
| `tools/ta_elf.py` | 把 TA 分段拼成可加载 ELF |
| `scripts/vm_elf_func.sh` 等 | TA 反编译/查引用/扫描 |
| `patches/enable-frontcam-patches.sh` | **把 0032/0048 接进 APKBUILD**（前摄修复的主入口）|
| `patches/fix-front-camera-rails.sh` | 前摄供电轨修复（⚠️ 已被 0039 补丁覆盖，仅存档）|
| `tools/fpc1020_v11.c` | 当前最好的驱动源码（参数可覆盖 PXL_CTRL/ADC 增益）|
