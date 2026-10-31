# FPC1020 TA（fpctzapp）反编译笔记

> 2026-10-29 00:30，首次成功把 Qualcomm TEE 的 TA 装进 Ghidra 并读懂关键路径

---

## 1. 镜像格式与本仓库的加载方法

### 1.1 段布局（来自 `fpctzapp.mdt` 的 ELF32 program headers）

| 文件 | 虚拟地址 | 大小 | 权限 |
|---|---|---|---|
| `b02` | `0x000000` | `0x8e409` | R+X（代码 + 只读数据 + 字符串）|
| `b03` | `0x08f000` | `0x0a608` | RW |
| `b04` | `0xb9a000` | `0x0015c` | RW |
| `b05` | `0xb9b000` | `0x00088` | RW |
| `b06` | `0xb9b000` | `0x00088` | （与 b05 同址，哈希/签名相关，跳过）|
| `b07` | `0xb9c000` | `0x04648` | R |

`.mdt` 是 ELF32 “hash segment” 头（`e_entry = 0`，`e_machine` 也没有意义）。

### 1.2 关键：TA 是 **32 位 ARM**

```
b02 开头: 02 00 50 e3  →  cmp r0, #2      (ARM A32)
```

用 `arm64` 反汇编会得到乱码、只识别 1 个函数；改成 **`arm`** 后：
`procedure_count = 1474`（单段）/ **1513**（多段 ELF），`language_id = ARM:LE:32:v7`。

### 1.3 构造可加载的 ELF（`tools/ta_elf.py`）

把 mdt 里各段按虚拟地址拼成一个 ELF32/EM_ARM 可执行文件：

```bash
python tools/ta_elf.py          # -> build/fpctzapp.elf （5 个 PT_LOAD 段）
scp build/fpctzapp.elf vm:/tmp/ta.elf
```

Ghidra 直接把数据段也装进来后，`.rodata` 里的字符串指针、路由表、全局配置都能解析。

---

## 2. TA 的 API 名字表（`.rodata`，直接可搜）

```
fpc_ta_router_init            fpc_ta_sensor_exit
fpc_ta_route_command          fpc_ta_sensor_command_handler
fpc_ta_common_init/exit       fpc_ta_sensor_device_init
fpc_ta_common_command_handler fpc_ta_check_finger_lost
fpc_ta_bio_init/exit          fpc_ta_finger_lost_wakeup_setup
fpc_ta_bio_command_handler    fpc_ta_wakeup_setup
fpc_ta_bio_begin_enroll       fpc_ta_qualify_capture
fpc_ta_bio_enroll             fpc_ta_poll_qualify
fpc_ta_bio_end_enroll         fpc_ta_capture_image      ← 采集
fpc_ta_bio_identify           fpc_ta_deep_sleep
fpc_ta_bio_update_template    fpc_ta_get_force_value
fpc_ta_bio_load_empty_db      ...
fpc_ta_bio_delete_template
fpc_ta_bio_get_template_db_id
```

地址：`fpc_ta_capture_image` 名字串在 `0x81075`，`fpc_ta_sensor_command_handler` 在 `0x80f17`。

---

## 3. SPI / 寄存器访问层次（已反编译）

```
fpc_spi_init / destroy / read / write / writeread / select_low_freq
        ↓
qsee_spi_open / close / read / write / full_duplex        (QSEE HAL)
```

### 3.1 `FUN_0002583c` = `cac_if_reg_read/write`（0x2583c）

```c
bVar1 = *buf;                       /* 首字节 = 命令/寄存器地址 */
uVar3 = bVar1 >> 2;                 /* 索引 = cmd >> 2 */
/* 命令长度表：DAT_00025938 + (cmd>>2)*0x10，每条 0x10 字节 */
if (uVar3 == 0x31 || table[uVar3].min_len < 2) { ... }   /* 0x31 = 0xC4 = READ_IMAGE 特例 */
if (expected_len <= 0 || expected_len == len) {
    FUN_00003d54();                            /* 加锁 */
    FUN_00003e40(buf, len, out, outlen);       /* 实际传输 */
}
```

**这条印证了我们手推的规则**：命令字右移 2 位查长度表，0xC4（READ_IMAGE）长度可变所以特判。

### 3.2 `FUN_00003e40` = 传输（0x3e40）

memset → `FUN_0000947c(6, ...)`（QSEE HAL 调用，6 = 操作码）→ 检查/释放锁。

### 3.3 命令发送 `FUN_000262a4(cmd, irq_mask, check)`（0x262a4）

```c
if (cmdtable[cmd>>2].len == 3) {     /* 某些命令需要 3 字节 */
    FUN_00003d54();                  /* 锁 */
    FUN_00003dd4(&cmd, 1);           /* 发 1 字节 */
    if (irq_mask && wait_ok) {
        read reg 0x1c;               /* 读 IRQ */
        if (irq == 0xff) -> reset 错误
        if ((irq & irq_mask) == irq_mask) return 0;
    }
}
```

