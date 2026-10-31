# 52 — IPA v3.1 移植：厂商数据、缺口、下一步

- 日期：2026-10-30 13:00
- 状态：**侦察完成，未动 boot。** 结论：可以做，但需要改 DT + 改驱动 + 多次刷 boot，且有一个硬缺口（SMP2P/SMEM ID）。

---

## 1. 从 MIUI boot 镜像里挖到的厂商数据（重要）

`artifacts/rom/miui-boot.img` 里偏移 13331810 处有一个 346KB 的 DTB，
decompile 后（`/tmp/miui.dts`）拿到了完整的厂商 IPA 节点：

```dts
qcom,ipa@14780000 {
    compatible = "qcom,ipa";
    reg = <0x14780000 0x4effc>, <0x14784000 0x26934>;
    reg-names = "ipa-base", "bam-base";
    interrupts = <0 0x14d 0>, <0 0x1b0 0>;
    interrupt-names = "ipa-irq", "bam-irq";
    qcom,ipa-hw-ver = <6>;          /* v3.1 */
    qcom,ipa-hw-mode = <0>;
    qcom,wan-rx-ring-size = <0xc0>;
    qcom,lan-rx-ring-size = <0xc0>;
    clocks = <&rpmcc 0x22>, <&rpmcc 0x59>;   /* core_clk, smmu_clk */
    qcom,arm-smmu; qcom,smmu-disable-htw; qcom,smmu-s1-bypass;
    qcom,ee = <0>;
    qcom,use-ipa-tethering-bridge;
    qcom,modem-cfg-emb-pipe-flt;
    qcom,ipa-wdi2;
    qcom,use-dma-zone;

    ipa_smmu_ap  { iommus = <&apps_smmu 0x19c0>; iova 0x10000000+0x40000000; };
    ipa_smmu_wlan{ status = "disabled"; iommus = <&apps_smmu 0x19c1>; };
    ipa_smmu_uc  { iommus = <&apps_smmu 0x19c2>; iova 0x40000000+0x20000000; };
};
```

厂商 SMP2P（**只有单个节点，没有 per-entry 列表**）：
```dts
qcom,smp2p-modem@17911008 {
    compatible = "qcom,smp2p";
    reg = <0x17911008 0x4>;
    qcom,remote-pid = <1>;
    qcom,irq-bitmask = <0x4000>;
    interrupts = <0 0x1c3 1>;      /* IRQ 451 */
};
```
厂商 SMEM：
```dts
qcom,smem@86000000 {
    reg = <0x86000000 0x200000 0x17911008 0x4 0x778000 0x7000 0x1fd4000 0x8>;
    reg-names = "smem","irq-reg-base","aux-mem1","smem_targ_info_reg";
};
```

## 2. 主线驱动实际需要什么（已读 7.0.14 源码）

| 需求 | 代码位置 | 厂商数据够不够 |
|---|---|---|
| `reg` 里至少 `ipa-reg` + `gsi` 两段 | `ipa_reg.c` / `gsi_reg.c` | ✅ 两段正好对应 ipa-base / bam-base |
| `ipa-shared` | v3.1 驱动**不用** | ✅ 不需要 |
| `ipa` + `gsi` 两个中断 | `ipa_interrupt_init` / `gsi_irq_init` | ✅ 333 / 432 |
| `core` 时钟 | `ipa_power_init` | ⚠️ 厂商用 rpmcc 0x22，主线 rpmcc 索引要映射 |
| `interconnects`（memory/config） | `ipa_power_init` | ❓ 主线可能要求，sdm660 的 icc 节点要有对应 path |
| `iommus` | io-pgtable | ✅ apps_smmu 0x19c0 / 0x19c2 |
| `qcom,smem-states`（两个 state） | `ipa_smp2p_init` | ❌ **硬缺口**：需要 smp2p-mpss 的 `ipa` 条目 |
| `ipa-clock-query` 中断 | `ipa_smp2p_init` | ❌ 同上 |
| `memory-region` + `firmware-name` | `ipa_firmware_load`（仅 SELF loader） | ⚠️ 固件有（mlipay.*），预留内存节点要新建 |

## 3. 硬缺口：SMP2P / SMEM ID

- 主线 `qcom_smp2p` 用 `qcom,smem = <item-id>` + `mboxes`，每个 entry 一个子节点
  （`qcom,entry-name = "ipa"`，两个方向）。
- 厂商 DTB 里没有 item-id（厂商驱动按 remote-pid + bitmask 动态找），
  当前系统也没有 `smp2p-mpss` 节点、没有 SMEM debugfs，**无法直接读出 ID**。

