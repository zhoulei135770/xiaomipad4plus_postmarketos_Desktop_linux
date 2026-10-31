# 晚上回来怎么做（一页纸）

> 平板目前离线。**GPU 的最优解已经找到并离线验证过**：删掉 DTB 里的 `zap-shader` 节点。

---

## 结论先说

| | |
|---|---|
| 症状 | 桌面 1.8 FPS，`glxinfo` 显示 llvmpipe |
| 根因 | GPU 初始化失败：`Unable to load a512_zap.mdt` → `gpu hw init failed: -2` |
| **正解** | **DTB 里删掉 `zap-shader` 节点** → 驱动改走 `SECVID_TRUST_CNTL` 路径，GPU 正常工作 |
| 依据 | 内核源码 + 主线 sdm630/sdm660 本来就没有这个节点 |
| 风险 | 低（只改 DTB，显示由 DPU 负责不受影响，随时可回滚） |

---

## 第 1 步：平板能进桌面（哪怕没网）

`Ctrl+Alt+F2` 进文字终端，登录 user/<SUDO_PASSWORD>：

```sh
sudo sh /tmp/pad_fix_gpu_nozap.sh --build   # 先只构建，看看输出
sudo sh /tmp/pad_fix_gpu_nozap.sh           # 确认没问题再刷入+重启
```

脚本会：解出 DTB → 删 `zap-shader` → 重编译 → 校验（节点消失/DTB 可解析/kernel 不变）
→ 备份 `/root/boot-rollback.img` → 刷入 → 回读校验 → 重启。

同时它会顺手还原我之前改坏的固件加载器（如果备份还在）。

## 第 2 步：开不了机

电脑 + USB，音量下 + 电源进 fastboot：

```sh
fastboot flash boot mipad4plus\backup\device-boot\boot.img
fastboot reboot
```

## 第 3 步：验证

```sh
sudo sh /tmp/gpu_acceptance.sh
```

期望看到：

```
✅ ZAP 固件加载没有报错
✅ card0 是 adreno/msm 驱动
✅ Xorg 正在用 Adreno 硬件渲染
✅ 帧率 40-60 FPS
```

如果 GPU 起来了但仍显示 llvmpipe，再补一句：`sudo sh install-xorg-gpu.sh`

---

## 备选方案（如果删节点失败）

`pad_gpu_fix_all.sh` —— 塞 ZAP 固件进 initramfs 的方案（已写好，但绕路更多）。
两条方案的差别：

| 方案 | 改动 | 说明 |
|---|---|---|
| **删 zap-shader（首选）** | 只有 DTB | 驱动走 -ENODEV → SECVID_TRUST_CNTL |
| 塞固件进 initramfs | ramdisk | 需要固件在 /lib/firmware 根（上次放错到 qcom/） |