即：**发命令后轮询 0x1C，等 IRQ 位**。

---

## 4. 采集路径（`fpc_ta_capture_image` → `FUN_00045654`）

### 4.1 完整伪代码要点

```c
int FUN_00045654(out_buf, offset, size, buf_len, ok_flag)
{
    if (buf_len < offset + size) return -7;

    iVar2 = FUN_000262a4(0xc0, 0x20, 1);       /* ★ 发 0xC0，等 IRQ 0x20(FIFO_NEW_DATA) */
    if (iVar2 < 0) ...

    local_20 = { ?, 0xC4 };                    /* ★ 2 字节读图命令 {0xC4, 0} */
    ...
    uVar1 = *(u16 *)(config + 0xc);            /* ★ 配置里 +0xC 是 {行, 列} 两个字节 */
    img = malloc((s16)(uVar1>>8) * (s16)(uVar1 & 0xff) + 2);   /* ★ 行*列 + 2 */
    iVar2 = FUN_00003e40(&local_20, 2, img, size);             /* 发 2 字节命令，读 size 字节 */

    /* 检查 IRQ 错误位 */
    local_20 = { 0x1C };
    FUN_0002583c(&local_20, 1, &local_20, 1);
    if (!(irq & 4)) {                          /* bit2 = ERROR */
        FUN_0006872c(out_buf, img + 2, size);  /* ★ 图像从 img+2 开始拷贝！ */
        return 0;
    }
    /* 否则读 0x38 (READ_ERROR) 并返回错误 */
}
```

### 4.2 三条可直接用的事实

| 事实 | 对驱动的意义 |
|---|---|
| 采集 = 单字节 `0xC0` + 等 IRQ `0x20` | 与我们实现一致 ✅ |
| 读图 = 2 字节 `{0xC4, 0}` 然后读 `行×列+2` 字节 | 与我们一致 ✅ |
| **图像从 `buf+2` 开始** | 驱动需要跳过前 2 字节 → 已加 `img_skip=2` 参数（v10）|
| 采集后读 `0x1C`，bit2 是错误 | 应作为失败判据，而不是只看有没有数据 |

### 4.3 图像尺寸公式

```
size = (u16 at config+0xC 的高字节) × (低字节) + 2
```

对我们现在的窗口：`0xB0 × 0x40 = 176 × 64 = 11264`，`+2 = 11266`，与 `read_len` 完全吻合。

---

## 5. TA 侧的操作码（由 HAL 反推）

HAL `fingerprint.fpc.so`（未 strip，有符号表）里：

```c
/* fpc_tac_transfer: TA 命令字放在共享内存第一个 u32 */
*puVar5 = *(u32 *)(param_2 + 8);
QSEECom_send_modified_cmd(...);

/* sensor_command(hal, sub) */
*puVar3     = 10;          /* ★ TA 操作码 10 = SENSOR_COMMAND */
puVar3[1]   = sub;         /* ★ 子命令 */
fpc_tac_transfer(...);

/* fpc_tee_identify */
*puVar4 = 0x30000000b;     /* ★ 低 32 位 0x0B = TA 操作码 11 = IDENTIFY */
```

子命令已知：`3`（capture_image 路径）、`4`（capture_snapshot）。

**下一步**：在 TA 里找操作码 10 的处理函数（`fpc_ta_sensor_command_handler`），
它内部按子命令 3/4 分派，并负责写 `0x54` 等采集配置。

---

## 6. 工具（VM 上一行命令）

```sh
export GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC

sh /tmp/elf_func.sh  0x45654 90      # 反编译一个函数（TA ELF）
sh /tmp/elf_multi.sh 0x112c 0x1442   # 批量反编译
sh /tmp/elf_xrefs.sh 0x81075         # 查字符串/地址的引用
sh /tmp/rea.sh search fpc_ta         # 搜字符串（单段 b02）
sh /tmp/ta_func.sh  0x2583c          # 单段模式（b02 only）
```

脚本源：`scripts/vm_elf_func.sh`、`vm_elf_multi.sh`、`vm_elf_xrefs.sh`、`vm_rea.sh`、`vm_ta_func.sh`、`vm_ta_xrefs.sh`。

⚠️ 经验：
* `--architecture arm`（不是 arm64）
* 单段 b02 时字符串 xref 常常解析不出来；**用多段 ELF 就全通了**
* PowerShell 里 `$` 会被本地展开，远程脚本一律写成文件再 `sh`

---

## 7. 尚未解决

1. `0x54` 的字段编码（写入会回读异常：`0x28605050` → `0x2870D050`）
2. 图像为何是"行内恒定"的一维数据（col_spread ≈ 1）
3. 子命令 3 的完整处理流程（写哪些寄存器、按什么顺序）

