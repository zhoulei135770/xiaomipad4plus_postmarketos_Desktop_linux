# 21 · `fpc-redrive-supply` 核查结论：**死属性**，不是指纹的电源开关

> 2026-10-28 21:10，设备在 MoKee（Android 11 / 4.4.205 / root）上现场采集
> 采集物：`artifacts/mokee-20261028/`（`fdt.dtb` 341767 B、`c2/` 全部 sysfs/dmesg、`mokee-boot.img`）

---

## 0. 一句话结论

| 问题 | 答案 |
|---|---|
| pmOS DT 里有 `fpc-redrive-supply` 吗？ | **没有**（r253 实际 DTB 里 `fpc`/`redrive` 零命中） |
| 把它加进 pmOS DT 能修好指纹吗？ | **不能**。厂商自己的 SS PHY 节点 `status = "disabled"`，驱动从不 probe，属性从未被消费；pmOS 内核里也没有任何代码读 `redrive` |
| 它指向什么？ | `pm660_l11`（1.78 V），一条**被触摸/相机/DSI 共用的常开轨** |
| Android 下指纹的电源谁给？ | 硬件常开 + TEE 内部管理；**内核驱动完全不做 SPI**，也不驱动 GPIO92/98 |

---

## 1. 证据链

### 1.1 pmOS 侧（无）

```
$ fdt_tool.py sdm660-xiaomi-clover-plus.dtb search fpc      → 0 命中
$ fdt_tool.py sdm660-xiaomi-clover-plus.dtb search redrive  → 0 命中
$ fdt_tool.py ... path /soc@0/phy@c010000
    compatible = "qcom,sdm660-qmp-usb3-phy"
    status     = "disabled"
    （没有任何 *-supply）
```

* 内核源码 `arch/arm64/boot/dts/qcom/` 与 `drivers/phy/` 中 `redrive` **零命中** ⇒ 即使抄进 DT 也是 inert。
* clover DTS 只启用 `&qusb2phy0`（USB2），从未覆写 ssphy。

### 1.2 厂商（MoKee）侧（有，但死的）

从设备直接 `adb pull /sys/firmware/fdt`（341767 B，与 `tools/android-cam-data/vendor.dtb` 同尺寸）：

```
/soc/ssphy@c010000
  compatible          = "qcom,usb-ssphy-qmp-v2"
  status              = "disabled"        ← 关键
  fpc-redrive-supply  = <0x17b>
  qcom,redrive-load   = 0x19a28 (105 mA)
  qcom,redrive-voltage-level = 1800000..1950000

phandle 0x17b → /soc/qcom,rpm-smd/rpm-regulator-ldoa11/regulator-l11
              = pm660_l11, 1.78 V
```

同一个 `l11` 还被这些消费者引用：`gt9xx@5d vcc_i2c`、`focaltech@38 vcc_i2c`、
三路 `qcom,camera N cam_vio`、`mdss_dsi_ctrl0/1 wqhd-vddio`。
**它是一条共用 1.8 V 轨**，不是指纹专属开关。

全树 `fpc` 相关只有：`/soc/fpc1020` 节点 + 8 个 pinctrl 状态 + 这一条 supply。
`/soc/fpc1020` 本身 **没有任何 `*-supply`**。

### 1.3 MoKee 运行时电源状态（78 个 regulator 已存档）

```
pm660_l11  enabled  num_users=1  1780 mV     ← 共用 1.8V，在
pm660_l19  enabled  num_users=1  3312 mV     ← 3.3V（WiFi/BT）
pm660_l3b  (gt9xx vdd_ana)                   ← 3.0V
```

---

## 2. 厂商驱动到底管什么（源码已拿到，不用再猜）

MoKee 上跑的就是 FPC 官方 **`fpc1020_platform_tee.c`**（16 751 B）。
已下载：`tools/ref_fpc1020_platform_tee.c`
来源：<https://github.com/MoKee/android_kernel_sony_sdm660/blob/c3b11878c32e16dc6f474f639af1e98c04a7ae3d/drivers/input/misc/fpc1020/fpc1020_platform_tee.c>

它的真实能力边界（源码逐条）：

| 项 | 内容 |
|---|---|
| pinctrl | 只 lookup 三个状态：`fpc1020_reset_reset` / `fpc1020_reset_active` / `fpc1020_irq_active` |
| regulator | 只有一个 `vdd_ana`（3.3 V）—— 需要 DT 有 `vdd_ana-supply`；本机 `fpc1020` 节点**没有**，这条路径本来就走不通 |
| `vcc_spi` / `vdd_io` | **被注释掉** |
| SPI | **完全不做**（源码注释：*This driver will NOT send any commands to the sensor*） |
| reset 时序 | `reset_active`(高) 100–200 µs → `reset_reset`(低) 5000–5100 µs → `reset_active`(高) → 读 IRQ GPIO |
| IRQ | `IRQF_TRIGGER_RISING \| IRQF_ONESHOT`，wakeup |

### 由此得到三个推论

1. DT 里的 `fpc_avdd_active` / `fpc_vddio_active`（**gpio98 / gpio92**）这份驱动**根本不 lookup**。
   ⇒ **Android 下这两个脚谁都不驱动，默认态就是它们的工作态。**
2. 既然 Android 不拉高 92/98 而指纹照常工作 ⇒ 我们的 pmOS 驱动去拉高它们既不是必要条件，
   也不会因为"没拉对"而失败。**GPIO 供电假说可以彻底划掉。**
3. 指纹的模拟电源在 Android 里是**常开的硬件轨**，没有软件开关。

### 那 SPI 谁做？TEE

* dmesg 时间线：`fpc1020_probe: ok` (1.76 s) → `QSEECOM: App (fpctzapp) now loaded` (7.69 s)
* 内核只打印 `IRQ after reset 0` —— 那是 `gpio_get_value(irq_gpio)`，**不是读寄存器**
* TA：`/firmware/image/fpctzapp.mdt + b00..b07`（2019-05-15，b02 代码段 582 665 B）
* HAL `fingerprint.fpc.so` 里只有 `fpc_tac` / `fpctzapp` / `fpc1020` 符号 ⇒ 走 QSEECom
* TA 字符串里出现 `fpc1020`(11)、`fpc2060`(7)、`1021`(1) ⇒ 通用 1020 系列 TA

