# 56 — IPA 打点实证：M1–M4 全通，M5 硬挂（2026-10-30 深夜）

> 承接 [55-IPA-MARKER-HANDOFF.md](55-IPA-MARKER-HANDOFF.md) §3.3 的“下次第一步”。
> 本轮把 M0→M5 阶梯全部跑完，**拿到决定性结论**：打点通道可靠，卡点精确定位在
> 第一次 IPA 寄存器访问；并找到最可能的根因（DT 缺 ICC 投票）。

---

## 1. 本轮结论（一句话）

p12 尾部打点通道 **完整可用**（含硬挂→断电重启后仍可读回）；M1–M4 全部通过；
`readl(0x14780034)` **让 CPU 停住**，此时时钟已是 75 MHz、`readl` 机制本身正常（GCC 读数成功）。
最可能根因：**IPA 节点没有 `interconnects`，a2noc/snoc 上 mas_ipa/slv_ipa 带宽投票为 0，
导致 IPA 端口不回包**（读操作永远等不到完成）。

## 2. 决定性证据（p12 尾部原文）

```
BEGIN stage=5 wmode=0 clk_hz=75000000 sanity=1 ts=1793373544
M1 dev found 14780000.qcom,ipa
M2 clk_get ok rate=2147483647
M3a clk_set_rate(75000000) ret=0 rate=75000000
M3b clk_prepare_enable ret=0 rate=75000000
M4 ioremap ok addr=0xffff8000808d7000
M4s GCC[0x0]=0xc0118000 (readl ok)
M5 read BEGIN addr=0x14780034
```

重启后读回、内容完好——**打点方案成立**，旧笔记里“umh 版本未验证成功”的疑虑可以划掉
（两种通道都验证过：`kernel_write` 与 `call_usermodehelper`）。

对照：上一轮 `stage=4` 时时钟 rate 还是哨兵值 `2147483647`；`stage=5` 时因为时钟已被上轮
enable 过，`clk_set_rate` 生效、rate 变成 75000000。**这排除了“时钟没开/没设频”这一项**。

## 3. 新增的硬事实（都可复现）

| 事实 | 证据 |
|---|---|
| DT IPA 节点**没有** `interconnects`/`interconnect-names` | `ls /proc/device-tree/soc@0/qcom,ipa@14780000/` 无该属性 |
| 只有 1 个 clock：`clock-names="core"`、`clocks=<&rpmcc 0x44>` | id 0x44=68 = `RPM_SMD_IPA_CLK`，与主线 `qcom,rpmcc.h` 一致 |
| `of_icc_get()` 在无 `interconnects` 时**返回 NULL**（不是错误） | `drivers/interconnect/core.c`：`/* ... return a NULL path to skip setting constraints */` |
| 因此模块里 `icc_set_bw()` 返回 0 是**空操作**，`mas_ipa`/`slv_ipa` 仍 0/0 | `/sys/kernel/debug/interconnect/interconnect_summary` |
| live DT 的 ICC provider 是主线 `qcom,sdm660-{bimc,cnoc,snoc,a2noc,mnoc,gnoc}`，`#interconnect-cells=<1>` | `/proc/device-tree/soc@0/interconnect@16*` 等 |
| `mas_ipa` 在 **a2noc(0x1704000)**、`slv_ipa` 在 **snoc(0x1626000)** | `drivers/interconnect/qcom/sdm660.c` + `dt-bindings/.../qcom,sdm660.h`（`MASTER_IPA=0`、`SLAVE_IPA=10`） |
| a2noc 自己把 `ipa_clk` 当消费时钟（`1704000.interconnect` / id `ipa`） | `clk_summary` |
| `qcom,ee = 0`（APPS 拥有 IPA，不是 TZ/其它 EE 的问题） | `/proc/device-tree/.../qcom,ee` |
| 没有 watchdog（`/dev/watchdog` 不存在、`CONFIG_QCOM_WDT` 未编） | 挂死后只能长按电源；`panic_on_oops=1`、`panic=120`（若发生 panic 才会自动重启） |

