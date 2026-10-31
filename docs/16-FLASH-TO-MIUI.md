# 16 · 线刷回 MIUI 验证硬件 + 完整恢复方案

> 起因：扬声器和听筒**都没有声音**，但软件侧已逐层验证全对
> （ftrace 确认 AFE/ASM/DAPM 全启动，SPMI 寄存器确认 PA/LDO/时钟全开，
> 耳机有声证明整条数字链路正常）。
> 结论指向**模拟功放输出端或扬声器的硬件问题**，需要用 Android 交叉验证。

---

## 零、执行清单（按顺序）

```
[✅] 1. 备份关键分区到平板 /root/preflash-*/
[✅] 2. 下载备份到 PC artifacts/preflash/（192.8 MB）
[✅] 3. 采集全量硬件数据 evidence/hw-full-preflash-20261024.txt（611 行）
[ ] 4. 进 fastboot，刷 MIUI 线刷包
[ ] 5. 开机测试扬声器/听筒
[ ] 6. 刷回 pmOS + 恢复所有配置
[ ] 7. 验证一切正常
```

---

## 一、备份清单（已完成）

### 1.1 平板端位置

```
/root/preflash-20261024-174908/          647.7 MB
/tmp/pfbackup/                           可读副本（chown 给 user）
```

### 1.2 PC 端位置

```
mipad4plus/artifacts/preflash/           192.8 MB, 25 个文件
```

### 1.3 备份内容与用途

**Tier 1 — 设备唯一，丢失不可重建（最关键）**

| 分区 | 大小 | MD5(前16位) | 为什么重要 |
|---|---|---|---|
| `persist` | 32 MB | `afed307fbf0fac7c` | **Wi-Fi/BT MAC、传感器校准、触摸校准** |
| `modemst1` | 2 MB | `9b23c08b0be265c0` | 基带校准 |
| `modemst2` | 2 MB | `f14d657c7b9ec805` | 基带校准 |
| `fsg` | 2 MB | `8457f07c10853e34` | 基带配置 |
| `fsc` | 1 KB | `0f343b0931126a20` | 基带状态 |
| `devinfo` | 4 KB | `21c84eb65fa9af76` | 设备信息、解锁状态 |
| `sec` | 16 KB | `51c03529417aa23c` | 安全配置 |
| `keystore` | 512 KB | `59071590099d21dd` | 密钥库 |
| `frp` | 512 KB | `9b01db7baaba0743` | 工厂重置保护 |
| `misc` | 1 MB | `b4fc8e8255ec7eb9` | 启动标志、recovery 命令 |

**Tier 2 — 引导链（刷坏了能救砖）**

| 分区 | 大小 | MD5(前16位) |
|---|---|---|
| `boot` | 64 MB | `b48000b431df303a` |
| `recovery` | 64 MB | `6fddb7a1987fc077` |
| `vbmeta` | 64 KB | `a181dd745b0f14c1` |
| `splash` | 32.6 MB | `a10283b26e16659e` |
| `logo` | 32.6 MB | `e07ea8b3b97c082c` |
| `devcfg` | 1 MB | `2fb5d70b03998a51` |
| `rpm` | 512 KB | `2d2c5e9350319640` |
| `tz` | 4 MB | `9bf7f200c282f5b0` |
| `hyp` | 512 KB | `c2303a96e03aa0b4` |
| `xbl` | 3.5 MB | `2c2a3c8e187ddc57` |
| `abl` | 1 MB | `70b673e7989b73e9` |
| `pmic` | 512 KB | `c4937cd169b51486` |

**Tier 3 — 我们的软件成果**

| 文件 | 大小 | 内容 |
|---|---|---|
| `lib-modules.tar.gz` | 13.7 MB | 我们编译的 r3 内核模块（637 个） |
| `rootfs-etc-home.tar.gz` | 389 MB | `/etc` `/root` `/usr/local` `/var/lib/systemd` |
| `custom-tools/` | — | **所有 tablet-\* 工具、service、desktop、xorg.conf** |
| `kernel-patches/` | — | 内核补丁 diff |
| `meta.txt` | 14.7 KB | 分区表、挂载、cmdline、模块列表 |

### 1.4 `custom-tools/` 明细（这是最该保住的）