> ⚠️ 结论：**Android 侧拿不到 SPI 报文做对照**，唯一参考仍是 `tools/fpc_decomp.c`。
> 这也是为什么"对比 MoKee 的 SPI"这条路走不通。

---

## 3. 那 pmOS 的恒定图像（153/154/155）是什么问题

排除法之后只剩两类：

1. **模拟前端没配置**（最可疑）
   我们的 `fpc1020_apply_config()` 出于"设了反而检测不到手指"的实测，**故意不写**
   `0xA0 ADC_SHIFT_GAIN` 和 `0xA8 PXL_CTRL`；而厂商参考驱动 `fpc1020_write_sensor_1020a_a3a4_setup()`
   是**必写**的（`0xA0 = shift<<8 | gain`，LO_a3a4 正常档 = `0x0B01`；`0xA8 = 0x0f0b`）。
   ADC 增益/移位留在复位默认值时，输出恒定中间值 —— 与观察完全吻合。

2. **几何/表选错**
   参考表 LO_a3a4：`row_start 19 / row_count 171 / col_start 2 / col_groups 21`
   ⇒ 图像长度 = 171 × 21 × 8 = **28 728 B**；我们现在只读 `64*176+2 = 11 266 B`。
   另外 `0xFC` 读回 `0x0341`，与参考 `chip_data` 的 `0x020a / 0x021a / 0x021b / 0x150a / 0x140b`
   **都不匹配** —— 表是不是选对了要打问号。

---

## 4. 回到 pmOS 后的实验顺序（不用重编内核 —— 脚本已备好）

> 关键细节：`capture_now` **每次都会跑 `fpc1020_apply_config()`**，把 `0x90/0x68/0x8C/0x5C/0x54`
> 重写一遍、并做 `0x94/0xEC/0xAC/0xDC` + 校准。它**唯一不写的就是 `0xA0/0xA8`** ——
> 恰好是我们要试的两个，所以手写的值能活下来。`0x54` 由 `img_capt_size` 模块参数控制。

一键脚本：`scripts/fpc_regtest.sh`（拷到平板 root 下 `sh fpc_regtest.sh`）。

它做四组对照，每组抓完图直接给直方图摘要（distinct / min / max / top5 / 头 24 字节）：

| 组 | 0xA0 ADC_SHIFT_GAIN | 0xA8 PXL_CTRL | 说明 |
|---|---|---|---|
| base | 不写（现状） | 不写 | 只把读取长度从 11266 加到 **28728** |
| A | `0x0B01` (shift 11, gain 1) | `0x0f0b` | 厂商 LO_a3a4 **正常**档 |
| B | `0x0408` (shift 4, gain 8) | `0x0f0a` | **dry** 档 |
| C | `0x0600` (shift 6, gain 0) | `0x0f1f` | **wet** 档 |

判读：
* 四组都还是单峰 153/154/155、min==max ⇒ 模拟前端仍没起来，问题在**芯片/表选择**
  （`0xFC` 读回 `0x0341`，与参考 `chip_data` 的 `0x020a/0x021a/0x021b/0x150a/0x140b` 都不符）
* 任一组 distinct > 8 或 min≠max ⇒ **真的有像素了**，接着扫 `a0/a8` 附近的值，
  再定 `img_capt_size` / 几何
* 打印 `capture_now: no image (intr=0x..)` ⇒ 0xC0 握手失败，记下 intr 值，那是下一条线索


---

## 5. 已排除 / 不要再做

* ❌ 往 pmOS DT 加 `fpc-redrive-supply`（无驱动消费，ssphy disabled）
* ❌ 再纠结 GPIO92/98 电平（Android 也不驱动）
* ❌ 读 `/sys/kernel/debug/regulator/regulator_summary` 或 `clk_summary`（**会让 4.4 内核死锁**，
  2026-10-28 已复现一次，必须长按电源重启）
* ❌ 试图在 Android 侧抓 SPI（在 TEE 里）

---

## 6. 本次新增的本地产物

| 文件 | 内容 |
|---|---|
| `artifacts/mokee-20261028/fdt.dtb` | 运行中的完整 FDT（厂商 DT，权威） |
| `artifacts/mokee-20261028/c2/` | dmesg / kallsyms / config.gz / 78 个 regulator / fpc sysfs / DT 节点 hex / logcat |
| `artifacts/mokee-20261028/mokee-boot.img` | MoKee boot 分区 64 MiB（内核内是那份 platform_tee 驱动） |
| `tools/fdt_tool.py` | 自写的 FDT 解析器（nodes / path / phandle / refs / search） |
| `tools/ref_fpc1020_platform_tee.c` | 厂商平台驱动源码（已核实与设备行为一致） |

---

## 7. 2026-10-28 夜 · pmOS 上实测（恢复系统后，免重编）

### 7.1 `0xA0 / 0xA8` 不是答案

四组对照（base / LO_a3a4 normal / dry / wet）全部抓到 28728 字节，
但**全部是平线**：`distinct 4–7，min 150 max 156，153/154 占 95%`。
⇒「ADC 增益/移位没配」这个假设**排除**。

### 7.2 意外发现：`IMG_CAPT_SIZE (0x54)` 的编码和我们的值

参考驱动 `fpc1020_capture_set_crop()`：

```c
temp_u32  = first_row;
temp_u32 <<= 8; temp_u32 |= num_rows;
temp_u32 <<= 8; temp_u32 |= (first_column * adc_group);   /* adc_group = 8 */
temp_u32 <<= 8; temp_u32 |= (num_columns * adc_group);
```

我们的值 `0x4000B000`（字节序 `00 B0 00 40`）解出来是 **176 行 × 64 列**，
正好等于驱动读的 11264 字节 —— 说明这个窗口是"有效但被裁过"的。

