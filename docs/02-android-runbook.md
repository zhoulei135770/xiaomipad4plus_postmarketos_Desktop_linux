# Android 侧信息采集 Runbook（Mi Pad 4 Plus）

> 目的：在平板跑 Android 时，把"写驱动需要的事实"一次性抓全，避免反复刷机。
> 适用：MIUI / LineageOS / Pixel Experience 等任意 Android，**有 root 最好，无 root 也能拿到一半**。

---

## 0. 先分清：哪些东西"不需要平板"也能拿到

很多人以为必须先刷回 Android，其实一半的料在**线刷包**里就有：

| 需要的料 | 来源 | 需要平板吗 |
|---|---|---|
| `boot.img` / `dtbo.img` / `vbmeta.img` | **官方 fastboot 线刷包**（tgz 里的 `images/`） | ❌ 不需要 |
| `vendor.img` / `system.img` / `super.img` | 同上 | ❌ 不需要 |
| 面板时序、触控 IC、GPIO 配置 | 上面两个镜像解析 | ❌ 不需要 |
| **运行时真实生效的 DTB**（overlay 合并后） | 设备 `/proc/device-tree` | ✅ 需要 |
| **dmesg 启动日志**（驱动加载顺序、固件路径、错误） | 设备 | ✅ 需要 |
| 触控固件版本、input 设备名 | 设备 | ✅ 需要 |
| Wi-Fi 校准文件（`bdwlan.b*`、`WCNSS_qcom_wlan_nv.bin`） | 设备 `/vendor/firmware/` 或 `persist` | ✅ 需要（线刷包里不一定全） |
| 音频 mixer 实际路由 | 设备 `/vendor/etc/mixer_paths*.xml` | 部分可从 vendor.img 拿 |
| 传感器列表与型号 | 设备 `dumpsys sensorservice` | ✅ 需要 |

**结论**：先搞到线刷包（不用平板），再在 Android 上跑一次采集脚本（要平板），两批料合起来才完整。

---

## 1. 刷回 Android 前的准备

### 1.1 确认设备状态

```powershell
adb devices            # 有序列号 = 系统可连
adb shell getprop ro.product.device    # 期望 clover
adb shell getprop ro.build.version.release
fastboot devices       # 能进 bootloader 才有后路
```

### 1.2 备份（刷机前必做）

- 照片/文档：`adb pull /sdcard/DCIM`、`/sdcard/Documents`
- 微信/QQ 聊天记录：应用内迁移
- **当前 pmOS 的任何改动**（如果刷过）：`/boot`、`/etc`、自定义脚本
- 记录当前 Bootloader 状态：`fastboot getvar unlocked`、`fastboot getvar current-slot`

### 1.3 下载对应线刷包

- 关键词：`clover fastboot ROM`、`小米平板4Plus 线刷包`
- 认准 **codename = clover**（不是 cloverlte 单独包，Plus 与 8 寸共用 clover 代号，靠 DTBO 区分）
- 包内应有：`images/boot.img`、`dtbo.img`、`vbmeta.img`、`vendor.img`、`super.img`、`flash-all.bat`
- **别用来源不明的"精简版/优化版"**，DTB/DTBO 被改过就没参考价值了

### 1.4 ARB 检查（防变砖）

```powershell
fastboot getvar anti          # 有输出说明有防回滚
```
SDM660 的 clover 一般没有严格 ARB，但仍建议**版本号只升不降**。

---

## 2. 刷回 Android

### 方式 A：MiFlash（推荐给非开发者）

1. 装 MiFlash（需关闭驱动签名强制）
2. 关机 → **Power + Volume Down** 进 fastboot
3. MiFlash 选线刷包目录 → `flash_all.bat`（**不要** `flash_all_lock`，否则会重新上锁）
4. 等待自动重启，首次开机 5–10 分钟

### 方式 B：fastboot 手动

```powershell
fastboot flash boot      images\boot.img
fastboot flash dtbo      images\dtbo.img
fastboot flash vbmeta    images\vbmeta.img --disable-verity --disable-verification
fastboot flash vendor    images\vendor.img
fastboot flash super     images\super.img      # 若包里有
fastboot erase userdata                          # 会清数据
fastboot reboot
```

> 用 `--disable-verity` 是因为后面要 root 采集；刷完 MIUI 后可用 Magisk 打 root。

### 2.1 开 root（采集阶段需要）

任选其一：

- **Magisk**：提取 `boot.img` → 手机端 Magisk 修补 → `fastboot flash boot magisk_patched.img`
- **KernelSU**（若内核支持）
- **LineageOS 官方 root**（`adb root` 直接可用，最省事）

验证：

```powershell
adb shell su -c id     # 期望 uid=0
```

---

## 3. 采集内容清单（按"用途"分组）

### 3.1 系统与分区（5 分钟）

| 文件 | 命令 | 用途 |
|---|---|---|
| `props.txt` | `getprop` | 机型/版本/分区指纹 |
| `version.txt` | `cat /proc/version; uname -a` | 内核版本、编译配置线索 |
| `partitions.txt` | `ls -l /dev/block/by-name`、`cat /proc/partitions` | 分区布局，决定 dump 哪些 |
| `cmdline.txt` | `cat /proc/cmdline` | 启动参数、`androidboot.*` |

### 3.2 设备树（最关键）

```powershell
adb shell "su -c 'tar -cf - /proc/device-tree 2>/dev/null'" > devicetree.tar
```

