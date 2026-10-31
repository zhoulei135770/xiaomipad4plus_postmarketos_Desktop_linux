# 10 · 自动旋转 + 合盖休眠（首个真正可用的传感器功能）

> 创建：2026-10-24 10:10（Asia/Shanghai）
> 前置：`09-P0-1-SENSORS.md`（传感器真实状态 + 方向 bug 修复）
> **本文记录：把"加速度计能读数据"变成"屏幕会自动转"和"合盖会休眠"的完整实现。**

---

## 零、一句话状态

```
✅ 已交付：tablet-orientd —— 自动旋转 + 合盖休眠守护进程
   - 直接读 IIO 加速度计（不依赖 iio-sensor-proxy 的 compass 缺陷）
   - 几何判定 11/11 自测通过
   - 已装为 systemd 服务，但**默认 disabled**（等你拍板启用）
   - 零风险：不改 boot、不改驱动、不调 xrandr --rotate
```

**你要做的**：决定是否启用。一条命令：
```bash
sudo systemctl enable --now tablet-orientd
```

---

## 一、为什么不能照常规写自动旋转

### 1.1 三个"常规做法"在这台机器上都是坑

| 常规做法 | 为什么不行 |
|---|---|
| `monitor-sensor \| grep orientation` | iio-sensor-proxy 只报 **tilt**（face-up/flat），**不报 orientation**（left-up/right-up）。因为 SMGR 没有融合传感器 |
| `xrandr --output DSI-1 --rotate left` | **rotate + glamor = Adreno 512 硬挂死**（07 文档 §3，42 次 hard LOCKUP，只能物理重启） |
| Wayland 的自动旋转（sway/wlroots） | 本机是**原生 Xorg**，没有 wlroots |

### 1.2 实测的 iio-sensor-proxy 能力边界

```
$ monitor-sensor
=== Has accelerometer (orientation: undefined, tilt: face-up)
=== No ambient light sensor
=== No proximity sensor
=== No compass
```

**关键**：`orientation: undefined`。proxy 拿得到 tilt，拿不到方位角。

原因（09 文档 §5.2）：udev 规则要的是
`scan_elements/in_rot_from_north_magnetic_tilt_comp_en`（融合后的旋转矢量），
SMGR 只提供**原始** accel/gyro/mag，不提供融合量。

**所以自动旋转必须自己算。** 这反而是好事：不依赖 proxy 那个残缺的接口。

### 1.3 现有旋转机制的真实形态（关键发现）

`tablet-display-mode` **不是运行时旋转**，它是：

```bash
landscape)  touch /etc/tablet/landscape
            mv 50-msm-soft.conf.off -> 50-msm-soft.conf   # 关 glamor
            systemctl restart greetd                      # ← 重启整个会话！
```

会话脚本 `xfce-tablet-session` 在启动时读这个 flag：
```sh
if [ "$LANDSCAPE" = "1" ]; then
    xrandr --output "$OUT" --rotate left     # 此时 glamor 已关，安全
    xinput set-prop "$TOUCH_ID" "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1
fi
```

**两个关键事实：**
1. `xrandr --rotate left` **本身是安全的** —— 前提是 `AccelMethod "none"`（llvmpipe）
2. 切换模式**会重启 greetd**，即关闭所有应用

**这决定了 daemon 的设计**：它不能像手机那样流畅过渡，
只能在"竖屏 GPU 快"和"横屏软渲染安全"之间**整会话切换**。

---

## 二、`tablet-orientd` 设计

### 2.1 架构

```
systemd (system unit, User=user)
  └─ /usr/local/bin/tablet-orientd
       ├─ 线程 1: accel 轮询
       │    ├─ echo 1 > scan_elements/in_accel_{x,y,z}_en
       │    ├─ echo 1 > buffer/enable
       │    ├─ read(/dev/iio:device2, 24 bytes)   ← s32 x, s32 y, s32 z, u32 pad, s64 ts
       │    ├─ 乘 scale (1.5258e-05) 得到 m/s²
       │    ├─ classify() -> portrait | landscape | flat
       │    └─ 连续 3 次一致才动作（防抖）
       └─ 线程 2: /dev/input/event3 SW_LID
            ├─ val==1 (合上) -> tablet-sleep
            └─ val==0 (打开) -> tablet-sleep wake
```

### 2.2 方向判定算法（含几何论证）

