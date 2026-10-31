# 小米平板4 Plus (clover-plus) Linux 移植 — 文档索引

> 最后整理：**2026-10-30 20:50**
> 系统：postmarketOS edge + 主线内核 `7.0.14-sdm660`（**r253**）
> 状态：**28 项硬件自检全通过**，指纹成像待攻

---

## 🚩 从这里开始

| 文档 | 说明 | 建议 |
|---|---|---|
| **[START-HERE.md](START-HERE.md)** | **新会话起点**（现状 / 环境 / 下一步 / 血泪教训）| ★★★ **先读这个** |
| **[HARDWARE-STATUS.md](HARDWARE-STATUS.md)** | 逐硬件状态总表 + 根因 + 踩坑清单 | ★★ 硬件全貌 |
| **[RESTORE-GUIDE.md](RESTORE-GUIDE.md)** | **刷机后恢复完整指南**（fastboot 逐步命令）| ★★ 救砖必读 |
| [RESUME-HERE.md](RESUME-HERE.md) | 126 节完整工作日志（最详细）| 查细节 |
| [HANDOVER.md](HANDOVER.md) | 环境、工具、构建流程 | 接手时读 |

---

## 📦 备份与救援（2026-10-30 刷 MoKee 前做的）

**三份副本，全部已验证：**