```
tablet-audio                    音频路由切换
tablet-autobright               自动亮度守护进程
tablet-autobright.service
tablet-battery-status
tablet-bt-pair
tablet-display-mode             显示模式切换
tablet-orientd                  自动旋转 + 合盖休眠
tablet-orientd.service
tablet-restore-snapshot
tablet-rotation-settings        屏幕旋转设置 GUI
tablet-rotation-settings.desktop
tablet-session-launcher(+2 备份)
tablet-sleep
00-keyboard.conf                键盘布局 cn
50-msm-soft.conf                llvmpipe 软渲染
tablet-config/                  /etc/tablet/ 内容（rotation.json、landscape 标志）
```

---

## 二、分区表（56 个分区，实测）

```
mmcblk1p1   xbl             3 MB     mmcblk1p33  apdp          0 MB
mmcblk1p2   xblbak          3 MB     mmcblk1p34  msadp         0 MB
mmcblk1p3   tz              4 MB     mmcblk1p35  dpo           0 MB
mmcblk1p4   tzbak          4 MB     mmcblk1p36  splash       32 MB
mmcblk1p5   rpm             0 MB     mmcblk1p37  limits        0 MB
mmcblk1p6   rpmbak          0 MB     mmcblk1p38  toolsfv       1 MB
mmcblk1p7   hyp             0 MB     mmcblk1p39  logfs         8 MB
mmcblk1p8   hypbak          0 MB     mmcblk1p40  ddr           1 MB
mmcblk1p9   pmic            0 MB     mmcblk1p41  sec           0 MB
mmcblk1p10  pmicbak         0 MB     mmcblk1p42  bluetooth     1 MB
mmcblk1p11  fsg             2 MB     mmcblk1p43  bluetoothbak  1 MB
mmcblk1p12  boot           64 MB     mmcblk1p44  fsc           0 MB
mmcblk1p13  system       3072 MB     mmcblk1p45  ssd           0 MB
mmcblk1p14  vendor       2048 MB     mmcblk1p46  modemst1      2 MB
mmcblk1p15  keymaster       1 MB     mmcblk1p47  modemst2      2 MB
mmcblk1p16  keymasterbak    1 MB     mmcblk1p48  persist      32 MB
mmcblk1p17  cmnlib           1 MB    mmcblk1p49  cache       256 MB
mmcblk1p18  cmnlib64         1 MB    mmcblk1p50  misc          1 MB
mmcblk1p19  cmnlibbak         1 MB   mmcblk1p51  recovery     64 MB
mmcblk1p20  cmnlib64bak       1 MB   mmcblk1p52  keystore      0 MB
mmcblk1p21  mdtpsecapp        4 MB   mmcblk1p53  devcfg        1 MB
mmcblk1p22  mdtpsecappbak     4 MB   mmcblk1p54  devcfgbak     1 MB
mmcblk1p23  mdtp             32 MB   mmcblk1p55  frp           0 MB
mmcblk1p24  mdtpbak         32 MB   mmcblk1p56  logdump      64 MB
mmcblk1p25  modem          256 MB   mmcblk1p57  sti           2 MB
mmcblk1p26  modembak       256 MB   mmcblk1p58  storsec       0 MB
mmcblk1p27  dsp             16 MB   mmcblk1p59  rawdump     128 MB
mmcblk1p28  dspbak          16 MB   mmcblk1p60  vbmeta        0 MB
mmcblk1p29  abl              1 MB   mmcblk1p61  vbmetabak     0 MB
mmcblk1p30  ablbak           1 MB   mmcblk1p62  cust        832 MB
mmcblk1p31  dip              1 MB   mmcblk1p63  logo         32 MB
mmcblk1p32  devinfo          0 MB   mmcblk1p64  userdata  111563 MB
```

**pmOS 的 rootfs 在 `userdata`（p64）**，MIUI 会把它重建成 Android data 分区。

---

## 三、当前系统状态快照

```
内核     7.0.14-sdm660 #4 (pmos@user, Alpine clang 23.1.4)
         含补丁 1（data_type）+ 补丁 2（采样率回退）
         boot 分区 MD5 b48000b431df303a
系统     postmarketOS "Nura edge" (edge)
设备     Xiaomi Mi Pad 4 Plus  (xiaomi,clover-plus / qcom,sdm660)
序列号   27eec4d2
cmdline  mdss_mdp.panel=...nt51021_boe_10wu_wuxga_video...
```

### 硬件实测数据（2026-10-24 17:54）

