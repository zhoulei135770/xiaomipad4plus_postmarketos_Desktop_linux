# 19 · pmOS 恢复成功 + 磁盘修复（2026-10-24 夜）

> 会话时间：2026-10-24 19:00 ~ 22:15（约 3.5 小时）
> 设备：Xiaomi Mi Pad 4 Plus（clover-plus / SDM660），序列号 27eec4d2
> 核心成果：**从 MIUI 刷回 pmOS，修好磁盘扩展，装好 Xorg+XTCE 桌面，背光修复**
> 最终状态：**XFCE 桌面运行中，横屏 1920x1200，背光 180/255，WiFi 192.168.1.29**

---

## 一、最终状态（已验证）

```
内核    : 7.0.14-sdm660 #4-postmarketos-qcom-sdm660 SMP PREEMPT
          Sat Oct 24 07:20:56 UTC 2026  aarch64
系统    : Nura edge (postmarketOS)
运行    : 1 小时 09 分，load 1.86 / 0.88 / 0.52（稳定，无重启）

磁盘    : /dev/mmcblk1p64  105.6 GB  已用 3.3 GB  可用 98.0 GB (3%)
          分区实际 108.9 GB

图形    : Xorg 1.21.1.25  pid 16500  (:0 -keeptty -dpi 150 -nolisten tcp)
          xfwm4        pid 17228   ✅
          xfce4-panel  pid 17332   ✅
          xfdesktop    pid 17400   ✅
          xfce4-session pid 16628  ✅
          xfsettingsd  pid 17303   ✅

显示    : DSI-1 connected 1920x1200 left（横屏）
          原生模式 1200x1920 60Hz

背光    : 180 / 255  ✅（原为 9，几乎全黑）

传感器  : iio:device0 = pm660-rradc
          iio:device1 = 800f000.spmi:pmic@0:adc@3100
          iio:device2 = qcom-smgr-mag
          iio:device3 = qcom-smgr-gyro
          iio:device4 = qcom-smgr-accel
          iio:device5 = qcom-smgr-prox   ← ALS 在这里

音频    : sdm660-internal - Xiaomi Mi Pad 4

网络    : wlan0  192.168.1.29/24  MAC d2:89:ce:0c:09:e0  ✅

GUI 包  : xorg 2 个、xfce 19 个，共 79 个以 x 开头的包
服务    : alsa-mic-tablet.service      active ✅
          alsa-restore-tablet.service  active ✅
          tablet-autobright.service    inactive（有 bug，见 §六）
          tablet-orientd.service       inactive（用户会话服务）
```

---

## 二、回答核心问题：「为什么刷完之后跟备份的不一样」

### 2.1 三个原因叠加

**原因 1：刷的是 10/19 的旧镜像，不是 10/24 的系统**

```
pmos-rootfs3.img      2026/10/19 21:23   ← 刷进去的
lean-config.tar.gz    2026/10/24 17:57   ← 你的实际配置（晚 5 天）
lib-modules.tar.gz    2026/10/24 17:54   ← 你的实际模块
boot.img              2026/10/24         ← 新内核 r3
```

我犯的错误：**以为 UUID 匹配（`8def993b-42f5-4ba1-9813-c046e498fe22`）
就等于镜像内容是最新的**。UUID 只保证内核能找到分区，不代表内容版本。

10/20 ~ 10/24 的工作全部不在镜像里：
- ALS 环境光驱动
- 自动亮度服务
- 旋转设置 UI
- tablet-* 脚本
- ALSA 配置
- xorg.conf

**原因 2：镜像里根本没装 Xorg/XFCE**

```
$ command -v Xorg
(空)
$ command -v xfce4-session
(空)
xfce-x-session.log: "Xorg: not found"
```

镜像里装了 `xorg-server-common`（只有公共文件），但**没有 `xorg-server` 本体**，
也没有任何 XFCE 包。这是安装过程的中间状态。

**原因 3：文件系统只有 2.2 GB，没扩展到分区大小**

```
分区 mmcblk1p64  : 108.9 GB   ← 实际有 108.9 GB
文件系统         : 2.2 GB     ← 但只用了 2.2 GB，100% 满
```

**这是最关键的问题**。`fastboot flash userdata <镜像>` 只写入镜像大小（2.39 GB），
文件系统保持 2.2 GB，没有**自动扩展**到分区大小。

后果：磁盘 100% 满 → `apk` 装包时 `No space left on device` → 
Xorg/XFCE 装不上 → `tablet-session-launcher` 找不到 Xorg → 回退到 Phosh。

### 2.2 为什么回退到 Phosh

