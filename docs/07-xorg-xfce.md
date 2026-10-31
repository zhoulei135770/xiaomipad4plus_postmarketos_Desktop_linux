# 07 · 原生 Xorg + XFCE 桌面改造（2026-10-24）

> 本文记录把设备从 **Phosh（Wayland）** 迁移到 **原生 Xorg + XFCE** 的完整过程，
> 包含一次严重的 **GPU 硬挂死事故**及其根因、实测验收数据、以及后续待办。
>
> 结论先行：**XFCE 桌面已经跑通并成为默认开机桌面**，但**横屏旋转暂时禁用**
> （会触发 Adreno 512 硬挂死），当前是原生竖屏 1200×1920。

---

## 0. TL;DR

| 结论 | 内容 |
|---|---|
| ✅ 成功 | 原生 Xorg 驱动 msm_dpu，`glamor` 拿到 **FD512 硬件加速** |
| ✅ 成功 | XFCE 4.20 完整会话：`xfwm4` 接管窗口管理，panel/desktop/thunar 全部正常 |
| ✅ 成功 | **开机自动进 XFCE**（greetd → launcher → Xorg → XFCE），9 秒出窗口管理器 |
| ✅ 成功 | 中文界面、`fcitx5` 输入法、DPI 150、触控对齐、无锁屏/无休眠 |
| ✅ 成功 | 远程桌面 `x11vnc` + `noVNC`，浏览器即可用电脑键鼠操作平板 |
| ✅ 成功 | **横屏 1920×1200 可用**（软件加速，零 GPU 风险），一键切换竖/横 |
| ❌ 限制 | **硬件只有 0°/180° 旋转**，横屏必须软件合成（CPU 代价） |
| ⚠️ 事故 | `xrandr --rotate` + glamor 会触发 GPU 硬挂死，需物理重启（§3） |
| ⏭ 待办 | 音频、蓝牙键鼠、触屏拼音实测、休眠 |

---

## 1. 为什么换掉 Phosh

`06-xfce-experiment.md` §3 已证明：Phosh（`phoc`/wlroots）的 Xwayland 自带 root WM
（在 X 里显示为 `"wlroots wm"`），`xfwm4 --replace` 永远等不到接管，导致
`xfce4-panel` segfault、`xfdesktop` SIGBUS。**这不是配置问题，是架构冲突。**

原生 Xorg 没有这个冲突 —— 实测 `xfwm4` 直接成为 WM、panel 正常存活、零崩溃。

---

## 2. 技术验证链（每一步都有实测）

### 2.1 modesetting 驱动可用

```
(II) Matched modesetting as autoconfigured driver 0
(II) modeset(0): using drv /dev/dri/card1
(II) glamor: Using OpenGL 3.1 context.
(II) glamor X acceleration enabled on FD512        ← 硬件加速，不是软渲染
(II) Modeline "1200x1920"x60.0  165.58 MHz
```

### 2.2 关键障碍：`Xorg.wrap` 只允许控制台用户

```
/usr/libexec/Xorg.wrap: Only console users are allowed to run the X server
```

greetd 起的会话不是 logind 认定的“活动控制台会话”，所以被拒绝。
**解法**：`/etc/X11/Xwrapper.config`

```
allowed_users=anybody
needs_root_rights=yes
```

### 2.3 面板原生方向是竖屏

```
/sys/class/drm/card1-DSI-1/modes  →  1200x1920     ← 不是 1920x1200
DTS: touchscreen-size-x = <1200>; touchscreen-size-y = <1920>
```

**屏幕和触控的坐标系都是竖屏**。想要横屏必须旋转，而这正是事故来源（§3）。

### 2.4 触控坐标变换矩阵

X 的 `Coordinate Transformation Matrix` 必须和 framebuffer 方向**匹配**：

| framebuffer | 正确矩阵 |
|---|---|
| 竖屏（原生，不旋转） | `1 0 0  0 1 0  0 0 1`（单位阵） |
| `xrandr --rotate left` | `0 1 0  -1 0 1  0 0 1` |

**踩过的坑**：禁用旋转后忘记把矩阵改回单位阵，导致触摸转了 90°、点哪都不对。

---

## 3. ★ 严重事故：GPU 硬挂死（必读）

### 3.1 现象

- **VNC 能看到完整桌面，但物理屏幕全黑**
- `xrandr` 命令**永久阻塞**，之后所有 `xdpyinfo` 超时
- 屏幕上没有任何输出

### 3.2 根因链（逐环有证据）

```
1) xrandr --output DSI-1 --rotate left
     ↓  glamor 需要用 GPU 做旋转合成（shadow buffer）
2) Adreno 512 (a5xx) 环形缓冲 fault
     [drm:a5xx_irq] *ERROR* gpu fault ring 0 fence 4a18 status 800001C1
3) hangcheck 反复恢复失败
     [drm:recover_worker] *ERROR* 5.1.2.0: hangcheck recover!
     [drm:a5xx_preempt_timer] *ERROR* 5.1.2.0: preemption timed out
4) Xorg / xfwm4 变成不可回收的僵尸，旧 Xorg 的一个线程卡在 D 态
     pid 52216 thread 52224: wchan = __flush_work
5) 该 work 阻塞 VT 激活，此后任何新 Xorg 都卡在
     pid 60432 wchan = vt_waitactive
   → 所有 X 客户端超时（:0 / :1 / :3 全部一样）
6) 附带：display :0 的抽象 socket (@/tmp/.X11-unix/X0) 无主残留，无法从用户态删除
```

**累计 42 次 watchdog `hard LOCKUP`（CPU5），耗时约 10 分钟才勉强退出。**

### 3.3 为什么“屏幕黑但 VNC 有画面”

X 仍在往自己的 framebuffer 渲染（所以 VNC 能读到），但 **GPU 故障后 CRTC 无法提交新帧到面板**，
物理屏就没有更新。

### 3.4 恢复过程（失败的尝试，记录下来省时间）

| 尝试 | 结果 |
|---|---|
| `kill -9` Xorg/xfwm4 | ❌ 变僵尸，`__flush_work` 线程杀不掉 |
| 换 display `:1` | ❌ X 启动但卡在 `vt_waitactive`，不响应客户端 |
| 删 `/tmp/.X0-lock` + socket 文件 | ❌ 抽象 socket 无文件实体，删不掉 |
| `chvt` 切换 VT | ❌ VT 子系统被 `__flush_work` 卡住 |
| **物理重启** | ✅ **唯一有效方案**，重启后 GPU 故障计数归零 |

### 3.5 教训

> **在这块 Adreno 512 + 当前内核上，不要用 `xrandr` 旋转 framebuffer。**
> 旋转会让 glamor 走 GPU 合成路径，直接触发 a5xx 环形缓冲故障。

---

## 4. 最终架构

```
greetd (vt=7, user=user)
  └─ /usr/local/bin/tablet-session-launcher          ← 90 秒看门狗 + Phosh 回退
       ├─ /usr/local/bin/xfce-x-session              ← 起 Xorg :0，等 X 就绪
       │    └─ dbus-run-session -- /usr/local/bin/xfce-tablet-session
       │         ├─ 旋转（ROTATE_OUTPUT=1 才开，默认关）
       │         ├─ 触控矩阵（跟随旋转状态）
       │         ├─ DPI 150（xrdb + **xfconf**，后者才是权威）
       │         ├─ xset s off / -dpms / noblank
       │         ├─ fcitx5（中文输入）
       │         └─ exec startxfce4
       └─ 失败时 → /usr/libexec/phrog-greetd-session（Phosh）
```

### 4.1 文件清单

| 文件 | 作用 |
|---|---|
| `/usr/local/bin/tablet-session-launcher` | 入口，含僵尸感知的存活检测 + 回退 |
| `/usr/local/bin/xfce-x-session` | 启动 Xorg，等 `xrandr` 可用 |
| `/usr/local/bin/xfce-tablet-session` | 桌面配置 + 启动 XFCE |
| `/usr/local/bin/restore-phosh` | **一键回退到 Phosh** |
| `/etc/phrog/greetd-config.toml.bak` | 原始 greetd 配置备份 |
| `/etc/X11/Xwrapper.config` | 允许非控制台用户启动 X |
| `/etc/tablet/force-phosh` | 存在时强制走 Phosh（应急开关） |
| `/etc/nftables.d/50-tablet-vnc.nft` | 放行 6080（VNC） |

### 4.2 三层安全网

1. **看门狗**：90 秒内 `xfwm4` 没出现 → 自动回 Phosh
2. **应急开关**：`touch /etc/tablet/force-phosh && systemctl restart greetd`
3. **本地控制台**：`getty@tty1/tty2/tty3` 已启用

---

## 5. 实测验收数据（34 项全部 PASS）

### 5.1 分辨率 ✅

