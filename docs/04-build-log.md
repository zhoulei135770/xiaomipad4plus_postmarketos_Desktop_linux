# 04 · 构建日志（pmOS 镜像）

> 2026-10-19，虚拟机 `user@192.168.1.200`

---

## 1. 过程时间线

| 时间（VM/UTC） | 事件 |
|---|---|
| 10:51:14 | `pmbootstrap init` 开始（管道喂答案） |
| 10:51:58 | `(1/4) PREPARE NATIVE CHROOT` |
| 10:52:13 | `(2/4) CREATE DEVICE ROOTFS` |
| 10:52:38 | 安装 `postmarketos-base-systemd` |
| 10:55:11 | 安装主包集合（phosh + GNOME + firefox 等 63 个直接依赖） |
| 11:00:30 | 下载中，apk 缓存 469 MB，已装 112 包 |
| 11:08:39 | `DONE!` |
| 11:09:13 | `pmbootstrap export` 完成 |

总耗时：**约 17 分钟**（17 分钟里含 ~8 分钟下载、~9 分钟 qemu 安装）。

## 2. 命令

```bash
export PATH=$PATH:$HOME/.local/bin
pmbootstrap config ui phosh
pmbootstrap config user user
pmbootstrap config hostname xiaomi-clover
pmbootstrap config timezone Asia/Shanghai
pmbootstrap config build_pkgs_on_install false
nohup pmbootstrap install --password <SUDO_PASSWORD> > ~/pmb_install.log 2>&1 &
```

## 3. 结果

```
[11:08:39] DONE!
```

- `ERROR` 出现次数：**0**
- 安装包数：**1212**
- 内核 release：`7.0.14-sdm660`
- rootfs 文件系统大小：约 2.9 GB（压缩后镜像 `xiaomi-clover.img` 2.9 GB）

## 4. 校验记录

### 4.1 打包的 DTB

```bash
$ ls /tmp/postmarketOS-export/dtbs
sdm660-xiaomi-clover-plus.dtb
```

只有 Plus 一个，说明 `kernel = cloverplus` 生效。

### 4.2 boot.img 内机型字符串

```bash
$ grep -a -o "Xiaomi Mi Pad 4[^\x00]\{0,12\}" /tmp/postmarketOS-export/boot.img
Xiaomi Mi Pad 4 Plus
Xiaomi Mi Pad 4
```

（第二条来自 common dtsi 里的兼容字符串，不影响。）

### 4.3 GPU 栈

```bash
$ ls ~/.local/var/pmbootstrap/chroot_rootfs_xiaomi-clover/usr/lib/dri/ | head
apple_dri.so  armada-drm_dri.so  asahi_dri.so  etnaviv_dri.so ...

$ grep -a "^P:mesa" .../lib/apk/db/installed
P:mesa
P:mesa-dri-gallium
P:mesa-egl
P:mesa-gbm
P:mesa-gl
```

freedreno 编在 `mesa-dri-gallium` 内，运行时由内核 msm 驱动 + a5xx 固件加载。

### 4.4 UI / 会话

```bash
P:postmarketos-ui-phosh
P:postmarketos-ui-phosh-default-osk
```

## 5. 产物清单

```
/tmp/postmarketOS-export/
├── boot.img          → 25 MB（软链）
├── xiaomi-clover.img → 2.9 GB（软链，双分区磁盘镜像）
├── dtbs/sdm660-xiaomi-clover-plus.dtb
├── vmlinuz
├── vmlinuz.efi
└── initramfs
```

实体文件位置：

```
~/.local/var/pmbootstrap/chroot_rootfs_xiaomi-clover/boot/boot.img
~/.local/var/pmbootstrap/chroot_native/home/pmos/rootfs/xiaomi-clover.img
```

> `/tmp` 重启会清空，重新 `pmbootstrap export` 即可。

## 6. 已知但未验证的点

- **触屏能否工作**：DTS 齐全，但要等真机启动才知道 probe 是否成功
- **Wi-Fi 稳定性**：wiki 标 Partial，未测
- **音频**：wiki 标 Partial，未测
- **GPU 实际帧率**：只知道驱动在，未跑过实际负载
- **休眠/唤醒**：未测
