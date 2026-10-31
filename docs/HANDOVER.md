# 小米平板4 Plus (clover-plus) 硬件移植 — 完整交接文档

> 最后更新：2026-10-28 12:20
> 设备：192.168.1.29（user/<SUDO_PASSWORD>），构建机：192.168.1.200（user/<VM_PASSWORD>）
> 系统：postmarketOS edge + 主线内核 `7.0.14-sdm660`（boot r181）

---

## 1. 当前状态总览

**全硬件自检 17/17 PASS**（`sudo pad_selftest`）

| 硬件 | 状态 | 证据 |
|---|---|---|
| 屏幕 / 触摸 | ✅ | Goodix 触摸工作 |
| WiFi / 蓝牙 | ✅ | 已连接 |
| 音频 | ✅ | `plughw:0,0` 播放 0.5s 正常 |
| USB | ✅ | 2 个设备 |
| **后摄 OV13855** | ✅ | 拍照 16,558,080 字节 |
| **光线传感器** | ✅ | ALS 73 lx → 背光 139（闭环）|
| **霍尔传感器** | ✅ | 新驱动 `qcom-smgr-hall`，开合正常 |
| **OTG 供电** | ✅ | `otg_vbus` 0→1→0 |
| **指纹（检测）** | ✅ | HWID `0x0341` 应答；触摸中断工作 |
| **指纹（成像）** | 🔧 | 配置与厂商 rev-4 逐字节一致，但图像不随手指变化 |
| 调制解调器 | ✅ | remoteproc 运行 + QMI 应答 |
| GPU | ✅ | devfreq 19.2 MHz |
| 电池 | ✅ | 98% 充电中，39°C |
| systemd | ✅ | **0 个失败单元** |
| **前摄 S5K5E8** | ❌ | i2c 4-0010 无响应（硬件）|
| **venus 硬解** | 🔧 | AXI 时钟修复后**核心打通**（19/19 自检全绿），会话初始化仍不响应 |

---

## 2. 关键工具与环境

### 2.1 辅助脚本（本机 `tools/`）
```powershell
python tools\ssh_pad.py '命令'          # 在设备上执行（sudo 用 P=<SUDO_PASSWORD>）
python tools\put_pad.py 本地 远程       # 推文件到设备
python tools\get_pad.py 远程 本地       # 从设备取文件
python tools\ssh_vm.py '命令'           # 在构建机上执行
python tools\scp_vm.py 本地 远程        # 推到构建机
python tools\get_vm.py 远程 本地        # 从构建机取
```

### 2.2 构建流程（改内核补丁）
```powershell
# 1. 改 tools/fpc1020.c 等源文件
# 2. 重新生成补丁
python tools\rebuild_driver_patch.py
# 3. 推到构建机的 pmaports
python tools\scp_vm.py tools\0035-fpc1020-driver.patch <pmaports路径>/0035-fpc1020-driver.patch
# 4. 构建机上递增 pkgrel 并构建（约 2-4 分钟，ccache）
python tools\ssh_vm.py 'D=~/.local/var/pmbootstrap/cache_git/pmaports/device/testing/linux-postmarketos-qcom-sdm660; sed -i "s/^pkgrel=N/pkgrel=N+1/" $D/APKBUILD; cd ~ && export PATH=$HOME/.local/bin:$PATH && (setsid nohup sh -c "pmbootstrap checksum linux-postmarketos-qcom-sdm660 && pmbootstrap build linux-postmarketos-qcom-sdm660 --force" > /tmp/build.log 2>&1 &)'
# 5. 取模块并装到设备
python tools\get_vm.py /tmp/fXX/.../xxx.ko.zst tools\xxx.ko.zst
python tools\put_pad.py tools/xxx.ko.zst /tmp/xxx.ko.zst
# 6. 设备上：cp 到 /usr/lib/modules/... && reboot
```

### 2.3 🎯 VM 上可用完整 REA（重要）
```sh
# 构建机 192.168.1.200
export GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC
rea doctor        # 全绿

rea analyze <elf> --format json
rea function <elf> --procedure FUN_xxxx --format json --filter-output normalized_result.pseudocode
rea search <elf> --pattern HFI --mode literal
rea xrefs <elf> 0x地址 --format json --filter-output normalized_result
rea search-bytes <elf> "00 20 0d e0"
```
**注意**：Windows 上的 REA **不支持 ELF/ARM**（只接受 PE / raw 6502）。
所有 ARM 固件分析必须走 VM。

### 2.4 代理
`192.168.1.151:16514`（http:// 或 socks5h://），用于 GitHub 等被墙站点。

---