**实测原始帧**（屏幕朝上平放）：
```
accel = (+0.16, +0.37, -9.73) m/s²      ← z 是重力，负号是驱动约定
```

**六种姿态的重力分布：**

| 姿态 | 重力主轴 | 判定 |
|---|---|---|
| 平放（屏朝上/下） | \|z\| ≈ 9.8 | `flat` → 保持当前 |
| 竖持（正常） | \|y\| ≈ 9.8 | `portrait` |
| 竖持（倒置） | \|y\| ≈ 9.8 | `portrait` |
| 横持（一侧） | \|x\| ≈ 9.8 | `landscape` |
| 横持（另一侧） | \|x\| ≈ 9.8 | `landscape` |
| 斜 45° 左右 | 两轴接近 | `flat` → **不改**（防抖） |

**判定规则：**
```python
TILT_G    = 6.5   # 平面轴上的重力必须超过这个值（≈41°倾斜内）
DOMINANCE = 2.0   # 主轴必须比次轴大 2 倍（≈26.5° 内），否则算模糊
```

**为什么 `DOMINANCE = 2.0`**：
tan(26.5°) ≈ 0.5，倒数是 2。即"离轴 26.5° 以内"才翻转。
更松的值（1.6 ≈ 32°）会在手斜着拿时误翻转 —��� 这是自测逼出来的。

### 2.3 自测覆盖（11 项，全部通过）

```
[OK] lying flat, screen up (MEASURED)      ( +0.16, +0.37, -9.76) -> flat
[OK] lying flat, screen down               ( +0.16, +0.37, +9.76) -> flat
[OK] held upright, portrait (natural)      ( +0.20, -9.75, +0.30) -> portrait
[OK] held upright, portrait upside-down    ( +0.20, +9.75, +0.30) -> portrait
[OK] held upright, landscape (one side)    ( +9.75, +0.30, +0.20) -> landscape
[OK] held upright, landscape (other side)  ( -9.75, +0.30, +0.20) -> landscape
[OK] diagonal ~58 deg, ambiguous           ( +5.00, +8.00, +0.50) -> flat
[OK] near 45 deg, ambiguous                ( +7.00, +6.90, +0.50) -> flat
[OK] flat but upside down (screen down)    ( +0.50, +0.50, +9.70) -> flat
[OK] portrait, tilted ~11 deg              ( +0.30, -9.60, +1.80) -> portrait
[OK] landscape, tilted ~11 deg             ( +9.60, -1.80, +0.30) -> landscape

11/11 passed
```

**自测是硬性门槛**：改阈值必须重跑，`--selftest` 返回非 0 就不能装。

### 2.4 安全设计（为什么零风险）

| 风险 | 规避方式 |
|---|---|
| GPU 硬挂死 | **从不直接调 `xrandr --rotate`**，只调 `tablet-display-mode`（先关 glamor 再重启会话） |
| 误翻转打断工作 | 连续 3 次一致（1.2 秒）+ 26.5° 死区 |
| 平放时乱转 | 重力在 z 轴 → `flat` → **什么都不做** |
| 权限不足 | 系统服务 + `CAP_DAC_OVERRIDE`（只给这一个能力） |
| 与 iio-sensor-proxy 冲突 | 不订阅 proxy，**直接读 IIO**，互不干扰 |
| 开机就转 | **默认 disabled**，需要你手动 enable |

**唯一的"副作用"是设计意图**：方向变化会重启 greetd，等于切换桌面模式。
应用会被关闭。这是现有架构的限制，不是 daemon 的 bug。

---

## 三、安装与验证（已实测）

### 3.0 源码位置

| 文件 | 说明 |
|---|---|
| `mipad4plus/tools/tablet-orientd` | 可执行源码（部署到 `/usr/local/bin/`） |
| `mipad4plus/tablet-orientd.txt` | 同一份，改成 `.txt` 方便直接阅读 |

**自测**（不需要 root）：
```bash
python3 mipad4plus/tools/tablet-orientd --selftest
# 期望：11/11 passed
```

### 3.1 已完成的部署

```bash
/usr/local/bin/tablet-orientd                          # 9,559 字节，0755
/etc/systemd/system/tablet-orientd.service             # 系统服务，User=user
/etc/udev/rules.d/99-tablet-accel-matrix.rules         # 方向修正（09 文档 §5.1）
/etc/udev/rules.d/99-tablet-sensors-user.rules         # iio/input 组（辅助）
```

