# HANDOFF · Mi Pad 4 Plus 办公化交接文档

> **最后更新：2026-10-24 23:50**
> **⚠️ 当前状态：设备因 GPU 挂死离线，需长按电源 10-15 秒强制重启**
> 重启后为竖屏 + 软件渲染（可用）。桌面托盘/电量/蓝牙/音量已补齐；
> 触摸矩阵自动跟随旋转已就绪；扬声器驱动已移植但**仍无声**。
> 本轮详情见 `20-SPEAKER-TOUCH-DESKTOP.md`。
> 设备：Xiaomi Mi Pad 4 Plus（clover-plus / SDM660），序列号 `27eec4d2`
> 系统：postmarketOS "Nura edge"，内核 `7.0.14-sdm660`（已刷 r5：含 TAS2557 DTS + 驱动补丁）

---

## 一、30 秒上手

```powershell
cd C:\Users\zl\Documents\deepseek-harness\default-workspace\mipad4plus

# 连平板（WiFi，已通）
$env:PAD_HOST = "192.168.1.29"
python tools\ssh_pad.py "uname -a; df -h / | tail -1"

# 用 sudo
cd tools; .\pad_sudo.ps1 -Cmd "systemctl status greetd" -Timeout 120

# 连构建 VM
python tools\ssh_vm.py "ls ~/.local/var/pmbootstrap/"

# 平板进 fastboot
adb reboot bootloader
# 或：长按电源 10-15s → 松手等 2s → 音量减+电源
```

**密码**：平板 `user` / `<SUDO_PASSWORD>`；VM `user` / `<VM_PASSWORD>`

---

## 二、当前状态快照（2026-10-24 22:13 实测）

```
内核    : 7.0.14-sdm660 #4-postmarketos-qcom-sdm660  aarch64
系统    : Nura edge
运行    : 1h09m，load 1.86/0.88/0.52（稳定，无重启）

磁盘    : 105.6 GB 总量，已用 3.3 GB，可用 98.0 GB (3%)   ← 已扩展！
图形    : Xorg 1.21.1.25 + xfwm4 + xfce4-panel + xfdesktop + xfsettingsd
显示    : DSI-1 connected 1920x1200 left（横屏）
背光    : 180/255  ← 已修复（原为 9）
网络    : wlan0 192.168.1.29  MAC d2:89:ce:0c:09:e0
传感器  : mag / gyro / accel / prox（prox 里含 ALS）
音频    : sdm660-internal "Xiaomi Mi Pad 4"
```

**详细状态见 `evidence/final-state-20261024.txt`**

---

## 三、已完成的工作（按时间倒序）

### 3.1 本轮（2026-10-24 19:00 ~ 22:20）：从 MIUI 恢复 pmOS

| 成果 | 文档 |
|---|---|
| 刷 MIUI V10.3.2.0 + Magisk root + 48 项硬件采集 | `18-HARDWARE-COMPLETE.md` |
| Android vs pmOS 硬件对比 | `17-ANDROID-VS-PMOS-HARDWARE.md` |
| **恢复 pmOS + 磁盘修复 + Xorg/XFCE 安装 + 背光修复** | `19-PMOS-RESTORE.md` |

**核心发现：**
1. **扬声器无声的根因是 TI TAS2557 智能功放缺 DTS 节点**
   - 驱动 `CONFIG_SND_SOC_TAS2557=m` **已编译在内核里**
   - `snd-soc-tas2557.ko.zst` 存在于 `lib-modules.tar.gz`
   - 只需加设备树节点：I2C6 @ 0x4c/0x4e，reset GPIO 80/48
2. **磁盘问题**：刷完镜像必须 `resize2fs`（2.2 GB → 105.6 GB）
3. **Xorg/XFCE 需单独安装**（旧镜像里没有）

### 3.2 上一轮（2026-10-20 ~ 10-24）：ALS 与自动亮度

| 成果 | 文档 |
|---|---|
| ALS 环境光传感器驱动修好 | `13-ALS-SUCCESS.md` |
| 自动亮度服务 | `14-AUTO-BRIGHTNESS.md` |
| ALS 采样率分析 | `15-ALS-SAMPLERATE.md` |
| 旋转设置 UI | `10-AUTOROTATE.md` |

### 3.3 更早（2026-10-18 ~ 10-19）：基础搭建

| 成果 | 文档 |
|---|---|
| 刷机流程、Android 采集 | `02-android-runbook.md`、`05-android-collection.md` |
| Xorg/XFCE 配置权威指南 | `07-xorg-xfce.md` |
| 硬件缺陷审计（9 项） | `08-HARDWARE-AUDIT.md` |
| 传感器深挖 | `09-P0-1-SENSORS.md` |

---

## 四、硬件状态总表（48 项）

### 4.1 已工作（✅）

| 组件 | 细节 |
|---|---|
| 屏幕 | BOE NT51021，1200x1920 原生，横屏 1920x1200 |
| 背光 | TI LP8556 @ i2c8-0x2c，0-255 |
| 触摸 | Goodix GT9110 @ i2c3-0x5d |
| WiFi | Qualcomm WCN3990 (ath10k_snoc) |
| 蓝牙 | BTFM（同 WCN3990） |
| 加速度/陀螺/磁力/接近 | qcom-smgr（5 个 IIO 设备） |
| **ALS 环境光** | CM3232，在 `qcom-smgr-prox` 里（`in_proximity_*`）|
| 音频 codec | PM660L WCD（模拟+数字） |
| 耳机 | MBHC 检测，有声 |
| 麦克风 | AMIC + DMIC |
| 电源键 | qpnp_pon |
| 音量+ | gpio-keys，GPIO 466，KEY_VOLUMEUP |
| 存储 | eMMC 105.6 GB |
| SD 卡槽 | sdhci |
| USB/OTG | DWC3 双角色（`ufp dfp`）+ Type-C PD |
| 电池 | Li-poly 8620 mAh |
| GPU | Adreno 512（llvmpipe 软件渲染） |
| 视频编解码 | Venus |
| 热管理 | 12 个 thermal zone |

### 4.2 未工作（❌）

| 组件 | 根因 | 优先级 | 工作量 |
|---|---|---|---|
| **扬声器** | TAS2557 缺 DTS 节点 | **高** | **低**（驱动已在） |
| **ALS 自动亮度** | systemd 条件写死 device3 | **高** | **极低**（改条件） |
| **摄像头** | OV13855/S5K5E8 缺驱动 | **高**（视频会议） | 中 |
| 睡眠 | DPU suspend 死锁 | 中 | 高 |
| 闪光灯 | `CONFIG_LEDS_QCOM_FLASH` 未开 | 低 | 低 |
| RGB 呼吸灯 | 无 leds-qpnp 驱动 | 低 | 中 |
| 快充/QC | 缺 SMB1351 驱动 | 中 | 中 |
| GPS | 缺 ADSP GNSS QMI | 低 | 中 |
| 指纹 | 需 TEE/QSEECOM（闭源） | 低 | 极高 |
| 关机充电 | 未实现 charger 模式 | 低 | 中 |

### 4.3 硬件不存在（❌）

- **振动马达**：`/sys/class/timed_output/` 空
- **按键背光**：`/sys/class/leds/` 无 button/kbd 类
- **FM 收音**：有 `fm_qsoc_patches` 但无 `/dev/radio0`

---

## 五、最高优先级的三个修复

### 5.1 ALS 自动亮度（最快，约 10 分钟）

**问题**：`tablet-autobright.service` 的条件写死了 device 索引：

```ini
ConditionPathExists=/sys/bus/iio/devices/iio:device3/buffer/enable
```

但设备索引变了：
```
iio:device3 = qcom-smgr-gyro      ← 检查的是这个
iio:device5 = qcom-smgr-prox      ← ALS 在这里
```

**修复方案**：改 service 文件，去掉 `ConditionPathExists`，让脚本自己按名字查设备。

`tablet-autobright` 是 Python 脚本，在开头加：

```python
import glob, os, sys

def find_prox():
    for d in glob.glob('/sys/bus/iio/devices/iio:device*'):
        try:
            if open(f'{d}/name').read().strip() == 'qcom-smgr-prox':
                return d
        except OSError:
            pass
    return None

if find_prox() is None:
    sys.exit(0)
```

然后：
```bash
sudo systemctl daemon-reload
sudo systemctl restart tablet-autobright
systemctl status tablet-autobright
```

### 5.2 扬声器（约 30 分钟，需编译内核）

**驱动已在内核**（`CONFIG_SND_SOC_TAS2557=m`），只需加 DTS 节点。

**在 clover 板级 DTS 加**（`sdm660-xiaomi-clover-common.dtsi`）：