这三条都要继续读 `fpc_ta_sensor_command_handler`。

---

## 8. 寄存器全表（从厂商 `fpc1020_regs.h` 整理，十进制→十六进制）

| 寄存器 | 名称 | 宽度 | 说明 |
|---|---|---|---|
| 0x14 | FPC_STATUS | 1 | RO 状态（idle=0x0E）|
| 0x18 | READ_INTERRUPT | 1 | RO |
| 0x1C | READ_INTERRUPT_WITH_CLEAR | 1 | RO，读完清除（TA 采集后读它判断 bit2 错误）|
| 0x38 | READ_ERROR_WITH_CLEAR | 1 | RO |
| 0x40 | MISO_EDGE_RIS_EN | 1 | WO |
| 0x44 | FPC_CONFIG | 1 | RW |
| 0x4C | IMG_SMPL_SETUP | 3 | RW |
| 0x50 | CLOCK_CONFIG | 1 | RW |
| **0x54** | **IMG_CAPT_SIZE** | **4** | RW，`first_row<<24 | rows<<16 | col_start<<8 | cols` |
| 0x5C | IMAGE_SETUP | 1 | RW |
| 0x60 | ADC_TEST_CTRL | 1 | RW |
| 0x64 | IMG_RD | 1 | RW |
| 0x68 | SAMPLE_PX_DLY | 8 | RW |
| 0x6C | PXL_RST_DLY | 1 | RW |
| 0x78 | TST_COL_PATTERN_EN | 2 | RW（棋盘测试图案）|
| 0x7C | CLK_BIST_RESULT | 4 | RW |
| 0x84 | ADC_WEIGHT_SETUP | 1 | RW |
| 0x88 | ANA_TEST_MUX | 4 | RW |
| 0x8C | FINGER_DRIVE_CONF | 1 | RW |
| 0x90 | FINGER_DRIVE_DLY | 1 | RW |
| 0x94 | OSC_TRIM | 2 | RW |
| 0x98 | ADC_WEIGHT_TABLE | 10 | RW |
| 0x9C | ADC_SETUP | 5 | RW |
| 0xA0 | ADC_SHIFT_GAIN | 2 | RW |
| 0xA4 | BIAS_TRIM | 1 | RW |
| 0xA8 | PXL_CTRL | 2 | RW |
| 0xD0 | FPC_DEBUG | 1 | RO |

### 8.1 `fpc1020_sensor_write(buf, len)` 的语义（TA `FUN_00025f68`）

```c
bVar1 = *buf;                    /* 寄存器地址 */
校验长度表 DAT_0006bd00 + (reg>>2)*0x10
FUN_00003dd4(buf, len);          /* 整段原样 SPI 写出（寄存器 + 值，芯片字节序）*/
```

⇒ 3 字节写 `{0x08, 0x54, 0xFF}` = **写寄存器 0x08，值 0x54FF**（不是写 0x54！）。
这说明 `FUN_00024ef8` 那段代码是**另一种芯片（1021/1150）的探测流程**，不是我们的 1020a。

### 8.2 参考驱动的寄存器访问（已核对，和我们一致）

```c
cmd.len  = 1 + FPC1020_REG_ACCESS_DUMMY_BYTES(reg);   /* reg 原样发出 */
data.len = reg_size;
写：huge_buffer = reverse(dataptr)   /* 小端主机 → 线上大端 */
读：huge_buffer → reverse → dataptr
```

⇒ 我们的 `write_reg/read_reg`（BE 反转 + 0x14/0xD0 哑字节）与厂商完全一致。

---

## 9. 夜间结论

**已知**：采集时序、读图命令、图像偏移（+2）、寄存器表、SPI 层、API 名表。
**未知**：0x54 的字段语义为何被芯片改写、图像为何是行内恒定。

**下一步（明天，需要手指）**：
1. 用 `img_skip=2`（v10 已装）重拍，确认对比度是否变化
2. 若仍是行内恒定 → 说明不是对齐问题，需要从 TA 找 `0x54` 的构造代码
3. TA 里 `fpc1020_sensor_write` 的调用点有 24 个（`0x22d36 0x22d98 0x24f38 …
   0x2854c 0x28574 0x2859e 0x4609a 0x460b8 0x460de 0x460fc`），
   逐个看哪个在写 0x54

---

## 10. 采集配置的完整调用链（2026-10-29 01:00 新进展）

### 10.1 TA 的 sensor HAL API（全部在 `.rodata` 可搜到）

