# 🔄 刷 MoKee 后的完整恢复指南

生成时间：2026-10-30 20:15
设备：小米平板4 Plus（clover-plus / SDM660）
备份位置：`/root/preflash-20261028-194245/`（设备）→ `backup/preflash/`（PC）

---

## 一、备份内容清单

### 🔴 Tier 1：设备唯一（丢失永久损坏，绝对不可少）

| 文件 | 大小 | 内容 |
|---|---|---|
| `persist.img` | 32 MB | **指纹传感器校准、触摸校准、WiFi MAC、传感器标定** |
| `modemst1.img` | 2 MB | modem 射频校准 |
| `modemst2.img` | 2 MB | modem 射频校准（备份） |
| `fsg.img` | 2 MB | modem 文件系统 |
| `fsc.img` | 1 KB | modem 文件系统计数 |
| `devinfo.img` | 4 KB | 设备解锁状态 |
| `sec.img` | 16 KB | 安全分区 |
| `keystore.img` | 512 KB | 密钥库 |
| `frp.img` | 512 KB | 工厂重置保护 |
| `misc.img` | 1 MB | 启动模式标志 |

### 🟠 Tier 2：引导链

| 文件 | 大小 |
|---|---|
| `boot.img` | 64 MB（pmOS r253 内核）|
| `recovery.img` | 64 MB（TWRP）|
| `vbmeta.img` | 64 KB |
| `xbl.img` | 3.5 MB |
| `abl.img` | 1 MB |
| `tz.img` | 4 MB |
| `hyp.img` | 512 KB |
| `rpm.img` | 512 KB |
| `pmic.img` | 512 KB |
| `devcfg.img` | 1 MB |
| `logo.img` / `splash.img` | 32.6 MB 各 |

### 🟢 Tier 3：系统数据

| 文件 | 大小 | 说明 |
|---|---|---|
| `vendor-content.tar.gz` | 167 MB | vendor 分区内容（固件：IPA/GPS/相机/音频）|
| `rootfs-etc-home.tar.gz` | 153 MB | `etc/ root/ usr/local/ var/lib/systemd/` 全部配置和脚本 |
| `rootfs-full.tar.gz` | 2.9 GB | **完整 pmOS 系统**（解包即恢复）|
| `lib-modules.tar.gz` | 13.4 MB | 内核模块（7.0.14-sdm660）|
| `packages.txt` | — | 已安装包列表（`apk add` 恢复用）|
| `meta.txt` | — | 系统信息快照 |
| `MD5SUMS` | — | 所有文件的校验和 |

---

## 二、刷 MoKee 之前

### 1. 验证备份完整性

在 PC 上（`backup/preflash/` 目录）：
```powershell
# 生成校验和并和设备的对比
Get-ChildItem *.img, *.tar.gz | Get-FileHash -Algorithm MD5 | Format-Table
```

在平板上：
```sh
cd /root/preflash-20261028-194245 && md5sum -c MD5SUMS
```

### 2. 确认 U 盘有一份
把整个 `backup/preflash/` 拷到 U 盘（58 GB 那个）。

---

## 三、恢复 pmOS（刷完 MoKee 后）

### 前提
- 已刷回 TWRP（`recovery.img` 用 fastboot 刷）
- PC 上有 `backup/preflash/` 全部文件
- 平板能进 TWRP

### 步骤 1：进入 fastboot，恢复引导链和关键分区

```bash
# 关机，按住音量下 + 电源进入 fastboot
fastboot devices

# 引导链（顺序很重要：先 xbl/abl，再 boot）
fastboot flash xbl      xbl.img
fastboot flash abl      abl.img
fastboot flash tz       tz.img
fastboot flash hyp      hyp.img
fastboot flash rpm      rpm.img
fastboot flash pmic     pmic.img
fastboot flash devcfg   devcfg.img
fastboot flash vbmeta   vbmeta.img
fastboot flash boot     boot.img
fastboot flash recovery recovery.img

# ★ 设备唯一分区 —— 绝对不能错
fastboot flash persist  persist.img
fastboot flash modemst1 modemst1.img
fastboot flash modemst2 modemst2.img
fastboot flash fsg      fsg.img
fastboot flash fsc      fsc.img
fastboot flash misc     misc.img
fastboot flash devinfo  devinfo.img
fastboot flash sec      sec.img
fastboot flash keystore keystore.img
fastboot flash frp      frp.img
```