三条出路：
1. **改驱动**：把 `ipa_smp2p_init()` 改成“没有 smem-states 就跳过”，
   只保留时钟常开（`ipa_clock` 由 rpmcc 管）。先让 probe 走通，代价是
   失去 modem↔AP 的时钟投票（bring-up 阶段可接受）。
2. 从 modem 固件里解析 SMP2P/SMEM 表（深，且没把握）。
3. 从旧安装的 kernel 源码/DTS 里找（旧安装的 LTE 射频能稳定，
   说明当时 kernel 对 modem 的 IPA 客户端有不同处理）。

## 4. 建议的迭代顺序（每次都要刷 boot）

1. 只加 **reserved-memory + ipa 节点（status=disabled）**，其余不动 → 刷机验证
   “改动 DTS + 重新打包 boot 能正常启动”。（上次 nozap 失败可能只是 DTB 内容问题，
   需要一次“纯重打包”来隔离。）
2. 加 smp2p-mpss（先用假 ID / 或改驱动跳过）→ 刷机，看 `ipa` probe 是否到
   `IPA driver initialized`。
3. 给 `memory-region` + `firmware-name = "mlipay.mdt"`，看固件加载/SCM 是否成功。
4. 调 icc / rpmcc 索引，直到 probe 不再 EPROBE_DEFER。
5. 最后才是 rmnet/QMI 数据通路。

## 5. 风险

- 每次刷 p12 都可能“刷完不启动”（12:05 已发生过一次），需要在场的 fastboot 恢复。
- IPA 寄存器布局如果和主线 v3.1 不一致，第 2 步就会看到寄存器读写异常，
  甚至总线挂死（需要断电）。
- 没有串口控制台，失败原因只能靠 dmesg（如果还能启动）。

## 6. 当前设备状态（未受本次侦察影响）

横屏 1920×1200、触摸矩阵、WiFi 均正常；modem 保持 shutting-down（fatal=0）；
boot 分区仍是原镜像（md5 55C7BCE4…）。

---

## 7. 实机迭代记录（2026-10-30 13:00–13:15）

### 已做
1. 验证了打包器：用 boot.img 自带的 gz+dtb+ramdisk 重新打包，**md5 与原件逐字节一致**
   （55C7BCE4…），说明 12:05 的 nozap 失败不是打包问题。
2. 验证了 DTB 往返：decompile→recompile 后 md5 不变（4B60ED01…），dtc 不会破坏这棵树。
3. 在 DTB 的 `soc@0` 里加了 IPA 节点（regs/irqs/clocks/iommus），重新打包并刷入 p12。
   - 第一次：`error -ENOENT: error getting core clock` → rpmcc 的 IPA 时钟索引是
     **68 (0x44)**，不是厂商的 0x22；另外中断 flags=0 会触发 GIC 的
     `WARN_ON(type == IRQ_TYPE_NONE)`，改成 4 后消失。
   - 第二次：`DT error getting "ipa-shared" memory property`。

### 现在的进展
```
platform 14780000.qcom,ipa: Adding to iommu group 1     ← 节点已绑定
ipa_interrupt_init() 通过（ipa/gsi 两个中断 OK）
ipa_power_init() 通过（core clock 68 OK）
ipa_mem_init() 失败：缺 "ipa-shared" 资源
```

### 卡点
`ipa_mem_init()` 要求第三个 reg 段 `ipa-shared`（memremap 后作为 IPA 本地内存窗口）。
厂商 DTS 只给了 `ipa-base 0x14780000+0x4effc` 和 `bam-base 0x14784000+0x26934`，
**没有任何资料给出 sdm660 的 ipa-shared 基址/大小**：
- 主线 msm8998 没有 DTS 节点（v3.1 只合了 driver data + binding，没合 DTS）；
- 厂商 IPA 驱动源码没有；
- 猜错地址会在 `ipa_config()` 阶段写 MMIO，可能直接总线挂死。

### 下一步（如果继续）
1. 需要找到 sdm660 IPA 的 shared 窗口地址（0x1478?000/0x147C?000，大小 0x2000），
   或从旧安装内核/固件里挖出来；
2. 然后解决 SMP2P（SMEM item id）或改驱动跳过 `ipa_smp2p_init()`；
3. 再处理 `memory-region`（msm8998 参考值：imem 0x146bd000+0x2000，smem id 497+0x2000）。

### 当前 boot 镜像
p12 里现在是“带 IPA 节点”的镜像（md5 D353B5C7…），**能正常启动**，
IPA probe 在 `ipa-shared` 处安全失败（不会碰硬件）。
回滚镜像：`/root/p12-rollback-ipa.img`（刷之前的完整 p12）。

