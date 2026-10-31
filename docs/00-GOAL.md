# 00 · 总目标与路线（新会话必读第一篇）

> 创建：2026-10-24 09:00（Asia/Shanghai）
> 最后更新：2026-10-24 15:40
> 用途：**新会话从这里开始**，先读这份，再读 `HANDOFF.md` 和 `07-xorg-xfce.md`。
> **硬件缺陷全清单见 `08-HARDWARE-AUDIT.md`（2026-10-24 全量普查，9 项缺陷）。**
> **⚠️ P0-1 已完成深度调查，结论见 `09-P0-1-SENSORS.md`（推翻了 08 的传感器结论）。**
> **✅ 自动旋转 + 合盖休眠 → `10-AUTOROTATE.md`（`tablet-orientd`，已启用）**
> **⭐⭐ ALS 真因 → `11-REGISTRY-EXPERIMENT.md`：`qcom_smgr.c` 把 `data_type`
>    硬编码成 0，ALS 需要 1。**
> **⛔→✅ 刷机 4 次黑屏 → `12-FLASH-ATTEMPT.md`；成功记录 → `13-ALS-SUCCESS.md`**
> **   黑屏唯一根因 = `CONFIG_DEBUG_INFO_BTF_MODULES=y`，
>    必须【内核 + 637 模块 + initramfs】三件套同时换。**
> **✅ `15-ALS-SAMPLERATE.md`：补丁 2 —— 驱动从不使用 `cur_sample_rate`，
>    `report_rate=0` 时 DSP 不产生样本。加采样率回退后 ALS 真正可用。**
> **✅ `14-AUTO-BRIGHTNESS.md`：`tablet-autobright` 已启用，实测 39~141 lx 正常调光。**
> **用户已确认：没有磁铁（合盖休眠待实测）；选 A（保留自动旋转）。**

---

## 一、最终目标（用户原话，不得改动）

> 让这台 **小米平板 4 Plus（xiaomi-clover-plus，SDM660）** 可以**完美使用**，
> 包括**所有硬件**，最终成为**办公电脑**。
>
> 不管是：
> - 应用响应速度
> - 必须的应用插件
> - **无法驱动的硬件**
>
> 都要解决，都要可以使用。
>
> 必要时可以：
> - 使用 **REA**（逆向工程工具，本会话可用）
> - 搜索全网数据
> - **进行反汇编，拿到驱动，进行调试**

**这意味着：不再接受"硬件限制"作为终点。所有硬件必须工作。**

---

## 二、当前状态一句话

**桌面已可用（原生 Xorg + XFCE），触屏中文输入可用，麦克风可用，电池显示可用。**
**但扬声器无声、真休眠死锁、蓝牙键鼠未配对。**
**扬声器已确认卡在"机器驱动硬编码 dai_link，不解析 DT"这一层，必须改驱动源码 + 重编内核。**

---

## 三、已完成（有实测证据）

| 项 | 状态 | 关键证据 |
|---|---|---|
| 原生 Xorg + XFCE 4.20 | ✅ | 开机自动进入，替代 Phosh |
| 横屏 1920×1200 | ✅ | `xrandr` 实测 |
| 一键切竖屏 | ✅ | `tablet-display-mode` |
| 远程桌面 | ✅ | `:6080/vnc.html` |
| 字体清晰 | ✅ | **三层 DPI 全部 150** + 中文截图确认 |
| 永不自动锁屏 | ✅ | DPMS `600/600/600` → `0/0/0` |
| 触屏中文输入 | ✅ | **实测打出候选词「你好」** |
| 麦克风 | ✅ | `hw:0,1` + 400% 增益 = 13% FS |
| 电池指示器 | ✅ | 面板显示，与 sysfs/upower 一致 |
| 面板自愈 | ✅ | systemd 服务，kill -9 后 4 秒恢复 |
| 回退快照 | ✅ | `tablet-restore-snapshot`，28 文件 |
| 验收 | ✅ | 34 项全部 PASS |

---

## 四、未完成（这是接下来的工作）

> **⚠️ 重要更正（2026-10-24 09:30）**
> 本节原先只列了 3 项（扬声器/休眠/蓝牙）。**做了全硬件普查后发现实际有 9 项缺陷。**
> **完整清单见 `08-HARDWARE-AUDIT.md`**，那一份才是权威。

