# ⚠️ 事故记录：pmaports 定制树丢失与抢救结果

> 2026-10-29 07:35–07:50。**这是本项目的重大事故，记录清楚以便复盘和追责。**

---

## 发生了什么

用户授权我清理 VM 磁盘。我执行了：

```sh
sudo rm -rf /home/user/.local/var/pmbootstrap/chroot_native
```

问题：**`pmaports` 等目录以 bind mount 方式挂在 `chroot_native/mnt/` 下面**
（`chroot_native/mnt/pmaports` → `cache_git/pmaports`）。

`rm -rf` 遍历进这些挂载点，**删掉的是真实文件**，不是 chroot 里的副本。

⇒ `cache_git/pmaports` 被清空，其中的 **定制 APKBUILD（pkgrel=253）+ 84 个补丁**丢失。

## 损失清单

| 项目 | 状态 |
|---|---|
| `cache_git/pmaports`（定制树） | ❌ **丢失**（已被我重新 clone 成上游 master，pkgrel=2、0 补丁）|
| 84 个补丁文件 | ❌ 丢失约 72 个 |
| `chroot_native`（14 G 构建 chroot） | ❌ 删除（**可重建**，不算损失）|
| 内核源码树 `~/kbuild/linux-7.0.14-sdm660` | ✅ **完好**（1.8 G，含 fpc1020.c / .config / clover dts）|
| `chroot_rootfs_xiaomi-clover` | ✅ 完好（7.3 G）|
| 设备上的内核与运行状态 | ✅ 未受影响 |

## 抢救到的（已存进 `mipad4plus/backup/`）

### `pmaports-salvage/` —— 12 个补丁文件

```
0002-arm64-dts-qcom-sdm660-xiaomi-clover-tas2557.patch
0005-ASoC-tas2557-match-16bit-I2S-and-right-slot-offset.patch
0006.patch                          ← 49 KB，疑似 ov13855 相机驱动
0007-arm64-dts-qcom-sdm660-xiaomi-clover-camera.patch
0008-arm64-dts-clover-enable-usb-host-mode.patch
0009-clk-mmcc-sdm660-add-camss-gp2-clock.patch
0010-power-supply-qcom-smbx-add-otg-vbus-control.patch
0082-venus-packet-diag.patch
0083-venus-skip-props.patch
0084-arm64-venus-hfi4-with-v3-pm.patch
vdiag.patch
xorg-rotate-fastpath.patch
```

来源：`/home/user/*.patch`（早期手工放的零散副本）。

### `device-boot/` —— 设备上的最终产物

```
sdm660-xiaomi-clover-plus.dtb       66080   ← 84 个补丁全部应用后的 DTB
sdm660-xiaomi-clover-plus-fixed.dtb 66320   ← 我加了前摄 port@2 的版本
extlinux.conf                        319
```

**这个 DTB 是关键**：它 = "所有 DT 补丁的最终结果"，
可以反编译回 DTS 作为新的 DT 基准（已做：`dtc -I dtb -O dts`）。

## 补救：前摄其实不需要重建内核

`/boot/extlinux/extlinux.conf`：

```
label postmarketOS
	kernel /vmlinuz
	fdt /sdm660-xiaomi-clover-plus.dtb      ← 独立的 DTB 文件
	initrd /initramfs
```

⇒ 前摄的三处改动**全是 DTS**，只要替换这一个 `.dtb` 文件 + 重启，
**不需要内核源码、不需要重编、不需要刷机**。

已执行：
1. 从设备取回 live DTB
2. `dtc` 反编译成 DTS
3. 加 `camss/ports/port@2` + `camera@10/port`（phandle 0xf0/0xf1）
4. 编译成新 DTB（66 320 字节）
5. 装到 `/boot/sdm660-xiaomi-clover-plus.dtb`，原文件备份为
   `/boot/sdm660-xiaomi-clover-plus.dtb.bak-20261029-074734`

回滚：

```sh
sudo sh /tmp/install-dtb.sh --rollback && reboot
```

## 还没恢复的

驱动类补丁（`0035-fpc1020`、venus 系列 0047–0051/0072–0077、
smbx 0085–0088、camss 调试 0011–0028 等）**没有副本，无法恢复**。

影响：
- 无法重编"和你现在跑的一模一样"的内核
- 但**当前运行的内核是好的**，前摄修复走 DTB 路线，不需要重编

将来若要重编内核，需要：
1. 以上下游补丁大部分要重写（文档里有部分描述）
2. 或用 live DTB + `~/kbuild` 源码树做"仅 DT"的迭代

## 教训（已写进 START-HERE 血泪教训）

> **清理 pmbootstrap 的 chroot 之前，必须先 `mount | grep chroot` 确认没有
> bind mount，先 `umount -R` 再 `rm -rf`。**
> 正确做法是用 `pmbootstrap zap -n`（它会自己先卸载）。

我图快直接 `rm -rf`，这是我的责任。