---

## 8. 13:20 现场：模块编译卡住 + 充电优先

已经写好 `patches/ipa-skip-smp2p.py`（把 `ipa_smp2p_init()` 改成“没有 smem states 就跳过”，
并给 `ipa_smp2p_exit/irq_disable_setup/notify_reset/power_release` 加 NULL 保护），
但在设备上编译 `ipa.ko` 失败：

```
gcc: error: unrecognized command-line option '-fsanitize-cfi-icall-experimental-normalize-integers'
```
→ 必须用 clang（`make LLVM=1`）。改用 LLVM=1 后又卡在：
```
ERROR: modpost: "__platform_driver_register" [ipa.ko] undefined!
```
→ 树里没有完整的 `Module.symvers`/vmlinux（不是完整构建产物），modpost 解析不了内核符号。

**下次继续时的第一步**：
1. 在树里 `make LLVM=1 modules_prepare`，并拿到原厂构建的 `Module.symvers`
   （或做一次完整 `make LLVM=1 -j`，设备上大约 1–2 小时）；
2. 编译出 `ipa.ko`，zstd 压缩后替换 `/lib/modules/7.0.14-sdm660/kernel/drivers/net/ipa/ipa.ko.zst`；
3. DTB 里给 `ipa-shared` 猜一个窗口（按 IPA v3.1 内存表最大 offset 0x2000，
   候选 `0x147CE000+0x2000`），再刷一次 boot。

**用户侧约束**：平板只剩一个 USB-C 口，充电时不能同时插 hub（有线网）；
后续实验只能在 WiFi 下做，且需要用户在场处理可能的硬挂。

### 13:16 更新：模块其实编出来了

```
make LLVM=1 M=drivers/net/ipa KBUILD_MODPOST_WARN=1 modules
→ drivers/net/ipa/ipa.ko (6.1 MB)
```
- `.config` 里 `CONFIG_MODVERSIONS` 没开，`MODULE_SIG_FORCE` 没开 → 未签名模块可加载；
- vermagic 与原厂一致：`7.0.14-sdm660 SMP preempt mod_unload aarch64`；
- 159 个 undefined 符号全部能在 `/proc/kallsyms` 找到（0 missing）。

**已备好但没刷**：`/tmp/ipaboot/boot-ipa.img`（md5 `0d426166…`）——
在旧节点上加了 `ipa-shared = 0x147CE000+0x2000` 和 `qcom,gsi-loader = "skip"`。
等用户醒来、在场时再：
1. 把 `ipa.ko` zstd 压缩替换 `/lib/modules/.../ipa.ko.zst`；
2. 刷这个 boot 镜像并重启；
3. 看 `ipa_config()` 是否把总线写挂（这是最大风险点）。

### 13:20 实测：`ipa_config()` 确实挂死

刷了上面的镜像、手动 `insmod` 打补丁的模块后：
- 跳过 SMP2P 成功（`no IPA SMP2P states; skipping SMP2P`）
- 跳过 `ipa_mem_config()` 也成功（补丁：SHARED_MEM_SIZE 读到 0 就直接 return）
- 然后进入 `ipa_config()` 的硬件寄存器配置，**设备立刻挂死**（SSH/ping 全无响应），
  只能长按电源重启。重启后自动回到原厂 `ipa.ko.zst`，系统正常。

**结论**：挂死点不在 `ipa-shared` 窗口（那次已经跳过 mem config 了），
而在 `ipa_config()` 里的寄存器/电源/时钟/IOMMU 路径。

---

## 9. 14:20 反编译厂商内核 + 厂商 IPA 驱动（关键发现）

### 9.1 厂商内核
`artifacts/rom/miui-boot.img` → 解压得到 `build/miui-vmlinux.bin`：
```
Linux version 4.4.302-XDKernel-gcc1d65a03adc (clang 18.1.3) #6 SMP PREEMPT aarch64
```
（raw ARM64 Image，text_offset=0x80000；含 `ipa-base`/`bam-base`/`IPA_SHARED_MEM_SIZE` 字符串）

### 9.2 厂商 IPA 驱动源码（ASUS sdm660 msm-4.4，公开仓库）
从 `github.com/ahmedshaikh123/android_kernel_asus_sdm660`（分支 ellen）
`drivers/platform/msm/ipa/ipa_v3/` 拿到：