## 4. 原厂 DTB 对照（`artifacts/rom/miui-dtb-0.dtb`，用 `tools/dts_ipa.py` 解析）

```
soc/qcom,ipa@14780000:
  clock-names = "core_clk", "smmu_clk"      <- 原厂两个时钟
  clocks      = <&rpmcc 34>, <&rpmcc 89>    <- 都来自 rpmcc（RPM 管理）
  qcom,ipa-hw-ver = <6>
  qcom,ee     = <>            qcom,ipa-wdi2 / qcom,arm-smmu / qcom,ipa-hw-mode
  reg         = <0x14780000 0x4effc>, <0x14784000 0x26934>   <- 两段，地址与我们一致
  qcom,msm-bus,num-paths = 2  （mas-ipa + slv-ipa，ap-owned，4 档向量 MIN/SVS/PERF/TURBO）
```

结论：原厂 **APPS 侧对 IPA 显式投票 mbus**（`qcom,ap-owned`），并且 IPA 有两个 rpmcc 时钟。
我们现在只有 `core`，且完全没有投票——这正是最可疑的两处缺口。

## 4.5 假设 H 已执行、并被否证（2026-10-30 23:40）

按 §5 做完了：DTB 加 `interconnects=<&a2noc 0 &snoc 10>` + `interconnect-names="memory"`
+ 第二个时钟 `clocks=<&rpmcc 68 &rpmcc 69>`、`clock-names="core","smmu"`，
重打包 boot（内核字节未动）并 `dd` 写入 p12，重启后 live DT 确认三项都生效：

```
interconnects = 00 00 00 41 00 00 00 00 00 00 00 b7 00 00 00 0a   (=<&a2noc 0 &snoc 10>)
interconnect-names = "memory"
clock-names = core smmu
```

然后 `insmod stage=5 icc_kbps=1000000` → **仍然硬挂**（SSH 立即失联，需长按电源）。
即：**ICC 投票 + 第二时钟都不是根因**（或投票没真正到达 a2noc 硬件）。

因此下一个判别点是“投票是否落地”以及“整个 0x1478/0x147c 窗口是否被译码”，见 §7。

## 4.6 孔径扫描：IPA 没死，只死一页（2026-10-30 23:52）

`stage=6` 依次读 4 个地址（每次读前都落盘），断电重启后 p12 尾部原文：

```
M4i icc_set_bw(1000000) ret=0
S0 read BEGIN 0x14784000 (+0x4000)   ->  S0 = 0x00020002    (GSI 有响应 = GSI v2.2)
S1 read BEGIN 0x14787000 (+0x7000)   ->  S1 = 0x00000000    (SRAM 有响应，全 0)
S2 read BEGIN 0x147ce000 (+0x4e000)  ->  卡死（无 S2 结果）
```

结论：

| 地址 | 归属 | 结果 |
|---|---|---|
| `0x14784000` | GSI / bam-base | ✅ 可读，`0x00020002` |
| `0x14787000` | IPA SRAM | ✅ 可读，`0x00000000` |
| `0x14780000 + 0x34` | ipa-base 首页（VERSION） | ❌ stall |
| `0x147ce000` | **我们 DT 里编造的第三段** | ❌ stall |

- 原厂 `reg` 只有两段：`<0x14780000 0x4effc>, <0x14784000 0x26934>`；
  `0x147ce000` 是 `build_final.py` 里写进去的第三段（`ipa-shared`），**在 sdm660 上没有译码**，
  以后必须从 DT 删掉，否则驱动迟早会踩到它。
- 既然 GSI/SRAM 能读，说明 **IPA 孔径本身是通的、NoC 投票也够**；
  只有 `0x14780000..0x14783fff` 这一页（core 寄存器，含 VERSION）不响应。