## 3. 指纹 FPC1020（HWID 0x0341）

### 3.1 已确认的事实
```
SPI 1MHz，mode 0
id[0xfc] = 03 41                 HWID
AVDD=GPIO98  VDDIO=GPIO92  RESET=GPIO108(低有效)  IRQ=GPIO71
0x24 武装后触摸 → IRQ 触发（计数 104→105）
```

### 3.2 🎯 芯片是 revision 4（关键发现）
寄存器宽度实测：`0x8C`=2B、`0xA8`=3B、`0x90`=9B —— 正是厂商 rev4 的宽度。
（rev3 是 1/2/8；rev5 的 0xA8 是 4B，实测 4B 会丢首字节，排除）

### 3.3 rev-4 正确配置（已写入驱动 r199）
```
0x54 = 00 08 00 b0       IMG_CAPT_SIZE（见 3.4）
0x5C = 03                IMAGE_SETUP
0x8C = 00 1F             FINGER_DRIVE_CONF   (2 字节)
0x78 = 00 00             TST_COL_PATTERN_EN
0xA0 = 00 00             ADC_SHIFT_GAIN
0xA8 = 00 0F 01          PXL_CTRL            (3 字节)
0x6C = 0A                PXL_RST_DLY
0x90 = 0D 3F 3F 3F 3F 00 00 00 00   FINGER_DRIVE_DLY (9 字节)
0x68 = 01 00 00 00 14 14 14 14 14   SAMPLE_PX_DLY    (9 字节)
```
另外 `fpc1020_vendor_init()` 对 `0x94/0xEC/0xAC/0xDC/0xD8` 做读-改-写。

### 3.4 🎯 IMG_CAPT_SIZE 的行数决定真实数据量
```
0xB0000800 → [0, 8,0,176]   只有  8 行真实（厂商只做匹配扫描）
0xB0001000 → [0,16,0,176]   16 行真实
0xB0002000 → [0,32,0,176]   32 行真实
0xB0004000 → [0,64,0,176]   64 行真实 ← 完整帧
```
其余行是 `0xBD/0xC0` 交替填充值。**已固化到 `/etc/modprobe.d/fpc1020.conf`**

### 3.5 驱动参数（r199/r200）
```
img_capt_size=0xB0004000   read_len=11266
capture_delay_ms=20        reset_before_capture=0
skip_config=0              test_pattern=0
adc_gain / pxl_ctrl / pxl_rst_dly / finger_drive_conf / image_setup
```
设备上的诊断脚本：`pad_fp_check` `pad_fp_dump` `pad_fp_regs` `pad_fp_rows`
`pad_fp_sweep` `pad_fp_probe` `pad_fp_testpat`

### 3.6 仍未解决
**图像内容不随手指变化。** 证据：
- 24 帧按压/抬起循环：mean 恒定 193~197，无台阶
- 暗帧 vs 手指帧：mean 完全相同
- 二维自相关 dx=8 强周期（0.705），7 种去交织公式最低只到 0.403
- 但触摸中断正常工作 → **电容检测活着，图像读出不响应**

### 3.7 已排除的假设
| 假设 | 结论 |
|---|---|
| 寄存器写入没生效 | ❌ 9/9 精确匹配（rev4 值）|
| 写短了导致右对齐错位 | ✅ 已修正（0x8C/0xA8/0x90 各 +1 字节）|
| 采集前需要软复位 | ❌ 加/不加都平坦 |
| 测试图案能出结构 | ❌ 0x78 只改电平 |
| 位深 16 位 | ❌ rev3 不支持，0x4C bit2 已是 8 位 |
| 采集未完成就读取 | ❌ 0xC0 后 10ms 内 bit5 就置位 |
| 电容检测失效 | ❌ IRQ 正常触发 |

### 3.8 第 9 个排除：读图命令第二字节
加了参数 `read_cmd_param`，扫 0~4：
```
0 → uniq 39   1 → 29   2 → 29   3 → 28   4 → 27
```
0（厂商值）最好，**第二字节无实质影响**。

### 3.9 结论：怀疑硬件
**配置/协议/时序/布局全部与厂商一致，但成像对 finger 无响应，而电容检测正常。**
检测通路与成像通路是分开的 —— 最可能是**成像/模拟前端硬件故障**。

旁证：
- `0x38` 错误寄存器曾读到 `01`
- 暗帧与手指帧 mean 完全相同
- dx=8 固定图案与手指无关

**彻底确认方法**：在 Android 原系统里试指纹 —— 若那边也拍不出图，即硬件故障。
软件侧已无更多可做的。