**服务内容：**
```ini
[Service]
Type=simple
User=user
SupplementaryGroups=input
AmbientCapabilities=CAP_DAC_OVERRIDE
CapabilityBoundingSet=CAP_DAC_OVERRIDE
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/10000
ExecStart=/usr/local/bin/tablet-orientd
Restart=on-failure
Nice=5
```

**为什么需要 `CAP_DAC_OVERRIDE`**：
IIO 的 sysfs 属性是 `root:root 0644`，`udev GROUP=` **对 sysfs 属性无效**
（实测：`ls -l .../buffer/enable` 仍是 `root root`）。
加 `iio` 组也没用（实测 `sg iio` 写不进去）。
所以只能给这一个能力，比整个服务跑 root 更窄。

### 3.2 实测记录

```
$ systemctl start tablet-orientd
$ journalctl -u tablet-orientd -n 5
[orientd] watching /dev/input/event3 for SW_LID
[orientd] accel scale = 1.5258e-05

$ tablet-orientd --dry-run --rotate-only
[dry] accel=+0.17,+0.38,-9.73 -> flat (current landscape)
[dry] accel=+0.15,+0.37,-9.70 -> flat (current landscape)
...
（正确识别为 flat，因为平板确实平放；没有误触发切换）
```

**状态确认：**
```
landscape flag: PRESENT（未被改动）
Xorg=1  xfwm4=1（桌面存活）
accel buffer=0（每次采样后正确关闭，不泄漏）
boot 分区: 0 files（未被触碰）
```

### 3.3 启用 / 停用

```bash
# 启用（重启后仍生效）
sudo systemctl enable --now tablet-orientd

# 临时跑一下看行为
sudo systemctl start tablet-orientd
journalctl -u tablet-orientd -f

# 停用
sudo systemctl disable --now tablet-orientd

# 干跑（不切换，只打印判定）
sudo systemctl stop tablet-orientd
sudo -u user DISPLAY=:0 /usr/local/bin/tablet-orientd --dry-run
```

---

## 四、合盖休眠（已实现，未实测）

### 4.1 硬件路径（已验证存在）

```
gpio75  : in  high func0 6mA pull up          ← 霍尔引脚，当前高电平（盖子打开）
中断表  : msmgpio  75 Edge  Hall Effect Sensor
input   : /dev/input/event3  (gpio-hall-sensor)
SW_LID  : 当前 = 0（打开）
wakeup  : enabled（可唤醒）
```

**这条路完全绕开 SMGR/DSP**，是 09 文档 §4.3 推荐方案的具体实现。

### 4.2 daemon 的合盖逻辑

```python
# 线程 2: 读 /dev/input/event3
if typ == EV_SW(0x05) and code == SW_LID(0x00):
    if val == 1:  tablet-sleep        # 合上
    if val == 0:  tablet-sleep wake   # 打开
```

用的是现有的 `tablet-sleep`（即 09 文档提到的"伪休眠"，关背光 + DPMS off），
不是真休眠（真休眠被 `mdss_runtime_suspend` 死锁阻塞，见 00-GOAL §4.2）。

### 4.3 ⚠️ 未实测的部分（需要磁铁）

**你说没有磁铁，所以这一段没有验证：**

| 项 | 状态 |
|---|---|
| SW_LID 是否随磁铁翻转 | ❓ **未测**（`event_count = 0`，从未触发过） |
| 极性是否如假设（1=合上） | ❓ 未测 |
| `tablet-sleep` 在合盖时是否合适 | ❓ 未测 |

**这意味着合盖休眠功能虽然代码就绪，但不能算"已验证"。**

**没有磁铁的替代验证方法**（如果你愿意）：
```bash
# 1. 先用软方式确认 event3 通路能收到事件（不需要磁铁）
sudo evtest /dev/input/event3     # 然后碰一下平板边缘/靠近任何磁铁性物体
#    或者：用另一个磁铁性物体（螺丝刀、音箱、冰箱贴、手机壳磁扣）

# 2. 确认 tablet-sleep 本身正常（不用磁铁）
sudo -u user DISPLAY=:0 /usr/local/bin/tablet-sleep
sudo -u user DISPLAY=:0 /usr/local/bin/tablet-sleep wake
```