```dts
&i2c_6 {
    status = "okay";

    tas2557_left: audio-codec@4c {
        compatible = "ti,tas2557";
        reg = <0x4c>;
        #sound-dai-cells = <0>;
        reset-gpios = <&tlmm 80 GPIO_ACTIVE_LOW>;
        vbat-supply  = <&pm660l_bob>;       /* 需确认实际供电 */
        iovdd-supply = <&vreg_l7b_1p8>;     /* 待确认 */
        avdd-supply  = <&vreg_l6b_1p8>;     /* 待确认 */
        dvdd-supply  = <&vreg_l6b_1p8>;     /* 待确认 */
        ti,channel = <0>;                   /* 左声道 */
        firmware-name = "tas2557_uCDSP_d9p.bin";
    };

    tas2557_right: audio-codec@4e {
        compatible = "ti,tas2557";
        reg = <0x4e>;
        #sound-dai-cells = <0>;
        reset-gpios = <&tlmm 48 GPIO_ACTIVE_LOW>;
        vbat-supply  = <&pm660l_bob>;
        iovdd-supply = <&vreg_l7b_1p8>;
        avdd-supply  = <&vreg_l6b_1p8>;
        dvdd-supply  = <&vreg_l6b_1p8>;
        ti,channel = <1>;                   /* 右声道 */
        firmware-name = "tas2557_uCDSP_d9p.bin";
    };
};
```

**还需要**：
1. 固件文件：`/lib/firmware/tas2557_uCDSP_d9p.bin`（从 Android 的 `vendor/firmware/` 复制，39,615 B）
2. 修改机器驱动 `sdm660-internal.c`，把 DAI link 接到 TAS2557（或加新的 link）
3. 编译内核（VM 上约 25-37 分钟）

**参考**：`18-HARDWARE-COMPLETE.md` §4.2 有完整的 TAS2557 硬件参数。

### 5.3 摄像头（工作量最大）

**已知**：
- 后置：**OV13855** + BU64297 VCM + QTech EEPROM，csiphy0/csid0，LaneMask 0x1F
- 前置：**S5K5E8** + QTech EEPROM，csiphy2/csid2，LaneMask 0x7

**内核有**：
- `camss.c` 支持 `qcom,sdm660-camss` ✅
- 上游 `sdm630.dtsi:2061 camss: camss@ca00020` + `cci: cci@ca0c000` ✅

**缺**：
- `ov13855.c`（可从 `ov13858.c` 派生）
- `s5k5e8.c`（需新写）
- 板级 DTS 完全没有摄像头节点

---

## 六、关键文件与路径

### 6.1 备份（最重要）

```
mipad4plus/artifacts/preflash/          （281 MB，29 文件，MD5 已校验）
├── boot.img              64 MB    pmOS r3 内核
├── persist.img           32 MB    含 WiFi/BT MAC、指纹、音频校准
├── modemst1/2.img         2 MB    基带
├── fsg.img / fsc.img      2 MB
├── misc.img / devinfo.img / sec.img / keystore.img / frp.img
├── devcfg/rpm/tz/hyp/xbl/abl/pmic/vbmeta/boot/recovery/splash/logo.img
├── lib-modules.tar.gz   13.7 MB   10/24 内核模块（847 条目）
├── lean-config.tar.gz   23.3 MB   10/24 配置
│     └── 内层：lean-etc.tar.gz (23.2 MB) + lean-root.tar.gz (130 KB)
├── custom-tools.tar.gz
└── MD5SUMS / meta.txt

mipad4plus/tools/pmos-final.img      2.39 GB  ← 含 10/24 配置的 rootfs
mipad4plus/tools/pmos-rootfs3.img    2.39 GB  ← 原始（10/19，无配置）
```

**MD5 前缀**：persist `afed307fbf0fac7c`，modemst1 `9b23c08b0be265c0`，
modemst2 `f14d657c7b9ec805`，fsg `8457f07c10853e34`，boot `b48000b431df303a`

### 6.2 平板上的关键路径

```
/usr/local/bin/tablet-*                    20 个脚本
  tablet-autobright            ALS 自动亮度（Python）
  tablet-orientd               自动旋转
  tablet-rotation-settings     旋转设置 UI
  tablet-audio / tablet-sleep / tablet-battery-status
  tablet-display-mode / tablet-bt-pair / tablet-restore-snapshot
  tablet-session-launcher      会话选择（XFCE 优先，失败回退 Phosh）
  xfce-tablet-session          XFCE 会话
  xfce-x-session               启动 Xorg + XFCE

/etc/systemd/system/
  tablet-autobright.service
  tablet-orientd.service
  alsa-mic-tablet.service
  alsa-restore-tablet.service

/etc/tablet/
  landscape                    横屏标志
  rotation.json                旋转状态

/etc/X11/xorg.conf.d/
  00-keyboard.conf             cn,cn,us 键盘
  50-msm-soft.conf             llvmpipe（AccelMethod "none"）

~/.local/share/tablet-session/
  launcher.log                 会话选择日志
  xfce-x-session.log           Xorg 启动日志
```

### 6.3 依赖工具

```
mipad4plus/tools/
  ssh_pad.py      连平板（PAD_HOST 环境变量）
  put_pad.py      传文件到平板
  get_pad.py      从平板取文件
  run_sudo.py     平板上跑 sudo 脚本
  pad_sudo.ps1    用密码管道跑 sudo（SSH 无 TTY 时用）
  ssh_vm.py       连构建 VM
  scp_vm.py       传文件到 VM
  get_vm.py       从 VM 取文件
  fetch_apks.py   并行下载 Alpine 包（见 §八）

  pad_*.sh        平板侧诊断/操作脚本（100+ 个）
  vm_*.sh         VM 侧构建/分析脚本
```

---

## 七、重要教训（必须记住）

| # | 教训 | 说明 |
|---|---|---|
| 1 | **刷镜像后必须 `resize2fs`** | 否则 2.2 GB 100% 满，什么都装不上 |
| 2 | **UUID 匹配 ≠ 内容最新** | `pmos-rootfs3.img` UUID 对但内容是 5 天前的 |
| 3 | **刷前必须注入最新配置** | 否则 10/20~10/24 的工作全丢 |
| 4 | **不要动 USB gadget 的 UDC** | 解绑重绑会崩，USB 全失，只能强制重启 |
| 5 | **SSH 下 sudo 要管道密码** | `echo PASS \| sudo -S -p '' cmd` |
| 6 | **PowerShell 不嵌 shell 语法** | `$(...)`、反引号会被 PS 抢先解析，写 .sh 文件 |
| 7 | **让平板自己 apk add** | 手动下 Alpine 包会依赖冲突（openrc vs systemd） |
| 8 | **MIUI 13 不能刷** | 必须用官方 8.1 包，且要刷全部 `*bak` 分区 |
| 9 | **Magisk 要用当前 boot 现打补丁** | 旧 patched.img 内核不匹配会卡米 |
| 10 | **背光持久化路径带前缀** | `/var/lib/systemd/backlight/platform-c1b8000.i2c:backlight:lcd-backlight` |

---

## 八、工具：fetch_apks.py（加速下载）

**问题**：平板 WiFi 下 `apk add` 很慢（Aliyun 返回 HTML 伪装导致重试）。

**方案**：在 Windows 上并行下载，再整批传回。

```powershell
cd mipad4plus\tools

# 下载（自动解析 APKINDEX，多镜像回退，并行 16 线程）
python fetch_apks.py --out .\pkgs --pkgs xorg-server xfce4-session xfwm4 --workers 16

# 打包
tar -czf pkgs.tar.gz -C .\pkgs .

# 传（实测 110-120 Mbps，29 MB 只要 2 秒）
python -c "
import paramiko
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.1.29',username='user',password='<SUDO_PASSWORD>')
s=c.open_sftp(); s.put(r'pkgs.tar.gz','/tmp/pkgs.tar.gz'); s.close(); c.close()"

# 平板安装
python tools\ssh_pad.py "rm -rf /tmp/pkgs && mkdir /tmp/pkgs && tar -xzf /tmp/pkgs.tar.gz -C /tmp/pkgs"
cd tools; .\pad_sudo.ps1 -Cmd "apk add --no-progress --allow-untrusted --force-non-repository /tmp/pkgs/*.apk"
```

> **注意**：如果空间充足，**直接用平板 `apk add` 更简单**，
> 因为手动下的 Alpine 包可能依赖 openrc/elogind，与 pmOS 的 systemd 冲突。
> 本轮最后就是靠平板自己 `apk add` 一次装成功的（177 个包）。

---

## 九、刷机速查（紧急恢复）

### 9.1 从 Android 刷回 pmOS