### 4.0 全硬件缺陷总览（详见 08-HARDWARE-AUDIT.md）

> **⚠️ 传感器一行的结论已被 `09-P0-1-SENSORS.md` 推翻，见下表后的更正。**

| 硬件 | 状态 | 根因 |
|---|---|---|
| **全部传感器（5 个芯片）** | ❌ 驱动在但读不到数据 | `scan_elements` 为空，raw 通道未注册 |
| **摄像头** | ❌ 完全无驱动 | DT 无 camss/cci/csiphy 节点 |
| **GPS** | ❌ 完全无驱动 | 无 `/dev/gnss*`，DT 无节点 |
| **霍尔传感器（保护套）** | ❌ 无驱动绑定 | `qcom-smgr-hall-effect` 未绑定 |
| **扬声器** | ❌ 无声 | 机器驱动硬编码 dai_link |
| **休眠** | ❌ 死锁 | `mdss_runtime_suspend` |
| **GPU（横屏）** | ⚠️ 走 llvmpipe | 已知 rotate+glamor 硬挂死 |
| **充电器识别** | ⚠️ 常退回 500mA | DCP/SDP 识别不稳 |
| **电池元数据** | ⚠️ 缺 health/cycles | 驱动未暴露 |

#### ✅ 传感器一项的重大更正（2026-10-24 09:40，实测）

**"`scan_elements` 为空"是错的。五个传感器的真实状态：**

| 芯片 | 状态 | 证据 |
|---|---|---|
| BOSCH BMI120 加速度计 | ✅ **能读** | `/dev/iio:device2` 实测 `z = -9.81 m/s²` |
| BOSCH BMI120 陀螺仪 | ✅ **能读** | 实测静态 `~0.02 rad/s` |
| AKM AK09918 磁力计 | ✅ **能读** | 实测 `117 µT`（地磁正确） |
| Capella CM3232 环境光 | ⚠️ DSP 拒绝 `0x501` | **DSP 里驱动存在，只缺 registry JSON** |
| ROHM BU52061NVX 霍尔 | ✅ 硬件可用 | **走 gpio-keys 的 SW_LID，不需要 SMGR** |

**已修复**：方向矩阵是镜面（det=-1），用 udev 覆盖 `ACCEL_MOUNT_MATRIX` 修好，
`monitor-sensor` 从 `face-down` 变成 `face-up`。**纯用户态，零风险。**

**新结论：P0-1 不是"修 raw 通道"，而是三个独立问题，详见 `09-P0-1-SENSORS.md`。**

**传感器真实身份（从 `dmesg | grep qcom_smgr` 得到）：**
```
BOSCH BMI120      加速度计 + 陀螺仪
AKM AK09918       磁力计
Capella CM3232    环境光传感器（自动亮度）
ROHM BU52061NVX   霍尔传感器（智能保护套）
```

### 4.1 扬声器无声 —— **下一步主攻方向：改驱动源码**

#### 已经确认的事实链

**1. 数字链路完全正常**
```
PCM RUNNING 48000Hz S16_LE 2ch
PDM_RX3 / SPK DAC / SPK PA / SPK_OUT 全程 On
RX_BIAS On，RX3 增益 124 (40 dB 最大)
```

**2. 声学回环测试证明真的没声音**
```
麦克风 400% 增益（噪声底 rms=688，足够灵敏）
输出关闭 : rms=688.4
播放噪声 : rms=698.5
ratio = 1.01x
```
四条路径（SPK / EAR / HPH / 全开）ratio 全部 ≈ 1.00。

**3. Android 原厂配置指向 PRI_MI2S**
```xml
<!-- vendor/etc/mixer_paths.xml -->
<path name="deep-buffer-playback speaker">
    <ctl name="PRI_MI2S_RX Audio Mixer MultiMedia1" value="1" />
</path>
```
**整个扬声器路径只有这一条控制，不碰 SPK DAC / Digital RX3 / EAR_S。**
说明喇叭接在 PRIMARY MI2S 总线，不在 pm660 模拟功放上。

**4. 硬件排查：没有独立 I2C 功放**
```
I2C 设备只有: gt9110（触屏）, lp8556（背光）
DT 里无 spk/amp 节点
```

