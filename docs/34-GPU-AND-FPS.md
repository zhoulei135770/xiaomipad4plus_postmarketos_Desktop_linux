# 帧率与 GPU：为什么桌面只有 1.8 FPS

> 2026-10-29 10:10。用户要求"帧率！"。以下是完整测量、根因和已做的尝试。

---

## 1. 实测数字

| 场景 | glxgears (1200×900) |
|---|---|
| 合成器 **开** + vsync | **1.88 / 1.75 FPS** |
| 合成器 **关** | **1.48 FPS** |

渲染器：

```
Device: llvmpipe (LLVM 23.1.3, 128 bits)
Accelerated: no
OpenGL renderer string: llvmpipe (LLVM 23.1.3, 128 bits)
```

**桌面是纯软件渲染（llvmpipe），Adreno 512 完全没参与。**

⇒ 帧率问题的根因不是合成器，不是桌面设置，而是 **GPU 没起来**。

**结论：合成器保持开启**（1.88 > 1.48，有 vsync 反而更顺）。

---

## 2. 根因链

```
[    3.77] adreno 5000000.gpu: GPU speedbin fuse 135 ...
[    3.92] adreno 5000000.gpu: *ERROR* Unable to load a512_zap.mdt
[    3.92] msm_dpu: *ERROR* gpu hw init failed: -2      ← ENOENT
```

GPU 需要 **ZAP 安全固件**（`qcom/a512_zap.mdt` + `.b00/.b01/.b02`）才能初始化。

而 `firmware-qcom-adreno-a530` 包**只装了 pm4/pfp/gpmu，没有 ZAP 着色器**
（a530 是 SDM845 的 GPU；本机是 Adreno **512**）。

### 为什么装上文件还是失败

| 事实 | 后果 |
|---|---|
| 内核固件搜索路径被覆盖为 `/run/msm-firmware-loader/target` | 放 `/lib/firmware` 无效 |
| 该目录由 `msm-firmware-loader.service` 在**开机 3-20 秒**间建立 | 与 GPU 探测（3.9 秒）**抢时间** |
| `msm.ko` 在 **initramfs** 里（25 个模块之一） | 根文件的 modprobe 黑名单管不到 |

---

## 3. 已经试过的（都没成）

| 尝试 | 结果 |
|---|---|
| 从 modem 分区复制 a512_zap.* 到 `/lib/firmware/qcom/` | ❌ 路径被覆盖，看不到 |
| 复制到 `/lib/firmware/`、`updates/`、`target/qcom/` | ❌ 同上 |
| 给加载器加 systemd drop-in（`ExecStartPost`） | ❌ 太晚（脚本跑完才执行） |
| `blacklist msm` + 延迟加载服务 | ❌ 模块在 initramfs 里，黑名单无效 |
| 运行时 `modprobe -r msm` | ❌ 被 DRM fbdev 占住，无法卸载 |
| **把固件塞进 initramfs 并重刷 boot.img** | ❌ 仍然 3.9 秒失败 |
| 在加载器脚本里、设路径**之前**建符号链接 | ⏳ 补丁已打，**尚未重启验证** |

**最新一次修复（已落盘，未验证）**：`/usr/sbin/msm-firmware-loader.sh`
在设置 `firmware_class.path` 之前，把
`/lib/firmware/qcom/a512_zap.*` 链接进 `target/qcom/`（备份为 `.orig-gpu`）。

---

## 4. 下一步建议（按可行性排序）

1. **重启验证第 3 节的补丁**（最快，已就位）
2. 如果还不行，怀疑 **ZAP 文件格式**：主线可能期待 `.mbn`（ELF 单文件）
   而不是 Android 的 `.mdt`+`.bNN` 分片。可试：
   - 把 `a512_zap.mdt` 直接命名成 `a512_zap.mbn`
   - 或用 `qcom-mdt` 工具把分片合成单文件
3. 终极方案：从 linux-firmware 拿 **a530_zap.mbn**（同为 a5xx 家族，
   本机 pm4/pfp 已经在用 a530 的文件，说明驱动把它当 a5xx 族）

---

## 5. 顺带发现：WiFi 固件在崩溃循环

本次启动 **5 次** `ath10k firmware crashed!`，伴随大量

```
failed to create WMI vdev 0: -108   (ESHUTDOWN)
failed to setup powersave: -108
```

