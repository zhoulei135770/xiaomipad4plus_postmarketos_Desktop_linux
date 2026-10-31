# 12 · ALS 修复实战：编译成功、刷机黑屏、根因排查（2026-10-24）

> 前置：`11-REGISTRY-EXPERIMENT.md`（真因 = `data_type` 硬编码）
> 本文记录：**补丁编译成功，但刷入后黑屏**，以及排查到一半的确切状态。

---

## 零、当前状态（最重要）

```
✅ 诊断完成，真因铁证如山（见 11 文档）
✅ 补丁写好，内核编译成功（25 分 19 秒，pmbootstrap）
✅ 补丁确认编入（函数 476 → 488 字节）
✅ boot.img 格式验证正确（gzip + DTB，与原镜像结构一致）
❌ 刷入后黑屏 —— 试了 2 个版本的 DTB，均失败
✅ 已恢复原状（boot 分区 MD5 与实验前完全一致，系统/音频/传感器全部正常）
⏸ 下一步：需要换思路定位内核为何不启动
```

**设备当前完全正常，已验证到字节级。**

### 已排除的原因（逐项实测，别再重试）

| 怀疑点 | 结论 | 证据 |
|---|---|---|
| 镜像格式 | **排除** | 原镜像 kernel 是 gzip；第一次误用 `vmlinuz.efi`(MZ) 已改对，**仍黑屏** |
| DTB 大小/内容 | **排除** | 用 `boot-current` 里 62,664 字节的 DTB（与工作镜像**字节完全相同**）→ **仍黑屏** |
| DTB 是否在末尾 | **排除** | `DTB is last = True`，`trailing = 0` |
| boot header 字段 | **排除** | 逐字段比对：只有 `kernel_size`（合理）和 `name`(SHA1 校验) 不同，cmdline/addr/page_size **完全一致** |
| initramfs 里的旧模块 | **排除** | initramfs 只带 25 个启动关键模块（msm/goodix/usb/drm），**不含 qcom_smgr** |
| 内核配置 | **排除** | 平板 `/proc/config.gz` vs pmaports 配置：**只有 4 行编译器版本号不同**，功能配置 100% 相同 |
| gzip 头格式 | **排除** | 两者都是 `1f8b0800 00000000 0203`（CM=8 FLG=0 MTIME=0 XFL=2 OS=3 Unix） |
| ARM64 Image 头 | **排除** | `flags=0xa`、`magic=41524d64`、`text_offset=0` 两者一致 |
| 只换模块 | **已证不可行** | `CONFIG_DEBUG_INFO_BTF_MODULES=y` → BTF 类型 ID 按 vmlinux 偏移，重编后必然错位 |

### 剩下唯一未排除的差异

```
平板内核编译者：Alpine clang 23.1.3 / LLD 23.1.3
我们编译用    ：Alpine clang 23.1.4 / LLD 23.1.4
配置          ：CONFIG_CFI=y + CONFIG_SHADOW_CALL_STACK=y
```

**CFI（Control Flow Integrity）对编译器版本极其敏感。**
跨版本编译时，函数的 CFI 哈希（type hash）会变，而 `__cfi_check` 的间接调用校验可能失败
→ 早期启动就挂，且**无任何串口/屏幕输出**（与观察到"闪一串代码后黑屏"吻合）。

### 与既有线索的一致性

`pmos-boot2.img`（10-19 构建）用 62,468 字节的**原始 DTB** 也能正常启动，
说明**DTB 不是关键**，且这印证了"问题在内核二进制"。

---

## 一、下次必须换的方法（不要重复这次的路）

### 方法 A：用完全相同的 clang 23.1.3 重新编译 ⭐ 最可能成功

```bash
# 在 pmbootstrap 的 chroot 里固定 clang 版本
# Alpine edge 有 llvm23 / clang23 的历史包，或从 snapshots 拉
apk add clang=23.1.3-r* lld=23.1.3-r* llvm=23.1.3-r*
# 然后 pmbootstrap build --force linux-postmarketos-qcom-sdm660
```
**验证方法**：编译后比对内核 banner 里的 clang 版本必须是 `23.1.3`。

### 方法 B：临时关闭 CFI 验证补丁逻辑 ⭐ 先证明补丁有效

