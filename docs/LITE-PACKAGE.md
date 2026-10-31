# 精简包（< 2 GiB）：为什么用 gzip 而不是 xz

> 目标：让 **U 盘 + TWRP 直接刷** 也能用。
> 结论：**TWRP 里没有 `xz`，所以用 gzip + 剔除冗余文件**，最终 **1.836 GiB**。

---

## 1. 先验证 TWRP 支持什么

解析 `twrp-3.7.0_9-0-clover-mipad4.img` 的 ramdisk（3491 个条目）：

| 工具 | TWRP 是否提供 |
|---|---|
| `gzip` / `gunzip` | ✅（`sbin/gzip`、`sbin/gunzip`） |
| `bzcat` / bzip2 | ✅ |
| **`xz` / `unxz` / `lzma`** | ❌ **没有**（只有 `sbin/liblzma.so` 这个库） |
| `tune2fs` / `e2fsck` | ✅ |
| `tar`（busybox） | ✅（支持 `-z`，不支持 `--numeric-owner`） |

所以 **xz 方案不可行**，改用 gzip。

---

## 2. 怎么把包压到 2 GiB 以内

原始 tar.gz 是 **2.79 GB**，直接 gzip 压不动。先剔除**与运行无关的冗余**：

| 剔除项 | 大小 | 理由 |
|---|---|---|
| `/root/*.img`（20 个） | **1.28 GB** | 都是 64 MB 的整分区 boot 备份，调试内核时留的 |
| `/root/restore-*/` | 少量 | 旧的恢复草稿 |
| `/boot/*.img`、`*.bak*` | 0.18 GB | 旧内核镜像；真正的内核在 boot 分区 |
| `/var/log/journal`、`/var/cache`、`/var/tmp` | 0.27 GB | 日志与缓存 |
| `/usr/share/doc`、`/usr/share/man`、`/usr/lib/debug` | 少量 | 文档与调试符号 |

结果：

```
剥离前：111,276 条目 / 6.00 GB
剥离后：111,165 条目 / 4.42 GB   （删掉 111 个条目 / 1.58 GB）
gzip -9：1.77 GiB
加 boot.img + META-INF：1.836 GiB   ✅ < 2 GiB
```

> 重打包用**流式**方式（直接从原 tar 复制条目，不解压到磁盘），
> 所以符号链接、权限、uid/gid 全部原样保留。

---

## 3. 成品

| 项 | 值 |
|---|---|
| 文件 | `clover-restore-lite.zip` |
| 大小 | **1.836 GiB**（1,971,xxx,xxx 字节） |
| sha256 | `96697bbc…` |
| 成员 | `boot.img`(64 MB)、`rootfs.tar.gz`(1816 MB)、`META-INF/` |
| 每个成员 | 均 **< 2 GiB** ✅ |
| 内部 rootfs | sha256 与剥离后的 tar 完全一致 ✅ |
| 脚本 | 解包到 `/data`、校验 `sbin/init`、恢复 UUID(`8def993b…`) ✅ |

---

## 4. 刷法（U 盘 + TWRP）

1. U 盘放好 `clover-restore-lite.zip`
2. 平板进 TWRP → Mount → 勾 **USB OTG**
3. Install → `/usb_otg/clover-restore-lite.zip`

预期输出：

```
==== clover postmarketOS restore ====
boot     : /dev/block/bootdevice/by-name/boot
userdata : /dev/block/bootdevice/by-name/userdata
Flashing boot.img ...
boot.img flashed
Mounting userdata at /data ...
target root: /data
rootfs parts: rootfs.tar.gz
Extracting rootfs (streamed) to /data ...
rootfs extracted
rootfs looks valid (init present)
current UUID: xxxx
restoring UUID -> 8def993b-42f5-4ba1-9813-c046e498fe22
UUID now: 8def993b-42f5-4ba1-9813-c046e498fe22
sync done
==== finished: reboot to system ====
```

---

## 5. 尚未验证

| 项 | 状态 |
|---|---|
| 这份 lite 包在 TWRP 里实际刷入 | ⏳ 待测（大小已满足 TWRP 的 mmap 限制） |
| 剥离内容后的系统完整性 | 已确认 `sbin/init`、systemd、sudo、shadow 都在；未做完整回归 |