```
内存     3708416 kB (3.5 GB)  zram0 启用
CPU      8 核 (cpu0-cpu7)
温度     aoss 48.3°C / cpuss0 44.8 / cpuss1 46.7 / gpu 48.3
         电池 31.5°C / pm660 44.4 / pm660l 37.0
显示     DSI-1 connected enabled, 1200x1920
         背光 lcd-backlight cur=226 max=255 type=platform
面板     nt51021_boe_10wu_wuxga_video
```

---

## 四、刷 MIUI 步骤

### 4.1 线刷包

```
C:\Users\zl\Desktop\miui_clover_V14.0.5.0.TKZCNXM_dc8f6b8_13.0.zip   2.72 GB
```

解包后结构：
```
images/boot.img           64 MB
images/system.img.zst   1660 MB   (zstd 压缩)
images/vendor.img.zst   1051 MB
images/NON-HLOS.bin      112 MB   (modem)
images/dspso.bin          16 MB
images/mdtp.img           17 MB
images/logo.img          3.6 MB
images/splash.img        8.8 MB
images/xbl.elf           2.5 MB
images/abl.elf          0.11 MB
images/tz.mbn            1.9 MB
images/rpm.mbn           0.2 MB
images/hyp.mbn           0.3 MB
images/pmic.elf         0.04 MB
images/devcfg.mbn       0.05 MB
images/cmnlib.mbn        0.2 MB
images/cmnlib64.mbn      0.3 MB
images/keymaster64.mbn   0.3 MB
images/mdtpsecapp.mbn    1.0 MB
images/BTFM.bin          0.5 MB
bin/windows/fastboot.exe         ← 用这个，版本匹配
bin/windows/zstd.exe
```

### 4.2 关键警告

> **⚠️ 这个包会重写 `persist` 和 `devinfo`！**
> MIUI 的 `flash-all.bat` 通常包含 `fastboot flash persist`。
> 一旦重写，Wi-Fi MAC、传感器校准会变。
> **我们已经备份了 persist，可以恢复。**
>
> **建议：手动刷，跳过 persist/devinfo/modemst\*，只刷系统分区。**

### 4.3 推荐的手动刷机命令

```powershell
cd <解包目录>
$fb = ".\bin\windows\fastboot.exe"

# 先确认设备
& $fb devices
& $fb getvar unlocked          # 应该返回 unlocked: yes

# ---- 只刷必要分区，跳过 persist/devinfo/modemst ----
# 引导链（如果 ARB 允许；版本只升不降）
& $fb flash xbl      images\xbl.elf
& $fb flash abl      images\abl.elf
& $fb flash tz       images\tz.mbn
& $fb flash rpm      images\rpm.mbn
& $fb flash hyp      images\hyp.mbn
& $fb flash pmic     images\pmic.elf
& $fb flash devcfg   images\devcfg.mbn
& $fb flash keymaster images\keymaster64.mbn
& $fb flash cmnlib   images\cmnlib.mbn
& $fb flash cmnlib64 images\cmnlib64.mbn
& $fb flash mdtpsecapp images\mdtpsecapp.mbn
& $fb flash mdtp     images\mdtp.img
& $fb flash BTFM     images\BTFM.bin
& $fb flash dsp      images\dspso.bin
& $fb flash modem    images\NON-HLOS.bin
& $fb flash splash   images\splash.img
& $fb flash logo     images\logo.img

# ---- 系统分区（需要先解压 zst）----
& .\bin\windows\zstd.exe -d images\system.img.zst -o images\system.img
& .\bin\windows\zstd.exe -d images\vendor.img.zst -o images\vendor.img
& $fb flash system   images\system.img
& $fb flash vendor   images\vendor.img

# ---- boot ----
& $fb flash boot     images\boot.img

# ---- 清 data（必须，否则 pmOS 的 ext4 会让 Android 起不来）----
& $fb erase userdata
& $fb erase cache

# ---- vbmeta 必须禁用校验，否则起不来 ----
& $fb --disable-verity --disable-verification flash vbmeta images\vbmeta.img

& $fb reboot
```

> **如果要最小风险**：只刷 `boot` + `system` + `vendor`，保留现有固件引导链。
> 但版本跨度大时可能不兼容。

### 4.4 如果 MIUI 起不来

刷回备份的引导链：
```powershell
$b = "mipad4plus\artifacts\preflash"
foreach ($p in @('xbl','abl','tz','rpm','hyp','pmic','devcfg','keymaster',
                 'cmnlib','cmnlib64')) {
  & $fb flash $p "$b\$p.img"
}
```

---

## 五、测完扬声器后，回到 pmOS

### 5.1 刷回 pmOS boot