### 3.10 驱动健壮性（已确认无害）
```
IRQ 计数 10（无中断风暴）  无 wakeup 源（不会唤醒设备）
参数全部默认  自检 17/17
```

---

## 4. venus 硬件解码

### 4.1 现状
```
固件启动成功：pc_ready=1，cs0=0x101，启动期发 3 次中断
但：q0(命令队列) rd=0 wr=3   ← 驱动写了 3 个包，固件一个都没读
    q1(消息队列) rd=0 wr=0   ← 固件什么都没回
    INIT_DONE 永远不来
```

### 4.2 主机侧已逐项确认正确
```
hfi_version = 3XX（与固件 "v3" 匹配）
sfr_da 分配成功（0xd8bfe000）
队列表地址 0xd8c00000 已写入 UC_REGION_ADDR(0x64) 和 CPU_CS_SCIACMDARG2(0x54)
队列头字段 type/start/q_size 全对
主机→固件软中断 0x8000 每个包都发（venus_soft_int）
DT 有 iommus 属性
```

### 4.3 已排除的 8 个假设
1. 固件版本（换原厂固件后 pc_ready=1，改善但不够）
2. 队列表头 284B vendor 布局（移除后仍超时）
3. INIT 超时太短（5 秒仍超时）
4. 队列寄存器没写（与厂商源码一致）
5. HFI 发包版本（v3/v4 都超时）
6. 固件 CLK_DN 握手（本固件走 WA 1.1，不发 CLK_DN_REQ）
7. SFR 分配失败（sfr_da 正常）
8. `CPU_CS_H2XSOFTINTEN`（写了仍无效）

### 4.4 🎯 根因：`video_axi_clk` 是 0 Hz（主线 bug）

实测 `/sys/kernel/debug/clk/clk_summary`：
```
video_axi_clk            enable=5  rate=0        ← 使能了但速率 0
throttle_video_axi_clk   enable=5  rate=0
axi_clk_src              enable=0  rate=384000000
video_core_clk           rate=441600000
video_ahb_clk            rate=80799990
```
**AXI 总线时钟 0 Hz → venus 核心读不到 DDR → 固件看不到队列 → `rd=0`**

两层原因：
1. `pm_helpers.c: core_clks_enable()` 只对 **V6 / V4-lite** 调 `clk_set_rate()`，
   sdm660 两者都不是 → 所有 venus 时钟从未设过速率
2. 更根本：`mmcc-sdm660.c` 的 `video_axi_clk` / `throttle_video_axi_clk`
   **没有 `.parent_hws`** → `recalc_rate()` 永远返回 0

**修复补丁（已写好，未验证）**
- `0079-venus-axi-clock-rate.patch`：`pm_helpers.c` 给 "bus" 时钟设 384 MHz
- `0080-clk-video-axi-parent.patch`：`mmcc-sdm660.c` 给两个 AXI 分支补 `parent_hws`

**⚠️ 需要刷 boot 才能生效**（`mmcc-sdm660` 是内建）。
设备上已备好 `/tmp/linux-r214.apk`（md5 `bd78ad000e158cd8fb2f935c33f21330`），
回滚镜像是 `tools/boot-r181.img`。

**验证步骤（需人在场）**
```sh
sudo apk add --allow-untrusted /tmp/linux-r214.apk
sudo boot-deploy && sudo reboot
# 起来后
sudo dmesg | grep -E 'diag:|venus'
sudo pads_selftest 2>/dev/null || sudo /usr/local/bin/pad_selftest | tail -6
```
期望：`[PASS] video_axi_clk at 384000000 Hz` 且 dmesg 出现 `INIT_DONE received`。

### 4.5 诊断补丁
`0078-venus-diag-queue-dump.patch`（队列读写指针 + sfr + softint + H2X 日志）
包含它的内核是 r205~r208；**设备当前用 r180 干净版**。

### 4.6 自检里的 venus 检查
`pad_selftest` 末尾会报 `video_axi_clk` 的速率：
```
[FAIL] video_axi_clk is 0 Hz - venus cannot reach DDR (needs patch 0080)
```
刷完 r214 后应变成 `[PASS] video_axi_clk at 384000000 Hz`。

---

## 5. 其它硬件驱动（已交付）

### 5.1 霍尔传感器（新驱动）
- 补丁 `0076-iio-smgr-hall.patch`
- 通过 smgr prox 驱动 id `qcom-smgr-hall-effect` → 设备 `qcom-smgr-hall`
- `pad_hall`：`hall_raw=0 -> open`（0=开，1=磁吸/合盖）