- 这是**运行时合并后**的 DTB（含 dtbo overlay），比线刷包里的原始 dtbo 更真实
- 重点节点：
  - `/soc/mdss@c901000/dsi@c901000/panel@0` → 面板时序
  - `/soc/i2c@c175000/*` → 触控 IC
  - `/soc/slim@c140000` / `wcd934x` → 音频 codec
  - `/soc/usb@a600000` → Type-C / role switch

### 3.3 显示与触控

| 文件 | 命令 |
|---|---|
| `dmesg.txt` | `su -c dmesg`（**最重要**） |
| `input_devices.txt` | `cat /proc/bus/input/devices` |
| `getevent.txt` | `getevent -pl` |
| `input_names.txt` | `for d in /sys/class/input/input*; do echo "$d: $(cat $d/name)"; done` |
| `i2c.txt` | `for d in /sys/bus/i2c/devices/*; do echo "$d: $(cat $d/name 2>/dev/null)"; done` |
| `backlight.txt` | `cat /sys/class/backlight/*/max_brightness`、`brightness` |
| `drm_modes.txt` | `cat /sys/class/drm/card0-*/modes` |

### 3.4 音频

| 文件 | 命令/路径 |
|---|---|
| `mixer_paths.xml` | `/vendor/etc/mixer_paths*.xml` |
| `audio_policy.xml` | `/vendor/etc/audio_policy_configuration.xml` |
| `tinymix.txt` | `su -c tinymix`（若存在） |
| `dumpsys_audio.txt` | `dumpsys audio` |

### 3.5 Wi-Fi / 蓝牙

| 文件 | 路径 |
|---|---|
| `firmware/` | `/vendor/firmware/`（`bdwlan.b*`、`WCNSS_qcom_wlan_nv.bin`、`wlan_mac.bin`） |
| `persist/` | `/persist/`（部分校准数据，需 root） |
| `wifi_cfg.txt` | `ls -l /vendor/etc/wifi/` + `cat /vendor/etc/wifi/WCNSS_qcom_cfg.ini` |
| `dumpsys_wifi.txt` | `dumpsys wifi` |

### 3.6 传感器 / 摄像头 / 电源

| 文件 | 命令 |
|---|---|
| `sensors.txt` | `dumpsys sensorservice` |
| `camera.txt` | `dumpsys media.camera` |
| `power.txt` | `for d in /sys/class/power_supply/*; do echo "$d"; cat $d/uevent; done` |
| `thermal.txt` | `for d in /sys/class/thermal/*; do echo "$d: $(cat $d/type 2>/dev/null)"; done` |

### 3.7 可选：分区 dump（需 root，体积大）

```powershell
adb shell "su -c 'dd if=/dev/block/by-name/boot of=/sdcard/boot.img'"
adb shell "su -c 'dd if=/dev/block/by-name/dtbo of=/sdcard/dtbo.img'"
adb pull /sdcard/boot.img D:\firmware\clover-dump\
adb pull /sdcard/dtbo.img D:\firmware\clover-dump\
```

- `boot`、`dtbo`、`vbmeta` 小（几十 MB），建议都 dump
- `vendor` 1–2 GB，可 dump
- `super` 可能 4 GB+，**只在线刷包里拿，别 dump**

---

## 4. 一键采集

已提供脚本：`collect-android.ps1`（同目录）

```powershell
cd C:\Users\zl\Documents\deepseek-harness\default-workspace
.\collect-android.ps1 -OutDir D:\firmware\clover-dump
```

脚本行为：

- 自动检测 `adb devices`，多于一台时让你选
- 逐项执行采集，**单步失败不中断**，最后打印"缺了什么"
- 有 root 走 `su -c`，无 root 自动降级并标注
- 输出目录结构：

```
D:\firmware\clover-dump\20261018-2310\
├── props.txt
├── version.txt
├── partitions.txt
├── dmesg.txt
├── devicetree.tar
├── input/
├── i2c.txt
├── display/
├── audio/
├── wifi/
├── sensors.txt
├── manifest.txt        ← 每项采集结果 OK/FAILED 及原因
└── _pull/              ← adb pull 下来的文件
```

---

## 5. 交付与分析顺序

采集完成后，把 `D:\firmware\clover-dump\<时间戳>\` 整个目录给我（或打 zip）。我会按这个顺序出结论：

1. **`devicetree.tar` + `dmesg.txt`** → 面板时序、触控 IC、codec、GPIO/regulator，生成"mainline DTS 对照表"
2. **`i2c.txt` + `input/`** → 确认触控驱动候选（goodix / focaltech / synaptics）
3. **`audio/`** → UCM 配置草案
4. **`wifi/`** → 固件与校准文件清单
5. **线刷包的 `dtbo.img`** → 用 REA 反查 overlay 里 Plus 专用的部分

产出物：

- `plus-hardware-facts.md`：事实清单（型号、地址、时序、GPIO）
- `mainline-dts-diff.md`：原厂 DT vs mainline DTS 的差异，指出要补的节点
- `driver-candidates.md`：每项硬件对应的内核驱动候选与工作量

---

## 6. 注意事项

- **不要在采集时开"开发者选项里的 USB 调试安全设置"以外的改动**
- `dmesg` 在 Android 10+ 需要 root；`adb shell dmesg` 会被 SELinux 拒
- `/vendor` 是只读挂载，采集不会破坏系统
- 采集本身**不影响保修状态**（root 会，但你已经解锁了）
- 如果平板已经是 pmOS，`/proc/device-tree` 和 `dmesg` 同样能抓，但那时拿到的是 mainline 的树，**参考价值不如 Android 侧**
