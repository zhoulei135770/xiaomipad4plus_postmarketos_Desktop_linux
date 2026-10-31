# 小米平板 4 Plus（xiaomi-cloverplus）跑 Ubuntu 桌面 · 实施方案

> 版本：v1（方案稿，未执行）
> 主机：Windows 10 专业版 / i5-12400F (6C12T) / 32 GB RAM / C 盘剩 24.6 GB、D 盘剩 91.6 GB
> 目标设备：Xiaomi Mi Pad 4 Plus（SDM660，10.1" 1920x1200，LTE）

---

## 0. 结论摘要

1. **"所有硬件可用"不成立**，卡点在 mainline 缺驱动和厂商固件，不是投入时间能解决的（详见 §2、§7）。
2. 现实目标：**能日常当平板用的 Ubuntu 桌面**，硬件覆盖约 80%（屏幕/触屏/GPU/Wi-Fi/蓝牙/音频/电池/存储/SD）。
3. 架构选 **方案 B**：pmOS 做硬件宿主 + Ubuntu 24.04 容器做用户空间。既拿到 mainline 硬件支持，又拿到真 Ubuntu 桌面和 deb 生态。
4. 构建放在 **Linux 虚拟机**（不用 WSL2），**刷机放在 Windows 主机**（fastboot/adb 直连 USB，避免虚拟机 USB 透传的坑）。
5. REA 有用，但只解决"**看懂**"这一层：从原厂固件/内核模块/DTBO 里挖出面板时序、触控 IC、传感器型号、GPIO/regulator 配置，缩短写驱动前的调研。它**不能**替你写驱动、不能替代真机测试、不能解签名固件。

---

## 1. 验收标准（先定义"完成"）

### 1.1 必须达到（MUST）

- [ ] 能从 eMMC 冷启动进桌面，无需连电脑
- [ ] 10.1" 屏正常点亮，亮度可调，35° 自动旋转正确
- [ ] 触屏可点按、可滑动，无偏移（Plus 是不同触控 IC，需单独验证）
- [ ] Wi-Fi 可连 5 GHz，休眠唤醒后自动重连
- [ ] 蓝牙可连键鼠
- [ ] 扬声器/耳机出声，麦克风可录
- [ ] 电池电量与充电状态正确，待机掉电 < 3%/8h
- [ ] Ubuntu 24.04 容器内可 `apt install` 任意 arm64 包，能跑 Firefox / VS Code / LibreOffice
- [ ] 中文输入法（fcitx5 + 拼音）可用

### 1.2 期望达到（SHOULD）

- [ ] GPU 硬件加速（freedreno + mesa），浏览器滚动不卡
- [ ] 视频硬解（H.264/H.265）
- [ ] USB-C OTG 外接键盘/U 盘
- [ ] 外接显示器（USB-C DP alt mode）——大概率不可行，看 PMIC/PHY

### 1.3 明确放弃（WON'T，本期）

- [ ] 摄像头（前后）
- [ ] 4G 通话/SMS/移动数据
- [ ] GPS
- [ ] 光线/距离/霍尔/磁力计

---

## 2. 硬件现状（来源：Nura/pmOS wiki，2026-09-27 修订）

| 状态 | 项目 |
|---|---|
| ✅ 可用 | 刷机、USB 网络、eMMC、SD 卡、电池与充电、屏幕、触屏、3D 加速、蓝牙、FDE、加速度计 |
| ⚠️ 部分 | 音频（话筒/耳机通路不全）、Wi-Fi（可连但稳/速率受限） |
| ❌ 坏 | 摄像头、闪光灯、GPS、通话/SMS/移动数据、USB OTG、磁力计、光线、距离、霍尔 |

- 内核：**linux-postmarketos-qcom-sdm660，6.13 mainline**
- 设备包：`device/testing/device-xiaomi-clover`（testing 分类）
- DTB：`sda660-xiaomi-clover`（8" WiFi）、`sdm660-xiaomi-clover`（8" LTE）、**`sdm660-xiaomi-clover-plus`（10" Plus，本次目标）**
- Plus 与普通版差异：**触控控制器和显示屏不同**，wiki 明确提示

### 2.1 为什么这几项"补不了"