改成全帧 `0x00C000C0` / 厂商表 `0x13AB10A8` 后：**采集直接不出帧**（`intr=0x00`），
且把传感器留在了坏状态（`0x54` 读回全 0，只能重启恢复）。
⇒ 原来的 `0x4000B000` 是这块模组的正确窗口，**不要再改**。

### 7.3 `reset_before_capture=1` 让连续采集变可用

默认参数下**只有复位后第一帧能抓到**，之后就 `no image (intr=0x00)`。
把 `reset_before_capture` 设为 1（每帧前硬复位）后，**连续 5 帧全部成功**。
⇒ 这个参数不是"可选项"，是连续采集的必要条件；之前"它会破坏采集"的结论是错的。

### 7.4 供电与 GPIO：全部正常，不是电源问题

```
gpio71  in  low     (IRQ)
gpio92  out high    (fpc_vddio)
gpio98  out high    (fpc_avdd)
gpio108 out high    (reset 释放)
gpio24-27 func1     (blsp_spi7，SPI 引脚复用正确)
```

稳压器对比（pmOS vs MoKee 现场）：

| 轨 | pmOS | MoKee（指纹可用） |
|---|---|---|
| l11 | enabled 1.784 V | enabled 1.780 V |
| l13 | enabled 1.780 V | **disabled** |
| bob | enabled 3.3 V | disabled（pin1 3.6 V） |
| l19 | enabled 3.2 V | enabled 3.312 V |

⇒ 两边的轨都在，**没有"少了一条电源"**。

### 7.5 寄存器全景（pmOS，复位后）

```
0x14 FPC_STATUS      = 00        ← 注意：不是 0x0e(idle)
0x1c IRQ(clear)      = ff (刚复位)
0x38 READ_ERROR      = 01        ← 错误位有置位
0x54 IMG_CAPT_SIZE   = 00 b0 00 40
0x5c IMAGE_SETUP     = 0b (采集时)
0x64 IMG_RD          = 1e
0x78 TST_COL_PATTERN = aa 55     ← 可疑（列测试图案）
0x8c FINGER_DRIVE_CONF = 02
0x90 FINGER_DRIVE_DLY  = 00 (读回) / 写的是 09
0x94 OSC_TRIM        = 1a 07
0x98 ADC_WEIGHT_TABLE= 03 e9 bf 37 fe 05 19 32 9b 66
0x9c ADC_SETUP       = 00 55 40 00 3f
0xa8 PXL_CTRL        = 0f 00
0xd8                 = 13 11 10 10 ...（校准写入的 4 个 code）
0xfc HWID            = 03 41
```

**多字节读有明显字节错位**：写 `0x68 = 14 14 14 14 08 08 08 08`，
读回 `08 14 14 14 14 08 08 08` —— 整体右移一字节。
⇒ 以后不要用读回值判断写入是否生效。

### 7.6 一个决定性的矛盾

* **校准路径（0xF0/0xF4）会随手指变化**：空载 `13 11 10 10`，手指按下 `15 14 13 11` / `15 15 13 11`
  ⇒ 模拟前端**是活的**，能感知电容变化。
* **图像路径（0xC0/0xC4）无论有没有手指都是 153/154 的平线**。

⇒ 问题不在电源、不在 ADC 配置，而在**图像采集/读出这条路径**：
要么 `0xC0` 没有真正触发扫描（`0x14` 读到 0x00 而不是 idle 的 0x0e），
要么 `0xC4` 读到的不是像素 FIFO（例如 `0x64 IMG_RD=0x1e`、`0x78=0xAA55` 这类可疑状态）。

### 7.7 下一步的关键解锁：驱动是**可加载模块**

```
/lib/modules/7.0.14-sdm660/kernel/drivers/input/misc/fpc1020.ko.zst
```

⇒ 不用重编内核、不用刷机，**改驱动 → VM 编一个 .ko → 推上去重启 → 测**，
单轮迭代 5 分钟左右。而且 `apply_config()` 里把 `finger_drive_conf/dly`
写死成 `0x02/0x09`、模块参数没接上，这类问题一改就能验。

⚠️ 老文档里"绝不卸载 fpc1020 模块"仍然有效 —— 用**重启**加载新 .ko，不要 `rmmod`。

---

## 8. 模块编译流水线（已跑通一半，卡在 CFI）

### 已经可行的部分

1. 从设备取**精确配置**：`zcat /proc/config.gz`（220 318 B）→ `backup/kernel-config-7.0.14-sdm660.txt`
2. 内核树：VM `~/MiPad4Plus_Ubuntu_Porting/03_Kernel_Source/linux`（正好 7.0.14）
3. 把 `tools/fpc1020_params.c` 放进 `drivers/input/misc/`，Makefile 追加 `obj-m += fpc1020.o`
4. `make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig modules_prepare`
5. `make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- M=drivers/input/misc KBUILD_MODPOST_WARN=1 modules`
   → 90 秒出 `fpc1020.ko`（471 KB，含 DEBUG_INFO）

### 踩到的两个坑

**① vermagic 多了 `+`**：源码树带 `.git` 且被判定为脏，`scripts/setlocalversion` 追加 `+`。
修法：编译期间 `mv .git .git.hold`（编完再挪回来），release 就变回 `7.0.14-sdm660`。

**② 最大的坑：`CONFIG_CFI=y`**
```
CONFIG_CFI=y
CONFIG_CFI_ICALL_NORMALIZE_INTEGERS=y
CONFIG_LTO_NONE=y
```
运行内核是 **Alpine clang 23.1.4 + LLD** 编的，带 CFI；用 GCC 编出来的模块加载时报：
```
module fpc1020: .gnu.linkonce.this_module section size must match
                the kernel's built struct module size at run time
```
（`struct module` 里含 CFI 相关成员，GCC 编不出来）。

### 下一步（唯一正确路径）

用 pmbootstrap chroot 里的**同一套 clang 交叉工具链**编：

