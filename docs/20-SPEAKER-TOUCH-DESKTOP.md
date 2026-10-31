# 20 · 桌面补齐 + 触摸矩阵 + ALS + 扬声器移植

> 创建：2026-10-24 23:45（Asia/Shanghai）
> 前置：`HANDOFF.md`、`13-ALS-SUCCESS.md`、`18-HARDWARE-COMPLETE.md`
> 本文记录 2026-10-24 22:25 ~ 23:45 这一轮的全部改动，以及**未完成/有风险**的部分。

---

## 零、一句话状态

```
✅ 桌面：电量/网络/蓝牙/音量/通知 全部补齐，应用菜单换成 Whisker（可搜索）
✅ 触摸：新增 tablet-touch-rotate，矩阵自动跟随四种旋转（含自愈）
✅ ALS：自动亮度服务修好并启用（条件写死 device3 → 按名字找 device5）
⚠️ 扬声器：驱动/固件/声卡都通了，但**功放不出声**（根因未定）
❌ GPU：glamor 在本机必挂（a5xx ring fault），已回退软件渲染
⚠️ 横屏：开机即横屏会触发 DPU 提交超时 → 黑屏（见 §5）
```

---

## 一、桌面补齐（用户要求：电量/蓝牙/网络/WiFi 设置）

### 1.1 安装的包

```bash
apk add network-manager-applet blueman xfce4-pulseaudio-plugin \
        xfce4-notifyd xfce4-whiskermenu-plugin
```

### 1.2 面板插件（panel-1，共 12 个）

| id | 插件 | 作用 |
|---|---|---|
| 1 | `whiskermenu` | 应用菜单（带搜索/分类，替代原来空白的 applicationsmenu）|
| 2 | `tasklist` | 窗口列表 |
| 3-7 | separator/pager/systray | 原有 |
| 19 | `battery` | **电量百分比 + 图标**（走 UPower）|
| 20 | `pulseaudio` | **音量图标 + 滑块** |
| 8-10 | clock/actions | 时钟、用户菜单 |

**关键坑**：改 `xfconf` 必须在面板**退出后**改，否则面板退出时会用内存里的旧配置覆盖：

```bash
xfce4-panel -q                      # 先退出
xfconf-query ...                    # 再改
systemd-run --user --unit=xfce4-panel-restore ... /usr/sbin/xfce4-panel
```

### 1.3 托盘（网络 / 蓝牙）

`nm-applet` + `blueman-applet` 必须在**会话自己的 D-Bus** 上运行。XFCE 会话的 bus 是
`/tmp/dbus-XXXX`，**不是** `/run/user/10000/bus`（那是 systemd user manager 的）。
用错总线时 nm-applet 能起但托盘不注册，blueman 直接 D-Bus 超时退出。

自动启动文件（写入 `~/.config/autostart/`）：

```ini
# nm-applet.desktop
Exec=nm-applet          # 不要 --indicator：XFCE systray 不支持 StatusNotifier
# blueman-applet.desktop
Exec=blueman-applet
```

### 1.4 systemd 会话单元会杀进程

从 SSH 用 `nohup ... &` 启动的 GUI 进程会被 systemd 按会话 scope 清理：

```
systemd[1]: session-c198.scope: Killing process 24676 (xfce4-panel) with signal SIGTERM
```

**正确做法**：`systemd-run --user --unit=... --setenv=DISPLAY=:0 ...`，
或写进 `~/.config/autostart/`。

### 1.5 应用菜单空白

`/etc/xdg/menus/xfce-applications.menu` 在 garcon 下解析出 0 项（`xfce4-appfinder` 却有全部应用，
说明 .desktop 没问题，是菜单文件本身的问题）。直接换 Whisker Menu：

```bash
xfconf-query -c xfce4-panel -p /plugins/plugin-1 -t string -s whiskermenu
```

同时把 `gnome-applications.menu` 软链到 `xfce-applications.menu`，消除
“无法载入应用程序菜单”的报错。

### 1.6 onboard 虚拟键盘

原来会话启动时无条件拉起 onboard，浮在左上角挡住内容。已在
`/usr/local/bin/xfce-tablet-session` 里把启动条件改成 `if false && ...`（保留可手动启动）。

---

## 二、触摸坐标（用户报“点这到那”）

### 2.1 根因