| 位置 | 内容 | 状态 |
|---|---|---|
| PC `backup/preflash/` | 27 文件 3.41 GB | ✅ |
| U 盘 `G:\pmos-preflash-20261030\` | 28 文件 3.42 GB | ✅ 26/26 MD5 与 PC 一致 |
| 平板 `/root/preflash-*/` | 已随刷机丢失 | ✗ |

**关键文件：**
```
persist.img          32 MB   🔴 设备唯一（指纹/传感器校准）
modemst1/2.img        4 MB   🔴 设备唯一（射频校准）
fsg.img fsc.img       2 MB   🔴 设备唯一
rootfs-full.tar.gz  2.9 GB   完整 pmOS 系统
vendor-content.tar.gz 167 MB 固件
rootfs-etc-home.tar.gz 153 MB 配置和脚本
lib-modules.tar.gz   13.4 MB 内核模块
boot.img（r253）recovery.img（TWRP）
xbl/abl/tz/hyp/rpm/pmic/devcfg/logo/splash/vbmeta
MD5SUMS  meta.txt  packages.txt
```

**还原关键**：`mkfs.ext4` **必须带 `-U 8def993b-42f5-4ba1-9813-c046e498fe22`**，
否则 boot 的 cmdline 找不到根分区。

旧还原包（备用）：
`backup/restore-20261029/`、`G:\pmos-restore-20261029\`、
`backup/restore-20261029/restore-rootfs.sh`、`tools/boot-r181.img`

---

## 🔧 各硬件专项记录

### 指纹 FPC1020（🔴 唯一未通关的硬件）
| 文档/文件 | 内容 |
|---|---|
| [START-HERE.md](START-HERE.md) | ★ 完整寄存器表、参数表、13 项已排除清单、`fpc-redrive-supply` 线索 |
| [RESUME-HERE.md](RESUME-HERE.md) §90-126 | 完整调查史 |
| `tools/fpc1020.c` | 驱动源码（r253，LO 参数）|
| `tools/0035-fpc1020-driver.patch` | 驱动补丁 |
| `artifacts/fpc_hal.so` | **厂商指纹 HAL**（140 KB，ARM64，通过 QSEECom 调 TA）|
| `artifacts/fpc_ta.elf` / `fpc_decomp.c`（VM `/tmp/`）| 厂商 TA 二进制 + 反编译 |
| `artifacts/fp_image.bin` | 采集到的图像样本 |
| `artifacts/rom/miui-boot.img` | 原始 Android 启动镜像（内含厂商 DTB）|

**当前进展**：采集通路已打通（11266 字节 = 64×176），但图像恒定 153/154/155，无脊线。

### USB / 充电 / TypeC（✅ 已通关）
| 补丁 | 作用 |
|---|---|
| **0085** | OTG buck-boost 使能（修复 OTG 完全不出电）|
| **0086** | OTG 电流限制 1.5 A（修复带载崩溃 5.06 V→0.02 V）|
| **0087** | 电池状态判断修复（充电时误报"Charging"但电流为负）|
| **0088** | TypeC CC 状态读取（自动 host/charge 切换）|

设备脚本：`pad_usb_autoswitch.sh`（CC 轮询自适应）、`pad_usb_mode.sh`（手动切换）

### 前摄 S5K5E8（🔴 未通）
| 文档 | 内容 |
|---|---|
| [FRONT-CAMERA.md](FRONT-CAMERA.md) / [FRONT-CAMERA-MEASURE.md](FRONT-CAMERA-MEASURE.md) | 早期测量 |
| [CAMERA-FINDINGS.md](CAMERA-FINDINGS.md) | 相机总调查（90 KB）|
| `artifacts/vendor-clover.dtb` / `vendor.dts` | **从 recovery 分区提取的厂商 DT**（权威参考）|

**卡点**：CCI master 1 总线无应答，所有 DT/供电/pinmux 与厂商一致，**需示波器测 MCLK**。

### 后摄 OV13855（✅ 可用）
[CAMERA-FINDINGS.md](CAMERA-FINDINGS.md) / [ANDROID-CAM-FINDINGS.md](ANDROID-CAM-FINDINGS.md) / [MIUI-CAMERA-EXPERIMENT.md](MIUI-CAMERA-EXPERIMENT.md)

### 传感器（✅ 全部可用）
[09-P0-1-SENSORS.md](09-P0-1-SENSORS.md) / [13-ALS-SUCCESS.md](13-ALS-SUCCESS.md) /
[14-AUTO-BRIGHTNESS.md](14-AUTO-BRIGHTNESS.md) / [15-ALS-SAMPLERATE.md](15-ALS-SAMPLERATE.md)

### venus 视频解码（⚠️ 部分）
[RESUME-HERE.md](RESUME-HERE.md) §70-89, §97 — 固件读 23 字节后停住，SESSION_INIT 超时

### 显示 / Xorg / XFCE（✅ 可用）
[06-xfce-experiment.md](06-xfce-experiment.md) / [07-xorg-xfce.md](07-xorg-xfce.md) /
[10-AUTOROTATE.md](10-AUTOROTATE.md) / [20-SPEAKER-TOUCH-DESKTOP.md](20-SPEAKER-TOUCH-DESKTOP.md)

### LTE 数据（🔴 未通）
SIM 识别、射频注册、信号测量都正常，**只缺 IPA 驱动**。
固件已备好：`/lib/firmware/ipa_fws.{mdt,b00..b07}`（9 文件 80 KB）

### 蓝牙音频（✅ 可用）
PulseAudio 3 模块 + 1 sink，需真实耳机验证 A2DP

---

## 📊 数据与审计

| 文档 | 内容 |
|---|---|
| [HARDWARE-DATA.md](HARDWARE-DATA.md) | 硬件原始数据（51 KB）|
| [08-HARDWARE-AUDIT.md](08-HARDWARE-AUDIT.md) | 硬件审计 |
| [17-ANDROID-VS-PMOS-HARDWARE.md](17-ANDROID-VS-PMOS-HARDWARE.md) | Android vs pmOS 对照 |
| [18-HARDWARE-COMPLETE.md](18-HARDWARE-COMPLETE.md) | 硬件完成度 |
| [DRIVER-GAP-ANALYSIS.md](DRIVER-GAP-ANALYSIS.md) | 驱动差距分析 |

---

## 🛠 构建与刷机

| 文档 | 内容 |
|---|---|
| [RESTORE-GUIDE.md](RESTORE-GUIDE.md) | ★ **恢复完整指南** |
| [04-build-log.md](04-build-log.md) | 构建日志 |
| [12-FLASH-ATTEMPT.md](12-FLASH-ATTEMPT.md) | 刷机尝试 |
| [16-FLASH-TO-MIUI.md](16-FLASH-TO-MIUI.md) | 刷回 MIUI 记录 |
| [19-PMOS-RESTORE.md](19-PMOS-RESTORE.md) | pmOS 还原记录 |
| [PATCHES.md](PATCHES.md) | 补丁清单 |

---

## 📜 历史/规划类（已被取代）

`00-GOAL.md` `01-plan.md` `NEXT-SESSION.md` `NEXT-STEPS.md` `MORNING.md`
`MORNING-BRIEF.md` `HANDOFF.md` `HANDOVER-TONIGHT.md` `OTHER-HARDWARE-PLAN.md`
`11-REGISTRY-EXPERIMENT.md`

---

## 🧰 工具（`tools/`）

### SSH / 文件传输
```
ssh_pad.py  put_pad.py  get_pad2.py ★  ssh_vm.py  scp_vm.py  get_vm.py  wait_pad.py
```
⚠️ `get_pad.py` 有 bug（paramiko 本地写入被拦），**用 `get_pad2.py`**
⚠️ `ssh_pad.py` 有 60 s 超时，长命令必须用 `systemd-run` 后台跑

### 构建与补丁
```
rebuild_driver_patch.py   use_lo_tables.py   vm_build.sh   flash_boot.sh
stream_restore.py         mk_otg_buckboost.py  mk_otg_current_patch.py
mk_fg_status_patch.py     mk_typec_status_patch.py
```

### 设备端脚本（源码在 tools/，部署到 `/usr/local/bin/`）
```
pad_selftest（28 项自检）        pad_imu  pad_gps  pad_als  pad_hall  pad_otg
pad_usb_autoswitch.sh  pad_usb_mode.sh
pad_fp_check  pad_fp_dump  pad_fp_regs  pad_fp_rows  pad_fp_sweep
pad_fp_probe  pad_fp_testpat  pad_fp_burst  pad_fp_status_test
pad_fp_diag_regs  pad_fp_install_cal  pad_fp_cal_abtest
pad_fp_rmw.sh（读-改-写序列）    pad_fp_monitor.sh（0xD4 监视）
pad_front_cam_check  pad_front_cam_bus  pad_cci_pinmux
pad_venus_status  pad_venus_decode_check
```

### Android / MoKee 侧
```
android_spi_snapshot.sh  android_grep_fp_log.sh  android_fp_inventory.sh
android_camera_probe.sh  android_camera_dt.sh  android_gps_probe.sh
```

---

## 🔑 关键事实速查

```
分区：boot=/dev/mmcblk1p12(64MB)   recovery=/dev/mmcblk1p51(64MB, TWRP)
      pmOS root=userdata(mmcbkl1p64)   UUID 8def993b-42f5-4ba1-9813-c046e498fe22
      vendor=/dev/mmcblk1p14(2GB)      persist 32MB（设备唯一）