| 项目 | 阻塞原因 | 可解性 |
|---|---|---|
| 摄像头 | mainline 无该 sensor 的 V4L2 驱动；无 ISP 管线（CAMSS 只覆盖部分 SoC）；需 libcamera tuning | 极低（社区多年未成） |
| 基带/GPS | 需高通专有固件 + QRTR/QMI 用户态栈 + rmtfs；固件签名不可改 | 极低 |
| USB OTG | Type-C role switch / PMIC 驱动缺失 | 中（可尝试） |
| 传感器 | SSC(ADSP) 子系统 mainline 只跑通加速度计 | 低-中 |

---

## 3. 总体架构

```
┌──────────────── Windows 10 主机 ────────────────┐
│  D:\APPS\platform-tools\fastboot.exe  ← 刷机    │
│  Ubuntu 24.04 虚拟机（VMware/Hyper-V）           │
│    └─ pmbootstrap → 产出 boot.img / rootfs      │
│         │ 共享目录（VMware Shared Folder）      │
│         └──► 主机 D:\build\clover\              │
└──────────────────────┬──────────────────────────┘
                       │ USB
              ┌────────▼────────┐
              │  Mi Pad 4 Plus  │
              │  pmOS + Phosh   │
              │   └ distrobox   │
              │      Ubuntu 24  │
              └─────────────────┘
```

**为什么构建在 VM、刷机在主机：**

- pmbootstrap 只支持 Linux，且**禁止 root 运行**；
- 虚拟机 USB 透传到 fastboot 经常掉设备（尤其 fastboot reboot 瞬间重枚举），Windows 主机直连最稳；
- 构建产物通过共享目录回主机，`fastboot flash` 一条命令搞定。

---

## 4. 虚拟机方案（不用 WSL2）

### 4.1 现状

- 已装：无 VMware、无 VirtualBox（`vmrun.exe` / `VBoxManage.exe` 均不存在）
- `systeminfo` 报 **"A hypervisor has been detected"** → Hyper-V/VBS 已在运行

### 4.2 选型

| 方案 | 评价 |
|---|---|
| **VMware Workstation Pro**（个人免费） | 推荐。15.5+ 走 WHP 兼容层，在 Hyper-V 开启时也能跑，USB 透传成熟 |
| Hyper-V 原生 VM | 次选。性能最好，但 USB 透传需 Enhanced Session/第三方工具，麻烦 |
| VirtualBox 7 | 可用，WHP 模式下性能一般，USB 过滤偶尔丢设备 |

**建议：VMware Workstation Pro（免费个人版）。** 若你已有 Hyper-V 且不想装第三方，也可直接用 Hyper-V，但刷机仍走主机。

### 4.3 虚拟机配置

| 项 | 值 | 说明 |
|---|---|---|
| vCPU | 6（不超过物理核数） | 内核编译瓶颈 |
| 内存 | 12 GB（可 16） | pmbootstrap 编译 + 链接 |
| 磁盘 | 120 GB 精简置备 | 源码 ~8 GB + 产物 ~20 GB + ccache |
| 网络 | NAT | 需要能访问 gitlab.postmarketos.org / dl-cdn.alpinelinux.org |
| 系统 | Ubuntu 24.04 LTS Server | 无桌面更省内存；也可 Desktop 方便调试 |
| 用户 | 非 root 普通用户，带 sudo | pmbootstrap 硬性要求 |

### 4.4 系统内准备

```bash
sudo apt update
sudo apt install -y git python3 python3-pip pipx curl unzip \
  android-tools-adb android-tools-fastboot \
  build-essential ccache

# pmbootstrap（官方推荐 pipx）
pipx install pmbootstrap
# 或
git clone https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git
```

> 注意：Ubuntu 24.04 自带的 `python3` 是 3.12，pmbootstrap 新版已兼容；若报错优先 `pipx install --python python3.12 pmbootstrap`。

---

## 5. 构建与刷机流程

### 5.1 初始化

```bash
pmbootstrap init
# vendor: xiaomi
# device: clover
# variant: cloverplus        ← 关键，选 10 寸 Plus
# interface: phosh           ← 先选最成熟的，后面容器跑 Ubuntu
# 其余默认（systemd 可选，建议 systemd 便于 distrobox）
```

`pmbootstrap init` 会读 `deviceinfo_dtb_cloverplus`，确认最终写进 boot.img 的 DTB 是 `qcom/sdm660-xiaomi-clover-plus`。

