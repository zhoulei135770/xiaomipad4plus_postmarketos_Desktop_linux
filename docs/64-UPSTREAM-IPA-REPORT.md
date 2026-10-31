# 64 — 可提交上游的报告：IPA 核心时钟顺序 bug + SDM660 IPA 访问性结论

> 10-31 下午整理。本文件把今晚可回报上游的内容完整打包：
> 一份补丁（真 bug）和一份 SDM660 IPA 访问性的结论（给社区/后续开发者）。

## 一、补丁（真 bug，与 SDM660 无关也成立）

**文件**：`patches/0001-net-ipa-apply-core-clock-rate-after-enable.patch`
**目标**：`drivers/net/ipa/ipa_power.c`

### 问题

RPM 时钟驱动（`drivers/clk/qcom/clk-smd-rpm.c`）在时钟**未使能**时会**静默忽略**速率设置：

```c
static int clk_smd_rpm_set_rate(struct clk_hw *hw, unsigned long rate,
				unsigned long parent_rate)
{
	...
	if (!r->enabled)
		return 0;          /* <-- 速率被丢弃 */
	...
}
```

而 `ipa_power_init()` 的调用顺序是**先 `clk_set_rate()`，之后（runtime resume 时）才
`clk_prepare_enable()`**：

```c
	clk = clk_get(dev, "core");
	...
	ret = clk_set_rate(clk, data->core_clock_rate);   /* 时钟还没 enable */
```

所以在所有使用 rpmcc 时钟的平台（msm8998、sdm660 等）上，
**IPA 核心时钟的速率从来没有真正生效过**。

### 实测证据（Xiaomi Mi Pad 4 / SDM660）

| 操作 | `clk_get_rate()` 结果 |
|---|---|
| 原代码：`clk_set_rate(75MHz)` 后读 | `2147483647`（INT_MAX，rpmcc 默认值） |
| 先 `clk_prepare_enable()` 再 `clk_set_rate(75MHz)` | `75000000` ✅ |

复现方式：在模块里对 IPA 平台的 `"core"` 时钟按两种顺序分别操作，读回速率即可。

### 修复

在 `ipa_power_enable()` 里、核心时钟使能之后**重新应用一次速率**
（`ipa_power_init()` 里原来那次保留，对接受的 provider 无影响）。

补丁已在 SDM660 设备上编译并运行过；速率从 INT_MAX 变为 75000000。

### 提交建议

- 收件人：`netdev@vger.kernel.org`、`linux-arm-msm@vger.kernel.org`，抄送 IPA 维护者
  （Alex Elder）与 rpmcc 维护者（Bjorn Andersson）；
- 标题：`[PATCH] net: ipa: apply the core clock rate after enabling it`；
- 该 bug 独立于 SDM660 的 IPA 访问性问题，**任何** rpmcc 平台都受影响。

## 二、SDM660 的 IPA 访问性结论（给社区）

### 现象

Xiaomi Mi Pad 4（clover, SDM660, IPA `hw-ver = 6`，寄存器窗 `0x14780000 + 0x4effc`）：

> **任何对 IPA 寄存器窗的读/写都会让 CPU 永久停住（stall），必须长按电源或等 panic 重启。**

### 已排除的原因（都有实测证据）

| 因素 | 做法 | 结果 |
|---|---|---|
| rpmcc 时钟 | `core`/`smmu` 都使能，速率 75 MHz（修顺序后确认） | 仍然 stall |
| ICC | `memory`/`imem`/`config` 三路径，INT_MAX 投票，与厂商 DT 一致 | 投票成功，仍 stall |
| SMMU 时钟 | 使能 | 仍 stall |
| modem | `qcom_q6v5_mss` 正常，`remoteproc0 running` | 仍 stall |
| 固件 | `ipa_fws.mdt` + `b00..b07` 在 `/lib/firmware` | — |
| 驱动流程 | 主线 IPA 驱动（含 smp2p 跳过 + 上面的时钟修复） | probe 在第一笔寄存器访问处挂死 |
| TZ 解锁 | 复刻原厂 `ipa3_tz_unlock_reg()`（SCM_SVC_MP/0x10，28 字节描述符，SMC64 与 Legacy 两种约定） | `-EIO` |
| TZ 是否支持该服务 | 用 `__qcom_scm_is_call_available()` 直接查询 | **`SCM_SVC_MP (0x0c)` 整条服务对 APPS 不可用**（对照：PIL 服务返回 1） |
| 引导加载器 | ABL `fastboot oem` 无 peek/poke | 无法从 bootloader 读寄存器 |
| DMA 代读 | BAM DMA（`qcom,bam-v1.7.0`，无 IOMMU） | 驱动只声明 `DMA_SLAVE`，无 memcpy 能力 |

### 反汇编原厂驱动的结论

原厂 `_ipa_enable_clks_v2_0` / `_ipa_disable_clks_v2_0` 做的事和我们完全一致：

1. 使能 `core_clk`（rpmcc）
2. 设置速率
3. bus 投票（msm-bus 两条路径）
4. 使能 `smmu_clk`

日志里出现的 "enabling gcc_ipa_clk" **只是日志文案**：镜像里没有该时钟的符号名，
原厂 IPA 节点也只引用两个 rpmcc 时钟。**没有任何额外的 MMIO 写或隐藏时钟。**

### 结论

在 Android 之外的 Linux 上，SDM660 的 IPA 寄存器块**无法从 AP 侧访问**。
最可能的原因是引导阶段（XBL/TZ）设定的访问许可或复位状态，而修改它需要
安全世界配合（该平台的 `SCM_SVC_MP` 服务对 APPS 不开放）。

这与社区现状一致：[pmOS SDM660 wiki](https://wiki.nura.eco/wiki/Qualcomm_Snapdragon_660/630/636_(SDM660/SDM630/SDM636))
明确写着 "The thing missing to call it 'functioning modem' is mobile data
driver (IPA)"，所有 SDM660/636/630 机型都还没有 4G 数据。

### 给后续开发者的建议

1. 先解决 **IPA 寄存器可访问性**，再谈驱动：在能拿到 TZ/PAS 授权链信息之前，
   主线 IPA 驱动在这颗 SoC 上无法推进；
2. 可以从 U-Boot（自带 `md`/`mw` 命令）验证引导早期 IPA 寄存器是否可读，
   这能区分"复位保持"与"XPU 拦截"；
3. 本仓库的 BTF 修复（见 63 号文档）对所有自定义 sdm660 内核构建都适用。

## 三、可复用产物清单

| 产物 | 位置 |
|---|---|
| 上游补丁 | `patches/0001-net-ipa-apply-core-clock-rate-after-enable.patch` |
| 探针模块（stage 0/16/22/23/24/26/27/28/30） | `tools/ipa_marker.c` |
| 构建/打包脚本 | `tools/vm_*.py`、`tools/vm_*build*.sh` |
| BTF 修复说明与步骤 | `63-CUSTOM-KERNEL-AND-TZ-TEST.md` |
| modem 崩溃修复 | `60-MODEM-CRASH-FIX.md` |