```powershell
$fb = "D:\APPS\platform-tools\fastboot.exe"
$b  = "mipad4plus\artifacts\preflash"

& $fb flash boot "$b\boot.img"
& $fb erase userdata
& $fb erase cache
& $fb erase misc
& $fb flash userdata "mipad4plus\tools\pmos-final.img"
& $fb reboot

# 启动后（WiFi 或串口）
# sudo resize2fs /dev/mmcblk1p64     ← 千万别忘！
```

### 9.2 从 pmOS 刷回 Android 8.1（官方包）

```
包：E:\mipad4plus-work\rom81\clover_images_V9.6.4.0.ODJCNFD_20180615.0000.00_8.1_cn\
或：E:\mipad4plus-work\rom1032\clover_images_V10.3.2.0.ODJCNXM_20190515.0000.00_8.1_cn\

40 步：主分区 + 所有 *bak + userdata.img + erase misc
脚本：E:\mipad4plus-work\flash1032.ps1
```

**关键**：必须刷 `*bak` 分区（`ablbak, bluetoothbak, cmnlibbak, cmnlib64bak,
devcfgbak, dspbak, hypbak, keymasterbak, mdtpbak, mdtpsecappbak, modembak,
pmicbak, rpmbak, tzbak, xblbak`），并且 `flash userdata userdata.img`
（**不是** `erase userdata`）。

### 9.3 Root Android（Magisk）

**必须用当前 ROM 的 boot.img 现打补丁**，不能用旧的 patched 镜像。

```powershell
# 1. 推 ROM 的 boot.img 到设备
adb push <rom>\images\boot.img /sdcard/boot.img
# 2. 装 Magisk v26.4（v31 在 8.1 上失败）
adb install Magisk-v26.4.apk
# 3. 平板操作：Magisk → 安装 → 选择并修补文件 → /sdcard/boot.img
# 4. 拉回补丁
adb pull /sdcard/Download/magisk_patched-26400_XXXXX.img
# 5. 刷入
adb reboot bootloader
fastboot flash boot magisk_patched-26400_XXXXX.img
fastboot reboot
# 6. 验证
adb shell "/sbin/magisk su -c id"    # 注意：su 符号链接会 Permission denied
```

---

## 十、环境信息

```
Windows 主机
  C:  213.6 GB 总量，可用 24.7 GB
  D:  284.9 GB（软件）
  E:  4.0 TB（数据，可用 2.4 TB）  ← 大文件都放这
  F:  1.0 TB（其它，可用 945 GB）

构建 VM  : 192.168.1.200  Ubuntu 22.04 / 5.15 内核，磁盘 77 GB
  pmaports: ~/.local/var/pmbootstrap/cache_git/pmaports
  内核源码: ~/.local/var/pmbootstrap/cache_distfiles/linux-v7.0.14-sdm660.tar.gz
  device  : device/testing/linux-postmarketos-qcom-sdm660/
  编译时间: 25-37 分钟

Android 工具
  fastboot: D:\APPS\platform-tools\fastboot.exe (34.0.4)
  adb     : D:\APPS\platform-tools\adb.exe

MIUI 包
  V10.3.2.0: E:\mipad4plus-work\rom1032\   （1492 MB，已验证完整）
  V9.6.4.0 : E:\mipad4plus-work\rom81\     （已验证可用）
```

---

## 十一、下一步（建议顺序）

### 立刻（本轮可完成）

1. **修 ALS 自动亮度**：改 `tablet-autobright.service` 条件（10 分钟）
2. **实测触摸/键盘/音量键**（5 分钟）
3. **验证 WiFi 稳定性**（ping 测试）

### 短期（1-2 轮会话）

4. **修扬声器**：TAS2557 DTS 节点 + 固件 + 编译内核（30 分钟）
5. **睡眠**：DPU suspend 死锁（`drm_atomic_helper_suspend()`）
6. **闪光灯**：开 `CONFIG_LEDS_QCOM_FLASH` + DTS

### 中期

7. **摄像头**：OV13855 驱动（从 ov13858.c 派生）+ S5K5E8（新写）+ camss DTS
8. **快充**：SMB1351 驱动
9. **RGB 呼吸灯**：leds-qpnp 或 LPG

### 不现实

10. 指纹（需 TEE，闭源 fpctzapp）
11. GPS（需 ADSP GNSS QMI）

### 办公电脑目标

**当前完成度约 70%**

阻塞项（按影响排序）：
1. **扬声器无声** — 影响媒体播放/会议
2. **摄像头无驱动** — 影响视频会议（刚需）
3. **睡眠死锁** — 影响续航与便携
4. **性能**（llvmpipe 软件渲染，横屏 1920x1200 时较卡）

---

## 十二、文档索引

| # | 文档 | 主题 |
|---|---|---|
| 00 | `00-GOAL.md` | 总目标与路线图 |
| 01 | `01-plan.md` | 初始计划 |
| 02 | `02-android-runbook.md` | Android 刷机手册 |
| 03 | `03-findings.md` | 早期发现 |
| 04 | `04-build-log.md` | 内核编译日志 |
| 05 | `05-android-collection.md` | Android 采集方法 |
| 06 | `06-xfce-experiment.md` | XFCE 实验 |
| 07 | `07-xorg-xfce.md` | **Xorg/XFCE 权威配置** |
| 08 | `08-HARDWARE-AUDIT.md` | 硬件缺陷审计（9 项） |
| 09 | `09-P0-1-SENSORS.md` | 传感器深挖 |
| 10 | `10-AUTOROTATE.md` | 自动旋转 |
| 11 | `11-REGISTRY-EXPERIMENT.md` | 显示注册表实验 |
| 12 | `12-FLASH-ATTEMPT.md` | 刷机尝试记录 |
| 13 | `13-ALS-SUCCESS.md` | ALS 修好 |
| 14 | `14-AUTO-BRIGHTNESS.md` | 自动亮度 |
| 15 | `15-ALS-SAMPLERATE.md` | ALS 采样率 |
| 16 | `16-FLASH-TO-MIUI.md` | **刷 MIUI 完整流程** |
| 17 | `17-ANDROID-VS-PMOS-HARDWARE.md` | Android vs pmOS 对比 |
| 18 | `18-HARDWARE-COMPLETE.md` | **48 项完整硬件清单** |
| 19 | `19-PMOS-RESTORE.md` | **本次恢复全过程** |
| —  | `HANDOFF.md` | 本文 |

---

## 十三、2026-10-24 23:50 本轮状态与禁令（必读）

> 详细内容见 `20-SPEAKER-TOUCH-DESKTOP.md`

### 13.1 绝对不要做的事

| 禁令 | 原因 |
|---|---|
| **任何情况下不要开 glamor**（不要移走 `50-msm-soft.conf`） | Adreno 512 立即 `a5xx ring fault` → `hangcheck recover` → X 卡死 → 连 `systemctl reboot` 都走不完，只能长按电源 |
| **不要用 `/etc/tablet/landscape` 开机即横屏** | 会话启动时 `xrandr --rotate left` 会触发 `dpu ... vblank timeout` → 面板无输出（背光 255、DRM 报 enabled，但黑屏） |
| 不要从 SSH 用 `nohup ... &` 启动 GUI 进程 | systemd 会按 session scope 杀掉；用 `systemd-run --user` 或 `~/.config/autostart` |
| `pad_sudo.ps1 -Cmd` 里不要用 `$`、`;` 串联多命令 | PowerShell/引号会把命令破坏；一律写 `.sh` 文件再 `-Cmd "sh /tmp/x.sh"`，且脚本必须是 **LF** 换行 |

### 13.2 设备当前状态

```
竖屏 1200x1920，llvmpipe（AccelMethod none），合成器已关闭
tablet-touch-rotate    active（矩阵自动跟随，当前 identity）
tablet-autobright      active（ALS 在 iio:device5）
boot                   r5（TAS2557 DTS + 双实例驱动补丁）
声卡                   card 0 "Xiaomi Mi Pad 4" 已注册，但扬声器无声
/root/boot-old.img     旧 boot 备份（64 MB）
/root/boot-r4.img      r4 boot 备份
```

### 13.3 恢复步骤（设备离线时）

1. 长按电源 10–15 秒强制关机
2. 等 2 秒，按电源开机
3. 开机约 30 秒后 WiFi 自动连回 192.168.1.29

若开不了机：`fastboot flash boot artifacts\preflash\boot.img`（已知可用的 pmOS r3 内核）。

### 13.4 扬声器当前进度（无声音）

- 两颗 TAS2557 已 probe、固件 `tas2557_uCDSP.bin` 已加载（PG2.1 left/right ready）
- 声卡注册成功，`INT0_MI2S_RX Audio Mixer MultiMedia1 = on`，`speaker-test` 能跑完
- 播放时两颗功放寄存器成片变化 → hw_params/enable 路径确实被调用
- **但听不到声音**，下一步见 `20-...md` §4.5（重点怀疑 I2S 无数据 / 16-bit vs 32-bit / DAPM 未上电）

