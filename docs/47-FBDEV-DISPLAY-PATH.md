# 47 — 黑屏的最终解法：改用 fbdev 驱动

- 日期：2026-10-30 凌晨
- 结果：**画面恢复**，路径可靠、可重现

---

## 1. 最后的诊断链条

| 测试 | 结果 | 说明 |
|---|---|---|
| 停掉 X，直接写 `/dev/fb0`（品红/白/绿图案） | **正常显示** | 面板、DSI、DPU 都没问题 |
| 启动 X 后再写 `/dev/fb0` | 图案消失、变黑（只剩光标） | X 接管了扫描缓冲 |
| X 自己截屏（`import -window root`） | **有完整桌面** | X 渲染正常，但内容没进扫描缓冲 |
| DRM 状态 `plane-0` | `enabled`、`fb=68`、`allocated by = Xorg` | 主图层指向 X 的缓冲 |
| X 日志 | `glamor disabled`、`ShadowFB: enabled NO`、`TearFree is not used` | 没有影子缓冲，也没有 glamor |

**结论**：modesetting（KMS）这条路径下，X 的渲染结果**永远不会出现在面板上**。
面板本身完全正常——只要绕过 KMS，直接写帧缓冲就能显示。

## 2. 解法

换用 X 的 **fbdev 驱动**，让它直接画到 `/dev/fb0`：

```sh
apk add xf86-video-fbdev
```

`/etc/X11/xorg.conf.d/20-fbdev.conf`：

```ini
Section "Device"
    Identifier  "fbdev"
    Driver      "fbdev"
    Option      "fbdev" "/dev/fb0"
EndSection
```

同时停用所有 modesetting 配置（改名为 `.disabled`）：

```
50-msm-soft.conf.disabled
20-gpu.conf.{disabled,broken,bad-present}
```

## 3. 代价与限制

| 项目 | 影响 |
|---|---|
| **不支持 RandR 旋转** | `xrandr --rotate` 不可用，固定 1200×1920 竖屏 |
| 无硬件光标 | 软件光标（本来也是 llvmpipe 渲染） |
| 无 glamor 加速 | 之前也是关闭的，无变化 |
| `FBIOPUTCMAP: Invalid argument` | 32 位直色模式下的无害报错，可忽略 |

**横屏目前不可用**。以后若要横屏，可行的方向：

1. 在应用层做旋转（例如让桌面在 1200×1920 的 X 屏幕上以旋转后的坐标布局）——复杂度高
2. 修好 modesetting 路径（真正的问题仍未定位到根因）
3. 内核层面用 `fbcon=rotate:1` 只对控制台有效，对 X 无用

## 4. 昨晚那个内核补丁的结论

`46-KERNEL-DPU-PATCH.md` 里改的 `msm` 模块：

- **有效的部分**：拦住 `vblank timeout` 后不再 `-ETIMEDOUT`，X 不会卡死、`xrandr` 不会挂起
- **无效的部分**：复位 CTL 之后画面并没有回来，屏幕仍然黑
- **副作用**：守护进程看到「已自愈」就不再重启，反而让黑屏变成永久状态

**已回滚**：`mmcblk1p12` 恢复为原始 boot.img，`srcversion = 2BAF661FFE47B5EC3784E50`。
补丁代码和结论保留在 46 号文档里，等有时间再迭代（下一步该在复位后调用
`dpu_encoder_helper_trigger_start()` 重启时序引擎）。

## 5. 当前稳定配置

| 项目 | 值 |
|---|---|
| X 驱动 | `fbdev`（`/dev/fb0`） |
| 分辨率 | 1200×1920 竖屏 |
| 内核模块 | 原始版 `2BAF…` |
| 自动旋转 | 关闭 |
| 开机旋转 | 已从 `lxqt-x-session` 移除 |
| 防息屏 | `tablet-no-blank.service`（每 30 秒检查 `fb0/blank`） |
| 触摸 | Goodix，libinput，矩阵为 identity（竖屏） |

## 6. 教训

> **「截图有内容」不等于「屏幕有内容」。**
> X 的截屏读的是 X 自己的绘制结果，和扫描输出完全是两件事。
> 判断显示链路必须分层：先直接写 `/dev/fb0` 验证面板，再验证 X 的输出路径。

这一条如果早一点想到，昨晚能省掉几小时的 modesetting 折腾。