**SRAM 窗口的确切算法**（`ipa.c` `_ipa_init_sram_v3_0()`）：
```c
phys_addr = ipa3_ctx->ipa_wrapper_base          // DT "ipa-base" = 0x14780000
          + ipa3_ctx->ctrl->ipa_reg_base_ofst   // v3.0 = 0
          + ipahal_get_reg_n_ofst(IPA_SRAM_DIRECT_ACCESS_n,
                                  smem_restricted_bytes / 4);
ipa_sram_mmio = ioremap(phys_addr, smem_sz);
```
`ipahal_reg.c` 里 v3.0 表（v3.1 继承）：
```
[IPA_HW_v3_0][IPA_SHARED_MEM_SIZE]       = { ..., 0x00000054, 0 }
[IPA_HW_v3_0][IPA_SRAM_DIRECT_ACCESS_n]  = { ..., 0x00007000, 0x4 }
```
⇒ **SRAM 窗口 = 0x14780000 + 0x7000 + smem_restricted_bytes = 0x14787000 + restricted**
（不是我们之前猜的 0x147CE000！大小 = smem_sz）

**时钟**：设备上 `/sys/kernel/debug/clk/clk_summary` 里：
```
ipa_clk       ... provider 1704000.interconnect  consumer ipa
ipa_a_clk     ... deviceless
```
即 IPA core clock 由 `1704000.interconnect`（a2noc）这个设备提供/暴露，
启用计数为 0（probe 没走到 pm_runtime_get_sync）。

**厂商初始化顺序**（`ipa.c`）：clock enable → `_ipa_init_sram_v3_0`（写 canary）
→ `_ipa_init_hdr_v3_0` → … → Q6/GSI setup。我们挂死的 `ipa_config()` 正对应这一段的寄存器写。

### 9.3 下一步实验（按风险从低到高）
1. **只改 DT 的 `ipa-shared` 为 `0x14787000 + 0x2000`**，不装补丁模块 → 原厂模块仍在
   `smem-state-names` 安全失败，只验证节点/资源解析（低风险，但信息量小）。
2. **验证时钟**：在跑着的系统上手动 `devm_clk_get` 不可行，但可以先用
   `cat /sys/kernel/debug/clk/clk_summary | grep ipa` 确认 ipa_clk 的 provider 和 enable 计数；
   若用补丁模块，可在 `ipa_power_init` 成功后打印 `clk_get_rate(core)`，看是否为 0。
3. **在 `ipa_config()` 前加“只读一次 VERSION 寄存器”的探针**：如果读 VERSION 就挂，
   说明时钟/电源没开；如果读成功，再逐步放开写操作（每次刷机一次）。
4. 确认 a2noc 的 `clocks = <&rpmcc RPM_SMD_IPA_CLK>` 与 IPA 节点用的是同一个时钟源；
   必要时把 IPA 节点的 clock 改成 a2noc 暴露的 ipa_clk（需 phandle/索引）。

### 9.4 现状
- 设备已重启，横屏/WiFi 正常；boot 仍是带 IPA 节点的镜像（stock 模块安全失败）。
- 补丁模块只在 `/root/kbuild/.../ipa.ko`，**没有安装**，重启不会自动加载。
- 下次继续前，先确认用户在场（可能要断电），再按 9.3 的顺序做。

---

## 10. 14:40–15:10 完整资源反编译结果（厂商源码 + 主线源码）

工具环境：VM `192.168.1.200` 有外网，已 sparse clone：
- `~/sdm660-src` = ASUS sdm660 msm-4.4 厂商内核（含完整 `ipa_v3` 源码）
- `~/linux-main` = 主线 Linux（ipa/icc/clk/dts）

### 10.1 寄存器偏移（厂商 `ipahal_reg.c` v3.0 表，v3.1 继承）
| 寄存器 | 偏移 |
|---|---|
| IPA_VERSION | `0x34` |
| IPA_SHARED_MEM_SIZE | `0x54` |
| IPA_SRAM_DIRECT_ACCESS_n | `0x7000`，步长 `0x4` |

### 10.2 SRAM / shared 窗口
```c
phys = ipa_wrapper_base + ctrl->ipa_reg_base_ofst
     + 0x7000 + smem_restricted_bytes;      // n_ofst = 0x7000 + (restricted/4)*4
size = smem_sz;
```
`ipa_wrapper_base = DT "ipa-base" = 0x14780000`，`ipa_reg_base_ofst` v3.0 = 0。
⇒ **真实窗口 = 0x14787000 + smem_restricted_bytes，大小 smem_sz**。
之前猜的 `0x147CE000` 是错的。

`smem_sz` / `smem_restricted_bytes` 来自 `ctrl->ipa_sram_read_settings()` 读寄存器
（即 SHARED_MEM_SIZE 0x54），**只有 IPA 固件跑起来后才有值**；没有固件时读到 0。