### 13.5 性能

- 已关 xfwm4 合成器（持久化在 xfconf）
- 内核 **没有 CPU cpufreq**（`sdm660.dtsi` 把 cpu 的 `operating-points-v2` 删掉了），
  CPU 频率由 bootloader 决定，无法调频 —— 这是平台上游限制，不是配置问题
- 后续只能靠：纯色壁纸、必要时降分辨率、减少重绘
---

## 十四、2026-10-25 00:30 夜间进展（用户休息，未做重启类操作）

### 14.1 办公应用已安装

```
libreoffice-writer / -calc / -impress + libreoffice-lang-zh_cn   （25.8.7.3，中文界面）
zathura + zathura-pdf-poppler    PDF
file-roller                      压缩包
mpv                              视频播放（可验证声音）
xfce4-screenshooter / ristretto  截图 / 看图
galculator                       计算器
```

验证：`soffice --version` → `LibreOffice 25.8.7.3`；`/usr/lib/libreoffice/share/registry/Langpack-zh-CN.xcd` 存在。

> 安装必须用 `systemd-run` 起系统级单元，否则 SSH 退出时会被 session scope 杀掉（这次踩过：
> `nohup` 起的 apk 在 44/79 处被杀）。

### 14.2 UVC（USB 摄像头）已编进内核 r9（待部署）

发现 `CONFIG_MEDIA_USB_SUPPORT` 是关闭的 —— 意味着插 USB 摄像头也不会出 `/dev/video0`。
已改内核配置：

```
CONFIG_MEDIA_SUPPORT=y            (原 =m，bool 依赖需要 y 才能开 USB 子选项)
CONFIG_MEDIA_USB_SUPPORT=y
CONFIG_USB_VIDEO_CLASS=m
CONFIG_USB_VIDEO_CLASS_INPUT_EVDEV=y
```

`pmbootstrap build` 正在编译 r9。**部署需要重启**，留到用户醒来后做。

这是"视频会议"最现实的路径：内置摄像头需要新写 OV13855/S5K5E8 驱动，
而 USB UVC 摄像头只要内核支持就能用。

### 14.3 摄像头为什么是硬骨头（调研结论）

| 事实 | 影响 |
|---|---|
| MIUI 的 boot.img DTB（已反编译）里**只有 csiphy/cci 控制器，没有 sensor 节点** | 拿不到官方 GPIO/供电/CSI lane 配置 |
| Xiaomi `clover-o-oss` 内核源码里**没有 camera sensor 驱动**（只有 cci/csid/csiphy 框架） | 不能直接移植寄存器表 |
| 主线 `qcom,sdm660-camss` 存在，但没有任何主线设备真正用它出图 | 属于未验证路径，可能要修 camss |
| vendor 分区有 `libchromatix_ov13855_*.so` 等 1346 个相机库 | 只能做逆向参考，不能直接变驱动 |

结论：内置摄像头需要「新写 V4L2 sensor 驱动 + camss DTS + 可能修 camss」，是数轮的工作量。
短期用 USB UVC 摄像头满足视频会议。

### 14.4 其它

- 音频：`pactl set-sink-mute 1`（夜间静音，早上要 `set-sink-mute 0` 恢复）
- 横屏：延迟 15s 旋转已生效，`/etc/tablet/landscape` 存在
- UCM 新配置：`/usr/share/alsa/ucm2/Xiaomi/clover/HiFi.conf`（Speaker + Headphones），
  备份在 `/root/clover-HiFi.conf.orig`
### 14.5 夜间补充（00:40）

- 桌面快捷方式改为放进**应用菜单**（Whisker）：`~/.local/share/applications/`
  - `tablet-rotate` 旋转切换（横/竖屏）
  - `tablet-osk` 屏幕键盘（onboard 已不再自动启动）
  - `bluetooth-manager`、`network-settings`
- 教训：**不要从 SSH 直接 `pkill xfdesktop` 再 `setsid xfdesktop`**，
  新进程会被 session scope 杀掉，桌面变黑；要么用
  `systemd-run --user --unit=xfdesktop-unit ...`，要么 `systemctl restart greetd`。
- 夜间把 PulseAudio sink 静音了（避免吵醒用户），并建了 **07:00 自动取消静音** 的
  user timer（`unmute-audio.timer`）。若早上仍无声，先看 `pactl get-sink-mute`。
- r9（UVC）产物已在 Windows：`tools/boot-r9.img`、`tools/modules-r9.tar.gz`
- r9 的 boot.img 里 DTB 与 r7 相同（只有内核配置变化），部署 = 写 boot + 装模块 + 重启
### 14.6 摄像头 sensor 库逆向（夜间，未完成但已拿到关键信息）

从 vendor 分区（`/dev/mmcblk1p14`，ext4）用 `debugfs dump` 取出真正的 sensor 驱动库：

```
libmmcamera_ov13855_f13v10l.so   798392 B   ELF32 ARM, stripped
libmmcamera_s5k5e8.so            798384 B   ELF32 ARM, stripped
libmmcamera_qtech_ov13855_eeprom.so / ..._s5k5e8_eeprom.so
```

已保存到 `tools/vendor-libs/`。

分析结论：

| 项 | 值 |
|---|---|
| 模块名 | `qtech_ov13855`（.data 0x4008 的字符串） |
| I2C 写地址 | `0x6c`（即 7 位地址 0x36） |
| 导出函数 | `sensor_open_lib`(0xac0)、`ov13855_qtech_calculate_exposure`(0x7e8)、`ov13855_qtech_fill_exposure_array`(0x8b0) |
| 代码规模 | `.text` 仅 0x1ad0 (6.8 KB)，其余 780 KB 全是 `.data` 表 |
| 字符串 | 只有 3 条，无调试符号 |

**关键障碍**：`sensor_lib_t` 结构体 ABI 头文件（`msm_camsensor_sdk.h` 的 sensor SDK 版本）
不在小米内核源码里，只有内核侧 UAPI，所以无法直接按字段解码 `.data` 里的
power settings / init settings 指针表。下一步需要：找 msm-4.4 的 sensor SDK 头
（`msm_camera_sensor_lib.h`）或按已知 ABI 手工推断字段偏移。

**目前还缺的**：camss 在 sdm660 上的实际出图验证（主线无先例），
以及 CSI lane / csiphy 编号（推测后置 csiphy0、前置 csiphy2）。
### 14.7 恢复点（2026-10-25 00:50）

`/root/restore-20261025/`：

| 文件 | 内容 |
|---|---|
| `boot-r7-good.img` (64 MB) | 当前可用 boot 分区整包 |
| `configs.tar.gz` | Xorg 配置、systemd 单元、会话脚本、ALSA UCM |
| `user-config.tar.gz` | XFCE 面板/桌面/自启动 |
| `README.txt` | 恢复命令 |

恢复：`dd if=boot-r7-good.img of=/dev/disk/by-partlabel/boot bs=4M`，再解包 configs、`systemctl daemon-reload`。

另外给开机延迟旋转加了**重试 + 竖屏回退**：旋转后校验 `xrandr` 是否为 1920x1200，
失败重试一次，仍失败则转回竖屏，避免开机黑屏无人可救。
### 14.8 夜间验证清单（2026-10-25 00:55）

| 功能 | 状态 | 证据 |
|---|---|---|
| 触摸 | ✅ | 用户实测光标在手指下；矩阵随旋转自动切换 |
| 显示 | ✅ | 1920×1200 横屏；竖屏 121 FPS / 横屏 16 FPS |
| 声音 | ✅ | TAS2557 主 MI2S；UCM Speaker 路由；当前静音待 07:00 |
| 自动亮度 | ✅ | `457 lx -> 255/255`，暗处 `0 lx -> 43/255`，曲线 1–200 lx |
| 蓝牙 | ✅ | 控制器 Powered，5 秒扫到周边设备 |
| Wi-Fi | ✅ | wlan0 UP 192.168.1.29/24 |
| 中文输入 | ✅ | fcitx5 + chinese-addons，DefaultIM=pinyin，XIM_SERVERS=@server=fcitx |
| 办公软件 | ✅ | LibreOffice 25.8.7.3（中文）、zathura、mpv 等 |
| 内核日志 | ✅ | 仅有已知无害项（psci firmware bug、BTF 校验、传感器固件回退） |
| 恢复点 | ✅ | `/root/restore-20261025/` |

未验证/待定：内置摄像头、横屏流畅度优化、休眠/唤醒、USB OTG 键鼠。
### 14.9 摄像头寄存器表已提取（2026-10-25 01:00）

夜间最有价值的进展：**从 vendor 驱动库里把 OV13855 的寄存器表解出来了**。

