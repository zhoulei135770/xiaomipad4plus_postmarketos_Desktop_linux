# 63 — 打通自编内核（BTF 修复）+ TZ 解锁 IPA 的首次实测

> 10-31 中午。本次会话把"自编内核能不能在这台机器上跑"这个问题彻底解决了，
> 并且第一次真正调用到 TZ 的 IPA 解锁接口。

## 1. 结论先说

| 项目 | 结果 |
|---|---|
| 自编内核启动整机（桌面、WiFi、modem） | ✅ **成功** |
| 发行版模块加载 | ✅ 成功（修掉 2 处 BTF 校验） |
| TZ 的 IPA 寄存器解锁（SCM_SVC_MP/0x10） | ⚠️ 调用可达，但返回 **-EIO** |

## 2. 自编内核能启动的两个关键修复

之前无论 clang 18 / clang 20 / gcc 编出来的内核都黑屏，根因**不是**内核本身，
而是**发行版的模块被我们的内核拒绝加载**，导致 systemd 起不来（黑屏、无 SSH）。

### 2.1 BTF 名字校验（第一处）

```
BPF: Invalid name
failed to validate module [libcomposite] BTF: -22
```

`kernel/bpf/btf.c` 里的 `btf_name_valid_identifier()` / `btf_name_valid_section()`
拒绝发行版（新 pahole 生成）的 BTF 名字。放宽为始终通过后，121 个模块正常加载。

### 2.2 空 TYPE_TAG 名（第二处）

```
BPF: [131638] TYPE_TAG
BPF: Invalid name
failed to validate module [mac80211] BTF: -22
```

`BTF_KIND_TYPE_TAG` 类型要求名字非空，而新 pahole 会产出空名字。
把 `if (!value || !value[0])` 改为 `if (!value)` 后，`mac80211`/`ath10k` 正常加载，
**WiFi 恢复**。

### 2.3 编译方法（可复现）

```bash
cd /home/user/kbuild/src-714          # sdm660-mainline v7.0.14-sdm660
cp <运行内核的 /proc/config.gz> .config
export PATH=/usr/lib/llvm-20/bin:$PATH
make ARCH=arm64 LLVM=1 olddefconfig
make ARCH=arm64 LLVM=1 -j8 Image
gzip -9 -k -f arch/arm64/boot/Image      # Image → Image.gz
# 然后与 boot 镜像里的 dtb + ramdisk 重新打包（kernel 段 = Image.gz + dtb）
```

模块必须**在同一个树里**编译（否则 `struct module`/BTF 不匹配，insmod 直接失败）。

## 3. TZ 解锁 IPA：第一次实测

### 3.1 做了什么

- 在 `qcom_scm.c` 增加并导出 `qcom_scm_mp_unlock(phys, len)`：
  `SCM_SVC_MP (0x0c)` / `cmd 0x10` / 三个 32 位参数 `{phys_lo, phys_hi, len}`；
- 模块 `stage=24` 构造描述符并调用，失败时**不再读寄存器**（避免挂死）。

### 3.2 描述符格式（按反汇编逐字节核对）

28 字节/条：

```
offset 0   u64  addr & ~0xfff
offset 8   u64  addr & ~0xfff
offset 16  u64  size
offset 24  u32  0x000C0311      (mov w10,#0x311 ; movk w10,#0xc,lsl#16)
```

（最初的实现把 size 写成 u32、flags 写成 0xC00311，是错的，已修正。）

### 3.3 结果

```
desc phys=0x10500d680 size=0x4effc
qcom_scm_mp_unlock ret=-5        ← EIO
unlock failed -> NOT reading registers
```

TZ 拒绝了调用。

### 3.4 追加实验（都失败）

主线检测到的约定是 **`smc arm 64`**，而原厂用的是 legacy `scm_call`。于是再加了一个
走 legacy 约定的变体 `qcom_scm_mp_unlock_legacy()`（内部调用 `scm_legacy_call()`）：

| 实验 | 结果 |
|---|---|
| SMC64 约定 + 28 字节描述符 | `-EIO` |
| **Legacy 约定**（与原厂相同的接口） | **`-EIO`** |
| 缓冲区放 4 GB 以下（GFP_DMA32） | `-EIO` |

已排除：
- 描述符格式（已按反汇编逐字节核对：`{u64,u64,u64,u32}` + `0x000C0311`）；
- SMC 调用约定（两种都试了）；
- 缓冲区地址高位。

仍未知（需要进一步逆向 TZ 契约）：
- 除 `{phys, len}` 外是否还有额外参数（如 IPA base、region 数量、标志）；
- 该命令是否只允许特定调用者（TZ 可能校验调用上下文/VMID）；
- vendor 的原始表里到底有哪几个条目（我们只放了 IPA 寄存器窗一个）；
- `0x000C0311` 的确切含义。

