# 恢复镜像的校验方法与包内结构

> 实测刷机记录与三个 TWRP 坑见 [FLASH-TESTED.md](FLASH-TESTED.md)；刷机步骤见 [FLASHING.md](FLASHING.md)。

> 目标：确保 `clover-restore-*.zip` 在 **fastboot** 或 **TWRP** 下能直接刷回，
> 且 **UUID / 权限 / 架构** 都正确。

---

## 1. 包内结构

```
clover-restore-<日期>.zip
├── boot.img               内核 + 设备树（fastboot flash boot）
├── rootfs.tar.gz          根文件系统（/dev/mmcblk1p64）
├── META-INF/com/google/android/
│   ├── update-binary      TWRP 刷机脚本（busybox sh）
│   └── updater-script
└── README-RESTORE.md      本说明
```

## 2. 校验清单（每次打包后必须逐条通过）

| # | 检查项 | 命令 | 期望 |
|---|---|---|---|
| 1 | zip 完整性 | `unzip -t clover-restore-*.zip` | `No errors detected` |
| 2 | boot.img 架构 | `file boot.img` | 含 `ARM aarch64` / `Android bootimg` |
| 3 | 内核版本 | `strings boot.img \| grep -m1 'Linux version'` | `7.0.14-sdm660` |
| 4 | rootfs 架构 | `tar -tzf rootfs.tar.gz \| head` → 检查 `bin/busybox` | `ELF 64-bit LSB * ARM aarch64` |
| 5 | 根分区 UUID | `blkid /dev/mmcblk1p64` 与 `tar -xzOf rootfs.tar.gz ./etc/fstab` | 一致 |
| 6 | 关键权限 | `tar -tvzf rootfs.tar.gz ./usr/bin/sudo ./etc/shadow` | sudo 有 `s` 位；shadow `640 root:shadow` |
| 7 | 所有者 | `tar -tvzf rootfs.tar.gz ./home/zhoulei` | `10000/10000` |
| 8 | 无绝对路径/穿越 | `tar -tzf rootfs.tar.gz \| grep -E '^/|\.\./'` | 空输出 |
| 9 | 解包体积 | `tar -tzvf rootfs.tar.gz \| awk '{s+=$3} END{print s/1024/1024" MB"}'` | 与磁盘占用接近 |
| 10 | 可启动性 | 刷入后 `fastboot reboot` | 出现锁屏并能解锁 |

## 3. 打包命令（参考）

```sh
# 在设备上（或挂载 rootfs 的主机上）
cd /
sudo tar --numeric-owner -czf /tmp/rootfs.tar.gz \
    --exclude=./proc --exclude=./sys --exclude=./dev \
    --exclude=./run --exclude=./tmp --exclude=./mnt --exclude=./media \
    --exclude=./lost+found .

# boot.img 直接取当前启动分区
sudo dd if=/dev/mmcblk1p? of=/tmp/boot.img bs=1M
```

> 打包时**必须** `--numeric-owner`，否则 UUID 之外的用户/组名映射会错。

## 4. 刷机方式

### fastboot

```sh
fastboot flash boot boot.img
fastboot reboot
# rootfs 用 TWRP 刷，或 fastboot 直接写分区（危险，需确认分区号）
```

### TWRP

```
Wipe → Format Data（可选）
Install → clover-restore-*.zip
Reboot → System
```

## 5. 已知注意点

- **首次启动会重新生成 SSH host key**，属正常；
- **`/etc/shadow` 里的密码哈希是公开的默认凭据**（见 README），
  请第一时间改密码；
- 若目标机分区布局不同（例如 rootfs 不在 `p64`），需要改 `updater-script`；
- 刷机前务必备份 `boot` 与 `modem`/`persist` 分区。
