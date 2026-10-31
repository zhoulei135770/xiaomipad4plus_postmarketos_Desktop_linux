# NEXT-SESSION · 小米平板 4 Plus (clover-plus) 交接

> **更新时间：2026-10-27 07:30**
> 本轮发生了**两次刷机事故**（都已恢复），并且查清了一个**比前摄更重要的问题**：
> **VM 上的编译环境已经编不出能启动的内核了。先读第 0 节。**

---

## 0. 最重要的事：换内核必须同时换整套模块（**已实测纠正**）

### 结论
之前判断"编译环境坏了"是**错的**。真实原因是：
**刷了新内核，但 rootfs 里的 `/usr/lib/modules` 还是旧内核编的模块。**

- 模块的 `vermagic` 只含 release（`7.0.14-sdm660 SMP preempt mod_unload aarch64`），**不含 build 号**
- 所以旧模块照样会加载，然后在内核里踩到布局/内联变化 → 黑屏、无网络、无法唤醒
- 一旦把**同一个 apk 里的整套 638 个模块**装进 rootfs，新内核立刻正常启动

### 证据（2026-10-27 实测）
| 组合 | 模块 | 结果 |
|---|---|---|
| r148（#149） | r143 旧模块 | ❌ 卡死 |
| **r148（#149）** | **r148 整套 638 个模块** | ✅ **启动，全部硬件正常** |
| **r151（#152）** | **r151 整套模块** | ✅ **启动**（venus + 前摄供电版）|

### 正确流程（**铁律**）
```powershell
# 1) VM 上编译
python tools\ssh_vm.py 'setsid nohup sh ~/vm_build.sh NNN > /tmp/buildNNN.log 2>&1 &'
# 2) 拉 boot 镜像 + 内核 apk
python tools\getb.py NNN
python tools\get_vm.py /home/user/.local/var/pmbootstrap/packages/edge/aarch64/linux-postmarketos-qcom-sdm660-7.0.14-rNNN.apk tools\_kernel-rNNN.apk
# 3) 设备上装匹配模块（会自动备份旧模块到 /var/backup/）
python tools\put_pad.py tools\_kernel-rNNN.apk /tmp/kernel-rNNN.apk
python tools\put_pad.py tools\pad_install_modules.sh /tmp/install_modules.sh
python tools\ssh_pad.py 'P=<SUDO_PASSWORD>; echo $P | sudo -S sh /tmp/install_modules.sh /tmp/kernel-rNNN.apk'
# 4) 刷 boot（systemd-run，写后校验 md5）
python tools\put_pad.py tools\flash_boot.sh /tmp/flash_boot.sh
python tools\put_pad.py tools\boot-rNNN.img /tmp/boot-rNNN.img
python tools\ssh_pad.py 'P=<SUDO_PASSWORD>; echo $P | sudo -S systemd-run --unit=flash --collect sh /tmp/flash_boot.sh /tmp/boot-rNNN.img <size>'
# 5) 校验后再 reboot（首次启动可能慢，等 3-5 分钟）
```

### 卡死后的恢复（不变）
长按电源 10 秒 → 音量下+电源进 TWRP → 
`python tools\recover_boot_adb.py tools\boot-r143.img 25812992`
（push→dd→双端 md5→通过才 reboot）

### 仍然成立的两条
1. **绝不在写 boot 分区时中断**（用 systemd-run）
2. kexec 不可用（缺 `/proc/kcore` → VA_BITS 未知 → 一执行就黑屏）

---

## 1. 当前设备状态（2026-10-27 07:30 实测）

| 项 | 值 |
|---|---|
| 地址 | `192.168.1.29`，用户 `user`，密码 `<SUDO_PASSWORD>` |
| 当前 boot | **r151**（内核 #152，含 0039 前摄供电 + 0040 venus 时钟；`tools/boot-r151.img`）|
| 当前模块 | r151 整套 638 个（`/var/backup/modules-7.0.14-sdm660.orig.tar` 是旧模块备份）|
| 状态 | ✅ 已启动、稳定 |
| 后摄 | ✅ `/dev/video0` 无回归 |
| 前摄 | ❌ 仍然 NACK（见第 2 节）|
| **venus** | ⚠️ 已注册且有 441.6 MHz 时钟，但 **REQBUFS 仍超时**（固件未起，见第 4 节）|
| **OTG** | ✅ **已修**：`tablet-otg.service` 条件写错导致 5V 从不打开（见第 5 节）|
| 指纹 | ✅ 驱动 + 取像协议全通 |
| 4G 模组 | ✅ 固件 + QMI + 自启 |
| 4G 数据 | ❌ 缺 IPA（mainline 公共缺口）|
| 休眠 | ⚠️ 进入可以，唤醒未验证；已装禁止自动休眠配置 |

体检（`sudo pad_hwstatus.sh`）：除前摄/ALS 状态脚本误报/venus/移动数据外全部 OK。

---

## 2. 前摄 S5K5E8：本轮查到的全部事实

### 已经做的（本轮新增）
用 **r143 内核 + 只改设备树**（补丁 0039 的等价改动，绕开坏编译环境）启动后实测：

```
cam_avdd_front_2v8   state=enabled  users=1     ← tlmm 49 拉高
cam_front_dvdd_1v8   state=enabled  users=1     ← pm660l gpio3 拉高 + l13 使能
pm660_l11            state=enabled  users=3     ← VIO 1.8V（与后摄共用）
pm660_l13            state=enabled  users=3
tlmm gpio38/39       in high func1(cci_i2c) pull up   ← CCI master1 总线空闲高电平
MCLK2                24000000 Hz 已使能
reset (gpio52)       已释放（logical=0）
```

**结果：bus 4（CCI master 1）从 0x08 到 0x77 全部 NACK；bus 3（后摄）ACK 0x50/0x58。**
`s5k5e8` probe 因 `-6 (ENXIO)` 失败，失败得干净（不再卡死）。

### 关键对照：Android 侧是能 probe 成功的
```
[7.573798] msm_camera_power_up: 1523 usr_idx:3 dts_idx:3
[7.645263] s5k5e8 probe succeeded
```
而且 `reg-after.txt` 显示当时：
```
cam_avdd_front_gpio_regulator  use=0（关）
cam_vadd / cam_vaf             use=0
pm660_l11  → ca0c000.qcom,cci:qcom,camera@2  1800mV  ← 只有 VIO 是开的
```
⇒ **I2C 应答只需要 VIO(1.8V)，不需要 VANA/VDIG。**

### 因此现在最可能的原因（按概率）
1. **VIO 没真正到模组**：l11 是 1.8V 且 enabled，但模组侧可能还有一级开关/排线问题
2. 模组排线松/断，或模组本身损坏
3. CCI master1 的两条线（gpio38/39）到模组座断路

**下一步必须做物理测量**（这是唯一剩下的关卡）：
```bash
# 先手动把电都打开（脚本已修好 ioctl）
sudo python3 pad_campower2.py high
```
量前摄排线座（竖屏朝上、顶部中间偏左）：
| 信号 | 期望 | 说明 |
|---|---|---|
| VIO / DOVDD | **1.8 V** | 来自 pm660_l11，**最关键**（Android 证明只靠它就能 ACK）|
| VANA / AVDD | 2.8 V | tlmm 49 开关，来自 pm660l_l3/bob |
| VDIG | 1.8 V | l13 + pm660l gpio3 |
| RESET | 1.8 V | gpio52 |
| MCLK | 直流约 0.9 V（24MHz 方波）| gpio33 |

若 VIO 有 1.8V 但 I2C 仍无应答 ⇒ 模组或排线问题（对照法：量后摄座同位置）。

---

## 3. 设备树手术工具（不重编内核就能改 DT）

这轮新写的一套工具，**以后改 DT 一律用它们**（因为内核不能重编）：

| 工具 | 作用 |
|---|---|
| `tools/fdt_dump.py <boot.img\|dtb> [节点名...]` | 解析并打印 DTB 节点/属性（自写 FDT 解析器，无依赖）|
| `tools/bootinfo.py <boot.img...>` | 打印 Android boot 头（kernel/ramdisk 大小、cmdline）|
| `tools/boot_cmdline.py in out --drop "quiet splash" --append "console=tty0"` | 改启动参数（黑屏取证用）|
| `tools/kexec_prep.py <boot.img> <outdir>` | 拆出 Image / dtb / initrd |
| `tools/boot_swap_dtb.py <内镜像> <dtb文件或镜像> <out> [--debug-cmdline]` | 换设备树（或换内核）重打包 |
| `tools/dtb_edit.py <in> <out> --set-status <节点>=<值>` | 改节点状态 |
| `tools/dtb_add_frontcam.py <in.dtb> <out.dtb> --enable` | 加前摄两路电 + 打开 camera@10 |
| `tools/dtb_gpio_scan.py <img> <引脚...>` | 查某引脚被哪些节点引用（查冲突）|
| `tools/flash_boot.sh <img> <size>` | 设备端 dd + md5（**配合 systemd-run 用，禁止前台中断**）|
| `tools/recover_boot_adb.py <img> <size>` | TWRP 里 adb 恢复 boot（push→dd→md5→reboot）|

### 标准流程（已验证）
```powershell
# 1) 从 r143 的 DTB 生成"加前摄供电"版本
python tools\kexec_prep.py tools\boot-r143.img tools\_kexec143
python tools\dtb_add_frontcam.py tools\_kexec143\dtb tools\_dtb-front.dtb --enable
# 2) 用 r143 内核 + 新设备树打 boot 镜像
python tools\boot_swap_dtb.py tools\boot-r143.img tools\_dtb-front.dtb tools\boot-r143-front.img
# 3) 运行中的设备上安全刷写（systemd-run，写不中断）
python tools\put_pad.py tools\boot-r143-front.img /tmp/boot.img
python tools\ssh_pad.py 'P=<SUDO_PASSWORD>; echo $P | sudo -S systemd-run --unit=flash --collect sh /tmp/flash_boot.sh /tmp/boot.img <size>'
# 4) 校验 md5 后再 reboot
```

---

## 4. venus（硬件视频编解码）：时钟修好了，固件还是没起

补丁 0040（`assigned-clocks = <&mmcc VIDEO_CORE_CLK_SRC>; assigned-clock-rates = <518400000>;`）
生效后实测（r151）：

```
/dev/video6  Qualcomm Venus video decoder   （NV12 / Q08C）
/dev/video7  Qualcomm Venus video encoder   （H264 / VP8 / HEVC / MPG4 / H263）
video_core_clk = 441600000      ← 驱动按模式表选的档位（原来是 19.2 MHz）
video_ahb_clk  = 80799990
video_axi_clk  = 0              ← 仍是 0
genpd: venus on / venus_core0 off-0   ← 核心电源域仍然没上电
REQBUFS → -1 (Operation timed out)    ← 与 r135 一样的失败点
```

**结论：登记+时钟已修，但 `venus_core0` 电源域没人打开、HFI 固件仍不响应。**
下次要查的方向（按可能性）：
1. 谁该给 `venus_core0` 上电（mainline venus 驱动对子设备的 `pm_runtime_get`）
2. DT 里 video-decoder/encoder 的 `power-domains` 现在指向 `rpmpd`（phandle 2, index 1），
   是否应该指向 venus 的 GDSC