- 表格式：8 字节/项 `{u16 reg, u16 val, u16 delay_ms, u16 data_type}`
- 锚点：`0x0103 = 0x01`（软复位，delay 5 ms）
- OV13855 init 表 **208 项**（PLL 0x0300–0x0312 等）
- 7 张模式表（每张 36 项），覆盖三种输出：

  | 模式 | 分辨率 |
  |---|---|
  | a1/a2 | 4224 × 3136（13 MP） |
  | b1/b2/b3 | 2112 × 1568（2 MP binning） |
  | c1/c2 | 1024 × 768 |

- I2C 写地址 **0x6c（7 位 0x36）**
- S5K5E8 5 张 60 项表，偏移与 OV13855 相同（共骨架）

产物：

```
tools/camera-re/ov13855_tables.json  结构化
tools/camera-re/ov13855_tables.h     C 头文件（可直接编译）
tools/camera-re/s5k5e8_index.json    前置摄像头表索引
tools/camera-re/README.md            方法与后续缺口
tools/vendor-libs/*.so               原始驱动库
```

仍缺：上电时序（regulator/GPIO/MCLK）、CSI lane 数、camss 出图验证。
### 14.10 摄像头硬件参数全部拿到（2026-10-25 01:15）

**重大更正**：之前说"MIUI DTB 里没有 camera 节点"是**错的**——当时只按 `ov13855`/`s5k5e8`
字符串搜。实际上 DTB 里完整保留了 `qcom,camera@0/1/2`、`qcom,eeprom@N`、`qcom,actuator@N`
节点，供电/GPIO/MCLK 全在里面。

后置 OV13855（csiphy0/csid0，4 lane，CCI master 0，I2C 0x6c）：

```
MCLK 24MHz      TLMM GPIO 32
RESET           TLMM GPIO 46 (active low)
STANDBY         TLMM GPIO 44
cam_vio 1.8V    pm660_l11
cam_vana 2.8V   固定 regulator，使能 TLMM GPIO 51
cam_vdig 1.2V   固定 regulator，使能 PMIC GPIO 4（输入 pm660_l13）
cam_vaf 2.8V    固定 regulator，使能 TLMM GPIO 50（VCM bu64297）
```

前置 S5K5E8（csiphy2/csid2，2 lane，CCI master 1）：

```
MCLK 24MHz      TLMM GPIO 33
RESET           TLMM GPIO 52
cam_vio 1.8V    pm660_l11
cam_vana 2.8V   固定 regulator，使能 TLMM GPIO 49
cam_vdig 1.8V   pm660_l13 + 使能 PMIC GPIO 3
```

原始 DT 片段存于 `tools/camera-re/miui-camera-dt.txt` 与 `miui-camera-regulators.txt`。

现在摄像头四要素齐了：**寄存器表 + 上电时序 + CSI 参数 + I2C 地址**，
只剩「写 V4L2 驱动 + camss DTS + 上机验证」。
### 14.11 OV13855 驱动已写出并编译通过（2026-10-25 01:05）

基于主线 `ov13858.c`（同系列 13MP）派生，用我们逆向出的寄存器表替换：

- 新增 `drivers/media/i2c/ov13855.c`（约 37 KB）
- Kconfig: `CONFIG_VIDEO_OV13855`；Makefile: `ov13855.o`
- 寄存器表 = vendor init（208 项）+ 每模式 delta（36 项），三种模式：
  - 4224×3136（VTS 0x0c8e）
  - 2112×1568（VTS 0x0c8e）
  - 1024×768（VTS 0x0430）
- link frequency：540 MHz（1080 Mbps/lane，4 lane，PPL 4488）
- PLL 表用 vendor 的 0x0300–0x0315 值

构建结果：`r10` 内核镜像与模块已生成，包内含

```
usr/lib/modules/7.0.14-sdm660/kernel/drivers/media/i2c/ov13855.ko.zst
usr/lib/modules/7.0.14-sdm660/kernel/drivers/media/usb/uvc/uvcvideo.ko.zst
```

> r10 同时包含 UVC（r9 的功能），是 r9 的超集；部署 r10 即可两者兼得。
> 产物：`tools/boot-r10.img`、`tools/modules-r10.tar.gz`（部署需要重启）。

已知问题：编译时有一个 `array index 1 past the end` 警告（因为 link freq 只有 1 项而
ov13858 的代码里还有 `NUM_OF_LINK_FREQS - 1` 的用法），仅警告不影响加载。

**还差 camss 设备树**：没有 DTS 节点，模块不会 probe。下一步写 clover 的
`&camss`/`&cci`/`&cci_i2c0` 节点 + sensor 节点（供电参考 14.10 的表）。
### 14.12 摄像头驱动 + 设备树已进入内核 r14（2026-10-25 01:17）

**驱动补上上电时序**：`ov13858.c` 是 Intel ACPI 风格（假设设备已被 ACPI 上电），
直接套用会在 clover 上永远读不到芯片。已按 `ov8856.c` 的做法补：

- `struct ov13855` 增加 `xvclk` / `supplies[3]` / `reset_gpio`
- `ov13855_power_on/off()`：clk → reset 拉高 → regulator_bulk_enable → reset 拉低
- probe：`devm_v4l2_sensor_clk_get_legacy(dev, "xvclk", ...)`、`devm_regulator_bulk_get`、
  `devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_HIGH)`
- probe 里先上电再读 chip id，读完再断电（原驱动没有这一步）
- `start_streaming` 上电、`stop_streaming` 断电
- 修了 `usleep_range` 缺 `<linux/delay.h>`、以及 link-freq 数组越界警告

**设备树**（`0007-...clover-camera.patch`）：

- 两个 fixed regulator：
  - `cam_avdd_2v8`：GPIO 51 使能，2.8 V
  - `cam_rear_dvdd_1v2`：PMIC GPIO 4 使能，1.2 V（输入 `vreg_l13a_1p8`）
- `&camss { status = "okay"; ports { port@0 { csiphy0_ep } } }`
- `&cci { status = "okay"; }`
- `&cci_i2c0 { ov13855: camera@36 { ... } }`：
  - `reset-gpios = <&tlmm 46 GPIO_ACTIVE_LOW>`
  - `clocks = <&mmcc CAMSS_GP0_CLK>`（24 MHz）
  - `dovdd = vreg_l11a_1p8`、`avdd = cam_avdd_2v8`、`dvdd = cam_rear_dvdd_1v2`
  - `link-frequencies = <540000000>`、`data-lanes = <1 2 3 4>`

**构建验证**：r14 内核 + DTB 均成功；反编译 DTB 确认存在

```
camera@36 { compatible = "ovti,ov13855"; reg = <0x36>;
            reset-gpios = <&tlmm 46 GPIO_ACTIVE_LOW>; ... }
```

产物：`tools/boot-r14.img`、`tools/modules-r14.tar.gz`（r14 = driver + DTS + UVC，
是 r9/r10 的超集）。**部署需要重启**。

未验证/风险点：
- `data-lanes` 映射（MIUI 的 LaneAssign 0x4320 可能对应 <0 2 3 4>，先用 <1 2 3 4>）
- `CAMSS_GP0_CLK` 是否真能输出 24 MHz 给 sensor
- camss 本身能否出图（主线无先例）
### 14.13 其它硬件盘点（2026-10-25 01:20）

装了 `i2c-tools` / `v4l-utils` 后做了一次设备盘点，比旧文档记录的好：

| 设备 | 节点 | 状态 |
|---|---|---|
| 霍尔传感器 | `input3: gpio-hall-sensor` | ✅ 存在 |
| 耳机插孔检测 | `input6: Xiaomi Mi Pad 4 Headset Jack` | ✅ 存在 |
| 光线/接近 | `iio:device2: qcom-smgr-prox` | ✅ 自动亮度正在用 |
| 加速度计 | `iio:device3: qcom-smgr-accel` | ✅ 节点在，数据走 IIO buffer |
| 陀螺仪 | `iio:device4: qcom-smgr-gyro` | ✅ 同上 |
| 磁力计 | `iio:device5: qcom-smgr-mag` | ✅ 同上 |
| 触摸 | `input4: Goodix Capacitive TouchScreen` | ✅ |
| 电源键/音量键 | `input0/1` + `input2: gpio-keys` | ✅ |
| TAS2557 | i2c-1 @4c/@4e (UU) | ✅ |
| 背光 LP8556 | i2c-2 @2c (UU) | ✅ |
| 触摸 GT9110 | i2c-0 @5d? (UU) | ✅ |

注意：smgr 传感器**没有直接的 raw 属性**，只有 `buffer`/`scan_elements`，
数据要通过 IIO buffer 读（自动亮度服务就是这么做的）。
如果以后要做「自动旋转」，需要装 `iio-sensor-proxy` 并让桌面消费它。

