# 刷机实录：真机验证与三个致命坑（2026-10-31）

> 本文记录 **2026-10-31 夜间在真机上完整刷机** 的过程与结果。
> 结论先行：**包内容没问题，坏在 TWRP 的三个限制上**，脚本已按实测修正。

---

## 1. 实测过程

| 步骤 | 结果 |
|---|---|
| TWRP 里 Install → U 盘 zip（2.66 GB） | ❌ 报"刷机包已损坏" |
| 缩小到 <2 GiB 成员 | ❌ 仍报损坏 |
| 从 TWRP 命令行 `twrp install` | ❌ 真实错误：**`映射文件失败`（mmap 失败）** |
| 几 KB 的测试包 → `twrp install` | ✅ `TINY ZIP OK`（说明 zip 格式本身正确） |
| 改用 **adb**：push + dd + tar | ✅ **成功开机** |
| 开机后体检 | ✅ 权限/UUID/服务/GPU/旋转/锁屏全部正常 |

---

## 2. 三个坑（都已在脚本里修掉）

### 坑 1：TWRP 无法 mmap 超大 zip

```
映射文件"/usb_otg/clover-restore-v3.zip"失败
```

不是包损坏，是 TWRP（32 位）无法把 2.7 GB 的 zip 映射进地址空间（exFAT 上的 U 盘更容易失败）。
**几 KB 的包可以正常安装**，证明格式没问题。

> ✅ 对策：**大包不要走 TWRP zip**，用 `tools/flash-via-adb.sh`（已验证）。

### 坑 2：TWRP 的 `/sdcard` 不是分区根目录

第一次 adb 刷机时解包到 `/sdcard`，重启后进 initramfs：

```
Root partition does not contain a root filesystem
```

因为 `/sdcard` 是 `/data/media` 这一层的视图，整棵树落在了子目录里，分区根 `/data` 是空的。

> ✅ 对策：解包目标必须是 **`/data`**（分区根）。脚本已改为显式挂载 `/data` 并校验 `sbin/init`。

### 坑 3：格式化会换掉 ext4 UUID

TWRP 的 **Wipe → Format Data** 会生成新的 UUID（实测变成 `290aeb08-…`），
但内核 cmdline 和 `/etc/fstab` 里仍是旧的 `8def993b-…` → 同样掉进 initramfs。

> ✅ 对策：刷机后立刻
> ```sh
> e2fsck -f -y /dev/block/bootdevice/by-name/userdata
> tune2fs -U 8def993b-42f5-4ba1-9813-c046e498fe22 -L pmOS /dev/block/bootdevice/by-name/userdata
> ```
> 脚本已自动执行。

---

## 3. 逐项校验（真机实测）

| 项目 | 期望 | 实测 |
|---|---|---|
| `/etc/shadow` | 640 root:shadow | ✅ `-rw-r----- 0:42` |
| `/usr/bin/sudo` | 4755 | ✅ `-rwsr-xr-x` |
| `/usr/bin/passwd` | 4755 | ✅ `-rwsr-xr-x` |
| `/etc/sudoers` | 440 | ✅ `-r--r-----` |
| `/home/zhoulei` | uid 10000 | ✅ `10000:0` |
| ext4 UUID | `8def993b-…` | ✅（tune2fs 恢复后） |
| GPU 加固 | preemption=0 / eviction=N / PM=on | ✅ 服务自动生效 |
| 会话环境 | `FD_MESA_DEBUG=nogrow,noindirect,sysmem` | ✅ |
| 旋转 / 触摸 | transform=90 + 矩阵一致 | ✅ |
| 锁屏 / 电源键 | 运行中 | ✅ |
| GPU hang | 0 | ✅ |
| 失败服务 | — | `nftables.service`（内核无 conntrack，与本项目无关） |

---

## 4. 推荐的刷机方式（按可靠性排序）

| # | 方式 | 适用 | 状态 |
|---|---|---|---|
| 1 | **`tools/flash-via-adb.sh`** | 有 USB 数据线 + TWRP | ✅ **本机实测成功** |
| 2 | TWRP Install 小包（<2 GiB） | 包能压到 2 GiB 以内 | ⚠️ 本包 2.66 GB，超限 |
| 3 | fastboot 刷 boot + adb 推 rootfs | 只有 fastboot 可用 | 等价于 1 |

```sh
# 方式 1（推荐）
adb wait-for-recovery
./tools/flash-via-adb.sh boot.img rootfs.tar.gz
```

---

## 5. 仍未验证

| 项 | 说明 |
|---|---|
| TWRP 图形界面刷 <2 GiB 的 zip | 未实测（当前包超限） |
| 压缩到 <2 GiB 的新包（xz） | 需要确认 TWRP 是否带 `xz` |
| 长时间使用后的稳定性 | 待观察 |