### 5.2 构建

```bash
pmbootstrap install                # 生成 rootfs + boot.img
pmbootstrap export                 # 导出到 /tmp/postmarketOS-export
```

### 5.3 首次验证：SD 卡启动，不动 eMMC（强烈建议）

```bash
# VM 内插 SD 卡读卡器（USB 透传）或主机写卡
pmbootstrap install --sdcard=/dev/sdX
pmbootstrap flasher boot           # 临时引导，不写 bootloader
```

能进桌面、触屏可用，再往下走。

### 5.4 刷入 eMMC

```bash
pmbootstrap flasher flash_kernel
pmbootstrap flasher flash_rootfs --partition userdata
```

或回主机用 fastboot：

```powershell
fastboot flash boot  D:\build\clover\boot.img
fastboot flash userdata D:\build\clover\xiaomi-clover.img
fastboot reboot
```

### 5.5 回退与救砖

- 官方固件线刷（MiFlash / fastboot 全量包）可回 Android；
- 高通 **EDL 9008** 模式是最后兜底（需后盖短接或 `fastboot oem edl`，视解锁状态）；
- **解锁 Bootloader 会清空全部数据**，且小米有账号绑定等待期（72h 起）。

---

## 6. Ubuntu 桌面层（方案 B 落地）

pmOS 只做"硬件+显示+输入"，桌面跑在容器里：

```
pmOS (Phosh 只保留显示/输入/网络栈)
 └─ distrobox: ubuntu:24.04
      ├─ XFCE4 或 GNOME on Wayland
      ├─ fcitx5 + 中文
      ├─ Firefox / VS Code / LibreOffice
      └─ 音频：pipewire（透传宿主 socket）
```

要点：

1. **GPU**：容器内用宿主 `/dev/dri`，装 `mesa-utils`、`freedreno` 驱动走宿主内核，容器只放 userspace mesa。
2. **音频**：宿主 pipewire，容器挂载 `$XDG_RUNTIME_DIR/pipewire-*`。
3. **输入法**：`fcitx5` + `fcitx5-chinese-addons`，GTK_IM_MODULE 统一。
4. **开机自启**：pmOS 侧 systemd user unit 拉起 `distrobox enter` + 桌面会话。
5. **性能**：`zram` + `cpufreq schedutil`；SDM660 的 Adreno 512 在 1920x1200 下建议开 `WLR_RENDERER=pixman` 兜底，稳定后再切 GL。

---

## 7. 硬件攻坚清单（按优先级）

| 优先级 | 项目 | 需要的证据 | 难度 | REA 用途 |
|---|---|---|---|---|
| P0 | Plus 触屏校准 | 触控 IC 型号、I2C 地址、分辨率映射 | 中 | 从原厂 dtbo / touch 固件 / HAL 提取 |
| P0 | Wi-Fi 稳定性 | WCN3990 固件加载路径、board-2.bin 校准 | 中 | 分析原厂 `wlan.ko`、`bdwlan` 文件 |
| P0 | 音频 UCM | codec 型号、DAPM 路由、耳机检测 GPIO | 中 | 反编译原厂 audio HAL / mixer_paths.xml |
| P1 | 亮度/自动旋转 | 背光 PWM/DSI 亮度节点、ALS 型号 | 低-中 | DTB 对比 |
| P1 | 休眠唤醒 | 唤醒源、regulator 掉电序列 | 中 | 原厂内核 suspend 回调 |
| P2 | USB OTG | Type-C 控制器、role switch、vbus | 高 | 原厂 dwc3/typec 驱动 |
| P3 | 传感器 | SSC 与 IIO 桥接 | 高 | 原厂 sensors HAL |
| — | 相机 | sensor 驱动 + ISP + tuning | 极高 | 只能定位型号，做不完 |
| — | 基带 | 专有固件 + QMI | 极高 | 无意义 |

---

## 8. REA 能帮到什么程度（回答你的问题）

**能：把"猜"变成"有证据"。**

具体可做的分析对象（都在原厂 Android 固件包 / 线刷包里）：

