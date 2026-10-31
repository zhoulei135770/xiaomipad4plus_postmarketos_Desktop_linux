# 55 — 4G/IPA 攻关记录与交接（2026-10-30 夜）

> 目标：让 LTE 数据工作。核心是 IPA 驱动。本文件记录**已排除的路线**和**下一次的确切起点**，
> 避免重复踩坑。

---

## 0. 当前设备状态

- 平板正常：zap boot、Wayland/LXQt 横屏、GPU（FD512）、触摸矩阵正常（锁定横屏）。
- IPA：stock 模块随系统加载，probe 安全失败在 `missing qcom,smem-state-names`（不挂死）。
- 回滚镜像：主机 `mipad4plus/backup/device-boot/boot-zap-2026-10-30.img`
  （fastboot 可刷回：`fastboot flash boot <img>`）。
- 设备 SSH：`192.168.1.100` user/<SUDO_PASSWORD>；VM：`192.168.1.200` user/<VM_PASSWORD>。
- 代理：`192.168.1.151:16514`（VM 上 `curl -x http://192.168.1.151:16514 ...` 可访问 GitHub）。

## 1. 已完成的 IPA 侧工作

### 1.1 DTB 修正（已刷入过，可重做）
- 原厂 IPA 的 SRAM 窗口 = `0x14780000 + 0x7000 = 0x14787000`；
- IPA 节点需要：`reg` 第三段 `0x14787000 0x2000`、`interconnects`（memory/imem/config）、
  `snoc_icc` 标签；
- 修正后 live DT 验证：`00007814 fcef0400 00407814 34690200 00707814 00200000`；
- stock 驱动仍失败在 smem states（预期）。

### 1.2 补丁模块（跳过 smem/smp2p、只读 VERSION）
- 源码补丁在平板 `/root/kbuild/linux-7.0.14-sdm660/drivers/net/ipa/`：
  - `ipa_main.c` 的 `ipa_config()` 已被改成只做：
    ```c
    val = ioread32(ipa->reg_virt + 0x34);  // VERSION
    ```
  - `ipa_power.c` 加了 `IPA-STEP` 打点（icc_enable/clk_enable）；
- 模块 `ipa.ko` 可编译成有效 ELF；
- **加载即硬挂死**（修正 SRAM 后仍然），位置在 `ipa_config()` 的第一条寄存器读之前/之中；
- 结论：**时钟/ICC/电源域没有真正打开**，或该寄存器的 APB 访问会挂死总线。

## 2. 已排除的路线（不要再做）

| 路线 | 结果 |
|---|---|
| 重编内核加 `CONFIG_NETCONSOLE=y`（平板树，clang 23） | 黑屏，无任何内核输出 |
| 重编内核加 netconsole（VM 真源码，clang 18，pmaports 配置） | 同样黑屏 |
| 用 pmaports 权威配置重新编译 | 配置与运行内核 **diff=0**，仍黑屏 |
| USB 当串口（gadget ACM） | 不可行：USB 口固定 host 模式，无 UDC（`/sys/class/udc` 空，debugfs mode 写不进去）|
| 官方 clover DTB 找 IPA 节点 | 官方 DTB **没有 IPA 节点**（mainline 未定义）|
| pstore/ramoops | 内核未配 ramoops，硬挂死也不会留记录 |
| iio/日志等 | 与 IPA 无关 |

**结论：重编内核这条路被“黑屏原因未知”堵死**，除非找到原内核的构建/打包差异。

## 3. 可行且已验证一半的方案：p12 尾部打点

### 3.1 已验证
- p12 是 boot 分区，大小 64MB；镜像只占约 25.5MB；
- 尾部空闲区（偏移 `67100672`，即 512 字节块 `131056`）：
  ```
  echo "MARKER-TEST-12345" | dd of=/dev/mmcblk1p12 bs=512 seek=131056 conv=fsync
  dd if=/dev/mmcblk1p12 bs=512 skip=131056 count=1 | strings
  ```
  **能写能读**（已验证）。

### 3.2 未完成
- 内核模块里往块设备写标记还没成功：
  - `kernel_write` 对块设备（4 字节 buffer）静默失败；
  - `blkdev_get_by_path`/`bdev_open_by_path`/`bdev_handle` 在 7.0.14 的 API 对不上（编译不过）；
  - `call_usermodehelper` 版本写了但**没有验证成功**（最后一次 insmod 被中断，p12 尾部读不到标记）。

### 3.3 下次的第一步（务必按顺序）
1. 写**最小模块**：只调用 `mark("TEST-OK")` 然后返回，**不碰 IPA**；
2. 用 `filp_open("/dev/mmcblk1p12", O_RDWR|O_LARGEFILE)` + `kernel_write`
   **带 512 字节对齐 buffer/offset**，并检查返回值写 dmesg；
   若仍失败，改用 `call_usermodehelper("/bin/sh","-c","printf ... | dd ...")`；
3. `insmod` 后立刻用户态读回 p12 尾部，确认读到 `TEST-OK`；
4. 通道确认后，逐步加：
   - `M1 dev found`（`bus_find_device_by_name(&platform_bus_type,NULL,"14780000.qcom,ipa")`）
   - `M2 clk_get ok`（`clk_get(dev,"core")`）
   - `M3 clk_enable ok`（`clk_prepare_enable`）
   - `M4 ioremap ok`（`ioremap(0x14780000,0x1000)`）
   - `M5 version 0x%08x`（`readl(base+0x34)`）
5. 挂死后长按电源重启，读 p12 尾部即可定位卡点；
6. 根据卡点决定：补 power-domain/ICC（DT 或驱动），或确认 IPA 总线不可达。

## 4. 关键文件/命令速查

- 平板内核树：`/root/kbuild/linux-7.0.14-sdm660`（可用 `make LLVM=1 modules_prepare` 后编模块）
- 打点模块源码：`mipad4plus/tools/ipa_marker.c`（当前版本是 call_usermodehelper 写法，未验证）
- 打包脚本：`mipad4plus/tools/build_final.py`（原始 Image + 修正 DTB + zap ramdisk）
- 模块编译：
  ```
  make LLVM=1 M=/root/ipa_marker KBUILD_MODPOST_WARN=1 modules
  insmod /root/ipa_marker/ipa_marker.ko
  ```
- 读标记：
  ```
  dd if=/dev/mmcblk1p12 bs=512 skip=131056 count=1 2>/dev/null | strings
  ```
- fastboot 回滚（主机 Windows）：
  ```
  fastboot flash boot <boot-zap-2026-10-30.img>
  fastboot reboot
  ```

## 5. 下一会话开场白

> “继续 IPA 打点：先做最小模块验证 p12 尾部写入，再逐步加 M1–M5。”
