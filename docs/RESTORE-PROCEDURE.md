# 备份与恢复流程（Mi Pad 4 Plus / pmOS）

> 这份文档记录的是**验证过可用**的完整流程，以及 2026-10-25 那次事故的教训。
> 照做可以避免重复踩坑。

---

## 0. 当前备份清单

| 文件 | 大小 | 位置 | 说明 |
|---|---|---|---|
| `rootfs.tar.zst` | 1.5 GB | 设备 `/var/backup/`、U 盘、电脑 `backup/pad-full-20261025/` | 完整根文件系统快照（tar + zstd） |
| `pmos-restore-v2.img` | 4.9 GB | 电脑、U 盘 | **正确版本**的 ext4 恢复镜像（属主已修正） |
| `boot-r26-current.img` | 64 MB | 同上 | boot 分区整块镜像（r26 内核） |
| `gpt.dump` | 11 KB | 同上 | 分区表 |
| `configs.tar.gz` | 4 MB | 同上 | /etc、systemd 单元、polkit、桌面项、home 配置 |
| `packages.txt` | 116 KB | 同上 | 已安装包清单 |
| `qcom_smbx-r27.ko.zst` | 9 KB | 电脑 `tools/` | OTG 升压控制模块（r26 内核配套） |

---

## 1. 制作恢复镜像（**最容易出错的一步**）

```bash
# 1) 以 root 解包，并保留数字属主（不要用用户名映射！）
sudo mkdir -p /tmp/rootfs
sudo sh -c 'zstd -dc rootfs.tar.zst | tar --numeric-owner -x -C /tmp/rootfs'

# 2) 校验属主（必须是 0:0 4755 / home 10000）
sudo stat -c "%u:%g %a %n" /tmp/rootfs/usr/bin/sudo /tmp/rootfs/home/user

# 3) 生成镜像（大小对齐 4096，UUID/卷标与原分区一致）
USED=$(sudo du -sb /tmp/rootfs | cut -f1)
SIZE=$(( (USED + USED/8 + 536870912 + 4095) / 4096 * 4096 ))
sudo truncate -s $SIZE pmos-restore.img
sudo mkfs.ext4 -F -L pmOS_root -U 8def993b-42f5-4ba1-9813-c046e498fe22 \
     -d /tmp/rootfs pmos-restore.img

# 4) 校验镜像内部属主
sudo mount -o loop,ro pmos-restore.img /mnt
sudo stat -c "%u:%g %a %n" /mnt/usr/bin/sudo /mnt/etc/shadow /mnt/home/user
sudo umount /mnt
```

**必须满足**：

- `usr/bin/sudo` → `0:0 4755`
- `etc/shadow` → `0:42 640`
- `home/user` → `10000`（**不是 1000**）
- 卷标 `pmOS_root`、UUID `8def993b-…`

---

## 2. 恢复方式

### 2.1 fastboot（推荐，需要电脑）

```powershell
# 设备进 fastboot（音量下 + 电源）
fastboot flash boot boot-r26-current.img
fastboot -S 16M flash userdata pmos-restore-v2.img
fastboot reboot
```

⚠️ **已知问题**：最后一块的落盘确认可能"卡住"很久（这是设备端的固有问题）。
数据其实已写入，**看到 235/235 全部 OKAY 后可以放弃等待**，直接断电重启。

### 2.2 U 盘 dd（不依赖电脑）

前提：initramfs 能识别 U 盘（本机实测**未能识别**，暂不可用）。

### 2.2b TWRP 3.7.0_9-0 (clover) 恢复 —— **2026-10-25 新增，已验证镜像结构**

TWRP ramdisk 的 recovery.fstab 已核对：

```
boot      = /dev/block/bootdevice/by-name/boot
userdata  = /dev/block/bootdevice/by-name/userdata
OTG 挂载点 = /usb-otg          ← 带连字符
自带 sbin/e2fsck、sbin/resize2fs、sbin/toybox(dd)、exfat-fuse（能读 exFAT U 盘）
镜像备份：tools/twrp-clover-3.7.0.img
```

