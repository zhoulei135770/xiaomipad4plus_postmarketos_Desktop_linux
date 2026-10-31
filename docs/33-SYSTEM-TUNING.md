# 系统优化与桌面（像一台真正的电脑）

> 2026-10-29 09:40。目标：让它用起来像一台电脑——**该有的设置界面、该有的开关**。
>
> 本文记录：内存优化、CPU 调频现状、桌面调优、控制中心。

---

## 1. 体检基线（改之前）

```
内存      3621 MB 总量 / 1214 MB 已用 / 2386 MB 可用
swap      zram 5.3 GB（未用）
CPU       8 核，**没有 /sys/.../cpufreq**（无调频接口）
显示      1920×1200 @ 60Hz（DSI-1）
桌面      XFCE 4 + Xorg，无合成器
服务      38 个运行中，0 失败
```

### 发现的浪费

| 进程 | 内存 | 说明 |
|---|---|---|
| `chatty` | 149 MB | 短信应用，平板用不上 |
| `gnome-calls` | 148 MB | 电话应用 |
| `vvmplayer` | 143 MB | 可视语音信箱 |
| `mmsdtng` / `vvmd` | — | 短信/语音后台 |

合计 **约 440 MB** 白占。

---

## 2. 内存优化（已完成）

**做法**：不改 `/etc/xdg/autostart`，而是在
`~/.config/autostart/` 放同名 `Hidden=true` 覆盖（可逆、不动系统文件）：

```
sm.puri.Chatty-daemon        → Hidden=true
org.gnome.Calls-daemon       → Hidden=true
org.kop316.vvmplayer-daemon  → Hidden=true
vvmd                         → Hidden=true
mmsd                         → Hidden=true
```

同时结束正在跑的进程，并调了两个内核参数：

```
vm.swappiness        = 150   （zram 场景下偏高是对的）
vm.vfs_cache_pressure = 50   （少回收 dentry/inode）
```

**效果：已用内存 1214 MB → 1070 MB（省 144 MB）**。

撤销：

```sh
sudo sh pad_disable_phone_apps.sh --undo
```

---

## 3. CPU 频率：**驱动有，缺 DT 节点**

查证结果：

| 项 | 结果 |
|---|---|
| `/lib/modules/.../qcom-cpufreq-hw.ko.zst` | ✅ **存在** |
| `qcom-cpufreq-nvmem.ko.zst` | ✅ 存在 |
| `modprobe qcom-cpufreq-hw` | ❌ 绑不上（没有 DT 节点） |
| `/sys/devices/system/cpu/cpu0/cpufreq/` | 不存在 |

SDM660 的 CPU 调频走 **OSM/APM**（`qcom,clk-cpu-osm`，寄存器 0x179c0000），
而 `qcom-cpufreq-hw` 是按 sdm845/sdm670 的寄存器布局写的（0x17d43000、偏移 0x920/0x9b0）。
**布局不同，不能直接套用。**

⇒ 真正的调频需要写一个 sdm660 的 OSM 驱动（此前评估 2–4 周）。
目前 CPU 跑在 bootloader 设定的固定档位。

**能做且已经做的**：减少后台负载（第 2 节），这直接降低平均功耗和温度。

---

## 4. 桌面调优（已完成）

| 项 | 改动 | 目的 |
|---|---|---|
| 合成器 | `use_compositing = true`，`vblank_mode = xpresent` | 有 vsync，滚动/拖窗不撕裂 |
| 窗口移动 | `box_move = false`、`box_resize = false` | 实时重绘，手感更跟手 |
| 字体 | `Noto Sans 11` | 10 寸屏触控可读 |
| 电源 | 插电时不自动黑屏（`blank-on-ac = 0`） | 当电脑用时不会自己黑 |

所有设置都走 `xfconf`，可用 `xfconf-query` 单独改回。

### 工具：`pad-asuser`

`su - user -c` 会清掉 `DISPLAY`/`DBUS_SESSION_BUS_ADDRESS`，导致 xfconf/gsettings
静默失败。所以我们用：

