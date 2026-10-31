# 指纹（FPC1020）攻坚手册 · 下次开工直接照做

> 最后更新：2026-10-28 23:55
> 设备：Mi Pad 4 Plus (clover-plus)，pmOS "Nura edge"，内核 `7.0.14-sdm660`
> 当前状态：**驱动链路已全部打通，只剩"图像内容不对"这一个问题**

---

## 1. 一句话现状

芯片完好、SPI 协议已修对、读出通路已证明可用、ADC 增益可控；
**图像是一维条纹而不是指纹脊线**，原因收敛到两点：FIFO 的 8 字节交织布局、`0x54` 窗口编码规则。

---

## 2. 已证明的事实（不要再重复验证）

| 结论 | 证据 |
|---|---|
| 供电/GPIO 正常 | gpio92/98/108 输出高，SPI 引脚 func1，两边系统稳压器一致 |
| 芯片一直是 idle | 修好状态读后 `0x14 = 0x0e` |
| 上电/复位时序不是问题 | v2 驱动照抄厂商时序，无变化 |
| 读出通路正常 | 棋盘图案 → FIFO 内容立刻变（255 vs 150）|
| ADC 增益生效 | 增益 0x1100→0x0010，输出电平 255→151 单调 |
| FIFO 是 8 字节交织 | period=8 有 82.5% 字节相同 |
| `0x54` 有硬件约束 | 写 0x28605050 回读 0x2870D050，图像全 0x7F |

---

## 3. 两个已修的协议 bug（关键知识）

### 3.1 状态寄存器要发 2 字节

```c
#define FPC1020_REG_ACCESS_DUMMY_BYTES(reg) \
    ((reg) == FPC102X_REG_FPC_STATUS /*0x14*/) ? 1 : \
    ((reg) == FPC102X_REG_FPC_DEBUG  /*0xD0*/) ? 1 : 0
```
命令阶段长度 = `1 + DUMMY_BYTES(reg)`。少了这个字节，状态永远读成 0x00。

### 3.2 多字节寄存器是**大端**

厂商 `fpc1020_reg_access()` 在 ARM 上读/写都会反转字节。
**由此 `img_capt_size` 等参数必须写"寄存器应持有的值"**：

```
0x00B00040 = 11534400   ← 正确（row 0/176, col 0/64）
```

---

## 4. 驱动源码在哪、怎么编译部署

### 4.1 源码谱系

| 文件 | 内容 |
|---|---|
| `tools/fpc1020.c` | 原始带外驱动（pmOS 里的那个）|
| `tools/fpc1020_params.c` | +finger_drive 参数、skip_config、status 打印 |
| `tools/fpc1020_v2.c` | +上电时序、reset_hold、wake_cmd、idle_before_capture |
| `tools/fpc1020_v3.c` | +状态寄存器哑字节 |
| `tools/fpc1020_v4.c` | +wake/diag 走 read_reg |
| `tools/fpc1020_v5.c` | +大端读写 |
| `tools/fpc1020_v6/v7.c` | +棋盘测试图案（v7 修到 capture_now）|
| **`tools/fpc1020_v8.c`** | **当前设备上跑的版本**（棋盘可用 adc_gain 覆盖）|

### 4.2 编译（VM 192.168.1.200，user/<VM_PASSWORD>）

```bash
# 内核源码：~/.local/var/pmbootstrap/cache_distfiles/linux-v7.0.14-sdm660.tar.gz
# 已解压在 /home/user/kbuild/linux-7.0.14-sdm660
# 工具链：clang-18 + lld-18 + dwarves(pahole)
scp tools/fpc1020_v8.c user@192.168.1.200:/tmp/
ssh user@192.168.1.200 'bash /tmp/vm_build_v2.sh /tmp/fpc1020_v8.c'
# 产物 /tmp/fpc1020-v2.ko.zst
```

⚠️ 三个必须满足的条件，缺一个模块就加载不了：
1. `CC=clang-18`（内核带 `CONFIG_CFI=y`，GCC 编的 struct module 尺寸不对）
2. `.config` 每次从设备 `/proc/config.gz` 重新覆盖（`olddefconfig` 不会重新打开被关掉的符号）
3. `CONFIG_DEBUG_INFO_BTF=y` 需要 `pahole`（否则 struct module 少 24 字节 → 正好差 64）
4. 编译期间 `mv .git .git.hold`（否则 vermagic 多一个 `+`）

### 4.3 部署

