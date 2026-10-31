# 50 — 横屏成功：给 fbdev 驱动加"竖屏面板旋转"补丁

- 日期：2026-10-30 12:00
- 结果：**1200×1920 竖屏面板上跑出 1920×1200 横屏桌面**（fbdev + ShadowFB 软件旋转）
- 关键文件：`patches/fbdev-rotate/`

---

## 1. 为什么 stock fbdev 的 `Option "Rotate"` 会失败

```
(EE) FBDEV(0): FBIOPUT_VSCREENINFO: Invalid argument
(EE) FBDEV(0): mode initialization failed
```

`xf86-video-fbdev` 的旋转实现是给**横屏面板**设计的：

1. `FBDevScreenInit()` 先用面板原生模式（1200×1920）做 `fbdevHWModeInit()`；
2. 然后把 `pScrn->virtualX/Y` 转置成 1920×1200，`fbScreenInit()` 申请 1920×1200 的 shadow；
3. **但之后 X 服务器还会调用 `SwitchMode`**，此时 `fbdevHWSetMode()` 用转置后的尺寸算
   `xres_virtual/yres_virtual`，得到 `yres_virtual(1200) < yres(1920)` → DRM fbdev 直接 EINVAL。

本机面板是竖屏，所以这条路必挂。

## 2. 补丁内容（`patches/fbdev-rotate/fbdev.c`）

三处改动，`xf86-video-fbdev 0.5.0`：

| 位置 | 改动 |
|---|---|
| `FBDevPtr` | 加 `Bool rotated` |
| `FBDevScreenInit()` | 做模式设置前，强制把 `virtualX/Y/displayWidth` 还原成 `currentMode` 的 1200×1920；设置成功后再转置并置 `rotated=TRUE`。**模式设置失败时自动退回不旋转**（保证不会黑屏） |
| `fbdevSwitchMode()` / `fbdevEnterVT()` | 旋转状态下调用 `fbdevHW*ModeInit` 前临时把尺寸换回面板的 1200×1920，调用完再换回来 |

效果：fb 模式始终是面板的 1200×1920；X 屏幕是 1920×1200；ShadowFB 负责把每次 damage
旋转写进 fb（`FBDevWindowLinear` 用 `fix.line_length`=4864，自动处理 stride 填充）。

## 3. 一个必须注意的坑：BIND_NOW 导致模块加载失败

第一次编译出来的 `.so` 带 `BIND_NOW`（eager binding），X 加载时报：

```
(EE) Failed to load .../fbdev_drv.so: Error relocating ...: fbdevHWEnterVT: symbol not found
```

原因：`fbdevHW*` 符号在 `libfbdevhw.so` 里，由 X 的 loader 在运行时解析；主程序
`/usr/libexec/Xorg` 并不导出它们。stock 模块是 lazy binding，所以能加载。

解决：编译时 `export LDFLAGS="-Wl,-z,lazy"`，然后确认
`readelf -d fbdev_drv.so | grep BIND_NOW` 为空。

## 4. 部署结果（实机，已通过重启验证）

重启后（2026-10-30 12:05，uptime 133s）：
```
xrandr: current 1920 x 1200
fb0: 1200x3840（面板模式未变）
xinput id 9:
  libinput Calibration Matrix:         0,-1,1, 1,0,0, 0,0,1
  libinput Calibration Matrix Default: 0,-1,1, 1,0,0, 0,0,1   ← udev 自动生效
systemctl: tablet-autorotate=inactive, tablet-touch-rotate=inactive, tablet-no-blank=active
fb 抓图 mean=30.3（非黑），转 90° 后桌面完整
```
⇒ 横屏、触摸矩阵、服务状态全部**开机自动恢复**，无需人工干预。

```
$ xrandr --query
Screen 0: minimum 1200 x 1200, current 1920 x 1200, maximum 1920 x 1920
default connected 1920x1200+0+0 0mm x 0mm
   1200x1920      0.00
   1920x1200      0.00*
$ cat /sys/class/graphics/fb0/virtual_size
1200,3840          # 面板模式没变，仍是竖屏 1200×1920（双缓冲）
```

抓 `/dev/fb0` 第一页（1200×1920）转 90° 后得到完整的 1920×1200 桌面：
`build/fb_land2_upright.png`（面板在底部、图标在左上，文字方向正确）。

## 5. 触摸

`Rotate "CCW"` 对应 screen=(1−v, u)，因此：

```
# 运行时（X 里）
xinput set-prop 9 'libinput Calibration Matrix' 0 -1 1 1 0 0 0 0 1

# 持久化（udev，libinput 用 6 值）
/etc/udev/rules.d/99-goodix-landscape.rules
ATTRS{name}=="Goodix Capacitive TouchScreen", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 -1 1 1 0 0"
```

注意 Goodix 有两个 XInput 设备（id 9 pointer、id 11 keyboard），**必须设 id 9**；
`xinput set-prop "名字"` 会报 multiple devices。

## 6. 关闭的两个服务（重要）

```sh
systemctl disable --now tablet-autorotate tablet-touch-rotate
```

- `tablet-autorotate`：本来用于 DPU 黑屏自愈/重力旋转；横屏固定后不需要，
  而且它会把 modeset 异常升级成 `systemctl reboot`（10-30 上午就被它坑过一次）。
- `tablet-touch-rotate`：它按 XRandR 旋转状态反复改触摸矩阵；fbdev 下没有 RandR，
  会把我们设好的矩阵覆盖掉。

## 7. 回滚（30 秒）

```sh
cp /root/fbdev_drv.so.orig /usr/lib/xorg/modules/drivers/fbdev_drv.so
cp /root/20-fbdev.conf.orig /etc/X11/xorg.conf.d/20-fbdev.conf
rm -f /etc/udev/rules.d/99-goodix-landscape.rules
udevadm control --reload
systemctl restart greetd
systemctl enable --now tablet-autorotate tablet-touch-rotate
```

## 8. 想换成另一个横屏方向（转 180°）

把 `20-fbdev.conf` 里的 `Rotate` 改成 `CW`，触摸矩阵改成
`xinput set-prop 9 'libinput Calibration Matrix' 0 1 0 -1 0 1 0 0 1`，
udev 规则改成 `"0 1 0 -1 0 1"`，重启 greetd 即可。

## 9. 已知代价

- 旋转是 **CPU 软件旋转**（ShadowFB），不是 DPU 硬件旋转；全屏刷新会吃 CPU，
  普通桌面/浏览够用，视频全屏会明显。
- 没有 glamor/GPU 合成（本来也没有）。
- `FBIOPUTCMAP: Invalid argument` 每帧报错是 32bpp fbdev 的无害现象。