**5. 改 DTB 加 pri-mi2s-dai-link —— 已实测无效**

2026-10-24 已刷入带补丁的 boot 镜像，结果：

```
✅ DTB 补丁确实生效
   live fdt: 63429 bytes (原 63233，+196)
   dtc 反编译可见 "pri-mi2s-dai-link" 和 "Primary MI2S Playback"
   设备正常启动，SSH 20 秒恢复，桌面完好

❌ 但驱动忽略了它
   PCM 设备仍只有 MultiMedia1 / MultiMedia2
   PRI widget 数 = 0
   asoc 组件列表无新增
```

**6. 根因：机器驱动硬编码 dai_link 表，不解析 DT**

对 `snd-soc-sdm660-int.ko` 做 strings 分析：

```
✅ 驱动认识这些时钟:
   pri_mi2s_clk_count
   int0_mi2s_clk_count
   int3_mi2s_clk_count
   pri_tdm_clk_count
   sec_tdm_clk_count

❌ 但驱动没有这些字符串:
   （完全搜不到 sound-dai / link-name / dai-link）
```

**结论：`snd-soc-sdm660-int` 用的是静态 `struct snd_soc_dai_link[]` 数组，
不遍历 DT 的 `dai-link` 子节点。所以加 DT 节点无效。**

#### 下一步要做的（改源码 + 重编内核）

**目标文件**（上游 pmOS / mainline 内核）：
```
sound/soc/qcom/sdm660.c        或
sound/soc/qcom/common.c        或
sound/soc/qcom/sdm660-int.c
```
需在构建 VM 上确认实际文件名。

**要改什么**：
1. 找到静态 `snd_soc_dai_link` 数组
2. 增加一条 `PRI_MI2S_RX` 的播放链路，参照现有 `int0-mi2s-dai-link`：
   ```c
   {
       .name = "Primary MI2S Playback",
       .stream_name = "Primary MI2S Playback",
       .cpu_dai_name = "PRI_MI2S_RX",        /* 注意短名 */
       .platform_name = "q6routing",
       .codec_dai_name = "msm8916_wcd_analog",
       .codec_name = "800f000.spmi:pm3:audio-codec@f000",
   }
   ```
3. **关键不确定点**：q6afe 的 DAI 名在这个内核里是短名 `PRI_MI2S_RX`
   （不是上游的 `PRIMARY_MI2S_RX`），DAI id 是 `1` 还是别的需要确认
4. 或者改用 DT 解析方式（`snd_soc_of_parse_card_name` + `dai-link` 遍历），
   这样更通用但要重写整个 probe

**验证方法**（改完后）：
```bash
# 1. 新的 PCM 设备应该出现
cat /proc/asound/devices

# 2. asoc 组件列表应该多一项
ls "/sys/kernel/debug/asoc/Xiaomi Mi Pad 4/"

# 3. 然后做声学回环测试
sh tools/speaker_contrast.sh    # ratio > 3 = 成功
```

#### 已知的三个误判（写下来避免重复踩坑）

| 错误判断 | 真相 |
|---|---|
| "DAPM On 就是有声音" | DAPM 只证明寄存器写成功 |
| "codec 的 DT 节点几乎空白" | 节点完整（14 个中断、jack 检测、micbias） |
| "PCM 缓冲区不流动" | ALSA 的 status 在 RUNNING 时不报 delay/avail 字段 |

---

### 4.2 真休眠 —— 内核 mdss 死锁

**根因**（`/var/log/mdss-suspend-bug.txt` 记录）：
```
clk_branch_toggle → clk_core_disable → mdss_runtime_suspend [msm]
  → mdss_pm_suspend → device_suspend → dpm_suspend → pm_suspend
```
关 MDSS 时钟时死锁，记录有 42 次 `hard LOCKUP on cpu 5`。

**没有任何安全测试手段**：
```
/dev/watchdog            不存在
watchdog 内核模块         未加载
CONFIG_PM_TEST_SUSPEND   未编译
```
任何测试都要物理按电源键恢复。

**已做的缓解**：`mdss-pm-pin.service` 把显示控制器固定 runtime-active。
**替代方案**：`tablet-sleep` 伪眠（实测 `200→0→200`，Xorg/xfwm4 全程存活）。

