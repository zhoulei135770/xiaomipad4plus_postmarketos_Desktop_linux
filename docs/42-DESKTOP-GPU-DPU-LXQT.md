# 42 — 桌面、GPU 与 DPU 卡死：今天的整套诊断

- 日期：2026-10-29
- 结论：桌面卡死（只有鼠标能动）是 **DPU 丢 vblank**；GPU 硬件可用但不适合给 X 做合成；
  已迁移到 LXQt（内存更低）。

---

## 1. "只有鼠标能动"的真正原因

现象：桌面冻结、鼠标还能移动、SSH 正常。

内核日志：

```
[drm:dpu_encoder_phys_vid_wait_for_commit_done:543] [dpu error]vblank timeout: 1000000
[drm:dpu_kms_wait_for_commit_done:525] [dpu error]wait for commit done returned -110
```

**DPU（显示控制器）收不到垂直同步中断**，画面停止刷新。

鼠标能动是因为光标走 DPU 的硬件光标层，不需要翻页 —— 这解释了"只有鼠标能动"。

### 1.1 触发条件（A/B 结论）

| 配置 | DPU vblank 超时 | 桌面可用 |
|---|---|---|
| glamor（GPU 合成）+ 588 MHz | 是，且伴随 `gpu fault` | 会冻结 |
| glamor + 370 MHz | 是 | 偶尔冻结 |
| 软件渲染（llvmpipe），GPU 固件缺失 | 启动时 4 次，之后无 | **稳定** |
| 软件渲染，GPU 固件存在 | 启动时 4 次，之后无 | **稳定** |

结论：
- 启动后 ~80 秒的 4 次 vblank 超时是**初始化抖动**，可恢复，不是卡死原因
- 真正的冻结与 **glamor** 强相关（GPU 侧翻页偶尔完不成 → X 一直等）
- 与 GPU 是否初始化无关（把 ZAP 固件移走后 DPU 照样报那 4 次）

### 1.2 处置

`/etc/X11/xorg.conf.d/20-gpu.conf` 停用（改名为 `.conf.disabled`），
X 回到 llvmpipe。GPU 驱动与 370 MHz 限频保留。

---

## 2. GPU 现在的状态：硬件可用，但不给 X 用

```
X 的 GLX:   llvmpipe (LLVM 23.1.3)      Accelerated: no      ← 稳定优先
EGL/DRM:    OpenGL core profile renderer: FD512                 ← 硬件可用
devfreq:    max_freq=370000000  cur=19200000
gpu fault:  0
```

也就是说：**应用可以通过 EGL/DRI 用到真正的 Adreno FD512**，
只是 X 的 2D 合成走软件渲染。

### 2.1 为什么锁 370 MHz

588 MHz 会触发：

```
[drm:a5xx_irq] gpu fault ring 0 fence ffffff00 status 800001C1
[drm:adreno_idle] timeout waiting to drain ringbuffer 0 rptr/wptr = 23/C
hangcheck recover!
```

根因是 GPU 的 `vdd` / `vddcx` 是 dummy regulator（没有真正调压），
高频下电压不足。370 MHz 是当前供电条件下实测稳定的最高档。

可用档位：`19200000 160000000 266000000 370000000 465000000 588000000`

### 2.2 启动时那两行错误可以忽略

```
adreno 5000000.gpu: [drm:adreno_zap_shader_load] *ERROR* Unable to load a512_zap.mdt
msm_dpu c901000.display-controller: [drm:adreno_load_gpu] *ERROR* gpu hw init failed: -2
```

GPU 在 initramfs 阶段就 probe，那时 `/lib/firmware` 还没挂载；
X 起来时重试成功（FD512 可用即为证据）。

---

## 3. 桌面迁移：XFCE → LXQt

### 3.1 为什么换

用户要求"内存低又好看"。实测：

| 桌面 | 已用内存 | 说明 |
|---|---|---|
| XFCE | ~1100 MB | 原来那套 |
| **LXQt 2.4** | **~940 MB** | 省约 170 MB |

Deepin DDE / 麒麟 UKUI 在 Alpine 仓库里**没有包**，只能从源码移植，不现实。

### 3.2 装了什么

```
lxqt-desktop lxqt-session lxqt-panel lxqt-qtplugin lxqt-themes
lxqt-config lxqt-runner lxqt-powermanagement lxqt-globalkeys
lxqt-notificationd lxqt-about lxqt-admin lxqt-archiver lxqt-menu-data
pcmanfm-qt qterminal openbox breeze-icons kvantum xf86-input-libinput
```

（`apk add` 实测 13 秒，镜像很快，不需要代理。）

### 3.3 会话架构

```
greetd
 └─ /usr/local/bin/tablet-session-launcher      读写 /etc/tablet/desktop
     ├─ "lxqt" → /usr/local/bin/lxqt-x-session  → dbus-run-session -- startlxqt
     └─ "xfce" → /usr/local/bin/xfce-x-session  → dbus-run-session -- xfce-tablet-session
```