| 项 | 实测 | 期望 |
|---|---|---|
| framebuffer | `1200x1920+0+0` | 面板原生 |
| 面板原生模式 | `1200x1920` | 一致 |
| X dimensions | `1200x1920` | 一致 |

> 注意：内核上报的物理尺寸 `318x509 mm` 是**错的**（真实 10.1" 应约 217×136 mm），
> 所以 X 自算 DPI 只有 96 —— 必须靠 Xft.dpi 显式覆盖。

### 5.2 DPI / 字体 ✅

| 项 | 值 |
|---|---|
| `xfconf /Xft/DPI` | **150**（权威，xsettingsd 读这个） |
| `xrdb Xft.dpi` | 150（后备） |
| subpixel RGBA | **rgb**（子像素抗锯齿开启） |
| hint style | **hintslight** |
| antialias | 1 |
| 字体 | `Noto Sans CJK SC 12` |
| 光标 | 36px |
| 中文解析 | `NotoSansCJK-Regular.ttc` ✅ |

**12pt 在 150dpi 下渲染为 25px**（96dpi 只有 16px，在 224dpi 面板上无法阅读）。
面板原生约 224dpi，150/224 = **1.49x UI 缩放**。

> **关键坑**：只写 `xrdb` 不够！XFCE 的 `xsettingsd` 以 **xfconf** 为准，
> 必须在 `startxfce4` **之前**把 `/Xft/DPI` 写进 xfconf。

### 5.3 触控 ✅

```
Coordinate Transformation Matrix: 1,0,0  0,1,0  0,0,1   ← 单位阵（竖屏正确）
touch device: Goodix Capacitive TouchScreen (id=9, pointer)
```

### 5.4 充电 ✅

| 时间 | 电量 | 电池电流 | 功率 |
|---|---|---|---|
| t0 | 67% | +467 mA | — |
| t1（+15s） | 67% | +322 mA | **+1.29 W** |

充电器 `online=1`、`current_max=1500 mA`、温度 30.8 ℃。

### 5.5 无锁屏 / 无熄屏 / 无休眠 ✅

| 项 | 值 |
|---|---|
| gnome `lock-enabled` | false |
| gnome `idle-activation-enabled` | false |
| gnome `idle-delay` | 0 |
| `sleep.target` / `suspend.target` | **masked** |
| XFCE `dpms-enabled` | false |
| XFCE `inactivity-on-ac` | 0 |
| 背光 | 200/255，`bl_power=0`（开） |

### 5.6 桌面组件 ✅

`Xorg` / `xfwm4` / `xfce4-session` / `xfce4-panel` / `xfdesktop` / `fcitx5` 全部存活，
`wmctrl -m` → `Name: Xfwm4`。

### 5.7 远程桌面 ✅

| 服务 | 状态 |
|---|---|
| `x11vnc` | active，`127.0.0.1:5900`（仅本机） |
| `novnc` | active，`0.0.0.0:6080`（局域网） |
| 访问 | `http://192.168.1.123:6080/vnc.html`，密码 `tablet` |

### 5.8 内核健康 ✅

```
GPU faults since boot : 0     （事故时是 16，之后 42 次 lockup）
D-state processes     : 0
uptime                : 281s
```

### 5.9 资源

内存 1.1 GiB / 3.5 GiB 已用，磁盘 6.0 G / 105.6 G（6%）。

---

## 6. 横屏：已解决（软件加速方案）

### 6.1 先排除的两条路

**A. 硬件旋转 —— 不可行**

`modetest` 显示 msm 驱动的平面只支持：
```
rotation property values:
  rotate-0=0x1  rotate-180=0x4  reflect-x=0x10  reflect-y=0x20
                ↑
        没有 rotate-90 / rotate-270
```
DSI-1 连接器有 **0 个** rotation 属性，`/sys/class/drm/card1-DSI-1/` 只有 9 个基础节点，
DT 里也没有 `panel-orientation`。

**结论：硬件只能转 180°，转不了 90°。横屏必须软件合成。**

**B. 客户端环境变量强制软渲染 —— 无效**

```bash
LIBGL_ALWAYS_SOFTWARE=1 xrandr --rotate left      # 仍报 FD512
GALLIUM_DRIVER=llvmpipe ...                        # 仍报 FD512
MESA_LOADER_DRIVER_OVERRIDE=llvmpipe ...           # 仍报 FD512
```

原因：**glamor 在 Xorg 进程启动时就绑定了 GPU**，客户端的环境变量管不到。
（这也说明早期“软渲染旋转成功”其实是运气，仍在 GPU 上跑。）

### 6.2 有效方案：Xorg 层关闭 glamor

```ini
# /etc/X11/xorg.conf.d/50-msm-soft.conf
Section "Device"
    Identifier  "msm-soft"
    Driver      "modesetting"
    Option      "AccelMethod" "none"
EndSection
```

验证结果：
```
OpenGL renderer string: llvmpipe (LLVM 23.1.3, 128 bits)   ← 真软件渲染
旋转后 X 稳定、GPU faults = 0
```

> `-configdir` 不能用绝对路径（Xorg 以 root 跑时要求相对路径），
> `-config` 传绝对路径也被拒。**最简单可靠的办法就是切换 `xorg.conf.d` 里的文件名。**

### 6.3 两种模式并存

| 模式 | 分辨率 | 渲染 | CPU | 风险 |
|---|---|---|---|---|
| **portrait**（默认） | 1200×1920 | glamor / FD512 | ~0% | 安全 |
| **landscape**（可选） | 1920×1200 | llvmpipe | 重绘时较高 | 安全（不碰 GPU 故障路径） |

切换命令：
```bash
tablet-display-mode            # 查看当前
tablet-display-mode landscape  # 切横屏（自动开软渲染 + 旋转 + 触控矩阵）
tablet-display-mode portrait   # 切竖屏（自动关软渲染 + 硬件加速）
```

内部实现：
- `/etc/tablet/landscape` 存在 → 横屏
- `50-msm-soft.conf` / `.off` 文件名切换来控制 Xorg 是否用 glamor
- 会话脚本读标志位，决定旋转和触控矩阵

### 6.4 踩到的坑：触控矩阵会被重置

**现象**：会话脚本明明设了 CCW 矩阵（日志有记录），但 `startxfce4` 起来之后
读回来是单位阵。手动设置则能稳定保持。

**结论**：重置发生在**会话启动窗口内**（`xfce4-session`/`xfsettingsd` 初始化期间），
不是某个长期运行的进程在反复改。

**解法**：在 `exec startxfce4` 之前，派生一个**延迟重应用**的后台进程：

```sh
for delay in 5 10 20 35; do
    sleep "$delay"
    TID=$(xinput list --short | grep -i goodix | grep -iv keyboard | ...)
    xinput set-prop "$TID" "Coordinate Transformation Matrix" $M
done &
```

> 另一个坑：**不要硬编码 `xinput` 设备 id**。X 重启后 id 会变（属性编号也会变，
> 观察到 128 → 122），必须每次按名字重新解析。

### 6.5 验收数据（2026-10-24 01:38，横屏模式，34 项全过）

```
framebuffer   1920x1200+0+0     rotation=left          ✅
renderer      llvmpipe (LLVM 23.1.3, 128 bits)         ✅
Xft/DPI       150（xfconf + xrdb 一致）                 ✅
RGBA/风格     rgb / hintslight / antialias=1           ✅
12pt 字体     25px；中文 NotoSansCJK-Regular.ttc        ✅
触控矩阵      0,1,0 -1,0,1 0,0,1                       ✅
充电          73%，+538 mA，2.16 W，30.0 ℃              ✅
锁屏/熄屏     全部 false / masked                       ✅
组件          Xorg/xfwm4/session/panel/desktop/fcitx5  ✅
VNC           6080 监听，5900 仅本机                     ✅
GPU faults    0                                        ✅
loadavg       0.54（8 核，很轻）                         ✅
```

**CPU 实测**：空闲时 `loadavg 0.54`，Xorg 累计 6.4%。重绘时（如滚动终端）会明显升高，
这是 llvmpipe 的固有代价，但**不影响日常使用**。

---

## 7. 顺带解决的其他问题

### 7.1 充电很慢（旧充电头）
| 项 | 旧头/线 | 新头/线 |
|---|---|---|
| 输入电流 | 32 mA | **1422 mA** |
| 电池电流 | **−365 mA（放电）** | **+1120 mA（充电）** |
| `current_max` | 25 mA | **1500 mA** |

**结论：供电链路是通的，只是对充电器有要求。** 5V/25mA 时充不进去（还会掉电），
换 5V/2A 后正常快充。`usb_type` 仍报 `Unknown` 属于驱动上报不全，不影响实际供电。