```
~/.local/var/pmbootstrap/chroot_rootfs_xiaomi-clover/usr/bin/
  aarch64-alpine-linux-musl-clang / -clang++ / ld.lld
```
做法：把内核树 bind-mount 进 chroot，用
`CC=aarch64-alpine-linux-musl-clang LD=ld.lld AR=llvm-ar ... make M=drivers/input/misc modules`
（或直接 `pmbootstrap build linux-postmarketos-qcom-sdm660` 走正规打包，30-60 分钟）。

### 驱动补丁内容（`tools/fpc1020_params.c`，已生成）

| 改动 | 目的 |
|---|---|
| `finger_drive_conf/dly` 默认值 0x02/0x09，且 `apply_config()` 真正使用这两个参数 | 能扫 finger drive 取值范围（原来写死，参数是摆设）|
| `capture_now` 尊重 `skip_config` | 用 `cmd` 手写寄存器后不会被 `apply_config` 覆盖，可做任意序列实验 |
| 采集成功后打印 `status(0x14)` 与 `err(0x38)` | 直接看到"为什么这帧是平的" |

⚠️ 当前平板已**恢复原模块**（`fpc1020.ko.zst.orig`），`dmesg` 显示 `FPC1020 ready (irq=151)`，系统正常。

---

## 9. 模块编译：链条打通，卡在最后 64 字节（2026-10-28 22:30）

### 打通的部分

| 环节 | 结果 |
|---|---|
| 精确源码 | 在 pmbootstrap 缓存里找到 **`linux-v7.0.14-sdm660.tar.gz`**（260 MB，就是编译 r253 用的那份）|
| 工具链 | clang-18 + lld-18（从 apt.llvm.org 装；Ubuntu 自带的 14/15 都不行）|
| `CONFIG_CFI` | ✅ 用 clang-18 后 `olddefconfig` 保留 `CONFIG_CFI=y`（clang-15 不支持 `-fsanitize=kcfi`，会被丢弃）|
| vermagic | ✅ `7.0.14-sdm660 SMP preempt mod_unload aarch64` |
| 编译 | ✅ 3 分钟出 `.ko`（含 DEBUG_INFO）|

### 仍差一步：`struct module` 1216 vs 1280

```
新编 .gnu.linkonce.this_module  = 0x4c0 (1216)
设备原模块                      = 0x500 (1280)   ← 内核期望值
```

即使换成**同一份源码 tarball** 仍然差 64 字节，且：
```
CONFIG_CFI=y                       ← 已开
ARCH_USES_CFI_TRAPS                ← 未选中（arm64 的 Kconfig 里没有 select 它）
```
`struct module` 里 CFI 相关的成员是：
```c
#ifdef CONFIG_ARCH_USES_CFI_TRAPS
	s32 *kcfi_traps;
	s32 *kcfi_traps_end;      /* 16 字节 */
#endif
```
16 字节对上，但还差 48 —— 说明**还有别的成员差异**，不是单纯 CFI 一项。

### 下一步（明确、便宜）

设备内核 `CONFIG_DEBUG_INFO_BTF=y`，所以 **`/sys/kernel/btf/vmlinux` 存在**，
里面有运行内核里 `struct module` 的**精确成员与偏移**。
拉下来用 `bpftool btf dump file vmlinux format c`（或 pyelftools 解析 BTF）
跟源码里的 `include/linux/module.h` 逐字段对比，就能定位那 64 字节来自哪个成员，
再决定是补配置还是补补丁。

### ⚠️ 电量

2026-10-28 22:27 实测平板 **21%，充电中**。平板侧实验（部署模块、抓图）全部暂停，
只做 VM 侧编译。

### 当前平板状态

原模块已还原，`dmesg: FPC1020 ready (irq=151)`，系统正常，SSH 可用。

### 9b. BTF 已取回，布局差在尾部（22:33）

从设备拉了 `/sys/kernel/btf/vmlinux`（5 470 181 B，存 `build/vmlinux.btf`），
用自写的 [tools/btf_struct.py](tools/btf_struct.py) 解析出运行内核的 `struct module`：

```
size = 1280 (0x500), 67 members
尾部: ... 1160 source_list, 1176 target_list, 1192 exit, 1200 refcnt, 1208 dyndbg_info
```

**注意：设备内核里根本没有 `kcfi_traps` 成员**（BTF 里没有），所以 CFI 不是那 64 字节的来源。
我们编出来的是 1216（DWARF 确认 `DW_AT_byte_size 0x04c0`），差的 64 字节在尾部某一项
（`refcnt` / `dyndbg_info` 区域），需要把两边的成员列表逐项对比才能定位。

已排除的配置差异（设备 vs 本地一致）：`DYNAMIC_DEBUG / KPROBES / FTRACE / FUNCTION_TRACER /
TRACEPOINTS / EVENT_TRACING / BPF_EVENTS / KALLSYMS / MODULE_UNLOAD / SRCU / JUMP_LABEL /
LIVEPATCH / STATIC_CALL`，唯一不同的是 `CONFIG_DEBUG_INFO_BTF`（不影响 struct module）。

下一步：用 `llvm-dwarfdump-18 --debug-info --show-children` 打出我们这边的成员表，
和 BTF 的 67 项逐一对齐，找出少掉的那几个成员属于哪个 `#ifdef`。

---

## 10. 模块编译彻底打通 + finger-drive 扫描（2026-10-28 22:40）

### 10.1 struct module 之谜解开

之前差的 64 字节 = **`CONFIG_DEBUG_INFO_BTF` 的 4 个字段**（`btf_data_size / btf_base_data_size /
btf_data / btf_base_data` = 24 B）+ 64 字节对齐后正好 1280。

`DEBUG_INFO_BTF` 被 `olddefconfig` 丢掉，是因为**没装 `pahole`**（BTF 生成依赖它）。
装上 `dwarves` 之后用同一份源码 tarball + clang-18 重编：

```
新编 .gnu.linkonce.this_module = 0x500
设备原模块                     = 0x500   ✅ 一致
vermagic: 7.0.14-sdm660 SMP preempt mod_unload aarch64
```