**下一步**：需要查 upstream msm/dpu 的 `runtime_suspend` 实现，
或考虑在 suspend 时跳过 mdss 的 PM 回调（hacky 但可能有效）。

---

### 4.3 蓝牙键鼠 —— 未配对

主机侧全部就绪：
```
hidp / uhid 已加载
AlwaysPairable = true
agent 已注册（org.bluez.Agent1）
DiscoverableTimeout = 0
```

**但从未与真实设备配对过。** 需要用户把键鼠打到配对模式。

---

## 五、响应速度与应用生态（办公电脑目标）

### 当前性能数据
```
CPU busy : 0.2%（空闲）
内存     : 1.3G / 3.5G
续航     : 约 5-6 小时（纯电池 3.3W）
```

### 已做的优化
| 处理 | 效果 |
|---|---|
| 关闭窗口合成器 | llvmpipe 下每帧都耗 CPU |
| 禁用 tumblerd/goa-daemon/wireplumber/gsd-*/localsearch/mmsdtng/geoclue/phosh-tour | 释放 ~300MB |
| 停用常驻 x11vnc/novnc | 之前占 10% CPU |
| 杀掉重复 fcitx5 | 省 81MB |
| 面板 systemd 自愈 | 崩溃 4 秒恢复 |

### 办公电脑还缺什么（需评估）
- [ ] 办公套件（LibreOffice？当前未装）
- [ ] 浏览器（当前未确认）
- [ ] 文件管理（Thunar 已有）
- [ ] 终端（xfce4-terminal 已有）
- [ ] 截图工具（scrot 已有）
- [ ] PDF 阅读
- [ ] 打印支持
- [ ] 蓝牙键鼠（4.3）

---

## 六、环境与访问

### 设备
```bash
ssh user@192.168.1.123     # 密码 <SUDO_PASSWORD>
# sudo: echo '<SUDO_PASSWORD>' | sudo -S <cmd>
```

**硬性规则**：
- 所有 `pactl` / `systemctl --user` / `xfconf-query` / `gsettings`
  **必须在 user 身份下执行**：
  ```bash
  sudo -u user env XDG_RUNTIME_DIR=/run/user/10000 HOME=/home/user <cmd>
  ```
- 在 SSH 里启动 GUI 程序必须 `setsid ... </dev/null`，否则 SSH 挂起

### fastboot（本机 Windows）
```
D:\APPS\platform-tools\fastboot.exe
设备 serial: 27eec4d2，product: clover，unlocked
```

**恢复命令**（平板不启动时）：
```powershell
& "D:\APPS\platform-tools\fastboot.exe" flash boot pmos-boot2.img
& "D:\APPS\platform-tools\fastboot.exe" reboot
```

### 构建 VM
```
192.168.1.200  —— 当前关机，需要时手动开机
用途：重编内核
```

---

## 七、关键文件与工具

### 项目文档
| 文件 | 内容 |
|---|---|
| `00-GOAL.md` | **本篇**，总目标与路线 |
| `HANDOFF.md` | 交接：状态、紧急恢复、文件地图、TODO |
| `07-xorg-xfce.md` | 桌面改造全部细节（18 章） |
| `04-build-log.md` | 构建记录 |
| `05-android-collection.md` | Android 固件分析 |
| `06-xfce-experiment.md` | XFCE-under-Phosh 失败记录 |

### 设备上的关键脚本
```
/usr/local/bin/xfce-tablet-session     会话主脚本（旋转/DPI/触控/输入法）
/usr/local/bin/xfce-x-session          启动 Xorg :0
/usr/local/bin/tablet-session-launcher 90s 看门狗
/usr/local/bin/tablet-display-mode     竖/横切换
/usr/local/bin/tablet-audio            扬声器/耳机切换
/usr/local/bin/tablet-sleep            伪休眠
/usr/local/bin/tablet-battery-status   电池 → genmon XML
/usr/local/bin/tablet-restore-snapshot 回退
/usr/local/bin/restore-phosh           回退到 Phosh
```

