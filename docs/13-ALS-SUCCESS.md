# 13 · ALS 修复成功：`0x501` 彻底解决（2026-10-24）

> 前置：`11-REGISTRY-EXPERIMENT.md`（真因 = `data_type` 硬编码）
> 前置：`12-FLASH-ATTEMPT.md`（4 次刷机失败的排查过程）
> **本文记录最终成功的方案，以及之前所有失败的统一根因。**

---

## 零、结论（最重要的三行）

```
✅ ALS（CM3232 环境光）已完全修好：buffer 能 enable，读出真实光照 29.6~141.6 lx
✅ 真因确实是 11 文档说的：qcom_smgr.c 把 data_type 硬编码为 0，ALS 需要 1
✅ 之前 4 次刷机"黑屏"的唯一根因：CONFIG_DEBUG_INFO_BTF_MODULES=y
   → 重编内核后，必须【同时】替换全部 637 个模块 + 重建 initramfs
   → 只换内核 = 模块 BTF 校验失败 = qrtr 起不来 = 无 smgr / 无 DRM = 黑屏
```

---

## 一、成功验证的原始输出

### 1.1 内核身份

```
Linux xiaomi-clover 7.0.14-sdm660 #2-postmarketos-qcom-sdm660 SMP PREEMPT
  Sat Oct 24 03:46:54 UTC  aarch64 Linux
Linux version 7.0.14-sdm660 (pmos@user) (Alpine clang version 23.1.4, LLD 23.1.4)
```

**注意 `pmos@user` 和 `clang 23.1.4`** —— 确认跑的是我们编译的内核，不是出厂的 `pmos@build` / `23.1.3`。

### 1.2 模块 BTF 校验（之前失败的地方，现在 0）

```
############ 2. module BTF validation errors?
0
  ^ should be 0
-- any failed modules --
  (空)
```

### 1.3 `0x501` 消失

```
############ 3. 0x501 (the ALS bug)
  count: 0
```

### 1.4 传感器全部枚举

```
qcom_smgr 5-60: 0x00,0: BOSCH BMI120 Accelerometer
qcom_smgr 5-60: 0x00,1: BOSCH BMI120 Temperature
qcom_smgr 5-60: 0x0a,0: BOSCH BMI120 Gyroscope
qcom_smgr 5-60: 0x0a,1: BOSCH BMI120 Temperature
qcom_smgr 5-60: 0x14,0: AKM AK09918 Magnetometer
qcom_smgr 5-60: 0x28,0: Capella CM3232 ALS          ← 关键
qcom_smgr 5-60: 0x50,0: ROHM_SEMICONDUCTOR BU52061NVX ROHM_Hall_Effect

IIO 设备：
  device0 = pm660-rradc
  device1 = 800f000.spmi:pmic@0:adc@3100
  device2 = qcom-smgr-mag
  device3 = qcom-smgr-prox      ← ALS 在这里
  device4 = qcom-smgr-gyro
  device5 = qcom-smgr-accel
```

### 1.5 **决定性验证：buffer 能 enable**

```
############ 4. THE TEST: can the ALS buffer be enabled?
-- channels --
in_proximity_en   in_proximity_index   in_proximity_type
in_timestamp_en   in_timestamp_index   in_timestamp_type

-- enable all channels --
    enabled in_proximity_en
    enabled in_timestamp_en

-- THE MOMENT OF TRUTH: write 1 to buffer/enable --
  ✅ SUCCESS! ALS buffer enabled. The patch works.
```

**在修复前，这一步在 1/5/10/50/100 Hz 所有频率下都返回 `0x501` 失败。**

### 1.6 真实光照数据（不是固定值）

```
=== 读 6 个样本（灯光开着）===
  values: [141558, 141558, 141558, 29622, 49349, 49349, 49349, 49349]
  min=29622 max=141558
  as lux (DSP 输出 mlux, /1000): 29.6 .. 141.6 lx

=== 遮住传感器后 ===
  values (covered): [70779, 70779, ...]
  as lux: 70.8 .. 70.8 lx
```