1. 屏幕旋转（xrandr）和触摸矩阵（X input property）是**两套独立状态**，没人同步；
2. `xfsettingsd` 启动时会重置矩阵；
3. 旧代码里 left/right 的矩阵**方向写反了**（镜像）。

### 2.2 新组件 `tablet-touch-rotate`

- `/usr/local/bin/tablet-touch-rotate`（Python，源码在 `tools/tablet-touch-rotate`）
- `/etc/systemd/system/tablet-touch-rotate.service`（User=user，`Restart=always`）

每秒读一次 `xrandr --query` 的真实 rotation，把矩阵写成对应值；**发现被改回就重设**。
矩阵按 libinput 官方文档校正：

| xrandr | 矩阵 |
|---|---|
| normal | `1 0 0 0 1 0 0 0 1` |
| left | `0 -1 1 1 0 0 0 0 1` |
| right | `0 1 0 -1 0 1 0 0 1` |
| inverted | `-1 0 1 0 -1 1 0 0 1` |

实测四种旋转都能在 1–2 秒内自动同步（`pad_rot_test.sh`）。

**注意**：`xinput list-props` 输出带逗号，解析时必须去掉，否则每秒都判定为“变了”并重写
（第一版就踩了这个坑，CPU 白烧 41 秒）。

### 2.3 设备坐标轴

`xinput` 的 Goodix 设备在 DTS 里是 `touchscreen-size-x=1200 / y=1920`，没有 swapped-x-y，
所以竖屏 identity 正确，横屏用上面的旋转矩阵。

### 2.4 待验证

矩阵方向是否正确需要**手指实测**（点左上角看光标是否也在左上角）。若整体镜像，
执行 `tablet-touch-rotate --flip` 即可翻转并持久化到 `/etc/tablet/touch.json`。

---

## 三、ALS 自动亮度

```bash
# 删掉写死的条件
sed -i '/^ConditionPathExists=/d' /etc/systemd/system/tablet-autobright.service
systemctl daemon-reload && systemctl restart tablet-autobright
```

日志确认：

```
tablet-autobright: ALS /sys/bus/iio/devices/iio:device5 (/dev/iio:device5)
tablet-autobright: backlight 255/255, curve 1.0-200.0 lx -> 15%-100%
```

`--dry-run` 实测读数 398–457 lx（室内灯光），说明传感器和曲线都在工作。

---

## 四、扬声器（TAS2557）—— 已通到声卡，但不出声

### 4.1 硬件事实（从设备 vendor 分区 + MIUI DTB 反解）

| 项 | 值 |
|---|---|
| 芯片 | TI TAS2557 ×2（`tas2557s`，DDC=D9）|
| I2C | `blsp_i2c6`（`c1b6000`）@ **0x4c 左 / 0x4e 右** |
| 复位 GPIO | 左 **80**，右 **48**（低有效）|
| IRQ | 左 28，右 55（下游编号）|
| 固件 | `/vendor/firmware/tas2557s_uCDSP_d9p.bin`，39615 B，MD5 `21a800398c167168579395d9662cf4f3` |
| 总线 | **主 MI2S（INT0）**，`i2s-bits = 16`，SoC 为 master |
| 供电 | 下游用 `cdc-vdd-spkdrv`（Android 报 regulator not found，实际常开）|

**固件是在设备上直接提取的**（vendor 分区还在，`mmcblk1p14`）：

```bash
debugfs -R "dump /firmware/tas2557s_uCDSP_d9p.bin /tmp/tasfw/x.bin" /dev/mmcblk1p14
cp /tmp/tasfw/x.bin /lib/firmware/tas2557_uCDSP.bin   # 驱动默认名
```

### 4.2 内核改动（pmaports 补丁）

| 补丁 | 内容 |
|---|---|
| `0002-...clover-tas2557.patch` | DTS 加 `&blsp_i2c6` 两个 `ti,tas2557` 节点，并把它们加进 `int0-mi2s-dai-link` 的 codec 列表 |
| `0003-ASoC-tas2557-unique-...patch` | 驱动支持**双实例**：控件名加 Left/Right 前缀、DAI 名加 -left/-right（否则第二颗注册时报 `control ... already present`，整张声卡注册失败）|

编译：`pmbootstrap build linux-postmarketos-qcom-sdm660 --force`（ccache 命中时 3 分钟）。