```powershell
$fb = "D:\APPS\platform-tools\fastboot.exe"
& $fb flash boot "mipad4plus\artifacts\preflash\boot.img"      # 我们编译的 r3 内核
& $fb erase userdata
& $fb erase cache
& $fb reboot
```

### 5.2 重新安装 pmOS

MIUI 把 `system`/`vendor`/`userdata` 都重写了，pmOS 的 rootfs 需要重装。

**有三种方式：**

**方式 A（推荐，最快）：用之前的 pmOS rootfs 镜像**
```
mipad4plus/tools/pmos-rootfs3.img   2444 MB
```
这是之前做的可启动 rootfs 镜像。写入 userdata 即可。

**方式 B：pmbootstrap install（干净重装）**
```bash
# 在 VM 上
pmbootstrap install --sdcard=/dev/sdX --filesystem=ext4
# 然后用 dd 把 p64 写入
```

**方式 C：只恢复我们的配置到新装的 pmOS**
```bash
# 新装 pmOS 后
tar -xzf lib-modules.tar.gz -C /                     # 内核模块
tar -xzf rootfs-etc-home.tar.gz -C /                 # 配置
cp -a custom-tools/tablet-* /usr/local/bin/          # 工具
cp -a custom-tools/*.service /etc/systemd/system/
systemctl daemon-reload
```

### 5.3 恢复后必须验证

```bash
# 1. 内核是 r3？
uname -a        # 期望 #4 ... pmos@user ... clang 23.1.4
cat /proc/version

# 2. 模块 BTF 正常？
journalctl -b 0 -k | grep -c 'BTF: -22'      # 期望 0

# 3. 5 个传感器都在？
for i in 0 1 2 3 4 5; do cat /sys/bus/iio/devices/iio:device$i/name 2>/dev/null; done

# 4. ALS 能读？
journalctl -b 0 -k | grep -c '0x501'         # 期望 0

# 5. 自动亮度
systemctl is-active tablet-autobright

# 6. 自动旋转
systemctl is-active tablet-orientd
tablet-rotation-settings status

# 7. 桌面
pgrep -c Xorg; pgrep -c xfwm4

# 8. 音频/显示/WiFi
cat /proc/asound/cards
ls /dev/dri/
ip -br addr
```

---

## 六、扬声器诊断：在 Android 上要看什么

刷回 MIUI 后，请按顺序确认：

### 6.1 基础确认

```
[ ] 1. Android 系统声音（按键音）有没有
[ ] 2. 播放音乐有没有
[ ] 3. 铃声音量调到最大有没有
```

### 6.2 如果 MIUI 上也没声音

→ **确认是硬件故障**。三种可能：
- 扬声器单元损坏
- 扬声器 FPC 排线松脱/断裂
- 功放芯片（在 PM660L 内）损坏

处理：需要拆机检查排线，或用万用表测扬声器阻值（正常 8Ω 左右）。

### 6.3 如果 MIUI 上有声音

→ **说明是 Linux 侧的问题**，而且是我们还没找到的地方。那就有了新的调查方向。

### 6.4 顺便可采的 Android 数据（有 root 时）

```bash
adb root        # 或 adb shell su
# 音频
adb shell "tinymix -D 0" > android-tinymix.txt
adb shell "cat /vendor/etc/mixer_paths.xml" > android-mixer.xml
adb shell "dumpsys media.audio_flinger" > android-audioflinger.txt
# 摄像头（验证我们的 OV13855 结论）
adb shell "ls -l /dev/video*"
adb shell "cat /proc/device-tree/soc/*cci*/qcom,camera@0/*" 2>/dev/null
# 确认扬声器音量寄存器
adb shell "cat /sys/kernel/debug/regmap/*/registers" | grep -i f19e
```

---

## 七、风险与回退

| 风险 | 概率 | 缓解 |
|---|---|---|
| MIUI 覆盖 persist → MAC/校准丢失 | **高**（如果跑 flash-all.bat） | **已备份 persist.img**，可 `fastboot flash persist` 恢复 |
| ARB 阻止降级 | 低 | 只刷同级或更高版本 |
| MIUI 起不来 | 中 | 有完整引导链备份，可刷回 |
| userdata 被清（pmOS rootfs 丢失） | **确定会** | 已有 `pmos-rootfs3.img` 和配置 tar |
| 刷机后进不了 fastboot | 低 | 长按电源 10-15s 强制重启，再 Vol-Down+Power |

### 强制恢复流程（如果彻底起不来）