### 7.2 内存浪费
`gnome-calls` 120MB + `chatty` 119MB + `vvmplayer` 109MB + `goa-daemon` 65MB
≈ **430 MB 白耗**（无基带，这些应用永远无用）。已停用并禁用自启。

### 7.3 防火墙
pmOS 默认 `nftables` 策略是 **`policy drop`**，只放行 22/53/53317 等。
6080 被静默丢弃 → 浏览器超时。已加 drop-in：
```
/etc/nftables.d/50-tablet-vnc.nft
  add rule inet filter input tcp dport 6080 accept comment "noVNC remote desktop"
```

### 7.4 x11vnc 拒绝启动（Wayland 误判）
```
x11vnc: Wayland display server detected ... Exiting
```
用户会话环境里残留 `WAYLAND_DISPLAY=wayland-0`（Phosh 时代留下）。
**注意**：`Environment=WAYLAND_DISPLAY=` 设为空**没有用**（变量仍存在）。
必须用 `env -u WAYLAND_DISPLAY` 真正移除 → 已封装在 `/usr/local/bin/start-x11vnc`。

---

## 8. 触屏中文输入（2026-10-24 已打通）

### 8.1 组件与链路

```
onboard（屏幕键盘，停靠底部全宽 1920x340）
   ↓ 按键事件
fcitx5（输入法框架，pinyin 引擎）
   ↓ 候选词
应用（GTK/Qt 通过 GTK_IM_MODULE=fcitx 接入）
```

### 8.2 踩到的坑（都修好了）

**坑 1：fcitx5 反复饿死**

```
I] Disconnected from X11 Display :0
I] Save before exiting...
I] Unloading addon ...（全部卸载）
```

`fcitx5` **主动退出**，根因是 Phosh 时代残留的 `WAYLAND_DISPLAY=wayland-0`：
它先尝试 Wayland（失败），混合状态最终导致 X11 连接被丢弃。

**注意**：`Environment=WAYLAND_DISPLAY=` 设成空**没有用**（变量仍存在），
必须 `env -u WAYLAND_DISPLAY` 真正移除。这跟 x11vnc 的坑是同一个。

**坑 2：onboard 启动失败**

| 报错 | 原因 |
|---|---|
| `no such option: --notifications` | 我用了不存在的参数 |
| `Gdk-WARNING: cannot open display` | `DISPLAY` 没传进去 |
| 进程随 shell 退出而消失 | 前台启动，没托管 |

**解法**：写成 systemd `--user` 服务（`onboard.service`），带 `DISPLAY=:0`。

**坑 3：gsettings 键路径写错**

`org.onboard.window.docking-enabled` 不存在，正确写法是
`gsettings set org.onboard.window docking-enabled true`（schema 与键分开）。

### 8.3 最终配置

```bash
# fcitx5（systemd --user，自动重启）
~/.config/systemd/user/fcitx5.service
  ExecStart=/usr/bin/env -u WAYLAND_DISPLAY -u QT_QPA_PLATFORM fcitx5 --replace

# onboard（systemd --user）
~/.config/systemd/user/onboard.service
  Environment=DISPLAY=:0
  ExecStart=/usr/bin/onboard

# onboard 几何（底部全宽）
org.onboard.window               docking-enabled=true  docking-edge='bottom'
                                 force-to-top=true     window-decoration=false
org.onboard.window.landscape     dock-width=1920  dock-height=340  dock-expand=true
org.onboard.auto-show            enabled=true
```

### 8.4 验收结果（16 项全过）

```
[PASS] fcitx5 / onboard 进程存活
[PASS] 两个 systemd --user 单元 active + enabled（重启后自动起）
[PASS] fcitx5-remote 返回 0（客户端可达）
[PASS] libpinyin.so 存在，profile 的 DefaultIM=pinyin
[PASS] GTK_IM_MODULE / QT_IM_MODULE / XMODIFIERS 全部为 fcitx
[PASS] onboard 停靠底部、全宽 1920、auto-show 开启
```

**实测打字**：用 `xdotool` 向窗口发送 `nihao`，屏幕底部出现候选词 **「你好」**，
证明拼音转换链路完整工作。

> 截图见 `tools/ime_typing.png`（候选词条清晰可见）。

---

## 9. 音频（麦克风 ✅ / 扬声器 ❌ 需板级原理图）

### 9.1 结论

**音频链路是好的。** 用 15 秒音频、在播放中途（t+2s / t+6s）采样 DAPM：

```
pcm0p status : state: RUNNING      ← 硬件流真的打开
hw_params    : 7 lines             ← 参数已协商
RX_BIAS      : On                  ← 模拟偏置上电
SPK_OUT      : On                  ← 扬声器输出通电
bias_level   : On                  ← codec 完全唤醒
dsp failures : 0
```

耳机模式同样正常（`RX_BIAS On`、`SPK_OUT Off`、`HPHL PA` 通电），两条路径都能切换。

### 9.2 我先前错在哪（重要教训）

我曾在本文件里写下"根因是 DSP 层失败，`q6asm_dai_prepare` 返回 -22"。**那是错的**，
是我自己的测试方法造成的假象：

| 我的错误 | 后果 |
|---|---|
| 用 **1 秒** 的 tone.wav，却在 `sleep 3` 之后才检查状态 | 播放早已结束，读到 `pcm closed` / DAPM `Off`，误判为"没通电" |
| 让 PulseAudio 与 `aplay` **同时**抢声卡 | 产生 `q6asm_dai_prepare -22`、`Failed to close copp` 等错误 |
| 把并发争用产生的错误当成持久性驱动缺陷 | 在文档里写下错误的根因 |

**正确做法**：用足够长的音频，在**播放中途**采样；测裸 ALSA 时先停 PulseAudio。

### 9.3 真正的配置缺口：扬声器要走 RX3

UCM 只定义了耳机（走 RX1/RX2），扬声器需要 RX3：

```
扬声器: Digital I2S RX3 → RX3 MIX1 → Digital RX3 INT → PDM_RX3
          → SPK DAC → SPK PA → SPK_OUT        （DAPM 实测可通电）

耳机:   Digital I2S RX1/2 → PDM_RX1/2 → HPHL/HPHR DAC → PA → HPH_L/R
```

DAPM 里的完整证据（`SPK DAC` 的输入明确是 `PDM_RX3`）：
```
SPK DAC  widget-type mixer
  in  "Switch" "PDM_RX3"
  out "static" "SPK PA"
SPK PA   widget-type pga
  in  "static" "SPK DAC" + "SPKR_CLK" + "RX_BIAS"
  out "static" "SPK_OUT"
```

### 9.4 最终配置

```bash
tablet-audio speaker     # 切到扬声器：RX3 + SPK DAC=on，HPHL/HPHR=ZERO
tablet-audio headphone   # 切到耳机：  SPK DAC=off，HPHL/HPHR=Switch
tablet-audio status      # 查看当前路由
```

开机自动生效：`/etc/systemd/system/alsa-restore-tablet.service`
（`alsactl restore` + 显式 RX3 路由）。

### 9.5 不要做的事

- **不要**给 `/usr/share/alsa/ucm2/Xiaomi/clover/HiFi.conf` 追加 `Speaker` section：
  我试过，会让 UCM 解析失败，声卡只剩 `off` profile（已回滚，备份在 `HiFi.conf.orig`）
- **不要**装 `pipewire-pulse`：与 `postmarketos-base-ui-audio-backend-pulseaudio` 冲突
- **不要**用 1 秒的测试音判断音频是否工作

### 9.6 麦克风（✅ 可用，需软件增益）

**采集设备是 `hw:0,1`（MultiMedia2）**，不是 `hw:0,0`：

```
hw:0,0 -> arecord: audio open error: Invalid argument
hw:0,1 -> OK
```

与 UCM 定义一致：`SectionDevice."Mic" { Value { CapturePCM "hw:${CardId},1" } }`

**路由**（UCM 的 `Mic` EnableSequence）：
```bash
amixer -c 0 sset 'Digital CIC1 MUX' AMIC
amixer -c 0 sset 'Digital DEC1 MUX' ADC1
amixer -c 0 sset 'ADC1' 8          # 0-8，48 dB 上限
```

**DAPM 证明链路通电**（录音时）：`MIC_BIAS1 On`、`AMIC1 On`、`ADC1 On`。

**问题：原始电平极低**

| 配置 | 峰值 | 占满量程 |
|---|---|---|
| 裸 ALSA `hw:0,1`，ADC1=8 | 54 | **0.16%** |
| PulseAudio source @400% | 4288 | **13.09%** |

增益扫描证明这是**真实的、可放大的信号**（不是坏输入）：
```
ADC1=0 -> peak 6
ADC1=3 -> peak 10
ADC1=6 -> peak 39
ADC1=8 -> peak 59      ← 单调上升
```