**数值在 29.6 ~ 141.6 lx 之间真实变化**，证明传感器确实在采样，不是返回常数。

> 注：单位是 **mlux**（毫勒克斯），DSP 原始输出。除以 1000 得到 lux。
> 这与 09 文档 §3.6 的发现一致（`raw_convert_to_mlux`）。

### 1.7 无回归

```
############ 6. compare with the other sensors
  accel: buffer OK
  gyro:  buffer OK
  mag:   buffer OK

############ 7. desktop / hardware sanity
  Xorg=1 xfwm4=1
  audio: Xiaomi Mi Pad 4 (X4 / sdm660-internal)
  battery: 58%
  wifi: 1
  /dev/dri/: card1, renderD128
```

---

## 二、之前 4 次失败的统一根因

### 2.1 真正的错误信息

`journalctl -b -4`（12:57 那次）里藏着答案：

```
failed to validate module [uhid] BTF: -22
failed to validate module [nfnetlink] BTF: -22
failed to validate module [rfkill] BTF: -22
failed to validate module [qrtr] BTF: -22      ← 反复出现 20+ 次
systemd[1]: Failed to start Load Kernel Modules.
systemd-modules-load[334]: Failed to insert module 'fuse': Invalid argument
systemd-modules-load[334]: Failed to insert module 'uhid': Invalid argument
```

### 2.2 因果链

```
CONFIG_DEBUG_INFO_BTF_MODULES=y
        ↓
kernel/bpf/btf.c: btf_parse_module()
    btf->start_id = base_btf->nr_types;      ← 用运行中 vmlinux 的 BTF 类型数做偏移
        ↓
重编内核 → vmlinux 的 BTF 变了（补丁新增了函数）
        ↓
旧模块的 BTF 类型 ID 全部错位 → "failed to validate module [X] BTF: -22"
        ↓
systemd-modules-load 失败
        ↓
qrtr.ko 加载不了（qrtr 是 smgr 的传输层）
        ↓
qcom_smgr 无法与 ADSP 通信 → 无传感器
        ↓
msm.ko 也加载不了 → 无 DRM 设备 → Xorg "cannot open display :0"
        ↓
黑屏（但内核完全正常，journalctl 里有 6451 行日志）
```

### 2.3 为什么之前没发现

| 我做的 | 为什么没用 |
|---|---|
| 只看 `dmesg` | 只能看到**当前**启动。失败那次的日志在 `journalctl -b -1/-4` |
| 反复排查 DTB / CFI / 镜像格式 | 这些**全都不是原因**，白白浪费 3 次刷机 |
| 以为"黑屏 = 内核崩溃" | 实际内核跑得很好，`greetd` 会话都开了，只是没显示 |
| 单独换 `qcom_smgr.ko` | 第一次尝试就撞上同一个 BTF 问题，但没意识到它也会影响**其他**模块 |

**关键教训**：
> **内核"黑屏"≠"没启动"。先查 `journalctl --list-boots` 和 `journalctl -b -N`，
> 再决定要不要刷机。** 这一步能省掉大量无用功。

---

## 三、可复现的完整流程

### 3.1 编译（已在 12 文档记录，此处只列要点）

```bash
# 前提：内核源码 tarball 的 SHA512 必须与 pmaports APKBUILD 一致
#   83f7e717...e51298  linux-v7.0.14-sdm660.tar.gz

# 补丁：drivers/iio/common/qcom_smgr/qcom_smgr.c
# 注入 pmaports APKBUILD 的 source= 和 sha512sums=
# 不要动 CFI！保持 CONFIG_CFI=y（第一次 r1 是保留 CFI 的，也能启动）

cd ~ && pmbootstrap build --force linux-postmarketos-qcom-sdm660
# 耗时约 25-37 分钟
# 产物：~/.local/var/pmbootstrap/packages/edge/aarch64/linux-postmarketos-qcom-sdm660-7.0.14-r1.apk
```

