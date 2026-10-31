# 其他硬件攻坚分析（2026-10-27 傍晚，静态 RE + 厂商 DTB/源码）

> 设备因 venus 实验挂起中，以下全部来自厂商 DTB、厂商内核源码、我方已有产物。

---

## 1. 指纹 FPC1020 —— **其实已经做完了大半**

### 硬件（从厂商 DTB `/soc/fpc1020` 解出）
```
compatible  = "fpc,fpc1020"     SPI 1 MHz
AVDD 使能   = TLMM GPIO98 (output-high = on, output-low = off)
VDDIO 使能  = TLMM GPIO92 (output-high = on)
RESET       = TLMM GPIO108 (high = release, low = 复位)
IRQ         = TLMM GPIO71
pinctrl     = fpc_avdd / fpc_vddio / fpc_spi(24,25,26,27) / fpc_reset / fpc_irq
```
厂商复位时序：
```
reset high 100 µs → reset low 5 ms → reset high 5 ms → 读 IRQ
```

### 我们已有的东西
| 产物 | 状态 |
|---|---|
| `tools/fpc1020.c`（13.7 KB） | ✅ 完整 SPI 驱动：寄存器读写、上电、复位、IRQ、分块读 |
| 协议常量 | ✅ `FPC_CMD_CAPTURE=0xC0`、`FPC_CMD_IMAGE_READ=0xC4`、`INT_CLEAR=0x1C`、IRQ bit5 |
| 图像规格 | ✅ 192×192 + 1 dummy byte |
| 传感器配置 | ✅ SAMPLE_PX_DLY/PXL_RST_DLY/ADC_SHIFT_GAIN/PXL_CTRL/IMAGE_SETUP/IMG_CAPT_SIZE 等 |
| sysfs 接口 | ✅ `/sys/bus/spi/devices/spi0.0/{capture,capture_now,cmd,finger,image}` |
| 真实取图 | ✅ 文档记录"抓到过真图"，SPI 读 0x1c 验证可靠 |
| 匹配器 | ✅ `tools/fingerprint.py`（enroll/verify/compare/selftest，含暗帧相减）|
| PAM | ⚠️ `fp-pam` 已写好但**故意未启用** |

### 结论
**指纹不缺驱动、不缺协议** —— 缺的是"注册/验证流程跑通并接进 PAM"。
设备恢复后直接跑 `fingerprint.py selftest` → `enroll` → `verify`，通了再开 PAM。

### TEE 路线的死结（已确认不可行）
- HAL `fingerprint.fpc.so`（aarch64, stripped）导出全是 `fpc_tee_*`（capture_image/enrol/auth…）
- 厂商驱动 `fpc1020_platform_tee.c` 只做供电/复位，协议在 TEE
- trustlet 不在 vendor.img（只有 GPU/音频/wlan 固件）→ 在独立 firmware 分区
- **我们不需要它**：自己的 fpc1020.c 已经能直接读图

---

## 2. 4G / IPA —— 有现实可行性（v3.1 与 msm8998 同代）

### 厂商 DTB 实测（`/soc/qcom,ipa@14780000`）
```
reg         = <0x14780000 0x4effc> (ipa-base), <0x14784000 0x26934> (gsi/bam)
interrupts  = SPI 333 (ipa-irq), SPI 432 (bam-irq)
qcom,ipa-hw-ver   = 6        → 厂商枚举 = IPA_HW_v3_1
qcom,ipa-hw-mode  = 0
qcom,ee           = 0        (AP 是 EE0)
qcom,arm-smmu, smmu-disable-htw, smmu-s1-bypass
qcom,use-ipa-tethering-bridge, qcom,modem-cfg-emb-pipe-flt, qcom,ipa-wdi2
qcom,lan-rx-ring-size = 192, qcom,wan-rx-ring-size = 192
SMMU 子节点: ipa_smmu_ap / ipa_smmu_wlan / ipa_smmu_uc
+ /soc/qcom,rmnet-ipa
```

