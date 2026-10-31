# 小米平板4 Plus (clover-plus) — 硬件移植状态总表

> 最后更新：**2026-10-30 20:50**
> 系统：postmarketOS edge + 主线内核 `7.0.14-sdm660`（**r253**）
> 设备：192.168.1.29（user/<SUDO_PASSWORD>）/ 192.168.1.101（千兆 USB 网卡）
> 构建机：192.168.1.200（user/<VM_PASSWORD>）
> ⚠️ **当前设备上跑的是 MoKee（用户刷入，已 root），不是 pmOS**

---

## 一、总览

```
sudo pad_selftest  →  28 passed / 0 failed / 0 skipped
systemctl --failed →  0 个失败单元
```

| 硬件 | 状态 | 证据 / 根因 |
|---|---|---|
| 屏幕 (NT51021) | ✅ 可用 | DRM connector connected |
| 触摸 (Goodix GT9xx) | ✅ 可用 | 多点触控正常 |
| WiFi (ath10k) | ✅ 可用 | 5GHz 5745MHz，-25dBm |
| **有线网络 (USB 网卡)** | ✅ 可用 | hub 上的 RTL8153，**1000Mb/s**，外网 0% 丢包 |
| 蓝牙 | ✅ 可用 | hci0 正常；HID 键鼠已配对过；扫描到 14 个设备 |
| 音频 (TAS2557 + WCD) | ✅ 可用 | `plughw:0,0` 播放正常 |
| **USB OTG host** | ✅ **已修复** | 补丁 **0085**（buck-boost）+ **0086**（1.5A 电流）；hub+键盘+网卡全部枚举 |
| **USB 键盘** | ✅ 可用 | 注册为 3 个输入设备 |
| **后摄 OV13855** | ✅ 可用 | 实拍 **16,558,080 字节** |
| 光线传感器 (ALS) | ✅ 可用 | 73 lx → 背光 139（闭环）|
| 霍尔传感器 | ✅ 可用 | `qcom-smgr-hall`，开合正常 |
| **电池 / 充电** | ✅ **已修复** | 补丁 **0087**（状态判断）；**自动自适应**：插充电器→充电，插设备→host |
| **TypeC CC 角色检测** | ✅ **已实现** | 补丁 **0088** 暴露 SMB2 的 TYPE_C_STATUS_1/2；`usb-autoswitch` 每 2 秒自动切 |
| GPU (Adreno 512) | ✅ 可用 | devfreq 19.2 MHz |
| **调制解调器 (mpss)** | ✅ 可用 | remoteproc running；`qmicli --dms-set-operating-mode=online` 后注册中国移动 |
| **蜂窝射频 / SIM** | ✅ 射频可用 / ❌ 不能长开 | 换卡后注册 **CMCC 460/0**，LTE **RSSI -62 dBm / RSRP -90 dBm / SNR 13.8 dB**；但联网约 3 分钟触发 IPA 断言崩溃并带崩 WiFi（见下行）。**只差 IPA 数据通路** |
| **GPS / GNSS** | ✅ 可用 | **`qmicli -d qrtr://0`（节点 0！）** `--loc-start` 成功；standalone 模式；定位需室外天空视野（10-31 复核） |
| **SIM** | ✅ 正常（10-31 换卡后） | 旧卡坏（`no-atr-received`）；新卡 `Card state: 'present'`，注册 **CMCC**，LTE RSSI **-62 dBm** |
| **蜂窝联网稳定性** | ❌ 不可长期在线 | modem 设 online 后约 3 分钟：`ipa_util.c:1089 IPA Assert` → MPSS 崩溃 → **连带 ath10k/wcn3990 固件崩溃，WiFi 掉线**（`ath10k_snoc: failed to enable wcn3990: -22`）。恢复：`modprobe -r ath10k_snoc && modprobe ath10k_snoc` 或重启。根因仍是缺 IPA 数据通路 |
| **蓝牙音频 (A2DP)** | ✅ 栈就绪 | PulseAudio 用户服务开机自启，3 个蓝牙模块，1 个 ALSA sink；只需配对耳机 |
| **加速度/陀螺/磁力** | ✅ 可用 | Z=-9.79 m/s² / +0.018 rad/s / +0.70/+0.14/+0.65 gauss |
| **venus 视频解码** | 🔧 核心通 | AXI 384 MHz、驱动绑定、`/dev/video7`；**会话初始化超时** |
| **指纹 FPC1020** | 🔧 **采集通路已通** | **11266 字节 = 64×176 完整帧**，但图像恒定 153/154/155 无脊线；成像/匹配在闭源 TA，见 §2.1 与 [29](29-FINGERPRINT-CEILING.md) |
| **前摄 S5K5E8** | ❌ 软硬件排查穷尽 | **硬件在 Android 下正常**；Linux 侧已试：reset 52/47、VANA 独立/共用、standby 脚、8 种延时、全地址扫描 —— 全部 `-6 ENXIO`；见 [26](26-FRONT-CAMERA-DIAGNOSIS.md) §19 |
| DisplayPort 输出 | ⚠️ 硬件支持 | DP 控制器 0xc990000 + PLL 0xc011000 存在；无 DT 节点、驱动未启用、无法测试 |
| suspend/resume | ⚠️ 未验证 | 此前两次"挂死"实为 venus panic |