TWRP → Advanced → Terminal：

```sh
ls /usb-otg                                  # Mount → 勾 USB OTG 之后
umount /data 2>/dev/null
dd if=/usb-otg/boot-r35.img of=/dev/block/bootdevice/by-name/boot bs=4M
dd if=/usb-otg/pmos-restore-v2.img of=/dev/block/bootdevice/by-name/userdata bs=4M
sync
/sbin/e2fsck -f -y /dev/block/bootdevice/by-name/userdata
/sbin/resize2fs /dev/block/bootdevice/by-name/userdata
sync
reboot
```

或者用脚本：`sh /usb-otg/twrp_restore.sh`（干跑）/ `--yes`（写入）。
OTG 没自动挂：`ls /dev/block/sd*` → `mkdir -p /usb-otg && mount -t exfat /dev/block/sda1 /usb-otg`。

**必做**：`resize2fs`（镜像是 5.3G 文件系统，不扩容根分区只有 5G）。


### 2.3 恢复后必做的三件事

```bash
sudo chown -R 10000:10000 /home/user     # 若家目录属主不是 10000
sudo systemctl reset-failed
sudo systemctl start greetd                  # 桌面
sudo systemctl mask usb-signaller            # host 模式无 UDC，属预期
```

---

## 3. 事故复盘（2026-10-25）

### 3.1 直接原因

为了让 MIUI 启动验证摄像头，清空了 `userdata`（当时是 pmOS 根分区）。
之后恢复过程反复失败，最终靠 fastboot + 手工修属主恢复。

### 3.2 踩过的坑（按发生顺序）

| # | 问题 | 现象 | 正确做法 |
|---|---|---|---|
| 1 | 镜像用普通用户制作 | `sudo` 失去 setuid，桌面起不来，服务名乱码 | 必须 `sudo` + `--numeric-owner` |
| 2 | tar 按用户名映射 uid | 家目录属主 1000（VM 用户），设备用户是 10000 | 解包加 `--numeric-owner` |
| 3 | fastboot 刷大镜像 | 最后一块落盘卡死，中断导致 fs 尾部损坏 | 看到 235/235 即可重启；或用 dd |
| 4 | 镜像大小未对齐 4096 | `invalid sparse header` | `truncate` 到 4096 倍数 |
| 5 | U 盘未安全弹出 | exFAT 只读，救援日志写不进 | Windows 里先"安全弹出" |
| 6 | 中断 fastboot 传输 | 设备 USB 状态卡死，需**重启设备**（拔插线无效） | 每次失败后长按电源 10 秒 |
| 7 | 后台任务挂 SSH 会话下 | 备份被 systemd 杀掉，tar 截断 | 用 `systemd-run --unit=... --collect` |
| 8 | busybox tar 不支持 `--one-file-system` | 备份只写出 13 字节 | `apk add tar` 用 GNU tar |
| 9 | 自制 initramfs 读不到 U 盘 | 无日志、直接回退正常启动 | 暂不依赖 U 盘救援 |
| 10 | `usb-signaller` 失败 | 系统显示 degraded | `systemctl mask usb-signaller`（host 模式预期） |
| 11 | MIUI boot 版本不匹配 | 清数据后仍回 recovery | 用整包线刷 ROM（`E:\Downloads\clover_images_*`） |
| 12 | MIUI 刷机后 data 被格式化 | pmOS 根分区丢失 | 事先做好备份 |

### 3.3 有效的救援手段（按可靠性排序）

1. **fastboot 小镜像**（boot 64 MB）—— 从未失败
2. **fastboot 大镜像** + 手工修属主 —— 可用，但需处理尾部卡死
3. root 登录 —— **不可用**（`root:!` 锁定），只能靠 sudo
4. U 盘 dd 救援 —— initramfs 识别不到 U 盘，暂不可用

---

## 4. 日常备份命令（在设备上）