**这才是 WiFi 反复掉线的真因**，`wifi-watchdog` 只是在掩盖症状。

---

## 6. 已做的系统改动清单

| 文件 | 作用 | 撤销 |
|---|---|---|
| `/etc/modprobe.d/msm-wait-for-firmware.conf` | 黑名单（无效，可删） | `rm` |
| `/usr/local/bin/msm-load-after-fw.sh` + unit | 延迟加载 msm | `sh pad_install_msm_order.sh --undo` |
| `/usr/local/bin/gpu-zap-fix.sh` + drop-in | 加载器后补链接 | 删文件 |
| `/usr/sbin/msm-firmware-loader.sh` 补丁 | **关键补丁**（未验证） | `cp .orig-gpu` 回去 |
| `/lib/firmware/qcom/a512_zap.*` | 固件副本 | `rm` |
| `/root/boot-rollback.img` | **回滚镜像**（md5 `c69516c8`） | `dd` 回 mmcblk1p12 |
| 当前 boot.img | 含 ZAP 固件的 initramfs（md5 `0626615d`） | 同上 |

回滚一条命令：

```sh
dd if=/root/boot-rollback.img of=/dev/mmcblk1p12 bs=1M
```

---

## 7. 2026-10-29 10:40 追加：**真正的 bug 找到了**（反编译内核驱动得出）

### 7.1 从内核源码看到的真相

在 VM 的内核树里读 `drivers/gpu/drm/msm/adreno/adreno_gpu.c`：

```c
np = of_get_child_by_name(dev->of_node, "zap-shader");
of_property_read_string_index(np, "firmware-name", 0, &signed_fwname);
if (signed_fwname) {
        fwname = signed_fwname;
        ret = request_firmware_direct(&fw, fwname, gpu->dev->dev);   /* ← 直接按名字找 */
} else if (fwname) {
        fw = adreno_request_fw(...);   /* 先试 qcom/<name> 再试裸名 */
}
if (IS_ERR(fw))
        DRM_DEV_ERROR(dev, "Unable to load %s\n", fwname);
```

而我们的 DTB 里：

```dts
zap-shader {
        memory-region = <0x35>;
        firmware-name = "a512_zap.mdt";     ← 没有 qcom/ 前缀！
};
```

⇒ 内核找的是 **`/lib/firmware/a512_zap.mdt`**，不是 `qcom/a512_zap.mdt`。

### 7.2 我犯的错

重刷的 initramfs 里，我只把固件放进了：

```
/usr/lib/firmware/qcom/a512_zap.mdt      ← 多了一层 qcom/
```

而正确位置是：

```
/usr/lib/firmware/a512_zap.mdt           ← 这一层才对
```

root 文件系统里我当时"散弹式"复制了两个位置都有，所以 root 侧没问题；
**但 GPU 是在 initramfs 阶段探测的（msm.ko 就在 initramfs 里）**，
那时只能看到 initramfs 里那份 —— 只有 `qcom/` 子目录那份，所以 `-ENOENT`。

### 7.3 修正后的构建脚本

`scripts/pad_build_gpu_boot2.sh`：

- 解开当前 boot.img
- 把 a512_zap.* 放进 **`usr/lib/firmware/`（根）** 和 `usr/lib/firmware/qcom/`（两处都放）
- 用同样的 zstd+cpio 重打包
- 校验：ramdisk 里 zap 条目数、DTB 仍在 kernel 内

### 7.4 这次为什么有把握

| 证据 | 结论 |
|---|---|
| 驱动源码明确用 `firmware-name` 属性、无前缀 | 路径必须是 `/lib/firmware/a512_zap.mdt` |
| 我们的 DTB 里确实是 `a512_zap.mdt` | 与源码吻合 |
| msm.ko 在 initramfs 里（25 个模块之一） | 探测发生在 initramfs 阶段 |
| initramfs 里 `/lib` 是指向 `usr/lib` 的符号链接 | 落点要写 `usr/lib/firmware/` |
| 上次只放了 `qcom/` 子目录 | 完全解释 `-ENOENT` |

### 7.5 晚上回来后执行顺序