```bash
# 在 APKBUILD 的 prepare() 里追加：
sed -i 's/^CONFIG_CFI=y/# CONFIG_CFI is not set/' "$builddir/.config"
```
**价值**：如果关掉 CFI 后能启动且 ALS 修好，就证明：
1. 补丁逻辑正确
2. 问题确实是 CFI/编译器版本

**这是最高性价比的下一步。**

### 方法 C：先做最小改动的对照实验

```
实验组：用 clang 23.1.4 编译，但**不加补丁**
对照组：原始内核（能启动）
```
若"不加补丁的 23.1.4 版本"也黑屏 → 100% 确认是编译器问题，与补丁无关。
**这一步能彻底分离变量，强烈建议先做。**

---

## 二、已完成的工作（全部可复用）

### 2.1 编译环境搭建（一次成功）

```bash
# 关键前提
pmbootstrap 3.12.1
内核源码 tarball：linux-v7.0.14-sdm660.tar.gz (248 MB)
  SHA512 = 83f7e717b8adc9049e828a27629e7347be2fa0aef6c8404608059410cebaafa0
           c2659317b615634fbd5d83f9a245bcf1a64e5d2cd0d8e3ec8aeaa3dcf0e51298
  ↑ 与 pmaports APKBUILD 校验和完全一致
```

**为什么必须用 pmbootstrap 而不是本地源码树**：
- 平板内核用 **Alpine clang 23.1.3 + LLD 23.1.3** 编译
- 配置里有 `CONFIG_CFI=y` + `CONFIG_SHADOW_CALL_STACK=y` → **gcc 不支持**，必须 clang
- 本地那棵树 `.config` 是旧的（514 模块），pmaports 配置是 626 模块

**代理问题**：Clash 只监听 `127.0.0.1:16514`（未开 Allow LAN），VM 连不上。
解决：**Windows 上用代理下载 tarball，再内网传给 VM**。

### 1.2 补丁（已生成、已验证、已编入）

`drivers/iio/common/qcom_smgr/qcom_smgr.c`：

```c
/*
 * The DSP expects a per-sensor-class "data type" selector in the buffering
 * request. Android's SSC HAL hardcodes these in each sensor class'
 * prepareAddMsg() (verified by disassembling sensors.ssc.so):
 *
 *   Accelerometer   sensor_id 0x00  data_type 0
 *   Gyroscope       sensor_id 0x0a  data_type 0
 *   Magnetic        sensor_id 0x14  data_type 0
 *   Light           sensor_id 0x28  data_type 1
 *   HallEffect      sensor_id 0x50  data_type 0
 *
 * Requesting the ambient light sensor with data_type 0 makes the DSP reject
 * the buffering request with result 0x501 (observed on Xiaomi Mi Pad 4 Plus),
 * so its IIO buffer can never be enabled.
 */
static u8 qcom_smgr_data_type_for(struct qcom_smgr_sensor *sensor)
{
	if (sensor->type == SNS_SMGR_SENSOR_TYPE_PROX_LIGHT)
		return SNS_SMGR_DATA_TYPE_SECONDARY;

	return SNS_SMGR_DATA_TYPE_PRIMARY;
}
```
调用点：
```c
-	req.items[0].data_type = SNS_SMGR_DATA_TYPE_PRIMARY;
+	req.items[0].data_type = qcom_smgr_data_type_for(sensor);
```

**补丁文件**：`artifacts/kernel/0001-iio-qcom-smgr-use-per-sensor-data-type.patch`
（用 `diff -u` 从真源码生成，能干净应用，无 fuzz）

**注入方式**（改 pmaports APKBUILD）：
```bash
source="
	linux-$_tag.tar.gz::...
	config-$_flavor.aarch64
	0001-iio-qcom-smgr-use-per-sensor-data-type.patch   ← 新增
"
sha512sums="
...  linux-v7.0.14-sdm660.tar.gz
...  config-postmarketos-qcom-sdm660.aarch64
b83d0950...940d  0001-iio-qcom-smgr-use-per-sensor-data-type.patch   ← 新增
"
```

### 1.3 编译产物

```
packages/edge/aarch64/linux-postmarketos-qcom-sdm660-7.0.14-r1.apk   39.9 MB
├── boot/vmlinuz            12,773,138  (gzip Image, 注意不是 .efi)
├── boot/vmlinuz.efi        12,833,280  (EFI stub, 本设备不用)
├── boot/dtbs/qcom/sdm660-xiaomi-clover-plus.dtb   62,468
└── usr/lib/modules/7.0.14-sdm660/                  637 个 .ko.zst
```