```bash
# 一次性备份到 U 盘（exFAT，自动挂载在 /run/media/user/<LABEL>）
sudo sh -c 'tar -C / --one-file-system \
  --exclude=./proc --exclude=./sys --exclude=./dev --exclude=./run \
  --exclude=./tmp --exclude=./mnt --exclude=./media \
  --exclude=./var/backup --exclude=./var/cache/apk --exclude=./var/tmp \
  -cf - . | zstd -3 -T0 -o /var/backup/rootfs.tar.zst -f'

# 重要：必须用 systemd-run 跑，否则 SSH 断开会被杀
sudo systemd-run --unit=backup-rootfs --collect --description="rootfs backup" \
  sh -c 'tar ... | zstd ...'
```

验证：

```bash
zstd -t /var/backup/rootfs.tar.zst
```

---

## 5. 关键坐标（不要忘）

| 项目 | 值 |
|---|---|
| pmOS 根分区 | `/dev/mmcblk1p64`（PARTLABEL `userdata`，105.6 GB） |
| boot 分区 | `/dev/mmcblk1p12`（64 MB） |
| 根文件系统 UUID | `8def993b-42f5-4ba1-9813-c046e498fe22` |
| pmOS 用户 | `user` / uid **10000** / 密码 `<SUDO_PASSWORD>` |
| root | **锁定**（`root:!`），只能 `sudo` |
| 设备 IP | `192.168.1.29`（DHCP） |

---

# 🔧 开机循环 / 设备不进系统的恢复步骤（2026-10-26 16:30 新增）

## 症状
平板上电后卡在开机 logo 反复重启，Wi-Fi 不上线，PC `ping 192.168.1.29` 不通。

## 原因（本次）
刷了 `boot-r108.img`，其 DTB 里有一个**没有 remote-endpoint 的 camss 端点**：
`camss_parse_ports()` 对每个 endpoint 调 `v4l2_async_nf_add_fwnode_remote()`，
没有对端时返回 -EINVAL → camss 探测失败 → 触发 WARN，而内核开了 `panic_on_oops=1`
→ panic → 自动重启 → 死循环。

## 恢复（二选一）

### A. TWRP（推荐，之前用过）
1. U 盘里要有 **`boot-r47.img`**（我放在电脑桌面，复制到 U 盘根目录即可）
2. 平板进 TWRP（关机后按住 电源+音量下，或之前用过的方式）
3. TWRP 里挂载 U 盘（通常 `/usb-otg`），然后：
```sh
dd if=/usb-otg/boot-r47.img of=/dev/block/bootdevice/by-name/boot bs=4M
sync
```
4. 重启 → 正常进 pmOS（boot-r47 + 老的 camss 模块）

### B. fastboot（如果设备支持）
关机后按住 电源+音量下 进 bootloader：
```
fastboot flash boot boot-r47.img
fastboot reboot
```

## 恢复之后
1. 告诉我一声（或直接等我下次操作）：我会重新装 `camss-r93.tar.xz`（后摄可用的模块）
2. 后摄出图三步：
```sh
sh /tmp/cfg.sh
v4l2-ctl -d /dev/v4l-subdev17 -c exposure=1600,analogue_gain=0x1000
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=1 --stream-to=/tmp/ok.raw
```

## 教训（已写入流程）
**刷 boot 前必须本地验证 DTB**：`tools/vm_valid110.py` 会检查 camss 每个 endpoint 是否都有
`remote-endpoint`，有悬空端点就绝对不能刷。

---

# 🚨 2026-10-26 19:30-20:05 恢复事故复盘（必读）

## 事故经过
1. 刷完魔趣，用 `twrp_restore_v3.sh --yes` 恢复 → **变砖（代码一闪黑屏）**
2. 排查发现：rootfs 被清空（v3 先删后解，TWRP 的 toybox tar 不支持 `-p` → 解包失败）
3. 用静态 busybox 重新解包 → 文件恢复，`sudo` setuid 位正常 → **仍然黑屏**
4. 真正原因：**分区 UUID 变了**