### 音频相关工具（本会话写的，可复用）
```
tools/speaker_contrast.sh      声学回环测试（黄金标准，ratio>3=有声音）
tools/max_gain_test.sh         最严格版本（400% 增益 + 白噪声 + 稳态窗口）
tools/port_sweep2.sh           扫描所有 RX 端口看哪个能点亮链路
tools/reg_decisive.sh          播放中采样 DAPM
tools/dtb_prepare.sh           从 boot 分区提取 DTB
tools/build_pri_dtb.sh         构建带 pri-mi2s-dai-link 的 DTB
tools/pack_boot2.sh            重打包 boot.img
```

### 关键镜像（本地 `mipad4plus/tools/`）
```
pmos-boot2.img         25,653,248 B   ← 恢复基线（ANDROID! 完整）
pmos-boot-nozap.img    25,653,248 B
pmos-boot.img          25,636,864 B
pmos-rootfs3.img       2,562,719,744 B
boot-pri-mi2s.img      25,653,248 B   ← 本次刷入的补丁版（已证明无效但无害）
patched.dtb            62,664 B
tablet-good-state.tar.gz              ← 配置快照
```

---

## 八、设备当前实际状态（2026-10-24 09:00）

```
boot 分区    = boot-pri-mi2s.img（补丁版，已证明驱动不认，但设备正常运行）
live fdt     = 63429 bytes（含 pri-mi2s-dai-link）
内核         = 7.0.14-sdm660
桌面         = 1920x1200 横屏，DPI 150，llvmpipe
电池         = 面板显示 ⚡ XX%，与 sysfs 一致
CPU          = 0.2%
```

**⚠️ 新会话第一件事建议**：决定是否把 boot 刷回 `pmos-boot2.img` 恢复干净状态。
刷回命令见第六节。**不刷也不影响使用**（补丁版只是多了一条驱动忽略的 DTB 节点）。

---

## 九、方法论（本会话总结，值得继承）

### 1. 不要相信 DAPM 状态
`DAPM On` 只证明寄存器写成功，**不证明有信号**。
验证音频必须用**声学回环**：播放 → 空气 → 麦克风录音 → 频谱/RMS 对比。

### 2. 测试设计决定结论可信度
- 麦克风增益太高（400%）会掩盖真信号 → 噪声底淹没
- 单频正弦不如白噪声容易检测
- 用 RMS 平均值会掩盖瞬态 → 要看滑动窗口
- 必须采样**稳态窗口**，避开切换瞬态

### 3. ALSA 的坑
`/proc/asound/card0/pcm0p/sub0/status` 在 RUNNING 状态**不报** `delay`/`avail`
字段，只报 `state`。别据此判断"缓冲区不流动"。

### 4. 改 DTB 与改驱动的分界
- DTB 能改：节点属性、设备树连接
- DTB 改不了：驱动源码里硬编码的 `struct snd_soc_dai_link[]` 数组
- 判断方法：`strings <module>.ko | grep 'sound-dai\|link-name\|dai-link'`
  —— 没有就是硬编码

### 5. 每次改动都留回退
- 快照：`tablet-restore-snapshot`
- boot 镜像：`pmos-boot2.img`
- 三层安全网：launcher 看门狗 → force-phosh → getty

---

## 十、下一步执行计划（按优先级，可直接照做）

### P0-1 · 传感器 —— ✅ **调查已完成，结论在 `09-P0-1-SENSORS.md`**

> **不要重做调查。** 全部证据、根因、改动清单都在 09 文档里。
> 本节只留一句话状态 + 指向。

**已完成**：
- ✅ 加速度计/陀螺仪/磁力计**数据一直是好的**（08 文档误判）
- ✅ 方向矩阵镜面 bug 已用 udev 修好（`face-down` → `face-up`，实测）
- ✅ DSP 固件验尸完成：`adsp.b13` 有完整 `sns_dd_cm3232`（104 符号），**无 hall 驱动**

**剩余事项**：

| # | 事项 | 要编内核 | 风险 | 状态 | 文档 |
|---|---|---|---|---|---|
| 1 | 自动旋转 + 合盖休眠 | ❌ | 零 | ✅ **已启用** | 10 |
| 2 | 保护套休眠实测 | ❌ | 零 | ⏸ 待磁铁 | 10 |
| 3 | ~~补 `cm3232.json`~~ | ❌ | — | ❌ 取消 | 11 |
| 4 | `data_type` → 1（补丁 1） | ✅ | 低 | ✅ **成功** | 13 |
| 5 | 采样率回退（补丁 2） | ✅ | 低 | ✅ **成功** | 15 |
| 6 | **自动亮度** | ❌ | 零 | ✅ **已启用** | 14 |
| 7 | 写 `qcom_smgr_hall.c` | ✅ | 中 | 可行，优先级低 | 11 §2.3 |
| 8 | 扬声器/摄像头/GPS | ✅ | 高 | 未开始 | 08 |

