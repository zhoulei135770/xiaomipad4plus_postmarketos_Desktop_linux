# 刷机指南（Windows / Linux / macOS / recovery）

镜像在 [Releases](../../releases)（v13 起压缩后约 1.3 GB，单文件，不分卷）：

```
debian-rootfs-v13.img.gz
SHA256SUMS
```

## 0. 前置

- 设备已解锁 bootloader（`fastboot oem unlock`，会清数据）
- 电脑装好 `fastboot` / `adb`（Android platform-tools）
- 至少 12 GB 空闲磁盘（合并后 8.6 GB + 解压临时空间）
- **先备份当前 userdata**（可选但强烈建议）：
  ```bash
  adb shell "su -c 'dd if=/dev/block/by-name/userdata of=/sdcard/userdata-backup.img bs=4M'"
  adb pull /sdcard/userdata-backup.img
  ```

## 1. 解压

Linux / macOS：

```bash
gzip -d debian-rootfs-v13.img.gz
sha256sum -c SHA256SUMS
```

Windows（PowerShell）：

```powershell
7z x .\debian-rootfs-v13.img.gz
Get-FileHash .\debian-rootfs-v13.img -Algorithm SHA256   # 对照 SHA256SUMS
```

## 2. fastboot 刷入（推荐）

```bash
adb reboot bootloader
fastboot devices
fastboot flash userdata debian-rootfs-v13.img
fastboot reboot
```

只写 `userdata`。**不要**碰 `boot` / `dtbo` / `vbmeta`。

## 3. recovery / TWRP 里 dd

适合没有电脑或 fastboot 不识别的情况：

```bash
adb push debian-rootfs-v13.img /sdcard/
adb shell
su
dd if=/sdcard/debian-rootfs-v13.img of=/dev/block/by-name/userdata bs=4M
sync
reboot
```

TWRP 终端里同理（`/dev/block/by-name/userdata` 或 `/dev/block/mmcblk1p64`）。

## 4. 首次启动

- 开机后是 greetd → labwc → LXQt 会话，锁屏 PIN 见下
- 默认账号：`zhoulei` / `147258`（root 同密码）——**刷完请立刻改**
  ```bash
  passwd
  sudo passwd root
  ```
- WiFi 用 `nmtui` 或面板托盘连接
- 第一次进桌面如果黑屏：`Ctrl+Alt+F2` 登录后 `sudo systemctl restart greetd`

## 5. 恢复 / 回滚

刷回原 pmOS 或上一个版本：

```bash
fastboot flash userdata userdata-backup.img   # 或 pmos-final.img
```

boot 分区没动过，所以任意 userdata 都能起来（只要 rootfs 里有对应内核模块）。

## 6. 常见问题

| 现象 | 处理 |
|---|---|
| `fastboot flash` 卡在 sending | 换 USB 2.0 口 / 换线；`fastboot -w` 后再刷 |
| 开机停在 pmOS logo | 分区没写对：确认刷的是 `userdata`（`mmcblk1p64`） |
| 进系统黑屏但有背光 | `systemctl restart greetd`，或看 `journalctl -b -u greetd` |
| 触摸方向不对 | `sudo tablet-rotate normal` 后重启会话 |
| 没有 WiFi | `sudo systemctl restart tqftpserv wpa_supplicant`，确认 `sns.reg` 存在 |