3. `video_axi_clk = 0` 是否意味着总线时钟没使能

⚠️ venus 现在是"注册了但一用就超时"，播放器可能选中它然后卡住。
需要稳定日常使用时：`echo cc00000.video-codec > /sys/bus/platform/drivers/qcom-venus/unbind`
（或刷 r148，那份是 venus 禁用的）。

---

## 5. OTG：已修（根因是 systemd 条件写错）

### 症状
插 U 盘/鼠标没反应 —— 因为 **OTG 5V 升压从来没打开**（`otg_vbus = 0`）。

### 根因
`/etc/systemd/system/tablet-otg.service` 里有
`ConditionPathExists=/sys/class/power_supply/pm660-charger`，
而该服务在 charger 设备注册**之前**就执行 → 条件不满足被跳过，且 oneshot 永远不再重跑。
（路径本身是对的；是**时序**问题。）

### 修复（`tools/pad_otg_setup.sh`，已装到设备）
1. service 改为：`After=multi-user.target` + `ExecStartPre` 轮询等待 charger 节点（最多 10 s）
2. 新增 udev 规则 `/etc/udev/rules.d/60-tablet-otg.rules`：
   charger 的 `online` 变化时重跑 `tablet-otg auto`
   - 插着充电器 → 升压关（避免和供电打架）
   - 用电池 → 升压开（U 盘/键鼠才能供电）

### 手动用法
```bash
sudo /usr/local/bin/tablet-otg on|off|status|auto
```
实测：拔掉充电线后 udev 会自动 `otg_vbus=1`；插上充电线自动回 0。

---

## 6. 已知良好镜像

| 文件 | md5 | 说明 |
|---|---|---|
| `tools/boot-r151.img` | `3fe031d099f022ccf2e9934c5afa73a4` | **当前在设备上**：前摄供电 + venus 启用（内核 #152）|
| `tools/boot-r148.img` | `30af1477c279fb56dc74e32099a84cac` | 最稳配置：venus/前摄都禁用（内核 #149）|
| `tools/boot-r143.img` | `23852ba0cbb26fc7d6e39e2932b2016f` | 老基线（内核 #144，必须配 r143 的模块）|
| `tools/boot-r143-front.img` | `2a2894904fc1aeb8eaa69408a099496e` | r143 内核 + 前摄供电 DT（历史）|
| `tools/boot-r47.img` | — | 最早基线 |

**关键：boot 镜像必须和 `/usr/lib/modules` 来自同一个 apk。** 混用必黑屏（见第 0 节）。
切换镜像时先装对应 `_kernel-rNNN.apk` 的模块。

---

## 7. 本轮踩过的坑（都会再踩，记住）

1. **前台 dd 会被工具超时打断** → boot 分区写坏。必须用 `systemd-run` + 写后 md5 校验
2. `python tools\ssh_pad.py '...$P...'` 里的 `$` 会被 PowerShell 吃掉 → 复杂脚本**写成文件 push 上去跑**
   （Windows 上写 shell 脚本必须 LF，`[IO.File]::WriteAllText($p, ($t -replace "\r\n","\n"))`）
3. 设备卡死后**没有 pstore**（这个 DTB 没有 ramoops 节点）→ 拿不到 panic 日志，只能靠二分
4. `modprobe.blacklist=` 放在 cmdline 上对 initramfs 里的 udev 不一定生效
5. TWRP 的 adb 设备号固定是 `27eec4d2`（进入 recovery 后 `adb devices` 可见）
6. **改 DTB 后必须验证没有"悬空 endpoint"**（r108 那次崩溃就是它）：
   `tools/` 里对每条 endpoint 检查 `remote-endpoint`

---

## 8. 下个会话的起点（按优先级）

1. **前摄唯一的关卡**：模组侧的电/连接。软件侧已全部排除（第 2 节），
   没有万用表就只能靠"回 MIUI 试前摄"或看正面镜片来判定模组是否还活着
2. 前摄一旦 ACK：加 media-graph `port@2`（camss port@2 ↔ camera@10 endpoint，2 lane），
   接 CSIPHY2/CSID2，才能出图（DTB 手术即可，不用重编内核）
3. **venus**：查 `venus_core0` 电源域由谁上电（第 4 节），以及 `video_axi_clk=0`
4. **OTG 实测**：拔掉充电线，插 U 盘/鼠标，确认 `otg_vbus=1` 且能枚举、能挂载
   （`udisksctl`/Thunar）；若仍不行再查 xhci 的 port 状态
5. 指纹用户态（取像已通，缺 fprintd 驱动）；4G 数据（IPA，仍是 mainline 公共缺口）

**日常稳定用法**：如果不想被 venus 影响，刷 `boot-r148.img` 并装 r148 模块
（或运行时 `echo cc00000.video-codec > /sys/bus/platform/drivers/qcom-venus/unbind`）。

---

## 9. 文档导航

| 想了解 | 看哪篇 |
|---|---|
| 硬件数据 / 每轮进展 | `HARDWARE-DATA.md` |
| 后摄全过程 | `CAMERA-FINDINGS.md` |
| 前摄测量指南 | `FRONT-CAMERA-MEASURE.md` |
| 补丁说明 | `PATCHES.md` |
| 备份/恢复 | `RESTORE-PROCEDURE.md` |
| 总索引 | `README.md` |

---

## 10. 追加（2026-10-27 08:10）：熄屏/锁屏替代休眠 + 断网自愈

### 为什么不做“整机休眠”
实测（`suspend_test.sh 20`，先设 RTC 闹钟）：
- 休眠**能进**，但 **RTC 闹钟叫不醒**
- 长按电源约 6 秒能唤醒（`Controller resume with wake event`），**不是重启**
- 唤醒后 DHCP 重启失败（`no lease`），WiFi/蓝牙都不会自动回来

⇒ 整机休眠在这台机器上不可用。已：
- `AllowSuspend=no` 写进 `/etc/systemd/sleep.conf.d/`
- `systemctl mask suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target`

### 改成“熄屏 + 锁屏”（CPU/WiFi 都不停）
```
xfce4-screensaver 4.20.2 已安装并配置：
  /saver/enabled true            /saver/idle-activation/enabled true
  /saver/idle-activation/delay 300     ← 空闲 5 分钟熄屏
  /lock/enabled true             /lock/saver-activation/enabled true   ← 熄屏即锁

xfce4-power-manager：
  dpms-enabled true
  dpms-on-ac-sleep 300 / dpms-on-ac-off 600
  dpms-on-battery-sleep 180 / dpms-on-battery-off 420
  inactivity-on-ac/battery 0     ← 永不整机休眠
  power-button-action 0          ← 交给 logind

/etc/systemd/logind.conf.d/50-clover-power-key.conf：
  HandlePowerKey=lock-session    ← 短按电源键 = 锁屏（再按/触摸/键鼠 = 亮屏）
  HandleSuspendKey/HibernateKey/LidSwitch=ignore
```
- 解锁密码 = 账户密码 `<SUDO_PASSWORD>`
- 锁屏守护在 `/etc/xdg/autostart/xfce4-screensaver.desktop`，下次登录自启
- 手动：`xflock4` 立即锁屏；`xfce4-screensaver-command --query` 看状态

### 断网/断蓝牙自愈
`tablet-reconnect.service`（开机后）+ `tablet-reconnect-resume.service`（唤醒后）：
- 若 wlan0 不是 connected，就 `nmcli connection up`（最多 6 次 × 5 s）
- 对每个已配对蓝牙设备尝试 `bluetoothctl connect`（最多 3 轮）
- 日志：`/run/tablet-reconnect.log`

---

## 11. 追加（2026-10-27 08:25）：电源键熄屏 + USB 键盘 + 断网自愈验证

### 电源键 = 熄屏/亮屏（不锁屏）
- `systemd-logind` 在**这一版 systemd 上不接受** `HandlePowerKey=lock-session`
  （日志：`Failed to parse HandlePowerKey=lock-session, ignoring: Invalid argument`）
- 因此写了 `tablet-powerkeyd`（Python，读 `/dev/input/event*` 的 `pm8941_pwrkey`）：
  - 按一下 → `xset dpms force off`（熄屏）
  - 再按一下 → `xset dpms force on`（亮屏）
  - 用 `setpriv --reuid=10000` 降权执行（**不要用 `su -`**：登录 shell 会清掉
    DISPLAY/DBUS，命令会静默失败）
  - 状态判断读 `/sys/class/drm/card*-DSI-*/dpms`（`xset q` 不可靠，永远显示 On）
- **锁屏已关闭**（`/lock/enabled=false`、`/saver/enabled=false`）：
  平板上没有稳定的键盘，密码锁会把人锁死（本轮真实发生过一次，靠 `pkill -f xfce4-screensaver` 救回）
  - 需要锁屏时手动：`xflock4`（有键盘时）；或以后装屏上键盘再启用

### USB 键盘：不是键盘问题，是控制器坏了
- 失败的休眠之后 dmesg 出现 `xhci-hcd: xHC error in resume, USBSTS 0x401, Reinit`
- 此后插任何 USB 设备都**没有枚举中断**；unbind/bind xhci 也救不回来（能重建总线但端口不响应）
- **重启后一切正常**：
  ```
  Bus 001 Device 003: ID c0f4:07c0 USB usb keyboard
  input: USB usb keyboard ... hid-generic ... HID v1.10 Keyboard
  xinput: USB usb keyboard (id=9) [slave keyboard]
  ```
  ⇒ 以后遇到 USB 不认，先重启；别再指望热恢复
- OTG 供电：`otg_vbus=1`（拔掉充电线后 udev 自动打开），`/sys/kernel/debug/usb/*/mode = host`

### 断网自愈验证通过
重启后 `/run/tablet-reconnect.log`：
```
reconnect start
wifi state: connected (try 0)      ← 开机 NM 自己就连上了
bt: trying E5:41:85:7D:29:45       ← 蓝牙鼠标自动重连
```

### 重要教训
1. **不要用整机休眠**（RTC 闹钟叫不醒，还会把 xhci 弄坏）
2. 平板上**不要启用需要密码的锁屏**，除非确认有可用键盘/屏上键盘
3. 复杂"以用户身份执行 X 命令"的脚本：用 `setpriv` + 显式环境变量，不要 `su -`

---

## 12. 追加（2026-10-27 08:35）：venus 深挖结论（需要驱动/固件层，不是设备树）

### 拿到的新事实
1. **开机时看到的 `/dev/video6`/`/dev/video7` 是假象**：bootloader 已经把 venus 固件跑起来了，
   驱动的 `venus_is_valid_state()` 看到"已运行"就跳过了自己加载固件
2. **驱动自己 probe 必定超时**（实测 unbind→bind）：
   ```
   qcom-venus cc00000.video-codec: probe with driver qcom-venus failed with error -110
   ```
   ⇒ `venus_boot()` 里 PAS auth/reset 超时（与 Round 23 一致）