**✅ 本次会话交付的两个可用功能**：
```
tablet-autobright   自动亮度            enabled + active   实测 39~141 lx 调光
tablet-orientd      自动旋转+合盖休眠    enabled + active   已修硬编码设备号
```

**⭐⭐ 修 ALS 需要两个补丁（关键认知）**：

```
补丁 1（13 文档）：data_type 按传感器类型选择，ALS → SECONDARY(1)
  → 解决 0x501，buffer 能 enable
  → 但每个样本都是 0！

补丁 2（15 文档）：采样率回退
  qcom_smgr_request_buffering() 声明 u16 sample_rate = 0;
  只从 native_sample_rates[] 或 max_sample_rate 赋值，
  【从不读 cur_sample_rate】。
  CM3232 两者都是 0 → report_rate = 0 → DSP 接受但不产生样本。
  → 回退到 cur_sample_rate，再回退到 10 Hz
  → ALS 才真正出数据
```

**⭐ 三条最重要的教训**：
```
1. 内核"黑屏" ≠ "没启动"。先 journalctl --list-boots + journalctl -b -N。
   （查 4 次 dmesg 没线索，一查历史 journal 就看到 "failed to validate module [qrtr] BTF: -22"）

2. sysfs 可写 ≠ 变量被使用。
   in_proximity_sampling_frequency 能写能读回，但请求函数根本不读那个变量。
   要追到"真正发出去的那一行"。

3. "设备能 enable 但读不到数据" 八成是请求里某个字段是 0。
   顺着"用户能改的变量 → 实际发出的字段"走一遍，就能找到断点。
```

**详细改动清单 → `09-P0-1-SENSORS.md` §6（注意：§3 的 ALS 根因已被 11 推翻）
**真因 + 补丁 → `11-REGISTRY-EXPERIMENT.md` §9**
**刷机失败记录（含 9 个已排除项）→ `12-FLASH-ATTEMPT.md`**
**✅ 成功记录 → `13-ALS-SUCCESS.md`**
**✅ 自动亮度 → `14-AUTO-BRIGHTNESS.md`**

---

### P0-2 · 扬声器（改驱动源码 + 重编内核）

**已排除**：改 DTB 加 `pri-mi2s-dai-link` **实测无效**（见 `07-xorg-xfce.md` §9.10）。

**根因**：`snd-soc-sdm660-int` 用静态 `struct snd_soc_dai_link[]`，
probe 时不读 DT。证据：模块里**搜不到** `sound-dai` / `link-name` / `dai-link`。

**要做**：
1. 开机 VM `192.168.1.200`
2. 拉 pmOS 内核源码，定位 `sound/soc/qcom/sdm660*.c`
3. 找到静态 dai_link 数组，参照 `int0-mi2s-dai-link` 加一条：
   ```c
   .name           = "Primary MI2S Playback",
   .stream_name    = "Primary MI2S Playback",
   .cpu_dai_name   = "PRI_MI2S_RX",     /* 注意短名！ */
   .platform_name  = "q6routing",
   .codec_dai_name = "msm8916_wcd_analog",
   .codec_name     = "800f000.spmi:pmic@3:audio-codec@f000",
   ```
4. **关键不确定点**：q6afe 的 DAI id 是否就是 `1`。
   需在源码里对照 `q6afe-dai.c` 的 `q6afe_dai_data[]` 数组确认。
5. 重编 → 出 `boot.img` → 刷入
6. **验证用声学回环**：`sh tools/speaker_contrast.sh`，`ratio > 3` 才算成功

**风险控制**：`tools/pmos-boot2.img` 是已验证的恢复基线。

---

### P0-3 · 蓝牙键鼠（需用户操作）

主机侧已就绪：
```
hidp / uhid 已加载
AlwaysPairable = true
agent 已注册
DiscoverableTimeout = 0
```

