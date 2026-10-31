# 54 — Wayland 桌面 + GPU 加速 + 四方向自动旋转（收官）

- 日期：2026-10-30 18:15
- 目标：像电脑一样的桌面 + 横屏 + 硬件加速 + 自动旋转

---

## 1. 为什么 X11 做不到“横屏 + 加速”

- DPU（sdm660，DPU 3.0.2）**没有 90° 内联旋转硬件**：
  - sdm660 的 VIG SSPP 是 `_VIG_SBLK(...)`，`rotation_cfg = NULL`；
  - 全内核唯一带 `_VIG_SBLK_ROT` 的是 `dpu_vig_sblk_qseed3_3_0_rot_v2`（SC7280/DPU 6.x）；
  - 因此 X 的 RandR 旋转（glamor 或软件）都会黑屏，只有 fbdev 的图像旋转能用（无加速）。
- 结论：想在 X 上同时横屏+加速，硬件不支持。

## 2. 最终方案：Wayland LXQt（labwc 合成器）

- 安装：`lxqt-wayland-session`、`labwc`、`wlr-randr`、`grim`；
- `~/.config/lxqt/session.conf` 加 `compositor=labwc`；
- greetd 启动 `/usr/local/bin/tablet-wayland-session`（→ `startlxqtwayland`）；
- labwc 以 `wlr-randr --output DSI-1 --transform 90` 横屏启动；
- 合成器用 GPU 把桌面旋转后渲染进面板原生的 1200×1920 缓冲，
  **不依赖 DPU 旋转**，所以横屏和加速同时成立。

验证：
```
wlr-randr: DSI-1 1200x1920, Transform: 90
glxinfo/eglinfo: freedreno FD512, OpenGL 3.1 / GLES 3.1
grim 截图: 1920x1200
```

## 3. GPU 固件（前置条件）

- 从厂商 `vendor.img:/firmware/` 提取 `a512_zap.*`、`a530_pfp.fw`、`a530_pm4.fw`；
- 打进 **boot 的 initramfs**（`usr/lib/firmware/` 和 `usr/lib/firmware/qcom/`）；
- 没有它们 GPU 不初始化，glamor/合成器无法加速。

## 4. 四方向自动旋转（`tablet-orientd`）

- 直接读 `/dev/iio:device2`（`qcom-smgr-accel`）的 IIO buffer，不用 iio-sensor-proxy；
- 传感器 mount matrix：`0,-1,0; -1,0,0; 0,0,1`
  ⇒ 设备系 `X=-raw_y, Y=-raw_x, Z=raw_z`；
- 映射：
  | 设备系 | transform |
  |---|---|
  | X > 0（横屏） | 90 |
  | X < 0（横屏反向） | 270 |
  | Y < 0（竖屏） | normal |
  | Y > 0（竖屏反向） | 180 |
- 阈值 0.6g、主导轴 1.3×、0.8s 迟滞，避免抖动误切；
- systemd 服务 `/etc/systemd/system/tablet-orientd.service`（enabled）。

实测日志（用户依次转四个方向）：
```
transform -> 90
transform -> normal
transform -> 270
transform -> 180
```
用户确认四个方向全部正确。

## 5. 持久化 / 回滚

- 持久化：greetd 配置、`~/.config/labwc/`、`tablet-orientd.service`、boot 里的 zap 固件；
- 回滚到 X11 fbdev：
  ```
  sudo cp /etc/phrog/greetd-config.toml.bak-x11 /etc/phrog/greetd-config.toml
  sudo systemctl stop tablet-orientd && sudo systemctl disable tablet-orientd
  sudo systemctl restart greetd
  ```
- X11 的 fbdev 配置仍在 `/etc/X11/xorg.conf.d/20-fbdev.conf`（Wayland 下不使用）。

## 6. 当前状态

- LXQt Wayland 桌面，横屏 1920×1200，GPU 加速（FD512）；
- 四方向自动旋转正常；
- Xwayland 运行 X11 应用（LXQt 面板、pcmanfm 等）；
- 系统稳定（连续运行 17 分钟无挂死）。

## 7. 已知问题：触摸只校准了横屏

- 触屏的 libinput 校准矩阵是**每个方向都不同**的（wlroots 不会把输出旋转应用到绝对坐标输入上）。
- 实测：横屏（transform 90）用 `0 -1 1 1 0 0` 正确；
  竖屏（normal）用 identity / 180° 矩阵都不对（点左上角会落到右上，且不是水平对齐）。
- 已实现按方向切换矩阵：`/usr/local/bin/tablet-touch-matrix {90|270|normal|180}`
  （写 udev 规则 + `udevadm trigger`），`tablet-orientd` 和 `tablet-rotate` 都会调用；
  但运行中 labwc 对矩阵的重读不稳定，且竖屏的正确矩阵还没标定出来。
- 当前默认：**锁定横屏 + 横屏矩阵**（`tablet-rotate lock`，flag=off），触摸正常。
- 「平板设置 → 屏幕方向」新增了 **自动旋转开关**；手动方向按钮会自动锁定。
- 下一步：竖屏矩阵需要再做 2–3 次标定测试（每次换矩阵 + trigger），
  或者改为“切换方向时重启合成器”以保证矩阵生效。

## 8. 触摸矩阵最终标定（18:45 完成）

四个方向全部实测通过：

| transform | 矩阵 |
|---|---|
| normal（竖屏） | `1 0 0 0 1 0 0 0 1` |
| 90（横屏） | `0 -1 1 1 0 0 0 0 1` |
| 180（竖屏倒置） | `-1 0 1 0 -1 1 0 0 1` |
| 270（横屏反向） | `0 1 0 -1 0 1 0 0 1` |

关键点：**改完 udev 规则后必须重新绑定触摸设备**（`Goodix-TS` 的 i2c client `0-005d`
unbind/bind），否则运行中的 labwc 不会重读矩阵。已封装在
`/usr/local/bin/tablet-touch-matrix {90|270|normal|180}`，`tablet-orientd` 和
`tablet-rotate` 每次切方向都会调用它。

已知瑕疵：**切换方向时画面有短暂卡顿**（已确认与重绑触摸无关，只切 transform 也卡；
dmesg 无 DPU 错误），属于合成器换缓冲/重绘的开销，暂时接受。

「平板设置 → 屏幕方向」里的**自动旋转开关**：
- 开 → 四方向自动旋转（触摸随方向切换）；
- 关 → 锁定当前方向；手动方向按钮也会自动锁定。


