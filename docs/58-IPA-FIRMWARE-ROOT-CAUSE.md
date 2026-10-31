# 58 — IPA 卡点的最终定位：缺的是固件加载（TZ 不支持 PAS）

> 今晚（10-30 夜 → 10-31 凌晨）沿着“反编译原厂内核”把 IPA 为什么一读寄存器就硬挂查到了底。
> 结论：**硬件没问题，缺的是 IPA 固件（ipa_fws）的加载与启动**；而这台设备的 TZ 不支持
> IPA 的 PAS 通道，必须走原厂那条“手动加载”路。

---

## 1. 证据链（按时间顺序，全部可复现）

1. **打点通道**：p12 尾部 1024 字节日志，硬挂断电后仍可读回，能精确到行（见 56 号文档）。
2. **孔径扫描**：`0x14784000`(GSI, 返回 `0x00020002`)、`0x14787000`(SRAM, 返回 0) 可读；
   `0x14780000` 首页（含 VERSION 0x34）**不可读**（stall）。
3. **排除项**：ICC 投票已落地（`mas_ipa`/`slv_ipa` 从 0 变 INT_MAX）、两个时钟 enable_cnt=1、
   无 IPA GDSC、无 AOSS QMP provider、无 ipa_fws 的 DT 节点。
4. **驱动级追踪**（VM 编 `ipa.ko` + 每步打印）：`reg/mem/cmd/gsi/endpoint/table` 全 0；
   `smp2p` 返回 -22（缺 `qcom,smem-state-names`）；跳过 smp2p 后用驱动自己的
   `pm_runtime → ipa_config → ipa_setup` 序列，**同样在黑屏在同一页** → 与我们的 enable 顺序无关。
5. **原厂内核解压成功**（关键突破）：`artifacts/rom/vendor-kernel.bin` 其实是
   `0x800` 字节零 + **gzip**，`.decompressed` 并未解压；正确解压得到 42.3 MB 真 Image，
   `VA = 0xffff800010080000 + file_offset`（详见 57 号文档）。
6. **原厂驱动字符串**：完整 downstream IPA 驱动（ipa3/ipahal/ipa_clients），含
   `ipa3_pil_load_ipa_fws`、`ipa3_manual_load_ipa_fws`、`request_firmware("ipa/ipa_fws.elf")`。
7. **主线驱动行为**：`qcom,gsi-loader = "self"` 时 `ipa_probe` 会先
   `ipa_firmware_load()` → `request_firmware` → `qcom_mdt_load(..., IPA_PAS_ID=15, ...)`
   → `qcom_scm_pas_auth_and_reset(15)`；而我们的 DT 写的是 `"skip"`，这条路被关掉了。
8. **TZ 实测**（今晚新做，零风险）：
   - `qcom_scm_pas_supported(id)` 对 0–8、15 **全部返回 0**（连 modem/adsp 也是 0）
     → 这个 SCM 查询调用在本机 TZ 上**未实现**，返回全是假阴性；
   - 直接调 `qcom_scm_pas_init_image(15, ipa_fws.mdt, 7004, NULL)` → **ret = -22 (EINVAL)**；
   - `request_firmware("ipa_fws.mdt")` → **0（成功）**，说明固件**就在设备上**
     （`/lib/firmware/ipa_fws.mdt` + `b00..b07`）。
   → 结论：**TZ 不接受 IPA 的 PAS**，主线 `"self"` 加载路走不通，必须走手动加载。
9. **固件结构**（`ipa_fws.mdt` ELF32，8 个 program header）：

   | 段 | paddr | filesz | memsz |
   |---|---|---|---|
   | 代码 | 0x0 | 0xfe09 | 0xfe09 |
   | 数据 | 0x10000 | 0x1f20 | 0x31f20 |
   | | 0x42000 | 0x90 | 0x90 |
   | | 0x43000 | 0x88 | 0x88 |
   | | 0x44000 | 0x150 | 0x150 |
   | | 0x45000 | 0x1a28 | 0x2000 |

   这些是 **IPA 微控制器地址空间**的偏移，不是系统物理地址 → 手动加载必须
   “映射 IPA SRAM/UC 区 → 按 paddr 拷贝 → 启动 UC”。

## 2. 结论：4G 的阻塞点 = IPA 固件 bring-up，且它与 modem 强耦合

- IPA 是“有微控制器（UC）的子系统”，UC 固件不跑，core 寄存器窗口就不响应（这正是 stall 的原因）。
- 原厂手动加载路径 `ipa3_manual_load_ipa_fws` 之后还要 `ipa3_uc_init`（QMI/GLINK 与 modem 侧握手）——
  反汇编里能看到 `ipa3_uc_load`/`ipa3_uc_loaded` 以及向 modem 发送消息的调用。
- 这意味着：**IPA 不能脱离 modem 单独点亮**，而我们目前 modem 一直是“能注册射频但固件会崩”的状态。
  所以 4G 的路线必须是 **modem 稳定 → IPA 固件加载 → IPA 驱动 bring-up** 三步。