```
fpc_sensor_hal_init / destroy
fpc_sensor_hal_create_default_setup
fpc_sensor_hal_set_config / get_current_config
fpc_sensor_hal_set_recommended_settings / get_recommended_settings
fpc_sensor_hal_set_adc_group_size
fpc_sensor_hal_set_idle_mode
fpc_sensor_hal_finger_present_status
★ fpc_sensor_hal_write_capture_setup      (0x865c3)
★ fpc_sensor_hal_write_wake_up_setup      (0x86604)
fpc_sensor_hal_write_test_setup
fpc_sensor_hal_write_swinging_checkerboard_settings
fpc_sensor_hal_write_direct_drive_settings
fpc_sensor_hal_write_image_constant_settings
fpc_sensor_hal_write_afd_cal_init_settings / _afd_cal_settings
_sensor_hal_write_cb_test_setup_ver1/2/3/4/6
_sensor_hal_write_reset_pixel_test_setup_ver1/ver3
```

### 10.2 调用链（已反编译）

```
fpc_sensor_hal_write_capture_setup()          FUN_00027158
   └─ log "%s" …
   └─ FUN_00027fd4(3)                          fpc_sensor_setup_usecase(usecase=3)
        ├─ FUN_00027590()                      取 sensor handle
        ├─ FUN_00023d12(sensor, uc, 3,    &p,&n)   查 ADC_SHIFT_GAIN   → 存到 DAT_00b9a0a4[0..1]
        ├─ FUN_00023d12(sensor, uc, 0x1b, &p,&n)   查 PXL_CTRL        → 拼成 u32 存 DAT_00b9a0a4+4
        ├─ FUN_00027edc(sensor, uc)            write_register_group()
        │     ├─ FUN_00023c6a(sensor, uc, &count)   这一组有几个寄存器
        │     ├─ FUN_00023e34(sensor, uc, ptr[], len[], 0)  取出每个寄存器的字节串
        │     └─ for each: FUN_00026090(ptr, len)
        │            └─ memcpy 到栈 → FUN_00025f68(buf,len) = fpc1020_sensor_write()
        ├─ if (usecase == 3)                    ← 只有采集用例才做
        │     └─ 从 config+0x1F 开始的变长寄存器列表，逐个 FUN_00026090 写出
        └─ 读 0x5C (IMAGE_SETUP)，置 bit3 (|0x08)，写回
```

### 10.3 三条可直接用的结论

1. **`IMAGE_SETUP(0x5C)` 最后一定要 `|= 0x08`** —— 我们的驱动写的是 `0x0B`（0x03|0x08），
   与 TA 的行为一致 ✅
2. **采集前先写 ADC_SHIFT_GAIN(0xA0) 和 PXL_CTRL(0xA8)** —— 我们从 v8 起"故意不写"，
   **而 TA 每次都写**。这很可能就是图像只有一维的原因（模拟前端没配置）
3. **只有 usecase==3（采集）会额外写一组寄存器**（来自 config+0x1F 的变长列表），
   这组内容是 ours 完全没有的

### 10.4 TA 自带配置里就有 `0x00B00040`

在 `b02` 里搜到多处 `00 B0 00 40`，例如 `0x6aec5` 附近是一串
"寄存器+值" 字节流：

```
... 54 00 B0 00 40 88 00 00 00 00 4C 04 FF FF 11 5C 0B A8 00 0F ...
        ^^^^^^^^^^^ ^^ ^^^^^^^^^^^ ^^ ^^^^^^^^ ^^ ^^^^^ ^^ ^^^^^
        0x54 = 0x00B00040      0x88 = 0     0x4C = 0x04FFFF11
                                0x5C = 0x0B  0xA8 = 0x000F
```

⇒ **我们的窗口值 0x00B00040 和厂商 TA 用的完全一样**，窗口不是问题。

而同一串里 `0x4C IMG_SMPL_SETUP = 0x04FFFF11`、`0xA8 PXL_CTRL = 0x000F`
是我们**从未写过**的寄存器。

### 10.5 下一步（明天，带手指）

把这一串里的寄存器**全部**照抄进驱动（尤其是 `0x4C` 和 `0xA8`），
再看图像是否出现列方向结构。这些值直接从 TA 里挖，不需要猜。

待抄的候选串（b02）：
```
0x6aec5  0x54=[00 B0 00 40] 0x88=[00 00 00 00] 0x4C=[04 FF FF 11] 0x5C=[0B] 0xA8=[00 0F] 0x32?...
0x6af08  同上但 0x4C=[00 FF FF 11]
```

（`0x32` 不是合法寄存器，说明这串可能还有长度前缀或压缩，需要再核对；
但 `0x54/0x88/0x4C/0x5C/0xA8` 这一段是清晰的。）

---

## 11. 配置块的结构（已解出）与为什么挖不到静态表

### 11.1 `FUN_00023d84` 反编译得到的完整布局