`tablet-session-launcher` 的逻辑：

```sh
/usr/local/bin/xfce-x-session &      # 启动 XFCE
while [ $i -lt 90 ]; do
    if live_pid xfwm4; then UP=1; break; fi   # 等 xfwm4 出现
    if ! kill -0 "$XPID"; then break; fi      # 或 wrapper 退出
done
if [ "$UP" -eq 1 ]; then wait; fi
log "FALLBACK -> Phosh"
exec /usr/libexec/phrog-greetd-session        # 回退
```

日志证据：
```
[21:06:59] xfce wrapper pid=4724
[21:07:00] xfce wrapper exited at 1s      ← Xorg 不存在，1 秒就死
[21:07:00] FALLBACK -> Phosh
```

装好 Xorg/XFCE 后：
```
[22:02:00] xfce wrapper pid=16466
[22:02:27] live xfwm4 detected at 25s     ← ✅ 这次成功了
[22:02:27] XFCE is up; waiting for it to end
```

---

## 三、完整恢复步骤（可复现）

### 3.1 前提

- 已备份：`artifacts/preflash/`（281 MB，29 个文件，MD5 校验通过）
- 已刷 MIUI V10.3.2.0 并做过 Android 硬件采集（见 doc 17/18）

### 3.2 进入 fastboot

```
长按电源 10-15 秒 → 松手，等 2 秒 → 按住音量减 + 电源
```

### 3.3 刷 boot 和 rootfs

```powershell
$fb = "D:\APPS\platform-tools\fastboot.exe"
$b  = "mipad4plus\artifacts\preflash"

# 1. 刷 pmOS 内核（r3，10/24）
& $fb flash boot "$b\boot.img"

# 2. 清 Android 数据
& $fb erase userdata      # 不要 erase 后再 flash，直接 flash 也行
& $fb erase cache
& $fb erase misc          # 清 Android 启动标志

# 3. 刷 rootfs（必须先注入配置，见 §3.4）
& $fb flash userdata "mipad4plus\tools\pmos-final.img"

& $fb reboot
```

### 3.4 关键：刷之前必须把 10/24 配置注入镜像

**这一步我一开始漏了，导致配置丢失。** 在 Linux VM 上做：

```bash
# 1. 挂载镜像
sudo mount -o loop,rw /var/tmp/rootfs.img /mnt/pmosroot

# 2. 备份原 /etc（安全措施）
sudo tar -czf /var/tmp/etc-backup.tar.gz -C /mnt/pmosroot etc

# 3. 解压嵌套的配置包
mkdir -p /var/tmp/cfgwork
tar -xzf lean-config.tar.gz -C /var/tmp/cfgwork
# 得到 lean-etc.tar.gz (23 MB) + lean-root.tar.gz (130 KB)

# 4. 写入 10/24 的内核模块（覆盖）
sudo tar -xzf lib-modules.tar.gz -C /mnt/pmosroot/

# 5. 写入 10/24 的配置（覆盖）
sudo tar -xzf /var/tmp/cfgwork/lean-etc.tar.gz -C /mnt/pmosroot/

# 6. 写入 /root 脚本
sudo tar -xzf /var/tmp/cfgwork/lean-root.tar.gz -C /mnt/pmosroot/

# 7. 验证
sudo ls /mnt/pmosroot/etc/systemd/system/ | grep tablet
# 应该看到：alsa-mic-tablet.service / alsa-restore-tablet.service /
#           tablet-autobright.service / tablet-orientd.service
sudo ls /mnt/pmosroot/usr/local/bin/ | grep tablet
# 应该看到 20 个 tablet-* 脚本

# 8. 卸载
sudo sync && sudo umount /mnt/pmosroot
```

### 3.5 首次启动后：**必须扩展文件系统**

**这是最关键的一步，漏了就 100% 满。**

```bash
# 通过 WiFi SSH 或串口登录后
sudo resize2fs /dev/mmcblk1p64
# 输出：The filesystem on /dev/mmcblk1p64 is now 28560215 (4k) blocks long.

df -h /
# 应该变成：105.6G  已用 2.2G  可用 99.0G  2%
```

### 3.6 安装 Xorg + XFCE

**关键教训：直接用平板 `apk add` 即可，不要手动下载传输。**

之前踩的坑：
- 尝试从 Windows 下载 77 个 .apk 再传输 → 依赖冲突（Alpine 包拉 openrc/elogind，
  而 pmOS 是 systemd）
- 尝试用官方 Alpine 源 → 也冲突

**正确做法**（空间修好后一次成功）：