```bash
# PC -> 平板
scp fpc1020-v8.ko.zst user@192.168.1.29:/tmp/fpc1020.ko.zst
ssh user@192.168.1.29 'echo <SUDO_PASSWORD> | sudo -S sh /tmp/dsh_pad_install_ko.sh'
# 重启（不要 rmmod）
```

### 4.4 测试脚本（`tools/pad_run.py` 直接跑）

```powershell
python tools/pad_run.py scripts/fpc_restore.sh --sudo     # 恢复默认参数
python tools/pad_run.py scripts/fpc_checker.sh --sudo     # 棋盘图案
python tools/pad_run.py scripts/fpc_gain.sh --sudo        # 增益扫描
python tools/pad_run.py scripts/fpc_frames.sh --sudo      # 抓 3 帧
```

⚠️ 脚本必须是 **LF 换行**，PowerShell `Set-Content` 会写成 CRLF 导致
`sh: syntax error: unexpected end of file (expecting "do")`。

---

## 5. 参数速查（`/sys/module/fpc1020/parameters/`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `img_capt_size` | 11534400 | `0x00B00040`，**写值不写字节** |
| `read_len` | 11266 | 11264 + 2 |
| `reset_before_capture` | 1 | 每帧前硬复位（连续采集必须）|
| `wake_before_capture` | 0 | 软复位+等 idle（现在能成功了）|
| `skip_config` | 0 | 1 = 不写配置，手动寄存器生效 |
| `reg_dummy_bytes` | 1 | 状态寄存器哑字节 |
| `big_endian_bytes` | 1 | 多字节大端 |
| `test_pattern` | 0 | 0xAA55 / 0x55AA 开棋盘 |
| `adc_gain` | 0 | 非 0 时覆盖棋盘配置的 0xa0 |
| `finger_drive_conf/dly` | 2 / 9 | 0x8C / 0x90 |

---

## 6. 下次开工的三条路（按性价比）

### 路线 A：离线搞清 FIFO 布局（不需要平板、不需要手指）

```bash
python tools/analyze_fifo.py build/frames/f0.bin
python tools/deinterleave.py build/frames/f0.bin build/frames/png6
```

已有发现：period=8 重复 82.5%，解交织后出现 8 列周期点阵 +
右下/左下各一块更亮的矩形（疑似手指覆盖区）。

要做：把"8 字节组 → 列"的映射穷举一遍（`adc*21+group`、`group*8+adc`、
行优先/列优先…），看哪种能出连续纹理。**纯离线，成本最低。**

### 路线 B：TA 反编译（answer 一切）

已定位：`fpctzapp.b02` 偏移 `0x73b3c` 是变体表
（`FPC1020 (A1)`→0x81、`(A2)`→0x82、`(A3)`→0x83、`(A4/A5)`→0x84，每条 32 字节）。

问题：objdump 直接反汇编是乱码（代码/数据混排、没有正确入口），
需要 Qualcomm TEE 的加载器（Ghidra 插件 / IDA loader），或者手工找出代码段起点。

### 路线 C：`0x54` 窗口编码规则

现象：写 `0x28605050` 回读 `0x2870D050`（行数 0x60→0xD0、列起点 0x50→0x70）。
说明芯片对字段做了范围检查/重编码。需要从 TA 里找 `0x54` 的构造代码。

---

## 7. 设备恢复原厂指纹驱动

```bash
ssh user@192.168.1.29
echo <SUDO_PASSWORD> | sudo -S sh -c 'M=/lib/modules/7.0.14-sdm660/kernel/drivers/input/misc/fpc1020.ko.zst; cp $M.orig $M; sync; reboot'
```

---

## 8. 血泪教训（补充）

* 电量低于 25% 不要做需要反复重启的实验
* 改 `0x54` 后如果 `capture_now` 报 `no image (intr=0x00)`，先查参数值是不是写成了字节序而不是值
* 脚本一律 LF；`dmesg` 要 sudo；`pad_run.py` 会自动处理
* 每次改 `img_capt_size` 后回读 `r 54 4` 确认芯片接受

---

## 9. 布局穷举的结果（2026-10-28 23:58，先看这个）

用 `tools/search_layout.py` 对所有 8 字节交织排列做全变差(TV)搜索：

```
f0.bin (28728 B, 有手指)
  TV=1.315  row-major shift=7 order=ag     ← 最好
  TV=1.315  row-major shift=0 order=ag
  ...
  TV=1.486  row-major shift=0 order=ga     ← 最差
```