```
blob[0..1]  A = (blob[0]<<8) | blob[1]
blob[2]     c = 寄存器条目总数
blob[3]     N = 用例(usecase)个数

值区        从偏移 4 开始，连续存放（长度由 sizes 表给出）
sizes[c]   @ A + 4
regs[c]    @ A + 4 + c
counts[N]  @ A + 4 + 2c          每个用例有几个寄存器
usecases[N]@ A + 4 + 2c + N      用例号（1..11）
```

查找逻辑：遍历用例 → 每个用例遍历它的寄存器 → 命中 (usecase, reg) 就返回
`(blob + 偏移, 长度)`，偏移从 4 开始累加 sizes。

### 11.2 但是：**静态镜像里没有这个 blob**

`DAT_00b9a098`（传感器结构体指针）指向 `0x90b78`，那里是 **0**；
`DAT_00b9a0a4`（ADC/PXL 缓存）也在运行时才填。

⇒ **配置是 `fpc_sensor_hal_create_default_setup()` 在运行时按芯片类型/OTP 构建的**，
不是静态数据。所以"直接从镜像里 dump 寄存器表"这条路走不通。

### 11.3 已经排除的替代路径

| 想法 | 结果 |
|---|---|
| 搜 `0x00B00040` 附近当寄存器脚本 | 手读像，但按寄存器宽度贪心解码 0 条合法序列 → 不是脚本 |
| 找指针数组（指向 b02 的字节串）| b03/b04/b07 里只有误报（ASCII "TS_TO…"）|
| 找解压器 | TA 里没有 compress/lz/unpack 相关代码（只有 DB 打包）|
| HAL .so 里有同一套表 | `fingerprint.fpc.so` 只有 TEE 客户端，无寄存器表 |

### 11.4 结论

要拿到 TA 的完整采集寄存器表，只剩两条路：

1. **动态**：在 TEE 侧 hook（需要 QSEE 调试环境，基本不可行）
2. **等价替代**：用厂商参考驱动 `fpc1020_common.c` 的 `write_sensor_1020a_a3a4_setup()` —— 
   这本来就是同一份配置的 C 版本，而且我们已经照着实现了

⇒ **所以"采集序列"这条线其实已经到底了**：我们能拿到的就是参考驱动里那套，
再往下必须动 TEE 运行时。

### 11.5 那当前驱动还差什么？

对比参考驱动的 `write_sensor_1020a_a3a4_setup()`，我们**已经写了**：
`0x90`、`0x68`、`0x8C`、`0x5C`、`0x54`、每帧 `0xA8`/`0xA0`。

参考驱动里我们**没写**的只有：
- `0x9C ADC_SETUP`（5 字节）—— 只在 rev<3 时写
- `0x88 ANA_TEST_MUX`（4 字节）—— 只在 rev<3 时写

⇒ 按参考驱动，rev≥3 的芯片不需要它们。

**所以从"寄存器配置"角度，我们的驱动已经和厂商一致了。**
图像一维的问题要么在模拟前端硬件（指纹模块本身的 sensor），要么在我们的读出/FIFO 理解。

---

## 12. 🎯 2026-10-29 04:30：在 TA 镜像里**找到了 0x54 的值**

第 11 节我说"配置是运行时构建的，静态挖不到" —— **这个说法不对**。
用机器码/数据搜索重新查了一遍，结果如下。

### 12.1 先证明 TA 里没有 `mov rN, #0x54`

寄存器写是通过"缓冲区首字节=寄存器号"完成的（`fpc1020_sensor_write(buf,len)`），
所以写 0x54 会体现为一条 `mov rN,#0x54`。搜遍整个 b02 段：

```
0 sites load 0x54 into a register
```

⇒ 0x54 **不是代码算出来的**，是数据里回放的。

### 12.2 但 `0x00B00040` 在镜像里有 **10 处**

```
BE at 0x06bec5 / 0x06bf08 / 0x06bf61 / 0x06bfa7 / 0x06bfcb / 0x06c0d6 / ...
LE at 0x06ad14 / 0x06d458 / 0x06d4d0 / ...
```

（文件偏移；b02 段 vaddr = 文件偏移 - 0x1000）

而 `0x00B00040` **正是我们驱动里用的 `img_capt_size`**，
也正是厂商参考驱动 `write_sensor_1020a_a3a4_setup()` 用的值。

⇒ **0x54 的裁剪编码问题解决了：它就是 0x00B00040，不是要推导的编码。**

### 12.3 附近的字节长这样

```
0x06beb8  08 20 1f 08 54 00 08 5c 00 9c 00 49 40 02 2d 00
0x06bec4  54 00 b0 00 40 88 00 00 00 00 4c 04 ff ff 11 5c
0x06bed4  0b a8 80 8f 02 68 01 44 29 24 09 39 34 19 14 90
```

按 `<reg:1><BE 值:size>` 手工对齐可以读出：

