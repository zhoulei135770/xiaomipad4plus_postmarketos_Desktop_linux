# 从零构建

在 x86_64 的 Debian/Ubuntu 上交叉构建（`qemu-user-static` + `mmdebstrap`）。
也可以直接在设备上用 chroot 方式装，但慢很多。

## 0. 依赖

```bash
sudo apt install mmdebstrap qemu-user-static binfmt-support \
                 debootstrap rsync e2fsprogs dosfstools
```

确认 binfmt 生效：

```bash
ls /proc/sys/fs/binfmt_misc/qemu-aarch64
```

## 1. 生成基础 rootfs

```bash
sudo ./scripts/build-base.sh /srv/debport/rootfs
```

脚本做的事：

1. `mmdebstrap --arch=arm64 --variant=apt forky` 生成最小系统
2. 写入 apt 源（Debian ports arm64 + forky）
3. 装内核模块（从设备的 pmOS 内核 `7.0.14-sdm660` 对应 modules 目录拷贝）

> 内核不重新编译：boot 分区仍是 pmOS 的 `boot.img`，rootfs 里只需要
> `/lib/modules/7.0.14-sdm660/` 与 `modules.dep`。

## 2. 装桌面与硬件支持

```bash
sudo ./scripts/setup-rootfs.sh /srv/debport/rootfs
```

包含：

- `labwc`、`lxqt`（Qt6）、`greetd`、`fcitx5`、`wvkbd`、`swayidle`、`wlopm`
- `mesa`（freedreno）、`pulseaudio`、`pipewire` 不装（PA 更稳）
- `network-manager`、`bluez`、`tqftpserv`（WiFi firmware）
- 传感器：`qcom_sns_reg` + `/lib/firmware/qcom/sensors/sns.reg`（**必须 25468 字节，644**）
- UCM2：`/usr/share/alsa/ucm2/Xiaomi/clover/`
- 主题：Onyxian-Rounded + Kvantum `Orchis-solid` + Papirus
- 脚本：`tablet-orientd`、`tablet-powerkeyd`、`tablet-battery-sni`、`tablet-pinlock` …

## 3. 生成可刷镜像

```bash
sudo ./scripts/make-image.sh /srv/debport/debian-rootfs.img 8G
```

脚本：`mkfs.ext4` → mount → `rsync -aHAX rootfs/` → `umount` →
输出 ext4，UUID 固定 `8def993b-42f5-4ba1-9813-c046e498fe22`。

## 4. 刷入

见 [`FLASH.md`](FLASH.md)。

## 5. 改配置后重新出镜像

设备上改完 `/usr/local/bin/tablet-*`、`~/.config/lxqt/*` 等，用：

```bash
sudo ./scripts/collect-configs.sh        # 设备 → tar
sudo ./scripts/apply-configs.sh          # tar → rootfs → 重新 make-image
```

## 6. 版本约定

| 版本 | 内容 |
|---|---|
| v9 | 首个完整可用（桌面/声音/传感器/主题） |
| v10 | 平板设置修复 + sudoers + pavucontrol-qt |
| v11 | 深色系壁纸 + powerkeyd EOF 修复 + rotate-restore 重启 panel |
| v13 | 电量百分比托盘（绕过 UPower）+ 星火商店 + Chromium + Firefox prefs |