**最好和最差只差 13%** —— 说明**没有任何一种排列能让图像变平滑**。
如果数据里真有脊线，正确排列的 TV 会比错误排列低很多（几倍）。

⇒ **结论：图像里根本没有脊线信息，只有 ADC 噪声底。**
不是"我们排错了"，是"数据本身没有内容"。

### 因此下一步的重心必须换

不再是"布局/解码"问题，而是**模拟前端为什么没有信号**：

1. `0x68 SAMPLE_PX_DLY` / `0x6c PXL_RST_DLY`（采样时序）—— 驱动里只有 `pxl_rst_dly` 可调
2. `0x8c/0x90 FINGER_DRIVE`（手指激励）—— 已可调，扫过 6 组无差别
3. **芯片 revision 对应的配置表**：TA 里有 A1/A2/A3/A4-A5 四套，
   我们一直用 a3a4 表。**我们的 HWID 0x0341 到底对应哪一套，还没确认。**
   → 这是最可能的方向：换 A1/A2 的时序值试

### 建议的下一步实验（明天的第一件事）

把参考驱动里 `write_sensor_1020a_a1/a2` 的 `SAMPLE_PX_DLY`、`PXL_RST_DLY`、
`FINGER_DRIVE_*`、`ADC_SHIFT_GAIN`、`PXL_CTRL` 全部读出来，
做成 4 套预设参数（`preset=a1|a2|a3a4`），逐套拍图对比对比度。

对比度判据：同一姿态下 `max-min` 和 TV 值。有手指时应显著高于无手指。

---

## 10. 2026-10-29 00:20 追加：revision 假设不成立，但拿到新的形状信息

### 10.1 试了 rev3 时序，没帮助

厂商 1020A 有两套时序：

| rev | SAMPLE_PX_DLY (0x68) | PXL_RST_DLY | FINGER_DRIVE_DLY |
|---|---|---|---|
| 3 | `0x1717171723232323` | 0x0f | 0x18 |
| 4 | `0x0808080814141414` | (0x0a) | 0x09 |

v9 驱动加了 `chip_rev` 参数（0=rev4、3=rev3），实测对比（同一手指）：

```
rev4: min 137 max 165  distinct 20-22
rev3: min 139 max 161  distinct 16-18
```

**没有差别。** revision/时序不是根因。

### 10.2 行列投影揭示了一个新事实

对 168×171 的帧做投影：

```
row means: :-:::-=-::--:-:-:::- =---:----- --=-----%%%      ← 末尾几行更亮
col means: +%+#:**%.+ - - - - - - - - - - - - - - - -      ← 只有前 ~10 列有结构
```

**只有最左边约 10 列、以及最后几行有内容，其余整片是平的。**

这非常关键：说明 **FIFO 里有效数据只占很小一部分，其余是填充/重复**。
和"period=8 重复 82.5%"完全吻合 —— 很可能是**读指针不前进**，
同一个 8 字节采样被反复读出，只有开头一小段是真实扫描数据。

### 10.3 因此下一个要查的（很具体）

1. **`0xC4 READ_IMAGE` 的读法**：厂商 `fpc1020_fetch_image()` 是不是先发命令字节、
   再 **单独一个 spi_transfer** 读数据（而不是我们这样把命令和数据塞进同一个 message）？
   如果芯片要求"命令结束后 CS 拉高再单独开始读"，我们的连续读会让它重复输出同一拍。
2. 对比 `fpc1020_reg_access()` 的 `cs_change` 用法（cmd transfer cs_change=0、
   data transfer cs_change=1）—— **这正是我们没照做的细节**。
3. 若确认：把 `fpc_read_chunked()` 改成"命令一个 message（CS 结束）、
   数据另一个 message（重新拉低 CS）"，很可能图像立刻正常。

> 这条优先级最高，因为它是目前唯一能解释"只有开头有数据 + 8 字节重复"的机制。

### 10.4 关键量化：数据其实是"一维"的

对同一帧在多种布局下算投影离散度：

```
168x171: row_spread=12.36  col_spread=0.94
171x168: row_spread=13.01  col_spread=0.43
64x176 : row_spread=4.33   col_spread=0.81
176x64 : row_spread=2.62   col_spread=1.06
```

**行内离散度 <1，行间 12–13。** 也就是说：

> 每个"行"块里所有像素几乎一样，只有块与块之间才变化。

⇒ **FIFO 输出的不是二维像素阵列，而是一维序列**（一个采样值按行宽重复），
这解释了为什么怎么排都出不了指纹。

### 10.5 下一个实验（已准备好脚本 `scripts/fpc_pxlctrl.sh`）

