# 46 — 修掉 DPU 黑屏：内核模块补丁（完整记录）

- 日期：2026-10-29 夜 ~ 10-30 凌晨
- 目标：彻底解决「旋转/重启后黑屏，只剩鼠标」的问题
- 结论：**已修复并在实机验证**（6 次连续旋转，全部自愈，零重启）

---

## 1. 症状

| 现象 | 说明 |
|---|---|
| 屏幕全黑，只有鼠标指针 | 硬件光标正常，主图层没了 |
| `xrandr --query` 显示一切正常 | 方向、分辨率、CRTC 都对 |
| `xrandr --rotate` 会卡住不返回 | 提交（commit）永远等不到完成 |
| 只能重启恢复 | modeset、切 VT、DPMS 都无效 |

内核日志：

```
[drm:dpu_encoder_phys_vid_wait_for_commit_done:543] [dpu error]vblank timeout: 1000000
[drm:dpu_kms_wait_for_commit_done:525] [dpu error]wait for commit done returned -110
```

## 2. 根因

`drivers/gpu/drm/msm/disp/dpu1/dpu_encoder_phys_vid.c`：

```c
ret = wait_event_timeout(phys_enc->pending_kickoff_wq,
        (hw_ctl->ops.get_flush_register(hw_ctl) == 0),
        msecs_to_jiffies(50));
if (ret <= 0) {
    DPU_ERROR("vblank timeout: %x\n", hw_ctl->ops.get_flush_register(hw_ctl));
    return -ETIMEDOUT;      /* <-- 直接放弃，CTL 块永远卡住 */
}
```

SDM660 的 **CTL（控制）块偶尔不会把 pending flush 位清零**。此时视频时序引擎
已经死了，但驱动只是返回 `-ETIMEDOUT`，**不做任何恢复动作**，于是流水线永久卡死，
之后每次 commit 都失败。只能重启。

## 3. 补丁

文件：`drivers/gpu/drm/msm/disp/dpu1/dpu_encoder_phys_vid.c`
（存档：`mipad4plus/patches/dpu-flush-timeout-recover.patch`）

超时后主动复位 CTL 并清除挂起位，然后返回 0 让下一次 commit 继续：

```c
if (ret <= 0) {
    u32 flush = hw_ctl->ops.get_flush_register(hw_ctl);

    DPU_ERROR("vblank timeout: %x, recovering ctl\n", flush);

    if (hw_ctl->ops.reset)
        hw_ctl->ops.reset(hw_ctl);              /* 写 CTL reset 并轮询完成 */
    if (hw_ctl->ops.wait_reset_status)
        hw_ctl->ops.wait_reset_status(hw_ctl);
    if (hw_ctl->ops.clear_pending_flush)
        hw_ctl->ops.clear_pending_flush(hw_ctl);

    return 0;
}
```

`hw_ctl->ops.reset` 对应 `dpu_hw_ctl_reset_control()`，会写 `MDP_CTL_x` 的 RESET
位并轮询 `dpu_hw_ctl_poll_reset_status()`，是驱动里已有的正规复位路径。

## 4. 编译：三个必须踩对的坑

### 4.1 必须用和运行内核**完全一致**的 .config

运行内核配置直接从设备上取：`zcat /proc/config.gz > .config`

### 4.2 `struct module` 大小必须一致，否则模块被拒

第一次编译用 gcc、并为了绕开 pahole 关掉了 `CONFIG_DEBUG_INFO_BTF`，加载时报：

```
module msm: .gnu.linkonce.this_module section size must match
            the kernel's built struct module size at run time
```

原因：运行内核是 **clang + CFI** 编译的（`CONFIG_CC_IS_CLANG=y`、`CONFIG_CFI=y`、
`CONFIG_DEBUG_INFO_BTF=y`），这些选项都会给 `struct module` 加字段。

**判据**：编译后用 `objdump -h msm.ko | awk '/this_module/{print $3}'`
必须与原始模块相同（本例 `00000500`）。

### 4.3 必须用 clang 编译

```sh
apk add clang lld llvm
make LLVM=1 olddefconfig
make LLVM=1 modules_prepare
make LLVM=1 KBUILD_MODPOST_WARN=1 M=drivers/gpu/drm/msm modules
```

- `KBUILD_MODPOST_WARN=1`：没有 `Module.symvers` 时把 735 个未解析符号警告降级
  （内核对 `CONFIG_MODVERSIONS` 未开启，符号在 insmod 时解析，正常）
- `CONFIG_DEBUG_INFO_BTF_MODULES=y` 需要 `pahole`（`apk add dwarves`）

### 4.4 源码树传输时的坑