| 位置 | 寄存器 | 值 |
|---|---|---|
| 0x06bec4 | **0x54** | **0x00B00040** |
| 0x06bec9 | 0x88 | 0x00000000 |
| 0x06bece | 0x4C | 0x04FFFF |
| 0x06bed4 | **0x5C** | **0x0B** |
| 0x06bed6 | 0xA8 | 0x808F |
| 0x06bed9 | 0x68 | 0x0144292409393419（8 字节）|

**0x5C = 0x0B 和我们驱动写的一模一样**，0x54 也一样。
⇒ 我们的寄存器值不是错的。

### 12.4 还没解决的部分

条目封装格式**没有完全定死**（中间有我们不认识的寄存器号，如 0x02/0x2D/0x11），
按简单 `<reg><BE值>` 走不到底。可能是：

- 条目之间还有长度/校验字节
- 或者是一段"脚本"，由 TA 里的解码器运行时展开

（早期会话建过 `tools/ta_decode_script.py`，说明当时也认为是编码脚本。）

**但关键结论不受影响**：0x54 的值、0x5C 的值都和我们对上了。

### 12.5 这对指纹问题的意义

既然寄存器值和厂商一致、协议也对、供电时钟都正常，而帧里就是没有图像 ——
**进一步印证问题在 TA 的成像/后处理，不在我们写的寄存器。**

工具：`tools/ta_find_054.py`、`tools/ta_find_window.py`、`tools/ta_align_script.py`、
`tools/ta_find_table_ptr.py`、`tools/ta_parse_regtable.py`

---

## 13. 2026-10-29 05:00：在 .rodata 里找到三张表

继续解 §12 遗留的"条目封装格式"，结果找到了**结构化数据**（不是脚本流）。

### 13.1 (指针,长度) 表：10 条

vaddr `0x97c00` 起（文件 0x98c00）：

```
0x098c00  2d 24 00 00 | 54 7c 09 00 | 03 00 00 00 | 57 7c 09 00
0x098c10  03 00 00 00 | 5a 7c 09 00 | 04 00 00 00 | 5e 7c 09 00
0x098c20  07 00 00 00 | 65 7c 09 00 | 05 00 00 00 | 6a 7c 09 00
0x098c30  03 00 00 00 | 6d 7c 09 00 | 0b 00 00 00 | 78 7c 09 00
0x098c40  02 00 00 00 | 7a 7c 09 00 | 0a 00 00 00 | 84 7c 09 00
0x098c50  0a 00 00 00 | <数据从这里开始>
```

10 组 `(长度, 指针)`：`3, 3, 4, 7, 5, 3, 11, 2, 10, 10`，
指针都指向 `0x97c54 … 0x97c84`（即文件 0x98c54 之后的连续区域）。

**10 组** 和当初从 `FUN_00023d84` 解出的 "N = usecase 数" 对上了。

### 13.2 id / 大小 表

vaddr `0x988c0` 附近（文件 0x999b0）：

```
0x0999b0  02 01 01 01 01 01 01 02 04 08 0f 1b 30 4d 73 9c
          ^^^^^^^^^^^^^^^^^^^^^ 大小          ^^^^^^^^^^^^^^^^^^ id
```

**id 里出现 `0x1b`** —— 正是第 3 轮反编译看到的 `FUN_00027fd4(3)`
查的 `PXL_CTRL` 的 id！

另一组（文件 0x99980）：
```
sizes: 2 1 1 1 1 1 1 2
regs : 04 08 0f 1b 30 4d 73 9c
```

⇒ **TA 内部用的是 id（0x04/0x08/0x0f/0x1b/0x30/0x4d/0x73/0x9c），不是寄存器地址。**
寄存器地址是 id 映射表另一侧的东西。

### 13.3 寄存器脚本（含 dry/wet 差异）

0x98c54 起有一段，**两个变体只差几个字节**：

```
变体 A: 8c 00 14 78 aa 55 a8 93 0f 41 9c 00 55 40 00 2d 00 4c 04 ff ff 11 ...
变体 B: 8c 00 14 78 55 aa a8 93 0f 41 9c 00 55 40 00 2d 00 4c 00 ff ff 11 ...
                        ^^^^^                                              ^
```

`aa 55` ↔ `55 aa`、`4c 04` ↔ `4c 00` —— 这正是 **dry/wet 两帧的不同设置**。

后面还有：
```
... 6c 04 80 82 15 15 15 15 09 09 09 09 68 01 08 08 08 08 14 14 14 14
```
`15 15 15 15`、`09 09 09 09`、`08 08 08 08`、`14 14 14 14` 这种"四个相同字节"
很像**每通道的重复值**（SAMPLE_PX_DLY 是 8 字节，正好 2 组 4 字节）。

### 13.4 仍然没定论的

条目到底是 `<id><值>` 还是 `<id><长度><值>`，还是 `id` 表 + 独立的"值"表，
需要**读这段数据的解码器**才能确定。线索：