**解决：PulseAudio 源增益 400%（36 dB 软件增益）**

```bash
pactl set-source-volume alsa_input.platform-sound.HiFi__Mic__source 400%
pactl set-default-source   alsa_input.platform-sound.HiFi__Mic__source
```

已持久化：`~/.config/systemd/user/tablet-mic-volume.service`（enabled）。

**为什么这么弱**：`MIC BIAS External1` 的电压（DT 的 `qcom,micbias-lvl`）
**没有暴露给用户空间**，`amixer` 找不到对应控件，只能靠 DAPM 开关。
提高偏置电压需要改内核/DT。

**实测录音**（重启后，用户身份）：
```
frames=437759  peak=4288 (13.09% FS)  rms=713.8
```

### 9.7 音频相关服务清单

| 单元 | 作用 | 状态 |
|---|---|---|
| `alsa-restore-tablet.service` (system) | 开机恢复扬声器 RX3 路由 | enabled |
| `alsa-mic-tablet.service` (system) | 开机设置麦克风采集路由 | enabled |
| `tablet-mic-volume.service` (user) | 麦克风源音量设 400% | enabled |

### 9.8 命令速查

```bash
tablet-audio speaker      # 切扬声器
tablet-audio headphone    # 切耳机
tablet-audio status       # 查看路由

# 手动录音测试（注意是 hw:0,1）
arecord -D hw:0,1 -f S16_LE -r 48000 -c 1 -d 3 /tmp/mic.wav
```

> **教训**：判断音频是否工作，必须用**足够长的音频**并在**播放中途**采样
> `pcm0p status` 和 DAPM。用 1 秒音频再 `sleep 3` 去查，只会得到误导性的 `closed`/`Off`。

### 9.9 扬声器无声：完整调查记录（结论：卡在板级信息）

这是本次改造中唯一**耗尽用户态手段仍未解决**的问题。完整证据链如下，按发现顺序。

#### 1. 声学回环测试：证明真的没声音

不依赖人耳的方法：播放白噪声 → 空气传播 → 麦克风录音 → 比较稳态 RMS。

```bash
sh tools/speaker_contrast.sh     # ratio > 3 = 有声音
sh tools/max_gain_test.sh        # 最严格版本
```

结果（麦克风 400% 增益，噪声底 rms=688，灵敏到能听见环境声）：

```
输出关闭 : rms=688.4
播放噪声 : rms=698.5
ratio = 1.01x            ← 无变化
```

四条路径全部测过：

| 路径 | ratio | 结果 |
|---|---|---|
| SPK（SPK DAC） | 0.95–0.98 | 无声 |
| EAR（EAR_S） | 0.94–0.97 | 无声 |
| HPH（HPHL/HPHR） | 1.00–1.06 | 无声 |
| 三条全开 | 1.00–1.02 | 无声 |

#### 2. 三个曾经误导我的假象

| 假象 | 真相 |
|---|---|
| 400% 增益 + 1kHz 正弦得 `ratio=2.14x` | 噪声底淹没信号；白噪声 + 稳态窗口得 **1.00** |
| EAR 路径 `peak=399`（基线 50） | **切换路径的咔哒声**，在 t=0–2s，不是音频 |
| `pcm status` 里 `delay=24960 avail=0` | ALSA 的 status 在 RUNNING 时**不报告**这些字段，我误判成"缓冲区不流动" |

**教训**：`DAPM 显示 On ≠ 有声音`。DAPM 只证明寄存器写成功。

#### 3. 端口扫描：只有 INT0 能点亮链路

```bash
sh tools/port_sweep.sh
```

```
INT0_MI2S_RX :  PDM_RX3=On  SPK_OUT=On    ← 唯一
INT1~INT6    :  全部 Off
DISPLAY_PORT :  Off
PRI_MI2S_RX  :  全部 Off
```

链路全程稳定（每 500ms 采样 12 次）：

```
t= 500ms  PDM_RX3=Off  SPK_OUT=Off   ← 启动
t=1000ms  PDM_RX3=On   SPK_OUT=On    ← 持续到结束
...
t=6000ms  PDM_RX3=On   SPK_OUT=On
```

#### 4. 排除的假设（每项都有实测）

| 假设 | 验证结果 |
|---|---|
| 走错端口（RX1/RX2） | 端口全扫，只有 INT0 有效 |
| 耳机检测卡住 | `HPHL/HPHR = ZERO`，强制关闭后 `SPK_OUT` 仍稳定 On |
| 需要独立 I2C 功放 | 板上没有（I2C 只有 `gt9110` 触屏 + `lp8556` 背光） |
| codec DT 节点空白 | **我一开始判断错了**，节点完整（14 个中断、jack 检测、micbias） |
| regulator dummy 是原因 | **不是**，麦克风能用说明 codec 已通电 |
| 采样格式问题 | 44.1k / 48k 都试过，同样无声 |

#### 5. Android 原厂配置给出的新方向

vendor 的 `mixer_paths.xml`：

```xml
<path name="deep-buffer-playback speaker">
    <ctl name="PRI_MI2S_RX Audio Mixer MultiMedia1" value="1" />
</path>
```

**整个扬声器路径只有这一条控制，完全不碰 SPK DAC / Digital RX3 / EAR_S。**

这说明喇叭接在 **PRIMARY MI2S** 总线，不经过 pm660 模拟功放。

#### 6. 为什么 DTB 补丁也没把握

内核的 `q6afe-dai` 支持这些 MI2S DAI：

```
PRI_MI2S_RX / PRI_MI2S_TX
SEC_MI2S_RX / TERT_MI2S_RX / QUAT_MI2S_RX / QUIN_MI2S_RX
INT0_MI2S_RX ... INT6_MI2S_RX
```

**短名 `PRI_MI2S_RX`**，上游头文件却叫 `PRIMARY_MI2S_RX = 1`。
DT 里 `INT0_MI2S_RX` 用的是 `0x89`（对上上游枚举 137），但 PRI 的短名说明
这个内核的枚举可能不同，**无法确证 `0x01` 对应 `PRI_MI2S_RX`**。

候选镜像已构建但**未刷入**：

```
/root/audio-dtb-work/boot-pri-mi2s.img   25,653,248 字节
  + pri-mi2s-dai-link { link-name = "Primary MI2S Playback";
                        cpu { sound-dai = <0x9b 0x01>; }; ... }
```

验证过：magic `ANDROID!` ✓、cmdline 保留 ✓、DTB 可反编译 ✓、
live 树与 in-boot 树结构一致（380 节点，0 差异）。

**但 DAI id 不确定 → 约 50% 概率无效，失败代价是平板不启动。**

#### 7. 真正的结论

```
数字链路 : 完整正确（PCM RUNNING / PDM_RX3 / SPK DAC / SPK PA / SPK_OUT 全 On）
模拟输出 : 无声
根因     : 需要板级原理图确认喇叭接在哪个 MI2S 引脚，或喇叭本身是否完好
```

**这是本机唯一无法通过 SSH 解决的问题。** 要往下走需要：
- 板级原理图（确认喇叭接线）
- 或拆机测喇叭阻抗
- 或 fastboot 环境 + 愿意承担刷坏风险

#### 8. 用户可以自己做的验证

```bash
# 插耳机听 —— 如果耳机有声，说明功放正常，只是喇叭没接/坏了
# 人耳贴近扬声器 —— 我的麦克风测试可能不如人耳灵敏
```

### 9.10 实测：改 DTB 加 pri-mi2s-dai-link 无效（2026-10-24）

这是本会话做过的最有风险、也最有价值的一次实验。**结论明确：这条路走不通。**

#### 做了什么

Android 原厂 `mixer_paths.xml` 显示扬声器走 `PRI_MI2S_RX`：

```xml
<path name="deep-buffer-playback speaker">
    <ctl name="PRI_MI2S_RX Audio Mixer MultiMedia1" value="1" />
</path>
```

而当前 DTB 的 `sound` 节点只有 4 条 dai-link（MultiMedia1/2 + INT0/INT3），
**没有 PRI_MI2S**。于是构建了一个补丁版 DTB：

```dts
pri-mi2s-dai-link {
    link-name = "Primary MI2S Playback";
    status = "okay";
    cpu      { sound-dai = <0x9b 0x01>; };          /* q6afedai, id 1 */
    platform { sound-dai = <0x9c>; };               /* q6routing */
    codec    { sound-dai = <0x9d 0x00 0x9e 0x00>; } /* analog + digital */
};
```

#### 构建与验证过程（全部通过）