**验证补丁已编入**（关键证据）：
```
旧 qcom_smgr.ko: qcom_smgr_request_buffering size = 476
新 qcom_smgr.ko: qcom_smgr_request_buffering size = 488   (+12 字节)
函数内 284 处字节差异
```

**vermagic 完全匹配**：`7.0.14-sdm660 SMP preempt mod_unload aarch64`

---

## 二、失败的两次尝试（都已恢复，**记录原因很有价值**）

### 2.1 尝试一：只换 qcom_smgr.ko（不刷 boot）

**结果**：`modprobe: ERROR: could not insert 'qcom_smgr': Invalid argument`

```
[11060.799680] qcom_smgr: module verification failed: signature and/or required key missing
[11060.804290] BPF: [124593] FUNC
[11060.804321] BPF: type_id=122785
[11060.804339] BPF: Invalid name
[11060.804360] failed to validate module [qcom_smgr] BTF: -22
```

**根因**：`CONFIG_DEBUG_INFO_BTF=y` + `CONFIG_DEBUG_INFO_BTF_MODULES=y`

内核源码 `kernel/bpf/btf.c`：
```c
static struct btf *btf_parse_module(...)
{
	base_btf = vmlinux_btf;                    /* 用运行中内核的 BTF 当基准 */
	btf->start_id      = base_btf->nr_types;   /* ★ 类型 ID 从这里开始偏移 */
	btf->start_str_off = base_btf->hdr.str_len;
```

模块里每个 BTF 类型 ID 都是**相对 vmlinux BTF 类型数**的偏移。
我们的模块是**重新编译**的，补丁新增了函数 → 类型数变了 → ID 全部错位 → `Invalid name`。

**结论：这个内核上，只换模块不可能成功，必须连内核一起换。**

### 2.2 尝试二：刷入自组装的 boot.img

**结果**：闪一串内核日志后黑屏，随后自动回 fastboot。

**已排除的原因**（逐项验证过）：

| 怀疑点 | 验证结果 |
|---|---|
| 镜像格式错 | ❌ 不是。原镜像 kernel 是 **gzip**，我第一次误用了 `vmlinuz.efi`（MZ/EFI）；第二次改对成 `vmlinuz`（`1f8b`）**仍然黑屏** |
| DTB 错 | ❌ 不是。我构建的 DTB 与工作镜像里的 DTB **字节完全相同**（62,468 字节，62,468 处全等） |
| DTB 位置错 | ❌ 不是。两者都是「gzip 内核 + DTB 追加在末尾」，`trailing bytes = 0` |
| ARM64 Image 头错 | ❌ 不是。`flags=0xa`、`magic=41524d64`、`text_offset=0` 两者完全一致 |
| 内核配置错 | ❌ 不是。平板 `/proc/config.gz` 与 pmaports 配置**只有 4 行编译器版本号不同**，功能配置 100% 相同 |

**剩余最可能的原因**：

```
1. 编译器小版本差异
   pad : Alpine clang 23.1.3 / LLD 23.1.3
   我们: Alpine clang 23.1.4 / LLD 23.1.4
   → CFI (Control Flow Integrity) 对编译器版本极敏感
   → CONFIG_CFI=y 时，跨版本编译的内核可能因 CFI 检查失败而无法启动

2. initramfs 里的旧模块
   已排查：initramfs 只带 25 个启动关键模块（msm/goodix/usb/drm），
   **不含 qcom_smgr**，且我们已把这 25 个全换成新编译的
   → 这条也已排除（但还没用新 initramfs 试过完整刷机）

3. 缺少某次编译的中间产物
   例如 CONFIG_MODULE_SIG 的签名密钥不同
```

---

## 三、本轮新增的关键事实

### 3.1 initramfs 结构（重要）

```
initramfs: 12,788,528 字节 zstd 压缩
├── cpio 解压后 29,173,420 字节
├── 385 个条目
└── 只有 25 个 .ko.zst：
      drm_display_helper, drm_dp_aux_bus, drm_exec, drm_gpuvm,
      msm, panel-novatek-nt51021, gpu-sched,
      qcom-spmi-rradc, goodix_ts, cec, pmi8998_fg, qcom_smbx,
      llcc-qcom, mdt_loader, ocmem, qcom_aoss, ubwc_config,
      u_ether, u_serial, usb_f_acm, usb_f_mass_storage,
      usb_f_ncm, usb_f_rndis, libcomposite, usb-storage
```

