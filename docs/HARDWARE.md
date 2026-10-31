# 硬件逐个说明：怎么解决的 / 为什么还没解决

> 每一项都包含：**现象 → 排查 → 解决步骤（可复现）→ 遗留问题或未解决根因**。
> 命令默认在设备上以 `zhoulei` 执行，需要 root 的地方写 `sudo`。

---

## 1. 显示（DSI / Novatek NT51021）

**状态：✅ 可用**

- 面板原生是**竖屏 1200×1920**，桌面靠旋转 90° 变成 1920×1200 横屏。
- 驱动：`panel_novatek_nt51021` + `msm`/`dpu`。

**解决步骤**

1. 设备树启用 `dsi0` + panel 节点（sdm660-mainline 已有）。
2. 旋转：`wlr-randr --output DSI-1 --transform 90`（由 `tablet-rotate` 统一管理）。
3. 防运行时挂起死锁：

```sh
# 服务 tablet-pin-mdss.service
for d in /sys/bus/platform/devices/*.dsi; do echo "$d" > /sys/bus/platform/drivers/msm_dsi/bind 2>/dev/null; done
```

**遗留问题**

- 开机时若在显示管线未就绪前就做旋转/叠加，会撞上 GPU 提交问题（见第 3 节）。

---

## 2. 触摸（Goodix GT9xx）

**状态：✅ 可用（但必须与旋转严格同步）**

**现象**：点击位置整体偏移 90°/180°。

**根因**：面板原生竖屏 + 输出旋转 90°，触摸坐标需要经
`LIBINPUT_CALIBRATION_MATRIX` 与输出变换配合；矩阵算错就镜像/旋转。

**解决步骤**

```sh
# /etc/udev/rules.d/99-goodix-landscape.rules
ATTRS{name}=="Goodix Capacitive TouchScreen", ENV{LIBINPUT_CALIBRATION_MATRIX}="0 -1 1 1 0 0 0 0 1"
```

对应 `x' = 1 - y`、`y' = x`。改完必须**重启会话**（libinput 只在打开设备时读矩阵）。

标定方法（实测法）：
1. 让用户点四个角，记录"点哪里 → 响应在哪"；
2. 若整体旋转 90°/180°/镜像，就组合出逆变换矩阵；
3. `tablet-touch-matrix 90|270|normal|180` 可直接切换四套正确矩阵。

**联动**：`平板设置 → tablet-rotate → tablet-touch-matrix`，
**旋转和矩阵必须由同一个调用同时设置**。开机由 `tablet-rotate-restore`
（等 Wayland socket + 校验 + 重试）恢复。

**遗留问题**

- 若有人单独执行 `wlr-randr --transform N`，矩阵不会跟着变 → 立刻错位。

---

## 3. GPU（Adreno 512 / a512）

**状态：🔧 可用，但必须加固**

**现象**（三种，同一个根因）

1. 整机硬死，SSH 也不响应；
2. 黑屏但有背光（hangcheck 恢复后显示没回来）；
3. 画面/控件闪烁、文字乱码。

**日志特征**

```
[drm:adreno_idle] timeout waiting to drain ringbuffer 0
msm_dpu: CP | opcode error | possible opcode=0x00000000
gpu fault ring 0 ... ib1 000000000A4DB000/0000     ← IB 长度为 0
[drm:hangcheck_handler] hangcheck detected gpu lockup rb 0!
[drm:recover_worker] offending task: labwc
```

**根因**：内核是**下游（Android 风格）msm 驱动**，用户态是**上游 Mesa/freedreno**。
上游 Mesa 使用较新的命令缓冲特性（可增长 cmdstream、硬件间接绘制），
下游内核处理不一致 → 提交长度 0 的 IB → CP 取到空 opcode → 卡死。

**注意**：这不是"缺 zap 固件"。内核明确打印
`Zap shader not enabled - using SECVID_TRUST_CNTL instead`，
说明 bootloader 已设好安全位，驱动走的是正常分支。