### 步骤 2：恢复 vendor 分区

```bash
fastboot flash vendor vendor.img          # 如果有 2GB 的裸镜像
# 或者（推荐，体积小）：
# 进 TWRP，格式化 vendor，然后解包 vendor-content.tar.gz
```

在 TWRP 的终端里：
```sh
mount /dev/block/bootdevice/by-name/vendor /mnt/vendor
cd /mnt/vendor && tar -xzf /external_sd/vendor-content.tar.gz
```

### 步骤 3：恢复 rootfs（userdata）

**方法 A：完整恢复（推荐）**
```sh
# 在 TWRP 里
adb push rootfs-full.tar.gz /tmp/
# 格式化 data 分区
adb shell mkfs.ext4 -L pmOS /dev/block/bootdevice/by-name/userdata
adb shell mkdir -p /mnt/pmos
adb shell mount /dev/block/bootdevice/by-name/userdata /mnt/pmos
adb shell 'cd /mnt/pmos && tar -xzf /tmp/rootfs-full.tar.gz'
adb shell sync
```

**方法 B：精简恢复（先装最小系统，再叠配置）**
```sh
# 用 pmbootstrap 重新安装 pmOS 到设备
pmbootstrap flasher flash_rootfs --partition userdata
# 然后解包配置
adb shell 'cd / && tar -xzf /tmp/rootfs-etc-home.tar.gz'
```

### 步骤 4：验证

```sh
# 关键检查点
ls /sys/class/net/             # 应该看到 wlan0
cat /sys/class/power_supply/qcom-battery/capacity
sudo pad_selftest              # 应该 28 passed
```

---

## 四、如果刷机后进不了 fastboot/TWRP

**这是最坏情况。恢复路径：**

1. **9008 EDL 模式**（高通紧急下载模式）
   - 短接主板测试点 或 特定按键组合
   - 需要 QFIL / `edl.py` 工具
   - 风险最高，**请先确认 U 盘和 PC 的备份都在**

2. **确认 persist 和 modemst 没丢** —— 这两个丢了信号和指纹会永久损坏

---

## 五、关键提醒

### ⚠️ 刷 MoKee 会覆盖什么

| 分区 | 是否被覆盖 | 后果 |
|---|---|---|
| boot / recovery | ✅ | 可恢复（我们备份了）|
| system / vendor | ✅ | 可恢复 |
| **userdata（pmOS rootfs）** | ✅ **通常会被格式化** | 可恢复（rootfs-full.tar.gz）|
| **persist** | ⚠️ 视刷机脚本 | **若丢失，指纹/传感器永久损坏** |
| **modemst1/2** | ⚠️ 视刷机脚本 | **若丢失，信号可能永久损坏** |

**⇒ 刷机前请确认刷机包不会写 persist / modemst。多数第三方 ROM 不会动它们，但快充/信号相关的"全量包"可能会。**

### ⚠️ 恢复后必须做的事

1. 重新安装 `apk add` 列表（见 `packages.txt`）
2. 重新部署 `/usr/local/bin/` 下的脚本（在 `rootfs-etc-home.tar.gz` 的 `usr/local/` 里）
3. 恢复 `/etc/modprobe.d/fpc1020.conf`（指纹参数）
4. 启用 `usb-autoswitch` 和 `pulseaudio` 服务

---

## 六、指纹研究的下一步（刷 MoKee 后）

**目标：拿到"工作状态"的寄存器快照**

在 MoKee 上（指纹能用），用 root shell 执行：
```sh
# 找到 SPI 设备
ls /sys/bus/spi/devices/
# 用 root 权限 dump fpc1020 的寄存器（0x00 - 0xFF）
# 或者在 MoKee 上跑 qseecom 工具 dump TA 的通信
```

**最简单的办法**：在 MoKee 上按住指纹，同时用 `cat /sys/kernel/debug/...` 或
直接读 `/dev/` 下的 SPI 节点，把 0x00-0xFF 全部寄存器打印出来。

对比 pmOS 下的值，就能找到差异。

---

## 七、实际执行记录（2026-10-28 21:2x - 21:42，已成功）

结果：**pmOS 7.0.14-sdm660 正常启动，`pad_selftest` 28 passed / 0 failed / 0 skipped**，
指纹 HWID 0x0341 应答、后摄 16.5 MB 帧、WiFi 5 GHz、modem QMI、GNSS、BT、OTG 全通。

