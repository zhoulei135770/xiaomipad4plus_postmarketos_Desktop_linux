# 62 — 内核侧尝试（SCM 解锁）与"自编内核不可启动"的结论

> 10-31 上午。用户选择继续攻 IPA，本文件记录内核实改尝试、隔离实验与最终结论。

## 1. 起因：找到 IPA 真正的锁

反汇编原厂 `ipa3_tz_unlock_reg`（`0xffff800010e15740` 附近）得到：

```
svc   = 0x0C          (SCM_SVC_MP，内存保护服务；主线 QCOM_SCM_SVC_MP 也是 0x0c)
cmd   = 0x10          (解锁命令)
args  = {u64 描述符表物理地址, u32 长度}
描述符 = 28 字节/条：{页对齐地址, 页对齐地址, 长度, 0x00C00311}
失败日志："scm call SCM_SVC_MP failed: %d"
```

→ **IPA 寄存器块由 TZ 的 XPU 保护，必须由 TZ 显式解锁**。这解释了为什么
把时钟、三条 ICC、modem 全部就位后，读 `0x14780034` 仍然 stall（不是没响应，是被拦住）。

## 2. 做了什么

1. 给主线 `qcom_scm.c` 增加 `qcom_scm_mp_unlock(phys, len)`（svc 0x0C / cmd 0x10，
   三个 32 位参数 `{phys_lo, phys_hi, len}`），并导出；
2. 写了 `stage=24`：用 `dma_alloc_coherent` 构造 28 字节描述符（IPA 寄存器窗
   `0x14780000/0x4effc`，flags `0x00C00311`），调用解锁，然后读 VERSION；
3. 在 VM 上完整编译内核（clang 18，`make ARCH=arm64 LLVM=1 Image`，成功，32.96 MB）；
4. 把 `Image.gz`（13.07 MB）与现有 DTB、ramdisk 重新打包成 boot 镜像并刷入。

## 3. 结果：新内核起不来（两次）

| 尝试 | 结果 |
|---|---|
| 带 SCM 补丁的内核 | 黑屏，SSH 不通 → fastboot 刷回备份恢复 |
| **撤掉补丁重编**（隔离实验） | **同样黑屏** → 说明不是补丁的问题 |

恢复手段（两次都成功）：
```
fastboot flash boot backup/device-boot/boot-icc3-2026-10-31.img
fastboot reboot
```
恢复后 modem 仍然 0 崩溃（29-bank 修复不受影响）。

## 4. 已排除的原因

| 检查 | 结果 |
|---|---|
| ARM64 Image 头 | 老内核与新内核一致：`text_offset=0`、`flags=0xa`、同一入口指令 |
| 内核 config | 与运行内核仅差编译器版本（clang 23 vs 18）和 3 个摄像头选项，无功能差异 |
| boot 镜像布局 | kernel(gz)+dtb 拼接、ramdisk 分页对齐——与之前成功刷 DT 的布局相同 |
| 补丁影响 | 不带补丁同样黑屏 |

## 5. 结论

**这棵源码树编出来的内核在这台机器上不能启动**，原因是它缺少 pmOS 官方打包
（`linux-postmarketos-qcom-sdm660` 包，`#254-postmarketos-qcom-sdm660`，10-28 构建）
所使用的补丁或构建条件。

### 5.1 补充实验（两种编译器都不行）

| 编译器 | Image 大小 | 结果 |
|---|---|---|
| clang 18 (LLVM=1) | 32.96 MB | 黑屏 |
| clang 18，撤掉 SCM 补丁 | 32.97 MB | 黑屏（对照组） |
| **aarch64-gcc 11.4** | **37.06 MB** | 黑屏 |

### 5.2 与上游 tag 的核对

- `sdm660-mainline/linux` 确有 **`v7.0.14-sdm660`** tag，`Makefile` 版本与本树一致；
- 该 tag 的 `qcom_q6v5_mss.c` 仍是 `i = 28`（说明我们补的 29-bank 是上游尚未合并的新改动）；
- 也就是说：**版本号相同，但设备上的 `#254` 内核带有本树没有的补丁/构建条件**，
  因此用它编出来的内核无法启动。

→ 要在内核侧做任何改动（包括 SCM 解锁），必须先拿到**该发行版（"Nura edge" /
postmarketOS 打包）实际使用的那套源码与构建配方**。

1. 向发行版/打包者索取内核源码树（含其补丁）与 config；
2. 或用 `pmbootstrap` + pmaports 对应分支完整重建（本机是 7.0.14，pmaports master 仍为 6.11.1，
   需要确认用的是哪个分支/仓库）；
3. 确认能启动后，再把 `qcom_scm_mp_unlock()` 与 `stage=24` 加进去。

## 6. 设备当前状态

- boot 已回滚到 `backup/device-boot/boot-icc3-2026-10-31.img`（可启动）；
- modem 29-bank 修复仍在生效（0 崩溃）；
- DT 仍带三条 ICC 路径（无害）；
- 所有内核实验产物只留在主机/VM，未写入设备。
