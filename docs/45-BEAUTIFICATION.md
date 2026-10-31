# 45 — 桌面美化与面板稳定性

- 日期：2026-10-29
- 目标：好看 + 轻量（软件渲染下不掉帧）

---

## 1. 最终配色与组成

| 层 | 选择 | 位置 |
|---|---|---|
| 壁纸 | 自生成深海军蓝渐变 + 右下青色光晕（1920×1200，145 KB） | `/usr/share/tablet/wallpaper.png` |
| 图标 | `breeze-dark` | `~/.config/lxqt/lxqt.conf` → `icon_theme` |
| LXQt QSS 主题 | `dark` | `lxqt.conf` → `theme=dark` |
| Qt 调色板 | 系统 `Dark` | `lxqt.conf` → `palette=Dark` |
| Qt 部件风格 | `Fusion` | `lxqt.conf` → `style=Fusion` |
| 标题栏 | Openbox `Onyx` | `~/.config/openbox/rc.xml` |
| GTK 应用 | `Adwaita-dark` | `~/.config/gtk-{3,4}.0/settings.ini` |
| 面板 | `#0a121c`，高 54px，图标 32px | `~/.config/lxqt/panel.conf` |

壁纸生成脚本：`mipad4plus/tools/make_wallpapers.py`（numpy + PIL，纯渐变/径向光晕/细弧线，
无位图纹理，软件渲染下每帧代价很低）。

---

## 2. 踩过的坑

### 2.1 `papirus-icon-theme` 在 Alpine 是**空包**

```
$ du -sh /usr/share/icons/Papirus /usr/share/icons/ePapirus-Dark
4.0K    /usr/share/icons/Papirus
4.0K    /usr/share/icons/ePapirus-Dark
```

目录存在但没有任何图标文件，设成 Papirus 后桌面图标只剩文字。
**`breeze-dark` 是完整可用的**：`user-home` / `user-trash` / `network-workgroup` / `computer` 都有。

### 2.2 调色板目录是 `palettes/`，不是 `themes/`

- ❌ `~/.local/share/lxqt/themes/<name>/<name>.colors`
- ✅ `~/.local/share/lxqt/palettes/<name>.colors`（系统在 `/usr/share/lxqt/palettes/`）

系统自带 13 套：`Ambiance Arch-Colors Clearlooks Dark Frost Graphite KDE-Plasma Kvantum Leech Light Silver Silver-bright Valendas`。
直接用 `Dark` 即可，不必自建。

### 2.3 Openbox 主题改不动的原因：`rc.xml` 不存在

`~/.config/openbox/rc.xml` 从来没有被创建过，所以一直用的是 `/etc/xdg/openbox/rc.xml`
里的系统默认主题（那个蓝灰渐变的旧观感）。修复：

```sh
mkdir -p ~/.config/openbox
cp /etc/xdg/openbox/rc.xml ~/.config/openbox/rc.xml
# 然后把 <theme><name> 改成 Onyx
openbox --reconfigure
```

### 2.4 `customcommand` 面板按钮会导致**应用无限自动打开**

给面板加 4 个 `customcommand` 按钮（文件/终端/相机/设置）后，
文件管理器窗口每隔几秒自动新增一个，20 秒能开 3 个。

原因：触摸点击后“按下”事件没有正常释放，Qt 按钮进入**自动重复**状态，
每隔几秒重新执行一次命令。

**结论：平板上不要用 customcommand 做 dock 按钮。** 用 `mainmenu`/`fancymenu` 入口即可。

### 2.5 手动启动的 `lxqt-panel` 会被清理

- 从 SSH 手动 `setsid nohup lxqt-panel &` 启动 → 会话 cgroup 清理时一起被杀
- 做成 **systemd 系统服务** → 稳定，但**拿不到会话 D-Bus**，
  `StatusNotifierProxy, services: QList()`，托盘全空
- ✅ 正确做法：交给 `lxqt-session` 在会话启动时拉起，不要手动干预

同理，**手动启动 `pcmanfm-qt --desktop` 会丢失壁纸和图标**（缺少会话环境变量），
必须让会话自己启动。

### 2.6 面板重启后托盘图标消失

`nm-applet` / `blueman-applet` / `fcitx5` 只在启动时向 `StatusNotifierWatcher` 注册一次。
面板重启后它们不会重新注册，于是托盘空白。重启这些 applet 或重启会话即可。

---

## 3. 面板最终配置（`~/.config/lxqt/panel.conf`）

```ini
[General]
panels=panel1

[fancymenu]
type=fancymenu
alignment=Left
icon=start-here-lxqt
showText=true
text=菜单

[taskbar]
type=taskbar
alignment=Left

[statusnotifier]
type=statusnotifier
alignment=Right

[tray]
type=tray
alignment=Right

[volume]
type=volume
alignment=Right

[worldclock]
type=worldclock
alignment=Right

[panel1]
alignment=-1
animation-duration=0
hidable=false
iconSize=32
lineCount=1
lockPanel=true
panelSize=54
plugins=fancymenu, taskbar, statusnotifier, tray, volume, worldclock
position=Bottom
background-color=#0a121c
background-alpha=240
font-color=#dbe6f3
```

托盘最终包含：WiFi、键盘(fcitx5)、网络、蓝牙、通知、音量、时钟。

---

## 4. 关于「lxqt-panel 缺插件」的澄清（重要）

Alpine 的 `lxqt-panel` 包里没有 `libmainmenu.so` / `libtaskbar.so` / `libclock.so`，
最初判断是“打包不全，需要自己编译”。

**实际不是。** 完整编译一遍（abuild，1366 个编译单元，8 核约 25 分钟）后，
产物 `.apk` 与官方包**内容完全一致**。原因：

```
[152/1366] Linking CXX static library plugin-worldclock/libworldclock.a
[242/1366] Linking CXX static library plugin-tray/libtray.a
[533/1366] Linking CXX static library plugin-taskbar/libtaskbar.a
[900/1366] Linking CXX static library plugin-mainmenu/libmainmenu.a
```

这些插件是**静态库，直接链接进 `lxqt-panel` 主程序**，本来就没有独立 `.so`。
两个二进制都链接了 `libdbusmenu-lxqt`，证明菜单功能是内建的。

菜单按钮当时不显示，真正原因是配置里 `icon = breeze` 不是有效图标名。

> 编译环境留在 `/opt/alpine-build`（约 1 GB），可以 `rm -rf` 删除。

---

## 5. DPU 黑屏与自愈（配合 44 号文档）

**今天共触发 7 次“物理屏幕全黑、只有鼠标”**，规律：

- 每次 `xrandr --rotate` 改变旋转方向，都有概率让 DPU 停止扫描输出主图层
- 内核日志会给出：`vblank timeout: 1000000` / `wait for commit done returned -110`
- `xrandr --query` 此时**仍然显示方向正常**，所以只能靠内核日志判断

自愈机制（`tablet-autorotate` 守护进程）：

1. 监听 `/dev/kmsg`，出现上述消息就强制 `normal → 目标方向` 两次 modeset
2. 若 60 秒内再次卡死（说明 modeset 无效），自动 `systemctl reboot`
3. 30 分钟内最多重启 3 次，避免无限重启循环

注意：`xrandr --dpms` 在这个版本不存在，X 里 DPMS 也是关闭的（`xset q` 显示
`DPMS is Disabled`），所以无法用断电再上电的方式恢复，只能 modeset 或重启。