### 4.3 部署方式（不需要 fastboot）

```bash
# VM 上：装包进 rootfs → 重新生成 boot.img
pmbootstrap chroot -r -- apk add --allow-untrusted --force-non-repository /tmp/kernel-rN.apk
cp $CHROOT/boot/vmlinuz $CHROOT/tmp/bootout/
pmbootstrap chroot -r -- /usr/sbin/boot-deploy -i initramfs -d /boot -o /tmp/bootout

# 平板：写 boot 分区 + 覆盖模块
dd if=/dev/disk/by-partlabel/boot of=/root/boot-old.img bs=4M      # 备份
dd if=/tmp/boot-rN.img of=/dev/disk/by-partlabel/boot bs=4M conv=fsync
tar -xzf /tmp/modules-rN.tar.gz -C /usr/lib/modules/ && depmod -a 7.0.14-sdm660
```

> `boot-deploy` 要求 `-i` 是 initramfs 文件名、`-d` 是输入目录、`-o` 是**另一个**目录，
> 且 kernel 必须已经在 `-o` 目录里（否则报 `No kernel found`）。

### 4.4 当前结果

```
tas2557 1-004c: PG2.1 left ready: fw 'tas2557_uCDSP.bin' ver=0x1010000 drv=0x400 (3 prog, 6 cfg)
tas2557 1-004e: PG2.1 right ready: fw 'tas2557_uCDSP.bin' ver=0x1010000 drv=0x400 (3 prog, 6 cfg)
card 0: X4 [Xiaomi Mi Pad 4], device 0: MultiMedia1
```

- 两颗芯片 I2C 通了、固件解析成功
- 声卡注册成功、`INT0_MI2S_RX Audio Mixer MultiMedia1 = on`
- `speaker-test -D hw:0,0` 能跑完，**但听不到声音**
- 播放时两颗芯片的寄存器成片变化（说明 hw_params/enable 路径被调用）

**待查（按可能性排序）**：

1. **I2S 无数据**：主 MI2S 的 pin mux 由 ADSP 固件负责，mainline 的 `INT0_MI2S_RX` 是否真的把
   数据送到 `pri_mi2s` 引脚？可在播放时读 TAS2557 的 ASI 状态/时钟错误位。
2. **位宽/时钟不匹配**：下游 `i2s-bits=16`，驱动默认按 32-bit word（`asi_offset` 用 32 计算）；
   右声道 offset 公式 `1 + width*2` 在 16-bit 时是 33、在 16-bit 正确值应是 17 —— 可能整体错位。
3. **DAPM 未上电**：驱动的 `OUT` widget 是否真的 power up（`/sys/kernel/debug/asoc/.../dapm`
   只有 `bias_level`，说明内核没开 `CONFIG_SND_DEBUG`，看不到 widget 状态）。
4. **供电**：`vreg_l6b_3p3` 是否真的给功放供电（下游是常开 `cdc-vdd-spkdrv`）。

### 4.5 下一步诊断脚本（设备回来后）

```bash
# 1) 看功放是否被 enable（动态调试，模块名是 snd_soc_tas2557，不是 tas2557）
echo 'module snd_soc_tas2557 +p' > /sys/kernel/debug/dynamic_debug/control
speaker-test -D hw:0,0 -c 2 -t sine -f 440 -l 1 &
dmesg | grep -i tas2557

# 2) 强制 16-bit / 44.1k 播放
aplay -D hw:0,0 -f S16_LE -r 44100 -c 2 /usr/share/sounds/alsa/Front_Center.wav

# 3) 读功放关键寄存器（regmap debugfs）
cat /sys/kernel/debug/regmap/1-004c/registers | head -40

# 4) 如果 INT0 不通，试 INT1：在 DTS 里把两个 codec 换到 int1 link（需要再编译）
```

---

## 五、GPU / 黑屏（重要教训）

### 5.1 glamor 必挂

把 `50-msm-soft.conf` 移走（启用 glamor）后：

```
[drm:a5xx_irq] *ERROR* gpu fault ring 0 fence ffffff00 status 800001C1
[drm:adreno_idle] *ERROR* 5.1.2.0: timeout waiting to drain ringbuffer
[drm:recover_worker] *ERROR* 5.1.2.0: hangcheck recover!
```