- 最可能：**这一页的 core 时钟没真正打开**（`ipa_clk` 的 rpmcc 投票声明成功但实际没生效），
  或该页另有独立门控/复位（retention）。

## 4.7 下一轮候选（每条最多 1 次挂死 + 1 次长按）

1. **修 DT**：删掉 `0x147ce000` 第三段；顺便把 `qcom,smem-states`/`qcom,smem-state-names`
   补上，让原厂 `ipa.ko` 能自己 probe 到 `ipa_config()`——用驱动自己的
   `pm_runtime + QMP + icc_bulk_enable` 序列去读 VERSION，和模块的手工序列做对照。
2. **模块级**：读 `0x14780000`（offset 0）确认是整页死还是只有 `0x34`；
   并可试 `clk_set_rate(core, 19200000)`/换 enable 顺序。
3. **rpmcc 核对**：原厂用 rpmcc id 34/89（core_clk/smmu_clk），主线按 `qcom,rpmcc.h` 用 68/69；
   若 RPM 资源号对不上，投票会“成功但无效果”——需要从 `QCOM_SMD_RPM_IPA_CLK` 常量反查。

## 4.8 驱动级追踪：probe 全链路 + 同样死在 core 页（2026-10-31 00:10）

在 **VM** 上重编 `ipa.ko`（必须在 x86 VM 上用 `ARCH=arm64`；**平板上编 ipa 驱动会把设备压到自重启**，
内存 3.6 GB 不够），给 `ipa_probe` 每一步插 `IPA-STEP` 标记，并把 `ipa_config()` 整个替换成
`pr_info + return 0`（保证追踪期间不碰寄存器）。手动 `rmmod ipa; insmod` 的结果：

```
IPA-STEP: ipa_reg_init start        ret=0
IPA-STEP: ipa_mem_init start        ret=0     <- "ipa-shared" 用 0x14787000 时 OK
IPA-STEP: ipa_cmd_init start        ret=0
IPA-STEP: gsi_init start            ret=0
IPA-STEP: ipa_endpoint_init start   ret=0
IPA-STEP: ipa_table_init start      ret=0
ipa 14780000.qcom,ipa: missing qcom,smem-state-names
IPA-STEP: smp2p_init start
IPA-STEP: smp2p_init ret=-22                 <- 真正卡点（不是 -22 来自 reg_init）
```

- 这棵树的 `ipa_smp2p_init()` 在缺 `qcom,smem-state-names` 时**直接返回 -EINVAL**（不是“警告后跳过”），
  必须补 DT 的 `qcom,smem-states`/`qcom,smem-state-names`，或临时改成 `return 0`。
- 把 smp2p 改成直接 `return 0` 后再 `insmod`：probe 继续走 `pm_runtime_get_sync → ipa_config(stub)`
  之后进入 `ipa_setup()` 写端点/表寄存器，**当场黑屏硬挂**。
- 结论：**换成驱动自己的电源序列（pm_runtime + clk）也一样死在 `0x14780000` 那页**。
  这排除了“我们模块的 enable 顺序不对”，把问题锁定在 **core 寄存器页本身没有时钟/没出复位**。

## 4.9 下一个待验证假设：IPA retention（AOSS QMP）

`ipa_power_retention_init()` 用 `qmp_get(power->dev)` 取 QMP，若失败则“假定不需要”并跳过；
成功则在 power enable 时给 AOSS 发 **IPA retention** 消息。我们 DT 的 IPA 节点没有 `qcom,qmp`，
所以这条路径从未执行。若 Bootloader/AOSS 把 IPA 留在 retention（块级门控、只放行 GSI/SRAM），
就能解释“GSI 能读、core 页不能读”。

验证（纯 DT，一次刷机）：给 IPA 节点加 `qcom,qmp = <&aoss_qmp>`（phandle 从当前 DTB 查），
其余不变；再手动 insmod 带标记的驱动，看 `ipa_power_retention_init` 是否成功、core 页是否活。