**模块成功加载**：`fpc1020 spi0.0: FPC1020 ready (irq=151)`，
参数生效（`finger_drive_conf=2` / `finger_drive_dly=9`）。

### 10.2 编译配方（可复用）

```sh
# 源码：~/.local/var/pmbootstrap/cache_distfiles/linux-v7.0.14-sdm660.tar.gz
# 工具链：clang-18 + lld-18 (apt.llvm.org) + dwarves(pahole)
cp /tmp/kconfig .config        # 从设备 /proc/config.gz 取
make ARCH=arm64 CC=clang-18 LD=ld.lld-18 AR=llvm-ar-18 NM=llvm-nm-18 \
     OBJCOPY=llvm-objcopy-18 OBJDUMP=llvm-objdump-18 STRIP=llvm-strip-18 \
     olddefconfig modules_prepare
make ... M=drivers/input/misc KBUILD_MODPOST_WARN=1 modules
```
⚠️ `.config` 必须**每次从设备配置重新覆盖** —— `olddefconfig` 不会把已经被关掉的符号再打开。

### 10.3 finger-drive 扫描结果：传感器是活的

| 状态 | distinct | min–max |
|---|---|---|
| 无手指 | 4–6 | 153–155（平线）|
| **有手指** | **17–24** | **143–172** |

⇒ **图像对比度随手指出现而显著上升**，模拟前端和 finger drive 都在工作。
（`conf/dly` 六组取值 0x02/0x09、0x02/0x18、0x02/0x00、0x00/0x09、0x01/0x09、0x03/0x09
都能出图，肉眼差别不大 —— 说明这两个参数不是关键。）

### 10.4 但图像还不是指纹

渲染出来是**横向条纹噪声**（每一行一个随机偏置，均值恒为 154.0），不是脊线纹理。
→ 下一步嫌疑：
1. **窗口太小**：现在只读 176 行 × 64 列 = 1/3 的列；真正的 FPC1020 是 192×192，
   可能需要 `0x54 = 0x00C000C0`（之前试过会不出帧，可能是没配合 `0x5c/0x4c` 或读长度）
2. **行偏置未校正**：每行固定 offset 说明 `PXL_RST_DLY / SAMPLE_PX_DLY` 或 ADC 权重表没配好
3. 需要按参考驱动的完整 `capture_set_crop + write_sensor_a3a4_setup` 顺序再来一遍

### 10.5 当前平板状态

* 新模块**保留在设备上**（比原版多了：参数化 finger drive、`skip_config` 生效、采集后打印 status/err）
* 原版备份：`fpc1020.ko.zst.orig`
* 电量 32% 充电中
* 帧数据：`artifacts/mokee-20261028/fpc-frames/`（fx0–2 有手指、x0 无手指、PNG 渲染）

### 10.6 全帧 192×192 尝试（skip_config 手动寄存器）

```
写 0x54 = 00 c0 00 c0  (row0/192, col0/192)   ← 回读确认生效
read_len = 36866
结果: 36864 B, distinct=4, min=102 max=105    ← 另一个常数，不是图像
恢复 176×64 窗口后: distinct=3, 153–155       ← 回到基线
```

⇒ 单纯把窗口改大**不行**（读数变成另一条平线 102–105）。
说明还有别的寄存器必须跟着改（`0x4C IMG_SMPL_SETUP` 当前 `00 ff ff`、
`0x98 ADC_WEIGHT_TABLE`、`0x9C ADC_SETUP` 等都是 OTP 值），
或者这种模组的读出控制器只支持厂商设定的那条窗口。

**下一步必须按参考驱动的完整顺序来**：`capture_set_crop()` → `write_sensor_1020a_a3a4_setup()`
→ `fpc1020_capture()`（含 `FINGER_PRESENT_QUERY` 0x20 命令）→ `fetch_image()`，
而不是只改其中一个寄存器。

---

## 11. 照参考驱动的顺序试：暴露出真正的卡点（2026-10-28 22:50）

### 11.1 厂商协议（从 `fpc1020_capture.c` + `fpc1020_common.c` 读出来的完整顺序）

```
fpc1020_wake_up()                 # 软复位 0xF8 → 等 0x1C 读到 0xFF → 轮询 0x14 到 0x0e(idle)
fpc1020_write_sensor_setup()      # a3a4 表：0x90/0x68/0x8C/0xA0/0xA8/0x5C/0xD8/0xDC
fpc1020_capture_set_crop()        # 0x54 = row_start/rows/col_start/cols(组×8)
（可选）FINGER_PRESENT_QUERY 0x20  # 等 COMMAND_DONE(0x80)
每帧: fpc1020_capture_settings(i) # 按 dry/wet/normal 选 adc_gain/shift、pxl_ctrl
      0xC0 CAPTURE_IMAGE          # 等 FIFO_NEW_DATA(0x20)
      0xC4 READ_IMAGE             # 读 image_size = rows × col_groups × 8
重复 capture_count = 3 帧
```

### 11.2 我们的芯片**不回应软复位**

打开 `wake_before_capture=1` 后：

```
capture_now: wake not confirmed (-5)     ← 0xF8 之后 0x1C 始终读不到 0xFF
capture_now: status=0x00 err=0x01        ← 状态永远不是 idle 的 0x0e
```

即使 reset 后 0x1C = 0xff，状态寄存器 0x14 仍是 **0x00**，不是 idle 的 **0x0e**。
⇒ 芯片停在一个厂商驱动不会遇到的模式里。这不是"读图参数不对"，而是**芯片没进工作态**。

### 11.3 可能的原因（下一步按这个顺序查）

1. **上电/复位时序**：厂商平台驱动是 `vdd_ana` 3.3V → 100–1000 µs → reset_active(高) → 100–200 µs
   → reset_reset(低) → 5000–5100 µs → reset_active(高)。我们的驱动只做了简单的高→低→高，
   **没有电源上下电与延时**。可以照抄到 probe 里。
2. **芯片可能停在 sleep/deep-sleep**：厂商有 `ACTIVATE_IDLE_MODE = 0x34`，
   先发 0x34 再试 0xF8，或直接 0x34 → capture。