### 3.2 三件套必须一起换（这是本次最大的坑）

```bash
K=7.0.14-sdm660

# ① 模块：637 个全部换成同批编译的
tar -xzf modules.tar.gz -C /tmp/kmod
cp -a /tmp/kmod/usr/lib/modules/$K/. /lib/modules/$K/
depmod -a $K

# ② initramfs：里面的 25 个启动关键模块也要换
python3 tools/pad_rebuild_cpio.py   # 自写的 cpio 重建器

# ③ boot.img：新内核 + 工作 DTB + 新 initramfs
```

### 3.3 boot.img 结构（本设备的硬性要求）

```
ANDROID! header
  kernel_size  = <gzip 大小 + DTB 大小>
  kernel_addr  = 0x8000
  ramdisk_addr = 0x1000000
  tags_addr    = 0x100
  page_size    = 4096
  header_version = 0
kernel payload:
  [0 .. N)      = Image.gz          ← 必须是 gzip（1f8b），不是 vmlinuz.efi
  [N .. N+62664) = DTB              ← 必须是 62,664 字节那个（含本地 DTS 修改）
  ↑ DTB 必须是最后一个对象，trailing bytes = 0
ramdisk = zstd 压缩的 cpio（28b52ffd）
```

**DTB 必须是 62,664 字节的版本**，从 `boot-current` 备份里提取：
```python
# artifacts/kernel/built/working-62664.dtb
# 而 tarball 编译出来的原始 DTB 是 62,468 字节 —— 那不是这个设备在用的
```

> 但注意：`pmos-boot2.img`（62,468 DTB）也能启动。
> 所以 DTB 大小**不是**黑屏原因，只是保险起见用工作镜像那个。

### 3.4 刷机

```bash
fastboot flash boot boot-final2.img
fastboot reboot
```

### 3.5 验证

```bash
# 1. 内核是我们编的？
cat /proc/version    # 应该看到 pmos@user + clang 23.1.4

# 2. BTF 错误为 0？
journalctl -b 0 -k | grep -c 'BTF: -22'    # 应该 0

# 3. 0x501 为 0？
journalctl -b 0 -k | grep -c '0x501'       # 应该 0

# 4. ALS buffer 能开？
ALS=/sys/bus/iio/devices/iio:device3       # 用 name 含 prox 的那个
echo 1 > $ALS/scan_elements/in_proximity_en
echo 1 > $ALS/scan_elements/in_timestamp_en
echo 1 > $ALS/buffer/enable                # ← 这一句以前必然失败

# 5. 读数据
python3 tools/pad_read_als.py /dev/iio:device3
```

---

## 四、当前设备状态

```
内核      7.0.14-sdm660 (pmos@user, Alpine clang 23.1.4, CFI=y, 含 ALS 补丁)
         编译时间 Sat Oct 24 03:46:54 UTC
boot      boot-final2.img   23,355,392 字节  MD5 c5feb1e8322060b462b8125b2eaed99a
模块      637 个，全部同批编译，BTF 校验 0 错误
initramfs 10,512,761 字节（自建，含同批 25 个启动模块）

ALS       ✅ 工作，29.6~141.6 lx，随光照实时变化
加速度计   ✅ 工作（-0.14 0.42 -9.75 m/s² 平放）
陀螺仪     ✅ buffer OK
磁力计     ✅ buffer OK
霍尔       ✅ SW_LID 可用（gpio-keys，event3）
音频       ✅ X4 / sdm660-internal
WiFi       ✅ 已连接
桌面       ✅ Xorg + XFCE，/dev/dri/card1
电量       58%
```

### 备份（全部保留）