`apply_config()` 里明确写着"**0xA0 / 0xA8 故意不设**"，而 `0xA8 = PXL_CTRL`
很可能就是**列读出/像素阵列使能**。手动写上：

```sh
echo "w a8 1b 0f" > /sys/bus/spi/devices/spi0.0/cmd   # 值 0x0f1b（BE 反转后写）
echo "w a0 01 0d" > /sys/.../cmd                       # ADC shift 13 gain 1
```

刚才试了一次，但**当时没有手指**，两帧都平（row/col spread ≈1），结论无效。
**下次必须带手指复测**，判据：`col_spread` 是否从 ~1 跳到 5 以上。

### 10.6 如果 0xA8 不是答案

那就只剩 TA 反编译了。届时需要：
* Qualcomm TEE 镜像加载器（Ghidra 插件 / IDA loader），或者
* 手工定位代码段起点（objdump 从 0 反汇编是乱码，说明前段是数据/表）

### 10.7 今晚（10-29 00:32）最终状态

```
模块 v9（chip_rev 可切 rev3/rev4，实测无差别）
参数：img=0x00B00040 read_len=11266 be=1 dummy=1 pattern=0 adc_gain=0 chip_rev=0
状态 0x1f，采集正常，电量 50%
```

### 10.8 0xA8/0xA0 实测（带手指，2026-10-29 00:40）：不是它

| 帧 | 条件 | row_spread | col_spread |
|---|---|---|---|
| a_base | 0xA8 不动 | 5.53 | 1.26 |
| a_base2 | 同上 | 3.12 | 1.12 |
| b_pxl | 0xA8=0x0f1b, 0xA0=0x0d01 | 4.33 | 0.98 |
| b_pxl2 | 同上 | 2.77 | 0.98 |
| c_pxl | 0xA8=0x0f0b | 5.00 | 0.94 |
| d_off | 0xA8=0x0f00 | 2.81 | 1.16 |

**col_spread 始终 ~1，没有任何一种 0xA8 取值让它跳起来。**
⇒ `PXL_CTRL` 不是列读出使能，这条假设排除。

### 10.9 目前的空白

所有"寄存器层面"的假设都试完了：

```
0x54 窗口          ✗ 有硬件约束
0x68/0x6c/0x90 时序 ✗ rev3/rev4 无差别
0x8c/0x90 驱动     ✗ 6 组无差别
0xa0 ADC 增益      ✓ 有效但只是整体电平
0xa8 PXL_CTRL      ✗ 无影响
0x78 测试图案      ✓ 能改变输出（但饱和/单电平）
```

数据始终是"行内恒定、行间变化"的一维形态。

⇒ **只能从 TA 里找答案了。** 这是唯一没走过的路，需要：
1. Qualcomm TEE 镜像的加载器（Ghidra 扩展 / IDA loader），或
2. 手工找出 `fpctzapp.b02` 的代码段起点（当前 objdump 从 0 开始全是乱码）

参考点：`fpctzapp.b02` 偏移 `0x73b3c` 是 A1/A2/A3/A4-A5 变体表；
`0x1a06b` 附近有 `C0 C4 F8` 命令字节序列，很可能是 SPI 命令封装函数。

### 10.10 建议

今晚（00:40）到此为止。下次开工二选一：
* **A**：花 1–2 小时搭 TEE 加载器（或用现成插件）→ 一次性看清采集序列
* **B**：换思路，先做别的硬件（前摄色彩校正 / CPU 调频 / 短信），指纹留到最后

---

## 11. TEE 反编译：环境已完全打通（2026-10-29 00:55）

### 11.1 关键发现：TA 是 **32 位 ARM**，不是 aarch64

```
b02 开头: 02 00 50 e3   →   cmp r0, #2      (ARM A32 指令)
```

之前一直用 `--architecture arm64` 反汇编，所以是乱码、只找到 1 个函数。
换成 `--architecture arm` 后：

```
procedure_count: 1474
string_count:    1582
language_id:     ARM:LE:32:v7
```

### 11.2 TA 的完整 API 名字表（都在 .rodata，可直接搜到）