```sh
# 1. 先恢复被我改坏的加载器（如果平板能进系统）
sudo cp /usr/sbin/msm-firmware-loader.sh.orig-gpu /usr/sbin/msm-firmware-loader.sh
sudo rm -f /etc/modprobe.d/msm-wait-for-firmware.conf
sudo systemctl disable msm-load-after-fw.service

# 2. 用修正脚本重新构建
sudo sh pad_build_gpu_boot2.sh

# 3. 校验无误后刷入（脚本会保留 /root/boot-rollback.img）
sudo sh pad_flash_gpu_boot2.sh

# 4. 重启，然后看
dmesg | grep -iE 'adreno|zap'
ls /dev/dri/
glxinfo -B | grep -E 'Device|Accelerated'
```

---

## 8. 10:55 追加：段文件命名也验证了

`drivers/soc/qcom/mdt_loader.c`：

```c
char *seg_name = kstrdup(fw_name, GFP_KERNEL);
sprintf(seg_name + strlen(fw_name) - 3, "b%02d", segment);
ret = request_firmware_into_buf(&seg_fw, seg_name, dev, ptr, phdr->p_filesz);
```

`"a512_zap.mdt"` 末 3 字符被替换成 `b00`：

```
a512_zap.mdt  →  a512_zap.b00 / .b01 / .b02
```

**同样是裸名**（没有 `qcom/` 前缀）。

⇒ 所以 `.mdt` 和 `.b0N` 必须全部位于 **`/lib/firmware/` 根目录**。
修正后的构建脚本正是这么放的（根 + `qcom/` 两处都有，兼容两种查找风格）。

### 格式检查（`mdt_header_valid`）

```c
if (memcmp(ehdr->e_ident, ELFMAG, SELFMAG)) return false;
if (ehdr->e_phentsize != sizeof(struct elf32_phdr)) return false;
```

厂商的 `a512_zap.mdt`（6684 字节）是标准 ELF32，满足要求。
`mdt_phdr_loadable()` 会跳过 `QCOM_MDT_TYPE_HASH` 段，厂商固件里的 hash 段会被正确忽略。

**结论：整条链路（DT 属性 → 请求名 → 段名 → ELF 解析）全部对得上，
只要文件在 `/lib/firmware/` 根目录，GPU 就应该初始化成功。**

---

## 9. 修复置信度评估

| 环节 | 依据 | 置信度 |
|---|---|---|
| DT 用 `firmware-name = "a512_zap.mdt"` | 解出的 dtb 原文 | 已确认 |
| 驱动因此调 `request_firmware_direct("a512_zap.mdt")` | 内核源码 | 已确认 |
| 段名由 `.mdt` 末 3 字符替换为 `b00` | 内核源码 | 已确认 |
| msm 在 initramfs 阶段探测 | msm.ko 在 initramfs 内 | 已确认 |
| 上次只放到 `qcom/` 子目录 | 构建脚本记录 | 已确认 |
| **把固件放到根目录即可解决** | 以上四条 | **高** |

唯一还不确定的是：GPU 初始化成功之后，Xorg 是否会正确切到 freedreno。
如果仍是 llvmpipe，用 `patches/install-xorg-gpu.sh` 显式指定 glamor。

---

## 10. 11:00 追加：DP 时钟那条**不成立**（自我纠正）

我一度以为 GPU 节点缺 `core` 时钟。用 `tools/gpu_clocks_decode.py` 完整解码后：

```
clock-names 原始: [iface, rbbmtimer, mem, mem_iface, rbcpr, core]     ← 6 个都在
clocks 6 对:
  <&gcc 55>   GCC_GPU_CFG_AHB_CLK     (iface)
  <&gpucc 8>  GPUCC_RBBMTIMER_CLK     (rbbmtimer)
  <&gcc 22>   GCC_BIMC_GFX_CLK        (mem)
  <&gcc 54>   GCC_GPU_BIMC_GFX_CLK    (mem_iface)
  <&gpucc 6>  GPUCC_RBCPR_CLK         (rbcpr)
  <&gpucc 7>  GPUCC_GFX3D_CLK         (core)
```

**与主线 sdm630（同为 a5xx）逐项一致。** 之前说"只有一个 iface"是我打印时截断了时钟名。

其它资源也齐：

| 资源 | 状态 |
|---|---|
| power-domains | ✅ |
| iommus | ✅ |
| interconnects | ✅ `<&bimc …>` |
| operating-points-v2 + opp-table | ✅ |
| nvmem speed_bin | ✅ |
| vdd / vddcx | ❌ 缺（dummy regulator）—— 但 sdm630 参考也没写，gpu 供电常开 |