3. **命令字发送格式**：参考驱动命令是 **单字节** `spi_transfer`（cs_change=1），我们一样；
   但有的 FPC 变种要求命令后跟一个哑字节，值得一试。
4. **TA 反编译**仍是最终裁判（fpctzapp 里一定有正确的唤醒/采集序列）。

### 11.4 当前状态

* 新模块保留（可用 `reset_before_capture=1` 稳定重复采集）
* 参数已恢复默认（`img_capt_size=0x4000B000`、`read_len=11266`、`wake=0`）
* 电量 34% 充电中
* 结论：**瓶颈从"图像参数"变成了"芯片唤醒/上电时序"** —— 这是今晚最有价值的定位

---

## 12. v2 驱动：照抄上电时序 + 唤醒命令可调（2026-10-28 23:00）

### 12.1 v2 驱动改了什么（`tools/fpc1020_v2.c`）

| 改动 | 说明 |
|---|---|
| `fpc1020_power()` 重写 | `avdd` 上电 → `udelay(power_delay_us=1000)` → `vddio` 上电 → 延时；下电顺序反过来 |
| `reset_hold_ms = 5` | 复位脉冲从 20 ms 改成厂商的 5 ms |
| `wake_cmd` 参数（默认 0xF8）| 可以改成 `0x34`(ACTIVATE_IDLE_MODE) 等别的唤醒命令 |
| `idle_before_capture` 参数 | 采集前先发 `0x34` |

编译产物：`struct module = 0x500` ✅，vermagic 正确，**模块加载成功**。

### 12.2 结果：唤醒仍然不成立

```
wake with 0xf8 -> capture_now: wake not confirmed (-5)
wake with 0x34 -> capture_now: wake not confirmed (-5)
status(0x14) 永远是 0x00，IRQ(0x18) = 0x04 (ERROR 位)
```

⇒ 电源时序**不是**根因。

### 12.3 新线索：寄存器读存在字节错位

复位后同一寄存器的不同长度读：

```
0x94 (OSC_TRIM, 2B):  1-byte -> 1a      2-byte -> 07 00     (应为 1a 07)
0x5c (IMAGE_SETUP):   1-byte -> 0b      2-byte -> 00 00
0x18 (IRQ):           1-byte -> 04      2-byte -> 00 00
0x1c (IRQ clear):     1-byte -> 04      3-byte -> 00 00 e0
```

`0xfc`(HWID) 两字节读 `03 41` 正常，但其它寄存器的多字节读看起来整体移位。
**要么是 SPI 采样边沿/时序问题，要么是驱动 `read_reg` 对 n>1 的消息构造有问题。**
下一步应该：
1. 用逻辑分析仪或把 SPI 降到 500 kHz/100 kHz 复测（排除边沿）
2. 检查 `fpc1020_read_reg()` 的 spi_message 构造是否与厂商 `fpc1020_reg_access()` 一致
   （厂商是先发命令字节再单独一个 rx transfer，且 `cs_change` 语义不同）

### 12.4 结论

* 电源时序、finger drive 参数、ADC 配置 —— **全部排除**
* 剩两个方向：
  a) **SPI 读协议/时序**（字节错位是硬证据，可能解释"状态读不到 idle"）
  b) **TA 反编译**（fpctzapp 里的真实序列）

### 12.5 设备状态

v2 模块在设备上并正常加载（`FPC1020 ready (irq=151)`），
参数默认值：`wake_cmd=0xf8`、`idle_before_capture=0`、`reset_before_capture` 由测试脚本设置。
原版备份 `fpc1020.ko.zst.orig` 仍在。电量 36% 充电中。

---

## 13. 突破：状态寄存器读法 + 字节序（2026-10-28 23:10）

### 13.1 根因之一：状态寄存器要发 **2 个字节**

厂商 `fpc1020_regs.h`：

```c
#define FPC1020_REG_ACCESS_DUMMY_BYTES(reg) (        \
    ((reg) == FPC102X_REG_FPC_STATUS) ?      1 : \   /* 0x14 */
    ((reg) == FPC102X_REG_FPC_DEBUG)  ?      1 : 0)  /* 0xD0 */
```

命令阶段长度 = `1 + DUMMY_BYTES(reg)`。我们的驱动只发了 1 字节，
所以 **0x14 永远读回 0x00** —— 驱动因此一直以为芯片"从不 idle"。

补上之后：

```
reg 0x14 = 1f     → bits1-3 = 0x0e = IDLE  ✅
reg 0x18 = ff     → 复位后 IRQ 正常
wake: idle after 0 ms (status 0x1e)          ✅ 唤醒成功
```

**芯片从头到尾都是好的。** 之前"wake not confirmed / status 0x00"全是读寄存器读错造成的假象。

### 13.2 根因之二：多字节寄存器是**大端**，我们发的是小端

厂商 `fpc1020_reg_access()` 在 `target_little_endian` 下会**把字节反转**再放到 SPI 总线上；
读方向也反转。所以：

```c
uint32_t v = 0x00C000C0;              /* row0/192, col0/192 */
/* 总线上实际是 00 C0 00 C0（大端） */
```

我们一直按小端发 `A8 10 AB 13` 而不是 `13 AB 10 A8`，
**所有多字节写入（0x54 裁剪窗口、0x68、0x98、0x9C、0xD8、0xDC…）字节序全是反的**。
这解释了为什么之前改 `0x54` 要么无效、要么出乱数据。

### 13.3 现状

* v4 模块在设备上，`reg_dummy_bytes=1` 默认开启
* 状态、唤醒、IRQ 全部正常
* 图像仍是**横向条纹**（每行一个偏置，均值 154），不是脊线
* 有手指时对比度 143–172，无手指 153–155 —— 传感器确实在感知

### 13.4 下一步（很明确）

1. **把驱动的读写全部改成大端**（写反转、读反转），再重试 `0x54 = 0x13AB10A8` 厂商裁剪窗口
2. 每行偏置说明可能需要 **ADC 权重/逐行校正**，或读出的 FIFO 排列不是行优先
3. TA 反编译仍可作为交叉验证

