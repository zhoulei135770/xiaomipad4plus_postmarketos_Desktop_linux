# 60 — 修复 modem 崩溃循环（MSS memory banks 28 → 29）

> 10-31 上午。这是本次会话**唯一真正修好**的问题：modem 不再每 18 秒崩一次，
> WiFi 也不再被它带崩。

## 1. 现象（修复前）

```
[ 51.3] qcom-q6v5-mss 4080000.remoteproc: fatal error received:
        dog_hb.c:266:Task starvation: diag, ping: 4
[ 60.9] qcom-q6v5-mss 4080000.remoteproc: fatal error received:
        err_qdi.c:459:EX:wlan_process:1:WLAN RT:2080:PC=b00c7394
[ 60.9] ath10k_snoc 18800000.wifi: firmware crashed!
```

- 每 ~18 秒一轮：modem 崩 → 重启 mpss → 再崩；
- modem 崩时**连带把 WiFi 固件打崩**（`EX:wlan_process`），这就是“modem 一崩 WiFi 就没”的根因；
- `remoteproc0/state` 一直显示 running（崩溃后自动恢复），很容易被忽略。

## 2. 根因与修复

上游 2026-10-11 的补丁（作者 Alexey Minnekhanov，Konrad Dybcio / David Heidelberg
都给了 Reviewed-by）：

> **SDM660 的 MSS（QDSP6v62 1.5）有 29 个 memory bank，不是 28 个。**
> 少上一个 bank 会导致“有存储未上电”，进而引发不可预期的崩溃。

这正是 `qcom_q6v5_mss.c` 里 `q6v5proc_reset()` 的 L2 bank 上电循环：

```c
			} else {
				/* MSS_MSM8998, MSS_SDM660 */
				mem_pwr_ctl = QDSP6V6SS_MEM_PWR_CTL;
				i = 28;                    /* ← 错：SDM660 应为 29 */
				reverse = 0;
			}
```

改成：

```c
				/* SDM660 QDSP6v62 1.5 has one additional memory bank */
				i = qproc->version == MSS_SDM660 ? 29 : 28;
```

来源：<https://patchew.org/linux/20261011-sdm660-mss-banks-count-v1-1-f4eced49b509@minlexx.ru/>

## 3. 我们怎么部署的（可回滚）

`CONFIG_QCOM_Q6V5_MSS=m`，所以只重编一个模块即可，**不用动内核/DT**：

1. VM（`192.168.1.200`，树 `/home/user/kbuild/linux-7.0.14-sdm660`）上打补丁：
   `tools/mss_banks_patch.py`；
2. 编模块：
   ```
   make ARCH=arm64 LLVM=1 M=drivers/remoteproc KBUILD_MODPOST_WARN=1 modules
   ```
   （`KBUILD_MODPOST_WARN=1` 必须加，该树没有 Module.symvers）
3. 生成 `drivers/remoteproc/qcom_q6v5_mss.ko`（493 KB，vermagic `7.0.14-sdm660`）；
4. 平板上安装（`tools/mss_install.sh`）：
   - 备份原文件 → `/lib/modules/7.0.14-sdm660/kernel/drivers/remoteproc/qcom_q6v5_mss.ko.zst.bak-banks28`
   - 放入未压缩的 `qcom_q6v5_mss.ko`，删除原 `.ko.zst`，`depmod -a`
5. 重启生效。

**回滚**：把 `.bak-banks28` 改回 `qcom_q6v5_mss.ko.zst`、删掉未压缩的 `.ko`、`depmod -a`、重启。

## 4. 验证（修复后）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 首崩时间 | 51 秒 | — |
| 崩溃次数（5 分钟） | 5+ 次（每 18 秒） | **0** |
| modem 状态 | 反复崩溃/恢复 | 持续 `running` |
| WiFi | 被连带打崩 | 正常（ath10k 加载成功） |

实测 5 分钟无任何 `crash detected`，`dmesg` 里只有正常的
`MBA booted without debug policy, loading mpss`。

## 5. 对 4G 的意义

- 这是 4G 的必要前提（modem 必须先稳）。
- 但 **modem 稳定 ≠ IPA 可用**：修复后再次读 `0x14780034`（IPA VERSION）
  **仍然硬挂**，说明 IPA 的电源/复位/固件并没有被 modem 启动过程带起来。
- IPA 那部分仍未解决，见 58 号文档；目前看需要 IPA 驱动自身完成 bring-up，
  而它的第一条寄存器访问就会 stall，属于 mainline 上尚未支持的部分。