⇒ **DT 侧没有坑了，唯一的问题就是 ZAP 固件路径。**

---

## 11. WiFi 崩溃循环的排查（附带结论）

`ath10k_snoc 18800000.wifi: firmware crashed!` 每次启动 5+ 次。

查 DT：供电**齐全**

```
vdd-0.8-cx-mx -> l5
vdd-1.8-xo    -> l9
vdd-1.3-rfa   -> l6
vdd-3.3-ch0   -> l19
vdd-3.3-ch1   -> 缺（该机型只用了 ch0，可选）
```

⇒ 不是 DT 配错。更像**固件版本 / 驱动时序**问题（`-108 ESHUTDOWN` 表示 FW 已死）。
这条暂时记为"待办"，不影响 GPU。

---

## 12. 交付：一条命令修 GPU

`scripts/pad_gpu_fix_all.sh`：

```sh
sudo sh pad_gpu_fix_all.sh --build   # 只构建 + 校验
sudo sh pad_gpu_fix_all.sh           # 构建 + 刷入 + 重启
```

它包含：

1. **预检**：校验 `a512_zap.mdt` 是合法 ELF32、phdr 大小 32、打印每个段
2. 还原我之前改坏的加载器补丁
3. 解包 boot.img → 解包 initramfs
4. 把固件放到 `usr/lib/firmware/`（根）**和** `qcom/`
5. 重打包 → 校验 ramdisk 里三个关键路径都存在
6. 备份回滚镜像 → 刷入 → 回读校验 → 重启

---

## 13. 11:20 追加：**最优解找到了——把 zap-shader 节点删掉**

### 13.1 关键代码

`drivers/gpu/drm/msm/adreno/a5xx_gpu.c`（hw_init 末尾）：

```c
ret = a5xx_zap_shader_init(gpu);
if (!ret) {
        /* ZAP 加载成功 → 用 CP 切出安全模式 */
        OUT_PKT7(gpu->rb[0], CP_SET_SECURE_MODE, 1);
        ...
} else if (ret == -ENODEV) {
        /* 设备不使用 zap shader */
        dev_warn_once(gpu->dev->dev,
                "Zap shader not enabled - using SECVID_TRUST_CNTL instead\n");
        gpu_write(gpu, REG_A5XX_RBBM_SECVID_TRUST_CNTL, 0x0);
} else {
        return ret;          /* ← 我们踩的这条：-ENOENT，致命 */
}
```

`adreno_zap_shader_load()`：

```c
if (!zap_available)                 return -ENODEV;
np = of_get_child_by_name(dev->of_node, "zap-shader");
if (!of_device_is_available(np)) { zap_available = false; return -ENODEV; }
...
if (IS_ERR(fw)) { "Unable to load %s" ; return PTR_ERR(fw); }   /* -ENOENT */
```

### 13.2 两条路的区别

| DT 状态 | 驱动返回 | 结果 |
|---|---|---|
| **没有** `zap-shader` 节点 | `-ENODEV` | 打一行警告，写 `SECVID_TRUST_CNTL=0`，**GPU 正常工作** |
| 有节点但固件读不到 | `-ENOENT` | **致命，GPU 放弃初始化** |

我们的 DT（`backup/device-boot/sdm660-xiaomi-clover-plus.dtb` 第 1623 行）：

```dts
zap-shader {
        memory-region = <0x35>;
        firmware-name = "a512_zap.mdt";
};
```

⇒ 走的是**致命**那条。

而主线 `sdm630.dtsi` / `sdm660.dtsi` **根本没有 zap-shader 节点**——说明这颗 SoC 在
解锁设备上本来就该走 `-ENODEV` → `SECVID_TRUST_CNTL` 这条路。

### 13.3 附带发现的第二个坑

`zap-shader { memory-region = <0x35> }` 指向的保留区只有 **8 KB**：

```
/reserved-memory/gpu@f0b00000   0xf0b00000 + 0x2000   (shared-dma-pool, no-map)
主线 sdm630 参考              : 20 MB
```

就算固件加载成功，驱动还会因为 `mem_size > resource_size` 报
`memory region is too small to load the MDT`（`-E2BIG`）。

⇒ **两条独立证据都说明：删掉这个节点才是正解。**

### 13.4 离线演练（已在 VM 上跑通）