**需要用户**把键盘/鼠标打到配对模式，然后：
```bash
bluetoothctl scan on          # 找到 MAC
bluetoothctl pair <MAC>
bluetoothctl trust <MAC>
bluetoothctl connect <MAC>
```

---

### P1-1 · 霍尔传感器（智能保护套）

```
/sys/bus/platform/devices/qcom-smgr-hall-effect.80   ← 有设备，无 driver 绑定
modalias: platform:qcom-smgr-hall-effect
```

**但** `gpio-hall-sensor` 作为 input 设备已存在（event3），
说明硬件在采数据，只是没走 SMGR 的 IIO 通道。

**先试**：`timeout 3 cat /dev/input/event3 | od -An -tx1`
合上/打开保护套（或磁铁靠近），看有没有事件。
有事件就能做 udev 规则触发 `tablet-sleep`。

---

### P1-2 · 休眠死锁

**根因**（`/var/log/mdss-suspend-bug.txt`）：
```
clk_branch_toggle → mdss_runtime_suspend → device_suspend → dpm_suspend
```
关 MDSS 时钟时死锁，42 次 `hard LOCKUP on cpu5`。无 watchdog、无 `pm_test`。

**可能方向**：
- 查 upstream msm/dpu 的 `runtime_suspend` 是否有已知修复
- 或在 suspend 路径跳过 mdss 的 PM 回调（hacky 但可能有效）
- 已做的缓解：`mdss-pm-pin.service`

**风险**：任何测试都要物理按电源键恢复。

---

### P1-3 · GPU 横屏加速

**现状**：横屏强制 llvmpipe（`50-msm-soft.conf` 的 `AccelMethod "none"`）。
原因：`xrandr --rotate` + glamor 会硬挂死 a5xx ring（已发生一次，需物理重启）。

**可能方向**：
- 试 `rotation` 走 DRM plane 的 `rotate-180`（硬件支持 0/180），
  配合面板本身翻转解决 90° 需求
- 或查 freedreno 对 a5xx 旋转的已知 bug

---

### P2 · 摄像头 / GPS（可能无解）

**摄像头**：DT 里没有 camss/cci/csiphy 节点，内核无 camss 驱动。
先查 mainline 对 SDM660 camss 的支持状态。若无，需从零写驱动，成本极高。

**GPS**：无 `/dev/gnss*`，DT 无节点。同理。

**建议**：这两项先确认上游状态，再决定是否投入。

---

### P2 · 待确认项

| 项 | 怎么测 |
|---|---|
| 振动马达 | 全系统搜不到 haptic 节点，可能这颗平板没有 |
| SD 卡槽 | 插卡后 `dmesg \| grep mmc`，看 `mmc2` 是否出现设备 |
| USB OTG host | 接 U 盘，看 `lsusb` 是否有输出 |

---

### P2 · 办公软件盘点（还没做）

下次会话第一件事应该是**实际检查装了什么**：
```bash
for p in firefox chromium libreoffice evince okular thunderbird; do
  apk info -e $p >/dev/null 2>&1 && echo "有 $p" || echo "无 $p"
done
```

按办公电脑需求补齐。

---

## 十一、新会话的起手式

```bash
# 1. 确认设备在线
ssh user@192.168.1.123 'uname -r; cat /sys/class/power_supply/qcom-battery/capacity'

# 2. 读文档（按顺序）
#    00-GOAL.md（本篇）→ 08-HARDWARE-AUDIT.md（9 项缺陷全清单）
#    → HANDOFF.md → 07-xorg-xfce.md §9（音频完整调查）

# 3. 决定 boot 是否刷回干净状态
#    当前是 boot-pri-mi2s.img（补丁版，已证明驱动不认，但无害）
#    fastboot flash boot pmos-boot2.img   可恢复

# 4. 按 P0-1 → P0-2 → P0-3 顺序推进
```

**一句话记住当前处境：**
> 桌面能用（1920×1200 + 中文输入 + 麦克风 + 电池显示），
> 但**传感器全废、摄像头无驱动、GPS 无驱动、扬声器无声、休眠死锁**。
> 扬声器已证明「改 DTB」无效，必须改驱动源码重编内核。
> 传感器最可能是固件 `sns.reg-xiaomi,clover-plus` 缺失。
