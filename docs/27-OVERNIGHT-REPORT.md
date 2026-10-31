# 夜间工作报告（2026-10-29 00:00–00:45）

> 你去睡觉期间的自主工作。**没有做需要手指或大量耗电的实验**，设备一直在充电。

---

## 一句话总结

> **指纹这条线从"黑盒"推进到"能读懂 TA 的采集函数"；前摄从"没驱动"推进到"定位到一行 DT 错误"；
> CPU/GPU 调优修正了之前两个错误结论。**

---

## 1. 指纹：TA 反编译环境打通（今晚最大成果）

### 1.1 根本性发现

**TA 是 32 位 ARM 代码，不是 aarch64。**

```
b02 开头:  02 00 50 e3  →  cmp r0, #2
```

之前一直按 `arm64` 分析 → 只识别出 1 个函数、全是乱码。
换成 `--architecture arm` 之后：

```
1513 个函数 / 1592 个字符串 / ARM:LE:32:v7
```

### 1.2 构造了可加载的多段 ELF

`tools/ta_elf.py` 把 `b02/b03/b04/b05/b07` 五个段按 mdt 里的虚拟地址拼成
一个 ELF32/EM_ARM 可执行文件 → Ghidra 能看到数据和代码的完整关系，
**字符串 xref 全部可解析**（单段模式时几乎全是空）。

### 1.3 挖到厂商的完整 API 名表

```
fpc_ta_router_init            fpc_ta_sensor_exit
fpc_ta_route_command          fpc_ta_sensor_command_handler
fpc_ta_common_command_handler fpc_ta_sensor_device_init
fpc_ta_bio_command_handler    fpc_ta_check_finger_lost
fpc_ta_bio_enroll / identify  fpc_ta_qualify_capture / poll_qualify
                              fpc_ta_capture_image   ← 采集
                              fpc_ta_deep_sleep / wakeup_setup
```

### 1.4 反编译出了采集函数（关键）

`FUN_00045654` = `fpc_ta_capture_image` 的实现：

```c
FUN_000262a4(0xc0, 0x20, 1);      // 发 0xC0，等 IRQ 0x20
img = malloc(rows*cols + 2);      // 配置里 +0xC 是 {行, 列}
FUN_00003e40({0xC4,0}, 2, img, size);   // 读 size 字节
read 0x1C;                        // 检查 bit2 错误
memcpy(out, img + 2, size);       // ★ 图像从 buf+2 开始
```

**三条可直接用的事实**：
1. 采集 = 单字节 `0xC0` + 等 IRQ `0x20`（和我们一致 ✅）
2. 读图 = 2 字节 `{0xC4, 0}` 再读 `行×列+2`（一致 ✅）
3. **图像从 buf+2 开始** → 已做成驱动参数 `img_skip`（v10，**已部署**）

### 1.5 顺带搞清楚了寄存器层

- `fpc1020_sensor_write(buf,len)`：首字节是**寄存器号**，其余是值（芯片字节序）
- 参考驱动的 `fpc1020_reg_access`：`[reg] + [值大端]`，和我们的实现**完全一致**
- 完整寄存器表已整理（0x14 状态 / 0x1C IRQ / 0x54 采集窗口 / 0xA8 PXL_CTRL …）

---

### 1.6 ⚠️ 但是：这条路拿不到指纹图（重要，后来更正）

后来做了对照实验：Android 下抓的原始帧和我们的**统计完全一致**，
但原始帧里**没有二维结构**（水平相关 0.82 / 垂直相关 0.04，行交织重排也救不回来）。

⇒ Android 上成像是 TA 在 TEE 里自己读、自己算的，内核驱动这条路径拿不到图像。
详见 **[29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md)**。
所以 §1 的这些成果是"协议层完全搞清楚了"，不等于"能出指纹"。

---

## 2. 前摄：根因是"两个补丁没进构建"（夜里两次自我更正后的最终结论）

### 2.1 现象

```
s5k5e8 4-0010: S5K5E8 probe: chip id = 0x0 (read ret -6)
s5k5e8 4-0010: S5K5E8 not responding (err -6), failing probe
```

`-6 = ENXIO` = i2c 无应答。

### 2.2 先排除了大量可能（都是实测）

- 复位极性/时序：`reset_mode=0/1/2` × `delay_ms=20/100/300` → 全 `-6`
- 供电：三路 regulator 全部 enable 成功（vddio/vana/vdig 返回 0）
- 时钟：`MCLK -> 0 rate=24000000`（24 MHz 正常）
- 复位：`reset released (logical=0)` 正常
- i2c 地址：用 `i2cdetect` 扫遍 bus 4 → **一个设备都没有**（不是地址问题）

### 2.3 中间错误结论（已更正）

