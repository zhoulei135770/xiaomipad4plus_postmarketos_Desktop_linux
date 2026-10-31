# 恢复包实测验证报告

> 对 `clover-restore-20261031.zip`（分卷 `.z01` + `.zip`，共 2.72 GB）的实测结果。
> 所有命令都在**本机（小米平板 4 Plus，sd660，aarch64）**上执行。

---

## 1. 验证方法

```sh
# 分卷必须用 zip -s 0 合并（不能直接 cat，也不能对末卷 unzip -t）
zip -s 0 clover-restore-20261031.zip --out merged.zip

# 解出内容，与打包源文件比对 sha256（等价于完整性校验）
unzip -o merged.zip
sha256sum boot.img rootfs.tar.gz
```

> ⚠️ `unzip -t` 对这个 2.6 GB 的**存储型条目**会报
> `not enough memory for bomb detection`——这是 unzip 的已知内存限制，
> **不代表包损坏**。用"解出后比 sha256"才可靠（下面就是这么做）。

---

## 2. 结果总表

| # | 检查项 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `zip -s 0` 合并 | 成功，2.7 GB | ✅ |
| 2 | `boot.img` sha256 与源一致 | `f1031702f0ad42a6…` 相同 | ✅ |
| 3 | `rootfs.tar.gz` sha256 与源一致 | `cfa0cbdcbce80aa5…` 相同 | ✅ |
| 4 | `META-INF` 完整 | `update-binary`(755)、`updater-script` | ✅ |
| 5 | `boot.img` 合法 | `Android bootimg, kernel(0x8000) ramdisk(0x1000000) page 4096` | ✅ |
| 6 | boot cmdline 的 root UUID | `pmos_root_uuid=8def993b-42f5-4ba1-9813-c046e498fe22` | ✅ |
| 7 | 该 UUID 与真实分区一致 | `blkid /dev/mmcblk1p64` = `8def993b-…` | ✅ |
| 8 | `/etc/fstab` | `UUID=8def993b-… / ext4 defaults 0 0` | ✅ |
| 9 | tar 可读性 | 解压无错误（`tar.err` 0 行） | ✅ |
| 10 | 条目数 | **111,276** | ✅ |
| 11 | 解包后大小 | **6.00 GB** | ✅ |
| 12 | 绝对路径 / `..` 穿越 | **0 条** | ✅ |
| 13 | `/etc/shadow` | `-rw-r----- 0/42`（640 root:shadow） | ✅ |
| 14 | `/etc/passwd` | `-rw-r--r-- 0/0`（644） | ✅ |
| 15 | `/usr/bin/sudo` | `-rwsr-xr-x`（**4755 setuid**） | ✅ |
| 16 | `/usr/bin/passwd` | `-rwsr-xr-x`（4755） | ✅ |
| 17 | `/etc/sudoers` | `-r--r----- 0/0`（440） | ✅ |
| 18 | `/home/zhoulei` | `drwxr-xr-x 10000:0` | ✅ 与真机一致 |
| 19 | 架构（busybox） | `ELF 64-bit LSB pie, ARM aarch64, musl` | ✅ |
| 20 | 抽样文件与真机对比 | `/etc/fstab`、`/etc/passwd` sha256 完全相同 | ✅ |
| 21 | 虚拟目录残留 | `/proc /sys /dev /run /tmp /mnt /media /lost+found` 均为 **0 条** | ✅ |

---

## 3. 已知的、可接受的不完美

| 项 | 说明 | 影响 |
|---|---|---|
| `unzip -t` 报内存错误 | 2.6 GB 存储条目超出 unzip 的检测上限 | 无（改用 sha256 比对） |
| 分卷需要手动合并 | GitHub 单附件 ≤ 2 GiB | 按 `zip -s 0` 一行命令解决 |
| 根目录有 `/bcdDevice`（6 字节） | Android 遗留文件，真机本来就有 | 无 |
| `usr/bin/python3` 未在归档中 | 实际路径不同（Alpine 的 python3 在别处） | 无 |

---

## 4. 尚未验证（诚实声明）

| 项 | 状态 |
|---|---|
| **在真机上完整刷入并开机** | ⏳ 还没做回归（需要另一台可牺牲的机器或先备份） |
| TWRP 里流式解压的实际耗时 | 未测（预计 20–40 分钟，取决于 eMMC 速度） |
| 刷完后首次启动的服务自愈 | 未测 |

> 结论：**包的内容、权限、UUID、架构、完整性都已逐项核对通过**；
> 唯一没做的是"真的刷一遍然后开机"这一步。
> 建议在对外声称"已验证"之前，先在一台备份好的机器上跑一次完整刷机。