pmOS 设备：   192.168.1.29 (WiFi) / 192.168.1.101 (千兆 USB 网卡，需插 hub)
              user / <SUDO_PASSWORD>    root 用 sudo（密码 <SUDO_PASSWORD>）

MoKee 设备：  adb（D:\APPS\platform-tools\adb.exe），序列号 27eec4d2，直接 root

构建机 VM：  192.168.1.200   user / <VM_PASSWORD>
             pmbootstrap 工作区：~/.local/var/pmbootstrap/
             内核源码：~/realsrc/linux-7.0.14-sdm660/
             TA 反编译：/tmp/fpc_decomp.c
             厂商驱动：/tmp/fpc1020_common.c  /tmp/fpc1020_regs.h

VM 里 REA：   export GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC
              rea analyze <elf>      （Windows 版不支持 ELF/ARM64）

代理：192.168.1.151:16514
```

---

## ⚠️ 血泪教训（绝对不要再犯）

1. **绝不**读 `/sys/kernel/debug/c1b7000.spi_dbg/*` —— 卡死平板
2. **绝不**在相机 i2c 总线 `new_device` —— 崩溃
3. **绝不**远程测试 suspend/resume
4. **绝不**卸载 `fpc1020` 模块
5. **绝不**热重载 `qcom_smbx`
6. **绝不**用 `/dev/mem` 读设备寄存器（曾 bus hang 需硬重启）
7. **绝不**在无人值守时刷机