**解决步骤（四层，缺一不可）**

```sh
# 1) 内核参数（msm 是内置模块，modprobe.d 无效，必须用服务写 sysfs）
#    /usr/local/bin/tablet-gpu-harden
/sys/module/msm/parameters/enable_preemption = 0
/sys/module/msm/parameters/enable_eviction    = 0
/sys/bus/platform/devices/5000000.gpu/power/control = on
#    由 tablet-gpu-harden.service 在 graphical.target 之前执行

# 2) Mesa 关闭危险命令缓冲路径（会话环境）
export FD_MESA_DEBUG=nogrow,noindirect,sysmem

# 3) 不要使用 WLR_DRM_NO_MODIFIERS=1（会让画面闪烁/错位）

# 4) Firefox 必须原生 Wayland（走 XWayland 会闪烁）
export MOZ_ENABLE_WAYLAND=1 GDK_BACKEND=wayland
```

**验证**

```sh
journalctl -b -1 | grep -icE "adreno_idle|opcode error|hangcheck|gpu fault"   # 期望 0
```
实测：哔哩哔哩连续播放 **10 分钟，0 次错误**（修复前约 4 分钟必挂）。

**未解决的部分**

- 这颗 GPU 仍然**不能跑满性能**：`sysmem` 关掉了分块渲染，3D 性能有损失；
- 根治需要**内核与 Mesa 版本对齐**（换上游 msm 内核，或降级 Mesa 的命令缓冲特性）；
- 没有 zap 意味着 GPU 运行在 bootloader 设定的模式下，无法自行重初始化。

---

## 4. 视频硬解（Venus）

**状态：✅ 可用（mpv）｜❌ 浏览器用不上**

**解决步骤**

```sh
apk add mpv yt-dlp
mpv --hwdec=v4l2m2m --vo=dmabuf-wayland <文件或 URL>
yt-dlp -g <bilibili URL> | xargs -I{} mpv --hwdec=v4l2m2m {}
```

**未解决原因**

- Firefox/Chromium 只支持 **VA-API**，而 Venus 在内核里是 **V4L2 stateless/m2m**，
  两者不通用 → 浏览器永远走软件解码（CPU 占用 ~200%）。

---

## 5. Wi-Fi（WCN3990 / ath10k_snoc）

**状态：🔧 可用，但受调制解调器影响**

**解决步骤**

1. 固件 `qcom/wlan-*.mbn` + `ath10k` 固件放入 `/lib/firmware`；
2. 设备树 wlan 节点 + `wlan-msa-guard` 保留内存；
3. 关闭会拖垮 Wi-Fi 的东西（见第 10 节 modem）。

**未解决原因**

- **调制解调器 assert 会把 Wi-Fi 一起带走**（同一套 remoteproc/PD 资源），
  所以本项目长期让 modem 处于 `shutting-down` 状态。

---

## 6. 蓝牙（WCN3990 / btqca）

**状态：✅ 可用**

```sh
apk add bluez
rc-service bluetooth start   # 或 systemctl enable --now bluetooth
bluetoothctl power on
```
固件：`qcom/htbtfw20.tlv`、`qcom/htnv20.bin`。

---

## 7. 音频（PM660 WCD + TAS2557）

**状态：✅ 可用**

**解决步骤**

1. 设备树 sound 卡 + `q6afe/q6asm`（ADSP）通路；
2. ACDB 参数（`/vendor/etc/acdbdata` 提取）放到 `/lib/firmware/qcom/`；
3. 用 **PulseAudio**（PipeWire 在这台机器上没有可用节点）：

```sh
# /etc/pulse/daemon.conf
default-sample-rate = 48000
avoid-resampling = yes
resample-method = speex-float-1
default-fragments = 8
default-fragment-size-msec = 20
```

4. 扬声器通路：`tablet-audio-mixer.service` 恢复 RX3 路由此类 mixer 设置。