```sh
/usr/local/bin/pad-asuser xfconf-query -c xfwm4 -l
```

它用 `setpriv` 保持 uid 但带上完整的桌面环境变量。

---

## 5. 控制中心：`tablet-settings`

![控制中心](img/control-center.png)

一个触屏友好的 GTK3 面板：

```
电量 95%   内存 1129/3621 MB   CPU 39°C        ← 顶部状态，2 秒刷新

连接       WiFi  [开关]      蓝牙  [开关]
显示与声音  屏幕亮度 [滑条]    音量 [滑条]
维护       清理内存  显示设置
           电源管理  声音设置
           所有设置  虚拟键盘
电源       锁屏  重启  关机
```

### 安装位置

```
/usr/local/bin/tablet-settings                      程序
/usr/share/applications/tablet-settings.desktop     菜单项
/home/user/Desktop/tablet-settings.desktop       桌面图标
/etc/sudoers.d/tablet-settings                      最小权限规则
/usr/local/bin/tablet-drop-caches                   清理内存的 root 助手
```

### 权限设计

只放开三条，且都是**固定参数**（新版 sudo 不允许参数里用通配符）：

```
user ALL=(root) NOPASSWD: /usr/bin/tee /sys/class/backlight/lcd-backlight/brightness
user ALL=(root) NOPASSWD: /usr/local/bin/tablet-drop-caches
user ALL=(root) NOPASSWD: /bin/systemctl reboot
user ALL=(root) NOPASSWD: /bin/systemctl poweroff
```

---

## 6. ⚠️ 本轮踩的坑（重要）

### 6.1 `sed -i s/\r$//` 会删掉行尾的字母 `r`

GNU sed 把 `\r` 当成**字母 r** 而不是回车。于是：

```
A=/usr/local/bin/pad-asuser   →   A=/usr/local/bin/pad-asuse
```

**所有这类脚本都被削掉行尾的 r**。修法：不要用 sed 清 CRLF，
上传前确保文件本来就是 LF（我们的 `write` 工具生成的就是 LF）。

### 6.2 sudoers 里不能用通配符

```
/bin/sh -c echo * > ...     ← 新版 sudo 直接判为无效规则
```

而且**无效的 sudoers 文件会让整条 sudo 报错**（本次实测 sudo 仍能执行，但每
次都打印错误）。改用固定参数的 root 助手脚本。

### 6.3 `pkill -f tablet-settings` 会杀掉自己

SSH 命令的字符串里含 `tablet-settings`，`pkill -f` 会匹配到这条命令本身。
要用 `pkill -x` 或精确路径。

### 6.4 `subprocess.CompletedProcess` 没有 `.ok`

那是 `requests` 的 API，要用 `returncode == 0`。（设置程序第一版就崩在这里）

---

## 7. 还没做 / 可以继续

| 项 | 说明 |
|---|---|
| **CPU 调频** | 需要写 sdm660 OSM 驱动（大工程） |
| **帧率实测** | 可以在平板上跑 `glxgears`/`ffmpeg` 测 fps，目前只开了 vsync |
| **把设置加入面板** | 面板启动器槽位是 `launcher-13`，还没往里加 |
| **greeter 常驻** | `greetd` 还挂着一个 greeter 会话（c1/tty7），可考虑关掉省内存 |
| **开机自启设置** | 目前要手动点桌面图标 |

---

## 8. 脚本索引

```
scripts/sys_survey.sh            体检：内存/CPU/图形/服务
scripts/desk_survey.sh           桌面会话与设置
scripts/cpufreq_probe.sh         CPU 调频能力探测
scripts/tools_survey.sh          可用工具（亮度/音量/键盘）
scripts/pad_asuser.sh            以桌面用户身份执行（带环境）
scripts/pad_tune_desktop.sh      桌面调优
scripts/pad_disable_phone_apps.sh 关手机应用（可 --undo）
scripts/pad_tune_memory.sh       内存参数
patches/tablet-settings          控制中心源码
patches/install-tablet-settings.sh  安装脚本
```