随后 X 无响应、`glxinfo` 卡死、`systemctl reboot` 也走不完，设备彻底离线（需长按电源）。
**结论：本机任何时候都不要开 glamor**，竖屏也一样。已把 `50-msm-soft.conf` 放回。

### 5.2 开机即横屏 → DPU 提交超时 → 黑屏

23:15 那次重启（`/etc/tablet/landscape` 存在，会话启动时 `xrandr --rotate left`）后：

```
[drm:dpu_encoder_phys_vid_wait_for_commit_done] [dpu error]vblank timeout: 1000000
[drm:dpu_kms_wait_for_commit_done] [dpu error]wait for commit done returned -110
```

面板无输出（背光 255、DRM 报 enabled、framebuffer 有内容），用户看到黑屏。
竖屏启动（landscape 标志改名 `landscape.off`）则 0 条报错、显示正常。

**当前状态**：`/etc/tablet/landscape` 已改名为 `landscape.off`，开机竖屏。

**待办**：搞清楚横屏为什么触发 DPU 提交超时（是启动时旋转太早？还是旋转本身？），
再决定横屏怎么用。触摸矩阵已经会自动跟随，不需要重启会话。

### 5.3 性能

llvmpipe + 1920×1200 很吃力。已做：关 xfwm4 合成器。
待做：纯色壁纸、必要时降分辨率、检查 cpufreq 是否存在。

---

## 六、本轮文件清单

### 平板

```
/usr/local/bin/tablet-touch-rotate              新增
/etc/systemd/system/tablet-touch-rotate.service 新增
/lib/firmware/tas2557_uCDSP.bin                 新增（39615 B）
/etc/systemd/system/tablet-autobright.service   删除 ConditionPathExists
/usr/local/bin/xfce-tablet-session              onboard 自动启动关闭
/etc/xdg/menus/gnome-applications.menu          软链（修菜单报错）
~/.config/autostart/{nm-applet,blueman-applet}.desktop  新增
~/.config/xfce4/.../xfce4-panel.xml             plugin-ids 12 项、plugin-1=whiskermenu
/root/boot-old.img, /root/boot-r4.img           boot 分区备份（64 MB）
/etc/tablet/landscape → landscape.off           临时：竖屏启动
```

### 构建机（VM）

```
pmaports/.../linux-postmarketos-qcom-sdm660/
  APKBUILD                                      pkgrel=5，新增 0002/0003 补丁
  0002-arm64-dts-...-tas2557.patch
  0003-ASoC-tas2557-unique-control-and-DAI-names-per-instance.patch
~/boot-r5.img, ~/modules-r5.tar.gz              已部署到平板的版本
```

### Windows 侧

```
tools/tablet-touch-rotate                源码
tools/boot-r5.img, tools/modules-r5.tar.gz
tools/pad_*.sh, tools/vm_*.sh            本轮诊断/操作脚本
```

---

## 七、2026-10-25 00:20 更新 —— 扬声器修好、UCM、性能实测

### 7.1 扬声器无声的真正根因（已修好）

不是驱动问题，是**接线映射**：

1. 同平台的 `sdm660-xiaomi-jasmine.dts` / `sdm636-xiaomi-tulip.dts` 里，TAS2557 挂在
   **`PRIMARY_MI2S_RX`** 上，并有一条独立的 `pri-mi2s-dai-link`；
   我们一开始错误地把它加进了 `int0-mi2s-dai-link`（内部 MI2S）。
2. 主线 `sdm630.dtsi` **完全没有 MI2S 引脚复用**，下游 DTS 里 `pri_mi2s` 用的是
   gpio12（sck）/ gpio13（ws）/ gpio14、15（data）。没有 pinmux，SoC 就不会在 I2S 线上输出。

修复（`0002-...clover-tas2557.patch` 重写）：

```dts
&q6afedai { dai@16 { reg = <PRIMARY_MI2S_RX>; qcom,sd-lines = <0>; }; };

&sound {
    pinctrl-0 = <&cdc_pdm_default>, <&cdc_dmic_default>, <&pri_mi2s_active>;
    pri-mi2s-dai-link {
        link-name = "Primary MI2S Playback";
        cpu  { sound-dai = <&q6afedai PRIMARY_MI2S_RX>; };
        codec{ sound-dai = <&tas2557_left>, <&tas2557_right>; };
    };
};

&tlmm {
    pri_mi2s_active: pri-mi2s-active-state {
        sck-pins  { pins = "gpio12"; function = "pri_mi2s"; };
        ws-pins   { pins = "gpio13"; function = "pri_mi2s_ws"; };
        data-pins { pins = "gpio14", "gpio15"; function = "pri_mi2s"; };
    };
};
```