### 3.5 终结性实验：直接问 TZ"这条命令存在吗"

导出 `qcom_scm_is_call_available(svc, cmd)`（主线内部 `__qcom_scm_is_call_available`
的包装，走 TZ 的 INFO 服务），在模块里查询：

```
avail svc=0x0c cmd=0x10 -> 0      ← 原厂 IPA 解锁命令：TZ 说不存在
avail svc=0x0c cmd=0x01 -> 0      ← MP 服务的其它命令：也不存在
avail svc=0x0c cmd=0x00 -> 0
avail svc=0x0a cmd=0x01 -> 1      ← PIL 服务：存在（对照组，说明查询机制正常）
avail svc=0x7f cmd=0x7f -> 0      ← 乱填的命令：0（符合预期）
```

**结论：这台设备的 TZ 完全不向 APPS 开放 `SCM_SVC_MP`（0x0c）服务。**

也就是说：
- 不是我们的参数格式错了；
- 不是 SMC 约定错了；
- 更不是地址问题；

而是**整条 MP 服务链对 Linux（APPS EE）不可用**。原厂驱动里那段
`ipa3_tz_unlock_reg()` 在这台机器上**大概率也是失败的**（它只打印
"scm call SCM_SVC_MP failed" 后继续执行），也就是说——**IPA 的寄存器访问并不依赖
这个解锁**，我们之前把 TZ 当成主因的判断是错的。

### 3.6 修正后的 IPA 结论

- IPA 寄存器"读一下就 stall"更可能是**电源/时钟/复位未真正打开**，
  而不是 XPU 拦截；
- 但我们已经验证过：两个 rpmcc IPA 时钟已使能、三条 ICC 路径全投票、
  modem 正常运行、固件在磁盘上——这些条件下寄存器仍不可访问；
- 剩下的可能性是**原厂通过某个我们尚未找到的路径**（GCC 分支时钟、
  某个 GDSC 或 RPM 电源域、或 modem 侧 IPA 固件的行为）来点亮 IPA 块。

下一步若有时间，方向应从"TZ"转向"**电源域/时钟树**"：把原厂 DTB 里 IPA 节点相关
的 clock/power 全部列出来逐一核对，以及检查 RPM/RPMH 里是否有 IPA 相关的电源域。

### 3.7 时钟顺序 bug（已修）与最终页扫描

主线 `clk_smd_rpm_set_rate()` 在时钟**未使能**时直接返回、不设置速率：

```c
if (!r->enabled)
	return 0;
```

而我们原来先 `clk_set_rate()` 再 `clk_prepare_enable()`，所以速率从未生效
（`clk_get_rate()` 读回 `2147483647`）。原厂顺序是**先 enable 再 set_rate**。

修正顺序后：

```
R core enable ret=0
R core set_rate ret=0 rate=75000000   ← 现在正确了
R clk smmu on
R icc memory ret=0 / imem ret=0 / config ret=0
R ioremap ok
R +0x0000 read...                     ← 第一笔寄存器读仍然 stall
```

**结论**：即使时钟真的跑到 75 MHz、SMMU 时钟开、三条 ICC 全部投票、modem 正常运行，
IPA 寄存器窗口的**第一个字节就读不动**。

已排除的因素汇总：

| 因素 | 状态 |
|---|---|
| rpmcc IPA 时钟（core/smmu，编号 68/69 正确） | ✅ 已使能，速率 75 MHz 确认 |
| 三条 ICC 路径（与厂商 DT 完全一致） | ✅ 投票成功 |
| modem / adsp / cdsp | ✅ 正常运行 |
| IPA 固件在 `/lib/firmware` | ✅ 存在 |
| TZ 的 MP 解锁服务 | ❌ APPS 不可用（见 3.5） |
| 直接读寄存器 | ❌ 任何偏移都 stall |

剩下的可能：IPA 块被**复位保持**（需要 GCC 的某个 reset 或 bootloader 侧的解除），
或由 XPU 在 boot 阶段就配置为拒绝 APPS（且 MP 服务不对外开放，无法改）。
这两者都需要更底层的资料（GCC reset 表 / TZ XPU 配置），**主线内核侧已无可用手段**。

## 4. 设备当前状态

- 运行**我们自己编译的内核**（`7.0.14-sdm660 #6`，clang 20）；
- 125 个模块加载正常，WiFi（ath10k/wlan0）、触摸、显示、modem（`running`）都正常；
- 想回退到发行版内核：`fastboot flash boot backup/device-boot/boot-icc3-2026-10-31.img`。

## 5. 复用价值

这次的 BTF 修复 + 编译流程，**任何后续内核实改都可以直接复用**：
改 `src-714` → `make Image` → 打包 boot（Image.gz + dtb + ramdisk）→ dd 到 p12 → 重启。
