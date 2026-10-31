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

---

## 12. 触摸 PIN 锁（取代 gtklock）

### 12.1 为什么 gtklock 不行

gtklock 用的是 **`ext-session-lock`**：锁定时整个会话被它独占，
**任何第三方屏幕键盘都画不出来**。实测两种 OSK 都被盖住：

| 方案 | 结果 |
|---|---|
| `wvkbd`（layer-shell 虚拟键盘） | 进程在跑，但被 gtklock 的全屏 surface 遮住 |
| `squeekboard`（输入法协议） | `Panel has been configured, but no request is pending`，GTK4/labwc 不触发 text-input |

而这台平板**没有硬件键盘**，所以 gtklock 等于"锁死自己"。

### 12.2 方案：自带数字键盘的 PIN 锁

`tablet-pinlock`（GTK4 + **gtk4-layer-shell**）：

- 覆盖全屏的 layer-shell surface（overlay 层、四边锚定、键盘独占）；
- 显示时钟/日期、PIN 圆点、0–9 数字键盘 + ⌫ + OK；
- PIN 以 **sha256** 存在 `/etc/tablet-lock-pin`（默认 **1234**，4–6 位）；
- 输错清空并提示"PIN 错误"，输对后退出、回到桌面。

文件：

```
/usr/local/bin/tablet-pinlock        启动包装（设置 LD_PRELOAD 后 exec python）
/usr/local/lib/tablet-pinlock.py     主程序
/usr/local/bin/tablet-lock-pin       PIN 管理：set <pin> | show | reset
/etc/tablet-lock-pin                 PIN 的 sha256
```

### 12.3 关键坑：Python 用 gtk4-layer-shell 需要 LD_PRELOAD

直接 `import Gtk4LayerShell` 会报：

```
Failed to initialize layer surface, GTK4 Layer Shell may have been linked after libwayland
```

因为 Python 动态加载 so 的时机晚于 libwayland。解法：

```sh
export LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so.0
```

包装脚本已经内置这一行。

### 12.4 触发方式

| 场景 | 行为 |
|---|---|
| 短按电源键 | 启动 `tablet-pinlock` + 关背光 |
| 开机 | labwc autostart 里延迟 3 秒启动 `tablet-pinlock` |
| 解锁 | 触摸输入 PIN → OK |

`tablet-powerkeyd` 通过 `pgrep -f /usr/local/lib/tablet-pinlock.py` 判断"是否已锁"，
所以重复按电源键不会叠加多个实例。

### 12.5 安全性说明

这是**应用层锁**（不是 `ext-session-lock`）：能挡住日常误触和普通用户，
但技术上不是内核/合成器级别的会话锁。考虑到"没有键盘就先得能进去"，
这是在可用性与安全性之间的取舍。

---

## 13. 整机假死根因：DPU ring hang（2026-10-31 晚）

### 13.1 症状

- 屏幕定格、**触摸无反应**、SSH 连不上（TCP 能建立但读不到 banner）；
- 只能长按电源 10 秒强断；
- 重启后 1~2 分钟又复现（当时开了"开机自动锁屏"）。

### 13.2 日志证据（`journalctl -b -1`）

```
17:19:30 [drm:adreno_idle [msm]] ERROR: 5.1.2.0: timeout waiting to drain ringbuffer 0 rptr/wptr = 23/C
17:19:30 msm_dpu c901000.display-controller: CP | opcode error | possible opcode=0x00000000
17:19:31 msm_dpu: [drm:a5xx_irq] ERROR: gpu fault ring 0 fence ffffffe9 status 800001C1
17:19:33 msm_dpu: [drm:recover_worker] ERROR: 5.1.2.0: hangcheck recover!
17:19:33 msm_dpu: [drm:recover_worker] ERROR: offending task: labwc
17:20:02 rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
17:20:02 rcu:       1-...0: (8 ticks this GP) idle=... softirq=5759/5761
17:20:12 watchdog: BUG: soft lockup - CPU#3 stuck for 22s! [rcu_exp_gp_kthr]
```

**因果链**：显示控制器命令队列卡住 → DPU 报 opcode error → 内核 hangcheck 尝试恢复 →
CPU 关中断死循环 → RCU 等不到该 CPU → 整机假死（所以 SSH 也不响应）。

### 13.3 触发条件与处理

| 触发 | 处理 |
|---|---|
| **开机自动锁屏**（layer-shell overlay 在 DPU 初始化窗口期提交） | 删除该 autostart 项，开机不再自动锁屏 |
| 合成器 GPU 提交 | 先进 `WLR_RENDERER=pixman` 全软件渲染验证（稳定但太卡），确认根因后**改回 GPU**，只让 GTK 应用走 cairo（`GSK_RENDERER=cairo`），实测 5 分钟 0 次 DRM 错误 |

结论：**没有开机锁屏时，硬件 GPU 渲染是稳定的**；之前的假死是"锁屏图层 + 开机提交"踩中了 DPU 的 bug。

下次再遇到假死，先看：

```sh
journalctl -b -1 | grep -iE "adreno_idle|opcode error|hangcheck|soft lockup|rcu.*stall"
```

## 14. 触摸标定（Wayland / labwc）

### 14.1 为什么需要标定

面板**原生是竖屏 1200×1920**，桌面靠 `wlr-randr --transform 90` 转成横屏 1920×1200。
触摸坐标要经过"设备坐标 → 输出变换"的映射，udev 里的 `LIBINPUT_CALIBRATION_MATRIX`
必须与之匹配，否则点击会镜像/旋转。

### 14.2 标定过程（实测法）

1. 让用户在四角各点一次；
2. 观察"点击位置 → 实际响应位置"的对应关系（例如：左下→左下、右上→右上、
   左上→右下、右下→左上 = 180° 旋转）；
3. 组合出逆变换矩阵，写入 udev 规则，**重启会话**（libinput 只在打开设备时读矩阵）。

### 14.3 最终配置

```udev
# /etc/udev/rules.d/99-goodix-landscape.rules
ATTRS{name}=="Goodix Capacitive TouchScreen", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 -1 1 1 0 0"
```

即 `x' = 1 - y`、`y' = x`（这也正是当年 X11 时代在用的那份矩阵）。

验证：四角点击全部落位正确。

## 15. 桌面体验修正

| 问题 | 原因 | 修复 |
|---|---|---|
| 点图标"跑到右下角" | labwc 窗口放置策略 `cascade` | `~/.config/labwc/rc.xml` → `<placement><policy>center</policy>` |
| 图标单击只选中、不打开 | `SingleClick=false` | `~/.config/pcmanfm-qt/lxqt/settings.conf` 里 `[Behavior]` 和 `[Desktop]` 都设为 `true`（需重启会话） |
| 屏幕键盘卡在屏幕上、布局错乱 | `wvkbd-deskintl` 残留实例 | `pkill -f wvkbd`；`/usr/local/bin/tablet-keyboard` 改为一键展开/收起 wvkbd |

## 16. 排查工具箱（本机已装）

| 工具 | 用途 |
|---|---|
| `libinput debug-events --device /dev/input/event4` | 看触摸原始坐标（已应用标定矩阵） |
| `wlrctl toplevel list/close` | 列出/关闭窗口 |
| `wev` | 查看应用实际收到的输入事件 |
| `grim` | 截图 |
| `wtype` | 注入键盘事件（测输入法/中文候选） |
| `journalctl -b -1` | 上一次启动的日志（假死分析主力） |