新增工具脚本：`tools/camera-bringup.sh`（摄像头上机检查清单：
模块加载 → probe 日志 → cci 设备 → /dev/video* → media-ctl 拓扑 → 抓帧）。
### 14.14 关键修复：CCI 总线驱动没编译（r15）

排查 camera 依赖时发现：

```
# CONFIG_I2C_QCOM_CCI is not set
```

CCI 是摄像头专用的 I2C 控制器。**没有它，`&cci` 节点不会绑定，ov13855 永远不会 probe**——
如果直接部署 r14，摄像头上机必然失败，而且报错会很有迷惑性（sensor 完全没出现）。

已改为 `CONFIG_I2C_QCOM_CCI=m`，重新构建 **r15**，现在三个模块齐了：

```
drivers/i2c/busses/i2c-qcom-cci.ko.zst
drivers/media/i2c/ov13855.ko.zst
drivers/media/platform/qcom/camss/qcom-camss.ko.zst
```

另外确认：`csiphy_res_660[].regulators = {}`，即 sdm660 的 csiphy 不需要额外
regulator，我们的 DTS 不用加 `vdda-supply`。

产物：`tools/boot-r15.img`（25.8 MB）、`tools/modules-r15.tar.gz`（14.0 MB）。
部署脚本：`tools/pad_deploy_kernel.sh <ver>`（备份 boot → 写入 → 校验 md5 → 装模块 → 重启）。
### 14.15 lane 映射与 MCLK 校验（r16）

读 `camss.c` 的端点解析代码，确认了两件事：

```c
csd->interface.csiphy_id = vep.base.port;          /* port 号 = csiphy 编号 */
lncfg->clk.pos  = mipi_csi2->clock_lane;
lncfg->num_data = mipi_csi2->num_data_lanes;
lncfg->data[i].pos = mipi_csi2->data_lanes[i];
```

1. **csiphy 用的是它自己端点上的 `data-lanes`**（不是 sensor 端的）。参考主线
   ov8856 的例子，csiphy 端写 `<0 1 2 3>`，sensor 端写 `<1 2 3 4>`。
   之前两边都写成 `<1 2 3 4>` 是错的，已改（r16）。
2. **MCLK 可用**：`mmcc-sdm660.c` 里 `ftbl_camss_gp0_clk_src` 明确包含
   `F(24000000, P_GPLL0_DIV, 1, 2, 25)`，所以 `assigned-clock-rates = <24000000>`
   能真正配出 24 MHz。

r16 = CCI + ov13855 + camss + 修正后的 lane 映射 + UVC。
产物：`tools/boot-r16.img`、`tools/modules-r16.tar.gz`。

> MIUI 的 `LaneAssign 0x4320` 按文档是"PHY data0←sensor0, data2←2, data3←3,
> data4←4，lane1 保留给 clock"，与主线 DT 的 1-based 编号不同。若 r16 仍不出图，
> 下一个要试的是 sensor 端 `<0 2 3 4>` + `clock-lanes = <1>`。
### 14.16 LibreOffice 横屏实测通过（2026-10-25 01:40）

用 `systemd-run --user` 启动 Writer 并截图验证：

```
窗口：1920×1149（横屏全屏）
界面：中文（文件/编辑/视图/插入/格式/样式/表格/表单/工具/窗口/帮助）
字体框：Noto Serif CJK SC，字号五号
欢迎向导：正常显示中文
```

首次启动到窗口完全渲染约 **25 秒**（含欢迎向导），后续启动会快很多。
内存占用峰值后释放，桌面仍剩 2.4 GB 可用。

结论：**办公文档这条路是通的**——LibreOffice 在这个「软件渲染 + 横屏」环境下
可以正常显示和操作，不存在渲染错乱/空白窗口的问题。

截图存档：`tools/lo3.png`（1920×1200 原始分辨率）。
### 14.17 前置 S5K5E8 寄存器表也提取了（2026-10-25 01:40）

从 `libmmcamera_s5k5e8.so` 按同样方法提取出 5 张表（每张 60 项），
格式与 OV13855 相同（`{u16 reg, u16 val, u16 delay, u16 dtype}`）：

```
mode_a 0136:0018 0137:0000 0305:0006 0306:0018 0307:00a8 0308:0034 ...
mode_c 0136:0018 0137:0000 0305:0006 0306:0014 0307:00a8 0308:001f ...
```

`0x0305-0x0309` 是 PLL，`0x0136/0x0137` 是时钟配置，符合三星 sensor 的寄存器布局。
存于 `tools/camera-re/s5k5e8_tables.json`。

前置摄像头优先级低于后置，等 OV13855 上机验证通过后再做。
### 14.18 屏幕键盘实测与调优（2026-10-25 01:45）

启动 onboard 验证：

- 默认尺寸 **700×205** —— 在 1920×1200、150 DPI 下按键只有 ~30 px，手指点不准
- 改成 `onboard -s 1500x420` 后按键约 **90 px**，横屏下适合手指输入

已把应用菜单里的「屏幕键盘」改成带尺寸参数并支持开关：

```sh
# ~/.local/bin/tablet-osk
if pgrep -x onboard; then pkill -x onboard; else exec onboard -s 1500x420; fi
```

截图存档：`tools/osk2.png`（1500×420 大键盘）、`tools/osk.png`（默认小键盘对比）。
### 14.19 PDF 阅读：从"能打开"到"可舒服阅读"（2026-10-25 01:50）

验证了完整办公链路：**文本 → LibreOffice 导出 PDF → 阅读器打开**。

- `soffice --headless --convert-to pdf` 生成 `/tmp/testdoc.pdf`（中文正常）
- zathura：能打开，但默认窗口 800×600、页面缩放偏小，且没有"打开即最大化"的办法
- **改用 evince**（触摸友好、有缩略图/搜索/缩放控件）

evince 默认窗口只有 760×610，因此做了个启动器：

```sh
# ~/.local/bin/tablet-pdf
( sleep 2; wmctrl -r "$(basename "$1")" -b add,maximized_vert,maximized_horz ) &
exec evince "$@"     # 必须前台 exec，否则 systemd 单元退出会带走子进程
```

并把 `tablet-pdf.desktop` 设为 `application/pdf` 的默认处理器。

实测结果：

```
窗口：1920×1173（最大化）
缩放：100%，中文清晰可读
工具栏：页码、缩放、搜索、旋转、侧栏缩略图
```

截图：`tools/pdf5.png`。
### 14.20 浏览器实测 + 修掉默认浏览器指向错误（2026-10-25 01:52）

实测 `firefox-esr`：

```
启动到窗口：12 秒
窗口：1920×1149（自动最大化）
渲染：中文标题/正文/列表全部清晰，URL 栏、标签页、工具栏正常
```

**发现并修复一个配置错误**：

```
xdg-settings get default-web-browser  →  firefox.desktop   ← 这个文件不存在！
```

系统里装的是 `firefox-esr.desktop`，`/usr/bin/firefox` 也不存在（只有 `firefox-esr`）。
也就是说之前从菜单/链接打开浏览器会失败。已修正：

```sh
xdg-settings set default-web-browser firefox-esr.desktop
xdg-mime default firefox-esr.desktop text/html
xdg-mime default firefox-esr.desktop x-scheme-handler/http  (and https)
# ~/.config/xfce4/helpers.rc  →  WebBrowser=firefox-esr
```

截图：`tools/ff3.png`。
### 14.21 恢复点 v2（2026-10-25 02:00）

`/root/restore-20261025/` 更新到当前状态（v1 保留）：

| 文件 | 内容 |
|---|---|
| `boot-r7-good.img` | 当前可用 boot 分区（r7，含 TAS2557 主 MI2S） |
| `configs-v2.tar.gz` | Xorg、systemd 单元、会话脚本、ALSA UCM、`/etc/tablet` |
| `user-config-v2.tar.gz` | XFCE 面板/桌面、autostart、mimeapps、zathura、PDF/OSK/旋转启动器 |
| `tools-v2.tar.gz` | `tablet-health.sh`、`camera-bringup.sh`、部署脚本 |

同时拷贝到 Windows 工作区 `backup/`（不含 64 MB 的 boot 镜像）。

恢复命令写在 `README.txt`。
### 14.22 显示稳定性核查（2026-10-25 02:00）

统计本次开机的 DPU 提交超时：

```
总计 324 次 —— 全部集中在 00:36:57 ~ 00:37:09（会话重启 + 延迟横屏旋转那一刻）
00:37:09 之后到现在（01:55，约 1 小时 18 分）: 0 次
```

这段时间里跑了 LibreOffice Writer、Firefox、evince、onboard、多次截图，
**没有任何新的 DPU 错误**。说明：

- 超时只发生在"旋转瞬间"（X 重新提交 framebuffer 尺寸时）
- 稳态显示完全正常，不会随机黑屏/花屏