## 3. 下一步（工程化，按依赖顺序）

**P1. 先确认 modem 能稳定运行**（前置条件）
- 现状：`4080000.remoteproc` 状态 running，但历史上 modem 固件崩溃会带崩 WiFi，被手动 keep down。
- 需要：把 modem 完整启动（`qcom_q6v5_mss` + `modem.mdt`）并观察稳定性；这一条不解决，
  IPA 的 UC 握手无从谈起。

**P2. 实现 IPA 固件手动加载（照抄原厂逻辑，写成独立模块或在 ipa 驱动里）**
1. `request_firmware("ipa_fws.mdt")`（已确认可用）；
2. 解析 ELF，按 paddr 把段写进 **IPA UC SRAM 窗口**（需要先确定该窗口的映射：
   候选 `0x14787000`(可读)、`0x147ce000`(不可读，已废弃)、或 `ipa-shared` 保留区）；
3. 写 UC 启动寄存器（需从原厂 `ipa3_uc_init/ipa3_uc_start` 反汇编里取精确偏移与值）。

**P3. 再回到主线 IPA 驱动**
- 固件起来后，`ipa_config()` 读 VERSION 应能成功；之后才是真正的驱动 bring-up
  （endpoint/RT 表/GSI/QMI 与 modem 的 IPA 协议）。
- 注意：我们的 compatible 走的是 `ipa_data_v3_1`（msm8998 数据），
  sdm660 实际可能是 IPA 3.5.1，数据表/寄存器布局需要对齐（`ipa_data_v3_5_1` 已存在于该树）。

## 4. 已准备好的工具与脚本

| 文件 | 用途 |
|---|---|
| `tools/ipa_marker.c` | 打点模块；`stage=10/11` 查 PAS、`stage=12` 用真固件头做 `pas_init_image` |
| `tools/dtb_icc3_pack.py` | 给 IPA 节点加回三条 ICC 路径（memory/imem/config）并重打包 boot |
| `tools/dtb_fix_pack.py` | 修掉编造的第三段 reg、去掉 interconnects |
| `tools/ipa_fw_patch.py` | 给主线 `ipa_firmware_load` 加 `dma_alloc_coherent` 兜底 + 恢复 VERSION 读 |
| `tools/mdt_parse.py` | 解析 `ipa_fws.mdt` 的 program header |
| `tools/carve_elf.py` + VM `llvm-objdump` | 任意地址反汇编（见 57 号文档） |
| VM `/home/user/kbuild/.../ipa.ko` | 已编好：smp2p 跳过 + 固件 DMA 兜底 + VERSION 读 |

## 4.5 待解决的一个具体问题：UC 内存窗口在哪

- 对原厂内核做了 `movz #0x1478, lsl 16` 全量扫描 → **0 命中**：驱动没有硬编码 IPA 基址，
  它和主线一样从 DT 的 `reg` 取（`ipa-base` = `0x14780000`，size `0x4effc`）。
- 固件段地址（0x0 / 0x10000 / … / 0x45000）是 **UC 地址空间**的偏移，
  所以“UC 内存基址”决定了写到哪个物理地址：若基址 = `0x14780000`，段 0 就落在**那页死区**里；
  若基址 = `0x14780000 + 0x8000`，则覆盖 `0x14788000..0x147CE000`（正好避开头页、又用满窗口）。
- 这个基址必须从原厂 `ipa3_uc_init`/`ipa3_map_sram` 的 ioremap 参数里读出来，
  或者用一次“读 `0x14788000` 看是否可访问”的实验确认（有挂死风险，等有人值守再做）。

## 6. 事故记录：PAS 号暴力枚举把设备挂死（2026-10-31 01:00 前后）

为了确认 sdm660 的 IPA PAS id 不是 15，我写了 `stage=13`：对 10–20 逐个调用
`qcom_scm_pas_init_image(id, 固件头, 7004, NULL)`。结果设备在枚举过程中**直接挂死**
（SSH 失联，需要长按电源）。教训：

- `pas_init_image` 虽然是“只交给 TZ 校验”，但某个 id 可能让 TZ 进入异常状态；
- **这个实验不要重试**。重启后先读 p12 尾部（跑 `ipa_run.sh` 前的日志块），
  能看到 `fw ret=0` 之后停在哪个 `pasN ->`，即挂死的 id。

## 7. 明天（人起来后）的第一小时

1. **长按电源** → 起来后读打点：`dd if=/dev/mmcblk1p12 bs=512 skip=131056 count=2 | strings`
   —— 记录 stage 13 挂在哪个 PAS 号（写进本文件）。
2. 把 VM 上已编好的 `ipa_marker.ko`（含 `stage=14`）拷到平板，跑：
   ```
   sh /root/ipa_run.sh 14 0
   ```
   它会：`ioremap(0x14787000, 0x50000)` → 请求 `ipa_fws.mdt` 与 `ipa_fws.bNN` →
   按 ELF program header 把段写进 SRAM → 再读一次 VERSION。
   - 若 VERSION 有值 → UC 固件起效，**根因坐实**，继续 P3（驱动 bring-up）；
   - 若 VERSION 仍 stall → 说明还缺“UC 复位释放”这一步，需要从原厂
     `ipa3_uc_init` 反汇编里找它写的寄存器（或确认必须由 modem 侧完成）。