> **注意**：pinctrl 节点必须放在独立的 `&tlmm { ... };` 块里，
> 不能插在原有 `&tlmm` 的属性前面，否则 dtc 报
> `Properties must precede subnodes`。

验证（播放时 dmesg）：

```
tas2557 1-004c: PLL locked, power-up OK (FLAG=0xfc F1=0x02 F2=0x02)
tas2557 1-004c: amplifier powered on (prog=0 cfg=0)
```

`F1 & 0x04` 才是 clock error，0x02 是正常状态位。

### 7.2 ALSA UCM（PulseAudio 自动切扬声器/耳机）

`/usr/share/alsa/ucm2/Xiaomi/clover/HiFi.conf` 原来只认识 INT0 + 耳机，导致 PulseAudio
在会话启动时把 `PRI_MI2S_RX` 关掉 → 扬声器又没声。重写为两个输出设备：

| 设备 | 路由 | 优先级 |
|---|---|---|
| `Speaker`（Built-in Speakers (TAS2557)）| `PRI_MI2S_RX Audio Mixer MultiMedia1 1` + 功放音量 15 | 200 |
| `Headphones`（3.5mm）| `INT0_MI2S_RX Audio Mixer MultiMedia1 1` + HPHL/HPHR | 100（JackControl=Headset Jack）|

重启 PulseAudio 后：

```
活动配置：HiFi (Mic, Speaker)
[Out] Speaker: Built-in Speakers (TAS2557) (type: 扬声器, priority: 200)
sink: alsa_output.platform-sound.HiFi__Speaker__sink
route: PRI_MI2S_RX Audio Mixer MultiMedia1 = on
```

**PulseAudio 没有 systemd 单元**（`pulseaudio --start` 自启），改 UCM 后要
`pulseaudio -k && pulseaudio --start` 才会重新读取。

### 7.3 横屏：改成"会话起来后再转"

早期会话脚本在 `startxfce4` **之前**就 `xrandr --rotate left`，这就是 23:15 那次
开机黑屏的原因（DPU 提交超时且卡死）。现在：

- 早期旋转删除，只记日志
- 新增延迟旋转：`sleep 15` 后转 left（在 `xfce-tablet-session` 的 detached 块里）
- 实测 `systemctl restart greetd` 后能正常进入 1920×1200 横屏，X 存活，桌面正常

### 7.4 性能实测（关键）

| 场景 | 帧率（glxgears）|
|---|---|
| 竖屏 1200×1920（无旋转）| **121 FPS** |
| 180° 旋转 | 32 FPS |
| 90° 旋转（横屏，left/right）| **16 FPS** |
| 横屏 + 600×400 窗口 | 5.8 FPS |

- 瓶颈不是 llvmpipe 填充，而是 **Xorg 的单线程软件 90° 转置**：横屏时 `Xorg` 稳定 98% CPU。
- 试过并否定：
  - `--scale-from`（DPU 硬件缩放）：旋转下不支持，产生 2560×625 和大量 vblank 超时
  - `-depth 16`：应用仍用 24 位视觉，反而多一层转换
  - glamor + `kms_swrast`：Mesa 仍然选中真实 fd512 GPU → 立即 `a5xx ring fault`
  - TearFree：无明显收益（保留，至少不撕裂）
- 已做：关合成器、纯色壁纸（减少整屏重绘）
- 若要真正解决，只有两条路：给 xorg-server 的旋转做 SIMD/分块优化，或找到 DPU 平面旋转的用法

### 7.5 当前生效配置

```
/etc/tablet/landscape                    存在（开机延迟 15s 转横屏）
/etc/X11/xorg.conf.d/50-msm-soft.conf     AccelMethod none + TearFree
~/.config/autostart/{nm-applet,blueman-applet}.desktop
/usr/share/alsa/ucm2/Xiaomi/clover/HiFi.conf   新版（Speaker + Headphones）
/etc/systemd/system/tablet-audio-route.service 开机兜底路由
/etc/systemd/system/tablet-touch-rotate.service
/etc/systemd/system/tablet-autobright.service
```