```
pad.dts: 88422 字节
已删除 zap-shader 节点（88 字节）
  compatible = "qcom,adreno-512.0\0qcom,adreno";
  status = "okay";
  operating-points-v2 = <0x34>;
  zap-shader: (已删除)
pad2.dtb: 66016 字节（原 66080）
zap-shader 出现次数: 0
```

### 13.5 交付脚本

`scripts/pad_fix_gpu_nozap.sh`（**只用 DTB，不动 initramfs**，风险最低）：

```sh
sudo sh pad_fix_gpu_nozap.sh --build   # 构建 + 校验
sudo sh pad_fix_gpu_nozap.sh           # 刷入 + 重启
```

流程：解出 DTB → dtc 反编译 → 删 `zap-shader` → 重编译 → 校验
（节点消失、DTB 可解析、kernel 字节不变）→ 备份回滚镜像 → 刷入 → 回读校验。

### 13.6 为什么这个方案更安全

| 方案 | 改动面 | 风险 |
|---|---|---|
| 塞固件进 initramfs | boot.img 的 ramdisk | 中（已试，路径踩坑） |
| **删 zap-shader 节点** | **只有 DTB** | **低**（我们做过很多次 DTB 替换） |

最坏情况：GPU 仍然起不来（`SECVID_TRUST_CNTL` 被安全策略挡住 → "crash horribly"），
但**桌面显示不受影响**（那是 DPU，与 GPU 无关），立刻能刷回 `/root/boot-rollback.img`。

---

## 14. ✅ 2026-10-29 11:07 — **GPU 成功启用，1.8 → 57.8 FPS**

### 14.1 最终实测

```
Device: FD512 (Freedreno Adreno 512)
Accelerated: yes
OpenGL version string: 3.1 Mesa 26.2.5

glxgears 1200x900  : 54.6 FPS     （之前 1.88）
glxgears 1920x1200 : 57.8 FPS     （之前 —— 全屏软件渲染基本卡死）
GPU 当前频率       : 588 MHz（最高档）
```

**提升约 30 倍，全屏已达到 60Hz 上限。**

### 14.2 真正起作用的组合（三个条件缺一不可）

| # | 改动 | 作用 |
|---|---|---|
| 1 | **ZAP 固件放在 initramfs 的 `/lib/firmware/a512_zap.mdt`**（+ `.b00/.b01/.b02`） | 驱动不再 `-ENOENT` |
| 2 | **把 zap 保留区从 8 KB 扩到 20 MB**（`/reserved-memory/gpu@f0b00000`） | 否则 `-E2BIG` |
| 3 | **`/etc/X11/xorg.conf.d/20-gpu.conf` 显式启用 glamor + DRI3** | Xorg 否则 `AIGLX: Screen 0 is not DRI2 capable` → 退回 swrast |

第 3 条最容易漏：GPU 起来了、`/dev/dri` 也有了，但 Xorg 仍报 llvmpipe，
日志里就是那句 `AIGLX: Screen 0 is not DRI2 capable`。

### 14.3 曾经失败的两条路（记录以免重走）

| 尝试 | 结果 |
|---|---|
| 删掉 `zap-shader` 节点（走 `-ENODEV` + SECVID_TRUST_CNTL） | **黑屏**——正是内核注释警告的 "crash horribly"，需 fastboot 救回 |
| 固件只放在 `/lib/firmware/qcom/` | `-ENOENT`（DT 的 `firmware-name` 没有 `qcom/` 前缀） |

### 14.4 当前生效的文件

```
boot 分区            : 含 ZAP 固件的 initramfs + 20MB zap 保留区的 DTB
/lib/firmware/a512_zap.*           （root 目录，initramfs 里也有一份）
/etc/X11/xorg.conf.d/20-gpu.conf   （glamor + DRI3）
回滚镜像             : /root/boot-rollback.img
```

### 14.5 ⚠️ 注意事项

- pmOS 的 boot-deploy 在**内核更新时**会重新生成 `boot.img`，
  届时需要重新执行 `pad_gpu_fix_v2.sh`（initramfs 里的固件会丢）。
- `/etc/X11/xorg.conf.d/20-gpu.conf` 在 root 文件系统上，**不会**被覆盖。

---

## 15. WiFi "断了又恢复"的原因（同一次排查的副产品）

```
本次启动 firmware crashed 次数: 5
board_file api 2 bmi_id N/A crc32 00000000     ← 板级校准数据是空的
```