**如果你之后拿到磁铁**：
```bash
# 单独看 lid 事件（不影响桌面）
sudo -u user /usr/local/bin/tablet-orientd --lid-only
# 合上保护套 -> 应打印 "lid closed -> tablet-sleep"
```

---

## 五、这一轮的认知更新

### 5.1 "自动旋转"在这台机器上的真实含义

不是手机那种"屏幕内容平滑转 90°"。而是：

```
竖持 → 1200×1920，glamor/FD512 硬件加速，省电
横持 → 1920×1200，llvmpipe 软渲染，安全
切换 = 重启 greetd = 关闭所有应用
```

**这是 Adreno 512 + 当前内核的硬限制**（面板只支持 rotate-0/180，
90° 必须软件合成，而软件合成 + glamor 会挂 GPU）。

**对办公电脑的实际影响**：横屏是用来"接键盘当笔记本用"的，
通常一整天不会变。所以"切换会关应用"其实影响不大 ——
**你不会在打字途中转屏幕。**

### 5.2 一个可能更好的方向（留给后续）

如果"切换关应用"不可接受，可以试：

| 方案 | 代价 | 收益 |
|---|---|---|
| 横屏常驻 + 只用软渲染 | 一直 llvmpipe（CPU 高一点） | 永不切换，零打扰 |
| 试 `rotate-180` + 面板翻转 | 需要改 DSI 初始化序列 | 可能拿到 GPU 加速的横屏 |
| 等上游修 a5xx + glamor rotate | 不确定 | 理想解 |

**我倾向第二个**：面板驱动 `panel-novatek-nt51021.c` 支持 180° 翻转，
如果能把"物理横屏"变成"面板原生 1920×1200 + 180° 翻转"，
就完全不需要软件旋转，GPU 加速也能用。

**这是一个待验证的假设，需要读面板驱动确认是否支持
`MIPI_DSI_MODE_LPM` + 翻转寄存器。** 记在 TODO 里。

### 5.3 方法论：自测先行

写 daemon 时先写 `--selftest`，用**几何真值**（不是"跑起来不崩"）验证分类逻辑。
这次自测抓出了一个真 bug：`DOMINANCE=1.6` 时 32° 倾斜就会误翻转，
用户斜着拿平板会疯狂切模式。

**教训：涉及物理量判定的代码，必须有可复现的真值表，不能靠"看起来对"。**

---

## 六、当前设备状态（2026-10-24 10:10）

```
boot 分区    = 未动（0 文件），仍是 boot-pri-mi2s.img
内核         = 7.0.14-sdm660（未重编）
桌面         = 1920×1200 横屏，DPI 150，llvmpipe
传感器       = accel/gyro/mag 可用；ALS 待修；hall 走 gpio-keys
方向修正     = 已生效（monitor-sensor 报 face-up）
tablet-orientd = 已安装，**disabled**（等你决定）
```

### 本次会话累计改动（全部可回滚）

| 改动 | 路径 | 回滚 |
|---|---|---|
| 方向修正 | `/etc/udev/rules.d/99-tablet-accel-matrix.rules` | `rm` + `udevadm reload/trigger` |
| 传感器组权限 | `/etc/udev/rules.d/99-tablet-sensors-user.rules` | 同上 |
| 旋转 daemon | `/usr/local/bin/tablet-orientd` | `rm` |
| daemon 服务 | `/etc/systemd/system/tablet-orientd.service` | `systemctl disable` + `rm` |
| user 加入 iio/input 组 | `/etc/group` | `deluser user iio input` |
| 诊断工具 | `apk add qrtr libssc-pyc` | `apk del qrtr`（libssc 勿删） |

**没动**：boot、rootfs 关键文件、驱动源码、DT、Xorg 主配置。

---

## 七、下一步（不变的部分）

按 `09-P0-1-SENSORS.md` §6.4，还差：

| # | 事项 | 要编内核 | 状态 |
|---|---|---|---|
| 1 | ~~自动旋转 daemon~~ | ❌ | ✅ **本轮完成** |
| 2 | ~~保护套休眠代码~~ | ❌ | ✅ 代码就绪，**待磁铁实测** |
| 3 | 补 `cm3232.json` 到 DSP registry | ❌ | 待做（§6.2 改动 3） |
| 4 | 改 prox 驱动 `IIO_INTENSITY` | ✅ | 待做（要你同意刷 boot） |
| 5 | 试"物理横屏"（rotate-180 + 面板翻转） | 可能要 | 新想法，待评估 |
