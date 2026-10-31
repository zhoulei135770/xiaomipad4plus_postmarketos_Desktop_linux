# 刷机指南（fastboot / TWRP）——为什么优先用 fastboot + 分卷

> 本机镜像是 **~2.6 GB**，在 WiFi 传输、U 盘拷贝、TWRP 写入过程中都可能
> 因为**长时间大流量而中断**。这一页说明怎样刷最不容易出事。

---

## 1. 两条路径对比

| | **fastboot（推荐）** | TWRP（备选） |
|---|---|---|
| 适用 | 刷 `boot.img`（小，64 MB） | 刷整个系统（含 rootfs） |
| 传输量 | 极小 | 2.6 GB |
| 中断风险 | 很低 | 中（大文件） |
| 恢复中断 | 重新执行同一条命令即可 | 需从头再刷 |
| 依赖 | 需能进 fastboot | 需能进 TWRP |

**建议流程**

```sh
# ① 内核：fastboot（最稳，64 MB）
fastboot flash boot boot.img
fastboot reboot

# ② 根文件系统：二选一
#    A. TWRP 刷 zip（包内已做流式解压，不占内存盘）
#    B. 有线连接后，用 adb 把 zip 推到 /data 再刷（比无线稳）
```

---

## 2. 大文件为什么容易断，怎么防

| 环节 | 风险 | 对策 |
|---|---|---|
| 从 GitHub 下载 | 2.6 GB，WiFi 抖动会断 | `curl -C -` **断点续传** |
| 拷到平板/TF 卡 | 同样 | 分卷（1 GB）+ 每卷校验 |
| TWRP 内解压 | TWRP `/tmp` 是内存盘，**必然失败** | 已改为**流式解压**（`unzip -p | tar -x`） |
| 刷写写入 | 掉电/断电 | 保持电量 > 50%，不要按电源 |

### 断点续传下载

```sh
curl -L -C - -o clover-restore.zip \
  https://github.com/zhoulei135770/xiaomipad4plus_postmarketos_Desktop_linux/releases/download/<tag>/clover-restore-20261031.zip
```

### 分卷（如果提供 .z01/.z02）

```sh
# 合并
zip -s 0 clover-restore.zip --out full.zip   # 自动合并分卷
# 或者
cat clover-restore.z01 clover-restore.z02 clover-restore.zip > full.zip
```

### 校验（务必做）

```sh
sha256sum -c clover-restore.sha256
```

---

## 3. TWRP 刷机步骤（详细）

1. `fastboot boot twrp-3.7.0_9-0-clover-mipad4.img`（临时启动，不覆盖现有 recovery）
   或 `fastboot flash recovery twrp...img` 永久刷入；
2. TWRP 里 **Wipe → Format Data**（会清空 `/data`，即 rootfs；可选但推荐）；
3. **Install → 选择 `clover-restore-*.zip`**；
4. 等待 `==== finished: reboot to system ====`；
5. Reboot → System。

> ⚠️ 不要用 TWRP 的 "Install Image" 刷 zip；必须用 Install → 选 zip。

---

## 4. 包内做了什么（可审计）

`META-INF/com/google/android/update-binary`：

```
1. 找 boot 分区（boot / boot_a）
2. unzip -p boot.img | dd of=<boot>        # 流式，不落 /tmp
3. mount userdata /data
4. unzip -p rootfs.tar.gz | tar -xz -C /data --numeric-owner   # 流式
5. chown root / chmod / sync
```

rootfs 里的 `/etc/fstab` 与内核 cmdline 都使用**固定的 root UUID**
（`8def993b-42f5-4ba1-9813-c046e498fe22`），所以恢复包不需要重写 UUID。

---

## 5. 已验证 / 未验证

| 项目 | 状态 |
|---|---|
| `boot.img` 为合法 Android bootimg，含本机 `pmos_root_uuid` | ✅ 已验证 |
| rootfs tar 使用 `--numeric-owner`，无绝对路径 | ✅ 已验证 |
| TWRP 流式解压（不占内存盘） | ✅ 已改（本版新增） |
| 完整刷入后开机 | ⏳ 需要在真机上回归一次 |

---

## 6. 万一刷坏了

| 症状 | 处理 |
|---|---|
| 卡在 bootloader | `fastboot flash boot boot.img` 重刷内核 |
| rootfs 损坏 | 重进 TWRP，重新刷 zip（可先 Format Data） |
| 什么都进不去 | 长按电源 10 秒重启；仍不行则用 EDL 模式（需 QFIL/厂商线刷包） |