从 x86 虚拟机拷来的树里带着**预编译的 x86_64 宿主工具**，在 aarch64 上会报
`scripts/kconfig/conf: line 1: ELF not found`。必须删掉 `scripts/` 和 `tools/`
下的所有 x86 可执行文件与 `.a` 静态库，让它们重新编译。

另外顶层 Kconfig 会 `source "Documentation/Kconfig"`，传树时若排除了 Documentation
要补一个空壳文件。

## 5. 部署：模块来自 boot.img 的 ramdisk，不是 rootfs

**这是最关键的一个认知**：

```
$ cat /sys/module/msm/srcversion
2BAF661FFE47B5EC3784E50        # rootfs 里换掉了，运行中还是旧的
```

设备实际从 **`/dev/mmcblk1p12`（64 MB，Android boot image）** 启动，
ramdisk 里有 `usr/lib/modules/…/msm.ko.zst`，由 initramfs 的
`usr/lib/modules/initramfs.load` 清单加载。`/boot/initramfs` 和
`/boot/extlinux/` 那套**根本没被使用**（改了没效果）。

### 部署流程

```sh
# 1. 备份启动分区（必须！）
dd if=/dev/mmcblk1p12 of=/root/p12-backup.img bs=1M

# 2. 解出 boot.img 的 ramdisk
python3 bootimg.py extract /boot/boot.img /tmp/bi
cd /tmp/rd && cpio -idm --quiet < /tmp/bi/ramdisk.cpio

# 3. 替换模块
zstd -19 msm.ko -o /tmp/new-msm.ko.zst
cp /tmp/new-msm.ko.zst usr/lib/modules/*/kernel/drivers/gpu/drm/msm/msm.ko.zst

# 4. 重新打 cpio + boot.img
find . -print0 | cpio --null -o -H newc --quiet > /tmp/new.cpio
python3 bootimg.py repack /boot/boot.img /tmp/new.cpio /boot/boot-new.img

# 5. 校验（条目数、srcversion、this_module、内核段大小都要一致）
# 6. 写入
dd if=/boot/boot-new.img of=/dev/mmcblk1p12 bs=1M conv=fsync
```

工具：`mipad4plus/tools/bootimg.py`（解析/解包/重打包 Android boot image v0-v2）。

**回滚**：把备份 dd 回 p12 即可，`mipad4plus/scripts/tab_flash_boot2.sh` 里
每次写入前都会自动备份。

## 6. 实机验证

```
起始 vblank=8   recovering=8
1) normal             rc=0  vblank=12 recovering=12
2) left --reflect xy  rc=0  vblank=16 recovering=16
3) normal             rc=0  vblank=20 recovering=20
4) left --reflect xy  rc=0  vblank=24 recovering=24
5) normal             rc=0  vblank=28 recovering=28
6) left --reflect xy  rc=0  vblank=32 recovering=32

uptime 217s -> 238s（21 秒 = 测试耗时，没有重启）
```

**每次超时都对应一次自愈**，6 次连续旋转、32 次超时，设备一次没重启，画面始终正常。

## 7. 配套改动

### 7.1 守护进程不再乱重启

`tablet-autorotate` 原本看到 vblank 消息就升级重启。现在驱动自己能恢复，
守护进程识别日志里的 `recovering ctl`：

```python
hits, rec = count_wedge(kmsg)
if rec:
    print(f'[autorotate] 驱动自愈 {rec} 次，跳过重启', flush=True)
    last_wedge = 0.0
elif hits:
    ...（原来的 modeset / 重启逻辑，作为最后兜底）
```

### 7.2 关掉自动息屏（这是「每次重启都黑屏」的另一个原因）

设备上同时存在 `xscreensaver` 和 `tablet-dpms`（`xset dpms 0 0 300`），
闲置几分钟就把 `fb0/blank` 置成 4。表现和 DPU 卡死一样（黑屏），但**光标还在**。

处理：

- 禁用 `lxqt-xscreensaver-autostart` 和 `tablet-dpms` 的自启动
- `xset s off; xset s noblank; xset -dpms`
- 新增 `tablet-no-blank.service`：每 30 秒检查 `fb0/blank`，非 0 就写回 0

## 8. 遗留

- 模块未做 strip（29 MB，压缩后 5.3 MB），boot 分区 64 MB 够用
- `CONFIG_DEBUG_INFO_BTF_MODULES=y` 但编译时没有 vmlinux，模块没生成 BTF
  （不影响加载，内核只警告）
- `/boot/boot-new.img`、`/boot/boot-new2.img`、`/boot/initramfs.*` 是过程产物，可清理