## 4.10 retention 假设也被否证（无 QMP provider）

想验证 IPA retention，需要给 IPA 节点加 `qcom,qmp`。实测：

```
/sys/bus/platform/drivers/qcom_aoss/     -> 空（模块加载但没绑定任何设备）
/sys/devices/.../*aoss*                  -> 无
/sys/kernel/debug/qmp                    -> 无
DT 里 compatible 含 aoss/qmp 的节点      -> 只有 phy@c010000(qmp-usb3-phy) 和 aoss-thermal
```

结论：**这份 DT 根本没有 AOSS QMP 节点**，`qmp_get()` 永远失败 → `ipa_power_retention` 永远跳过，
retention 无法验证（也无法用它解释 core 页不响应）。

## 4.11 目前仍未解释的唯一事实

`0x14780000..0x14783fff`（core 寄存器，含 VERSION）无响应，而 `0x14784000`（GSI v2.2）、
`0x14787000`（SRAM）可读；无论用模块手工序列还是驱动自己的 `pm_runtime` 序列结果一样。
剩余候选（下一会话按成本排序）：

1. **rpmcc 时钟资源号**：原厂 `core_clk/smmu_clk` 用 rpmcc id 34/89，主线用 68/69；
   若 RPM 资源号不匹配，`clk_prepare_enable` 会“成功但无效”。可从
   `QCOM_SMD_RPM_IPA_CLK` 常量与 sdm660 RPM 固件对照，或用 vendor 内核里
   `clk-ipa-clk` 这个字符串反查（`vendor-kernel.decompressed` 里有）。
2. **modem 侧依赖**：IPA 可能与 MSS 电源岛绑定；先把 `4080000.remoteproc`（mba）之后的 q6 完整拉起，再读 core 页。
3. **vendor 驱动反编译**：`artifacts/rom/vendor-kernel.decompressed` 里反汇编 IPA 驱动的
   clock/reset 序列，看它是否在 enable 前写了某个未建模的寄存器（纯主机侧工作，零风险）。

## 4.12 安全窗口 dump（stage 7/8）与两个死胡同

在**已证明可读**的窗口里做安全 dump（不碰死页，`insmod` 返回 0）：

```
+0x4000 = 0x00020002   +0x4004 = 0        +0x4008 = 0x00002000
+0x4034 = 0             +0x4100 = 0        +0x5000 = 0x00674427
+0x5004 = 0x10070004   +0x5008 = 0x070b0014   +0x5034 = 0
+0x5ffc = 0
```

- `+0x5000` 页有一组非零 ID/配置值，但 `+0x5034` 不是版本号——不足以证明寄存器块在 `+0x5000`。
- 死胡同 A：**ipa_fws 固件**。vendor 的 SELinux 上下文里有 `soc:qcom,ipa_fws@…`，
  但原厂 DTB（`build/miui.dtb`）**没有该节点**，vendor 内核里也没有 `ipa_fws` 驱动 → 本机不使用该固件。
- 死胡同 B：原厂 `clocks` 的第二个 phandle 我先前解析错了。正确值是
  `clocks = <&rpmcc 34>, <&rpmcc 89>`（`clock-names = core_clk, smmu_clk`），两个都来自 rpmcc。
  主线 rpmcc 用自己的编号（68/69），且 `QCOM_SMD_RPM_IPA_CLK = 0x617069`（ASCII "ipa"），资源号本身合理。

## 4.13 结论与下一步建议（2026-10-31 00:35）

已确认的事实链：

1. 打点通道可用，能精确定位硬挂点（本轮所有结论都靠它）。
2. IPA 的 GSI/SRAM 窗口可访问（GSI v2.2），**core 寄存器页 `0x14780000..0x14783fff` 不可访问**。
3. 与是否有 ICC 投票、是否开第二个时钟、用模块手工序列还是驱动 `pm_runtime` 序列**无关**——一律死在同一页。
4. 没有 IPA GDSC、没有 AOSS QMP provider、没有 ipa_fws 节点。

