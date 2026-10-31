# 44 — 屏幕旋转与触摸校准

- 日期：2026-10-29
- 结论：横屏用 `rotate left + reflect xy`；触摸必须设 **libinput Calibration Matrix**（XInput 的 CTM 在 libinput 设备上是只读的）。

---

## 1. 为什么不能用普通的 `--rotate right`

这台平板的 **DPU 主图层硬件旋转是坏的**：

```
xrandr --output DSI-1 --rotate right   → 物理屏幕全黑，只有硬件光标在动
xrandr --output DSI-1 --rotate left    → 能显示，但方向上下颠倒
xrandr --output DSI-1 --rotate left --reflect xy  → 横屏，方向正确 ✅
```

`left + reflect xy` 在数学上等价于 `right`（顺时针 90°），但驱动走的是反射路径，
避开了坏掉的那条旋转路径。

### 1.1 四种方向的实际实现

| 逻辑方向 | xrandr 命令 | 视觉 | 可用 |
|---|---|---|---|
| `normal` | `--rotate normal` | 竖屏 | ✅ |
| `inverted` | `--rotate inverted` | 竖屏倒置 | ✅ |
| `left` | `--rotate left --reflect xy` | 横屏（顺时针 90°） | ✅ |
| `right` | `--rotate left` | 横屏（逆时针 90°） | ✅ |

（`--rotate right` 本身不可用，所以 `right` 用 `--rotate left` 实现，正好是它的 180°。）

---

## 2. 触摸校准：踩了三个坑

### 2.1 坑一：以为改旋转会自动改触摸

不会。X 只旋转画面，触摸设备仍按原生坐标系上报，所以点位全错。

### 2.2 坑二：`libinput Rotation Angle` 只能旋转，不能镜像

我们的横屏组合里带 `reflect xy`，单纯旋转角表达不了。

### 2.3 坑三（最关键）：XInput 的 `Coordinate Transformation Matrix` 是只读的

```
$ xinput set-prop 9 'Coordinate Transformation Matrix' 0 -1 1 1 0 0 0 0 1
$ xinput list-props 9 | grep 'Coordinate Transformation'
  Coordinate Transformation Matrix (122): 1, 0, 0, 0, 1, 0, 0, 0, 1   ← 没变
```

设了完全没反应。真正生效的是：

```
libinput Calibration Matrix (258)        ← 这个可写
libinput Calibration Matrix Default (259)
```

**我在这上面浪费了很久**：一直改只读属性，所以无论怎么试触摸都不对。

### 2.4 触摸控制器原生坐标系（实测）

```
/dev/input/event4  Goodix Capacitive TouchScreen
  ABS_X              min=0 max=1199      (1200)
  ABS_Y              min=0 max=1919      (1920)
```

与面板原生竖屏一致（1200×1920），所以竖屏用单位矩阵即可。

### 2.5 最终矩阵表

X 的矩阵按行主序 `a b c / d e f / g h i`，作用于归一化坐标 `(u,v)`：

```
u' = a*u + b*v + c
v' = d*u + e*v + f
```

| 方向 | 矩阵 | 含义 |
|---|---|---|
| `normal` | `1 0 0  0 1 0  0 0 1` | 不变 |
| `inverted` | `-1 0 1  0 -1 1  0 0 1` | 180°：`(1-u, 1-v)` |
| `left` | `0 1 0  -1 0 1  0 0 1` | `(v, 1-u)` ✅ 实机验证 |
| `right` | `0 -1 1  1 0 0  0 0 1` | `(1-v, u)` |

`left` 是用户在横屏下实测校准的：点屏幕左上角，指针必须落在左上角。

---

## 3. 自动旋转：绕过坏掉的 iio-sensor-proxy

### 3.1 为什么 monitor-sensor 没用

```
iio-sensor-proxy: Could not find trigger name associated with
  .../qcom-smgr-accel.0/iio:device2
```

这颗 BMI120（QCOM SMGR 驱动）**没有 IIO trigger**，而 iio-sensor-proxy 依赖它，
所以方向永远是 `undefined`，只能报 `tilt: face-up`。

### 3.2 直接读 IIO 缓冲区

实测的真实布局（`scan_elements` 声称 16 字节，实际不是）：

```
offset 0   x   int32 LE
offset 4   y   int32 LE
offset 8   z   int32 LE
offset 12  4 字节填充
offset 16  timestamp int64
stride     24 字节
```

读数验证：静止时 `|g| ≈ 9.9 m/s²`，与重力一致。

**注意**：读 16 字节会被内核拒绝（EINVAL），必须读 ≥128 字节再按 24 字节切片。

### 3.3 方向映射（由挂载矩阵推导）

```
in_mount_matrix = 0,-1,0 ; -1,0,0 ; 0,0,1
=> sensor_x = -body_y,  sensor_y = -body_x,  sensor_z = body_z
```

| 物理姿态 | 加速度计主分量 | 逻辑方向 |
|---|---|---|
| 竖放正立 | `x+` | `normal` |
| 竖放倒立 | `x-` | `inverted` |
| 横放（一侧朝下） | `y+` | `left` |
| 横放（另一侧朝下） | `y-` | `right` |
| 平放 | `z ≈ ±9.8` | 保持当前方向，不旋转 |

### 3.4 防闪烁

初版在 45° 附近判定抖动，每抖一次就是一次 modeset → 屏幕闪。修正：

- 主轴占比 < 62% 时判为 `ambiguous`，不切换
- 必须**连续 6 个样本**（约 3 秒）方向一致才切换
- 平放（face-up/down）保持当前方向

---

## 4. 组件与文件

| 项目 | 路径 |
|---|---|
| 手动旋转 | `/usr/local/bin/tablet-rotate` |
| 自动旋转守护 | `/usr/local/bin/tablet-autorotate` |
| 服务 | `tablet-autorotate.service`（root 运行，带 `DISPLAY=:0` + 用户 Xauthority） |
| 方向映射 | `/etc/tablet/rotation.conf` |
| 手动覆盖状态 | `~/.config/tablet/rotation-manual` |
| 桌面图标 | `~/Desktop/旋转.desktop` |
| 会话里的初始旋转 | `/usr/local/bin/lxqt-x-session`、`xfce-x-session` |

守护进程必须以 **root** 运行（要写 `/sys/.../buffer/enable`），
但 `xrandr` / `xinput` 要连用户会话的 X，所以 unit 里带：

```ini
User=root
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/user/.Xauthority
```

---

## 5. 用法

```sh
tablet-rotate normal|inverted|left|right   # 手动指定
tablet-rotate cycle                        # 循环切换
tablet-rotate auto                         # 交回重力自动旋转
tablet-rotate status                       # 看当前状态

systemctl status|restart|stop tablet-autorotate
tablet-autorotate --calibrate              # 实时打印重力向量与判定
```

手动转过一次后自动旋转会暂停（避免刚调好又被重力抢走），`tablet-rotate auto` 恢复。

---

## 6. 教训

1. **显示问题必须对比 X 截图和物理屏幕**，只看内核日志会误判（DPU 报错为 0 不代表画面正常）。
2. **改属性要看改完的值**：`xinput set-prop` 对只读属性不报错也不生效，必须 `list-props` 回读。
3. **格式字符串会骗人**：`SGRBG10` 实际是 BGGR；`scan_elements` 说 16 字节实际 24 字节；只信实测。
