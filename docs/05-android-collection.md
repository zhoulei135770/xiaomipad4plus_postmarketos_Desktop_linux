# 05 · Android 侧采集结果（已 root）

> 2026-10-19 19:36，设备 `27eec4d2`，官方 8.1 + Magisk 26.4

---

## 1. 怎么拿到 root 的

| 步骤 | 结果 |
|---|---|
| Magisk **v31.0** 在应用内打补丁 | ❌ `Process error` / `Installation failed`（8.1 上跑不起来） |
| 降到 **v26.4** | ✅ 补丁成功，输出 `magisk_patched-26400_Nvyv5.img` |
| `fastboot flash boot` 该镜像 | ✅ 启动后 `verifiedbootstate=orange` |
| 验证 | `su -c id` → `uid=0(root)`；`magisk -v` → `26.4:MAGISK:R` |

> 结论：**Android 8.1 上要用 Magisk ≤ v26.x**，v31 的 patch 脚本在这台机器上直接 Process error。

## 2. 采集产物

路径：`D:\firmware\clover-dump\20261019-1936\`

| 文件 | 大小 | 价值 |
|---|---|---|
| `dmesg.txt` | 717 KB | ★ 驱动加载全记录 |
| `devicetree.tar` | 1.5 KB | ⚠ 打包失败（procfs + 权限），改用逐节点 dump |
| `i2c.txt` | — | ★ I2C 地址表 |
| `input/*` | — | 输入设备列表 |
| `audio/mixer_paths.xml` | 693 KB | 音频路由 |
| `audio/tinymix.txt` | 191 KB | codec 实际寄存器状态 |
| `wifi/WCNSS_qcom_cfg.ini` | 12 KB | Wi-Fi 配置 |
| `props.txt` / `mounts.txt` / `thermal.txt` | — | 系统信息 |

补充产物（工作区）：

- `artifacts/panel-props.txt` — 面板 DT 节点全部属性（hex）
- `artifacts/clover-dts/panel-novatek-nt51021.c` — 上游驱动源码

## 3. 关键发现（带证据）

### 3.1 触控就是 Goodix GT9110

```
[0.633793] [FTS][Info]max touch number:10, irq gpio:67, reset gpio:66
[1.661442] Gt9xx driver installing..
[1.662287] goodix-ts 3-005d: GTP Driver Version: V2.8.0.2<2017/12/14>
[1.662294] goodix-ts 3-005d: GTP I2C Address: 0x5d
[1.662309] goodix-ts 3-005d: touch input parameters is [id x y w p]<10 1200 1920 512 512>
```

I2C 扫描也确认：

```
/sys/bus/i2c/devices/3-005d     ← 触控 0x5d @ i2c3
/sys/bus/i2c/devices/8-002c     ← 背光 LP8556 0x2c @ i2c8
```

**与上游 DTS 完全一致**：`goodix,gt9110` @ `0x5d`，INT `gpio67`，RST `gpio66`，1200×1920。

### 3.2 面板是 NT51021 + BOE 10" WUXGA

内核命令行（dmesg 第 0 行）：

```
mdss_mdp.panel=1:dsi:0:qcom,mdss_dsi_nt51021_boe_10wu_wuxga_video:config0:1:none:cfg:single_dsi
```

实测 DT 时序（`artifacts/panel-props.txt`）：

| 属性 | 值（hex → 十进制） |
|---|---|
| panel-width | `0x4b0` → **1200** |
| panel-height | `0x780` → **1920** |
| bpp | `0x18` → 24 |
| h-front-porch | `0xac` → **172** |
| h-back-porch | `0x20` → **32** |
| h-pulse-width | 4 |
| v-front-porch | `0x19` → **25** |
| v-back-porch | `0x0e` → **14** |
| v-pulse-width | 1 |

上游 `panel-novatek-nt51021.c` 第 752 行：

```c
.clock = (1200 + 172 + 4 + 32) * (1920 + 25 + 1 + 14) * 60 / 1000,
```

**四个 porch 值逐个对上**（172/32/25/14），说明 upstream 驱动里的 BOE 模式就是这块屏。

### 3.3 为什么线刷包里没有小米 DTB

运行时设备树根节点：

```
model      = Qualcomm Technologies, Inc. SDM 660 PM660 + PM660L QRD
compatible = qcom,sdm660-qrd qcom,sdm660 qcom,qrd
```

**厂商内核直接用了高通 QRD 参考 DTB**，面板靠 cmdline 的 `mdss_mdp.panel=` 覆盖。这就解释了为什么 8.1 线刷包的 boot.img 里只有 32 个参考板 DTB——设备本来就不需要专属 DTB。

### 3.4 其他硬件

- Wi-Fi/BT：`icnss 18800000.qcom,icnss` 正常 probe（WCN3990）
- 背光：LP8556 @ i2c8 `0x2c`（与 DTS 一致）
- 音频：`mixer_paths.xml` + `tinymix` 已抓，PM660L codec 路由完整
- 电池/热区：`thermal.txt` 已抓

## 4. 对 pmOS 刷机的意义

| 之前担心 | 现在结论 |
|---|---|
| Plus 触控不支持 | ✅ 错误。GT9110 上游 goodix 驱动直接支持 |
| Plus 面板时序要逆向 | ✅ 不需要，实测值与上游驱动逐项一致 |
| 需要小米 DTB | ✅ 不需要，vendor 用的是 QRD 参考 DTB |

**结论：pmOS 镜像刷进去，触屏和屏幕大概率开箱可用。**

## 5. 尚未拿到（可选）

- 完整 `/proc/device-tree` 打包（procfs 归档失败，可按需逐节点读）
- 摄像头 sensor 型号（`dumpsys media.camera` 在 8.1 上返回空）
- 传感器列表（`dumpsys sensorservice` 同样为空，可能需要 `dumpsys sensorservice --list` 或 vendor 工具）
