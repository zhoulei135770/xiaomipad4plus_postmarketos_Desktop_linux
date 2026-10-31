# MIUI 对照实验方案（摄像头硬件验证）

目的：确认 OV13855 摄像头**硬件本身完好**，从而判断 pmOS 下的失败是软件问题。
方法：临时刷回 MIUI 的 boot，让设备启动原厂 Android，用相机 App 拍照；再刷回 pmOS。

---

## 0. 前置条件（已就绪）

| 项目 | 状态 | 位置 |
|---|---|---|
| 完整根文件系统备份 | ✅ 1.5 GB，md5 `46e01b5055e94e2f636a38f22743fd6f` | U 盘 `pmos-backup-20261025/rootfs.tar.zst`；电脑 `backup/pad-full-20261025/` |
| 当前 boot 分区镜像 | ✅ 64 MB（r26，已验证可启动） | 同上 `boot-r26-current.img` |
| 分区表备份 | ✅ `gpt.dump` | 同上 |
| 配置与包清单 | ✅ `configs.tar.gz`（4 MB）、`packages.txt` | 同上 |
| MIUI system 分区 (p13) | ✅ 完好（ext4，含 build.prop） | 设备内 |
| MIUI vendor 分区 (p14) | ✅ 完好（ext4，2019-05-15 构建） | 设备内 |
| MIUI boot 镜像 | ✅ `ANDROID!` 魔数，67 MB | `artifacts/rom/miui-boot.img` |
| fastboot | ✅ `D:\APPS\platform-tools\fastboot.exe`，已实测 | 电脑 |
| bootloader | ✅ 已解锁 | — |
| pmbootstrap 环境 | ✅ VM 内，含本机 device 配置 | `~/` |

---

## 1. 风险

1. **MIUI 可能改写 /data**
   pmOS 根文件系统占用 `userdata` 分区（`/dev/mmcblk1p64`，ext4，LABEL=pmOS_root）。
   MIUI 会把它当 `/data` 挂载。最可能的结果是：挂载失败 → 弹出"需要清除数据"提示
   （**不会自动格式化，需要用户确认**）。只要不点确认，数据安全。

2. **返回必须靠 fastboot**
   启动 MIUI 后 pmOS 的 SSH 消失，返回需要人工进 fastboot（音量下 + 电源）。

3. **vbmeta / dm-verity 不匹配**
   最坏情况：卡 logo 或进 fastboot。不影响数据，刷回 boot 即可。

---

## 2. 两级回滚

### Tier 1（最可能）：刷回 boot
```powershell
fastboot flash boot backup\pad-full-20261025\boot-r26-current.img
fastboot reboot
```
pmOS 根文件系统未被动过 → 直接恢复原状。

### Tier 2（rootfs 被破坏）：pmbootstrap 重装 + 配置恢复
```bash
# 在 VM 里
pmbootstrap install            # 用现有配置重新生成 rootfs 镜像
pmbootstrap flasher flash_rootfs
```
然后恢复个性配置：
```bash
# 设备上（SSH 可达后）
tar -xzf configs.tar.gz -C /     # /etc、systemd 单元、polkit、桌面项、home
apk add $(grep -oE '^[a-z0-9._-]+' packages.txt | sort -u | tr '\n' ' ')   # 可选，按清单重装
```
> 这一步会把系统恢复成"装好所有软件 + 恢复配置"的状态，
> 只是 /usr/local 下我们自己写的脚本需要从 `configs.tar.gz` 里覆盖回来（已包含）。

### Tier 3（保险）：从 rootfs.tar.zst 精确还原
需要先有可启动的 pmOS（任意版本）或救援环境，解开 tar 覆盖根分区。
`rootfs.tar.zst` 是逐字节的完整系统快照，配合 `gpt.dump` 可完全复原。

---

## 3. 实验步骤

### 阶段 A：准备
1. U 盘插好，OTG 供电开：`tablet-otg status` → `otg_vbus=1`
2. 记录当前状态：`uname -r`、`lsblk`、`sh /tmp/tablet-health.sh`
3. 电脑上确认镜像：
   ```powershell
   Get-FileHash artifacts\rom\miui-boot.img -Algorithm MD5
   ```

### 阶段 B：刷 MIUI boot
```powershell
# 设备关机 → 音量下 + 电源 → 出现 FASTBOOT
fastboot devices
fastboot flash boot artifacts\rom\miui-boot.img
fastboot reboot
```
等待 1–3 分钟。可能结果：
- 进入 MIUI → 阶段 C
- 卡 logo / 重启循环 → 阶段 D
- 进入 recovery 提示"清除数据" → **不要确认**，长按电源关机 → 阶段 D

### 阶段 C：MIUI 内验证摄像头
1. 打开「相机」→ 后摄 → 拍照
2. 记录：预览是否正常、能否拍照、照片是否清晰
3. 备用入口：拨号盘 `*#*#6484#*#*` → CIT 硬件测试 → 后置摄像头
4. 截图/拍照留证

### 阶段 D：返回 pmOS（Tier 1）
```powershell
# 关机 → fastboot
fastboot flash boot backup\pad-full-20261025\boot-r26-current.img
fastboot reboot
```
验证：
```bash
ssh user@192.168.1.29 'uname -r; ls /home/user | head; df -h / | tail -1'
```

### 阶段 E：若 Tier 1 失败 → Tier 2
按上面第 2 节执行。

---

## 4. 判定标准

| MIUI 结果 | 结论 | 后续 |
|---|---|---|
| 相机正常 | **硬件完好**，问题在 pmOS 设备树/驱动 | 继续调 pmOS：查 MCLK 实际波形、CCI 时序、传感器上电时序 |
| 相机打不开 | 硬件或模组问题 | 停止软件方向，检查排线/模组 |
| MIUI 起不来 | 无法判定 | 回 pmOS，改硬件测量 |

---

## 5. 时间估算

| 阶段 | 时间 |
|---|---|
| 刷 MIUI + 开机 | 5 分钟 |
| MIUI 内测试 | 5 分钟 |
| 刷回 + 验证 | 5 分钟 |
| （如需）Tier 2 重装 | 30–45 分钟 |

---

## 6. 回滚文件清单

| 文件 | 用途 |
|---|---|
| `boot-r26-current.img` | 刷回当前内核（r26 + 摄像头栈 + OTG 升压模块） |
| `rootfs.tar.zst` | 精确还原 pmOS 根文件系统 |
| `gpt.dump` | 恢复分区表（`sfdisk /dev/mmcblk1 < gpt.dump`） |
| `configs.tar.gz` | 恢复 /etc、systemd 单元、polkit、桌面项、home 配置 |
| `packages.txt` | 软件包清单（重建系统用） |

---

## 7. 待确认

1. 是否接受"MIUI 可能弹出清除数据提示"的风险（只要不确认就安全）
2. 实验期间需要你操作 fastboot（音量下 + 电源）2–3 次
3. 若 MIUI 相机也不工作，是否愿意做硬件测量（或送修检查排线）