- 厂商 `bdwlan.*` 在 modem 分区里，但 ath10k 期望的是 `ath10k/WCN3990/hw1.0/board-2.bin`
- 系统里那个 480 KB 的 `board-2.bin` 是通用文件，**board_id 与本机不匹配**，
  所以 ath10k 退回"空板级数据"（crc32 0）
- 固件在没有射频校准的情况下运行 → 周期性崩溃 → 平台自动恢复 → 看门狗重连
- 表现就是：WiFi 隔一阵断一下，几秒后自己回来

**彻底解决**需要用厂商 `bdwlan.bin` 重新打包出匹配的 `board-2.bin`
（`ath10k-bdencoder` 工具），属于下一步工作。

---

## 16. ✅ 最终方案（2026-10-29 11:34 验证通过）

### 16.1 结论：**不改 boot 镜像**，三件事都在 root 文件系统里

| # | 文件 | 作用 |
|---|---|---|
| 1 | `/lib/firmware/a512_zap.mdt` + `.b00/.b01/.b02` | ZAP 着色器（从 modem 分区复制） |
| 2 | `/etc/X11/xorg.conf.d/20-gpu.conf` | 显式启用 glamor + DRI3 |
| 3 | `/usr/local/bin/gpu-cap-freq.sh` + `gpu-cap-freq.service` | 把 GPU 上限钉在 **370 MHz** |

**boot 分区保持原版**（md5 `55c7bce4`），彻底避开了之前两次“等根分区”的翻车。

### 16.2 为什么 370 MHz

588 MHz 下实测崩溃：

```
[drm:a5xx_irq] gpu fault ring 0 fence ffffff00 status 800001C1
[drm:adreno_idle] timeout waiting to drain ringbuffer 0 rptr/wptr = 23/C
[drm:recover_worker] hangcheck recover!
```

原因链：DT 里 GPU 的 `vdd`/`vddcx` 是 **dummy regulator**
（`supply vdd not found`），高频档位需要更高电压却给不上去 → 挂死。

370 MHz 压测 30 秒：**0 次故障，仍跑满 60 FPS**。因为 60Hz 屏幕只要 60 FPS，
高频对体感没有额外收益，所以这个取舍是合理的。

### 16.3 开机后 GPU 的两条 ERROR（可忽略）

```
[3.71] adreno: Unable to load a512_zap.mdt
[3.71] msm_dpu: gpu hw init failed: -2
[4.18] （同样两条）
```

原因：GPU 在 initramfs 阶段就探测，那时 `/lib/firmware` 还没挂上。
但 Xorg 之后打开 DRM 设备时会**重试**，此时固件已在，于是成功。

实际结果：`FD512 / Accelerated: yes / 58.6 FPS`，说明重试生效。

### 16.4 最终实测（重启后）

```
boot 分区       55c7bce4（原版）
频率上限        max=370 MHz  服务 enabled+active
渲染器          FD512  Accelerated: yes  OpenGL 3.1 Mesa 26.2.5
GPU 故障        0 次
桌面            Xorg / xfwm4 / xfdesktop / xfce4-panel 全部运行
3D              58.6 FPS      （此前 1.8 FPS，提升 32 倍）
```

### 16.5 想更进一步（可选）

要真正解锁 588 MHz，需要给 GPU 补上真实供电：

- 厂商 DT 里 `vdd-supply = gdsc_gpu_gx`、`vddcx-supply = gdsc_gpu_cx`
  （是 GPUCC 的 GDSC，不是 PMIC 直供）
- 我们的 DT 已经有 `<&gpucc GPU_GX_GDSC>`（在 iommu 节点上）
- 但 PMIC 侧的 S2/S4 电压没有跟着 OPP 升——需要 `required-opps` 把
  `opp-level` 映射到 rpmpd 的电压档，且 GPU 的 vdd 要接上真正的 regulator

这属于后续优化，**不影响现在可用性**。

### 16.6 回滚

```sh
# 关掉 GPU 加速（回到软件渲染）
sudo mv /etc/X11/xorg.conf.d/20-gpu.conf /etc/X11/xorg.conf.d/20-gpu.conf.disabled
sudo systemctl restart greetd

# 恢复 588 MHz（不推荐，会挂）
sudo systemctl disable --now gpu-cap-freq.service
```
