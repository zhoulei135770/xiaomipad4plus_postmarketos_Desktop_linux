# Release 资产说明

镜像体积 8.6 GB，超过 GitHub 单文件限制（仓库 100 MB / Release 资产 2 GB），
所以按 **gzip 压缩 + 分卷** 上传。

## 本次发布文件

| 文件 | 说明 |
|---|---|
| `debian-rootfs-v13.img.gz.part-aa` | 分卷 1 |
| `debian-rootfs-v13.img.gz.part-ab` | 分卷 2 |
| `SHA256SUMS` | 合并后镜像的 SHA-256 |

## 合并

```bash
cat debian-rootfs-v13.img.gz.part-* > debian-rootfs-v13.img.gz
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
# 设备/VM 上生成整盘镜像后
gzip -9 -c debian-rootfs.img > debian-rootfs-v13.img.gz
split -b 1800m -d -a 2 debian-rootfs-v13.img.gz debian-rootfs-v13.img.gz.part-
sha256sum debian-rootfs.img > SHA256SUMS
gh release upload v13 debian-rootfs-v13.img.gz.part-* SHA256SUMS --clobber
```