这也解释了用户之前"开机黑屏"的体验：旋转发生在 DPU 还没稳定的时刻，
一次失败就卡死；现在延迟 15 秒 + 失败回退竖屏，稳态不再触碰 DPU 的敏感路径。
### 14.23 横屏性能根因定位（2026-10-25 02:05）

下载了 xorg-server 21.1.25 源码（Debian 镜像，9 MB），确认了旋转的完整路径：

1. `drmmode_display.c`: `xf86CrtcRotate()` 分配 `crtc->rotatedPixmap`（DRM dumb buffer）
2. 每次 damage: `xf86RotateCrtcRedisplay()`（`hw/xfree86/modes/xf86Rotate.c`）
   ```c
   SetPictureTransform(src, &crtc->crtc_to_framebuffer);
   CompositePicture(PictOpSrc, src, NULL, dst, ...);
   ```
3. pixman 走**通用仿射变换取像素**路径（`bits_image_fetch_transformed`）：
   每个目标像素反算源坐标、跨行取点。

实测吞吐 ≈ **37 Mpx/s**（2.3 Mpx / 62 ms），与单线程逐像素 gather 完全吻合。
→ 纯 CPU 瓶颈，与 GPU/显存无关。

**结论**：`-depth 16`、`--scale-from`、TearFree、关合成器都动不了根因；
唯一性价比合理的方向是给 `xf86RotateCrtcRedisplay` 加"纯 90°/180°/270°"快速路径
（分块转置 + 顺序写），预计 16 → 45–80 FPS。

完整方案、构建步骤、回退方法写在 `tools/perf/ROTATION-PERF.md`。
需要重编 xorg-server 并重启 X，**等用户在场再做**。
### 14.24 驱动模块预检：符号依赖已确认（r17 可加载）

在**不重启**的前提下，把 r17 的 `ov13855.ko` 解出来直接在 r7 上 `insmod` 试加载：

```
vermagic: 7.0.14-sdm660 SMP preempt mod_unload aarch64   ← 与运行内核一致
insmod: Unknown symbol v4l2_async_register_subdev_sensor
        Unknown symbol v4l2_async_unregister_subdev
        Unknown symbol v4l2_fwnode_device_parse
```

这三个符号来自 `v4l2-async` / `v4l2-fwnode`。r7 上它们是**模块**且没加载，所以失败。

关键结论：**r17 里这三个符号是编进内核的**。验证方法：解压 r17 的 vmlinuz，
直接搜符号字符串：

```
kernel image 32696832 bytes
v4l2_async_register_subdev_sensor -> 2   ← 存在
v4l2_fwnode_device_parse          -> 3
v4l2_async_unregister_subdev      -> 2
qcom-camss -> 0                          ← camss 仍是模块（符合预期）
```

原因：`CONFIG_VIDEO_QCOM_CAMSS=m` 会 `select VIDEO_DEV`，把 videodev/v4l2-async/
v4l2-fwnode 强制成 builtin（Kconfig 的 select 压过 =m），所以 r17 的模块树里
看不到这三个 .ko——这不是打包缺失，而是编进内核了。

→ **部署 r17 后 ov13855.ko 的符号依赖一定满足**，摄像头能否 probe 只剩 DTS/硬件层面。
### 14.25 设备树预检：摄像头供电与 GPIO 无冲突（2026-10-25 02:25）

反编译 r16/r17 的 DTB，逐个核对相机相关的 regulator 与 GPIO：

```
cam-avdd-2v8 {
    regulator-min/max-microvolt = <0x2ab980>;   /* 2 800 000 µV */
    enable-active-high;
    gpio = <&tlmm 0x33 0x00>;                  /* TLMM GPIO 51, active high */
    vin-supply = <&vph_pwr>;
};
cam-rear-dvdd-1v2 {
    regulator-min/max-microvolt = <0x124f80>;   /* 1 200 000 µV */
    enable-active-high;
    gpio = <&pm660_gpios 0x04 0x00>;           /* PMIC GPIO 4 */
    vin-supply = <&vreg_l13a_1p8>;
};
camera@36 { reset-gpios = <&tlmm 0x2e 0x01>; }  /* GPIO 46, active low */
```

冲突检查：

- DTB 里只有 camera@36 引用 GPIO 46，只有 avdd regulator 引用 GPIO 51
- clover DTS 的 `pins = ` 列表里没有 44 / 46 / 51 → 没有 pinctrl 抢占
- `pm660_gpios` 的 `gpio-ranges` 是 13 个脚，GPIO 4 在范围内

→ 上电时序所需的 regulator 与 GPIO 在设备树层面完全自洽，不会出现
「regulator 注册失败 → sensor probe 永久 defer」这类问题。
### 14.26 部署脚本加固（2026-10-25 02:30）

部署是今晚唯一有"变砖"风险的写操作，脚本重写成带多重防护：

1. **尺寸校验**：镜像 24.6 MB vs boot 分区 64 MB（`blockdev --getsize64`），
   太小（<8 MB）或超过分区直接中止
2. **格式校验**：检查偏移 0 是否是 `ANDROID!`（实测 r16/r17 都是）
3. **完整备份 + 备份校验**：`/root/boot-before-<ver>.img` 必须是整整 64 MB
4. **写后全量 md5 回读校验**（不是只查前 4 MB）：
   - 不匹配 → **自动用备份回写 boot**，然后退出，不重启
5. **模块安装后检查** `ov13855.ko.zst` 是否存在，缺了就提示
6. `NO_REBOOT=1` 可以先写不重启

实测预检：

```
boot part size: 67108864
img size:       25812992
magic:          ANDROID!
syntax-ok
```

→ 部署路径已经是"失败也能自动回滚"的状态。
### 14.27 摄像头攻坚记录（2026-10-25 07:00-08:00，r18→r24）

**已打通的部分**（每一步都有证据）：

1. 模块加载：先清掉上一版残留的 5 个模块（`mc`、`videodev`、`v4l2-async`、
   `v4l2-fwnode`、`v4l2-dv-timings` —— r18 起它们已编进内核），否则 `modprobe`
   报 `duplicate symbol __media_device_register` / `Exec format error`。
2. `qcom_camss` 注册成功：出现 `/dev/media0` + 8 个 `/dev/video*`（qcom-camss）。
3. CCI 总线正常：`i2c-3 = Qualcomm-CCI`，模块 **EEPROM 在 0x50 有应答**。
4. 三个 regulator 全部使能：
   - VIO `pm660_l11` 1784 mV（use count 4）
   - AVDD `cam_avdd_2v8` ← TLMM **GPIO 51**（debugfs 显示 out high）
   - DVDD `cam_rear_dvdd_1v2` ← **PM660L GPIO 4**（曾经错写成 PM660 GPIO，已修）
5. 复位：`gpio46` 极性修正为 **active high**，释放时实测 out low。
6. MCLK：`camss_gp0_clk` / `camss_gp1_clk` 都能开到 24 MHz（clk_summary 可见），
   `gpio32` 已切到 `cam_mclk` 功能（func1）。

**仍失败**：`ov13855 3-0036: failed to find sensor: -5`（I2C 无应答），
i2cdetect 扫描 0x00-0x7f 只有 0x50（EEPROM），两条 CCI 总线都扫过。

**下一步怀疑**：这块板后摄用的是 **MCLK2**（厂商标签 CAMIF_MCLK2，GPIO32），
而主线 mmcc-sdm660 只实现了 GP0/GP1 两路 24 MHz 输出。若 pad 32 硬连到第三路，
则需要给时钟驱动补 `camss_gp2_clk`（rcg + branch + dt-bindings ID）。

其它已排除：供电顺序、PWDN(GPIO44) 两种电平、两条 CCI 总线、复位极性。
### 14.28 OTG 打通（2026-10-25 07:55）

用**带电源的 USB hub** 实测：

```
usb 1-1: Product: USB2.1 Hub (GenesysLogic) 4 ports
usb 1-1.1: Disk 20, 62.9 GB
scsi host0: usb-storage -> /dev/sda, sda1 (exfat 58.6G)
```

挂载、读、写全部正常（root 与普通用户都验证过）：

```
/dev/sda1 on /mnt/usb type exfat (rw,...)
write OK / user write OK
```

**自动挂载**也配好了：

1. `udisks2` 已安装并运行，`thunar-volman` 已启用
2. `xfconf`: `thunar-volman /automount-drives/enabled = true`、
   `/automount-media/enabled = true`
3. 新增 polkit 规则 `/etc/polkit-1/rules.d/50-udisks-wheel.rules`：
   允许 `wheel` 组直接挂载/卸载可移动介质（这台平板的 X 会话被注册成
   greeter 会话，polkit 不认它是"本地活动会话"，所以需要这条规则）