→ 剩下最可能的两条：
- **(a) rpmcc 的 IPA 时钟投票在这个平台上是“成功但无效”**（RPM 固件不认这个资源），需要对照 vendor 内核的时钟初始化做交叉验证；
- **(b) IPA core 由 MSS/固件侧控制**，APPS 侧在 modem 完整起来之前无法访问该页。

**建议的下一会话第一步（零风险、不需要重启/刷机）**：在主机侧对
`artifacts/rom/vendor-kernel.decompressed` 做定向分析——找到 `clk_get(..., "core_clk")`
附近以及 `ipa` 驱动 probe 的初始化序列，确认原厂在 enable 时钟之外是否还写了某个
GCC/rpm 寄存器（即我们没建模的那一步）。只有这一步无解时，才值得再冒一次挂死去试 modem 先起。

## 4.14 夜间（主机侧）分析：RE 路线的可行性与限制

想在原厂内核里确认“开时钟之外还做了什么”，试了三条路，结论如下（都不影响设备）：

1. **裸 `ADRP+ADD` 扫描**（python，不依赖工具）：对 `vendor-kernel.decompressed` 全量扫
   引用 `core_clk`/`smmu_clk` 的指令，命中 0。诊断脚本显示全镜像仅 7 条 ADRP 落在
   `0x00c00000..0x00d20000`（字符串所在文件区间）——说明**该 blob 的文件偏移与虚拟地址不是线性对应**。
2. **头部校验**：blob 前 64 字节全 0，`0x38` 处不是 `ARM\x64`，且**全镜像没有 `Linux version` 字符串**
   → 它不是标准 ARM64 `Image`，也不是带 ELF 头的 `vmlinux`，不能直接按 VA=基址+偏移 反推。
3. **REA/Ghidra**：本机是 Windows，Ghidra P0 只接受 PE/raw-6502，**不支持 raw arm64**；
   Hopper 不支持 Windows；IDA/Kuna 未配置。→ 本机无法做 arm64 反汇编。

**可用的替代**：VM（Ubuntu，clang 18 自带 `llvm-objdump`）可以反汇编 aarch64；但需要先拿到
**带符号/带 ELF 头的原厂产物**（`artifacts/rom/vendor-kernel.bin` 或 vendor 分区里的
`/vendor/lib/modules/*.ko`），裸 blob 没有映射关系，反汇编价值有限。

## 4.15 明早的建议实验（按性价比排序）

| 编号 | 风险 | 内容 |
|---|---|---|
| E1 | 零 | 在已可读的 `0x14784000` 窗口继续 dump（GSI 版本/capacity），确认“只有 core 页不可达”这个唯一结论没有遗漏 |
| E2 | 1 次挂死 | 模块里把 `clk_set_rate` 改成 `19200000`（直通 xo）再读 core 页，排除“RCG 被设到非法分频导致时钟停” |
| E3 | 1 次挂死 | 只 enable `ipa_a_clk`(69)、不 enable `core`(68)，再读 core 页，排除两个时钟的相互依赖/顺序问题 |
| E4 | 1 次挂死 | 先把 modem（q6）完整拉起，再读 core 页，验证“IPA core 受 MSS 控制”的假设 |
| E5 | 零 | 从 `vendor.img` 里取出 `/vendor/lib/modules/ipa.ko`（ELF，有段表），拷到 **VM** 用 `llvm-objdump -d` 看原厂 `ipa_probe`/时钟使能序列——这是唯一能拿到“原厂到底写了哪些寄存器”的可靠途径 |

**当前设备状态（睡前）**：boot 分区是修正后的 DT（`reg` 三段合法、`clocks=core,smmu`、无 `interconnects`、
第三段 `0x14787000`），开机正常；stock `ipa.ko` 停在 `smp2p_init(-22)`，不碰寄存器；
带标记的驱动只在 `/root/ipa_trace*.ko`，不会自动加载（手动 insmod 才会动硬件）。
回滚镜像：主机 `backup/device-boot/boot-pre-icc-2026-10-30.img`。