3. **`venus_core0` 电源域之前永远是 `off-0`**。原因：主线的 sdm630.dtsi 里
   `venus` 节点只挂 `<&mmcc VENUS_GDSC>`，`VENUS_CORE0_GDSC` 只挂在 vdec/venc 子设备上，
   而子设备是核心 probe 时才创建 → 鸡生蛋
   - 实验：用 DTB 手术把核心节点改成
     `power-domains = <&mmcc 0>, <&mmcc 1>`（即 VENUS_GDSC + VENUS_CORE0_GDSC）
   - 结果：**`venus_core0` 能上电了**（`on`），这是真实进步
   - 但 `REQBUFS` 仍超时，且 `/proc/interrupts` 里**没有 venus 中断**（GIC_SPI 287）
     ⇒ HFI 从未就绪，固件不响应
4. 结论：venus 要能解码，需要解决 **PAS 固件加载（-110）** + **HFI 中断/握手**，
   属驱动/固件层问题；设备树能做的（时钟、GDSC、memory-region）已经做完

### 当前镜像（稳定）
`tools/boot-r153-stable.img`（md5 `5eb20bf20a876e9beac0439754458937`）
= r148 内核（venus 关闭）+ 前摄供电设备树（camera@10 okay）
- 硬件体检：除前摄（硬件）、venus（驱动缺口）、移动数据（IPA）外全部 OK
- ALS 现在如实报 `OK (CM3232 via IIO buffer)`

### 附：本轮其它改进
- `tablet-reconnect` 里所有 `bluetoothctl` 调用都加了 `timeout`，服务不再长时间 `activating`
- 电源键守护 `tablet-powerkeyd`：按一下熄屏 / 再按亮屏（用 DRM `dpms` 状态判断，不用 `xset q`）

---

## 13. 追加（2026-10-27 08:40）：音频链路实测通过

### 方法（可复现）
```sh
# 必须在用户会话里跑（PulseAudio 在 user 的会话中）
P=$(pgrep -u 10000 -f xfce4-session | head -1)
export XDG_RUNTIME_DIR=/run/user/10000
export DBUS_SESSION_BUS_ADDRESS=$(tr '\0' '\n' < /proc/$P/environ | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p')
export PULSE_SERVER=unix:/run/user/10000/pulse/native
speaker-test -c 2 -t sine -f 440 -l 1     # 播放
arecord -f S16_LE -r 48000 -c 1 -d 3 /run/user/10000/mic.wav
```
> 注意：`/tmp/*.log` 若被 root 写过，普通用户无法覆盖 → 日志写到 `$XDG_RUNTIME_DIR`。

### 结果
| 项目 | 数据 |
|---|---|
| PulseAudio sink | `alsa_output.platform-sound.HiFi__Speaker__sink` |
| PulseAudio source | `alsa_input.platform-sound.HiFi__Mic__source`（未静音，100%） |
| 播放 440 Hz | `rc=0` |
| 安静房间录音底噪 | 峰值 **128** / 32767 |
| 播放 1 kHz 同时录音 | 峰值 **16384** / 32767 ✅ 麦克风正常 |

⇒ 扬声器 + 麦克风 + 采集链路全部正常，不是"只有声卡节点"的假可用。

### 顺带记录
- 用户会话里 `amixer` 的 ADC/DEC 控件都在，但增益默认即可用，无需调整
- 音频测试脚本：`tools/pad_audio_test.sh`、`tools/pad_mic_check.sh`、`tools/pad_mic_loopback.sh`

---

## 14. 追加（2026-10-27 12:10）：venus 精确定位 + RTC 写会挂 + 显示栈 PM 固定

### venus：卡在 HFI SYS_INIT 等回应（不是 PAS）
新证据（本机实测）：
- `hfi.c: #define TIMEOUT msecs_to_jiffies(1000)` —— 与 probe 失败耗时**正好 1 秒**吻合
  ⇒ 失败点是 `hfi_core_init()` 里 `wait_for_completion_timeout(&core->done, 1000ms)`
- 固件**加载成功**（没有 `fail to load video firmware`）；IRQ 已注册并触发过：
  `/proc/interrupts` → `GICv3 319 Level venus`（= SPI 287）
- `use_tz = true`（DT 没有 `video-firmware` 子节点）⇒ 走 **PAS 安全世界**加载
- 时钟：`video_core_clk 441.6M` / `video_ahb_clk 80.8M` / `video_axi_clk 0`
  —— `mdss_axi_clk`、`bimc_smmu_axi_clk` 同样是 0 但显示/IOMMU 正常，
  所以 **axi=0 不是问题**（这类 throttle 分支不报 rate）
- dynamic debug 全开（`module venus_core +p`）后仍只有 `VenusLow : venus hw version 3.33.501`，
  之后无任何 HFI 收包日志

结论：固件"在跑但对 SYS_INIT 不回话"。要修得动驱动/固件层（PAS 内存布局、wrapper 队列寄存器、
或厂商固件版本），不是 DT 能解决的。**venus 暂保持禁用。**

### RTC：能读不能写，写会卡死 SPMI 总线
- 现象：`hwclock -r` 得到 1970-01-03；`hwclock -w` → `ioctl(RTC_SET_TIME) failed: No such device`
- 根因（源码）：`rtc-pm8xxx` 里 `allow_set_time` 默认 false，
  于是 `set_time` 走 `pm8xxx_rtc_update_offset()`，它要求 **nvmem cell 或 UEFI**：
  ```c
  if (!rtc_dd->nvmem_cell && !rtc_dd->use_uefi) return -ENODEV;
  ```
  两者都没有 → 就是那个 "No such device"
- 尝试：DT 给 rtc 节点加 `allow-set-time;`（`tools/boot-r154-rtc.img`）
  → 直接写 PMIC RTC 时**整机硬死**（SSH/ping 全断，只能长按重启）
  ⇒ **这条路有毒，已回滚**，当前跑的是 `boot-r153-stable.img`
- 现状：RTC 计数在走但基准是 1970；开机后靠 NTP 校准系统时间
- 缓解：确保 `systemd-timesyncd` 开机可用（联网即校准）；不要执行 `hwclock -w`

### 硬锁死（随机重启）与显示栈 PM
上个 boot 的日志：
```
watchdog: CPU3: Watchdog detected hard LOCKUP on cpu 4
do_idle+0x84/0x2f4 ... secondary_start_kernel
```
`/proc/sys/kernel/hardlockup_panic = 0`，但设备仍重启了（PMIC 看门狗兜底）。
已知根因是 mdss 运行时挂起路径死锁（`clk_core_disable -> mdss_runtime_suspend`）。

原来只有 `mdss-pm-pin.service` 固定了 `c901000.display-controller`，
但 `c900000.display-subsystem` 和 `c994000.dsi` 仍是 `auto` → 死锁路径仍在。
已把整条显示栈都固定为 `runtime PM = on`：
```
c900000.display-subsystem: control=on status=active
c901000.display-controller: control=on status=active
c994000.dsi:                control=on status=active
```
代价是空闲功耗略高，换稳定性。

### 新增/更新脚本
`tools/pad_venus_trace.sh`、`tools/pad_venus_boot_trace.sh`、`tools/pad_mdss_pin.sh`、
`tools/pad_verify_all.sh`、`tools/pad_audio_test.sh`、`tools/pad_mic_check.sh`、`tools/pad_mic_loopback.sh`

---

## 15. 追加（2026-10-27 12:20）：屏幕"频闪"真因 = 自动亮度抖动（不是硬件）

### 现象与排查
- 用户报"整个屏幕一亮一暗地闪"，怀疑烧屏
- 内核侧检查：
  - 背光 `brightness=actual_brightness` 稳定（无反复写入）
  - `dpu error` 计数 10 秒内不增长（不是 DPU/DSI 提交超时）
  - 背光芯片是 **TI LP8556**（i2c-2 0x2c，`bl_ctl_mode = register based`），
    使能轨 `lcd-backlight-regulator`（tlmm **GPIO72**，3.15 V，70 ms 延时）
  - 停掉 `tablet-autobright` 后**立刻不闪** ⇒ 元凶是自动亮度守护

### 根因
CM3232 的 ALS 只有几个离散增益档（约 3.2× 一档），控制律
`DEADBAND=0.12 / MIN_INTERVAL=5s / EMA_ALPHA=0.35` 在阈值附近会来回改背光 →
人眼看到的就是整屏脉动。

### 修复（`tools/pad_autobright_calm.sh`，已生效，原文件备份为 `.orig`）
```
DEADBAND   = 0.25     # 12% -> 25%
MIN_INTERVAL = 20.0   # 5 s -> 20 s
EMA_ALPHA  = 0.20     # 0.35 -> 0.20
```
实测：90 秒内背光稳定在 255，只发生一次决策（日志 `545.59 lx -> 255/255`）。

### 关于"烧屏"
Mi Pad 4 Plus 是 **10.1" 1920x1200 IPS LCD**，不存在 OLED 那种永久烧屏；
看到的多是**图像残留（image retention）**，会自行消退。
屏幕上留了全屏检测工具 `tools/screentest.py`（黑/白/红/绿/蓝/灰/渐变/残影检查，
点屏幕或按键切换、Esc 退出）。

### 教训
- 自动亮度类守护**必须有足够大的死区 + 限速**，否则在离散 ALS 上就是"频闪制造机"
- 判断是软件还是硬件：先停守护进程看现象是否消失（最快的二分）

---

## 16. 追加（2026-10-27 12:40）：指纹传感器确认"活着"，并修掉"等不到手指"的根因

