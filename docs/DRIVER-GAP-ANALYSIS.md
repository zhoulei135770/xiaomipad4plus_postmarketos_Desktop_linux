# 硬件驱动缺口分析（2026-10-27，静态分析，设备离线时完成）

> 设备因 venus HFI v4 实验 panic 挂起，本节全部结论来自**内核源码 + DTB 静态分析**，
> 没有实机验证。每项都给出"证据 → 结论 → 下一步"。

---

## 1. CPU 调频（DVFS）—— **短期不可行**

### 证据
1. `/proc/device-tree` 与 DTB 里**没有** `cpufreq`/`osm`/`cpr`/`apcs` 相关节点：
   ```
   找到的节点只有: /reserved-memory/venus@9cc00000, camera@36, camera@10
   ```
2. `drivers/cpufreq/qcom-cpufreq-nvmem.c` 的 of_match 列表：
   `apq8096, msm8909, msm8996, qcs404, ipq5332, ipq5424, ipq6018, ipq8064…`
   **没有 sdm660**
3. `drivers/cpufreq/qcom-cpufreq-hw.c`（OSM）匹配 `qcom,cpufreq-hw`，
   但要求 CPU 节点有 `qcom,freq-domain` phandle + OPP 表；我们的 DTB 都没有
4. **最关键**：`drivers/pmdomain/qcom/cpr.c` 的 of_match **只剩 `qcom,qcs404-cpr`**
   —— msm8996/msm8998/sdm660 的 CPR 支持已不在树里

### 结论
没有 CPR 就没有可信的电压角落（voltage corner），没有 OPP 表就没有频率-电压映射。
**强行调频 = 用错误电压跑 CPU = 随时挂**。要在 mainline 上做 sdm660 DVFS，需要：
- 移植 CPR 驱动（sdm660 的 CPR 参数表，来自厂商内核）
- 加 OSM cpufreq 支持（sdm660 的 OSM 寄存器布局）
- 写完整 OPP 表（十几档频率 × 电压）

工作量：**数周级别**，且失败会导致硬挂。

### 现状的代价
- `thermal_zone cpu0..3` 有 70 °C passive 触发点，但**唯一 cooling device 是 GPU**
  ⇒ 长时间满载时 CPU 无法降频，只能靠 110 °C 硬件保护关机
- 已经有的缓解：GPU 在 85/90 °C 会自动降频

---

## 2. 4G 数据（IPA）—— **需从零移植**

### 证据
1. DTB 里**没有** `ipa`/`gsi` 节点
2. `drivers/net/ipa/` 有 `ipa_data-v3.1.c`、`v3.5.1`、`v4.x`、`v5.x`，
   但 `grep -r sdm660 drivers/net/ipa/` **零命中**
3. 设备上 `mobile data MISSING (no IPA net port)`，SIM 也是 `absent`

### 结论
需要：IPA 的 sdm660 数据表 + DT 节点（IPA/GSI/SMMU/modem 链接）+ 固件（ipa_fws）。
另外用户目前没插 SIM，优先级低。

---

## 3. venus 硬解 —— **HFI 会话层卡住**（本轮最大进展）

### 已经确定的事实（实机日志）
```
diag: hfi_core_init state=0, calling core_init
diag: venus_core_init entry
diag: cs0=0x40000001 pc_ready=0 ifaceq_da=0xd8c00000
diag: region_addr=0xd8c00000 region_size=0x300000
diag: waiting for INIT_DONE (1 s)
diag: INIT_DONE received, err=0          ←★ 固件核心初始化成功
diag: hfi_session_init st=2 codec=2 fmt=34363248
diag: venus_session_init st=2 codec=2
diag: session_init packet queued
diag: SESSION_INIT reply bad -110 err=0  ←★ 会话初始化无任何响应
```

### 已排除
- ✗ 时钟（已修：19.2 MHz → 441.6 MHz，`video_core_clk_src`）
- ✗ 固件加载（PAS 成功，`venus hw version 3.33.501`）
- ✗ 供电/genpd（`venus`、`venus_core0` 都上电）
- ✗ 系统属性包（0046 跳过 image-version + default properties 后仍无响应）

