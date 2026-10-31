# 67 — 电源键 / 锁屏 / 休眠：现状与设计

> 10-31。用户问"锁屏和休眠结合按键是不是还没解决"。结论：**是"用禁用+替代方案解决"的**，
> 真正没解决的只有**内核真休眠**。

## 1. 设计（当前生效）

| 项 | 实现 | 位置 |
|---|---|---|
| 真休眠 | **完全禁用** | 三个 target masked；`/etc/systemd/sleep.conf.d/00-clover-suspend-safety.conf` 里 `AllowSuspend=no` |
| logind 电源键/睡键 | **ignore** | `/etc/systemd/logind.conf.d/{90-clover-powerkey,90-no-idle,91-no-suspend}.conf` |
| 电源键 | **自研守护进程** `tablet-powerkeyd` | `/usr/local/bin/tablet-powerkeyd` + systemd 单元 |
| 休眠替代 | **伪休眠** `tablet-sleep` | 关背光 + DPMS Off + 停帧 |
| 锁屏 | **没有**（无密码锁） | 电源键只关背光 |
| 唤醒 | 电源键任意键 / 触摸 / 键盘鼠标 | `tablet-powerkeyd` 监听所有 input 设备 |

### 为什么电源键不交给 logind

所在这版 systemd **拒绝** `HandlePowerKey=lock-session`（报 `Invalid argument`），
所以用 `HandlePowerKey=ignore` + 自研 daemon。

### 为什么不能真休眠

`mdss_runtime_suspend` 会让内核硬挂死（CPU5 被锁，watchdog trace 记录在
`/var/log/mdss-suspend-bug.txt`）。历史上两次远程 suspend 测试都导致设备失联，
只能物理按电源键恢复。

```
clk_branch_toggle -> clk_core_disable -> mdss_runtime_suspend [msm]
  -> mdss_pm_suspend -> device_suspend -> dpm_suspend -> pm_suspend
```

修复方向（上游）：suspend 前先 `drm_atomic_helper_suspend()`（主线后来的做法），
或让 msm/DPU 的 `runtime_suspend` 不要直接关时钟。

## 2. 伪休眠 `tablet-sleep`

```
tablet-sleep          # 关背光 + DPMS off（瞬间）
tablet-sleep wake     # 恢复
tablet-sleep status   # 查看状态
```

- 优点：**零风险**、瞬间唤醒、背光与渲染都停；
- 缺点：CPU 仍在跑（约 1–2 W），不是真休眠的 0.1 W 级。

## 3. 电源键 `tablet-powerkeyd`

- 短按：面板在「关背光 / 点亮」之间切换；
- 任意输入（触摸、键盘、鼠标）：面板若关着则点亮；
- 状态从 DRM connector 读取（因为 `xset q` 永远显示 `Monitor is On`）。

## 4. 仍然没解决的

1. **真休眠**（内核 DPU 死锁）——需要上游修复；
2. **锁屏/安全锁**——当前无锁屏；若要需要另装 locker（会和自动登录冲突）。

## 5. 若要测真休眠（危险，必须人在旁边）

```sh
sudo systemctl unmask sleep.target suspend.target
sudo sh -c 'echo +30 > /sys/class/rtc/rtc0/wakealarm'   # 先设 RTC 闹钟
sudo systemctl suspend
# 30 秒内无响应 = 死锁，长按电源键 10 秒硬重启
```

⚠️ 历史上 RTC 闹钟**并不能唤醒**这台机器（只有电源键能），所以务必人在旁边。

---

## 6. 2026-10-31 修复：Wayland 下的电源键

### 6.1 症状

- 按电源键**屏幕不黑**；
- 按一下就弹出「关机/重启/休眠/锁屏」菜单。

### 6.2 三个根因

1. **`tablet-powerkeyd` 用的是 X11 的 `xset dpms force off`**，而桌面是 **labwc（Wayland）** → 命令无效；
   它判断屏幕状态读的是 DRM `dpms` 属性，Wayland 下恒为 `On`，所以永远"只会关不会开"。
2. **labwc 自己也绑定了电源键**：`~/.config/labwc/rc.xml` 里
   `XF86PowerOff → lxqt-leave`（这就是弹菜单的元凶）。
3. **LXQt 全局快捷键** 也绑了 `XF86PowerOff → powermanager/keypoweroff`。

### 6.3 修复

| 项 | 做法 |
|---|---|
| 关屏 | 改为调用 `tablet-sleep`（真正写 `backlight/brightness=0`），唤醒调 `tablet-sleep wake` |
| 状态判断 | 用背光值（0 = 已熄屏）+ `/run/tablet-sleep.saved`，不再依赖 DRM dpms |
| 自动亮度冲突 | `tablet-autobright` 在 `/run/tablet-sleep.saved` 存在时跳过，不再抢背光 |
| labwc 绑定 | 删除 `XF86PowerOff` 键位（备份 `rc.xml.bak-keypower`） |
| LXQt 快捷键 | `[XF86PowerOff.41] Enabled=false`（备份 `globalkeyshortcuts.conf.bak-keypower`） |
| **长按 3 秒出菜单** | `tablet-powerkeyd` 记录按下/抬起时间；≥3 s 执行 `lxqt-leave` |
| 菜单弹不出的坑 | `session_env()` 原来只找 `xfce4-session`（旧桌面），拿不到 `WAYLAND_DISPLAY` → `lxqt-leave` 走 xcb 崩溃。改为识别 `lxqt-session`/`labwc` 并注入 `WAYLAND_DISPLAY` + `QT_QPA_PLATFORM=wayland` |