- 10 条 (ptr,len) 表在 vaddr 0x97c00
- 代码里没有指向 0x97c00 的字面量（搜过），说明是**基址 + 偏移**访问
- 下一步该反编译 vaddr 0x978xx–0x97axx 附近的函数（引用这张表的地方）

### 13.5 为什么这仍然有价值

即使条目格式没解完，已经能确认：

1. TA 用的是 **id 编号**体系（0x1b = PXL_CTRL），我们按寄存器地址操作是"另一层"
2. 配置里有 **10 个 usecase**，每个带一段小脚本
3. 脚本里明确有 **dry/wet 两变体**（`aa 55` vs `55 aa`）
4. `0x54 = 0x00B00040`、`0x5C = 0x0B` 与我们的驱动一致

⇒ 进一步确认"我们的寄存器层是对的，差别在 TA 内部的处理"。

工具：`tools/ta_find_header.py`、`ta_find_sorted.py`、`ta_dump_ids.py`

---

## 14. 2026-10-29 05:40：找到嵌套描述符，并验证了地址映射

### 14.1 先纠一个可能的坑：地址映射是对的

担心过"文件偏移 - 0x1000 = vaddr"只对第一段成立。用 ELF 程序头核对：

```
seg0: file 0x0001000..0x008f409  vaddr 0x000000..0x08e409
seg1: file 0x0090000..0x009a608  vaddr 0x08f000..0x099608
seg2: file 0x009b000..0x009b15c  vaddr 0xb9a000..0xb9a15c
seg3: file 0x009c000..0x009c088  vaddr 0xb9b000..0xb9b088
seg4: file 0x009d000..0x00a1648  vaddr 0xb9c000..0xba0648
```

前两段的文件偏移与 vaddr 差值**都是 0x1000**（ta_elf.py 按页对齐的结果），
所以 §12/§13 引用的所有 vaddr **都是对的**。

（注意：seg2 之后有页面空洞，`file - 0x1000` 不再成立；
工具 `tools/ta_map_segments.py` 会按程序头正确换算。）

### 14.2 vaddr 0x91300：一串 (长度, 指针) 描述符

```
0x091300  08 00 00 00 | 04 7c 09 00        (len=8,  ptr=0x097c04)
0x091308  0a 00 00 00 | 90 7c 09 00        (len=10, ptr=0x097c90)
0x091310  0a 00 00 00 | 1c 7d 09 00        (len=10, ptr=0x097d1c)
0x091318  0a 00 00 00 | a8 7d 09 00        (len=10, ptr=0x097da8)
0x091320  0a 00 00 00 | 01 00 00 00        (len=10, ...)
0x091328  00 00 00 00 | 74 0d 09 00        (      , ptr=0x090d74)
```

而 §13 找到的 10 组 (ptr,len) 表就在 **0x97c00**，
它又指向 0x97c54 起的数据 —— **三层嵌套**：

```
0x91300  描述符 [len, ptr]  ──┐
                              ↓
0x97c00  (ptr,len) 表 ×10  ──┐
                              ↓
0x97c54  真正的寄存器脚本数据
```

### 14.3 谁在用 0x91300？

搜指向它的字面量：

```
vaddr 0x0926ec / 0x0926f0 → 0x091304 / 0x09130c
vaddr 0x09272c / 0x092730 → 0x091304 / 0x09130c
vaddr 0x09276c / 0x092770 → 0x091314 / 0x09131c
```

这些字面量**都在 b03 数据段**（0x8f000–0x99608），不是代码。
⇒ 说明这张描述符表由**另一个结构**引用，最终消费者还是没定位到。

### 14.4 目前能确定的结构图

```
b02 (代码, vaddr 0..0x8e409)
  ├─ FUN 表 / 字符串 / 字面量池
b03 (数据, vaddr 0x8f000..0x99608)
  ├─ 0x91300  描述符数组 (len, ptr) …
  ├─ 0x97c00  (ptr,len) 表 ×10  → 0x97c54 起的数据
  │             └─ 含 0x54=0x00B00040、0x5C=0x0B、aa55/55aa 两变体
  └─ 0x989b0  id/大小 表（含 id 0x1b = PXL_CTRL）
b04/b05/b07 (证书/签名/杂项)
```

### 14.5 如何看待这个结果

- **0x54 的值、0x5C 的值**已经确认与我们一致（§12）
- **TA 用 id 编号体系**（0x1b = PXL_CTRL），不是直接寄存器地址
- **有 dry/wet 两套脚本变体**（`aa 55` / `55 aa`）
- **完整条目格式**还需定位最终消费者（第三层之后的代码）

这条线可以继续挖，但**对"能不能出指纹图"的判断没有影响** ——
寄存器层已经确认一致，图像仍然产不出来。