### 结论
固件能处理 `HFI_CMD_SYS_INIT` 并回 `INIT_DONE`，但对 `HFI_CMD_SESSION_INIT`
**既不回 done 也不回 error**，且之后不再产生任何中断。
下一步方向（按可能性）：
1. 对比厂商 `msm_vidc` 驱动的 session init 序列（寄存器/属性前置要求）
2. 检查 HFI 3XX 与固件期望的会话包布局差异
3. 确认固件是否在 INIT 后需要某个"资源表"（HFI_PROPERTY_PARAM_*）才能建会话

---

## 4. 前摄 S5K5E8 —— **DT 有三处错误 + 缺驱动**

### 证据（DTB 实测）
```
camera@10:
  vana-supply   -> /cam-avdd-front-2v8      2.8V  GPIO49   ✓ 与厂商一致
  vddio-supply  -> l11                      1.8V            ✓
  vdig-supply   -> /cam-front-dvdd-1v8      1.8V  PM660L3   ✗ 厂商要求 1.2V
  reset-gpios   -> tlmm 52, ACTIVE_LOW                      ✓
  clocks        -> <&mmcc 82>  (xvclk2 = MCLK2)             ✓
  没有 assigned-clocks                                      ✗ MCLK 频率没人设
  没有 port/endpoint                                        ✗ camss 不知道它连着 csiphy2
```

### 结论
1. **VDIG 1.8 V 应为 1.2 V** —— 这是 I2C 无 ACK 的最可能原因
   （对比：后摄 `cam-rear-dvdd-1v2` 是 1.2 V）
2. 需要加 `assigned-clocks = <&mmcc 82>; assigned-clock-rates = <24000000>;`
3. 需要加 `port/endpoint` 连到 `csiphy2`（厂商：csiphy2/csid2，CCI master1 → i2c-4，0x10，2 lane）
4. mainline **没有 s5k5e8 驱动** → 需要新写（可仿 `s5k3m5.c`，寄存器表已从厂商 .so 提取）

### 下一步（设备恢复后，最便宜的验证）
DTB 手术把 VDIG 改成 1.2 V，然后 `i2cdetect -y 4` 看 0x10 是否 ACK：
```sh
python tools/dtb_edit.py boot-r157.img boot-r164.img \
  --set-cells "/cam-front-dvdd-1v8=regulator-min-microvolt" "1200000" \
  --set-cells "/cam-front-dvdd-1v8=regulator-max-microvolt" "1200000"
```
如果 ACK 出现 → 证明硬件是好的，只剩写驱动。

---

## 5. 指纹 —— TEE 私有协议（已判定不投入）

厂商驱动 `fpc1020_platform_tee.c` 明说"The driver will NOT send any commands to the
sensor, it only controls the electrical parts"，真正的协议在 TrustZone。
SPI 通信本身已验证正常（读 `0x1c` 能清中断）。

---

## 6. 散热 —— 是 #1 的直接后果

12 个热区，`cpu0..3`/`pwr-cluster` 有 70 °C passive 触发点，但：
```
唯一 cooling_device: devfreq-5000000.gpu (max_state=5)
```
CPU 没有 cooling device 是因为没有 cpufreq。缓解手段只剩 GPU 降频。

---

## 汇总表

| 硬件 | 状态 | 缺口 | 可行性 |
|---|---|---|---|
| CPU 调频 | ✗ | CPR+OSM 驱动、OPP 表 | 数周，高风险 |
| 4G 数据 | ✗ | IPA 驱动数据+DT+固件 | 数周；且无 SIM |
| venus 硬解 | △ 核心通、会话不通 | HFI 会话层协议 | 待对比厂商序列 |
| 前摄 | ✗ | VDIG 电压 + endpoint + 新驱动 | 电压先试（便宜），驱动是大工程 |
| 指纹 | ✗ | TEE 私有协议 | 不可行 |
| 散热 | △ | 依赖 CPU 调频 | 阻塞于 #1 |