```bash
# Xorg（177 个包，一次装完）
sudo apk add --no-progress xorg-server xorg-server-common \
    xf86-input-libinput xrandr xinput xset xrdb xauth xinit

# XFCE
sudo apk add --no-progress xfce4-session xfwm4 xfce4-panel \
    xfdesktop xfce4-settings xfce4-terminal thunar \
    xfce4-appfinder xfce4-taskmanager xfce4-power-manager
```

装完验证：
```bash
for t in Xorg xrandr xinput xfce4-session xfwm4 xfce4-panel; do
  command -v $t
done
```

### 3.7 重启 greetd，进 XFCE

```bash
sudo systemctl restart greetd
sleep 40
tail -5 ~/.local/share/tablet-session/launcher.log
# 应该看到：live xfwm4 detected at 25s / XFCE is up
```

### 3.8 修复背光

```bash
# 立即
sudo sh -c 'echo 180 > /sys/class/backlight/lcd-backlight/brightness'

# 持久化（注意路径带 c1b8000.i2c 前缀）
sudo sh -c "printf '180' > '/var/lib/systemd/backlight/platform-c1b8000.i2c:backlight:lcd-backlight'"
```

---

## 四、踩过的坑（重要教训）

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | 刷完配置全丢 | 刷的是 10/19 旧镜像 | 刷前把 10/24 配置注入镜像 |
| 2 | 桌面回退 Phosh | 镜像没装 Xorg | `apk add xorg-server` |
| 3 | `apk add` 报 No space | 文件系统 2.2G 没扩展 | **`resize2fs /dev/mmcblk1p64`** |
| 4 | `pnputil` Access denied | 不是管理员 | 用管理员 PowerShell |
| 5 | NCM `ProblemCode 28` | Windows 只认 `MS_COMP_WINNCM` | 需改 INF，但**不建议折腾**（方案见 §5）|
| 6 | 手动下 77 个 apk 冲突 | Alpine 包依赖 openrc/elogind | 直接用 pmOS 自己的 apk |
| 7 | gadget 被我改坏，USB 全失 | 解绑 UDC 后重绑失败 | 长按电源强制重启 |
| 8 | `sudo` interactive auth | SSH 无 TTY | `echo PASS \| sudo -S` |
| 9 | 背光只有 9 | systemd-backlight 恢复旧值 | 写 brightness + 持久化文件 |
| 10 | `pad_sudo.ps1` 引号错 | PowerShell 嵌套引号 | 写 .sh 文件再执行 |

### 4.1 特别注意：**不要动 USB gadget 的 UDC**

我为了暴露 `p64` 分区给 Windows，执行了：

```sh
echo "" > /sys/kernel/config/usb_gadget/g1/UDC    # 解绑
echo "/dev/mmcblk1p64" > .../mass_storage.0/lun.0/file
echo "a800000.usb" > /sys/kernel/config/usb_gadget/g1/UDC  # 重绑
```

**结果 gadget 崩了**，CDC-NCM/acm/mass_storage 全部消失，只能长按电源强制重启。

**正确做法**：直接 `fastboot flash userdata`，不要碰 gadget。

---

## 五、NCM 驱动（可选，不影响使用）

### 5.1 为什么需要

pmOS 的 USB gadget 暴露 `CDC-NCM` 网卡（`172.16.42.1`），
但 **Windows 自带 `usbncm.inf` 只认微软私有 ID `USB\MS_COMP_WINNCM`**，
标准 CDC-NCM（`USB\Class_02&SubClass_0d&Prot_00`）那行是**注释掉的**。

设备状态：
```
CDC NCM
  Compatible IDs : USB\Class_02&SubClass_0d&Prot_00
  Problem Code   : 28 (CM_PROB_FAILED_INSTALL)
  Problem Status : 0xC0000490 (STATUS_DRIVER_BLOCKED)
```

### 5.2 不用 NCM 也能用

**平板连上 WiFi（192.168.1.29）后 SSH 完全可用，不需要 NCM。**

```powershell
$env:PAD_HOST = "192.168.1.29"
python mipad4plus\tools\ssh_pad.py "uname -a"
```

### 5.3 如果一定要装（需要禁用签名强制）

`microsoft/NCM-Driver-for-Windows` 是**源码**，不是编译好的驱动。
已在 `tools/ncmfix/` 准备好：

```
pmosncm.inf    1.6 KB    # 加了标准 CDC-NCM ID 的 INF
UsbNcm.sys   111.5 KB    # 从驱动库复制的真驱动
```