### 13.5 设备状态

v4 模块，参数已恢复默认（`img=0x4000B000`、`read_len=11266`、`dummy=1`），
电量 **41% 充电中**，`capture_now: status=0x0f`（idle）。

---

## 14. v5：大端字节序生效，图像仍无脊线（2026-10-28 23:22）

### 14.1 大端改动验证通过

v5 驱动（`tools/fpc1020_v5.c`）对多字节寄存器做读/写反转。结果：

```
0x94 (OSC_TRIM) = 0x1a07      ✅（之前读成 07 00）
0xfc (HWID)     = 0x0341      ✅
0x54 (CAPT_SIZE)= 0x00B00040  ✅（row0/176, col0/64）
0x14 (STATUS)   = 0x0e        ✅ 纯 idle
```

写厂商裁剪窗口 `0x13AB10A8`（row19/171, col16/168）后回读 `0x139F10A8`
—— **行数字节 0xAB 被芯片压成 0x9F**（171 → 159），说明该字段有位宽限制，
或者芯片按自己的规则回绕。

### 14.2 用厂商窗口抓图的结果

```
28728 B, distinct 16–24, min 134 max 164, row_spread 12.4
```

渲染（168×171）仍是**横向条纹**；把每行均值减掉后只剩噪声，
只有最左 ~40 列有纵向条带。

⇒ 目前读到的更像 **ADC 噪声**，不像指纹图像。

### 14.3 下一步：用测试图案验证读出通路（关键、便宜）

驱动已有 `test_pattern` 参数，参考驱动里有
`fpc1020_write_sensor_checkerboard_setup_1020()`（写 `0x78 TST_COL_PATTERN_EN`
= 0xAA55 / 0x55AA 等图案）。

**如果打开棋盘图案后能读出规则棋盘，说明读出通路完全正确**，
问题就锁定在模拟前端/驱动时序；如果读出来还是噪声，说明读出通路本身有问题。

这是下一步最有价值的一个实验，不需要外部仪器。

### 14.4 设备状态

v5 模块，参数恢复默认（`img=0x4000B000`、`read_len=11266`、`big_endian=1`、`dummy=1`），
状态 `0x0e`（idle），电量 **43% 充电中**。
`fpc1020.ko.zst.orig` 原版备份仍在。

---

## 15. 棋盘图案验证：读出通路是通的（2026-10-28 23:15）

### 15.1 大端改动带来的参数语义变化（容易踩）

改成大端之后，`img_capt_size` 参数的含义变成**"寄存器应该持有的值"**，不再是"要发到总线上的字节"。

```
正确：0x00B00040 = 11534400   (row_start 0, rows 176, col_start 0, cols 64)
错误：0x4000B000 = 1073786880 (这会被当成 row_start 0x40, rows 0 → 0 行 0 列)
```

踩过一次：参数还是旧值 → `capture_now: no image (intr=0x00)`，采不到任何数据。
**以后所有 0x54 的参数都要用"值"来写。**

### 15.2 棋盘测试图案 = 决定性实验

v6/v7 驱动里把参考驱动的 `fpc1020_write_sensor_checkerboard_setup_1020()`
（rev ≥ 3 分支）接上了 `test_pattern` 参数：

```
0x68 = 0x141414141e1e1e1e   0x6c = 0x0f    0x90 = 0x15   0x8c = 0x02
0xa0 = 0x1100               0xa8 = 0x0f1b  0x5c = 0x0b
0xd8 = 0x50                 0xdc = 0x0005  0x78 = pattern
```

结果（同样的采集流程，只改 `test_pattern`）：

| test_pattern | distinct | 范围 |
|---|---|---|
| 0（关）| 4–5 | 147–151 |
| 0xAA55 | **2** | **254–255** |
| 0x55AA | **2** | **254–255** |
| 再关掉 | 4 | 148–151 |

⇒ **改动传感器寄存器会直接改变读出的 FIFO 内容** ——
**读出通路（SPI 命令 → 采集 → FIFO → 读图）完全正常。**

但图案饱和成 255/255，说明棋盘配置里的 ADC 增益（`0xa0 = 0x1100`）太大，把图案打到满量程。

### 15.3 这意味着什么

* 剩下的问题**不在 SPI 协议、不在读出通路、不在状态机**
* 剩下的只有两种可能：
  1. **ADC 增益/移位**：正常配置下增益太小（或偏置不对），指纹的电容变化淹没在噪声里
  2. **模拟前端（finger drive 信号）**：确实没有激励到手指

下一步就是用棋盘图案 + 扫 `0xa0` 增益，找到"图案能看出明暗格"的增益区间，
再用同样增益去拍手指 —— 如果能出脊线就成功了。

### 15.4 设备状态

v7 模块（含棋盘图案），参数：`img=0x00B00040`、`read_len=11266`、`big_endian=1`、
`reg_dummy_bytes=1`、`test_pattern=0`，状态 `0x1f`，电量 **46% 充电中**。

---

## 16. ADC 增益扫描：增益寄存器确实在工作（2026-10-28 23:25）

用棋盘图案 + `adc_gain` 参数扫描 `0xa0`（ADC_SHIFT_GAIN）：

| adc_gain | distinct | min–max | 主流值 |
|---|---|---|---|
| 0x1100 | 2 | 254–255 | 255（饱和）|
| 0x0f00 | 4 | 245–248 | 247 |
| 0x0800 | 4 | 201–204 | 203 |
| 0x0400 | 4 | 176–179 | 177 |
| 0x0200 | 3 | 163–165 | 164 |
| 0x0100 | 4 | 156–159 | 158 |
| 0x0080 | 4 | 150–153 | 151 |
| 0x0010 | 4 | 150–153 | 151 |
| 0x0001 | 6 | 157–162 | 160 |
| 0x0000 | 2 | 254–255 | 255 |

**输出电平随增益单调变化 ⇒ ADC 增益寄存器确实生效、数据不是随机噪声。**