1. `boot.img` / `vendor_boot.img` → 解出内核、ramdisk、DTB/DTBO
2. `dtbo.img` → 每块屏/每个触控 IC 的覆盖配置
3. 内核模块 `*.ko`（`touchscreen.ko`、`wlan.ko`、`sensors.ko`）
4. 厂商 HAL：`vendor/lib64/hw/camera.*.so`、`audio.primary.*.so`、`sensors.*.so`
5. 固件文件：`bdwlan*.bin`、`fw_bcm`/`WCNSS` 相关、触控固件

**典型产出**：

- 面板 DSI 初始化序列、时序参数（porch/clock）→ 直接转成 mainline `panel-simple` / 自定义 panel driver
- 触控 IC 型号 + I2C 地址 + 中断 GPIO + 固件加载方式 → 决定用 `edt-ft5x06` / `goodix` / `synaptics` 哪个驱动，或要不要写新的
- 传感器型号 + I2C/SPI 地址 + 上报格式
- 音频 codec 型号、DAPM 路由、耳机检测脚
- USB/Type-C 的 role switch 与 vbus 控制 GPIO

**不能：**

- 写内核驱动（那是人写的，REA 只给事实）
- 替代真机测试（每改一次都要刷一次看效果）
- 解开签名/加密固件（modem、部分 sensor 固件）
- 从 Android 反推出 mainline 不存在的硬件能力（ISP、基带）

**示例命令**（REA 已装好，可直接用）：

```powershell
rea analyze D:\firmware\boot.img --format json          # 概览
rea open-binary D:\firmware\dtbo.img                    # 打开目标
rea decompile <addr> --json                             # 反编译函数
rea search-strings "ft5x06" --json                      # 找触控 IC 线索
rea inspect-artifact D:\firmware\vendor.img             # 看镜像结构
```

> 实际更常用的是 MCP 工具（`open_binary` / `analyze_function` / `search_strings`），我在会话里直接调。

---

## 9. 里程碑与工期（单人 + 我远程协助）

| 阶段 | 内容 | 预估 |
|---|---|---|
| M0 | 装 VMware + Ubuntu 24.04 VM，pmbootstrap 跑通 `init` | 0.5 天 |
| M1 | 构建出 cloverplus 镜像，SD 卡启动进 Phosh | 1-2 天 |
| M2 | 触屏/亮度/Wi-Fi/音频 调通（P0） | 1-3 周（依赖设备迭代次数） |
| M3 | Ubuntu 24.04 容器桌面 + 中文输入法 + 常用软件 | 2-3 天 |
| M4 | 刷入 eMMC，日常使用 | 0.5 天 |
| M5 | P1/P2 逐项优化 | 持续，按兴趣 |

---

## 10. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 解锁 Bootloader 失败/等待期 | 无法刷机 | 提前申请，等 72h+ |
| 刷坏 boot | 开不了机 | SD 卡启动兜底；EDL 可救 |
| Plus 触控不被现有驱动支持 | 触屏不可用 | 先 SD 卡验证；必要时写驱动或回退 Android |
| Wi-Fi 固件缺失 | 无网络 | 从原厂 `vendor` 分区提取 `bdwlan`/`WCNSS` 校准文件 |
| 虚拟机性能不足 | 编译慢 | 6 vCPU + ccache，增量构建 |
| 时间投入超预期 | 半途而废 | 先做 M0-M2，能日常用再继续 |

---

## 11. 需要你提供 / 确认

1. **设备信息**：具体型号（4/64 还是 6/128）、当前系统（MIUI/Havoc/LineageOS）、Bootloader 是否已解锁
2. **原厂固件包**：最好有对应版本的 fastboot 线刷包（`boot.img`、`dtbo.img`、`vendor.img`、`super.img`），REA 分析要用
3. **SD 卡**：≥16 GB，用于首次无损验证
4. **虚拟机软件**：装 VMware 还是用现有 Hyper-V
5. **是否接受"先 SD 卡跑，不动 eMMC"** 的渐进路线

---

## 附：立即可做的三件事（不需要设备）

1. 装 VMware Workstation Pro + Ubuntu 24.04 Server VM（6C/12G/120G）
2. VM 内 `pipx install pmbootstrap && pmbootstrap init`（选 xiaomi/clover/cloverplus），跑到 `pmbootstrap install` 出镜像
3. 把原厂线刷包放进 `D:\firmware\clover\`，我用 REA 先把 `dtbo.img` 和触控/音频 HAL 摸一遍，产出驱动线索清单