图例：✅ 有实测证据可用　🔧 进行中　⚠️ 未验证　❌ 确认故障（目前无）

---

## 二、三个进行中项目的根因

### 2.1 指纹 FPC1020（HWID `0x0341`，芯片 revision 4）

**硬件是好的** —— 刷 MoKee 实测：
```
fpc_tee_identify: coverage: 92, quality: 56, score: 62
do_authenticate capture_status: 0, identify_status: 0 → onAuthenticated
```

#### 🎯 r253 的突破：采集通路终于打通

**改用 LO 参数表**（厂商在 `moduleID_gpio` 无效时默认选 LO，而厂商 DT 里确实没有这个 GPIO）：
```c
// fpc1020_setup_default_LO_a3a4（正确）
.adc_gain  = {8, 0, 1},          /* Dry, Wet, Normal */
.adc_shift = {4, 6, 11},
.pxl_ctrl  = {0x0f0a, 0x0f1f, 0x0f0B},
.capture_row_start = 19,
```
效果：
```
改之前: capture_now: no image (intr=0x00)   → 0 字节
改之后: capture_now: 11266 bytes            → 完整 64×176 图像！
```

#### ❌ 但仍未解决
```
图像:     恒定 153/154/155（64×176 = 11264 字节，无脊线纹理）
0xD4:     手指状态寄存器（FINGER_PRESENT_STATUS）恒为 00 00，按压也不变
校准码:   15 14 13 11（会小幅波动，说明 ADC 在工作，但不随手指变化）
```

#### 📋 完整寄存器表

| 地址 | 名称 | 宽 | 值/状态 |
|---|---|---|---|
| `0x14` | FPC_STATUS | RO 1B | |
| `0x1C` | READ_INTERRUPT_CLEAR | RO 1B | （曾误用作手指判据）|
| `0x40` | MISO_EDGE_RIS_EN | WO 1B | |
| `0x4C` | IMG_SMPL_SETUP | RW 3B | |
| `0x54` | IMG_CAPT_SIZE | RW 4B | **0x4000B000** |
| `0x5C` | IMAGE_SETUP | RW 1B | 0x0B |
| `0x68` | SAMPLE_PX_DLY | RW 8B | |
| `0x8C` | FINGER_DRIVE_CONF | RW 1B | 0x02 |
| `0x90` | FINGER_DRIVE_DLY | RW 1B | 0x09 |
| `0x94` | OSC_TRIM | RW 2B | 0x1a07 |
| `0x9C` | ADC_SETUP | RW 5B | |
| `0xA0` | ADC_SHIFT_GAIN | RW 2B | (shift<<8)\|gain |
| `0xA8` | PXL_CTRL | RW 2B | |
| **`0xD4`** | **FINGER_PRESENT_STATUS** | **RO 2B** | **真正的手指状态** |
| `0xD8` | 阈值块 | RW **10B** | 读-改-写 |
| `0xDC` | 配置块 | RW **7B** | 读-改-写 |
| `0xEC` | 配置块 | RW 5B | |
| `0xFC` | HWID | RO 2B | 0x0341 |