但有个关键现象：**即使开着棋盘图案，整帧仍然只有一个电平**（distinct 2–6，且都是相邻值），
没有出现"明暗交替的格子"。

⇒ 这说明读出的 11264 字节**不是逐像素的图像阵列**，更像是**同一个采样点被重复读出**，
或者 FIFO 内容与像素位置无关。这与"正常采集时能看到行间起伏"又矛盾，
需要进一步确认 FIFO 的行/列组织方式（很可能是列并行读出，需要按 ADC 通道解交织）。

### 下一步

1. 结合正常采集（有手指时 143–172 的起伏）和棋盘（单电平），推断 FIFO 的真实组织：
   读一小段（如 256 字节）看是否重复同样的 8/16 字节块
2. 若确认是列并行：按 `171 行 × 21 组 × 8 ADC` 解交织后重排成图
3. TA 反编译可给出 FIFO 布局的最终答案

### 设备状态

v8 模块，参数恢复默认（`img=0x00B00040`、`adc_gain=0`、`test_pattern=0`），
状态 `0x1f`，电量 **48% 充电中**。

---

## 17. FIFO 组织与 TA 数据表（2026-10-28 23:35）

### 17.1 帧数据的周期性分析（`tools/analyze_fifo.py`）

对厂商窗口的一帧（28728 B，有手指）做周期性统计：

```
period=8   : 82.5% 的字节完全相同   ← 关键
period=16  : 79.1%
period=24  : 76.1%
period=32  : 73.1%
period=168 : 35.6%（一行）
period=1008: 32.7%
```

按 `index % 8` 分组，8 组均值全部约 150.0–150.4（无通道偏置）。
最常见 8 字节块：`95 95 95 95 95 95 95 95`（300 次）。

⇒ **FIFO 以 8 字节为一组，组内几乎恒定，组间缓慢变化。**
这正是"列并行读出、每组 8 个 ADC 对应 8 个相邻列"的特征，
也解释了为什么按"64 列行优先"渲染出来全是横条纹。

**解交织方向**：把流按 `组（8 字节）× 行` 重排，即
`row = i // 168`、`group = (i % 168) // 8`、`adc = i % 8`，
再按 `(adc, group)` 映射到列。

### 17.2 TA 里的变体表

`fpctzapp.b02` 偏移 `0x73b3c` 处有一张表：

```
0x73b3c  "FPC1020 (A1)"   ... 80 00 00 00 81 00 00 00 00 00 00 00 01 00 00 00
0x73b5c  "FPC1020 (A2)"   ... 80 00 00 00 82 00 00 00 00 00 00 00 01 00 00 00
0x73b7c  "FPC1020 (A3)"   ... 80 00 00 00 83 00 00 00 ...
0x73bbc  "FPC1020 (A4/A5)" ... 80 00 00 00 84 00 00 00 ...
```

即 **A1→0x81、A2→0x82、A3→0x83、A4/A5→0x84** 四个变体，
每条记录 32 字节（名称 20 B + 3 个 u32）。这是 TA 选择配置表的依据，
也是后面反编译时要找的入口。

### 17.3 结论与下一步

* FIFO 的组织方式已经有硬证据（8 字节一组），可以写解交织渲染器验证
* 棋盘图案下整帧单电平 —— 可能因为图案写进的是"列图案寄存器"而我们的窗口
  恰好只覆盖一个图案周期，需要换窗口再试
* 下一步优先级：
  1. 写解交织渲染器（纯离线，5 分钟）
  2. 用 0x54 换更宽的窗口重拍棋盘，确认图案能出格
  3. TA 反编译（数据表入口已定位）

### 17.4 解交织渲染（`tools/deinterleave.py`）

按 `171 行 × 21 组 × 8 ADC` 重排后渲染：

* 图里出现**规则的 8 列周期点阵**（交织结构的直接证据）
* **右下 / 左下各有一块明显更亮的矩形区域** —— 很可能是手指覆盖的区域边界

⇒ 说明：
1. 8 字节交织的判断正确
2. **手指确实被拍到了**，只是对比度极低 + 我们还没找到正确的行列映射
3. 手指只覆盖窗口的一部分，说明窗口位置（`0x54` 的 row_start/col_start）没对准传感器中心

**下一步**：把窗口缩到传感器中心（例如 row_start 40、rows 96、col_start 8 组、10 组），
再拍一次，看看亮块是否居中、是否出现脊线。

### 17.5 中心窗口尝试失败（窗口字段有硬件约束）

想把窗口挪到传感器中心：`0x54 = 0x28605050`（row 40/96, col 64/80）：

```
写入值 0x28605050
回读   0x2870D050   ← 行数 0x60 被改成 0xD0、列起点 0x50 被改成 0x70
图像   全部 0x7F（无效数据）
```

⇒ `0x54` 的字段**不是任意写入就生效**：
* 行数/列数可能必须是 8 的倍数且落在某个区间
* 回读值被芯片改写，说明它做了范围检查或按自己的编码解释

之前能工作的 `0x00B00040`（row0/176/col0/64）是 OTP 默认值，
大概率就是这块模组的出厂窗口。**在没搞清编码规则前不要再改它。**

### 17.6 今晚最终状态

```
模块：v8（棋盘图案 + 可扫增益 + 大端 + 哑字节）
参数：img=0x00B00040(11534400) read_len=11266 big_endian=1 dummy=1 pattern=0 adc_gain=0
状态：0x1f，采集正常
电量：49% 充电中
备份：fpc1020.ko.zst.orig（原厂模块）
```

### 17.7 留给明天的三件事（按性价比排序）

1. **离线**：用 `tools/analyze_fifo.py` + `tools/deinterleave.py` 继续研究
   FIFO 的 8 字节交织结构（不需要平板、不需要手指）
2. **TA 反编译**：数据表入口已定位（`0x73b3c` 的 A1..A4/A5 变体表），
   下一步找引用它的代码
3. **窗口编码规则**：从 TA 里找 `0x54` 的构造代码，搞清字段含义后再试其它窗口