**`qcom_smgr` 不在 initramfs 里** —— 它是运行时从 rootfs 的 `/lib/modules` 加载的。

### 3.2 已重建的 initramfs（在平板上）

用自己写的 cpio 重建器（`tools/pad_rebuild_cpio.py`）：
```bash
# 解析原 initramfs 的 cpio → 把 25 个模块换成 /lib/modules 里的新版 → 重新打包 zstd
replaced: 25   missing: 0
new cpio: 29,172,736 bytes (was 29,173,420)
compressed: 10,512,761 bytes (was 12,788,528)   ← 变小了，因为新模块更小
written: /root/bootgen3/initramfs.new
```

**为什么自己写打包器**：平板的 `mkinitfs`（Go + musl）报告 "completed" 但一个字节都不写。
试过 `-d`、`-no-bootdeploy`、`MKINITFS_DEBUG=1`、在 VM chroot 里挂 `/proc /dev /sys` 全部无效。

### 2.3 设备现状（已恢复到实验前，逐项验证）

```
内核      : 7.0.14-sdm660（原始）
boot 分区 : MD5 = 2d00a4bc79e8851c027635900552f927
            ↑ 与实验前 11:02 的 dump 完全一致
模块      : qcom_smgr.ko.zst sha256 = 35934e6a69...（原始）
音频      : X4 / sdm660-internal 正常（MI2S 补丁在）
桌面      : Xorg=1 xfwm4=1 panel=2
传感器    : 5 个全部识别（accel/gyro/mag/prox/hall）
dmesg     : 只有 3 条已知的 0x501（就是要修的那个 bug）
电量      : 70%
orientd   : inactive（未启用）
```

**备份清单（全部可用）**：
```
平板 /root/tablet-boot-backups/boot-current-20261024-110240.img   64 MB  ★ 完整分区
Windows artifacts/kernel/boot-current-real.img                    64 MB  ★ 同上，已拉回
Windows tools/pmos-boot2.img                                      25 MB    10-19 基线
平板 /root/smgr-backup-20261024-124728/                         16.6 MB   旧模块
平板 /root/bootgen3/initramfs.new                               10.5 MB   自建 initramfs
Windows artifacts/kernel/built/                                        全部编译产物
  ├── vmlinuz            12,773,138  (gzip, 正确格式)
  ├── vmlinuz.efi        12,833,280  (EFI stub, 本设备不用)
  ├── working-62664.dtb      62,664  (从工作镜像提取)
  ├── sdm660-*.dtb           62,468  (tarball 原始)
  ├── qcom_smgr.ko.zst        8,694  (带补丁)
  ├── modules.tar.gz        13.5 MB  (637 个新模块)
  ├── boot-alsfix.img       25.6 MB  (DTB 62468 版，黑屏)
  ├── boot-alsfix2.img      25.6 MB  (同上)
  └── boot-final.img        25.6 MB  (DTB 62664 版，黑屏)
```

---

## 九、本次刷机实验的完整时间线

| 时间 | 动作 | 结果 |
|---|---|---|
| 10:50 | 推翻 registry 假设，锁定 `data_type` 真因 | ✅ 见 11 文档 |
| 11:02 | dump 当前 boot 分区（64 MB） | ✅ 生成最关键备份 |
| 11:03–11:19 | 侦察 VM、下载源码、写补丁、注入 APKBUILD | ✅ |
| 11:22–11:47 | pmbootstrap 编译内核 | ✅ 25 分 19 秒，DONE |
| 11:59 | 只换 qcom_smgr.ko，重载模块 | ❌ BTF 校验失败（已回滚） |
| 12:06 | 组装 boot-alsfix.img（误用 vmlinuz.efi） | ✅ 格式其实是错的 |
| 12:10 | 刷入 → 黑屏回 fastboot | ❌ |
| 12:16 | 分析：原镜像 kernel 是 gzip，改用 vmlinuz | ✅ 修正 |
| 12:19 | 刷回 pmos-boot2.img | ✅ 系统恢复 |
| 12:20–12:21 | 组装 boot-alsfix2.img（gzip + 62468 DTB） | ✅ 结构验证正确 |
| 12:22 | 刷入 → 黑屏 | ❌ |
| 12:34 | 回刷 pmos-boot2.img | ✅ 恢复 |
| 12:47–12:52 | 装新模块到平板、自建 initramfs | ✅ 但证实 initramfs 非根因 |
| 12:53 | 发现真实基线是 boot-current（DTB 62664） | ✅ 关键发现 |
| 12:55 | 组装 boot-final.img（gzip + 62664 DTB） | ✅ DTB 与工作镜像字节相同 |
| 12:57 | 刷入 → 黑屏 | ❌ |
| 13:19 | 刷回 boot-current-real.img | ✅ **完全恢复，MD5 一致** |