#### 已排除的 13 项
① GPIO 中断 ② `0x1C` bit0 判据 ③ 轮询 FINGER_PRESENT_QUERY
④ AVDD 供电（`gpio98 : out high` ✓）⑤ VDDIO（`gpio92 : out high` ✓）⑥ RESET（`gpio108 : out high` ✓）
⑦ 几何参数（已修正）⑧ SPI 读写（`0x54` 正确回读）⑨ 命令集（完整）
⑩ 校准（64/64 samples）⑪ 采集路径（有数据时出 11266 字节）
⑫ ADC 配置寄存器 ⑬ 手指检测阈值寄存器

#### 🎯🎯🎯 最新线索（MoKee adb 侦察，2026-10-30）

```
/sys/firmware/devicetree/base/soc/ssphy@c010000/fpc-redrive-supply
```

**厂商 DT 里指纹的供电挂在 USB 3.0 SS PHY 的 `redrive` 稳压器下面** ——
不是我们一直在操作的那两个 GPIO（AVDD=98 / VDDIO=92）！
**这极可能是 pmOS 下指纹不工作的根因。**

另外 MoKee 的 fpc1020 是 **platform driver**（`/sys/bus/platform/drivers/fpc1020/soc:fpc1020`），
不是 SPI 设备，SPI 传输由驱动内部直接操作 `c1b7000.spi`（spi7）。

#### 下一步
1. **确认 `fpc-redrive-supply` 在 pmOS DT 里存不存在**（大概率缺失）
2. 如果缺 → 加进 DT，重编译测试
3. 用 `c1b7000.spi_dbg`（debugfs，**只能在 MoKee 上用，pmOS 上会卡死**）对比 SPI 通信

### 2.2 前摄 S5K5E8

**Android 上 probe 成功**（`s5k5e8 probe succeeded`）→ 硬件存在。

**已修正**：补上了 AVDD 2.8 V（GPIO 49）—— 之前完全没定义，传感器无供电。
VDIG 1.8 V 由补丁 0039 的 `cam_front_dvdd_1v8`（PM660L GPIO 3）负责。

**当前失败点**：CCI master 1 总线上**扫不到任何设备**（master 0 上后摄 0x36 + EEPROM 0x50 都正常）。

**DT 已核对与厂商一致**：cci-master=1、MCLK GPIO33、RESET GPIO52、VANA GPIO49、
VDIG PM660L GPIO3、`spi-max-frequency` 无关（走 CCI）。

**下一步**：查 CCI master 1 的 SDA 线选择、上电时序。

### 2.3 venus 视频解码

**已修正（真实主线 bug）**：`mmcc-sdm660.c` 里 `video_axi_clk` 和
`throttle_video_axi_clk` **没有 `.parent_hws`** → 速率恒为 0 → 固件读不到 DDR。
补丁 0080 修好后：
```
video_axi_clk  384000000   （之前是 0）
q0 命令队列 rd=23 wr=23    （之前 rd=0 wr=3，固件从不读）
```

**已排除**：`0073`（HFI v4 ops）—— 会因缺 OPP 表而 **panic 并导致启动循环**，绝不能再加。

**当前失败点**：`HFI_CMD_SESSION_INIT` 固件不回复（-110 超时）。

---

## 三、踩坑清单（17 条，血泪教训）

1. 远程测试 suspend 会挂死设备 —— 无人值守时绝不测试
2. PowerShell 长命令拼 SSH 必坏 —— 一律写 `.sh`/`.py` 文件 + 转义 CRLF
3. `sh -c` 里嵌套 `grep -iE "a|b"` 会断 —— 写脚本文件
4. 补丁 hunk 头行数必须与实际增删行数一致，否则 DTS 语法错误
5. `ccache: Could not find compiler` 是**良性**的，真正错误在 log.txt 更下方
6. 重复的 OTG 补丁（0074）会冲突 —— 0010 已覆盖
7. ALS 重命名（0075）会破坏 `tablet-autobright` —— 已回退
8. 相机 0048（`port@2`）会导致问题 —— 不要加回来
9. Windows 版 REA 不支持 ELF/ARM —— 必须用 VM 上的 REA
10. 内核 7.0+ 允许混合声明，但函数开头用未声明变量仍报错
11. **本机自动挂起不可靠** —— 长时调试前 `systemctl mask sleep.target suspend.target`
12. **换内核模块前必须备份旧模块**（`cp x.ko.zst x.ko.zst.bak`）
13. **venus 的 v4 PM ops（补丁 0073）会 panic** —— 缺 OPP 表，会导致启动循环
14. **TWRP 就在 recovery 分区里** —— `fastboot reboot recovery`，
    `adb shell` 直接是 root，可当普通 Linux 修 rootfs