```
1. 从 boot 分区 0xc344e6 提取原 DTB（62,468 字节，model "Xiaomi Mi Pad 4 Plus"）
2. dtc 反编译 → 加节点 → 重编译（62,664 字节，+196）
3. 确认 dtc 能字节级完美往返（round-trip BYTE-IDENTICAL）
4. 新 DTB 塞进 kernel payload（DTB 本来就在 kernel 末尾，直接追加）
5. mkbootimg-osm0sis 重打包，header 参数完全照抄原镜像
6. 校验：ANDROID! magic ✓ / cmdline 保留 ✓ / DTB 可反编译 ✓
7. diff 原版 vs 新版 DTS：**只多了一个 pri-mi2s-dai-link 块，其他 0 差异**
```

镜像：`boot-pri-mi2s.img`，25,653,248 字节
sha256 `6F4BAD0BBAC2C1CAA1D3DEB5BF6FC22453CC5552F2CD2B1AAE0B77DD7E2E59C3`

#### 刷入结果

```powershell
fastboot flash boot boot-pri-mi2s.img
fastboot reboot
```

**设备正常启动**（SSH 20 秒恢复，桌面完好）—— 说明镜像本身合法。

#### 但功能无效

```
✅ DTB 补丁确实进了运行中的设备树
   live fdt: 63429 bytes（原 63233，+196）
   dtc 反编译可见 "pri-mi2s-dai-link" 和 "Primary MI2S Playback"

❌ 但驱动没有为它创建 PCM
   PCM 设备仍只有 MultiMedia1 / MultiMedia2
   PRI widget 数 = 0
   asoc 组件列表无新增
```

#### 根因：机器驱动硬编码 dai_link 表

对 `snd-soc-sdm660-int.ko` 做 strings 分析：

```
✅ 驱动认识这些时钟名:
   pri_mi2s_clk_count
   int0_mi2s_clk_count
   int3_mi2s_clk_count
   pri_tdm_clk_count
   sec_tdm_clk_count

❌ 但完全搜不到:
   sound-dai
   link-name
   dai-link
```

**`add_dai_link` / `snd_soc_dai_link` 这些符号是 snd-soc-core 的通用 API，
不代表机器驱动会遍历 DT。**

结论：`snd-soc-sdm660-int` 用的是静态 `struct snd_soc_dai_link[]` 数组，
**probe 时不读 DT 的 `dai-link` 子节点**。所以加 DT 节点必然无效。

#### 下一步：必须改驱动源码

**要改的文件**（上游 pmOS / mainline）：
```
sound/soc/qcom/sdm660.c
sound/soc/qcom/common.c
sound/soc/qcom/sdm660-int.c
```
需在构建 VM 上确认实际文件名。

**两种改法**：

**A. 加一条静态 dai_link（简单，但硬编码）**
```c
{
    .name            = "Primary MI2S Playback",
    .stream_name     = "Primary MI2S Playback",
    .cpu_dai_name    = "PRI_MI2S_RX",     /* 注意：这个内核用短名 */
    .platform_name   = "q6routing",
    .codec_dai_name  = "msm8916_wcd_analog",
    .codec_name      = "800f000.spmi:pmic@3:audio-codec@f000",
    .dai_fmt         = SND_SOC_DAIFMT_CBS_CFS,
},
```

**B. 改成遍历 DT 的 dai-link（更通用，但要重写 probe）**
用 `snd_soc_of_parse_card_name` + `for_each_child_of_node(np, link)` 动态建链。

**关键不确定点**：q6afe 的 DAI 名在这个内核是**短名** `PRI_MI2S_RX`
（不是上游的 `PRIMARY_MI2S_RX`），DAI id 到底是不是 `1` 需要
在源码里对照 `q6afe-dai` 的 `q6afe_dai_data[]` 数组确认。

**验证方法**（改完后）：
```bash
# 1. 新 PCM 应该出现
cat /proc/asound/devices      # 期望多出 playback 设备

# 2. asoc 组件列表多一项
ls "/sys/kernel/debug/asoc/Xiaomi Mi Pad 4/"

# 3. 声学回环（黄金标准）
sh tools/speaker_contrast.sh  # ratio > 3 = 真出声
```

#### 这次实验的价值

**它不是白做的**：把"改 DTB 试试"这个猜测变成了**确定结论**。

| 之前的说法 | 现在的事实 |
|---|---|
| "补 PRI_MI2S dai-link 可能有用" | **已实测：无用** |
| "不确定 DAI id 对不对" | id 对不对都不重要，驱动根本不看 DT |

这样下一个会话可以直接从"改驱动源码"开始，不用再走一遍弯路。

#### 当前 boot 分区状态

**刷入的是补丁版 `boot-pri-mi2s.img`。** 它无害（设备正常、桌面正常、
音频行为和之前完全一样），只是多了一条被驱动忽略的 DTB 节点。

要恢复干净状态：
```powershell
fastboot flash boot pmos-boot2.img
fastboot reboot
```

### 9.11 麦克风是好的（对照实验）

同样条件下麦克风能清晰录到环境声：

```
400% 增益 : peak 3456~4544 (10~14% FS), rms≈700
频谱       : 200 Hz 有环境噪声峰
```

所以"无声"是**输出端**的问题，不是麦克风的。

---


## 10. 蓝牙键鼠（主机侧已就绪，待实际配对）

### 10.1 修复的两个真实问题

**问题 1：`hidp` 内核模块没加载**

```
hidp: not loaded     ← 经典蓝牙 HID 传输，BT3.0 键盘/鼠标必需
uhid: loaded         ← 已加载
```

没有 `hidp`，经典蓝牙键盘根本无法作为输入设备工作。

修复（持久化）：
```ini
# /etc/modules-load.d/tablet-bluetooth.conf
hidp
uhid
```

**问题 2：`Pairable: no`，怎么设都会退回去**

尝试 1 失败：把 `PairableTimeout=0` 放进 `[Policy]`
```
bluetoothd: Unknown key PairableTimeout for group Policy in /etc/bluetooth/main.conf
```
→ **键放错了组，被 BlueZ 忽略。**

尝试 2 失败：`if 'AlwaysPairable' not in s` 判断被**注释模板行**
`#AlwaysPairable = false` 误判，导致配置没写入。

最终正确做法：
```ini
[General]
DiscoverableTimeout=0
AlwaysPairable = true     ← 正确键在 [General]，不是 [Policy]
```

> `PairableTimeout` 在 BlueZ 5.87 里虽存在于字符串表，但**不属于 `[Policy]`**。
> 保持可配对要用 **`AlwaysPairable`**。

### 10.2 为什么不需要额外插件

`/usr/lib/bluetooth/plugins/` 是空目录，一度让我以为缺 HID 支持。实际上：
```
strings bluetoothd | grep profiles/input
  profiles/input/manager.c
  profiles/input/server.c
  profiles/input/device.c
  /etc/bluetooth/input.conf
```
**input 插件是编译进 `bluetoothd` 的**，不需要外部 `.so`。

### 10.3 配对助手

```bash
tablet-bt-pair                 # 扫描 30 秒并列出设备
tablet-bt-pair AA:BB:CC:DD:EE # 配对 + trust + connect
```

内部执行 `power on / agent on / default-agent / pairable on / pair / trust / connect`。

### 10.4 当前状态

```
Controller  02:00:29:4B:23:B3  (public)
Name        Xiaomi Mi Pad 4
Powered     yes
Discoverable yes        (DiscoverableTimeout=0)
Pairable    yes         (AlwaysPairable=true，30 秒后仍保持)
hidp/uhid   loaded 且开机自动加载
/dev/uhid   存在
agent       已注册（NoInputNoOutput，适合无需 PIN 的键鼠）
UUID        13 个
```

> **待做**：实际拿一个蓝牙键盘/鼠标配对验证。主机侧所有前提条件已满足。

---

## 11. 休眠 / 关屏（重要：找到"自动锁屏"的真凶）

### 11.1 "总是自动锁屏"的真正原因

之前我把 XFCE 的电量管理、GNOME 锁屏都关掉了，但屏幕**还是 10 分钟后自动黑**。
真凶在 **X 服务器层的 DPMS 定时器**：

```
$ xset q | grep -E 'Standby|Suspend|Off'
Standby: 600    Suspend: 600    Off: 600      ← 600 秒 = 10 分钟
```

**这两个层次是独立的**：
- `xfconf ... dpms-enabled=false` 只关掉 XFCE 的调用
- X 服务器自己的 DPMS 计时器仍在跑，到点就关屏

正确做法（已写入会话脚本）：
```bash
xset +dpms          # 保持扩展启用，这样 tablet-sleep 才能按需关屏
xset dpms 0 0 0     # 但三个超时全为 0 = 永不自动关屏
xset s off
xset s noblank
```

> **注意**：早先用 `xset -dpms` 直接禁用扩展，副作用是 `tablet-sleep`
> 无法再按需关屏。必须"扩展开启 + 超时为 0"。

### 11.2 为什么不能真正休眠