自动回退：LXQt 45 秒内没有 `lxqt-panel`/`openbox` 就杀掉并切 XFCE；
XFCE 也起不来就交给 Phosh。这条链路实测生效过。

切回 XFCE：

```sh
echo xfce | sudo tee /etc/tablet/desktop
```

### 3.4 踩过的三个坑

**坑 1：`startlxqt` 在 `/usr/sbin`，不在普通用户 PATH 里**

现象：会话 5 秒退出。
修复：会话脚本里用绝对路径 `/usr/sbin/startlxqt`，并把 sbin 加进 PATH。

**坑 2：Qt 选了 wayland 平台插件**

```
Failed to create wl_display (No such file or directory)
qt.qpa.plugin: Could not load the Qt platform plugin "wayland"
This application failed to start because no Qt platform plugin could be initialized
```

greetd 导出的环境让 Qt 以为在 Wayland 下。修复：

```sh
export QT_QPA_PLATFORM=xcb
export GDK_BACKEND=x11
export XDG_SESSION_TYPE=x11
```

**坑 3：屏幕是竖屏（1200×1920）**

面板原生是竖的，XFCE 那边有旋转设置，LXQt 没有。修复：会话里加

```sh
xrandr --output DSI-1 --rotate right
```

### 3.5 仍然待办（美化）

- 壁纸是黑的（`pcmanfm-qt --set-wallpaper` 钩子没生效）
- 桌面部分图标缺失（只有"计算机"有图标）
- 面板主菜单按钮疑似因图标主题不完整而"隐形"

这三项都属于美化，等用户回来再处理。

---

## 4. 教训

1. **不要在 SSH 里 kill/重启桌面进程**（`xfdesktop`/`xfce4-panel`）。
   它们不在会话管理器下，重启后与 X 的连接状态不对，会把显示拖死。
   要改就改配置文件然后重启整机。

2. **刷写与重启要用脚本文件 + systemd-run**。
   PowerShell 会吃掉 `$( )` 和引号，内联命令多次被截断，甚至导致刷写半途中断。

3. **`systemctl reboot` 有时不生效**（返回成功但机器没重启）。
   可靠做法是写入脚本文件后 `exec reboot -f`。

---

## 5. glamor 复测与一次自伤事故（2026-10-29 15:30）

### 5.1 有效的部分

在 370 MHz、`Present=false`（关闭翻页等待）下重新启用 glamor：

```
Device: FD512   Accelerated: yes   OpenGL 3.1 Mesa 26.2.5
glxgears 连续 60 秒：约 800 FPS（不限速）
gpu fault = 0    dpu vblank timeout = 0    hangcheck = 0
桌面进程全部存活，内存 984 MB
```

**结论：`Present=false` 确实是关键**。之前的 DPU vblank 超时来自 X 等待翻页完成，
关掉 Present 后不再走那条路径。

### 5.2 事故：把机器跑死了

为了验证长时间稳定性，我写了一个循环脚本，用 `vblank_mode=0` 的 `glxgears`
反复压 40 轮，每轮还启一个 `pcmanfm-qt`。

问题：**`vblank_mode=0` 会让 GL 客户端按 CPU 能力全速渲染**，没有任何帧率上限。
`glxgears` 于是把 4 个核占满，`pcmanfm-qt` 又不断启停，最终**用户态被彻底饿死**：

```
ICMP：偶尔回包，延迟 1329 ms   （内核还活着）
TCP 22：能握手，但 sshd 15 秒发不出 banner
一次探测返回 "Not allowed at this time"（MaxStartups 限流，说明它短暂调度过）
```

状态持续 20 分钟以上，远程无法恢复，**只能强制重启**。

注意：这**不是 GPU 挂死**。GPU 挂死的特征是"显示冻结但 SSH 正常"（今天出现过两次）；
这次是反过来 —— 内核在、用户态不调度。

### 5.3 后续修正

1. 会话里**去掉全局 `vblank_mode=0`**（它会让任何 GL 程序变成 CPU 烤机）
2. 保留 glamor + DRI3 + `Present=false`（这才是修 vblank 的部分）
3. 以后测 GL 性能必须有帧率上限（如 `vkcube --c 100`、或带 `-s` 的限速），
   不要用 `vblank_mode=0` 跑循环

脚本：`scripts/pad_post_reboot_fix.sh`（重启后执行，自动清理并去掉那两行 export）

### 5.4 状态判定速查

| 现象 | 含义 | 处置 |
|---|---|---|
| 屏幕冻结、鼠标能动、SSH 正常 | DPU 丢 vblank | SSH 改配置 + 重启 |
| 屏幕正常、SSH 无响应、ICMP 正常 | 用户态被饿死/挂死 | **只能强制重启** |
| 两者都无响应 | 内核挂死 | 强制重启 |

---

## 6. sshd 把自己锁死（2026-10-29 16:00）