```
0x80802 fpc_ta_router_init          0x80f04 fpc_ta_sensor_exit
0x8082b fpc_ta_route_command        0x80f17 fpc_ta_sensor_command_handler
0x80872 fpc_ta_common_init          0x80f67 fpc_ta_sensor_device_init
0x8088c fpc_ta_common_exit          0x80f9e fpc_ta_check_finger_lost
0x808b3 fpc_ta_common_command_handler 0x80fb7 fpc_ta_finger_lost_wakeup_setup
0x8093a fpc_ta_bio_init             0x80fd7 fpc_ta_wakeup_setup
0x809e4 fpc_ta_bio_exit             0x80feb fpc_ta_qualify_capture
0x80a1a fpc_ta_bio_command_handler  0x81015 fpc_ta_poll_qualify
0x80a6e fpc_ta_bio_set_active_fingerprint_set
0x80a94 fpc_ta_bio_begin_enroll     0x81075 fpc_ta_capture_image
0x80ad9 fpc_ta_bio_enroll           0x8108f fpc_ta_deep_sleep
0x80b2e fpc_ta_bio_end_enroll       0x810bd fpc_ta_get_force_...
0x80c38 fpc_ta_bio_identify         ...
0x80cee fpc_ta_bio_update_template
0x80e1d fpc_ta_bio_load_empty_db
0x80e36 fpc_ta_bio_delete_template
...
```

### 11.3 SPI 层次结构（已反编译）

```
fpc_spi_init / destroy / read / write / writeread / select_low_freq
        ↓
qsee_spi_open / close / read / write / full_duplex      (QSEE HAL)
```

寄存器访问分发器 **FUN_0002583c**（`cac_if_reg_read/write`）：

```c
bVar1 = *buf;                    /* 第一个字节 = 命令/寄存器 */
uVar3 = bVar1 >> 2;              /* 索引 = cmd>>2 */
if (uVar3 == 0x31 || table[uVar3].max < 2) { ... }   /* 0x31 = 0xC4 = READ_IMAGE 特例 */
if (len_expected <= 0 || len_expected == param_4) {
    FUN_00003d54();                            /* 上锁 */
    FUN_00003e40(buf, len, out, outlen);       /* 实际传输 */
    FUN_00025ba4(...);                         /* 记日志 */
}
```

传输函数 **FUN_00003e40**：memset → `FUN_0000947c(6, ...)`（qsee HAL 调用，6 = 操作码）。

**命令长度表**在 `DAT_00025938 + (cmd>>2)*0x10`，每个条目 0x10 字节。

### 11.4 已定位的可疑函数

`FUN_00024ef8`（0x24ef8）会写 3 字节命令 `{0x08, 0x54, 0xff}` 并读回 2 字节，
还检查 `0xa11` —— 很可能是**传感器类型/版本探测**，不是裁剪窗口。

### 11.5 调用 0x2583c（寄存器访问）的 14 个位置

```
0x22dbe 0x24f7c 0x250a4 0x25800 0x259b6 0x260f4 0x2619e
0x2622e 0x26262 0x26328 0x265da 0x26696 0x26702 0x2674a
```

**下一步就是逐个反编译这 14 个调用点，找出构造 0xC0/0xC4 和 0x54 的那个函数**
—— 它会给出：正确的裁剪窗口编码、采集时序、以及图像 FIFO 的读出方式。

### 11.6 现成工具（VM 上一行命令）

```sh
sh /tmp/ta_func.sh 0x24f7c          # 反编译一个函数（伪代码 + 被调用者）
sh /tmp/ta_xrefs.sh 0x2583c         # 查谁调用了某地址
sh /tmp/ta_scan.sh 0x22dbe 0x24f7c  # 批量反编译并筛出含关键常量的行
sh /tmp/rea.sh search fpc_ta        # 搜 TA 里的字符串
```

脚本源文件在 `scripts/vm_rea.sh`、`vm_ta_func.sh`、`vm_ta_xrefs.sh`、`vm_ta_scan.sh`、`vm_rea_show.py`。
`GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC` 必须设置。

---

## 12. 01:05 更新：v11 已编好（让 `pxl_ctrl` 参数真正生效）

### 12.1 发现一个死参数

`fpc1020_v10.c` 里：

```c
static unsigned int pxl_ctrl = 0x0A0F;   /* 0xA8 */
module_param(pxl_ctrl, uint, 0644);
MODULE_PARM_DESC(pxl_ctrl, "PXL_CTRL register 0xA8");
```

**声明了、注册了、但代码里从来没用过** —— 改它没有任何效果。
（`adc_gain` 也只影响棋盘图案那条路径。）

### 12.2 v11 修好了

现在两个参数都会**覆盖每帧的 LO_a3a4 表**：