---

## 十、教训总结

### 做得对的

1. **每一步都先备份** —— 三次刷机失败、三次完整恢复，零数据损失。
2. **区分了"实验前真实状态"和"更早的基线"** —— `boot-current`（含 MI2S 补丁）vs `pmos-boot2.img`。
3. **穷举排除法** —— 9 个怀疑点逐个用实测数据排除，没有靠猜。
4. **先做了无风险的模块换入测试** —— 虽然失败，但避免了盲目刷机。
5. **文档实时更新** —— 每次失败都记录，避免重复。

### 做得不够的

1. **没有先做"最小改动对照实验"** —— 应该先用 clang 23.1.4 编译**不加补丁**的版本，
   若也黑屏就能立刻锁定是编译器问题，省下 3 次刷机。
2. **对 CFI 敏感性认识不足** —— 早该注意到编译器小版本差异 + `CONFIG_CFI=y`。
3. **`mkinitfs` 折腾太久** —— 那个 Go 程序在 musl 上有问题，应该早点放弃、自己写 cpio 工具
   （最终确实是自己写的才成功）。

### 下次的第一件事

```
用 clang 23.1.4 编译【不加任何补丁】的原版内核，刷入测试。
  - 若黑屏 → 确认编译器/CFI 问题，改用 23.1.3
  - 若能启动 → 说明是补丁本身的问题，回头检查补丁
```

这一步能彻底分离变量，成本只有一次编译 + 一次刷机。

| 坑 | 教训 |
|---|---|
| `vmlinuz.efi` vs `vmlinuz` | 本设备 boot.img **必须用 gzip 的 `vmlinuz`**，不是 EFI stub |
| 手写 patch 文件 | 行号/上下文容易错，**必须用 `diff -u` 从真源码生成** |
| APKBUILD sha512 正则替换 | 容易吃字符，改完**必须 `sha512sum -c` 验证** |
| `mkinitfs -d` 不写文件 | 这个版本的 mkinitfs 有 bug/行为差异，**自己写 cpio 打包器更可控** |
| 只看 `registry/config/*.json` | **必须看 `sensor_def_qcomdev.conf` + `sns.reg` 二进制 + DSP 回话**（11 文档的教训） |
| 正则解析 cpio | 路径格式多变，**用 `cpio -it` 或严格解析 newc 头** |
| PowerShell 内联 SSH 命令 | 引号/`$` 转义反复出错，**一律写 .sh 文件再执行** |

---

## 六、工具清单（全部可复用）

| 文件 | 用途 |
|---|---|
| `tools/pad_rebuild_cpio.py` | **★ 自己写 initramfs 打包器**（换模块、保结构） |
| `tools/pad_build_boot2b.sh` | 组装 boot.img（gzip + DTB，参数从原镜像继承） |
| `tools/pad_mk_kernel.py` | 拼接 vmlinuz + DTB |
| `tools/pad_chk_boot.py` | 校验 boot.img 结构 |
| `tools/analyze_black.py` | 对比内核镜像结构，定位黑屏 |
| `tools/extract_good_dtb.py` | 从工作镜像提取 DTB |
| `tools/check_kernel_fmt.py` | 判断 gzip / EFI / zstd |
| `tools/vm_*.sh` | VM 侧侦察、编译、诊断 |
| `tools/pad_*.sh` | 平板侧操作 |

证据：`evidence/vm-recon.txt`、`evidence/vm-module.txt`、`evidence/patch-verify.txt`、
`evidence/pad-modules.txt`、`evidence/vm-btf-*.txt`、`evidence/vm-cfg-diff*.txt`