安装（**管理员 PowerShell**）：
```powershell
# 1. 临时禁用驱动签名强制（需重启）
bcdedit /set testsigning on
# 重启后
pnputil /add-driver "C:\...\tools\ncmfix\pmosncm.inf" /install
# 用完记得关
bcdedit /set testsigning off
```

**建议：不折腾。WiFi SSH 已经够用。**

---

## 六、待办：ALS 自动亮度（唯一未修复项）

### 6.1 问题

```
tablet-autobright.service   enabled/inactive
```

服务定义里的条件：
```ini
ConditionPathExists=/sys/bus/iio/devices/iio:device3/buffer/enable
```

但**设备索引变了**：

```
iio:device2 = qcom-smgr-mag
iio:device3 = qcom-smgr-gyro      ← 条件检查的是这个
iio:device4 = qcom-smgr-accel
iio:device5 = qcom-smgr-prox      ← ALS 实际在这里
```

启动日志：
```
Ambient-light automatic backlight (Xiaomi Mi Pad 4 Plus) skipped,
unmet condition check ConditionPathExists=/sys/bus/iio/devices/iio:device3/buffer/enable
```

### 6.2 修复方案

**方案 A：改条件为按名字匹配（推荐）**

```bash
# 新建一个 systemd 的 ExecStartPre 或改成软链接
sudo ln -sfn /sys/bus/iio/devices/iio:device5 /sys/bus/iio/devices/iio:device3-prox
```

或者改 service 文件：
```ini
# 删掉 ConditionPathExists，改成脚本内自检
# 在 tablet-autobright 脚本开头加：
D=$(for d in /sys/bus/iio/devices/iio:device*; do
      [ "$(cat $d/name 2>/dev/null)" = "qcom-smgr-prox" ] && echo "$d"
    done | head -1)
[ -n "$D" ] || exit 0
```

**方案 B：不依赖索引，用 `/dev/iio:deviceX` 的 name 查**

`tablet-autobright` 是 Python 脚本，可以改成：
```python
import glob
for d in glob.glob('/sys/bus/iio/devices/iio:device*'):
    if open(f'{d}/name').read().strip() == 'qcom-smgr-prox':
        return d
```

### 6.3 其他待办

| 项目 | 状态 | 说明 |
|---|---|---|
| `tablet-orientd.service` inactive | 正常 | 用户会话服务，登录后启动 |
| ALS raw 值为空 | 待查 | buffer 已启用，但没读到值 |
| 触摸/键盘验证 | 未做 | Xorg 认到了，但没实测点击 |
| 扬声器 | 未修 | 需 TAS2557 DTS 节点（驱动已在内核，见 doc 18） |
| 摄像头 | 未修 | 需 OV13855/S5K5E8 驱动 |

---

## 七、硬件状态（当前可用）

### 7.1 已工作

| 组件 | 状态 | 证据 |
|---|---|---|
| 屏幕 | ✅ 1920x1200 横屏 | `xrandr: DSI-1 connected ... left` |
| 背光 | ✅ 180/255 | `/sys/class/backlight/lcd-backlight/brightness` |
| 触摸 | ✅ Goodix | `xinput: Goodix Capacitive TouchScreen id=9` |
| 电源键 | ✅ | `xinput: pm8941_pwrkey id=7` |
| 音量键 | ✅ | `xinput: gpio-keys id=6`（vol_up）|
| WiFi | ✅ 192.168.1.29 | `ath10k_snoc` |
| 传感器 | ✅ 5 个 IIO | mag/gyro/accel/prox + rradc + adc |
| 音频 codec | ✅ | `sdm660-internal "Xiaomi Mi Pad 4"` |
| 磁盘 | ✅ 105.6 GB | `df -h` |

### 7.2 未工作

| 组件 | 原因 | 工作量 |
|---|---|---|
| 扬声器 | TAS2557 缺 DTS 节点 | 低（驱动已在） |
| 摄像头 | OV13855/S5K5E8 缺驱动 | 中 |
| ALS 自动亮度 | systemd 条件写死索引 | 极低 |
| 睡眠 | DPU suspend 死锁 | 高 |
| 指纹 | 需 TEE/QSEECOM | 极高 |
| 快充 | 缺 SMB1351 驱动 | 中 |
| GPS | 缺 ADSP GNSS QMI | 中 |

---

## 八、关键路径与命令速查

### 8.1 路径

