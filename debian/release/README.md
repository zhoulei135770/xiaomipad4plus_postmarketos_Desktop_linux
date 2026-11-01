# Release 资产说明

v13 起镜像压缩后约 **1.3 GB**，小于 GitHub 单文件 2 GB 限制，所以**不再分卷**。

## 本次发布文件

| 文件 | 说明 |
|---|---|
| `debian-rootfs-v13.img.gz` | 压缩后的整盘镜像（解压后 8.59 GB） |
| `SHA256SUMS` | 解压后镜像的 SHA-256 |

## 解压 + 校验

```bash
gzip -d debian-rootfs-v13.img.gz
sha256sum -c SHA256SUMS
```

## 刷入

```bash
fastboot flash userdata debian-rootfs-v13.img
```

或在 recovery 里：

```bash
dd if=debian-rootfs-v13.img of=/dev/block/by-name/userdata bs=4M
```

完整步骤见 [`../docs/FLASH.md`](../docs/FLASH.md)。

## 重新打包（维护者）

```bash
gzip -9 -c debian-rootfs.img > debian-rootfs-v13.img.gz
sha256sum debian-rootfs.img > SHA256SUMS
gh release upload v13 debian-rootfs-v13.img.gz SHA256SUMS --clobber
```