```c
if (pxl_ctrl)  write 0xA8 = pxl_ctrl;   /* 覆盖 {0x0f0a,0x0f1f,0x0f0b} */
if (adc_gain)  write 0xA0 = adc_gain;   /* 覆盖 {0x0408,0x0600,0x0b01} */
```

产物：`build/fpc1020-v11.ko.zst`（128 073 字节，BUILD_OK）

### 12.3 明天的实验（不需要重编，直接改参数）

```sh
# 装上 v11 后
echo 0x0f1b > /sys/module/fpc1020/parameters/pxl_ctrl
echo 0x0b01 > /sys/module/fpc1020/parameters/adc_gain
sh /tmp/fpc_frames.sh          # 抓 3 帧
```

判据：`col_spread` 是否从 ~1 跳到 5 以上。

可以扫的组合（PXL_CTRL × ADC_SHIFT_GAIN）：

| PXL_CTRL | ADC_SHIFT_GAIN | 来源 |
|---|---|---|
| 0x0f0b | 0x0b01 | LO_a3a4 Normal（当前默认）|
| 0x0f1b | 0x0b01 | 参考驱动 normal |
| 0x0f0a | 0x0408 | Dry |
| 0x0f1f | 0x0600 | Wet |
| 0x0f0b | 0x0010 | 低增益（之前扫过）|

### 12.4 TA 里还确认了别的

`fpc_sensor_setup_usecase()` 的最后一步：

```c
read 0x5C; 0x5C |= 0x08; write 0x5C;    /* IMAGE_SETUP */
```

我们驱动写的是 `0x0B`（= 0x03 | 0x08），**一致** ✅

---

## 13. ⚠️ 重要：先看 [29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md)

夜里做的对比分析得出一个结论，会影响后续所有计划：

**我们抓的原始帧（Android 上和 pmOS 上）统计完全一致，但里面没有可用指纹信号**
（逐像素方差 0.75、去均值渲染全是横条纹）。

原因是：**Android 上成像根本不走内核驱动** —— TA 在 TEE 里通过 `qsee_spi_*`
自己读、自己算。内核驱动那条"0xC0 → 0xC4"的路子，在 Android 上只是用来做手指检测。

⇒ **不要再花时间调 0x54 / 寄存器 / 布局了**，那条路的尽头是"读到的还是中间量"。

真正能出指纹的只有两条：
1. 跑厂商 TA（需要 QSEECOM + TA 加载器 + Android HAL，工程量数周，成功率低）
2. 放弃指纹功能，保留"驱动能控制芯片"的成果

### 那今晚之前做的还有意义吗？

有：
- SPI 协议（哑字节、大端）→ 这是所有后续工作的基础
- TA 反编译环境 → 1. 的前置
- 驱动的完整寄存器控制 → 芯片自检/调试仍然有用

**但"再调一个参数就能出图"的预期应该放下了。**

---

## 14. ✅ 0x54 裁剪编码：已有答案（2026-10-29 04:30 补）

§13 说"不要再花时间调 0x54" —— 现在可以更进一步：**0x54 的值我们一直是对的。**

### 证据

在 TA 镜像里搜数值 `0x00B00040`（我们驱动用的 `img_capt_size`）：

```
10 处命中：0x06bec5 / 0x06bf08 / 0x06bf61 / 0x06bfa7 / 0x06bfcb / 0x06c0d6 /
          0x06b119 / 0x06b172 / 0x06b1b8 / 0x06b1dc
```

而 TA 里**没有任何** `mov rN, #0x54`（0 处），说明这个值是从数据表回放的。

手工对齐附近的字节，能读出：

| 寄存器 | 值 |
|---|---|
| **0x54** | **0x00B00040** |
| 0x88 | 0x00000000 |
| 0x4C | 0x04FFFF |
| **0x5C** | **0x0B** |
| 0xA8 | 0x808F |
| 0x68 | 0x0144292409393419 |

**0x5C = 0x0B 和我们驱动写的完全一致。**

### 结论

- 不存在"没推导出来的 0x54 编码"——它就是常量 `0x00B00040`
- 我们的寄存器值、协议（哑字节 + 大端）、供电时钟**全都对**
- 帧里没有图像的根因**不在我们这边**，在 TA 的成像/后处理

### 唯一还没定的

寄存器脚本的条目封装格式（中间有 0x02/0x2D/0x11 等不认识的寄存器号），
简单 `<reg><BE值>` 走不到底。要做的话得先反编译读这段数据的解码器。
详见 [25-TA-REVERSE-ENGINEERING.md](25-TA-REVERSE-ENGINEERING.md) §12。

**但这不影响上面的结论。**