### 硬件确认
- Mi Pad 4 Plus **确实有指纹传感器**（[fonearena](https://www.fonearena.com/blog/260821/xiaomi-mi-pad-4-plus-price-specifications.html) 等发布会报道）
- 走 SPI7（gpio24–27，已是 `blsp_spi7` 功能），驱动 `fpc1020` 绑定，IRQ=141（tlmm **gpio71**）
- DT 供电脚：`avdd=gpio98`、`vddio=gpio92`（都 `out high`）、`reset=gpio108`（`out high` = 未复位）
- 读芯片寄存器能返回数据（`reg 0x1c = ff`），**说明 SPI 通信正常、芯片活着**

### 根因：中断挂起没清，边沿中断再也不触发
- `gpio71` 一直是 **high**（芯片把中断拉住）
- DT 里是 `IRQ_TYPE_EDGE_RISING`，线一直高 → 不会再有上升沿
- 所以 `capture` 永远报 `no finger within 15000 ms`，**即使手指按在传感器上**
- 修复方法：**先读一次 `INT_CLEAR(0x1c)`**，实测读完后 `gpio71` 立刻从 high 变 low
  ```
  echo "r 1c 1" > /sys/bus/spi/devices/spi0.0/cmd
  ```

### 新增工具
| 文件 | 作用 |
|---|---|
| `tools/fingerprint.py` | `capture` / `enroll` / `verify` / `compare` / `selftest`；192×192 帧、高通归一化 + ±2 px 平移容差的归一化互相关 |
| `tools/pad_fpc_frame.py` | 读取一帧并打印统计 + ASCII 预览 |
| `tools/pad_fpc_capture.sh` | 等手指并保存一帧 |
| `tools/pad_fpc_watch.sh` | 10 分钟窗口反复 arm（每次先清 0x1c），抓到就存 `/tmp/fp_N.bin` |

匹配算自测（无硬件）：同图 1.000 / 同花纹不同噪声 0.898 / 无关 0.013 → `SELFTEST OK`。
默认阈值 `THRESHOLD = 0.55`，等真手指数据后再定标。

### 下一步
1. 用户按手指 → 抓 3 帧 → `fingerprint.py enroll`
2. 用 `verify` 定标阈值（真手指 vs 假手指/无手指的分数分布）
3. 通过 `pam_exec` 挂到 `xfce4-screensaver` 的 PAM 服务上实现"指纹解锁"

### 驱动层的建议（下一轮可做）
`0035-fpc1020-driver.patch` 的 `capture` 路径应该**在 arm 之前先读一次 0x1c 清中断**，
否则第一次 capture 之后就会永久卡住（这正是我们踩的坑）。

### 指纹（续）：真实帧已抓到，匹配管线定型
- 清中断后 watcher 抓到 **2 帧真图像**：`/tmp/fp_1.bin`、`/tmp/fp_2.bin`
  - 统计：mean 136.4 / sd **24.3**（对比"无手指"帧 mean 103.8 / sd 3.3）
  - ASCII 预览里能看到手指边界和脊线纹理
- **匹配必须减暗帧**（固定图样噪声）实测对比：
  | 指标 | 手指 vs 手指 | 手指 vs 无手指 |
  |---|---|---|
  | 直接归一化互相关 | 0.996 | **0.783** ❌ 会误accept |
  | **减暗帧后** | 0.992 | **0.000** ✅ |
  ⇒ `fingerprint.py` 改成：模板 = 高通(25px) + 单位方差，比较时先减暗帧，±2 px 平移容差
- 已安装到设备：
  - `/usr/local/lib/fingerprint.py`（capture/dark/enroll/verify/compare/selftest）
  - `/usr/local/bin/fp-pam`（给 PAM 用的包装：最多等 4 秒手指，没有就退出让密码接手）
  - 模板目录 `/var/lib/fingerprint`（0700，模板 0600）
- **PAM 还没启用**（`/etc/pam.d/xfce4-screensaver` 未改）。启用命令：
  `sh /tmp/fp_install.sh --enable-pam`（会在首行插入
  `auth sufficient pam_exec.so quiet /usr/local/bin/fp-pam user`，密码登录仍然可用）

### 待用户配合
1. `python3 /usr/local/lib/fingerprint.py enroll user` —— 先保持 1 秒不碰（暗帧），再按 3 次手指
2. `... verify user` 反复几次，看真/假分数分布，再定阈值（现在默认 0.55）
3. 确认无误后再 `--enable-pam`

---

## 17. 追加（2026-10-27 12:55）：指纹驱动补丁 + 诚实的结论

### 驱动补丁（已生效）
`0035-fpc1020-driver.patch` 改动：
1. `fpc_wait_and_capture()` 和 `capture_now_store()` 在 arm 之前**先读 `INT_CLEAR(0x1c)`**
   （清掉挂起中断，否则边沿触发再也不来）
2. **顺带修了一个补丁本身的 bug**：hunk 头 `+1,496` 没随内容更新 → `patch` 会截断文件
   （第一次编译报 `fpc1020.c:496: expected expression` 就是这个原因）。已改成 `+1,506`。

编译 r152 后**只替换 `fpc1020.ko.zst`**（不动内核、不刷 boot），重启后干净加载，
`/sys/bus/spi/devices/spi0.0/{capture,capture_now,cmd,finger,image}` 都在。

### SPI 通信已验证可靠
```
读 0x1c: ff -> 00 -> 00     # 第一次读到挂起中断，第二次已被清掉
```
`gpio71`（IRQ）读 0x1c 后由 high 变 low —— 说明读写都真实生效。

### 但仍然**抓不到稳定指纹**（这是当前的真实状态）
- 有时能抓到真图像（12:22 那两帧：sd 24.3，ASCII 能看到手指边界和脊线）
- 大多数时候抓到的是**空帧**（sd ~3.3，和暗帧几乎一样）
- `0xD4`（手指存在寄存器）始终 `00 00`
- 甚至在**没有手指**时 `capture` 也会立刻返回 "captured 36865 bytes"

⇒ 判断：**驱动的初始化/协议与这颗芯片的版本不匹配**
（补丁里写死的是 "revision 3 (FPC1020A)" 的配置；我们这颗的 `id[0x00]` 读出来是 0，
`id[0xfc] = 03 41 00 00`）。要真正可用，需要把**厂商（Android 内核）的 fpc1020 初始化序列**
搬过来，或改用正确的"手指检测"模式。这是独立的工作量。

### 用户态已就绪（等驱动修好后可直接接上）
- `/usr/local/lib/fingerprint.py`（enroll/verify/compare/selftest，已含"减暗帧"处理）
- `/usr/local/bin/fp-pam`（PAM 包装，最多等 4 秒手指）
- `/etc/pam.d/xfce4-screensaver` **未修改**；启用命令 `sh /tmp/fp_install.sh --enable-pam`

### 教训
改补丁内容后**必须同步 hunk 头行数**，否则 `patch` 静默截断，报错位置会跑到文件末尾附近，
极难定位。健康检查：`patch -p1 --dry-run` + 应用后 `tail` 看文件结尾是否完整。

### 当前设备状态
重启后：内核 #149（r153-stable 镜像）+ **r152 的 fpc1020.ko**（新补丁）；
venus 关闭；自动亮度已限速；锁屏关闭。

---

## 18. 追加（2026-10-27 13:05）：熄屏后的"任何输入都亮屏"已实现并闭环验证

### 问题
实测：`xset dpms force off` 之后，X 服务器**不会**因为输入而自动亮屏
（注入 pointer motion / 按键后 `/sys/class/drm/card*-DSI-1/dpms` 仍然是 `Off`）。
也就是说只有按电源键能亮屏，触摸/键盘都没反应。

### 修复
把 `tablet-powerkeyd` 扩成"多设备输入守护"：
- 用 `select()` 同时监听所有 `/dev/input/event*`
  （实测有 7 个：pm8941_pwrkey、pm8941_resin、gpio-keys、gpio-hall-sensor、fpc1020、
  **Goodix 触摸屏**、**Xiaomi Mi Pad 4 Headset Jack** ← 顺带证明 3.5mm 插孔检测能用）
- `pm8941_pwrkey` 的 `KEY_POWER`：切换熄屏/亮屏
- 其它设备的任何 `EV_KEY/EV_REL/EV_ABS`：若 dpms 为 `Off` 就 `xset dpms force on`
- 状态判断读 DRM 的 `dpms`（`xset q` 永远显示 On，不可靠）

### 闭环验证方法（不需要真人操作）
`tools/uinject.py` 通过 `/dev/uinput` 创建虚拟键盘并注入一个 `KEY_A`（真实内核事件）：
```
1) blank ...            dpms: Off
2) inject KEY_A ...
   dpms: On
WAKE-ON-INPUT: OK
```
（注意：`xdotool` 走 XTEST，**不会**产生 `/dev/input` 事件，所以不能用来测这个）

### 新增工具
`tools/uinject.py`（uinput 事件注入）、`tools/pad_wake_test.sh`（验证"输入不自动亮屏"）、
`tools/pad_wake_loop.sh`（闭环验证）、更新 `tools/tablet-powerkeyd.py`

---

## 19. 追加（2026-10-27 13:15）：熄屏定时器修好（原来 5 小时才熄屏）+ 端到端验证

### 又抓到一个真问题
`xfce4-power-manager` 里的 `dpms-on-ac-sleep=300` **并没有传到 X 服务器**：
```
xset q  →  Standby: 18000   Off: 36000      # 5 小时 / 10 小时！
```
所以平板实际上**几乎从不自动熄屏**（这也解释了为什么以前"没感觉"）。

### 修复
新增 `/usr/local/bin/tablet-dpms` + `/etc/xdg/autostart/tablet-dpms.desktop`：
```sh
xset s off; xset s noblank
# 插电 300 s，用电池 180 s
xset dpms 0 0 $timeout
```
（`xset s off` 关掉 X 自带的屏幕保护，熄屏完全交给 DPMS，这样 powerkeyd 才能用输入唤醒）

### 端到端验证（完整复现用户场景）
```
set dpms Off=30
t=30s  dpms=Off          ← 自然熄屏
inject KEY_A (uinput)
       dpms=On           ← 输入唤醒
IDLE-BLANK+WAKE: OK
```
之后已恢复成 300 s。

### 现在完整的电源/显示行为
| 场景 | 行为 |
|---|---|
| 插电空闲 5 分钟 / 电池 3 分钟 | 熄屏 |
| 触摸 / 键盘 / 鼠标 | 亮屏 |
| 短按电源键 | 熄屏；再按亮屏 |
| 登录后 | autostart 自动设置 DPMS 定时器 |
| 整机休眠 | 禁用（RTC 叫不醒） |

---

## 20. 追加（2026-10-27 13:20）：散热/充电/传感器的实测结论

### 散热：只有一个能降频的设备，CPU 完全无法调频
12 个热区（空闲 36–44 °C），其中 `cpu0..3`、`pwr-cluster` 有 **70 °C passive** 触发点，
但**唯一的 cooling device 是 GPU**：
```
cooling_device0  devfreq-5000000.gpu  max_state=5
```
- CPU 之所以没有 cooling device，是因为**没有 cpufreq**；
- 时钟树里**根本没有 CPU PLL**（`clk_summary` 555 项里没有 c1/c2 PLL、没有 APCS/CPR 时钟）——
  频率由 RPMh/OSM 硬件管理，Linux 无法读也无法设；
- 结论：长时间满载时 CPU 只能一路升到 110 °C 由硬件保护关机。GPU 会在 85/90 °C 自动降频。
- 要做 CPU 调频必须写 **APCS/OSM + CPR** 驱动（含 OPP 表与电压映射），风险高（电压错会挂）。

### 充电：正常，约 1.25 A
```
pm660-charger: online=1 status=Charging vbus=5039062 µV
qcom-battery : current_now=-1250000 µA (负=充电) voltage=3715078 µV temp=30.5 °C cap=58%
```
`pm660-charger/current_max`（读 50000）**写不进去**（驱动会按 `CURRENT_SCALE_FACTOR` 换算），
但电池侧真实充电电流 ~1.25 A，属于正常水平，不需要干预。

### 传感器：4 个 SMGR 传感器全部实测出数据
它们是**纯 IIO buffer 设备**（没有 `*_raw`），必须开 buffer 读二进制。
`tools/pad_iio_sample.py` 按 `scan_elements` 的 s32×3 + u64 时间戳（含 8 字节对齐）解析：
```
qcom-smgr-accel  (-14749, 15063, -641433, 2482...)    ← x/y/z + ns 时间戳，递增
qcom-smgr-gyro   (2129, 1292, 0, ...)                 ← 静止时 ~1000 量级噪声
qcom-smgr-mag    (48169, 18678, 43844, ...)           ← 三轴磁场
qcom-smgr-prox   被 tablet-autobright 占用（EBUSY）→ 本身说明它在工作
```
PMIC ADC（`pm660-rradc`）也能读：多路温度 32/34.2/41.1 °C、VBUS 5.04 V、输入电流。

### 新增工具
`tools/pad_thermal_survey.sh`、`tools/pad_charge_test.sh`、`tools/pad_sensors_read.sh`、`tools/pad_iio_sample.py`

---

## 21. 追加（2026-10-27 13:35）：指纹走 TEE 死路 + 后摄"假 OK"修掉

### 指纹：厂商实现是 TEE 架构，mainline 无法复现
从 [MiCode/Xiaomi_Kernel_OpenSource `clover-o-oss`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/clover-o-oss)
拿到厂商驱动 `drivers/input/fingerprint/fpc/fpc1020_platform_tee.c`（22 KB），
文件头注释直接说明：

> This driver will NOT send any commands to the sensor, it only controls the electrical parts.
> …the other part of the sensor driver e.g. the TEE driver needs to do a _SOFT_ reset on the sensor after power up.

即：**真正的指纹协议（初始化、取像、匹配）跑在 TrustZone 里**，Linux 侧只做
供电（vcc_spi/vdd_io/vdd_ana 各 1.8 V）、复位时序、IRQ 和 wake lock。
⇒ mainline 上要能用，必须逆向 TEE 里的私有协议。**这条路本轮判定为不可行**，不再投入。
（我们自己的 `fpc1020.c` 驱动能抓到过真图，说明硬件和 SPI 没问题，缺的是协议。）

顺带记下厂商的复位时序（如果以后还要试）：
`reset 拉低 100 µs → 释放 5 ms → 再拉低 5 ms → 读 IRQ`，供电顺序 `vcc_spi → vdd_io → vdd_ana`，各延时 100/900 µs。

### 后摄：一直是"假 OK"
之前体检脚本只判断 `/dev/video0` 存在就报 OK，但 **`ov13855` 模块根本没加载**，
media graph 里也没有传感器实体（`entity=0`），所以取流必然失败。

- 修复：`/etc/modules-load.d/tablet-camera.conf` → `ov13855`，开机自动加载
- 加载后：
  ```
  ov13855 3-0036: xvclk0 on at 24000000 Hz
  ov13855 3-0036: OV13855 detected (id d855)
  ```
  media graph 里出现传感器（2 处引用）
- 体检脚本改成：**必须看到 ov13855 实体**才报 OK，否则 `PARTIAL (sensor not registered)`

### 后摄取流仍未通（独立问题）
手动连链路（sensor→csiphy0→csid0→vfe0_rdi0）+ 4224x3136 UYVY 取流：
```
VFE sof timeout / VFE reg update timeout / VFE halt timeout
```
说明 CSI/VFE 通道没收到帧。这需要回到 CSI/VFE bring-up（r99 时代有一份可用配方），
属于下一轮的工作。

### 当前体检结果（真实）
```
rear camera   OK (ov13855 entity present, refs=2)
front camera  MISSING (no entity)   ← 硬件
front i2c     FAILED (no ACK)
```

---

## 22. 追加（2026-10-27 13:25）：后摄**取流打通**（关键一步）

### 三个坑，逐个踩平
1. **模块没自动加载** → `/etc/modules-load.d/tablet-camera.conf` 里加 `ov13855`
   （加载后 `OV13855 detected (id d855)`）
2. **格式用错** → 传感器输出的是 **`SGRBG10_1X10`（10-bit Bayer）**，我之前用 UYVY8_1X16，
   全链路都要设成 SGRBG10，video 节点用 **`pgAA`**（10-bit Bayer GRGR/BGBG packed）
3. **VFE 会被失败尝试弄进异常状态** → 多次失败后即使配置正确也一直 `sof timeout`，
   **必须干净重启**才能恢复

### 成功证据
干净重启 + 正确配方后：
```
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=1 --stream-to=/tmp/photo_raw10.bin
→ 16,558,080 字节 = 4224×3136×10bit 单帧 ✓
dmesg: 没有任何 sof timeout / reg update timeout / halt timeout
       只有正常的 "CSIDCLK cphy_csid0 = 200000000 Hz"、"VFEPD on/off"
```
而且连拍两帧对比：**只有 66.6% 字节相同、平均差 13** → 是**实时数据**，不是静态垃圾缓冲。

### 画面为什么是"噪声"
两帧的 10-bit 值都在 50–96（很暗），解码出来是噪声：
- 这条 raw 通路**没有自动曝光/增益**（没跑 3A），暗环境就是暗噪声
- 需要用户把后摄对准强光再抓一次，或后续加曝光/增益控制才能出正常照片

### 新增工具
| 文件 | 作用 |
|---|---|
| `tools/pad_rearcam_recipe.sh` | 完整取流配方（链路/格式/取帧，每步校验）|
| `tools/pad_cam_fmt_matrix.sh` | 格式矩阵探测 |
| `tools/pad_cam_stream_probe.sh` | 取流过程中采样供电/时钟 |
| `tools/raw10_to_png.py` | RAW10(SGRBG10) → PNG（2×2 binning，PC 端用 numpy+Pillow）|

### 教训
- 摄像头这类有状态的外设，**失败几次后必须重启**再试，否则会被上一个失败状态干扰
- 判断"有没有真出图"：看帧大小是否正好等于 `W*H*10/8`，以及连拍两帧是否有差异

---

## 23. 追加（2026-10-27 13:30）：🎉 后摄**端到端打通并拍出真实照片**

### 决定性证据 1：传感器内置彩条
给 ov13855 设 `test_pattern=1`（Vertical Color Bar Type 1）后抓一帧，解码结果：
```
白 | 青 | 黄 | 绿 | 品红 | 蓝 | 红 | 黑      ← 顺序完全正确
raw10: min=64 max=1023 mean=540
```
⇒ **整条链路全部正常**：传感器 → CSIPHY0 → CSID0 → VFE0 RDI → DMA → `/dev/video0`，
并且我的 RAW10 解包 + SGRBG10 Bayer 顺序也是对的。

### 决定性证据 2：真实场景照片
设 `exposure=3206, analogue_gain=4000, digital_gain=4096` 后抓一帧，
解码后可以清楚看到桌面垫子上印的字（"星威国际 3CFS"）—— **真实照片**。
偏蓝、噪点多是因为**没有 3A（自动曝光/白平衡）**。

### 结论
后摄硬件、驱动、DMA 通道全部可用。距离"能当相机用"只差：
1. **3A 算法**（自动曝光/增益/白平衡）—— 现在必须手动给 exposure/gain；
2. 或走 libcamera / Camera HAL 那套（工作量大）。
作为"硬件可用性"验证，这一项**已完成**。

### 新增工具
| 工具 | 位置 | 作用 |
|---|---|---|
| `tablet-photo` | 设备 `/usr/local/bin/` | `tablet-photo [exp] [again] [dgain] [out]` 一键拍一张 RAW10 |
| `raw10_to_png.py` | PC `tools/` | RAW10(SGRBG10) → PNG（2×2 binning）|
| `pad_cam_tp_test.sh` | PC `tools/` | 彩条 + 高增益两连拍验证 |
| `pad_rearcam_recipe.sh` | PC `tools/` | 完整取流配方（每步校验）|

### 关键参数备忘
```
传感器: ov13855 @ i2c-3 0x36, 4-lane, link-freq 540 MHz, 4224x3136
格式  : SGRBG10_1X10（传感器）→ video0 用 pgAA（10-bit Bayer GRGR/BGBG packed）
控制  : /dev/v4l-subdev17  exposure 4..3206, analogue_gain 0..8191, digital_gain 0..16384
坑    : VFE 失败几次后会卡死，**必须重启**再试
```

---

## 24. 追加（2026-10-27 13:55）：后摄补上自动曝光 + 白平衡

### 设备端：`tablet-cam`（用户态 AE）
mainline 没有 3A，所以用用户态循环凑合：
```
tablet-cam /tmp/photo.raw [--target 450] [--iters 5]
```
- 每轮抓一帧 → 抽样解包 10-bit 值算平均亮度 → 调 exposure/analogue_gain
- 取最接近目标亮度的一帧保存
- 实测日志：
  ```
  iter 0: exp= 1200 gain= 1024 -> level   64.7 (target 450)
  iter 1: exp= 3206 gain= 1024 -> level   65.4
  iter 2: exp= 3206 gain= 7043 -> level   66.0
  iter 3: exp= 3206 gain= 8191 -> level   66.3
  ```
  亮度上不去是因为**摄像头正贴着桌面拍**（场景本身极暗），AE 逻辑本身是对的。

### PC 端：加了灰度世界白平衡
`tools/raw10_to_png.py` 现在会做 gray-world WB，之前偏青的画面恢复正常，
字（"星威国际 3CFS"）和天鹅 logo 都清晰可读。

### 现在的拍照能力
```
设备：tablet-cam /tmp/p.raw        # 自动曝光
PC  ：raw10_to_png.py p.raw p.png  # 解包 + binning + 白平衡
```
结论：后摄从"能出帧"前进到"能出可辨认的照片"。仍缺真正的 3A（连续收敛、场景自适应）
和降噪，但作为硬件可用性已经足够。

---

## 25. 追加（2026-10-27 13:40）：拍照 GUI（点一下就拍）

### 做了什么
`/usr/local/bin/tablet-camera-gui`（Python + GTK3）：
- 大按钮「拍照」+ 预览区 + 「打开相册」
- 点击后后台线程跑 `sudo -n tablet-cam`（用户态 AE，约 5 秒）
- 拿到 RAW10 后在**本进程内**用 numpy 解包 + 2×2 binning + 灰度世界白平衡，
  **自己写 PNG 编码**（zlib + CRC32，不依赖 Pillow）
- 存到 `~/Pictures/photo-YYYYmmdd-HHMMSS.png`，并显示在窗口里
- 桌面图标：`~/Desktop/tablet-camera-gui.desktop`（也已装入 `/usr/share/applications/`）

### 配套
```
/etc/sudoers.d/tablet-cam:  user ALL=(root) NOPASSWD: /usr/local/bin/tablet-cam, /usr/local/bin/tablet-photo
```
（GUI 以普通用户运行，拍照需要 root 访问 /dev/video0 和 /sys）

### 验证
- `sudo -n tablet-cam` 以 user 身份可正常跑 AE 循环 ✓
- GUI 的转换路径单独验证：`/tmp/photo_ae.raw` → `2112×1568` RGB → **6.6 MB PNG，签名正确** ✓
  （写出的图内容正确：蓝色垫子 + "星威国际 3CFS" 字样）
- GUI 前台启动 6 秒无报错 ✓

### 一个环境限制（记录）
从 SSH 会话里 `nohup setsid` 启动 GUI，**会话结束后进程会被 logind 回收**
（pmOS 默认 KillUserProcesses），所以远程没法长期留住 GUI 窗口。
在**用户自己的桌面会话**里点图标启动不受影响（那是 xfce4-session 的子进程）。
如需远程启动，可把 `/etc/systemd/logind.conf` 的 `KillUserProcesses=no` 打开。

### 新增工具
`tools/tablet-camera-gui.py`、`tools/tablet-camera-gui.desktop`、
`tools/pad_camgui_start.sh`、`tools/pad_camgui_check.py`、`tools/pad_win_list.sh`

---

## 26. 追加（2026-10-27 13:45）：屏幕键盘（平板模式下能打字了）+ OTG 复核

### OTG 复核
```
tablet-otg status → otg_vbus=0 charger_online=1
```
逻辑正确：**插着充电时不打开 5V 升压**（避免和充电冲突），服务也正常结束。
但目前没法实测带设备的情况 —— 平板只有一个 USB-C 口，充电时键盘插不上。

### 屏幕键盘：之前完全不可用
- `onboard` 其实**已经装了**（`/usr/sbin/onboard`），但**没在跑、也没自启动** →
  也就是说拔掉键盘后**根本没法输入文字**，这是平板模式下很实际的缺口。

修复：
1. `/etc/xdg/autostart/tablet-onboard.desktop`：登录时 `onboard --hidden --layout=Compact`
2. dconf 设置：
   - `org/onboard/auto-show/enabled = true`（点输入框自动弹出，依赖 at-spi，已自启）
   - `org/onboard/window/force-to-top = true`
3. 手动开关：`/usr/local/bin/tablet-keyboard`（在跑就 D-Bus ToggleVisible/停止，没跑就启动）
   + 桌面图标「屏幕键盘」

冒烟测试：`onboard --layout=Compact` 前台运行 4 秒无报错
（只有 mousetweaks/acpid/appindicator 的无害警告）。

### 新增工具
`tools/tablet-keyboard`、`tools/pad_keyboard_setup.sh`、`tools/pad_onboard_setup.sh`

---

## 27. 追加（2026-10-27 14:30）：venus 攻坚 —— 修掉核心时钟 bug，HFI 仍卡

### 已定位并修复的真 bug：视频核心时钟一直停在 19.2 MHz
驱动 `core_clks_enable()` 里只有 `IS_V6(core) || (IS_V4(core) && is_lite(core))` 才调 `clk_set_rate`，
**sdm660 的 AR50 走不到**，于是 `video_core_clk_src` 停在 XO 的 19.2 MHz —— 固件根本跑不动。

修复（两条一起上）：
1. **DT 层**：`&venus { status = "okay"; assigned-clocks = <&mmcc VIDEO_CORE_CLK_SRC>;
   assigned-clock-rates = <518400000>; }`（既有补丁 0040）
2. **驱动层**：新补丁 `0041-media-venus-program-core-clock.patch` —— 在 `core_clks_enable()`
   里对 `clks[0]`（core）先 `clk_set_rate(freq_tbl[0].freq)` 再 enable

验证：`video_core_clk_src` 从 **19200000 → 441600000** ✓

### 但硬解仍然失败（HFI 初始化超时）
```
ffmpeg -c:v h264_v4l2m2m → output VIDIOC_REQBUFS failed: Operation timed out
dmesg: venus hw version 3.33.501   （固件镜像确实加载了）
/proc/interrupts: venus 计数 3 → 3  （整个初始化过程中一次中断都没有）
```
⇒ 固件被 PAS 加载、硬件版本能读到，但**从不回应 HFI_CMD_INIT**。

### 下一个怀疑点（有数据支撑）
```
video_axi_clk            rate 0        ← AXI 分支时钟速率 0
interconnect summary:  cc00000.video-codec  0 0 0    ← 带宽投票全是 0
genpd: venus_core0  off-0
```
如果 AXI 总线没有带宽/时钟，固件访问共享内存（HFI 队列）就会卡死。
下一步方向：在 core init 阶段给 venus 投一个最小带宽（`icc_set_bw`），
或检查 `res->bw_tbl` 是否被正确应用；以及 HFI 队列内存的 SMMU 映射。

### 现场
- 设备现在跑 **r157**（r157 内核 + 638 个配套模块），venus 已启用
- 回退镜像：`boot-r153-stable.img`（md5 5eb20bf2…），r157 镜像 `boot-r157.img`（md5 d69afc23…）
- 工具：`tools/pad_venus_*.sh`、`tools/0041-media-venus-program-core-clock.patch`、
  `tools/vm_venus_clk_install.py`、`tools/vm_venus_clk_patch.py`

---

## 28. 追加（2026-10-27 14:45）：**充电偏慢的真因** + venus 诊断未命中

### 充电：边用边掉电的原因找到了
```
pm660-charger: online=1 status=Charging usb_type="Unknown SDP [DCP] CDP"
              current_max=50000 (=ICL_STATUS 50 mA)  vbus=5.04 V
qcom-battery : current_now≈-0.59 A  cap 39%→39%（20 秒内不涨）
```
- `current_max` **读的是 `ICL_STATUS`**（AICL 自动限流后的实际值），**写的是
  `USBIN_CURRENT_LIMIT_CFG`**（`CURRENT_SCALE_FACTOR=25000`，即 1 档 = 25 mA）
- 当前被识别成 **SDP（标准下行口，500 mA 上限）**，实际只跑到 ~0.6 A 进电池
- 写 500 k / 1 M / 1.5 M µA 都"接受"了，但 `ICL_STATUS` 与电池电流都不变
  ⇒ **硬件按 SDP 类型封顶**，软件改配置寄存器无效

结论：**插着充电器能充，但只有 ~0.6 A（约 7%/小时）**，一边跑相机/编译测试就会净放电。
要明显改善需要：让 SMB2 做 **APSD（DCP 检测）**，或打补丁在 SDP 情况下强制更大的 ICL。

### venus 诊断：补丁装上了但没打印
- 0042 诊断补丁（读 `CPU_CS_SCIACMDARG0` 的 PC_READY 位）已编译进 r158 模块，
  `strings` 能确认两条 `diag:` 字符串在 `venus-core.ko` 里
- 但实测解码时 dmesg **只有 "venus hw version 3.33.501"（出现两次），没有任何 diag 输出**
  ⇒ `venus_core_init()`（我打补丁的那个函数）**根本没被调用**，流程在更早的
  power-on / resume 路径就停住了。下一步应该把打印放到 `venus_power_on` / ISR 里确认调用链。

### 现场
- 设备跑 r157 内核 + r158 的 venus-core.ko（诊断版）
- 电量 39%，建议换一个能被识别为 DCP 的充电器，或先关机充电

### 进一步：熄屏能让它"回血"
```
屏幕亮着:  bat_cur ≈ -0.59 A   （净放电）
屏幕熄灭:  bat_cur ≈ -0.28 A   （开始慢慢充）
```
所以平板亮屏 + WiFi + 调制器运行时的功耗就超过了充电器能给的电量（SDP 500 mA 档）。
**结论：长期插电使用建议熄屏充电，或换能被识别为 DCP 的充电器。**

已执行：`xset dpms force off`（触摸/按键即可唤醒）+ 卸载 ov13855 省一点电。

---

## 29. 追加（2026-10-27 15:56）：🎉 **充电问题彻底解决**（AICL 是元凶）

### 真因
`qcom_smbx` 的 `USBIN_CURRENT_LIMIT_CFG` 早就被写成了 **60 档 = 1.5 A**（我之前的 sysfs 写入其实生效了），
但 **AICL（Automatic Input Current Limit）把实际限流压到了 2 档 = 50 mA** ——
50 mA 连平板待机都不够，所以一直净放电（`bat_cur` 负值、电量持续下降）。

### 修复（补丁 0043）
`qcom_smbx.c` 在 `smb_init_hw()` 末尾：
1. 写 `USBIN_CURRENT_LIMIT_CFG = 1.5A/25mA = 60`
2. **关掉 AICL**（`USBIN_AICL_OPTIONS_CFG` 的 `USBIN_AICL_EN_BIT`）
3. 清掉 `USBIN_SUSPEND_BIT`
4. 打印寄存器读回值，便于验证

实测日志（决定性证据）：
```
clover: icl cfg 60 -> 60 (wrote 60), status 2 -> 60, 25000 uA/step
                                            ^^^^^^ AICL 原来把它压在 2（50mA）
```

### 效果
| 指标 | 修复前 | 修复后 |
|---|---|---|
| ICL 实际值 | 50 mA | **1.5 A** |
| 电池电流 | **-0.30 A（放电）** | **+1.19 A（充电）** |
| 电量 | 30% 并持续下降 | **30% → 37%（约 6 分钟）** |

### 温度与保护（用户要求）
- 电池温度：**25.3 °C**；PMIC 36 °C；GPU 39 °C（都很凉）
- 硬件保护：PMIC `temp_alert_max = 61 °C`、`temp_max = 65 °C`
- **新增软件守护** `/usr/local/bin/tablet-charge-guard`（systemd 常驻）：
  | 电池温度 | 输入限流 |
  |---|---|
  | < 38 °C | 1.5 A |
  | 38–42 °C | 0.8 A |
  | 42–45 °C | 0.4 A |
  | 45–48 °C | 0.2 A |
  | ≥ 48 °C | 0.1 A |
  另外 ≥46 °C 有硬保护会强制降到 200 mA；电量 ≥95% 时降到 0.8 A 缓充。
- 现在 sysfs 写 `current_max` 能立即生效（AICL 关了），已经实测 500 mA ↔ 1.5 A 切换正常

### 注意
- 该修复在**模块层**（r159 的 `qcom_smbx.ko`），已安装并会开机自动加载；下次刷内核要用 r159+
- 备份：`backup/work-20261027-1500.zip`

---

## 30. 事故记录（2026-10-27 16:35）：venus HFI v4 实验导致整机 panic

### 发生了什么
为验证"会话初始化无响应是否因为 v3 电源路径不给总线投票"，打了补丁 0047：
把 `sdm660_res.hfi_version` 从 `HFI_VERSION_3XX` 改成 `HFI_VERSION_4XX`（走 v4 PM ops，
会做 ICC/OPP 投票），只热替换了 `venus-core.ko` 后重启。

结果：**设备再也没起来** —— ping 不通、SSH 超时。判断为内核 panic
（`CONFIG_PANIC_ON_OOPS=y` + `CONFIG_PANIC_TIMEOUT=-1` = 永不自动重启）。

推断原因：`pm_ops_v4` 需要 `vcodec_pmdomains`（"venus"/"vcodec0"/"vcodec1"）与 OPP 表，
sdm660 的 DT/资源里没有 → 空指针 → oops → panic。

### 恢复方案（已准备好）
1. 用户长按电源 10–15 秒强制断电，再开机
2. 若能进系统：把 `/usr/lib/modules/7.0.14-sdm660/kernel/drivers/media/platform/qcom/venus/venus-core.ko.zst`
   还原成 r161 的安全版本（`tools/_venus-core-r161.ko.zst`）
3. 若仍黑屏：`python tools/revert_venus_twrp.py --remove`（TWRP 里挂载根分区并删掉该模块）

### 教训（重要）
- **不要热替换可能导致 panic 的内核模块而没有"无 SSH 回滚"路径**
- 更安全的做法：模块实验前先准备好 TWRP 恢复流程，或把实验模块放在可切换的开关后面
- 风险高的驱动实验，最好有用户在旁边能断电

### venus 目前的确定结论（截至 0046）
```
diag: hfi_core_init state=0, calling core_init
diag: INIT_DONE received, err=0            ← 固件核心初始化成功！
diag: venus_session_init st=2 codec=2
diag: session_init packet queued
diag: SESSION_INIT reply bad -110 err=0    ← 会话初始化无任何响应
```
- 跳过 image-version + 默认属性包（0046）后**仍无响应**
- 固件在 INIT_DONE 后就不再产生中断；也没有发任何错误包
- 说明问题在 **HFI 会话层**（不是时钟、不是固件加载、不是供电）

### 设备状态
- 内核 r157 + r163 的 venus-core.ko（有问题的那个）
- 充电器插着，PMIC 会在硬件层继续充电（不受 panic 影响）

---

## 31. 追加（2026-10-27 17:00）：REA/静态分析产出 —— 前摄 endpoint + 探测矩阵（等设备恢复即可试）

### REA 环境现状
- 本机（Windows）REA **没有可用的 ELF/ARM 后端**：Ghidra P0 在 Windows 只收 PE，
  Hopper 仅 macOS，IDA/Kuna 未配置
- VM（Ubuntu 22.04）装了 REA 6.7.0，但 `rea doctor` 显示 **所有分析引擎都未配置**
  （`GHIDRA_INSTALL_DIR` 空、IDA/JADX/Kuna 未设置）→ 需要装 Ghidra 才能真正反编译
- 已装 `binutils-arm-linux-gnueabi`，可反汇编 ARM（但 .so 是 stripped，只有
  `sensor_open_lib` / `s5k5e8_calculate_exposure` / `s5k5e8_fill_exposure_array` 三个导出符号）

### 关键结论：s5k5e8 **驱动早就存在且已编译**
- `0029-media-i2c-s5k5e8.patch`（899 行）+ `CONFIG_VIDEO_S5K5E8=m` 已在内核里
- 设备上 `lsmod` 确实有 `s5k5e8`，DT compatible 也匹配 `samsung,s5k5e8`
- ⇒ 前摄问题不是"缺驱动"，而是**传感器不上电/不上时钟**，所以 probe 读 chip ID 时 NACK

### 用厂商 DTB 推翻了一个错误判断
之前以为"前摄 VDIG 应该是 1.2 V"。厂商 DTB 实测：
```
/soc/qcom,cci@ca0c000/qcom,camera@2:
  cam_vana-supply = /soc/cam_avdd_front_fixed_regulator   (2.8 V, gpio49)
  cam_vdig-supply = /soc/qcom,rpm-smd/.../regulator-l13   (1.78–1.95 V = 1.8 V)
  cam_vio-supply  = /soc/qcom,rpm-smd/.../regulator-l11   (1.8 V)
  gpios = <tlmm 33 (MCLK2)>, <tlmm 52 (RESET2)>, <tlmm 49 (VANA)>, <pm660l 3 (VDIG 使能)>
```
⇒ **VDIG 就是 1.8 V**，我们的 0039 补丁模型（l13 + pm660l gpio3 开关）**已经是对的**。

### 前摄唯一还缺的：CSI endpoint（已补，补丁 0048）
`camera@10` 节点没有 `port/endpoint`，所以 camss 永远绑不上 csiphy2 —— 即使传感器应答了也出不了图。
0048 补丁加了：
```dts
&camss { ports { port@2 { csiphy2_ep: endpoint { data-lanes = <0 1>; remote-endpoint = <&s5k5e8_ep>; }; }; }; };
&cci_i2c1 { camera@10 {
        assigned-clocks = <&mmcc 82>; assigned-clock-rates = <24000000>;
        port { s5k5e8_ep: endpoint { remote-endpoint = <&csiphy2_ep>;
                data-lanes = <1 2>; clock-lanes = <0>;
                link-frequencies = /bits/ 64 <540000000>; }; };
}; };
```
**r164 编译通过**（DTB 语法无误）。

### 设备恢复后第一件事：前摄探测矩阵
驱动暴露了 `reset_mode` / `delay_ms` / `hold` / `read_id` 四个参数，
`tools/fp_probe_matrix.sh` 会跑 3×3 组合（复位方式 × 延时），
每组都打印 dmesg 里的 chip ID 结果，最后再 `i2cdetect` 扫 CCI 总线：
```sh
sh /tmp/fp_probe_matrix.sh
```
哪一组能读到 chip ID，就说明前摄上电时序找到了。

### 待办（设备恢复后）
1. 还原 venus 模块（`_venus-core-r161.ko.zst` 或 TWRP 删除）
2. 跑前摄探测矩阵
3. 若前摄通了 → 用 r164 内核（含 endpoint）验证取流

---

## 32. 追加（2026-10-27 17:10）：Ghidra 装好 + 靠厂商源码定位 venus 会话失败的**最可能原因**

### Ghidra 12.1.4 已在 VM 装好，REA 全绿
```
ghidra                 ok   /home/user/ghidra_12.1.4_PUBLIC
ghidra-version         ok   12.1.4
ghidra-headless        ok   support/analyzeHeadless
ghidra-native_decompiler ok
ghidra-java            ok   JDK 21.0.12.1
```
环境变量 `GHIDRA_INSTALL_DIR=$HOME/ghidra_12.1.4_PUBLIC` 已写入 `~/.bashrc`。
VM 另装了 `binutils-arm-linux-gnueabi`（可反汇编 ARM ELF）。

### venus 重大线索：厂商在**每次会话前**重发系统属性
对照厂商 `venus_hfi.c`：
```c
venus_hfi_session_init():
        list_add_tail(...)
        __set_default_sys_properties(device);      // ←★ 每次会话前都发
        call_hfi_pkt_op(dev, session_init, &pkt, s, session_type, codec_type);
```
而 `__set_default_sys_properties()` 发三个属性：
```c
__sys_set_debug(device, msm_vidc_fw_debug);
__sys_set_idle_message(device, res->sys_idle_indicator || ...);
__sys_set_power_control(device, msm_vidc_fw_low_power_mode);   // 硬件电源塌缩
```
mainline 只在 `venus_core_init()` 里发**一次**。如果固件在电源塌缩/重新上电后丢失这些属性，
`HFI_CMD_SYS_SESSION_INIT` 就会被**静默丢弃** —— 与我们观测到的"包已入队、无任何回应、无中断"完全一致。

### 补丁 0049（已在 r165 编译通过）
在 `venus_session_init()` 发会话包**之前**调用 `venus_sys_set_default_properties(hdev)`，
并把 0046 的 `skip_sys_props` 默认值改回 false（正常发送属性）。

### 交叉验证过的点（不是猜）
| 检查 | 结果 |
|---|---|
| 命令类型 | mainline 与厂商都用 `HFI_CMD_SYS_SESSION_INIT` (0x10007) ✓ |
| 结构体布局 | 双方都是 20 字节 `{size, type, session_id, domain, codec}` ✓ |
| 固件启动 | 厂商用 VBIF CPA/FW 寄存器 + IOMMU 映射 + 写 SW_RESET；mainline 走 TZ PAS，已能收到 INIT_DONE ✓ |
| 属性内容 | mainline 的 debug/power_control 与厂商一致，只是**时机**不同 ✗ |

### r165 内容
- 0048 前摄 CSIPHY2 endpoint + MCLK 24MHz（DTS 编译通过）
- 0049 venus 每会话重发系统属性（编译通过）
- 其余补丁不变

### 设备恢复后的测试顺序
1. 还原 venus 模块 → 确认系统正常
2. 装 r165 的 `venus-core.ko` → 跑解码 → 看 `diag: SESSION_INIT reply` 是否变成成功
3. 装 r165 内核（含 0048）→ 跑前摄探测矩阵

---

## 33. 追加（2026-10-27 18:00）：指纹做成成品 + venus 开机自测就绪

### 指纹：软件栈已成品（等设备回来验证）
新增/整理的文件：
| 文件 | 作用 |
|---|---|
| `tools/tablet-fingerprint-gui.py` | 平板图形界面（全屏、大字号）：录入 / 验证 / 删除模板 / 退出 |
| `tools/fp-helper` | root 助手（模板在 `/var/lib/fingerprint` 0600，需 root）|
| `tools/tablet-fingerprint.desktop` | 桌面图标「指纹」|
| `tools/pad_fingerprint_setup.sh` | 一键安装：驱动 → udev 权限 → 匹配器 → 助手 → 桌面图标 |

设计要点：
- GUI 以**普通用户**运行；只有实际读写传感器时通过 `sudo -n fp-helper`（NOPASSWD sudoers）提权，
  避免整个 Python 跑在 root
- udev 规则把 `/sys/bus/spi/devices/spi0.0/{cmd,capture,capture_now,image,finger}`
  交给 `fingerprint` 组，权限 0660/0664
- 语法已校验：`python -m py_compile` ✓、`sh -n` ✓（4 个脚本）

### venus：开机自测（解决 /tmp 被清空的问题）
| 文件 | 作用 |
|---|---|
| `tools/venus-autotest.sh` | 开机后自动：等 venus 探测 → 生成测试视频 → 解码 → 抓 diag/中断 → 写 `/root/venus-autotest.log` → 自我禁用 |
| `tools/pad_install_venus_test.sh` | 备份旧模块 → 装新 `venus-core.ko` → 装并启用自测服务 → 重启 |

这样设备一恢复，只要：
```sh
sh /tmp/install_venus_test.sh /tmp/venus-core-r165.ko.zst
```
重启后我直接读 `/root/venus-autotest.log` 就有完整结果（不用再推脚本）。

### 指纹的 TEE 死结（记录，避免再走弯路）
- HAL `fingerprint.fpc.so` = aarch64 stripped，导出全是 `fpc_tee_*`
- 厂商内核驱动只做供电/复位，协议在 TEE
- trustlet **不在 vendor.img**（已用 debugfs 全盘确认：/firmware 只有 GPU/音频/wlan）
  → 在独立 firmware 分区，但**我们不需要它**（自研 fpc1020.c 已能直接读图）

---

## 34. 追加（2026-10-27 18:20）：CPU 调频数据挖出（vendor DTB 反推）

### 从厂商 CPR-H 节点提取的完整 OPP 表
生成物：`tools/sdm660-opp.dtsi` + `tools/sdm660-opp.json`（脚本 `tools/extract_sdm660_opp.py`）

**小核 cluster**（`cprh-ctrl@179c8000`，8 个 corner）：
| 频率 | 电压上限(ceil) | 电压下限(floor) |
|---|---|---|
| 300 MHz | 724 mV | 588 mV |
| 633 MHz | 724 mV | 588 mV |
| 902 MHz | 724 mV | 596 mV |
| 1113 MHz | 788 mV | 652 mV |
| 1401 MHz | 868 mV | 712 mV |
| 1536 MHz | 1068 mV | 744 mV |
| 1747 MHz | 1068 mV | 784 mV |
| 1843 MHz | 1068 mV | 844 mV |

**大核 cluster**（`cprh-ctrl@179c4000`，7 个 corner）：
| 频率 | 上限 | 下限 |
|---|---|---|
| 300 MHz | 724 mV | 588 mV |
| 1113 MHz | 724 mV | 596 mV |
| 1401 MHz | 788 mV | 652 mV |
| 1747 MHz | 868 mV | 712 mV |
| 1958 MHz | 988 mV | 744 mV |
| 2150 MHz | 988 mV | 784 mV |
| 2457 MHz | 1068 mV | 844 mV |

（CPR 会从 ceil 自适应往下压，所以 OPP 里用 ceil 是安全的）

### 移植成本评估（重要）
mainline `drivers/pmdomain/qcom/cpr.c` 是**为 qcs404 重写的硬编码驱动**：
- `struct cpr_acc_desc { const struct cpr_desc *cpr_desc; const struct acc_desc *acc_desc; }`
- 每个 SoC 一份 `cpr_desc`（fuse corner 表、step_quot、ring osc）+ `acc_desc`（ACC 寄存器序列）
- 只匹配 `qcom,qcs404-cpr`

要做 sdm660 需要：
1. 按厂商 DTB 的 `qcom,cpr-fuse-corners` / `qcom,cpr-ro-scaling-factor` / `qcom,cpr-corner-fmax-map` 等
   重构出 sdm660 的 `cpr_desc`/`acc_desc`（这些在厂商驱动里是 DT 解析的，mainline 是编译期常量）
2. 补 `compatible = "qcom,cprh-sdm660-kbss-regulator"` 的匹配
3. OPP 表（**已完成**，见上）
4. 还要 OSM/APCS cpufreq —— sdm660 的 OSM 与 sdm845 的寄存器布局不同

**结论：数据齐了 60%，但仍是数天级移植，且电压错误会随机死机 → 保持最低优先级。**

### 另外两项数据也备齐（未来可用）
- GPU CPR：`/soc/cpr4-ctrl@05061000`（qcom,cpr4-sdm660-mmss-ldo-regulator）
- devfreq cpufreq 节点：`/soc/devfreq-cpufreq`、`/soc/devfreq-cpufreq/mincpubw-cpufreq`

---

## 35. 追加（2026-10-27 18:45）：venus 结论 —— 固件在 INIT 后停止工作（硬件/固件不匹配）

### 决定性实验（补丁 0050：PING 活性探测）
在 `venus_core_init()` 末尾排入 `HFI_CMD_SYS_PING`，并在 `hfi_sys_ping_done()` 打印 ACK：
```
diag: PING queued (0)
diag: INIT_DONE received, err=0        ← 固件回应了 SYS_INIT
（没有 "PING ACK received"）            ← 之后一切命令石沉大海
```
venus 中断总数在整个过程中**始终是 3**（开机那几次），会话/PING 期间零新增中断。

### 已排除的所有可能（每项都是实测）
| 假设 | 实验 | 结果 |
|---|---|---|
| 时钟太慢 | 补丁 0041 + DT 钉频 | ✗ 19.2 MHz → 441.6 MHz，仍失败 |
| 缺系统属性 | 补丁 0049（每会话重发 debug/idle/power_control）| ✗ 仍无回应 |
| 固件睡眠需踢中断 | 补丁 0051（每次写命令都 `venus_soft_int`）| ✗ PING 依然无 ACK |
| 属性包导致固件崩 | 补丁 0046（跳过 image-version + 默认属性）| ✗ 仍无回应 |
| 命令类型/结构体错 | 与厂商 `hfi_packetization.c` 逐字段对比 | ✗ 完全一致（0x10007，20 字节）|
| domain/codec 枚举错 | 与厂商 `vidc_get_hfi_*` 对比 | ✗ 都是 2/2 |

### 结论
**固件在回答 INIT_DONE 之后就不再处理任何命令，也不产生中断。**
我们加载的是 `qcom/venus-4.4/*`（linux-firmware 里 msm8998 那一版），而：
- **厂商的 venus 固件不在 vendor.img**（已用 debugfs 全盘确认：`/firmware` 只有 GPU/音频/wlan，
  `grep -a "venus"` 命中的全是 sysfs/regulator 名字）
- 上游 `sdm630.dtsi` 里 venus 一直是 `status = "disabled"` —— **从来没人测过 sdm660 的 venus**

⇒ 最可能的原因：**固件与 sdm660 的 venus 硬件变体不匹配**（能跑握手，但会话子系统不存在/不兼容）。

### 下一步（若还要继续）
1. 找到厂商真正用的 venus 固件（可能在 `system` 镜像或 `modem` 分区的 image/ 里），替换后重测
2. 或者在 session 超时后读 `WRAPPER_CPU_STATUS` / `CPU_CS_SCIACMDARG0`，确认固件是"崩溃"还是"空闲"
3. 软件解码可用，venus 不是必需品

### 本轮还有的重要事实
- 设备已从 panic 中恢复（TWRP 通过 fastboot 临时启动，未刷机）：`tools/rescue_venus.py` 一键救援
- 恢复了"每次传输校验 md5"的习惯：`tools/pad_venus_install_verified.sh` 会逐级验证，
  之前就是一次文件损坏（zstd 魔数被 UTF-8 替换字符污染）导致 `Exec format error`
- 电量 87%，充电正常
- 指纹驱动在线（`/sys/bus/spi/devices/spi0.0/finger` 可读）

---

## 36. 追加（2026-10-27 18:55）：指纹现场结论 —— 传感器活着，但取图协议不对

### 实测到的事实
```
probe 日志:
  fpc1020 spi0.0: id[0x00] = 00 00 00 00
  fpc1020 spi0.0: id[0xfc] = 03 41 00 00     ←★ 传感器真实响应（SPI 通）
  input: fpc1020 as .../input/input4
  fpc1020 spi0.0: FPC1020 ready (irq=141)
/proc/interrupts: 141: msmgpio 71 Edge fpc1020   ← IRQ 已注册
```

### 取图为什么是平坦场
- `capture_now`：reset → 发 `0xC0`(CAPTURE) → 轮询 `0x1C` 的 bit5(IMAGE_READY) → 读到的是**陈旧缓冲**
  （30 帧全是 mean≈104 / sd≈3.4；只有 f26 略不同）
- `capture`（完整路径）：先写一串配置寄存器 → 发 `0x24`(等手指) → **等 IRQ** → 再 CAPTURE/读图
- 结论：**`0xC0` 命令没有产生 IMAGE_READY**，说明这套命令序列不适用于这颗传感器的版本（ID `0x0341`）

### 又一次系统挂死（我的责任，已恢复）
`modprobe -r fpc1020` 重新加载模块时，驱动在**卸载过程中被 IRQ 打断**（handler 里还 `input_report_key`）
→ 整机卡死 → watchdog 自动重启。**结论：绝不要热卸载 fpc1020 模块。**

### 为什么难以为继
厂商把采集/匹配全放在 TEE（HAL 全是 `fpc_tee_*`），trustlet 又不在 vendor.img 里，
所以**没有可参考的寄存器序列**。我们手上的 0xC0/0xC4 命令来自公开的 FPC1020 驱动，
对这颗 `0x0341` 版本不成立。

### 建议
1. **暂停**指纹取图实验（风险 > 收益，已经两次挂机）
2. 若以后要继续：需要拿到厂商的 fpc trustlet（firmware 分区 dump）反汇编出真实的 SPI 命令序列
3. 指纹栈（驱动/GUI/PAM 助手）保留，等协议打通即可用

---

## 37. 追加（2026-10-27 19:15）：🔑 **找到 FPC 的 TEE 应用本体**（协议+算法都在里面）

### 在哪
**`NON-HLOS.bin`（MIUI V10.3.2.0 线刷包的调制解调器镜像）** 里嵌了一个 32 位 ARM ELF。
（线索：`grep -a "fpc" NON-HLOS.bin` → `fpc1020_command`、`fpc_spi_write` 等）

提取脚本：`tools/carve_fpc_blob.py`
产物：`tools/fpc_blob.elf`（664,904 字节；1,470 个函数 / 486 个字符串）

### 这个 blob 是什么
字符串直接暴露身份：
```
fpc_ta_capture_image            ← TA = Trusted Application（这就是指纹 trustlet）
fpc_spi_init / fpc_spi_destroy
fpc_spi_read / fpc_spi_write / fpc_spi_writeread
fpc_device_capture_image / fpc_device_capture_uncalibrated_image
FpcBioEnrolAddImage / _fpc_algo_identify_image
decision = %d, matched: %d, score: %d, zones: 0x%x
"%s fpc_spi_write (reg=0x%x/%d) failed (%d)"
"%s - Timeout, polled: %u times(%u us) without IRQ being set"
```
⇒ **SPI 命令序列 + 采集流程 + 指纹匹配算法全在这里**，正是我们缺的东西。

### 为什么之前找不到
- 设备 `system`/`vendor` 里只有 HAL（`fingerprint.fpc.so`），没有 trustlet
- 魔趣 ROM 的 system/vendor 也没有（字节级全盘搜过）
- MIUI 的 vendor.img 也没有
- **它藏在 `NON-HLOS.bin` 里**（Xiaomi 把 TEE 应用塞在 modem 镜像）

### 已经做好的分析准备
- VM 上 Ghidra 12.1.4 + REA 可用，`rea analyze fpc_blob.elf` 成功
  （image base 0x10000，1470 函数，486 字符串）
- 关键字符串文件偏移（用 `tools/carve_fpc_blob.py` 定位）：
  `fpc_ta_capture_image@0x9d075`、`fpc_spi_write@0x9d74e`、`fpc_spi_writeread@0x9d78a`
- 该 ELF 的 program header 有几处奇怪的 NULL 段，字符串落在未映射的洞里
  → 下一步要按"原始 ARM blob"反汇编，或修补 program header 让 Ghidra 正确映射

### 下一步（拿到命令序列）
1. 反编译 `fpc_ta_capture_image` 和它调用的 `fpc_spi_write` 调用点
2. 提取写出的 (寄存器, 值) 常量 → 这就是传感器初始化/采集序列
3. 把序列填进我们的 `fpc1020.c`，替换猜的 0xC0/0xC4 命令
4. 匹配算法可以不用（我们自己有 `fingerprint.py` 的暗帧相减）

---

## 38. 追加（2026-10-27 19:25）：`capture` 通路打通了，但图像是饱和场（配置序列仍不对）

### 好消息：capture 不再挂机，能返回数据
```
[kernel] fpc1020 spi0.0: captured 36865 bytes
```
（之前那次整机挂死是 `modprobe -r` 卸载模块引起的，**不是 capture 的锅**）

### 但抓到的帧是饱和的
```
mean 85.8  sd 83.0  min 0  max 167
偶数行列 ≈ 0xA6/0xA7 (166/167)   ← ADC 饱和
奇数列   = 0x00（从第 7 行起）    ← 2 列交错
```
渲染成 PNG 是规则条纹，不是指纹脊线。

### 结论
- SPI 通路、IRQ 通路、采集流程都通了
- **传感器配置（ADC/增益/时序/图像格式）不对** → 读回饱和值
- 我们驱动里的初始化序列（0x68/0x6C/0x90/0x8C/0xA0/0xA8/0x5C/0xD8/0xDC/0x54）来自公开的 FPC1020 驱动，
  对这颗 ID `0x0341` 的传感器**不适用**
- 正确序列在 `tools/fpc_blob.elf`（NON-HLOS 里挖出的 FPC TA）里

### 反编译受阻
- Ghidra 12.1.4 headless 两次在导入阶段被 kill（VM 内存/时间）
- radare2/rizin 在 Ubuntu 22.04 上装不了
- 该 ELF 的 program header 有异常（字符串落在未映射洞），已写 `tools/patch_trustlet_elf.py` 修补
- 下一步：修好映射后用 REA 的 `decompile --procedure`（它成功分析过一次：1470 函数/486 字符串）

### 已确认可用的救命手段
- `tools/rescue_venus.py`：fastboot 临时启动 TWRP → 改 rootfs → 重启（今天救了一次）
- 设备 watchdog 可靠，挂死会自己重启