### 6.1 现象

用户态被饿死那段时间里，我为确认状态反复尝试 SSH，累计几十次连接。
系统恢复后（ping 回到 1 ms），SSH 依然连不上：

| 来源 | 结果 |
|---|---|
| 我的 PC（192.168.1.x） | `Not allowed at this time\r\n` —— sshd 明确拒绝 |
| VM（另一个 IP） | `kex_exchange_identification: read: Connection reset by peer` |

`Not allowed at this time` 是 **OpenSSH 9.8+ 的 PerSourcePenalties**：
短时间内过多失败/异常连接，会把源 IP 拉黑一段时间（默认最长约 10 分钟）。
VM 之所以被 reset，是因为 sshd 的全局 `/MaxStartups` 也已经饱和
（默认从第 10 个未认证连接起按比例丢弃，第 100 个全丢）。

### 6.2 结论

**平板本身没问题**（ICMP 1–2 ms、桌面正常运行），只是 sshd 的防护机制把远程通道关掉了。
这种情况远程无法自救，只能：

1. 等惩罚期过去（10 分钟以上，期间**一次都不要连**）
2. 或者本地重启一次

### 6.3 以后的操作规范

1. **探测失败后不要连发重试**。每次尝试之间至少 60 秒，连续 3 次失败就停下来报告。
2. 优先用**幂等的一条命令**确认状态（如单次 `uptime`），不要写轮询循环。
3. 需要长时间观察时，把轮询放到**平板本地**的脚本里（systemd-run 后台），
   然后用一次连接去读日志，而不是从外面反复连。
4. 用户的 PC 和 VM 是两个不同源 IP，可以互为备份，
   但**不要同时对同一台机器发连接**，那会更快触发全局 MaxStartups。

### 6.4 恢复清单（重启后按顺序做）

```sh
# 1. 清掉压测残留
sudo pkill -x glxgears
sudo systemctl reset-failed soakA1 gpusoak 2>/dev/null

# 2. 去掉把 GL 变烤机的全局设置
sudo sh /path/to/pad_post_reboot_fix.sh

# 3. 确认桌面与 GPU
pgrep -x lxqt-panel && glxinfo -B | grep -E 'Device|Accelerated'
dmesg | grep -c 'gpu fault'

# 4. 只有在需要时才压测，且必须限帧
#    ✗ vblank_mode=0 glxgears -info        （无限速，会饿死系统）
#    ✓ vkcube --c 300                       （跑固定帧数就退出）
```

---

## 7. 黑屏的真正根因：DPU 主图层旋转失效（2026-10-29 18:30）

### 7.1 现象

- 物理屏幕：全黑，只有鼠标光标能移动
- X 截图：**完整桌面**（壁纸、图标、面板全在）
- 内核日志：**没有任何 `gpu fault` 或 `vblank timeout`**
- DSI 状态：`connected` / `enabled` / DPMS `On`，背光 255

### 7.2 关键推理

光标能动、别的不动 —— 说明 **DPU 的光标层在扫描输出，主图层没有**。
X 确实把画面画进缓冲区（截图为证），但主 plane 的内容上不了屏。

### 7.3 逐项排除

| 尝试 | 结果 |
|---|---|
| 强制 modeset（`xrandr --off` + `--auto`） | 无效 |
| 切 VT（`chvt 1` → `chvt 7`） | 无效 |
| 冷启动（彻底断电） | 无效 |
| **`xrandr --output DSI-1 --rotate normal`** | **✅ 立刻恢复** |

**根因：主图层的硬件旋转（`--rotate right`）在本机不工作。**

### 7.4 可用的旋转组合

| 组合 | 扫描输出 | 方向 |
|---|---|---|
| `--rotate normal`（1200×1920） | ✅ | 竖屏 |
| `--rotate right` | ❌ **黑屏只剩光标** | — |
| `--rotate left` | ✅ | 横屏但**上下颠倒** |
| **`--rotate left --reflect xy`** | ✅ | **横屏，方向正确** |

`left` + `xy` 双向反射在数学上等价于 `right`，但驱动走的是反射路径而不是
那条坏掉的旋转路径，所以能正常工作。

### 7.5 已固化

`/usr/local/bin/lxqt-x-session` 与 `/usr/local/bin/xfce-x-session` 里都改成：

```sh
xrandr --output DSI-1 --rotate left --reflect xy 2>/dev/null || true
```

备份：`*.bak-rot`

### 7.6 今天的连环误判记录

1. 先以为 GPU 故障 → 实测 0 fault
2. 再以为 `Present=false` 修好了卡死 → 实际是 X 从此不翻页，屏幕永远停在初始黑帧
3. 把"压测 60 秒零错误"当证据 → 画面根本没上屏，当然没有翻页超时
4. 最后才用"X 截图 vs 物理屏幕"对比定位到旋转

**教训：显示问题必须对比 X 截图和物理屏幕，不能只看内核日志。**



