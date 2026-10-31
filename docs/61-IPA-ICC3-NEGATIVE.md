# 61 — A 方案结论：三条 ICC 路径都投了，IPA 页仍不可达

> 10-31 上午。用户选择“继续攻 IPA”，本文件记录这次尝试的完整过程与结论：
> **A 方案已试到底，失败；且失败原因不在时钟/ICC/DT。**

## 1. 这次做了什么（可复现）

1. **改 DT**：给 IPA 节点补上原厂同款三条 interconnect 路径（用 `tools/dtb_icc3_pack.py`）：
   ```
   interconnects = <&a2noc MASTER_IPA &snoc SLAVE_IPA>,     /* memory  0 -> 10 */
                   <&a2noc MASTER_IPA &snoc SLAVE_IMEM>,    /* imem    0 -> 13 */
                   <&a2noc MASTER_IPA &cnoc SLAVE_SNOC_CFG>;/* config  0 -> 16 */
   interconnect-names = "memory", "imem", "config";
   ```
   打包成 `/tmp/boot-icc3.img`（24.3 MiB）写入 p12，重启。
   现场核对：`/proc/device-tree/.../interconnects` 三条都在，names 为 `memoryimemconfig`。

2. **驱动侧**：开机时主线 IPA 驱动跑到了 `ipa_power_init`，已经把这三种节点投到 INT_MAX：
   ```
   mas_ipa 2147483647 / slv_ipa 2147483647 / slv_imem 2147483647 / slv_snoc_cfg 2147483647
   ```
   然后它仍卡在 `ipa_smp2p_init`（我们树里已改成跳过；stock 模块缺 DT 属性返回 -22）。

3. **模块侧**（`stage=22`）：对 `memory`/`imem`/`config` 三个名字显式投票，全部成功：
   ```
   icc memory bw ret=0
   icc imem   bw ret=0
   icc config bw ret=0
   reading VERSION after 3-path vote (may hang)
   ```
   随后**硬挂**（这次内核 panic 自动重启，省了长按）。

## 2. 结论

在以下条件**同时满足**的情况下：

- modem 已稳定运行（29-bank 修复后 0 崩溃）；
- IPA 的两个 rpmcc 时钟使能；
- 三条 ICC 路径全部投票成功（与厂商 DT 完全一致）；
- IPA 固件在 `/lib/firmware` 就位；

**读 `0x14780034`（VERSION）依然立刻 stall。** 这不是“少投了票”“少开了时钟”“DT 写错了”能解释的。

最可能的原因（按可能性排序）：

1. **XPU/TZ 保护**：IPA 寄存器块对 APPS 的访问被 TZ 配置成“挂起”而非报错。
   原厂 Android 上，APPS 的 IPA 访问是 TZ 通过 PAS/QMI 配置后才放行的；主线没有这套配置，
   所以任何 AP 访问都会永远等不到响应。
2. **电源域未开**：IPA 可能挂在一个只有 TZ/AOP 能开的域上（主线 sdm660 既没有 IPA GDSC，
   也没有 IPA 的 GCC 时钟——已用字符串搜索确认 vendor 内核里同样没有 `gcc_ipa_clk`）。
3. IPA 由 modem 侧固件独占（modem.b18 里确实含 `IPA_0_IPA_UC`、`IPA_0_IPA_WRAPPER` 等 XPU 域名），
   APPS 只是“协处理器”，必须等 modem 完成 IPA 初始化并授权。

## 3. 要继续需要什么

- 逆向原厂 TZ 侧的 IPA 初始化（`qseecom`/SCM 调用序列），或者找到 sdm660 IPA 的 XPU 配置协议——**工程量很大且没有公开资料**；
- 或者等上游有人给 mainline 补 sdm660 IPA 支持（目前 mainline 只有 msm8998/sdm845 等）。

## 4. 设备当前状态与回滚

- **DT**：现在带 3 条 ICC 路径（无害，且更接近原厂；驱动仍停在 smp2p 报错，不碰寄存器）。
- **boot 备份**（主机）：`backup/device-boot/boot-icc3-2026-10-31.img`
  （64 MiB，sha256 `83b0b2a70d77eeba94e8cf41f01614dd94db086d3ea507b9e39daec83a59c0ac`）。
- **想回到“无 interconnects”的旧 DT**：在设备上跑 `tools/dtb_fix_pack.py` 生成 `/tmp/boot-fix.img`，
  `dd` 到 `/dev/mmcblk1p12` 后重启即可。
- **modem 修复**（60 号）不受影响，继续生效。