### 实际走的路径（与上面理想流程的两处差异）

| 步骤 | 实际情况 |
|---|---|
| 进 TWRP | `fastboot reboot recovery` **无效**（只是普通重启）。可用的是 `fastboot boot recovery.img`（直接把 TWRP 引导起来）；用户在设备侧按 **音量+ + 电源** 也能进 |
| persist/modemst/fsg/fsc | **fastboot 拒绝写**（critical 分区，报 `Command failed`）→ 改为在 TWRP 里 `dd`，写后回读 MD5 逐个校验通过 |

### ⚠️⚠️ 最大的坑：重新 mkfs 后 UUID 变了，initramfs 找不到根

pmOS 的启动参数（`/proc/cmdline`，也记在 `meta.txt`）里是：

```
pmos_root_uuid=8def993b-42f5-4ba1-9813-c046e498fe22    ← 按文件系统 UUID 找根
```

`mke2fs` 会生成新 UUID ⇒ 开机永远停在 **`waiting for root partition`**。
修复（TWRP 里一条命令，数据不用重灌）：

```sh
tune2fs -U 8def993b-42f5-4ba1-9813-c046e498fe22 /dev/block/bootdevice/by-name/userdata
blkid /dev/block/bootdevice/by-name/userdata     # 确认 LABEL="pmOS" UUID=8def993b-...
```

> 如果下次是从**全新 rootfs** 恢复（没有原始 UUID），就用
> `mke2fs -t ext4 -L pmOS -U 8def993b-42f5-4ba1-9813-c046e498fe22 <dev>` 一步到位。

### 实际命令序列（可直接复用）

```sh
# 0) 校验备份（PC 侧，与 MD5SUMS 比对，boot/recovery/persist/modemst/fsg/fsc/vbmeta 全部一致）
# 1) fastboot
fastboot flash recovery recovery.img
fastboot flash boot     boot.img
fastboot flash vbmeta   vbmeta.img
fastboot flash misc devinfo sec keystore frp   # 这几个 fastboot 允许
# 2) TWRP（fastboot boot recovery.img）
adb push persist.img modemst1.img modemst2.img fsg.img fsc.img /sdcard/restore/
#    ⚠️ toybox dd 不接受 1M/1K 后缀，必须写数字：bs=1048576 / bs=1024
dd if=persist.img  of=/dev/block/bootdevice/by-name/persist  bs=1048576
dd if=modemst1.img of=/dev/block/bootdevice/by-name/modemst1 bs=1048576
dd if=modemst2.img of=/dev/block/bootdevice/by-name/modemst2 bs=1048576
dd if=fsg.img      of=/dev/block/bootdevice/by-name/fsg      bs=1048576
dd if=fsc.img      of=/dev/block/bootdevice/by-name/fsc      bs=1024
# 3) 根文件系统
umount /sdcard /data
mke2fs -t ext4 -L pmOS -F -q /dev/block/bootdevice/by-name/userdata
mount -t ext4 /dev/block/bootdevice/by-name/userdata /mnt/pmos
adb push rootfs-full.tar.gz /mnt/pmos/          # 3.07 GB, 98 s @ 29.7 MB/s
md5sum /mnt/pmos/rootfs-full.tar.gz             # 3cc8c3a9... 与本地一致
cd /mnt/pmos && tar -xzf rootfs-full.tar.gz     # 55 s
rm rootfs-full.tar.gz
# 4) vendor
mke2fs -t ext4 -L vendor -F -q /dev/block/bootdevice/by-name/vendor
mount -t ext4 /dev/block/bootdevice/by-name/vendor /mnt/vendor
adb push vendor-content.tar.gz /mnt/vendor/ && cd /mnt/vendor && tar -xzf vendor-content.tar.gz
# 5) ⚠️ 关键一步
tune2fs -U 8def993b-42f5-4ba1-9813-c046e498fe22 /dev/block/bootdevice/by-name/userdata
sync; reboot
```

### 恢复后状态

* `uname -r` → `7.0.14-sdm660`
* 根分区 `/dev/mmcblk1p64`，106.7 G，用 5.3 G
* `pad_selftest` → **28 passed**
* WiFi 5 GHz 可登（SSH `user@192.168.1.29`），`sudo` 密码 <SUDO_PASSWORD>
* `/vendor` 与 `/boot` **未挂载**（当前系统本来就不需要；固件从 rootfs 内取）