**遗留问题**

- 高负载时仍可能有轻微爆音（CPU 抢占导致音频欠载），已通过加大缓冲缓解。

---

## 8. 充电 / 电量计

**状态：✅ 可用**

- 主充 `qcom_smbx`（SMB2），并充 `smb135x`，电量计 `pmi8998_fg`。
- 设备树需要正确配置 `buck-boost`（补丁 `0010`）。

```sh
cat /sys/class/power_supply/qcom-battery/capacity
```

---

## 9. USB-C / OTG 角色切换

**状态：🔧 可用，但硬复位后失效**

**解决步骤**

- 读 SMB2 的 `typec_status` + `otg_vbus`，用守护脚本轮询 CC 状态并切换角色：

```sh
# /usr/local/bin/pad_usb_autoswitch  （每 2 秒）
# 检测到 UFP(Rd) -> 充电；检测到 DFP -> 开 otg_vbus 供电给外设
```

**未解决原因**

- **长按电源硬复位后，SMB2 的 CC 检测读不到任何东西**（`dfp=0`，
  强制 `otg_vbus=1` 也不枚举），必须**重启一次**才恢复。
  属于 PMIC/USB-C 状态在硬复位后不一致，软件层没有可靠的复位手段。

---

## 10. 调制解调器 / LTE

**状态：⚠️ 能注网，但不可长期运行**

**现象**：`qmicli` 能读到 SIM、能注册到 CMCC（RSSI ≈ -62 dBm），
但 **约 3 分钟后 modem 侧 assert**，并且把 Wi-Fi 一起带崩。

**排查结论**

- `qmi_helpers` + `qcom_q6v5_mss` 能加载固件、能建 QRTR 通道（`qrtr://0`）；
- 崩溃来自 modem 固件内部 assert（PDR 通知），不是主机侧驱动错误；
- **缺 SDM660 的 IPA 驱动**（主线没有），数据面无法正常工作。

**目前的处理**

- 让 modem 保持离线（`qmicli --dms-set-operating-mode=offline` 后停止服务），
  换取 Wi-Fi 稳定；
- 不要 `remoteproc` 重启 modem（会杀掉 Wi-Fi）。

**未解决原因**：主线缺少 `ipa`（SDM660 版本）驱动 + modem 固件 assert 无法规避。

---

## 11. GPS

**状态：⚠️ 有响应，无定位**

- QMI `LOC` 服务能连上、能下发启动定位请求；
- 但**从未拿到 fix**；且测试需要 modem 在线，而 modem 会崩。

**未解决原因**：缺少可用的 GNSS 数据通路（依赖 modem 的 NMEA/QMI LOC 上报），
叠加第 10 节问题，属于被动阻塞。

---

## 12. 后摄（OV13855）

**状态：✅ 可用（自研预览程序）**

**解决步骤**

1. 设备树启用 `qcom_camss` + CCI + CSIPHY；
2. 用 V4L2 直接采集 raw bayer（`/dev/video*`）；
3. `tablet-camera-gui` 做 ISP（去马赛克/白平衡/伽马）并显示。

**遗留问题**

- 不是标准相机栈（libcamera 不认这条 raw-bayer 管线），所以
  GNOME Snapshot 之类的应用用不了。

---

## 13. 前摄（S5K5E8）

**状态：❌ 未解决**

- 电源、时钟、复位都验证过（在 Android 下同一颗 sensor 正常出图）；
- 但**在 CCI 上始终没有 ACK**（`i2c` 读 ID 超时）；
- 怀疑：上电时序（mclk/regulator 先后）、或 CCI 与后摄共用时的仲裁。

**未解决原因**：需要在硬件层面用示波器核对上电时序，软件侧无法进一步推进。

---

## 14. 指纹（FPC1020）

**状态：❌ 未解决**