### 5.2 OTG 供电
- 补丁 `0010-power-supply-qcom-smbx-add-otg-vbus-control.patch`（**本来就存在**）
- `pad_otg on/off` 控制 `otg_vbus`
- 注意：**不要热重载 `qcom_smbx`**（会重启设备）

### 5.3 光线传感器
- 设备名 `qcom-smgr-prox`（**不要改名**，`tablet-autobright` 依赖它）
- smgr 驱动是 buffer-only，没有 `in_*_raw`
- 验证方式：看 `tablet-autobright` 服务的 journal + 背光值

### 5.4 后摄 OV13855
- 补丁 `0048` 曾引入 camss `port@2` 回归，**已移除，不要重加**

---

## 6. 踩坑清单（务必先读）

1. **绝不无人值守测试 suspend** —— 曾用 RTC 唤醒失败导致设备失联 3.5 小时
2. **不要热重载 `qcom_smbx`** —— 会立即重启设备
3. **不要热卸载 `fpc1020`** —— IRQ 挂起
4. CCI 驱动是模块，刷 boot 不会更新它
5. `/tmp` 重启会清空，重启后要重新推辅助脚本
6. **PowerShell 长复合 SSH 命令会被引号搞坏** —— 写 `.sh`/`.py` 文件再推上去
7. 设备脚本换行必须是 LF（`-replace "`r`n","`n"`）
8. **REA 在 Windows 不支持 ELF**，必须用 VM 上的 REA
9. `pmbootstrap` 构建失败时看 `~/.local/var/pmbootstrap/log.txt` 找真实错误
10. 内核 7.0+ 允许混合声明，但**在函数开头用未声明的变量仍会编译错误**
11. **本机的自动挂起不可靠** —— 长时间无操作会挂死（已发生 2 次）。
    远程长时间调试前先 systemctl mask sleep.target suspend.target
12. 换内核模块前**先备份旧模块**（cp x.ko.zst x.ko.zst.bak），否则救不回来

13. **venus 的 v4 PM ops（补丁 0073）在本机 panic** —— 没有 OPP 表，
    codec_control_v4 解引用空指针 → 启动循环。重新启用前必须先解决 OPP
14. **TWRP 就在 recovery 分区里** —— astboot reboot recovery，
    然后 db shell 直接是 root，可当普通 Linux 修 rootfs
16. **绝不在运行时读 /sys/kernel/debug/c1b7000.spi_dbg/ 的 QUP 寄存器** ——
    会干扰 TA 的 SPI 通信，指纹立即失效。重启可恢复（已验证）。
15. **pstore 有上次启动的完整内核日志** —— /sys/fs/pstore/console-ramoops-0
    （从 TWRP 读），排查"起不来"最快的路径


---

## 7. 备份索引

```
backup/work-20261028-0800.zip   指纹 error code 1 发现
backup/work-20261028-0900.zip   SPI 原语确认
backup/work-20261028-1000.zip   寄存器宽度表
backup/work-20261028-1100.zip   寄存器配置逐字节一致
backup/work-20261028-1200.zip   ★ 确认 rev4 + 信号提升 21 倍
backup/work-20261028-1300.zip   ★ 完整 64 行帧
backup/work-20261028-1400.zip   全工具链
backup/work-20261028-1500.zip   ★ REA-on-VM 发现
backup/work-20261028-1600.zip   venus CLK_DN 分析
backup/work-20261028-1700.zip   venus 队列表头排除
backup/work-20261028-1800.zip   ★ venus 固件不读队列（决定性）
backup/work-20261028-1900.zip   venus 诊断矩阵
backup/work-20261028-2000.zip   venus H2X 排除
```

主要文档：`mipad4plus/RESUME-HERE.md`（1~84 节，最详细）
本文件：`mipad4plus/HANDOVER.md`（总览）

---

## 8. 快速恢复设备状态

```powershell
# 1. 确认在线
ping 192.168.1.29

# 2. 全硬件自检
python tools\ssh_pad.py 'P=<SUDO_PASSWORD>; echo $P | sudo -S sh /usr/local/bin/pad_selftest'

# 3. 重推辅助脚本（重启后 /tmp 会清空）
foreach ($s in @('pad_selftest','pad_fp_check','pad_fp_dump','pad_fp_regs','pad_fp_rows','pad_fp_sweep','pad_fp_probe','pad_als','pad_hall','pad_otg')) {
  python tools\put_pad.py "tools\$s.sh" "/tmp/$s.sh"
}
python tools\ssh_pad.py 'P=<SUDO_PASSWORD>; echo $P | sudo -S sh -c "for f in /tmp/pad_*.sh; do install -m 755 $f /usr/local/bin/; done"'
```
