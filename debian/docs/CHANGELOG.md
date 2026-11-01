# 更新日志

## v13 — 2026-11-02 (public release)

**修复**

- 电量托盘改为实时：`tablet-battery-sni` 每 10 秒读一次 `capacity` 并发送 SNI
  `NewIcon` 信号（之前只在启动时画一次，会出现 88% 而实际 92% 的偏差）；
  `Id` 带 pid 避免 panel 缓存旧条目；`labwc/autostart` 里启动它

首个公开发布：镜像已清理浏览器配置 / WiFi 密码 / SSH 密钥 / 历史 / machine-id。

## v12 — 2026-11-01

**新增**

- `tablet-battery-sni`：电量百分比托盘图标（StatusNotifierItem，直读
  `/sys/class/power_supply/qcom-battery`，充电时主题强调蓝、否则浅白，
  tooltip 显示状态/电压/温度，点击打开平板设置）
- 星火应用商店 `spark-store 5.3.2 arm64`（补 `/usr/bin/spark-store` 软链，
  桌面项加 `--disable-gpu` 修复 Electron 中文缺字）
- Chromium arm64 + `/usr/local/bin/tablet-chromium`
  （`--ozone-platform=wayland --enable-gpu-rasterization --enable-zero-copy`），
  已设为默认浏览器，桌面「浏览器」图标指向它
- 深色系渐变壁纸（`#0c1018 → #1b202c`），与 Onyxian 主题统一

**修复**

- `lxqt-powermanagement` 电源托盘永远显示 0（`enableBatteryWatcher=false`，
  原因见 `docs/HARDWARE.md` 电源一节）
- `tablet-powerkeyd` input 设备 EOF 后 95% CPU 空转
- `tablet-rotate-restore` 恢复旋转后重启 `lxqt-panel` / `pcmanfm-qt`，
  否则壁纸只铺 2/3、面板只画 1200 px（systemd-run 单元名加 `$$` 避免冲突）
- Firefox：`gfx.webrender` 配置从旧 profile 移到实际使用的
  `o3nzgs7q.default-release`；`FD_MESA_DEBUG` 去掉 `sysmem`（否则黑屏/花字）
- 面板移除左下角相机/设置/终端三个按钮（横屏握持误触会自己弹窗）
- 平板设置里的 XFCE/Alpine 命令全部换成 LXQt / PA / wvkbd / tablet-pinlock
- 亮度、清缓存加 sudoers 白名单（`/etc/sudoers.d/tablet-settings`）
- 屏蔽 `plymouth-start/quit`（`plymouthd` 21% CPU）

## v11 — 2026-11-01

- 深色壁纸 + `TransformWallpaper=true`
- `tablet-powerkeyd` 单次 spawn 音量 OSD（131–164 ms，之前 40–80 秒）
- UCM 删除 `Mic` / `Headset Mic`（采集 PCM 坏的，导致 PA 卡主循环）
- `pulse/client.conf` `autospawn=no`，会话与 powerkeyd 显式 `PULSE_SERVER`

## v10 — 2026-11-01

- 平板设置：显示/电源/声音/所有设置/虚拟键盘/锁屏/重启关机全部改成 Debian 可用的命令
- 安装 `pavucontrol-qt`
- 亮度、drop-caches 的 sudoers 规则

## v9 — 2026-11-01

首个完整可用版本：

- labwc + LXQt 2.4 桌面，GPU 合成
- 自动旋转（orientd）+ 自动亮度（autobright）
- 锁屏 `tablet-pinlock`（GTK4 layer-shell + PAM）
- `lxqt-notificationd` + 音量 OSD
- Onyxian-Rounded 主题 + Kvantum `Orchis-solid` + Papirus
- WiFi / 蓝牙 / 声音 / 传感器 / 后置相机


