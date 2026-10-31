# ⚠️ 紧急恢复：平板重启后离线

> 2026-10-29 10:15。最后一次重启后平板约 6 分钟未上线（WiFi/以太网均不通）。
> **最可能的元凶是我 10:08 打的那个 `msm-firmware-loader.sh` 补丁。**

---

## 0. 先判断是哪种情况

| 现象 | 说明 | 去做 |
|---|---|---|
| **屏幕正常亮起、能看到桌面**，只是没网 | WiFi 固件没发布（加载器中断），系统本身好的 | **方案 A** |
| **屏幕黑/卡在开机 logo/反复重启** | GPU 初始化崩了内核 | **方案 B** |
| 屏幕亮但只有文字光标 | 桌面没起来 | 方案 A（用虚拟控制台） |

---

## 方案 A：能进桌面（哪怕没网）

打开终端（桌面右键 → 打开终端；或按 `Ctrl+Alt+F2` 切到文字终端登录 user/<SUDO_PASSWORD>）：

```sh
# 1. 还原被我改过的固件加载器
sudo cp /usr/sbin/msm-firmware-loader.sh.orig-gpu /usr/sbin/msm-firmware-loader.sh

# 2. 删除我加的 msm 黑名单（它现在只会帮倒忙）
sudo rm -f /etc/modprobe.d/msm-wait-for-firmware.conf
sudo systemctl disable msm-load-after-fw.service

# 3. 重启
sudo reboot
```

如果这样还没网，说明是 boot 镜像的问题，接着做方案 B 的第 2 步。

---

## 方案 B：开不了机 / 进了桌面也没网

### B1. 能进系统但想彻底回到早上 9:50 的状态

```sh
# 回滚 boot 镜像（这个镜像我刷之前校验过，md5 c69516c8）
sudo dd if=/root/boot-rollback.img of=/dev/mmcblk1p12 bs=1M
# 同时还原加载器
sudo cp /usr/sbin/msm-firmware-loader.sh.orig-gpu /usr/sbin/msm-firmware-loader.sh
sudo reboot
```

### B2. 完全开不了机（黑屏/卡 logo）

需要电脑 + USB 线，用 **fastboot**（音量下 + 电源进 fastboot）：

```sh
# 在电脑上，工作区里就有原始 boot.img
fastboot flash boot mipad4plus\backup\device-boot\boot.img
fastboot reboot
```

那个 `boot.img` 是**今天所有改动之前的原始镜像**（md5 `55c7bce436c0cd0be7c799eb68747125`），
刷进去一定能开机。

开机后再补一步（清掉我加的单元）：

```sh
sudo rm -f /etc/modprobe.d/msm-wait-for-firmware.conf
sudo systemctl disable msm-load-after-fw.service
```

---

## 我到底改了什么（完整清单，便于你判断）

| # | 改动 | 时间 | 风险 |
|---|---|---|---|
| 1 | `/lib/firmware/qcom/a512_zap.*`（复制固件） | 09:44 | 无 |
| 2 | `msm-wait-for-firmware.conf` 黑名单 | 09:52 | 无（无效） |
| 3 | `msm-load-after-fw.service` | 09:52 | 低 |
| 4 | `gpu-zap-fix.sh` + drop-in | 09:45 | 低 |
| 5 | **boot.img 换成含 ZAP 固件的 initramfs** | 10:00 | **中**（回滚镜像已存 `/root/boot-rollback.img`） |
| 6 | **`msm-firmware-loader.sh` 补丁** | 10:08 | **高（最可疑）** |

补丁内容只是加了几行 `ln -sfn`，但**如果脚本带 `set -e` 且某条失败，整段固件发布会被中断** →
WiFi/蓝牙/venus 全都没固件 → 表现就是"开机正常但没网"。

备份在：`/usr/sbin/msm-firmware-loader.sh.orig-gpu`

---

## 恢复后我该怎么做

1. 先用 `sh pad_install_msm_order.sh --undo` 和还原脚本把系统清干净
2. GPU 的事**换思路**：不再动加载器和 boot 镜像，改为
   - 确认 ZAP 文件格式（`.mdt` vs `.mbn`）
   - 或者干脆接受软件渲染，把桌面调成"软件渲染下也够快"的配置

---

## 抱歉

这一步是我推进太急。GPU 的收益很大（1.8 → 50+ FPS），但我不该在无法现场验证的情况下
连改加载器 + boot 镜像两处启动关键路径。恢复步骤都在上面，任何一步卡住告诉我现象。