实测 `udisksctl mount -b /dev/sda1` → `/run/media/user/FAE1-02DA`，
普通用户可读写。

**唯一限制**：平板自身不给外设供 5V（主线没有 PM660L SMB2 的 OTG 升压驱动），
所以必须用带电源的 hub；写 PMIC 驱动才能脱离 hub。
### 14.29 OTG 5V 升压打通（2026-10-25 08:30）

给 `qcom_smbx.c`（PM660 SMB2 充电器驱动）加了 OTG 升压控制：

```
SMB_OTG_CMD_OFF = 0x140   /* OTG_BASE 0x1100 + 0x40, bit0 = OTG_EN */
SMB_OTG_CFG_OFF = 0x153   /* bit1 = OTG_EN_SRC_CFG，清 0 表示由命令寄存器控制 */
```

上电流程：清 `OTG_CFG.OTG_EN_SRC_CFG` → 置 `CMD_OTG.OTG_EN`；关闭则清 `OTG_EN`。
寄存器定义取自 LineageOS sdm660 内核 `smb-reg.h`（OTG_BASE 0x1100、CHGR_BASE 0x1000）。

驱动的 sysfs 接口（platform device 上）：

```
/sys/devices/platform/soc@0/800f000.spmi/.../charger@1000/otg_vbus   (rw, 0/1)
```

**实测**：写 1 后 U 盘**不用 hub 直接枚举**：

```
usb 1-1: Disk 20
usb-storage -> sd 0:0:0:0: [sda] 58.6 GiB, sda1
```

udisks 自动挂载到 `/run/media/user/FAE1-02DA`，普通用户读写正常。
写 0 后设备立即断开（再次写 1 会重新枚举），说明升压确实受控。

用户态配套：

- `/usr/local/bin/tablet-otg on|off|status|auto`
  （`auto`：充电器在线时关，否则开；读 `/sys/class/power_supply/pm660-charger/online`）
- `tablet-otg.service`：开机自动 `auto`（已在 multi-user.target 启用）
- `~/.local/bin/tablet-otg-toggle` + 桌面项「USB OTG 供电开关」

注意：一开始加了 udev 规则做"插充电器自动关"，但它会在每次 power_supply
事件时把用户手动关闭的升压又打开，已删除；现在只有开机 auto + 手动开关。

补丁：`0010-power-supply-qcom-smbx-add-otg-vbus-control.patch`（r27）。

### 14.30 摄像头卡点（08:20）

`ov13855` 仍然 `failed to find sensor: -5`，已排除：三种上电顺序、PWDN(GPIO44)
两种电平、GP0/GP1 两路时钟、复位极性、两条 CCI 总线、地址 0x36/0x20/0x3c 等。
供应商时钟驱动确认 sdm660 **只有 GP0/GP1** 两路 MCLK（我加的 GP2 是错的，
r25 因此无法启动，已用 fastboot 刷回 r24 救回）。

EEPROM(0x50) 有应答说明 CCI 和模块 I2C 通路正常，但 sensor 芯片不应答，
需要硬件级诊断（示波器量 MCLK/复位/AVDD）或对照 MIUI 内核验证硬件本身。
### 14.31 完整备份与还原点（2026-10-25 09:05）

三份备份，全部校验一致（md5 `46e01b5055e94e2f636a38f22743fd6f`，1 632 113 657 字节）：

1. 设备内部 `/var/backup/rootfs.tar.zst`
2. U 盘 `pmos-backup-20261025/`
3. 电脑 `backup/pad-full-20261025/`

同时备份：`boot-r26-current.img`（64 MB 整块 boot）、`gpt.dump`（分区表）、
`configs.tar.gz`（/etc + systemd + polkit + 桌面项 + home）、`packages.txt`。

**备份过程中的两个教训**：

- pmOS 默认的 `tar` 是 busybox，不支持 `--one-file-system`，会直接打印用法并退出
  （导致第一次只写出 13 字节）→ 先 `apk add tar` 换成 GNU tar。
- 从 SSH 会话里 `nohup ... &` 启动的后台任务会随会话结束被 systemd 杀掉，
  备份两次被截断在 ~500 MB 且 `zstd -t` 报 `premature end`
  → 必须用 `systemd-run --unit=... --collect` 跑独立单元。

**MIUI 对照实验方案**见 `MIUI-CAMERA-EXPERIMENT.md`：
三级回滚（刷回 boot / pmbootstrap 重装+恢复配置 / rootfs.tar.zst 精确还原）。
已知 MIUI system(p13)、vendor(p14) 分区完好，MIUI boot 镜像在 `artifacts/rom/miui-boot.img`。
### 14.32 灾难恢复与根因（2026-10-25 13:00-14:05）

**事件**：MIUI 对照实验后，pmOS 根文件系统被多次写入，最终损坏；靠备份恢复了两次。

**关键根因（两个，都是我的操作失误）**：

1. **镜像用普通用户制作 → 属主全错**
   `mkfs.ext4 -d <dir>` 按 **当前用户**设置所有文件属主。我第一次用 `user` 解包
   tar，导致镜像里 sudo 失去 setuid、systemd 单元属主错乱，系统 `degraded`、
   桌面起不来（greetd "greeter exited without creating a session"）。
   正确做法：**以 root 解包**（`sudo tar -xzf`），或用 `fakeroot`/`--numeric-owner`。

2. **tar 按用户名映射 uid → 家目录属主错**
   即便以 root 解包，tar 默认按 **用户名** 映射。VM 里 `user` 是 uid 1000，
   设备上是 10000 → `/home/user` 变成 1000:0，用户无法写入，无法创建会话。
   正确做法：解包时加 `--numeric-owner`。

**恢复过程中验证过的有效手段**：

- `fastboot -S 16M flash userdata <img>`：能写入（235 块全部 OKAY），但**最后一块
  的落盘确认会卡住数分钟以上**，此时中断会丢掉尾部数据 → 文件系统损坏。
- **dd 从 U 盘镜像恢复**：可靠，但需要 initramfs 能识别 U 盘。
  实测 pmOS 官方 initramfs + 自定义前段 /init **未能识别 U 盘**（无日志），
  原因未查明；最终是 fastboot 写入 + 事后在设备上修属主解决的。

**最终修复步骤（本次实际用的）**：

```
1. fastboot flash boot boot-r26-current.img
2. fastboot -S 16M flash userdata pmos-rootfs-fixed.img   （属主已修正的镜像）
3. 开机后 SSH 可用，sudo 正常
4. sudo chown -R 10000:10000 /home/user                （修 uid 映射问题）
5. sudo systemctl reset-failed && systemctl start greetd  （桌面起来）
6. sudo systemctl mask usb-signaller                      （host 模式无 UDC，属预期）
7. resize2fs 自动完成，根分区 107 GB
```

**结果**：`systemctl is-system-running = running`，0 失败服务，桌面/Xorg/XFCE 正常，
触摸旋转、自动亮度、音频路由、Wi-Fi、蓝牙全部 active，重启后依然正常。

**教训（写进流程）**：

- U 盘在 Windows 上拔之前**必须安全弹出**，否则 exFAT 只读，救援日志写不进
- 制作 rootfs 镜像必须 **root + --numeric-owner**
- fastboot 大镜像刷写后**不要急着中断**，或改用 dd

**MIUI 对照实验结果（重要）**：MIUI 内核日志显示
`ov13855_f13v10l probe succeeded`、`s5k5e8 probe succeeded`、
`msm_cci_init: hw_version = 0x10060000` —— **摄像头硬件完好**。
MIUI 设备树给出关键参数：GPIO32=MCLK2、GPIO46=RESET0、**GPIO44=STANDBY0**、
clock-rates=24 MHz、cci-master=0、cam_vio/vana/vdig 三路供电。
pmOS 侧仍失败（I2C 无应答），下一步应按这些参数重做上电时序（尤其 STANDBY）。
### 14.33 2026-10-25 收尾：新会话请先读 NEXT-SESSION.md

本次会话完成了：
1. 从备份完整恢复系统（并修好两处**我造成的**镜像属主问题）
2. 重做**正确版救援镜像 v2**（`--numeric-owner`），存入电脑 + U 盘
3. 摄像头根因定位并修复 3 项：复位极性（ACTIVE_LOW）、芯片 ID（0xd855）、
   MCLK 时钟（CAMSS_MCLK0-3 而非 GP0/1）→ **传感器成功探测**
4. 直播卡在 `Failed to start media pipeline: -32`（camss 新 pipeline API 适配问题）

详见：
- `NEXT-SESSION.md`       下一页入口（状态、路线、命令、产物清单）
- `RESTORE-PROCEDURE.md`  备份/恢复流程 + 12 条踩坑
- `CAMERA-FINDINGS.md`    摄像头完整调试记录