3. 备份现状：当前 boot 仍是修正 DT，stock ipa 停在 smp2p(-22)，开机安全。

## 9. 重要修正（10-31 凌晨，纯源码分析）

前面有几处推断需要修正，这些修正**降低了“整页已死”结论的可信度**：

1. **主线驱动根本不读 VERSION 寄存器**。版本来自 `ipa_data->version`（由 DT compatible 选表），
   `grep -rn VERSION drivers/net/ipa` 只命中数据表与版本比较，没有任何 `ioread32(... + VERSION)`。
   → 我们之前读 `0x14780034` 是“照 msm8998 猜的偏移”，**不是驱动行为**；
   IPA 寄存器页可能存在“孔洞”（未实现偏移），读孔洞同样会 stall。
   所以“整页不可访问”这个结论**只被 0x34 一个点支撑**，证据不足。
2. **版本对不上**：原厂 DT 是 `qcom,ipa-hw-ver = <6>`，downstream 枚举里 6 = **IPA v3.0**；
   而我们的 DT compatible 选的是 `ipa_data_v3_1`（msm8998）。两版寄存器偏移不同，
   驱动按 3.1 写 3.0 的硬件，**写到一个不存在的偏移就会 stall** ——
   这比“固件没加载”更能解释“驱动自己 probe 也挂”。
3. `ipa_hardware_config_clkon()`（`ipa_main.c:231`）里有 `if (version == IPA_VERSION_3_1)`
   分支，写 `CLKON_CFG`（关 MISC 时钟门控）——这是 v3.1 专有的写操作，
   若我们的硬件是 v3.0，这一笔很可能就是第一次 stall。

**因此下一步的第一优先级不是灌固件，而是先把寄存器页的“哪些偏移可读”测出来。**

## 10. 已备好的探测（`stage=16`，VM 上已编译通过）

```
sh /root/ipa_run.sh 16 0
```

依次读 `+0x0000 / 0x0004 / 0x0008 / 0x0034 / 0x0040 / 0x0100 / 0x1000 / 0x2000 / 0x3000 / 0x3800`，
**每次读之前先落盘一行 `R +0x.... read...`**，读完再落 `R +0x.... = 0x.... OK`。
断电后读 p12 就能知道：

- 第一个 `read...` 没有对应 `OK` 的那个偏移 = **第一个会 stall 的地址**；
- 若 `+0x0000` 就挂 → 整页确实不可访问（回到时钟/固件假设）；
- 若 `+0x0000` 能读、后面某处挂 → 是**孔洞**问题，说明页是活的，
  之前驱动 probe 的挂死只是写到了不存在的偏移 → 应改用 v3.0/3.5.1 的数据表重试。

## 12. 下一步的最优实验（已编译好，不需要刷机、不需要改 DT）

之前的 `pas_init_image(15)` 返回 -22 **很可能只是元数据不合法**：TZ 要求的是
`qcom_mdt_read_metadata()` 构造过的元数据（ELF 头 + program headers + hash 段），
我们传的是裸 `.mdt`。而 `qcom_mdt_load()` 是 `EXPORT_SYMBOL_GPL`，
可以在打点模块里直接调用，走完 **元数据构造 → init_image → mem_setup → 装载 → auth_and_reset**
整条 TZ 流程，**无需修改 DT、无需刷机**：

```
# 0) 确认工具链（qcom_mdt_loader 可能是模块）
modprobe qcom_mdt_loader
# 1) 只装载，不碰寄存器（零挂死风险）
sh /root/ipa_run.sh 17 0
# 2) 装载成功后再读 VERSION（有一点点风险）
sh /root/ipa_run.sh 18 0
```

- `stage=17` 只调用 `qcom_mdt_load(dev, fw, "ipa_fws.mdt", 15, virt, phys, size, NULL)`
  并打印返回值：**0 = TZ 接受、IPA 已认证并复位释放**；负值 = TZ 拒绝。
- `stage=18` 在装载成功后再读 `+0x34`：
  - 有值 → IPA 活了，根因彻底坐实；
  - 仍挂 → IPA 的复位/时钟不归 PAS 管，需要继续找（GCC/AOSS）。

模块已在 VM 上编译通过（325 KB，`/home/user/ipa_marker/ipa_marker.ko`），
含 stage 10–18 全部探测。

## 13. 一句话总结

> 不是时钟、不是 ICC、不是 DT 地址——**IPA 的微控制器固件从来没被加载过**；
> 这台设备的 TZ 又不给 IPA 走 PAS，所以只能手动灌固件，而且必须先让 modem 稳定下来。
> 这是“4G 能不能通”的真正分水岭，也是下一步唯一值得投入的方向。