我一度以为"前摄接在后摄供电轨上"是 bug。**错的** ——
pmaports 里早就有 `0039-...-fix-frontcam-supplies.patch`，而且它在构建列表里；
设备上 `4-0010` 的 supplier 已经是 `cam-avdd-front-2v8` / `cam-front-dvdd-1v8`。

### 2.4 真正的根因：两个写好的补丁**从没被编进内核**

```
0032-arm64-dts-clover-i2c-gpio-front-camera.patch   ← bit-bang i2c，专为诊断前摄
0048-arm64-dts-clover-front-camera-endpoint.patch   ← 前摄接进 camss（port@2 → csiphy2）
```

文件在 pmaports 目录里，但 **APKBUILD 的 source 列表没有它们**：

```
$ grep -c '.patch' APKBUILD      → 84
$ grep -n '0032\|0048' APKBUILD  → 无输出
```

设备证据完全吻合：`camss/ports/` 只有 `port@0`，DT 里没有 `i2c-gpio` 节点。

⇒ **camss 从未给 csiphy2/csid2/CCI master 1 上过电，整条总线是死的**，
所以传感器怎么都不应答。

### 2.5 修复（脚本已备好）

```sh
sh patches/enable-frontcam-patches.sh          # 把两个补丁加进 APKBUILD
pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660
# 刷 boot 分区，然后验证：
i2cdetect -l                     # 应出现新的 i2c-gpio 总线
i2cdetect -y -r <该总线>          # 传感器应答吗
```

`CONFIG_I2C_GPIO=y` 已经在内核里，不用额外开配置。

---

## 3. CPU/GPU：修正两个错误结论

| 之前记的 | 实际 |
|---|---|
| GPU 缺 266/647 两档 | **266 在表里**；647/700/750 是**作者主动注释掉的**，注释写明"缺 GPU regulator，开了会挂" |
| CPU 有调频但没温控 | **CPU 完全没有 cpufreq**（`/sys/.../cpu0/cpufreq` 不存在），跑固定频率 |

⇒ CPU 调频是真正的空白，但**需要电压表（CPR）**，填错会烧硬件，不能猜。

---

## 4. 设备状态

```
电量  77%  充电中（睡觉前 50%）
运行  30 分钟，load 0.08
指纹  v10 模块，img_skip=2，参数默认
其它  未改动，无重启循环
```

---

## 5. 明天建议顺序（夜里多轮更正后的最终版）

1. **前摄**（★ 最高优先，有现成补丁）：
   ```sh
   sh patches/enable-frontcam-patches.sh
   pmbootstrap build --arch aarch64 linux-postmarketos-qcom-sdm660   # 约 30 分钟
   # 刷 boot，然后 i2cdetect -l / i2cdetect -y -r <新总线>
   ```
   三种结果对应三种结论，见 [26-FRONT-CAMERA-DIAGNOSIS.md](26-FRONT-CAMERA-DIAGNOSIS.md) §10.5
2. **modem 上线**：开机后跑一次
   ```sh
   sudo qmicli -d qrtr://0 --dms-set-operating-mode=online
   ```
   建议做成 systemd oneshot 服务
3. **短信**：qmicli 这版没有 WMS，需要带 WMS 的 libqmi，或者给 ModemManager 一个 QMI 端口
4. **指纹**：**先读 [29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md)**。
   不要再按手指调参数了 —— 证据表明内核驱动这条路径拿不到图像
5. **CPU 调频**：需要先从厂商 kernel 挖 CPR 电压表，属于大工程，别急

---

## 6. 追加：modem 默认关闭（新发现）

顺手检查短信能力时发现：

```
mmcli -L                                    → No modems were found
qmicli ... --dms-get-operating-mode         → 'shutting-down'
qmicli ... --nas-get-signal-strength        → -128 dBm（无信号）
```

**一条命令修复**：

```sh
sudo qmicli -d qrtr://0 --dms-set-operating-mode=online
```

立刻变成：

```
Mode: 'online'
LTE: -62 dBm
Registration: 'registered'   MCC 460 / MNC 0 = CMCC（中国移动）
Domain: 'cs-ps'              ← 短信/通话的 CS 域可用
```

⇒ **开机后必须跑这一条**，建议做成 systemd 服务（白天可以顺手加）。

短信本身还没验证：这版 `qmicli` 没有 WMS 选项，ModemManager 又看不到 modem。
详见 [22-LTE-CALL-SMS-OTG.md](22-LTE-CALL-SMS-OTG.md) 末尾。

---

## 7. 夜里改动的设备状态

| 项目 | 状态 |
|---|---|
| 指纹模块 | v10（含 `img_skip=2`），已部署 |
| modem | 已设为 online 并注册到 CMCC（重启后会回到 shutting-down）|
| s5k5e8 | probe 失败（与原状一致），夜里做过几轮参数实验 |
| 电量 | 77% → 充电中 |
| 网络 | 00:50 后 WiFi 随息屏挂起，SSH 不可达（正常）|