```
/var/log/mdss-suspend-bug.txt 记录的根因链：
  clk_branch_toggle -> clk_core_disable -> mdss_runtime_suspend [msm]
    -> mdss_pm_suspend -> device_suspend -> dpm_suspend -> pm_suspend
```
**关闭 MDSS 时钟会死锁**，表现为 42 次 `watchdog: CPU4: hard LOCKUP on cpu 5`。

而且这台设备：
```
/dev/watchdog       不存在
watchdog 内核模块    未加载
/sys/power/pm_test  不存在（CONFIG_PM_TEST_SUSPEND 未启用）
```
**没有硬件看门狗，一旦挂死只能长按电源键。**

`pm_test` 本来是最安全的验证方式（跑完设备挂起流程自动恢复、不真睡），
但内核没编译这个选项，所以**没有任何无风险的方式去测真休眠**。

### 11.3 已做的缓解（持久化）

`mdss-pm-pin.service`（system，enabled）：
```bash
# 把显示控制器固定为 runtime-active，绕开会死锁的时钟关闭路径
echo on > /sys/bus/platform/devices/*display-controller*/power/control
```

这是针对根因链的**直接缓解**，但不保证一定成功——从未验证过。

### 11.4 伪休眠（当前采用的方案）

```bash
tablet-sleep           # 关背光 + DPMS off，立即生效
tablet-sleep wake      # 恢复背光 + DPMS on
tablet-sleep status    # 查看状态
```

实测：
```
before: backlight=200
sleep : backlight=0    DPMS off
wake  : backlight=200  DPMS on
Xorg / xfwm4 全程存活，GPU faults 0
```

**优点**：零风险、瞬间唤醒、省电效果接近真休眠（背光和渲染都停了）
**缺点**：CPU 仍在跑（约 1-2 W），不能做到真休眠的 0.1 W 级别

### 11.5 如果想试真休眠

必须有物理访问权限（能按电源键）：

```bash
systemctl unmask sleep.target suspend.target
echo freeze > /sys/power/state        # s2idle，最浅
```

**如果 30 秒内无响应就是死锁了，长按电源键 10 秒硬重启。**
数据不会丢（都已落盘）。

---

## 12. 功耗实测（回答"电量够不够用"）

### 12.1 先纠正一个测量错误

我之前用 `/proc/stat` 算 CPU 占用时把 **idle 也加进了 busy**：

```sh
# 错的（$5 是 idle，所以永远是 100%）
awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8}'

# 对的（busy = user+nice+system+irq+softirq+steal）
awk '/^cpu /{print $2+$3+$4+$7+$8+$9}'
```

修正后的真实数据：

```
CPU 利用率: 0.4% of total capacity  (0.03 of 8 cores)
Xorg 静态时: 0.0% × 3 次采样
所有桌面进程: 0.0% of one core
```

**结论：横屏 + llvmpipe 在空闲时几乎不耗 CPU。** 之前"Xorg 21.8%"的数字是错的。

### 12.2 功耗平衡（含重要前提）

```
充电器输入 : 1437 mA @ 5.00 V = 7.18 W
电池充入   :  451 mA @ 4.20 V = 1.89 W
差额       : 5.29 W
```

**这个 5.29 W 不等于系统功耗**，它包含充电器转换损耗：

```
输入功率 = 电池功率 + 系统功耗 + 充电损耗
```

没有系统轨的分流电阻就无法拆分后两项。按典型线性充电器效率反推：

| 假设效率 | 损耗 | 推算系统功耗 |
|---|---|---|
| 85% | 1.07 W | ~2.44 W |
| 75% | 1.79 W | ~1.72 W |
| 65% | 2.51 W | ~1.01 W |

所以系统实际功耗大概 **1–2.5 W**，5.29 W 是上限而非实测值。

### 12.3 背光是最大的可控开销（实测）

保持充电输入恒定（1432–1437 mA），只改背光亮度：

| 背光 | 电池充入 | 相对 200 |
|---|---|---|
| 200/255 | 452 mA | 基准 |
| 100/255 | 719 mA | **+267 mA** |
| 40/255 | 854 mA | **+402 mA** |

**背光从 200 降到 40，省下约 402 mA × 4.2 V ≈ 1.7 W。** 这是实测差值，
不受充电损耗假设影响。

### 12.4 实际续航估算

电池设计容量 `8.62 Ah`，约 **36.7 Wh**（按 4.2 V）：

| 场景 | 功耗 | 续航 |
|---|---|---|
| 背光 40%，Wi-Fi 开 | 2.5 W | ~14.7 h |
| 背光 100%，Wi-Fi 开 | 3.5 W | ~10.5 h |
| 视频播放 | 4.0 W | ~9.2 h |
| 重度浏览 | 5.0 W | ~7.3 h |

**答案：够用。** 日常轻度使用 10 小时以上没问题。

### 12.5 已做的省电优化

**1. 默认背光 200 → 130**

写入会话脚本，开机生效。实测效果：
```
优化前: 电池充入 452 mA
优化后: 电池充入 630~693 mA   (+40~50%)
```

**2. 禁用平板用不到的手机应用**

这些是 `xfce4-session` 从 `/etc/xdg/autostart` 启动的（ppid 都是 xfce4-session）：

| 应用 | 内存 | 处理 |
|---|---|---|
| `gnome-calls` | 152 MB | 用 `Hidden=true` override 禁用 |
| `chatty` | 156 MB | 同上 |
| `evolution-alarm-notify` | 53 MB | 同上 |

override 写在 `~/.config/autostart/*.desktop`：
```ini
[Desktop Entry]
Type=Application
Exec=/bin/true
Hidden=true
X-GNOME-Autostart-enabled=false
```

重启桌面验证：三个进程都不再回来。

**3. 顺带修的"总是自动锁屏"**（见 §11.1）

X 服务器 DPMS 超时从 `600/600/600` 改成 `0/0/0`。

### 12.6 还能做什么

- 不用时关 Wi-Fi / 蓝牙（两者空闲也通电）
- 室内把背光降到 80–100
- 竖屏模式用 GPU 而非 llvmpipe，但**实测空闲功耗无差别**（CPU 本来就闲）

---

## 13. 字体清晰度的实测验证（三层 DPI 必须一致）

### 13.1 三层 DPI 是独立的

| 层 | 命令 | 影响 |
|---|---|---|
| X 服务器 | `xdpyinfo` / `xrandr --dpi` | 提供物理尺寸元数据 |
| xfconf | `xfconf-query -c xsettings -p /Xft/DPI` | **决定文字实际渲染大小** |
| xrdb | `xrdb -query` | 应用启动时读取 |

**`Xft/DPI` 才真正决定字形像素大小**；X 服务器的 DPI 只是给询问者的元数据。

### 13.2 一个真实的不一致，以及它的原因

Xorg 明明用 `-dpi 150` 启动，`xdpyinfo` 却报 96：

```
$ ps -o args= -p $(pgrep -x Xorg)
/usr/libexec/Xorg :0 -keeptty -dpi 150 -nolisten tcp

$ xdpyinfo | grep resolution
resolution:    96x96 dots per inch
```

**原因**：面板 EDID 谎报物理尺寸为 `509x318 mm`，X 相信 EDID 而不是 `-dpi`：

```
1920 px / 509 mm × 25.4 = 95.8 → 96
真实面板      : 135 × 216 mm（DRM 报告）
```

**修复**：`xrandr --dpi 150`（只改元数据，**不触发 modeset**，与旋转挂死无关）：

```
修复前: 1920x1200 (509x318 millimeters)  96x96 dpi
修复后: 1920x1200 (325x203 millimeters) 150x150 dpi
```

实测安全：GPU faults 0、X 正常响应、D-state 0。

### 13.3 开机后 DPI 会被重置（和触控矩阵同一个坑）

`xrandr --dpi 150` 写在会话脚本第 90 行（早于 `exec startxfce4`），但**开机后仍是 96**。
原因：`xfsettingsd`（由 xfce4-session 启动）重置了服务器 DPI。

**和触控矩阵完全相同的失败模式，用相同的方法解决**——放进延迟重应用循环：

```sh
for delay in 5 10 20 35; do
    sleep "$delay"
    xinput set-prop "$TID" "Coordinate Transformation Matrix" $M
    xrandr --dpi 150
done &
```

重启后日志：
```
[04:02:04] delayed-reapply +5s  dpi=150x150
[04:02:15] delayed-reapply +10s dpi=150x150
[04:02:36] delayed-reapply +20s dpi=150x150
[04:02:53] delayed-reapply +35s dpi=150x150
```

### 13.4 视觉验收

不是只看设置，而是实际渲染中文并截图确认：