模块已加好 `skip_core` 参数并重编（`/root/ipa_marker/ipa_marker.ko`），明天的两条实验各一条命令：

```
# E2：把 core 时钟设到 xo 直通 19.2MHz，再读 VERSION（可能挂，需长按电源）
sh /root/ipa_run.sh 5 0 clk_hz=19200000

# E3：完全不开 core，只开 smmu(ipa_a)，再读 VERSION（可能挂）
sh /root/ipa_run.sh 5 0 clk_hz=19200000 skip_core=1
```

## 5. 下一步（唯一未验证的关键假设）

**假设 H**：IPA 端口因为 a2noc 上没有带宽投票而保持关闭 → 首次访问永久 stall。

验证步骤（需要改 DTB 并刷 boot，内核/ramdisk 不动）：

1. 在 IPA 节点加（phandle 从当前 boot 的 DTB 里查，不能用 msm8998 的 0x41/0x33）：
   ```
   interconnects = <&a2noc 0 &snoc 10>;   /* MASTER_IPA=0, SLAVE_IPA=10 */
   interconnect-names = "memory";
   ```
   注意：`build_final.py` 里现成的 `<0x41 0x00 0x33 0x05>` 是 **msm8998 的编号**，在 sdm660 上无效。
2. 重打包 boot（沿用 `build_final.py` 的方式：当前 p12 的 kernel + 新 DTB），`fastboot flash boot`。
3. 模块投票 + 读版本：
   ```
   insmod /root/ipa_marker/ipa_marker.ko stage=5 wmode=0 icc_kbps=1000000
   ```
   预期日志：`M4i icc_set_bw(1000000) ret=0` → `M5 VERSION=0x........`；
   若仍停在 `M5 read BEGIN`，则 H 被否证，下一步转向第二个时钟（`RPM_SMD_IPA_A_CLK=69` / smmu_clk）
   或确认 IPA 总线在 APPS 侧真的不可达。
4. 刷机安全：stock `ipa.ko` 在 `ipa_smp2p_init` 就失败（缺 `qcom,smem-state-names`），
   **不会**走到 `ipa_config` 的寄存器读，所以加 `interconnects` 不会让开机阶段挂死。
   回滚：`fastboot flash boot mipad4plus/backup/device-boot/boot-zap-2026-10-30.img`。

## 6. 工具与命令（本轮新增/更新）

- 模块源码：`mipad4plus/tools/ipa_marker.c`（stage 0–5，参数 `stage` / `wmode` / `clk_hz` / `sanity` / `icc_kbps`）
- 设备侧：`/root/ipa_build.sh`、`/root/ipa_run.sh`（后者用法 `ipa_run.sh <stage> <wmode> [额外参数]`）
- 读标记：
  ```
  dd if=/dev/mmcblk1p12 bs=512 skip=131056 count=2 2>/dev/null | strings
  ```
- 设备侧改 DTB 用 `dtc`（`build_final.py` 已依赖它）、原厂 DTB 解析用 `tools/dts_ipa.py`
- SSH：`tools/padsh.py <脚本> --sudo`（注意脚本必须是 **LF** 换行，CRLF 会报 `can't open`）

## 7. 别忘的坑

- 写标记的 1024 字节块位于 p12 最后两个扇区（`seek=131056 count=2`），远离 boot 镜像本体，安全。
- 每次测试前脚本会先清零该块再写 `ATTEMPT`，避免读到上一轮残留。
- `insmod` 非 0 返回是**预期**（stage≥1 时模块返回 -ENODEV/-EIO 表示该步失败），看 p12 内容而不是返回码。
- 时钟 rate 读数为 `2147483647` 是该树时钟驱动的哨兵值（`ce1_clk` 同样），不要当成故障。
