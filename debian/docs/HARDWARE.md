# 硬件状态与调试笔记

## 平台

| 项 | 值 |
|---|---|
| SoC | Snapdragon 660 (SDM660)，4×Cortex-A73 + 4×A53 |
| GPU | Adreno 512（freedreno `fd512`，Mesa GL 3.1 / GLES 3.1） |
| 内存 | 4 GB |
| 屏幕 | 10.1" 1920×1200，DSI `nt51021`（BOE） |
| 触摸 | Goodix capacitive |
| 电池 | `qcom-battery` + `pm660-charger` |
| 存储 | `mmcblk1p64` = userdata；boot 分区保留 pmOS |

## 传感器（IIO）

链路：`qcom_sns_reg`（加载 `sns.reg`）→ `qcom_smgr` → SLPI → IIO

设备节点：

| 设备 | 传感器 |
|---|---|
| `/dev/iio:device2` | BMI120 加速度计 |
| `device3` | BMI120 陀螺仪 |
| `device4` | AK09918 磁力计 |
| `device5` | CM3232 环境光 |
| `device6` | BU52061NVX 霍尔 |

关键点：

- `/lib/firmware/qcom/sensors/sns.reg` 必须 **25468 字节**、`0644`，否则 `qcom_smgr` 不 probe
- `in_accel_scale = 1.5258e-05`，1 g ≈ 65536
- `tablet-orientd` 需要先 enable `scan_elements/in_accel_*_en` 和 `buffer/length=96`
- 旋转阈值：`THRESHOLD = 0.6 / in_accel_scale` ≈ 39323

## 音频

- PulseAudio（不是 PipeWire），UCM2 配置：
  `/usr/share/alsa/ucm2/Xiaomi/clover/{clover,HiFi}.conf`
- `/usr/share/alsa/ucm2/conf.d/sdm660-internal/` 里的 symlink 指向 clover.conf
  （文件名必须匹配 `Xiaomi Mi Pad 4`、`platform-sound`、`X4`、`sdm660-internal`）
- **采集 PCM `hw:X4,1` 是坏的（EINVAL）**，`HiFi.conf` 里已删除 `Mic` / `Headset Mic`，
  否则 PA 探测失败 → 每 4 秒重试 → 音量键 40–80 秒延迟

## WiFi / 蓝牙

- WiFi：ath10k + WCN3990，firmware 通过 QMI-TFTP 由 `tqftpserv` 提供
- 蓝牙：WCN3990，MAC 需要写死：
  `btmgmt public-addr 02:00:29:4B:23:B3`（`bt-address.service`）
- 每次重启 IP 会变（DHCP），用 `hostname -I` 查

## 4G（未完成）

- ModemManager 看不到 modem
- IPA（IP Accelerator）没打通，数据业务起不来
- 可继续的方向：`qmi_wwan` + `rmnet` + IPA 固件；SMS/通话走 `mmcli` 需先让 MM 识别

## 电源

- `qcom-battery` 只暴露 `capacity / voltage_now / current_now / temp`，
  **没有 `charge_now` / `energy_now`**
- UPower 因此 `energy = 0 Wh`，LXQt 电源管理显示 0；百分比本身是准的（`capacity`）
- 解决：自写 `tablet-battery-sni`，直读 sysfs 画百分比图标（10 秒刷新，发 SNI\n  `NewIcon`/`NewToolTip` 信号），并关掉 `lxqt-powermanagement` 的 `enableBatteryWatcher`\n- 注意：SNI 必须在 panel 启动后保持运行；已加入 `labwc/autostart`
- 充电上限：`pm660-charger` 默认 1.5 A；`tablet-charge-guard` 做温度保护

## GPU / 合成

- 桌面：labwc（wlroots）GPU 合成，`GSK_RENDERER` / `QT_QUICK_BACKEND` 已去掉
- `FD_MESA_DEBUG=nogrow,noindirect`（**不要加 `sysmem`**，会让 WebRender 画出黑屏/花字）
- Firefox：freedreno + WebRender(OpenGL) 不稳定 → 建议 Chromium 或软件合成
- 星火商店（Electron）：必须 `--disable-gpu`，否则中文缺字

## 输入

| 设备 | 节点 |
|---|---|
| 电源键 | `pm8941_pwrkey` (event0) |
| 音量/其他 | `gpio-keys` (event2) |
| 霍尔 | `gpio-hall-sensor` (event3) |
| 触摸 | Goodix (event4) |
| 耳机检测 | Xiaomi Mi Pad 4 Headset Jack (event5) |
| 蓝牙键盘 | Xiaoxin Mplus 5.0 (event6) |

`tablet-powerkeyd` 用 `select()` 监听所有 `/dev/input/event*`；设备消失时要
`close()+del`，否则 select 一直返回可读 → 95% CPU 空转。


## WPS Office（星火安装后打不开）

现象：点图标没反应，命令行 wps 立刻退出、无输出。

原因：WPS 11.1 是按 Debian 10/UOS 编译的，依赖的 soname 在 forky 已经升级：

| WPS 需要 | Debian forky 提供 |
|---|---|
| libxml2.so.2 | libxml2.so.16 |
| libicuuc.so.72 / libicui18n.so.72 | ICU 76 |

修法：把 bookworm 的 libxml2 + libicu72 解到
/opt/kingsoft/wps-office/office6/libcompat，再用 wrapper 设 LD_LIBRARY_PATH：

``bash
sudo debian/scripts/wps-fix.sh
``

首次启动会弹《WPS Office 最终用户许可协议》，点“确定”即可。