### 6.4 实测

```
短按  -> power key: display off   （背光 255 -> 0，autobright 不再覆盖）
再按  -> power key: display on    （恢复原亮度）
长按3s -> power key: long press -> leave menu  →  LXQt 关机菜单
```

## 7. 2026-10-31：卸载 XFCE

桌面最终定为 **labwc + LXQt**，XFCE 不再使用，已卸载：

```
53 个 xfce* / xfwm4 / thunar / xfconf / exo / garcon / tumbler / mousepad / ristretto 包
-> 0 个残留
```

**卸载前钉住的两个共享包**（否则会被当作孤儿删掉）：

```sh
apk add --no-progress procps-ng font-dejavu   # ps/top/free 与界面字体
```

会话入口未变：`greetd -> /usr/local/bin/tablewayland-session -> startlxqtwayland`，
卸载后 `/usr/share/wayland-sessions/` 只剩 `labwc`、`lxqt-wayland`、`phosh`。

结果：包数 1712 → 1634，磁盘 6.0 G → 5.9 G，当前会话与组件全部正常。

---

## 8. 锁屏（2026-10-31 晚）

### 8.1 为什么之前没有锁屏

原来是"能关屏、但没有锁"：电源键只关背光。要做锁屏有两个坑：

1. **swaylock 在这台机器上只出黑屏**（`ext-session-lock` + wlroots/EGL 渲染在 llvmpipe 上出不了图），
   进程在跑、屏幕全黑、没有密码框 → 改用 **gtklock**（GTK4 + layer-shell，渲染路径不同）。
2. **PAM 认证链路是断的**：`/etc/pam.d/gtklock` 是 `auth include login`，而 `/etc/pam.d/login`
   指向的 `base-auth` 在 `/etc/pam.d/` 里根本不存在 → 出现"输密码框一闪就进桌面"。
   真正的默认配置在 **`/usr/lib/pam.d/`**（`base-auth`/`base-session` 里有 `pam_systemd`）。

### 8.2 ⚠️ 重大教训：不要整份覆盖 `/etc/pam.d/base-*`

我一开始自己在 `/etc/pam.d/` 新建了 `login`、`base-auth`、`base-session` 等，
**覆盖了发行版默认值**（它们会 shadow `/usr/lib/pam.d/`）。
结果 `base-session` 没有 `pam_systemd` → 会话不注册到 logind → `libseat` 打不开 seat
→ greetd 的 greeter 崩溃 → **开机没有桌面**（只有一行行报错）。

修复：删掉自己创建的那些文件，让 `/usr/lib/pam.d/` 生效；锁屏只需要它自己的
`swaylock` / `gtklock` 配置项（引用官方 `base-*` 即可）。

### 8.3 现在锁屏行为

| 场景 | 行为 |
|---|---|
| 短按电源键 | `gtklock` 锁屏 + 关背光 |
| 开机 | 自动登录后 **立即锁屏**（labwc autostart 里启 `gtklock -d`），要输密码才进桌面 |
| 解锁 | 输入登录密码（PAM `pam_unix`） |
| 长按 3 秒 | LXQt 关机菜单 |

锁屏期间的"亮屏"由 `tablet-powerkeyd` 负责（任意输入唤醒背光），密码由 gtklock 处理。

## 9. 音量键（2026-10-31 晚）

| 项 | 结论 |
|---|---|
| 谁在监听 | 没有任何现成程序；`lxqt-globalkeyshortcuts` 已被停用 |
| 音量键设备 | 音量+ = `gpio-keys`，音量- = `pm8941_resin` |
| 音频后端 | **PulseAudio**（PipeWire 在跑但没有节点，`wpctl` 无效） |
| 实现 | `tablet-powerkeyd` 直接处理 KEY_VOLUMEUP/DOWN → `pactl set-sink-volume ±5%` |
| 重复通知 | 我们发的 `notify-send` 和 **lxqt-panel 自己的 OSD** 重复 → 去掉我们那一个 |
| 防抖 | 同键 200 ms 内只处理一次（某些设备会重复上报） |
| `No qdbus command available` | `lxqt-qdbus` 是脚本，需要 `qdbus` → 装 `qt6-qttools`（含 `qdbus6`，9 MiB） |

## 10. 桌面"应用菜单"图标（2026-10-31 晚）

`/usr/local/bin/tablet-menu` 原来是 `jgmenu_run`。jgmenu 在 labwc/Wayland 下弹出的是
**独立 surface，点其它地方不会消失**（只能 kill）——就是"多点一个关不掉的菜单"。

改为调用 LXQt 面板原生菜单：

```sh
exec /usr/bin/lxqt-qdbus openmenu
```

该菜单锚定在面板上，点别处自动关闭。**jgmenu 已卸载**。

## 11. 2026-10-31 晚其它

- **XFCE 已卸载**（53 个包），桌面固定为 labwc + LXQt；
- 桌面图标的黄色 ⚠ 是 pcmanfm 的"未受信任启动器"标记，已写入
  `metadata::trusted=true`（`gio set`，需要 `XDG_RUNTIME_DIR`）；
- **OTG 在硬复位后会失效**（SMB2 的 CC 检测读不到任何东西，`dfp=0`、强制 `otg_vbus=1` 也无枚举），
  **重启后自愈** —— 硬复位后 PMIC/USB-C 状态不一致，属已知现象，不用改软件。