15. **pstore 有上次启动的完整内核日志** —— `/sys/fs/pstore/console-ramoops-0`，
    从 TWRP 读，是排查"起不来"最快的路径
16. **绝不在运行时读 `/sys/kernel/debug/c1b7000.spi_dbg/` 的 QUP 寄存器** ——
    会干扰 TA 的 SPI 通信，指纹立即失效（重启可恢复）
17. **`mkfs.ext4` 会生成新 UUID**，而 boot cmdline 写死
    `pmos_root_uuid=8def993b-...` → 还原时必须 `mkfs.ext4 -U <原UUID>`

---

## 四、关键数据速查

### 4.1 分区与 UUID
```
boot      = /dev/mmcblk1p12 (64 MB)      TWRP: mmcblk0p12
recovery  = /dev/mmcblk1p51 (64 MB)      里面是 TWRP
pmOS root = userdata (mmcblk1p64)
            UUID 8def993b-42f5-4ba1-9813-c046e498fe22
```

### 4.2 还原包（本地 + U 盘，md5 已核）
```
boot-64MB-r220.img              64.0 MB   0ee0601782d36e260c57c26d4b13d998
pmos-rootfs-20261029.tar.zst  1684.4 MB  debea5727244138591061685af43472e
```
本地：`mipad4plus/backup/restore-20261029/`　U 盘：`G:\pmos-restore-20261029\`

### 4.3 构建流程
```powershell
# 改 tools/fpc1020.c 等 → 重建补丁 → 推 pmaports → 递增 pkgrel → 构建
python tools\rebuild_driver_patch.py
python tools\scp_vm.py tools\0035-fpc1020-driver.patch <pmaports>/0035-fpc1020-driver.patch
python tools\ssh_vm.py 'sed -i "s/^pkgrel=N/pkgrel=N+1/" <APKBUILD>; pmbootstrap checksum ... && pmbootstrap build ... --force'
python tools\get_vm.py <apk> tools\linux-rNNN.apk
python tools\put_pad.py tools/linux-rNNN.apk /tmp/
# 设备上：sudo apk add --allow-untrusted /tmp/linux-rNNN.apk（会自动 boot-deploy）
```

### 4.4 设备上的脚本
`/usr/local/bin/`：`pad_selftest` `pad_fp_check` `pad_fp_dump` `pad_fp_regs`
`pad_fp_rows` `pad_fp_sweep` `pad_fp_probe` `pad_fp_burst` `pad_fp_status_test`
`pad_fp_diag_regs` `pad_front_cam_check` `pad_front_cam_bus` `pad_cci_pinmux`
`pad_venus_status` `pad_venus_decode_check` `pad_als` `pad_hall` `pad_otg`

### 4.5 VM 上的 REA（重要工具）
```sh
export GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC
rea analyze <elf>
rea function <elf> --procedure FUN_xxxx --format json --filter-output normalized_result.pseudocode
rea search <elf> --pattern xxx --kind procedures
rea xrefs <elf> 0x地址 --format json --filter-output normalized_result
```
厂商源码在 VM 的 `/tmp/`：`fpc1020_regs.h` `fpc1020_common.c` `fpc1020_capture.c`
`fp_hal.so`（Android HAL）`vendor.dts`（厂商设备树，从 recovery 分区提取）

---

## 五、文档索引

| 文件 | 内容 |
|---|---|
| `HARDWARE-STATUS.md` | **本文件** —— 逐硬件状态 + 根因 + 踩坑清单 |
| `HANDOVER.md` | 总览：环境、工具、工作流 |
| `RESUME-HERE.md` | 100 节详细工作日志（最完整） |
| `backup/work-*.zip` | 每轮工作快照（含源码、补丁、boot 镜像）|
| `backup/restore-20261029/` | 完整还原包 + README + 还原脚本 |