**Thunar 真实界面**（截图 `tools/thunar_text.png`）：
- 菜单「属性」「名称」「修改日期」锐利
- 中文与数字混排（「1.6 GB 可用」）正常
- 侧栏「下载」「文档」「图片」「音乐」「公共的」「模板」「视频」「桌面」全部清晰

**12pt / 20pt 对比**（截图 `tools/font_test.png`）：
- 中文与拉丁字母在两种字号下都清晰
- 抗锯齿 + hintslight 让边缘平滑，无锯齿感

### 13.5 字号换算（150 dpi）

| pt | 像素 |
|---|---|
| 8 | 16.7 |
| 10 | 20.8 |
| **12** | **25.0** ← 当前 |
| 14 | 29.2 |
| 20 | 41.7 |

面板原生约 224 dpi。DPI 150 相当于 **0.67× 原生**，即 1.49× 缩放，
在 10.1 寸 1920×1200 上是比较舒服的阅读尺寸。

### 13.6 字体与渲染设置（最终）

```
Noto Sans CJK SC 12pt    (中文字体，30 个 CJK 字体文件)
Xft/DPI          150
Xft/Antialias    1
Xft/Hinting      1
Xft/HintStyle    hintslight
Xft/RGBA         rgb          (子像素抗锯齿)
Xft/Lcdfilter    lcddefault
X cursor size    36
```

---

## 14. 踩坑速查（本轮新增）

| 现象 | 根因 | 处理 |
|---|---|---|
| `Only console users are allowed to run X` | Xorg.wrap 校验 logind 活动会话 | `/etc/X11/Xwrapper.config` → `allowed_users=anybody` |
| XFCE 启动脚本日志为空、立即失败 | 以用户身份写 `/var/log` 被拒，`>>` 失败导致脚本退出 | 日志改到 `~/.local/share/tablet-session/` |
| `Another desktop manager is running` | 检查太早，xfdesktop 还没起 | 等 20 秒再查 |
| 面板“插件加载失败”弹窗 | 配置引用不存在的 `notification-plugin` | 重写 `xfce4-panel.xml` |
| 面板只有 26px、字小得没法点 | 默认布局是低 DPI 桌面用的 | 面板 56px、图标 32px |
| DPI 设了 144 但读到 96 | 只写 xrdb，xfconf 仍是空 | 必须写 `xfconf /Xft/DPI` |
| 触控点哪都错位 | 旋转矩阵没跟着 fb 方向改 | 竖屏用单位阵 |
| `pgrep` 说有进程但实际是死的 | 僵尸进程保留进程名 | 读 `/proc/PID/stat` 第 3 字段排除 `Z` |
| 浏览器连不上 VNC | pmOS nftables `policy drop` | 加 drop-in 放行 6080 |
| x11vnc 报 Wayland 就退出 | `WAYLAND_DISPLAY` 存在 | `env -u WAYLAND_DISPLAY` |
| **屏幕黑但 VNC 有画面** | **GPU 挂死，CRTC 提交不了新帧** | **物理重启**（见 §3） |

---

## 15. 命令速查

```bash
# 看桌面是否正常
DISPLAY=:0 wmctrl -m
DISPLAY=:0 xrandr --current
xfconf-query -c xsettings -p /Xft/DPI

# 回退到 Phosh（一键）
/usr/local/bin/restore-phosh

# 强制用 Phosh（重启前设置）
touch /etc/tablet/force-phosh && systemctl restart greetd
rm -f /etc/tablet/force-phosh

# 重启会话（不重启系统）
systemctl restart greetd

# VNC
systemctl --user status x11vnc novnc
pkill -x x11vnc; pkill -f websockify     # 临时停

# 日志
tail -f ~/.local/share/tablet-session/launcher.log
tail -f ~/.local/share/tablet-session/xfce-x-session.log
tail -f ~/.local/share/tablet-session/session.log

# 带旋转启动（仅在你确认安全后）
#   编辑 xfce-tablet-session 前先想清楚 §3 的教训
```

---

## 16. 待办 / 下一步

按优先级（2026-10-24 02:00 更新）：

| 优先级 | 项 | 状态 |
|---|---|---|
| ~~P0~~ | ~~横屏方案~~ | ✅ **已完成**（软件加速，`tablet-display-mode`） |
| ~~P1~~ | ~~触屏中文输入~~ | ✅ **已完成**（fcitx5 + onboard，16 项验收通过） |
| **P0** | 音频扬声器 | 声卡/DSP/播放通路都正常，但 UCM **没有 Speaker section**。需人耳确认 + 写 UCM |
| **P1** | 蓝牙键鼠配对 | 控制器正常（HCI 5.0、`Pairable: yes`、能扫到设备），需实际配对 |
| P2 | 休眠唤醒 | **被 mask**（`mdss_runtime_suspend` 硬挂死，见 §3）。需上游内核修复 |
| P2 | 清理 Evolution 残留 | `evolution-alarm` / `evolution-source-registry` 等仍占 ~120MB |
| P3 | 竖屏模式面板重排 | 竖屏时面板应改到侧边 |

> **注意**：本机音频后端是 **PulseAudio**（`postmarketos-base-ui-audio-backend-pulseaudio`），
> 不是 PipeWire。`pipewire-pulse` 与该包冲突，装不上 —— 别再试这条路。

---

## 17. 电池显示与响应速度（2026-10-24 新增）

### 17.1 电池指示器（面板右下角 `⚡ 99%`）

#### 为什么一开始没有

排查出**四层**问题，逐层都是真 bug：

**第 1 层：`xfce4-power-manager` 启动即崩**

两个 xfconf 值是非法值：
```
brightness-on-ac       = 0     ← 属性拒绝 0
brightness-on-battery  = 0
```
`GLib-GObject-CRITICAL: value "0" of type 'guint' is invalid ... for property 'brightness-on-ac'`

改成 50 后进程能启动。

**第 2 层：`upower.service` 是 disabled**

```bash
systemctl enable --now upower
```
之前靠 socket activation 偶然运行，重启后可能没有。

**第 3 层：面板插件的模块名写错**

```
X-XFCE-Module=xfce4powermanager     ← 正确值
我一开始写的       power-manager    ← 错
```
写错导致面板显示「插件加载失败」窗口。

**第 4 层（真凶）：glycin 图片解码器崩溃**

```
(xfce4-panel): Gtk-WARNING: Could not load a pixbuf from icon theme.
glycin_core::dbus: Process exited: ... Ok(ExitStatus(unix_wait_status(15)))
```

`unix_wait_status(15)` = **被 SIGTERM 杀死**。

glycin 是沙箱化的图片解码器，通过 D-Bus 启动独立进程解码每张图标。
这些辅助进程在这台 musl/Alpine 设备上被杀死，**连带把面板进程一起带走**。

这解释了为什么：
- 面板反复消失
- 电池插件显示「插件加载失败」
- 每次都有 pixbuf 警告

**修复**：
```bash
export GDK_PIXBUF_USE_GLYCIN=0
```
让 gdk-pixbuf 在**进程内**解码。已验证面板从此稳定（40 秒不掉，RSS 平稳 43MB）。

> **重要**：`gdk-pixbuf` 本身已链接 `libpng16`，PNG/SVG 都能内置解码，
> 不需要 glycin。

#### 最终采用 genmon 方案

内置的 `libxfce4powermanager` 和 `xfce4-battery-plugin` 都依赖 D-Bus/守护进程，
在这台设备上不稳定。改用 **`xfce4-genmon-plugin`**：

```
面板插件 = genmon
执行脚本 = /usr/local/bin/tablet-battery-status
```

脚本直接读 `/sys/class/power_supply`，**无守护进程、无 D-Bus，不可能挂死**：

```sh
B=/sys/class/power_supply/qcom-battery
C=/sys/class/power_supply/pm660-charger
cap=$(cat $B/capacity)        # 99
status=$(cat $B/status)       # Charging
cur=$(cat $B/current_now)     # uA
```

输出 genmon XML：
```xml
<txt>⚡ 99%</txt>
<tool>电池 99% · Charging
充电器已连接
电流 +157 mA · 电压 4.40 V
温度 28.5 °C</tool>
<bar>99%</bar>
```

图标含义：
| 图标 | 含义 |
|---|---|
| ⚡ | 正在充电 |
| 🔋 | 使用电池 |
| 🔌 | 已插充电器但未充电（如涓流/满电保护）|
| ✔ | 已充满 |

刷新周期 5 秒。

### 17.2 面板自愈（systemd 用户服务）

即使图标解码修好了，面板仍偶发退出。**与其追最后一个崩溃，不如让它自愈**：

`~/.config/systemd/user/xfce4-panel.service`：
```ini
[Service]
Type=simple
Environment=DISPLAY=:0
Environment=GDK_PIXBUF_USE_GLYCIN=0
ExecStart=/usr/bin/xfce4-panel --disable-wm-check
Restart=always
RestartSec=2
```