- `fpc1020` 驱动能让传感器上电、能读中断；
- 但**指纹成像与匹配在闭源的 TEE TA 里**（Android 侧 `fpc*` TA），
  主线没有对应 TA，也没有公开的算法。

**未解决原因**：闭源 TEE 可信应用，缺乏文档与固件接口。

---

## 15. 传感器（accel / gyro / mag / 环境光 / 霍尔）

**状态：✅ 可用**

**解决步骤**

1. `qcom_smgr` 驱动直读 ADSP 传感器（不走 iio-sensor-proxy）；
2. 加速度计用于自动旋转（`tablet-orientd`，读 `/dev/iio:device2` + 挂载矩阵）；
3. 环境光用于自动背光（`tablet-autobright`，ALS → 亮度曲线）。

```sh
# 自动旋转开关
tablet-rotate auto | lock
# 自动背光
systemctl status tablet-autobright
```

---

## 16. 电源键 / 音量键 / 锁屏

**状态：✅ 可用**

**为什么要自研**：logind 的 `HandlePowerKey` 行为固定（关机/挂起），
而平板需要"短按关屏 + 长按 3 秒出关机菜单 + 音量键调音量"。

**解决步骤**

1. `logind.conf`：`HandlePowerKey=ignore`、`HandleSuspendKey=ignore` 等；
2. `/usr/local/bin/tablet-powerkeyd` 直接读 `/dev/input/event*`：
   - 短按 → `tablet-pinlock` 锁屏 + 关背光
   - ≥3 秒 → `lxqt-leave`（关机菜单）
   - 音量键 → `pactl set-sink-volume ±5%`（200 ms 防抖）
3. 锁屏：`tablet-pinlock`（GTK4 layer-shell，自带屏幕键盘，
   PAM 校验账户密码）。**不要用 gtklock**：它的 `ext-session-lock`
   会把所有第三方屏幕键盘挡在外面，没键盘就解不开。
4. `tablet-sleep`：伪睡眠（关背光 + 停帧），`/run/tablet-sleep.saved` 记录状态。

**遗留问题**

- 真 suspend 仍然不可用（见第 19 节）。

---

## 17. 屏幕键盘 + 中文输入

**状态：✅ 可用**

```sh
# 屏幕键盘（wvkbd，桌面图标「屏幕键盘」）
/usr/local/bin/tablet-keyboard

# 中文输入法
apk add fcitx5 fcitx5-chinese-addons
# 会话环境：GTK_IM_MODULE=fcitx QT_IM_MODULE=fcitx XMODIFIERS=@im=fcitx
fcitx5-remote -o     # 切到 pinyin
```

锁屏里另有一套自带键盘（`tablet-pinlock` 的 QWERTY 页），
因为它跑在 layer-shell 上、无法依赖输入法协议。

---

## 18. 自动旋转

**状态：✅ 可用**

- `tablet-orientd` 读加速度计 → 判定方向 → **同时**设输出变换与触摸矩阵；
- 关键修复：`wlr-randr` 失败时**不许再改矩阵**（否则错位），
  且 `0°` 要正确映射为 `normal`；
- 开机用 `tablet-rotate-restore` 恢复用户上次的选择（带等待与校验）。

---

## 19. 深度休眠（suspend）

**状态：❌ 不可用（已用伪睡眠替代）**

- 真 suspend 会在 `mdss_runtime_suspend` 处死锁（显示控制器），
  唤醒后黑屏/死机；
- 现有方案：`tablet-sleep` 关背光 + 停止渲染，按键即醒（毫秒级）。

**未解决原因**：需要内核 DPU/DSI 运行时电源管理的修复（上游仍在演进）。

---

## 20. 存储

**状态：✅ 可用**

- eMMC：`/dev/mmcblk1`，根分区 `p64`（`/`）；
- SD 卡：`sdhci` 挂载读写正常。

---

## 附：一键安装

```sh
sudo ./install.sh     # scripts + services + udev + 桌面配置
sudo reboot
```