```powershell
$fb = "D:\APPS\platform-tools\fastboot.exe"
$b = "mipad4plus\artifacts\preflash"

# 1. 进 fastboot：长按电源 10-15s → 松手 → Vol-Down+Power
# 2. 逐个刷回引导链
& $fb flash xbl    "$b\xbl.img"
& $fb flash abl    "$b\abl.img"
& $fb flash tz     "$b\tz.img"
& $fb flash rpm    "$b\rpm.img"
& $fb flash hyp    "$b\hyp.img"
& $fb flash pmic   "$b\pmic.img"
& $fb flash devcfg "$b\devcfg.img"
& $fb flash vbmeta "$b\vbmeta.img"
# 3. 刷回我们的 boot
& $fb flash boot   "$b\boot.img"
& $fb reboot
```

---

## 八、当前三件事的结论（供后续参考）

### 8.1 扬声器

**软件侧已完全排除**，证据链：

| 层 | 验证手段 | 结果 |
|---|---|---|
| DTS 路由 | 与 Android 原厂 DTS 逐字对比 | ✅ 完全一致 |
| DSP 会话 | ftrace `q6asm_open_write` | ✅ |
| AFE 端口 | ftrace `q6afe_port_start` | ✅ |
| 数据写入 | ftrace `q6asm_write_async` | ✅ |
| DAPM 上电 | ftrace `enable_spk_pa` 4 次调用 | ✅ |
| SPKR_CLK | `f049` = 0x10 (bit4) | ✅ |
| SPK DAC | `f1b0` = 0x83 (bit7) | ✅ |
| Class-D PA | `f1b2` = 0xef (bit7) | ✅ |
| 功率级 | `f1b5` = 0xff | ✅ DAC_EN+BBM+HBRIDGE+CLAMP |
| 扬声器供电 LDO | `f19E` = 0x13 (bit0) | ✅ |
| 耳机通路 | 实测有声 | ✅ 证明数字链路正常 |

### 8.2 摄像头

已从 MIUI 线刷包完整提取配置：

```
CameraId 0 (后置)   ov13855_f13v10l   13MP  CSI2: csiphy0/csid0
                    actuator bu64297_f13v10l
                    eeprom   qtech_ov13855
                    MountAngle 90, LaneMask 0x1F, LaneAssign 0x4320
                    LensInfo: 3.44mm f/2.0 67.8°x53.1°

CameraId 2 (前置)   s5k5e8            5MP   CSI2: csiphy2/csid2
                    eeprom   qtech_s5k5e8
                    MountAngle 270, LaneMask 0x7, LaneAssign 0x4320
                    LensInfo: 2.639mm f/2.0 57.5°x44.8°

内核支持：camss.c 有 "qcom,sdm660-camss"
上游 DTS：sdm630.dtsi 有完整 camss@ca00020 + cci@ca0c000 节点
驱动现状：ov13858.c 存在（同系列可派生），ov13855.c 和 s5k5e8.c 缺失
```

### 8.3 睡眠

根因明确：
```c
SET_SYSTEM_SLEEP_PM_OPS(pm_runtime_force_suspend, pm_runtime_force_resume)
dpu_runtime_suspend() -> clk_bulk_disable_unprepare()   // 先关时钟
```
DPU 关时钟时仍在等 vblank → vblank timeout → watchdog hard LOCKUP on cpu5。
修复方向：suspend 前先 `drm_atomic_helper_suspend()`（主线后来的做法）。

---

## 九、文件索引

| 位置 | 内容 |
|---|---|
| `artifacts/preflash/*.img` | 21 个分区备份（192.8 MB） |
| `artifacts/preflash/lib-modules.tar.gz` | r3 内核模块 |
| `artifacts/preflash/MD5SUMS` | 校验和 |
| `artifacts/preflash/meta.txt` | 分区表、挂载、cmdline |
| `evidence/hw-full-preflash-20261024.txt` | 611 行全量硬件数据 |
| `artifacts/rom/miui-dtb-0.dtb` | MIUI 原厂 DTB（346 KB，含全部硬件节点） |
| `artifacts/rom/vendor-camera/camera_config.xml` | 摄像头 sensor 配置 |
| `artifacts/rom/vendor-audio/mixer_paths.xml` | Android 音频路由（105 KB） |
| `tools/pmos-rootfs3.img` | 可启动的 pmOS rootfs（2444 MB） |

平板端：
```
/root/preflash-20261024-174908/   完整备份
/tmp/pfbackup/                    可读副本
```