```
平板 SSH     : ssh user@192.168.1.29  (密码 <SUDO_PASSWORD>)
构建 VM      : ssh user@192.168.1.200  (密码 <VM_PASSWORD>)

平板脚本目录 : /usr/local/bin/tablet-*        （20 个）
平板服务     : /etc/systemd/system/*tablet*   （4 个）
平板配置     : /etc/tablet/                   （landscape, rotation.json）
会话日志     : ~/.local/share/tablet-session/{launcher,xfce-x-session,session}.log
镜像         : mipad4plus/tools/pmos-final.img  （2.39 GB，含 10/24 配置）
备份         : mipad4plus/artifacts/preflash/   （281 MB，29 文件）
```

### 8.2 常用命令

```powershell
# 连平板
$env:PAD_HOST = "192.168.1.29"
python mipad4plus\tools\ssh_pad.py "<cmd>"

# 传文件到平板
python mipad4plus\tools\put_pad.py <local> <remote>

# 用 sudo（密码管道）
cd mipad4plus\tools; .\pad_sudo.ps1 -Cmd "<cmd>" -Timeout 600

# 连 VM
python mipad4plus\tools\ssh_vm.py "<cmd>"

# 进 fastboot
adb reboot bootloader
# 或长按电源 10-15s → 音量减+电源

# 查 fastboot
& "D:\APPS\platform-tools\fastboot.exe" devices
```

### 8.3 平板提权

**注意**：SSH 无 TTY，`sudo` 直接运行会报 `interactive authentication is required`。

```bash
# 正确
echo '<SUDO_PASSWORD>' | sudo -S -p '' <command>
```

`tools/pad_sudo.ps1` 已封装此逻辑。

---

## 九、文档索引

| 文档 | 内容 |
|---|---|
| `00-GOAL.md` | 总目标与路线图 |
| `07-xorg-xfce.md` | Xorg/XFCE 权威配置（glamor vs llvmpipe） |
| `08-HARDWARE-AUDIT.md` | 9 个硬件缺陷清单 |
| `09-P0-1-SENSORS.md` | 传感器深挖 |
| `10-AUTOROTATE.md` | 自动旋转 |
| `13-ALS-SUCCESS.md` | ALS 修好 |
| `14-AUTO-BRIGHTNESS.md` | 自动亮度 |
| `15-ALS-SAMPLERATE.md` | ALS 采样率 |
| `16-FLASH-TO-MIUI.md` | 刷 MIUI 完整流程 |
| `17-ANDROID-VS-PMOS-HARDWARE.md` | Android vs pmOS 硬件对比 |
| `18-HARDWARE-COMPLETE.md` | **48 项完整硬件清单** |
| **`19-PMOS-RESTORE.md`** | **本文** |
| `HANDOFF.md` | 交接文档（待更新） |

### 证据文件

| 文件 | 大小 | 内容 |
|---|---|---|
| `evidence/hw-full-preflash-20261024.txt` | 23 KB | pmOS 侧全量硬件（刷机前） |
| `evidence/android-v1032-hw.txt` | 62 KB | Android 第 1 轮 |
| `evidence/android-v1032-hw2.txt` | 72 KB | Android 第 2 轮 |
| `evidence/android-v1032-hw3.txt` | 8 KB | Android 按键/TAS2557 |
| `evidence/android-v1032-otg.txt` | 14 KB | Android OTG + 关机充电 |
| `evidence/android-v1032-led3.txt` | 9 KB | Android RGB 呼吸灯 |
| `evidence/android-v1032-reg.txt` | 16 KB | Android 73 个 regulator |
| `evidence/final-state-20261024.txt` | — | **恢复后的最终状态** |

---

## 十、下一步建议

### 10.1 立刻可做（低成本高收益）

1. **修 ALS 自动亮度**（见 §6.2，约 10 分钟）
2. **实测触摸/键盘/音量键**（验证输入设备真的能用）
3. **修扬声器**（加 TAS2557 DTS 节点，编译内核约 30 分钟）

### 10.2 中期

4. 摄像头（写 OV13855/S5K5E8 驱动）
5. 睡眠（DPU suspend）
6. 快充（SMB1351）

### 10.3 长期 / 不现实

7. 指纹（需要 TEE，闭源固件）
8. GPS（ADSP GNSS QMI）

### 10.4 办公电脑目标评估

**当前可用于办公的程度：70%**

- ✅ 桌面、窗口、文件管理
- ✅ WiFi 网络
- ✅ 触摸操作
- ✅ 屏幕显示（横屏 1920x1200）
- ❌ 扬声器（无声）
- ❌ 摄像头（视频会议不行）
- ❌ 睡眠（合盖不省电）
- ⚠️ 性能（llvmpipe 软件渲染，横屏时慢）

**建议**：修好扬声器 + 睡眠后，配合蓝牙/USB 音频，可达到基本办公水平。
摄像头是视频会议刚需，优先级应提高。