```
设备 userdata UUID : 8abc4fa7-586f-4e4c-ba4f-8b86bdf1ad31
内核 cmdline 期望   : 8def993b-42f5-4ba1-9813-c046e498fe22
```
内核用 UUID 找根分区 → 找不到 → panic → 黑屏重启循环。
（UUID 变化是因为 v3 失败后 TWRP 挂不上分区，自动格式化了一次）

修复：
```sh
/sbin/e2fsck -fy /dev/block/bootdevice/by-name/userdata
/sbin/tune2fs -U 8def993b-42f5-4ba1-9813-c046e498fe22 /dev/block/bootdevice/by-name/userdata
reboot
```
→ 系统正常启动，后摄抓图 16,558,080 字节 ✅

## 两个坑（写进 v5 脚本，永久避免）

| 坑 | 后果 | v5 的做法 |
|---|---|---|
| 用 TWRP 自带 tar 解包 | toybox 不支持 `-p`，解包失败但系统已删 → 变砖 | 用 U 盘上的**静态 aarch64 busybox** 解包 |
| 先删后解 | 解包失败就无系统可救 | **先解到 `._new` 校验**（关键路径 + sudo 位），通过才替换 |
| 不设 UUID | 内核找不到根分区 → 黑屏 | 结束前 `e2fsck -fy` + `tune2fs -U <固定UUID>` |

## U 盘现在的布局（2026-10-26 20:10 整理）

| 文件 | 用途 |
|---|---|
| `README-恢复说明.txt` | **先看这个**：清单 + 步骤 + 校验值 + 历史教训 |
| `twrp_restore_v5.sh` | 恢复脚本（干跑 / `--yes` / `--yes --boot`） |
| `pmos-rootfs-20261026.tar.gz` | rootfs 备份 1,764,653,947 B，sha256 `dcd68f8d…` |
| `boot-current.img` | boot 镜像 25,812,992 B，sha256 `fc86cb74…` |
| `busybox-aarch64-static` | 解包工具（静态，TWRP 里可直接跑） |
| `old_*` | 已改名禁用的旧脚本（v3、整盘恢复、boot_only） |
| `pmos-restore-v2.img` | 10/25 的 5 GB 老快照（仅兜底） |

## 恢复正确姿势

```sh
# TWRP -> Mount -> USB OTG
sh /usb_otg/twrp_restore_v5.sh                # 干跑
sh /usb_otg/twrp_restore_v5.sh --yes --boot   # 恢复 rootfs + boot + UUID
reboot
```

---

## 2026-10-26 21:10 恢复成功（用户用 U 盘 v5 脚本）

最终确认状态（pmOS 正常启动）：

| 项目 | 值 |
|---|---|
| 内核 | 7.0.14-sdm660 |
| boot 镜像 | **r47**（无前摄 port@2，只有旧 stub 节点） |
| rootfs UUID | `8def993b-42f5-4ba1-9813-c046e498fe22` ✓ 与 cmdline 一致 |
| camss 模块 | r93（备份里的版本） |
| 前摄驱动 | 未安装（备份状态） |
| **后摄抓图** | **16,558,080 字节 ✓** |

### 关键教训（这次踩的坑）

1. **必须用 U 盘的 `twrp_restore_v5.sh`**（自带静态 busybox + 自动设 UUID）。
   我临时用的 adb 版 rescue 脚本没有设 UUID，且 fs 在 TWRP 自动重挂载后变脏，
   导致"恢复成功但重启黑屏"的假象。
2. 恢复后**不要**再让 TWRP 自动挂载 /data；脚本内部已处理（挂载→解包→校验→替换→
   sync→umount→e2fsck→tune2fs UUID）。
3. 判断是否恢复到位，最快的检查：
   ```sh
   ls /sdcard/sbin/init          # 应存在（指向 ../lib/systemd/systemd）
   ls /sdcard/usr/bin/sudo       # 应有 setuid 位
   blkid /dev/block/bootdevice/by-name/userdata   # UUID 必须是 8def993b-...
   ```