### 14.6 接手入口

这条线如果下次要继续，**先看 [30-TA-TABLE-HANDOFF.md](30-TA-TABLE-HANDOFF.md)** ——
里面写了已确定的事实、三层结构的确切地址、试过的格式假设、以及
"顺着 `FUN_00027fd4` 反编译"这条最可能走通的路。

---

## 15. 2026-10-29 06:15：反编译出配置的**调用链本体**

按 §14.6 的思路反编译了三个关键函数，机制现在清楚了。

### 15.1 `FUN_00027fd4` = **`fpc_sensor_setup_usecase(usecase)`**

伪代码（节选，保留原始符号名）：

```c
int fpc_sensor_setup_usecase(uint usecase)
{
    handle = fpc_sensor_hal_get_recommended_settings();   // FUN_00027590
    if (handle == NULL || usecase >= 0xc) return -8;      // usecase 上限 12

    /* id 3 = ADC_SHIFT_GAIN */
    if (lookup(handle, usecase, 3, &ptr, &len) >= 0) {
        DAT_00b9a0a4[1] = ptr[1];      // shift
        DAT_00b9a0a4[0] = ptr[2];      // gain
    } else log("ADC_SHIFT_GAIN not used by this sensor");

    /* id 0x1b = PXL_CTRL */
    if (lookup(handle, usecase, 0x1b, &ptr, &len) >= 0) {
        /* 从 ptr+len-1 往回逐字节，左移 8 位拼进 DAT_00b9a0a4+4 */
    } else log("PXL_CTRL not used by this sensor");

    write_register_group(handle, usecase);                 // FUN_00027edc

    /* 只有 usecase == 3 才额外写一段变长寄存器列表：config+0x1f */
    if (usecase == 3) {
        n = *(config + 0x1f);
        while (n) { write_reg(ptr, n); ptr += 1 + n; n = *ptr; }
    }

    /* 最后：0x5C |= 8 */
    read_reg(0x5c, buf, 1);  buf[0] |= 8;  write_reg(0x5c, buf, 1);
}
```

**新信息**：

- **usecase 上限是 12**（`usecase >= 0xc` 直接拒）
- **只有 usecase 3 会多写一段变长寄存器列表**（在 config 偏移 0x1f）
- `0x5C |= 8` 是**这个函数统一做的**，不是采集流程特有

### 15.2 `FUN_00023d12` = 按 (usecase, id) 查值

```c
int lookup(handle, usecase, id, &ptr, &len)
{
    if (usecase > 0xb && usecase != 0x26) return -8;   // 上限 11，例外 0x26
    if (id > 0x25 && id != 0x26) return -8;            // id 上限 0x25
    iVar1 = handle[1] ? FUN_00023d84(handle[1], usecase, id, &len, &off)
                      : FUN_00023d84(handle[0], usecase, id, &len, &off);
    *ptr = base + off;
}
```

**新信息**：

- **id 范围 0..0x25（37 个）** —— 不是寄存器地址，是配置项编号
- **usecase 范围 0..0xb（12 个）**
- 有两个配置源（`handle[0]` 优先、`handle[1]` 覆盖）

### 15.3 `FUN_00027590` = `fpc_sensor_hal_get_recommended_settings()`

```c
undefined4 *get_settings(void)
{
    if (DAT_00090b80 == 0) log("requesting recommended settings when not set");
    if (DAT_00090b88 != 0) log("%s: %s");
    return &DAT_00090b80;          /* 返回静态变量的地址 */
}
```

而镜像里 `DAT_00090b80` 和 `DAT_00090b88` **都是 0**：

```
vaddr 0x090b80: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

⇒ **配置确实在运行时才建立**，镜像里的句柄是空的。
而且代码里**没有字面量指向 0x90b80**（只有两处指向 0x90b8c/0x90b8e，且在数据段），
说明写入它的代码用的是别的基址计算方式，静态定位不到。

### 15.4 结论：静态分析到此为止

| 现在知道的 | 还是不知道的 |
|---|---|
| 配置项是 **id 0..0x25** | 每个 id 对应的**具体数值表**在哪 |
| usecase 是 **0..0xb（12 个）** | 12 个 usecase 各自的寄存器脚本 |
| usecase 3 = 采集 | 谁在运行时填充 `DAT_00090b80` |
| ADC_SHIFT_GAIN 从 ptr[1]/ptr[2] 取 | 条目字节格式（同 §13）|
| PXL_CTRL 从 ptr 尾部往回拼 | |
| `0x5C |= 8` 由 setup 统一做 | |

**要再往下走必须动态调试**（在 TEE 里打断点看 handle 被填成什么），
而那是安全世界，主线内核做不到。

⇒ **这条线到此为止是合理的。** 已有结论（0x54/0x5C 值与我们一致、
寄存器层没问题）不受影响。