```
Windows artifacts/kernel/boot-current-real.img     64 MB   原始 boot 分区 dump ★
Windows artifacts/kernel/built/boot-final2.img     23 MB   当前跑的成功镜像
Windows artifacts/kernel/built/vmlinuz             12 MB   r1 gzip 内核
Windows artifacts/kernel/built/vmlinuz-r2          12 MB   r2 内核（CFI 关闭，未用）
Windows artifacts/kernel/built/modules.tar.gz      13 MB   637 个 r1 模块
Windows artifacts/kernel/built/working-62664.dtb   62 KB   正确的 DTB
Windows tools/pmos-boot2.img                       25 MB   10-19 基线（也能启动）
平板 /root/tablet-boot-backups/boot-current-*.img  64 MB   同上
平板 /root/smgr-backup-*/                          16 MB   多份模块备份
```

---

## 五、本次的完整时间线（从怀疑 registry 到 ALS 可用）

| 时间 | 阶段 | 结果 |
|---|---|---|
| 10:50 | 推翻 registry 假设，锁定 `data_type` | ✅ 真因找到 |
| 11:22 | pmbootstrap 编译 | ✅ 25 分钟 |
| 11:59 | 只换 qcom_smgr.ko | ❌ BTF 失败（**当时就该意识到问题**） |
| 12:10 | 刷 boot（误用 vmlinuz.efi） | ❌ 黑屏 |
| 12:22 | 刷 boot（改对 gzip） | ❌ 黑屏 |
| 12:57 | 刷 boot（62664 DTB） | ❌ 黑屏（但内核其实起来了） |
| 13:29 | 关 CFI 重编 | ✅ 37 分钟 |
| 14:11 | 刷 CFI 关闭版 | ❌ 更糟（`Unknown symbol __SCT__`） |
| **14:17** | **查 journalctl 历史** | **★ 发现内核一直能启动，是模块 BTF 问题** |
| 14:24 | 装同批 637 模块 + 重建 initramfs | ✅ |
| 14:27 | 刷 boot-final2 | ✅ **15 秒启动** |
| 14:29 | 验证 ALS | ✅ **buffer 能开，读出 29.6~141.6 lx** |

**从"以为要补 registry"到"ALS 真的能用"，中间绕了 4 次刷机弯路，
根因是一行内核配置（`CONFIG_DEBUG_INFO_BTF_MODULES`）。**

---

## 六、下一步（ALS 已通，可以往上做了）

| # | 事项 | 说明 |
|---|---|---|
| 1 | **自动亮度** | ALS 有了，`iio-sensor-proxy` 能读，接 XFCE 电源管理 |
| 2 | 自动旋转 | `tablet-orientd` 已就绪（10 文档），但换方向要重启会话 |
| 3 | 合盖休眠 | 需要磁铁实测（用户说没有磁铁） |
| 4 | 写 `qcom_smgr_hall.c` | 11 文档 §2.3 已从"死路"改判"可行" |
| 5 | 扬声器 / 摄像头 / GPS | 08 文档列的其他缺陷，未动 |

---

## 七、附：本次新增/关键工具

| 文件 | 用途 |
|---|---|
| `tools/pad_rebuild_cpio.py` | **★ 自写 initramfs 打包器**（mkinitfs 在 musl 上有问题） |
| `tools/pad_build_final2.sh` | 组装最终 boot.img（内核+DTB+新initramfs） |
| `tools/pad_verify_als.sh` | **★ 完整 ALS 验证脚本**（含决定性 enable 测试） |
| `tools/pad_als_light_test.sh` | 验证 ALS 随光照变化 |
| `tools/pad_journal_boots.sh` | **★ 查历史启动日志**（本次突破的关键） |
| `tools/pad_boot_census.sh` | 统计每次启动的 0x501 / Unknown symbol |
| `tools/pad_install_final.sh` | 安装模块 + 重建 initramfs + depmod |
| `tools/analyze_black.py` / `cmp_headers.py` | 镜像结构对比（虽然没找到真因，但对以后有用） |

证据：`evidence/ALS-RESULT.txt`、`evidence/boot-1-analysis.txt`、
`evidence/boot4-detail.txt`、`evidence/boot4-modules.txt`、
`evidence/journal-boots.txt`、`evidence/crash-log.txt`