实测：`kill -9` 后 **4 秒内自动重启**，用户看不到面板消失。

### 17.3 响应速度优化

**关闭窗口合成器**（软件渲染下每帧都耗 CPU）：

```bash
xfconf-query -c xfwm4 -p /general/use_compositing -s false
xfconf-query -c xfwm4 -p /general/show_frame_shadow -s false
xfconf-query -c xfwm4 -p /general/show_popup_shadow -s false
xfconf-query -c xfwm4 -p /general/show_dock_shadow -s false
```

**禁用平板用不到的 GNOME/手机服务**：

| 服务 | 内存 | 说明 |
|---|---|---|
| `tumblerd` | 130 MB | 缩略图生成，桌面无用 |
| `goa-daemon` | 67 MB | GNOME 在线账户 |
| `wireplumber` | 59 MB | PipeWire 会话管理，**我们用 PulseAudio** |
| `gsd-*` | 若干 | GNOME 设置守护进程，XFCE 有自己的 |
| `localsearch-3` | 21 MB | GNOME 文件索引 |
| `mmsdtng` | 17 MB | MMS 短信守护 |
| `geoclue` | 7 MB | 定位示例 agent |
| `phosh-tour` | - | Phosh 引导，已无意义 |

用 `~/.config/autostart/*.desktop` 的 `Hidden=true` 覆盖禁用。

**实测结果**：
```
CPU busy: 0.3% of total capacity
所有桌面进程瞬时占用 0.0%
面板 RSS 稳定 43 MB
```

### 17.4 验证数据（重启后）

```
面板        pid 2759，运行 59 秒+
电池插件    genmon → /usr/local/bin/tablet-battery-status
电池读数    🔌 98% · Not charging（如实反映）
合成器      use_compositing = false
CPU         0.3% of total capacity
内存        1.3G / 3.5G
```

> 注意 `🔌 98% Not charging` 是正确的：电池接近满电时充电器会暂停，
> 指示器如实显示，没有撒谎。

### 17.5 相关文件

| 文件 | 作用 |
|---|---|
| `/usr/local/bin/tablet-battery-status` | 电池读数 → genmon XML |
| `~/.config/systemd/user/xfce4-panel.service` | 面板自愈 |
| `~/.config/systemd/user/xfce4-power-manager.service` | 电源管理守护（可选，已被 genmon 取代）|
| `~/.config/xfce4/panel/genmon-10.rc` | 插件配置 |

### 17.6 命令速查

```bash
# 看电池状态（原始值）
/usr/local/bin/tablet-battery-status

# 用 upower 看更详细
upower -i $(upower -e | grep -i bat | head -1)

# 面板自愈服务
systemctl --user status xfce4-panel
systemctl --user restart xfce4-panel

# 如果面板又消失，手动起一次
GDK_PIXBUF_USE_GLYCIN=0 setsid xfce4-panel </dev/null &
```

### 17.7 踩过的坑

| 坑 | 真相 |
|---|---|
| `brightness-on-ac=0` | 属性不接受 0，导致 power-manager 崩溃 |
| 插件模块名 `power-manager` | 正确值是 `xfce4powermanager` |
| 「插件加载失败」窗口 | 多半是图标解码崩溃的副作用 |
| 面板反复消失 | glycin 辅助进程被 SIGTERM，连带杀死面板 |
| `xfce4-panel -r` 反复重载 | 会把 xfconf 配置搞乱，别用 |
| root 下 `systemctl --user` | 报 `Failed to connect to user scope bus`，必须 `sudo -u user env XDG_RUNTIME_DIR=...` |
| SSH 里 `xfce4-panel &` | 会继承管道导致 SSH 挂起，必须 `setsid ... </dev/null` |

---

## 18. 回退机制（三层，按严重程度）

### 18.1 关键事实：本次改造全部是用户态

**没有写过任何分区，没有改过 boot 镜像。** 验证：

```bash
$ ls -1 /boot/ | wc -l
0
$ cat /proc/cmdline
quiet splash ... pmos_boot_uuid=d563e6a5-...
```

所以恢复**完全不需要刷机**，改文件就行。这是最重要的性质。

### 18.2 三层回退

| 层 | 手段 | 影响范围 | 代价 |
|---|---|---|---|
| **A** | `tablet-restore-snapshot <dir>` | 只回退本次会话的配置 | 秒级，无损失 |
| **B** | `/usr/local/bin/restore-phosh` | 换回 Phosh 会话，保留所有软件包 | 秒级 |
| **C** | 刷 `pmos-boot2.img` + `pmos-rootfs3.img` | 回到 10-19 状态 | **丢失 10-19 之后的一切** |

### 18.3 为什么需要 A 层（旧镜像不够用）

```
pmos-boot2.img   2026-10-19 19:59
pmos-rootfs3.img 2026-10-19 21:23
```

这两个镜像**早于本次会话全部工作**，回退会丢失：

- 原生 Xorg + XFCE 桌面
- 横屏 llvmpipe 方案
- 音频（扬声器 RX3 + 麦克风 400%）
- fcitx5 + onboard
- DPMS 0/0/0 修复
- 背光 130 + 手机应用禁用
- xrandr --dpi 150

所以真正有用的"已知良好状态"是**当前配置的快照**，不是那两个旧镜像。

### 18.4 快照内容（26 个文件）

```
/root/tablet-good-state-YYYYmmdd-HHMM/
├── usr-local-bin/          9 个脚本
│   ├── xfce-tablet-session      会话主脚本（旋转/DPI/触控/输入法）
│   ├── xfce-x-session           启动 Xorg :0
│   ├── tablet-session-launcher  90s 看门狗
│   ├── tablet-display-mode      竖/横切换
│   ├── tablet-audio             扬声器/耳机切换
│   ├── tablet-sleep             伪休眠
│   ├── tablet-bt-pair           蓝牙配对助手
│   ├── restore-phosh            回退到 Phosh
│   └── start-x11vnc             VNC 启动
├── systemd-system/         3 个 system 单元
│   ├── alsa-restore-tablet.service
│   ├── alsa-mic-tablet.service
│   └── mdss-pm-pin.service
├── systemd-user/           5 个 user 单元
│   ├── fcitx5.service / onboard.service
│   ├── tablet-mic-volume.service
│   └── x11vnc.service / novnc.service
├── xorg/                   X 配置
│   ├── Xwrapper.config
│   └── xorg.conf.d/50-msm-soft.conf
├── bluetooth/              main.conf / input.conf / modules-load
├── state/                  landscape 标志 + asound.state
└── user-config/            xfce4-panel.xml
```

### 18.5 使用

```bash
# 看有哪些快照
tablet-restore-snapshot

# 恢复
tablet-restore-snapshot /root/tablet-good-state-20261024-0408
systemctl restart greetd
```

验证过可解压、26 个文件齐全：

```
$ tar tzf tablet-good-state.tar.gz | wc -l
35
$ sha256sum tablet-good-state.tar.gz
97d6a2a26a74dead1def41e3473c3d5a4514fa7c77cd0d77a50aa596e7039133
```

**双重备份**：设备 `/root/` + 本地 `tools/tablet-good-state.tar.gz`。

### 18.6 三层安全网（防桌面起不来）

| 机制 | 作用 |
|---|---|
| `tablet-session-launcher` 90 秒看门狗 | 桌面起不来自动回 Phosh |
| `/etc/tablet/force-phosh` 标志 | 手动强制 Phosh |
| `getty@tty1/2/3` 已启用 | 屏幕上的救援控制台 |

验证：
```
getty@tty1  enabled
getty@tty2  enabled
getty@tty3  enabled
```

### 18.7 建议

**每次大改前先做快照**：

```bash
sudo sh -c 'S=/root/tablet-good-state-$(date +%Y%m%d-%H%M); mkdir -p $S; ...'
```

或者直接重跑 `tools/snapshot_state.sh`。

---



**这套改动没有动 boot/rootfs 镜像**，全部是用户态配置，所以回滚很简单：

```bash
# 1. 回到 Phosh（保留所有已装的包）
/usr/local/bin/restore-phosh

# 2. 如果要连镜像一起回到 10-19 的状态（会丢失这些改动）
#    tools/pmos-boot2.img + tools/pmos-rootfs3.img
#    fastboot flash boot     tools/pmos-boot2.img
#    fastboot flash userdata tools/pmos-rootfs3.img
```

已装的软件包可以按需卸载：
```bash
sudo apk del xfce4 xfce4-terminal thunar mousepad dbus-x11 polkit \
             xorg-server xinit xf86-input-libinput xterm xrandr xinput \
             fcitx5 fcitx5-chinese-addons fcitx5-gtk fcitx5-qt onboard \
             x11vnc novnc websockify
```
