# 厂商（MoKee/LineageOS 4.4 内核）摄像头数据提取与对比

日期：2026-10-25 19:40 ｜ 设备：clover（Mi Pad 4 Plus）

## 0. 结论先行

1. **MoKee 的摄像头能正常工作**，用的是高通 CAF 的 `camera_v2` 栈（`msm_csiphy/msm_csid/msm_ispif/msm_vfe`），
   内核 **4.4.205-perf+**（2021-08-21 构建），后摄就是我们熟悉的 `ov13855_f13v10l`。
2. **关键发现：sdm660 的 RDI 通路是 CSID → ISPIF → VFE RDI，不是直连。**
   厂商 `msm_ispif.c` 里完整实现了 RDI0/1/2：
   `ISPIF_RDI_CLK_MUX_SEL_ADDR`、`ISPIF_VFE_m_RDI_INTF_n_CID_MASK`、
   `RDI_INTF_n_PACK_CFG`、RDI SOF 计数、RDI overflow 中断。
   → mainline camss 的 `csid → vfe_rdi` 直连链路**在任何 sdm660 上都不可能出图**，
   这正好解释了我们的现象：CSID 收到 CSI-2 流量（IRQSTAT=0x0f），VFE 却一个 SOF 都没有。
3. mainline 的 `camss-ispif.c` 其实**代码齐全**（含 RDI），只是 `camss->ispif` 从不分配，
   整个 ISPIF 变成死代码。我们已经试过补上分配（r44）：ISPIF 实体出现、
   RDI0 配置跑通（见 §4 的 dump），但 STREAMON 时内核 oops 重启，还没拿到调用栈。

## 1. 已提取的厂商源码（本仓库 `vendor-cam/`）

来自 `LineageOS/android_kernel_xiaomi_sdm660`（branch `lineage-18.1`，内核 4.4.205，与 MoKee 同源）：

| 文件 | 作用 |
|---|---|
| `msm_csiphy.c` / `.h` | CSIPHY 驱动（2ph/3ph、V50 变体） |
| `msm_csiphy_3_5_hwreg.h` | **CSIPHY v3.5 寄存器表（sdm660 用这个）** |
| `msm_csid.c` / `.h` | CSID 驱动（含 LUT/CID 配置、3p 模式） |
| `msm_csid_3_5_hwreg.h` / `_3_5_1` / `_3_6_0` | CSID 寄存器映射（5.0 = 3_5 系列） |
| `msm_ispif.c` / `.h` | ISPIF 驱动（**含完整 RDI 路由**） |
| `msm_isp48.c` / `.h` | VFE 4.8（sdm660 用 vfe48） |
| `msm_isp_util.c`、`msm_isp_axi_util.c` | VFE 通用/写主（WM）与 RDI 输出配置 |
| `msm_cci.c` | CCI（I2C） |

## 2. 厂商 CSID 配置（msm_csid.c）

```c
/* msm_csid_cid_lut() */
val = (decode_format << 4) | 0x3;      /* 0x3 = ISPIF_EN | RDI_EN */
write(CID_n_CFG + cid*4, val);

/* msm_csid_config()，hw >= V30 */
val = (((lane_cnt - 1)) | (lane_assign << csid_dl_input_sel_shift));
write(CORE_CTRL_0, val);
val = (phy_sel << csid_phy_sel_shift) | 0xF;     /* ← mainline 写的是 | 0x9 */
write(CORE_CTRL_1, val);

/* hw >= V35 且 csi_3p_sel == 1 时，额外写 3P_CTRL_0（CPHY 才需要） */
val = ((lane_cnt - 1) << ENABLE_3P_BIT) | 每 lane input_sel | (phy_sel << 3p_shift) | ENABLE_3P_BIT;
write(csid_3p_ctrl_0_addr, val);
```

对比 mainline（`camss-csid-4-7.c`）：

| 寄存器 | 厂商 | mainline | 备注 |
|---|---|---|---|
| `CID_n_CFG` | `(df<<4) \| 0x3` | `(df<<4) \| 0x3` | ✅ 一致（我们实测 0x23） |
| `CORE_CTRL_0` | `(lanes-1) \| (lane_assign << shift)` | `(lanes-1) \| (lane_assign << 4)` | shift 需按 5.0 映射表核对 |
| `CORE_CTRL_1` | `(phy_sel << shift) \| 0xF` | `(csiphy_id << 17) \| 0x9` | ⚠️ 低 4 位不同（0xF vs 0x9） |

## 3. 厂商 CSIPHY v3.5 的“固定初始化表”（mainline 缺这一大块）

`msm_csiphy_3_5_hwreg.h` 里的 `csiphy_v3_5_3ph` 是一张约 65 条的固定寄存器表，
在 PHY 上电时整表写入（`msm_csiphy_write_settings()`）：

```
0x814=0x00 0x818=0x01 0x81c=0x06 0x82c..0x854 = 0xFF/0xFB/0xEF...（中断掩码/清除）
0x104=0x06 0x108=0x00 0x10c=0x00 0x114=0x20 0x118=0x3E 0x11c=0x41 0x120=0x41
0x124=0x7F 0x128=0x00 0x12c=0x00 0x130=0x01 0x134=0x00 0x138=0x00 0x13C=0x10
0x140=0x01 0x144=0x32 0x148=0xFE 0x14C=0x01 0x154=0x00 0x15C=0x23 0x160=0x02
0x164=0x50 0x168=0x70 0x16C=0x17 0x170=0x41 0x174=0x41 0x178=0x3E 0x17C=0x00
0x180=0x00 0x184=0x7F 0x188=0x7F 0x18C=0x7F 0x190=0x00 0x1cc=0x10
0x28=0x00 0x800=0x00
/* 每 lane 的 cfg（0x200*i 步进，时钟 lane +0x700） */
0x00=0xD7 0x04=0x08 0x08=0x00 0x0C=0xA5 0x10=0x52 0x1C=0x0A 0x2C=0x01
0x30=0x02 0x34=0x03 0x38=0x01 0x3C=0xB8
0x700=0xC0
```

