## 索引（按时间倒序，最新的在最上面）

| 文档 | 内容 | 状态 |
|---|---|---|
| [66-SESSION-2026-10-31.md](66-SESSION-2026-10-31.md) | **全天总结：自编译内核、IPA/TZ 结论、GPS 更正、相机色彩、前摄/指纹、SIM/WiFi 耦合与踩坑教训** | ⭐ 最新 |
| [65-GPS-QMI-FINDINGS.md](65-GPS-QMI-FINDINGS.md) | GPS 实测：**QMI 节点是 0**；LOC 服务可用但从未拿到坐标；与 4G 同源 | ✅ |
| [64-UPSTREAM-IPA-REPORT.md](64-UPSTREAM-IPA-REPORT.md) | **可提交上游：IPA 核心时钟顺序 bug 补丁 + SDM660 IPA 访问性结论（含全部排除项证据表）** | ✅ |
| [63-CUSTOM-KERNEL-AND-TZ-TEST.md](63-CUSTOM-KERNEL-AND-TZ-TEST.md) | **自编内核成功启动整机（BTF 两处修复）；TZ 的 SCM_SVC_MP/0x10 解锁调用可达但返回 -EIO** | ✅ |
| [62-KERNEL-SCM-ATTEMPT.md](62-KERNEL-SCM-ATTEMPT.md) | **内核侧 SCM 解锁尝试：找到 TZ XPU 锁；早期自编内核无法启动的原因分析** | ✅ |
| [61-IPA-ICC3-NEGATIVE.md](61-IPA-ICC3-NEGATIVE.md) | **A 方案结论：三条 ICC 路径全投票成功、modem 稳定、时钟已开，IPA 页仍 stall → 非时钟/ICC/DT 问题** | ✅ |
| [60-MODEM-CRASH-FIX.md](60-MODEM-CRASH-FIX.md) | **修复 modem 崩溃循环（MSS memory banks 28→29，上游补丁）；WiFi 不再被带崩** | ✅ |
| [59-LTE-BRINGUP-PLAN.md](59-LTE-BRINGUP-PLAN.md) | **4G 上主线的完整执行清单：依赖链、已确证事实、5 步计划与风险评估** | ✅ |
| [58-IPA-FIRMWARE-ROOT-CAUSE.md](58-IPA-FIRMWARE-ROOT-CAUSE.md) | **IPA 卡点定位：缺 ipa_fws 固件加载；本机 TZ PAS 待用 `qcom_mdt_load` 复核** | ✅ |
| [57-VENDOR-KERNEL-RE-TOOLCHAIN.md](57-VENDOR-KERNEL-RE-TOOLCHAIN.md) | **原厂内核反编译工具链：VM+REA+Ghidra 可用；发现 vendor-kernel 实为 gzip@0x800，已解出 42MB 真 Image** | ✅ |
| [56-IPA-MARKER-RESULTS.md](56-IPA-MARKER-RESULTS.md) | **IPA 打点实证：通道可用；M1–M4 通、core 寄存器页不可达；驱动级链路已走通，ICC/时钟/QMP 假设均否证** | ✅ |
| [55-IPA-MARKER-HANDOFF.md](55-IPA-MARKER-HANDOFF.md) | **4G/IPA 攻关记录与交接：已排除路线 + p12 打点方案（下次起点）** | 📜 已承接 |
| [54-WAYLAND-GPU-AUTOROTATE.md](54-WAYLAND-GPU-AUTOROTATE.md) | Wayland LXQt + GPU 加速 + 四方向自动旋转（收官） | ✅ 现行 |
| [53-OTHER-HARDWARE-RE.md](53-OTHER-HARDWARE-RE.md) | 其他硬件反编译：GPU 固件找到、SD/振动/前摄/指纹结论 | ✅ |
| [52-IPA-PORT-PLAN.md](52-IPA-PORT-PLAN.md) | IPA 移植：资源反编译（SRAM/时钟/ICC）+ 实机挂死记录 | 🔬 进行中 |
| [51-GPU-NOZAP-AND-LTE.md](51-GPU-NOZAP-AND-LTE.md) | GPU nozap 失败与恢复 + LTE 射频实测 + 稳定性取舍 | ✅ |
| [50-LANDSCAPE-FBDEV.md](50-LANDSCAPE-FBDEV.md) | 横屏成功：fbdev 竖屏面板旋转补丁 + 触摸矩阵 + 回滚 | ✅ 现行 |
| [49-STATE-2026-10-30.md](49-STATE-2026-10-30.md) | GPU 卡死原因、modem/IPA 真相、横屏驱动补丁 | ✅ |
| [48-HANDOFF-2026-10-30.md](48-HANDOFF-2026-10-30.md) | 交接文档：硬件全量核对 + 遗留问题清单 | ✅ |
| [47-FBDEV-DISPLAY-PATH.md](47-FBDEV-DISPLAY-PATH.md) | 黑屏最终解法：改用 fbdev 驱动（当前基础） | ✅ 现行 |
| [46-KERNEL-DPU-PATCH.md](46-KERNEL-DPU-PATCH.md) | 内核 DPU 补丁尝试（已回滚，结论保留） | ⚠️ 已回滚 |
| [45-BEAUTIFICATION.md](45-BEAUTIFICATION.md) | 美化：配色、面板稳定性、Papirus 空包、customcommand 陷阱 | ✅ |
| [44-ROTATION-AND-TOUCH.md](44-ROTATION-AND-TOUCH.md) | 旋转与触摸：DPU 旋转缺陷、libinput 校准矩阵、重力自动旋转 | ✅ |
| [43-CAMERA-PIPELINE.md](43-CAMERA-PIPELINE.md) | 相机管线（后摄已验证出图，前摄 NACK） | ✅ 部分 |
| [42-DESKTOP-GPU-DPU-LXQT.md](42-DESKTOP-GPU-DPU-LXQT.md) | 桌面 GPU/DPU/LXQt 早期排查 | ✅ |
| [36-EVENING-CHECKLIST.md](36-EVENING-CHECKLIST.md) | 晚上回来怎么恢复 + 修 GPU | 📜 历史 |

## 快速状态（2026-10-30 12:40，重启后验证）

- **显示**：fbdev + 自编旋转驱动，**1920×1200 横屏**（面板 1200×1920 软件旋转，重启自动恢复）
- **触摸**：libinput Calibration Matrix `0 -1 1 1 0 0`（udev 持久化，重启后 default 即为该值）
- **网络**：WiFi 192.168.1.100；USB hub 有线 eth0 192.168.1.4（救命通道）
- **modem**：QMI 可用、LTE 射频可注册（-63 dBm），但固件会崩并带崩 WiFi → 目前保持 shutting-down，ModemManager/modem-online 已禁用
- **GPU**：未初始化（原状）；nozap 刷机尝试失败已 fastboot 回滚，不再碰 boot 分区
- **已停服务**：`tablet-autorotate`、`tablet-touch-rotate`、`ModemManager`、`modem-online`

## 硬件一句话总结

| 能用 | 部分可用 | 不可用 |
|---|---|---|
| 屏幕（横/竖）、触摸、WiFi、有线网、蓝牙、音频、电池、背光、加速度计/陀螺仪/磁力计/霍尔/ALS | 摄像头（后摄可用/前摄 NACK）、指纹（仅输入设备）、调制解调器（QMI/LTE 射频可用但固件不稳） | GPU（Adreno 512）、GPS、手写笔、SD 卡、振动马达 |
