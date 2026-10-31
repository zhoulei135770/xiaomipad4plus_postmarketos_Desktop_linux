# 刷机指南（TWRP / fastboot / adb）

> 本页只写**实测能通**的方法。三条实测教训的来源见
> [`FLASH-TESTED.md`](FLASH-TESTED.md)。

---

## 1. 三种方式，按推荐顺序

| # | 方式 | 需要 | 状态 |
|---|---|---|---|
| 1 | **TWRP 装 `clover-restore-lite.zip`** | U 盘 + TWRP | ✅ 包已压到 1.84 GiB（TWRP 上限 2 GiB） |
| 2 | **adb 刷**（`flash-via-adb.sh`） | USB 数据线 + TWRP | ✅ 真机验证成功 |
| 3 | **fastboot 只换内核** | `boot.img` | ✅ 64 MB，最稳 |

---

## 2. 方式 1：TWRP 装 lite 包（推荐）

```sh
# 校验
sha256sum -c clover-restore-lite.zip.sha256
```

1. 把 `clover-restore-lite.zip` 放 U 盘
2. 平板进 TWRP（`fastboot boot twrp-3.7.0_9-0-clover-mipad4.img`）
3. **Mount → 勾 USB OTG**
4. **Install → `/usb_otg/clover-restore-lite.zip` → Swipe**

脚本会自动：刷 `boot.img` → 解包到 `/data` → 校验 `sbin/init` →
恢复 ext4 UUID（`8def993b-…`）→ sync。

---

## 3. 方式 2：adb 刷（TWRP 报损坏时的兜底）

```sh
unzip clover-restore-lite.zip boot.img rootfs.tar.gz
adb wait-for-recovery
sh flash-via-adb.sh boot.img rootfs.tar.gz
```

这个流程在 2026-10-31 真机跑通：push → `dd` 刷 boot → 解包到 `/data` →
`tune2fs -U` 恢复 UUID → 重启开机。

---

## 4. 方式 3：只换内核

```sh
fastboot flash boot boot.img
```

`boot.img` 里就是内核 + dtb + cmdline（`pmos_root_uuid=8def993b-…`）。
换了根文件系统却没换内核时，注意这个 UUID 必须对得上。

---

## 5. 三个必须知道的坑

| 坑 | 现象 | 处理 |
|---|---|---|
| **TWRP 不能 mmap >2 GiB 的包** | "刷机包已损坏" / "映射文件失败" | 用 lite 包（1.84 GiB）或改用 adb |
| **`/sdcard` 不是分区根** | 开机进 initramfs：`Root partition does not contain a root filesystem` | 解包目标必须是 `/data` |
| **格式化会换掉 ext4 UUID** | 同样进 initramfs | `tune2fs -U 8def993b-42f5-4ba1-9813-c046e498fe22 -L pmOS /dev/block/bootdevice/by-name/userdata` |

---

## 6. 出问题怎么救

| 症状 | 处理 |
|---|---|
| 卡 initramfs，提示找不到 root | 进 TWRP，`tune2fs -U` 写回 UUID；或 `pmos_continue_boot` 重试 |
| 卡 initramfs，提示没有 rootfs | 检查 `/data/sbin/init` 是否存在；不在说明解包位置错了 |
| TWRP 装包报损坏 | 改用 `flash-via-adb.sh` |
| 完全黑屏 | 长按电源 10 秒；仍不行走 EDL（需 QFIL + 厂商线刷包） |

---

## 7. 刷完自检

```sh
# 根分区 UUID
blkid /dev/mmcblk1p64          # 期望 8def993b-42f5-4ba1-9813-c046e498fe22

# 关键权限
stat -c '%A %u:%g %n' /etc/shadow /usr/bin/sudo /home/zhoulei

# GPU 加固
cat /sys/module/msm/parameters/enable_preemption   # 0
systemctl is-active tablet-gpu-harden

# 会话
tr '\0' '\n' < /proc/$(pidof labwc)/environ | grep FD_MESA_DEBUG
```