**mainline 只写了后半段**（每 lane 的 `CFG1/2/3/5/6/7/8/9` + `TEST_IMP` + `CTRL15`，
实测值与上表逐个对得上），**完全没写 0x100–0x1CC 这一大块“3PH 公共区”**。
厂商还在每 lane 多写了 20 多个寄存器（`lnn_ctrl1..36`），mainline 只写 12 个。

结论：如果 ISPIF 修好之后仍然没有有效数据，下一步就是把这张表补进
`camss-csiphy-3ph-1-0.c` 的 CAMSS_660 路径（做成 `csiphy_init_regs_660[]` 表 + `lanes_enable` 前写入）。

## 4. 我们这边 route A（恢复 ISPIF）的实测状态

已做（r44 调试模块）：

- `camss.c` 里给 `res->ispif_res` 分配 `camss->ispif` → **媒体图里出现了 `msm_ispif0..3`（各 10 条 link）**
- 链路配置：`csid0:1 → msm_ispif0:0`、`msm_ispif0:1 → vfe0_rdi0:0`（直连 link 关闭）
- `ISPIFDBG` 证明 ISPIF 真的被配置了：

```
ISPIFDBG enable=1 line=0 intf=1(RDI0) csid=0 vfe=0 fmt=0x300a
          clkmux=0x00000000/0x0000000f/0x00000000
ISPIFDBG CTRL0=0x0 IRQM0=0x0a492000 IRQST0=0/0/0 INSEL=0x0 CMD=0xfffffdff/0x0
ISPIFDBG RDI0 STATUS=0x0000000f CIDMASK=0x00000001 PACK0=0x0 PACK1=0x0
```

- 但紧接着 **`Unable to handle kernel NULL pointer dereference at virtual address 0x33c`**，
  内核直接重启（`panic_on_oops` 或中断上下文 oops）。
  因为 journald 没来得及落盘，调用栈没拿到。

**下一步（按顺序）**：

1. 拿到 oops 调用栈：暂时 `echo 0 > /proc/sys/kernel/panic_on_oops`（若不是中断上下文就不会重启），
   或给内核加 `CONFIG_NETCONSOLE=y`（当前配置是 `not set`，需要改 config 刷 boot），
   或开 ramoops/pstore 的 console 区域。
2. 修掉这个 NULL deref。最可能的嫌疑：
   - 主line ISPIF 路径里 `line->fmt[]`/`intf_cmd[]` 与 sdm660 的期望不一致
   - ISPIF `intf_cmd` 的 `ISPIF_VFE_m_INTF_CMD_0` 写成了 `0xfffffdff`（有点可疑）
   - 与 VFE 的 RDI SOF 中断同时到达有关（说明 ISPIF 一开就真的在送帧了，是好兆头）
3. ISPIF 通了以后，用现成的 `ISPIFDBG/VFEDBG/CSIDDBG` dump 确认 VFE 是否能收到 SOF；
   若还没有有效数据，再按 §3 补 CSIPHY 公共区初始化表。
4. 顺带对齐 §2 的两处 CSID 差异（CORE_CTRL_1 的 0xF、lane_assign shift）。

## 5. 在 MoKee 上顺手确认的事（已完成 ✅）

打开相机预览后抓 dmesg，**直接证明了厂商走 ISPIF**：

```
[ 96.408140] ispif_process_irq: PIX0 frame id: 0
[ 96.441519] ispif_process_irq: PIX0 frame id: 1
[ 96.474914] ispif_process_irq: PIX0 frame id: 2
[ 96.508303] ispif_process_irq: PIX0 frame id: 3
[ 96.541693] ispif_process_irq: PIX0 frame id: 4
```

两点重要信息：

1. ISPIF 确实在跑，帧率约 30fps（33ms 一帧）。
2. **厂商预览走的是 `PIX0`（ISPIF 的 PIX 接口 → VFE PIX），不是 RDI**。
   这解释了为什么 `RDI0 STATUS` 我们只看到静态值：
   vendor 的 RAW10 预览是“ISP 全流程”（VFE PIX 做 demosaic/缩放），RDI 只在抓 raw 时用。

   → mainline 侧两条路都可以试，但都要 ISPIF：
   - `RDI`：csid→ispif(RDI0)→vfe_rdi（实现简单，mainline 已有代码；当前卡在 oops）
   - `PIX`：csid→ispif(PIX0)→vfe_pix（要 VFE 全 ISP 配置，mainline 也有代码，但更复杂）
   建议仍然先修 RDI（改动小、抓 raw 有直接价值）。

## 6. 在 MoKee 上还能顺手确认的事（可选）

- 厂商在 `msm_ispif.c` 里对 RDI overflow 有 `pr_err_ratelimited("VFE0 rdi0 overflow.")`，
  如果我们的配置溢出，日志里会出现同样的字样。
- 若要抓厂商的寄存器值：MoKee 内核没有 `/dev/mem`（`devmem` 打不开），
  `CONFIG_DEVMEM` 不可用，也没有 ipc_logging 的 camera 上下文。
  → 用源码（本文档 §2/§3）作为权威依据，比抓寄存器更省事。

