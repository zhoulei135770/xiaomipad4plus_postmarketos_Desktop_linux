# 59 — 4G(LTE) 上主线：从当前状态到可用的完整方案

> 现状：平板可正常跑 postmarketOS 主线内核（`7.0.14-sdm660`），WiFi/显示/USB 可用；
> **LTE 不通**，卡在 IPA。本文是把“为什么不通、还差什么、按什么顺序做”写成可执行清单。

---

## 1. 链路依赖（谁离不开谁）

```
LTE 数据面：
  应用 → rmnet0 → IPA(硬件加速) → 调制解调器(q6) → 射频
                    ↑
              需要 4 样东西同时就位：
              ① IPA 的时钟/复位（GCC + rpmcc）
              ② IPA 微控制器固件 ipa_fws（UC）
              ③ IPA 驱动与 modem 的 QMI 握手
              ④ modem 固件(q6) 稳定运行
```

**当前 ①②③④ 都没到位**，其中 ① 和 ② 是今晚查清的部分。

## 2. 已确证的事实（本轮及之前）

| 项 | 结论 | 证据 |
|---|---|---|
| IPA 寄存器页 | `+0x34`(IPA_VERSION) 读即 stall | 打点 stage5；原厂代码 `0xffff800010d8c8e8` 证明该偏移就是 VERSION |
| GSI 窗口 | 可读，`0x00020002` | stage6 孔径扫描 |
| IPA SRAM 窗口 | `0x14787000` 可读（返回 0）；`0x147ce000` stall | stage6/7 |
| ICC 投票 | 能落地但不解决问题 | stage4，`mas_ipa/slv_ipa` 变 INT_MAX |
| 两个 rpmcc 时钟 | 能 enable（enable_cnt=1）但不解决问题 | stage3 + clk_summary |
| IPA 固件 | **设备上已有** `/lib/firmware/ipa_fws.mdt` + `b00..b07` | 设备实测 |
| TZ PAS | `pas_init_image(15, 裸.mdt)` = **-22**；可能是元数据不合法（需 `qcom_mdt_read_metadata` 构造） | stage12 |
| 原厂加载路 | 有 `ipa3_pil_load_ipa_fws` 与 `ipa3_manual_load_ipa_fws` 两条 | 反汇编字符串 |
| 原厂 IPA 节点 | clocks = rpmcc(34,89)；interrupts = SPI 333/432；无 memory-region；有 `qcom,arm-smmu` | vendor DTB 全属性 |
| 固件段 | UC 地址空间：0x0/0x10000/0x42000/0x43000/0x44000/0x45000（≈0x46000） | `ipa_fws.mdt` ELF 头 |

## 3. 关键判断

**IPA 是“带微控制器的子系统”**：UC 固件没跑起来之前，IPA 的核心寄存器域不响应
（GSI/SRAM 属于 always-on 域，所以能读）。而 UC 的启动有两条路：

1. **PAS（TZ 认证 + 复位释放）** —— 主线 `qcom_mdt_load()` 就是这条路，
   我们已把调用封装成 module 的 `stage=17/18`，**不需要改 DT、不需要刷机**。
2. **手动加载**（原厂 `ipa3_manual_load_ipa_fws`）—— 自己把固件写进 SRAM 再启动 UC。
   但 UC 的“启动/复位释放”若由 TZ 掌握，这条路也走不通，需要额外确认。

→ 所以下一步的实验顺序是**先试 PAS，因为它是唯一被证明能释放复位的机制**。

## 4. 执行清单

### 第 0 步（需要人）：恢复设备
长按电源 10 秒 → 开机。然后读 p12 尾部确认上次挂在哪里：
```
dd if=/dev/mmcblk1p12 bs=512 skip=131056 count=2 | strings
```

### 第 1 步（10 分钟，零风险）：验证 TZ PAS 是否真的可用
```
modprobe qcom_mdt_loader
sh /root/ipa_run.sh 17 0      # 只装载，打印 qcom_mdt_load 返回值
```
- **ret = 0** → TZ 接受、IPA 已认证并复位释放 → 进第 2 步；
- **ret < 0** → 走第 3 步（手动路径）或确认该机 TZ 不支持（则 IPA 无解，需换思路）。

### 第 2 步（半天，核心）：IPA 驱动 bring-up
```
sh /root/ipa_run.sh 18 0      # 装载后读 VERSION，验证寄存器页是否活了
```
若 VERSION 有值：
1. DT 里把 IPA 的 `compatible` 与数据表对齐（原厂 `ipa-hw-ver=6` ≈ IPA v3.0，
   主线最近的是 `ipa_data_v3_1`；必要时补一张 v3.0 表）；
2. 补 `qcom,smem-state-names`（否则 `smp2p_init` 返回 -22，probe 走不到底）；
3. 让驱动跑完 `ipa_setup()`，确认 endpoint/RT 表配置成功；
4. 接 `ipa_qmi`：需要 modem 侧回应，见第 4 步。

### 第 3 步（1–2 天）：手动固件加载（若 PAS 不通）
按原厂 `ipa3_manual_load_ipa_fws` 复刻：
1. `ioremap(0x14787000, 0x50000)`（UC 内存窗口，已验证可读）；
2. 按 ELF program header 把 `ipa_fws.bNN` 段写入 `SRAM + p_paddr`；
3. 找 UC 启动/复位释放的寄存器（从原厂 `ipa3_uc_init` 反汇编继续挖），
   或确认必须由 TZ/modem 完成。

### 第 4 步（1–2 天）：modem（q6）稳定
- 现状：`4080000.remoteproc` 能 running，但固件崩溃会带崩 WiFi，历史上被手动 keep down。
- 需要：`qcom_q6v5_mss` + `modem.mdt` 完整启动、稳定运行、并允许 IPA 的 QMI 通道。

### 第 5 步（半天）：数据面
- `rmnet` netdev、QMI 取 IP、路由/防火墙；
- 与 WiFi 共存（同一 `rmnet`/`wwan` 优先级）。

## 5. 诚实的评估

- **今晚**：只完成了“诊断 + 工具 + 待跑实验”，4G 尚未通。
- **最快路径**：第 0→1 步（一次重启 + 一条 insmod）就能确定 IPA 是否可救；
  若 PAS 可用，第 2 步是小时级；若不可用，第 3 步是天级。
- **风险**：只要 IPA 寄存器页不动，任何驱动改动都无从验证——所以第 1 步是唯一的关键分叉。

## 6. 现有可复用资产

| 资产 | 位置 |
|---|---|
| 打点模块（stage 0–18） | `tools/ipa_marker.c`，VM 已编 `/home/user/ipa_marker/ipa_marker.ko` |
| 固件段解析 | `tools/mdt_parse.py` |
| DT 打包（ICC 三路 / 修 reg） | `tools/dtb_icc3_pack.py`、`tools/dtb_fix_pack.py` |
| 原厂内核反汇编 | `build/vendor-kernel.raw.img` + VM `llvm-objdump`（见 57 号） |
| 一键探测脚本 | `tools/ipa_autoprobe.sh`（设备端 `/root/ipa_autoprobe.sh`） |