### 10.3 时钟
- 厂商：`clk_get(dev, "core_clk")`，**一个**时钟；enable 后 `clk_set_rate(200MHz turbo)`。
  - 厂商速率：SVS 75MHz / nominal 150MHz / turbo 200MHz（`ipa_utils.c`）。
- 主线：`clk_get(dev, "core")`，`clk_set_rate(16MHz)`（`ipa_data-v3.1.c` 的 core_clock_rate）。
- 设备 DT 用 `<&rpmcc RPM_SMD_IPA_CLK>`（=68），a2noc 也消费同一个时钟。
- **疑点**：主线设 16MHz，厂商设 200MHz；寄存器访问挂死可能是时钟频率/门控问题。

### 10.4 总线（interconnects）
厂商 DT 用 msm-bus vectors：
```
<master 0x5a(IPA) slave 0x200(EBI1)>  → memory
<master 0x01(APPS) slave 0x2a4(IPA_CFG)> → config
```
主线 ICC 对应（phandle 来自实机 DTB）：
| 节点 | phandle |
|---|---|
| a2noc interconnect@1704000 | `0x41` |
| bimc interconnect@1008000 | `0x33` |
| gnoc interconnect@17900000 | `0x42` |
| cnoc interconnect@1500000 | `0x43` |
| snoc interconnect@1626000 | **无 phandle**（需加 label） |

拟用：
```dts
interconnects = <0x41 0x00 0x33 0x05>,     /* MASTER_IPA -> SLAVE_EBI */
                <0x41 0x00 &snoc_icc 0x0d>, /* MASTER_IPA -> SLAVE_IMEM */
                <0x42 0x00 0x43 0x08>;      /* APPS -> SLAVE_IMEM_CFG */
interconnect-names = "memory", "imem", "config";
```
（`MASTER_IPA=0, SLAVE_EBI=5, SLAVE_IMEM=13, MASTER_APSS_PROC=0, SLAVE_IMEM_CFG=8`）

### 10.5 传输层：厂商用 SPS/BAM，不是 GSI
- MIUI DTB 的 IPA 节点：`reg-names = "ipa-base","bam-base"`，**没有 `qcom,use-gsi`**
  → 厂商驱动走 `IPA_TRANSPORT_TYPE_SPS`（BAM）。
- 主线 v3.1 只有 GSI 路径（`gsi_init`），**没有 SPS 支持**。
- 即使寄存器访问修好，数据通路还要面对这个差异（或者用 GSI 覆盖 BAM，需要确认硬件）。

### 10.6 TZ / 初始化顺序
- 可选 `qcom,ipa-tz-unlock-reg`：本机 DTB 没有 → 不需要。
- 厂商顺序：bus vote → clocks(+200MHz) → ioremap → ipahal_init → `ipa3_init_hw()`
  （含 HW reset）→ 读 SRAM settings。
- 主线没有 HW reset 步骤；如果 IPA 被 bootloader 留在 reset，读寄存器可能挂。

### 10.7 已准备好的下一版（等设备回来直接用）
1. `tools/build_ipa_boot.sh` 已更新：
   - `reg` 三段：`ipa-reg 0x14780000+0x4effc`、`gsi 0x14784000+0x26934`、`ipa-shared 0x14787000+0x2000`
   - `interconnects`/`interconnect-names` 如上（并给 snoc 节点加 `snoc_icc` label）
   - `qcom,gsi-loader = "skip"`（先只验证寄存器访问）
2. `patches/ipa-clock-200mhz.py`：把 `core_clock_rate` 从 16MHz 改成 200MHz。
3. 驱动补丁已有：`ipa-skip-smp2p.py`、`ipa-skip-memconfig.py`、`ipa-probe-version.py`
   （跳过 SMP2P、跳过 mem config、只读 VERSION 后返回）。
4. 刷机后测试顺序：
   - stock 模块能否安全 probe（预期在 smem-state-names 失败）；
   - 换补丁模块，看 VERSION 读是否还挂：
     - 还挂 → 时钟/电源/复位问题（下一步试 200MHz、power domain、HW reset）；
     - 读成功 → 逐步放开 `ipa_config()` 的写操作。
5. 若 VERSION 读成功但配置写挂，再考虑用厂商的 `ipa3_init_hw` 复位序列。

### 10.8 当前状态（15:10）
- 平板仍处于上次 `insmod` 挂死状态（用户上班，无法断电）；
  等用户回来长按电源重启，重启后自动恢复（补丁模块未安装）。
- 所有资源分析已完成，下一版镜像/补丁已就绪，只差实机验证。