### mainline 侧
```
ipa_match[]: msm8998 → ipa_data_v3_1 ; sdm845 → v3_5_1 ; sc7180 → v4_2 ; …
```
**sdm660 的 IPA 是 v3.1，和 msm8998 完全同版本** —— 意味着可以复用 `ipa_data_v3_1`
的数据结构，只需按 sdm660 的 endpoint/内存布局调整并新增 compatible。

### 缺的东西（按工作量排序）
1. DT 节点：把厂商属性翻译成 mainline 的 ipa 绑定（`firmware-name`、smp2p、memory-region）
2. `ipa_data-v3_1.c` 的 sdm660 变体（endpoint 配置、内存区域大小）
3. `ipa_fws.mdt` 固件（**在 firmware 分区**，要设备回来 dump）
4. GLINK/SMP2P + QMI(modem) 握手 + rmnet 网络设备

### 结论
**属于"数天到数周"的移植，不是从零**。第一步可以先把 DT 节点 + firmware 拷出来，
用 `ipa` 驱动打印的初始化日志判断固件能否起来。

---

## 3. CPU 调频（DVFS）—— 数据齐了，但工作量最大

### 厂商 DTB 里全都有
```
/soc/qcom,msm-cpufreq                 (厂商 cpufreq 节点)
/soc/cprh-ctrl@179c8000  qcom,cprh-sdm660-kbss-regulator   ← 大核 CPR-H
/soc/cprh-ctrl@179c4000  qcom,cprh-sdm660-kbss-regulator   ← 小核 CPR-H
/soc/cpr4-ctrl@05061000  qcom,cpr4-sdm660-mmss-ldo-regulator (GPU CPR)
/soc/devfreq-cpufreq, /soc/devfreq-cpufreq/mincpubw-cpufreq
```
mainline 的 `drivers/pmdomain/qcom/cpr.c` 现在**只支持 qcs404**，
sdm660 的 cprh 支持已被移除 → 需要把 cprh 逻辑补回来（旧版 mainline 曾有 msm8996/8998 的 cprh 实现可参考）。

### 工作量
- CPR-H 移植（含每档"corner"参数、fuse 修正、闭环校准）
- OSM/APCS cpufreq（sdm660 的 OSM 寄存器布局与 sdm845 不同）
- 完整 OPP 表（十几档 × 电压）
- 失败模式很危险（电压给错 = 随机死机）

**结论：数据齐备但风险高，建议放到最后做。**

---

## 4. 散热 —— 是 DVFS 的直接后果
12 个热区，cpu0..3 有 70 °C passive 触发点，但唯一 cooling device 是 GPU。
没有 cpufreq 就没有 CPU cooling device。缓解只能靠 GPU 降频 + 限制负载。

---

## 5. SD 卡 / OTG / 其他
- SD：控制器已启用，用户无卡可测
- OTG：VBUS 自动切换已验证（`otg_vbus=0` 充电时）
- 充电：**已修复**（AICL 元凶，1.5 A，见 §29）

---

## 汇总：按"投入产出比"排序的建议

| 优先级 | 项目 | 现状 | 下一步 | 预计工作量 |
|---|---|---|---|---|
| ★★★ | 指纹 | 驱动+协议+取图全有 | 跑 selftest/enroll/verify，通后开 PAM | 1 次会话 |
| ★★★ | venus 硬解 | 核心通、会话静默 | 0049（每会话重发属性）已验证编译 | 1 次会话 |
| ★★ | 前摄 | 驱动在、缺 endpoint | 0048 + 探测矩阵 | 1–2 次会话 |
| ★★ | 4G | IPA v3.1 同代可复用 | DT + ipa_fws + data 表 | 数天 |
| ★ | CPU 调频 | 数据齐、mainline 缺驱动 | 移植 cprh + OSM | 数周，高风险 |
