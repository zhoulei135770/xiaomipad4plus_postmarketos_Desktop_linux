# 早晨速览（2026-10-29 03:15）

> 一页纸看完昨晚发生了什么、今天该做什么。
> 上一版（2026-10-25）已被本轮覆盖；历史内容见 `INDEX.md` 的归档表。

---

## 现在的状态

```
设备     Mi Pad 4 Plus / pmOS 7.0.14-sdm660 r253
自检     28 通过 / 0 失败
电量     95%（充电中）
新增     modem 开机自动上线（已装；但它会崩，见下）
```

### 第一件事：跑体检

> ⚠️ **下面所有命令都要先进入 `mipad4plus/` 目录**（脚本用的是相对路径）：
> ```sh
> cd mipad4plus
> ```

```sh
python tools/pad_run.py scripts/morning_check.sh --sudo
```

一条命令收齐三件事的结果：modem 现在的状态（含夜里 mask ModemManager 的实验结论）、
前摄补丁是否已生效、指纹模块状态。全部只读。

---

## 昨晚的三条结论

### ✅ 1. modem 开机会自动上线 —— **但保不住**（后面查清了原因）

之前每次开机 modem 都躺在 `shutting-down` 状态，LTE 永远不注册。
现在有 systemd 服务，开机自动设置 online：

```
Mode: 'online'   注册 CMCC 460/0   LTE -62 dBm
```

⚠️ **但它只能撑几分钟**：夜里实测（把 ModemManager 完全 mask 掉之后）
modem 仍然在 **26 分钟里崩了 9 次**，然后回到 `shutting-down`。

已查明原因：**AP 侧没有 DIAG 消费者、也没有 IPA**，modem 固件等不到就崩
（`dog_hb.c:266: Task starvation: diag`）。现场枚举 modem 的 glink 通道，
确实只有 `DATA1..4 / DS / IPCRTR / apr_* / glink_ssr`，**没有 `DIAG`**。

⇒ 服务本身没问题，**是 modem 活不下来**。详见 [22](22-LTE-CALL-SMS-OTG.md) 最后两节。

想关掉服务：`sudo sh patches/install-modem-online.sh --remove`

### 🎯 2. 前摄：根因找到了，就差一步

**不是供电、不是时钟、不是地址问题** —— 而是两个早就写好的补丁
（`0032` bit-bang i2c、`0048` 接进 camss）**从来没被加进 APKBUILD**，
所以内核里根本没编进去。

证据：`camss/ports/` 只有 `port@0`、没有 `i2c-gpio` 节点、`i2cdetect` 扫 CCI bus 4 全空。

```sh
# ⚠️ 先腾磁盘！VM 现在 100% 满，构建会在链接 vmlinux 时 Bus error
pmbootstrap zap -n                                  # 删 native chroot，释放 ~14 G
pmbootstrap build --arch aarch64 --force linux-postmarketos-qcom-sdm660
# 刷 boot，然后一条命令验证：
python tools/pad_run.py scripts/frontcam_verify.sh --sudo
```

`frontcam_verify.sh` 会自动检查总线、`port@2`、扫描传感器、看 dmesg，**直接给结论**。

**补丁已经验证过能干净应用**（夜里实跑过完整构建，日志里两个补丁都 patch 成功），
那次失败纯粹是磁盘满 —— 不是补丁的问题。

**驱动本身是完整的**（三组模式表、各 60+ 条初始化序列都在），不用再挖别的。
（原来的 `0032` 补丁已经失效，我重做成了 `0053`，实测干净应用。）

### 🔚 3. 指纹：不是没调好，是这条路拿不到图

我们抓的原始帧和 Android 抓的**统计上完全等价**（min/max/spread 一致）—— 协议层是对的。
但原始帧里**没有二维结构**：水平相关 0.82、垂直相关 0.04，行交织重排也救不回来。

原因：**Android 上成像是 TA 在 TEE 里自己读、自己算的**，内核驱动这条路只拿得到中间量。

⇒ 想真出指纹只有"跑厂商 TA"一条路（要 QSEECOM + TA 加载器 + Android HAL，数周且成功率低）。
详细分析：[29-FINGERPRINT-CEILING.md](29-FINGERPRINT-CEILING.md)

---

## 昨晚的副产品

| 发现 | 文档 |
|---|---|
| 从厂商 DTB 解出**完整 CPU 频率/电压表**（silver 8 档、gold 7 档）| [23](23-PERF-THERMAL.md) §10 |
| CPU 调频要的是 **OSM/APM 驱动**（主线没有），不是补 OPP 表 | [23](23-PERF-THERMAL.md) §11 |
| 4G 的卡点是缺 sdm660 IPA 端点表；`ipa_fws` 其实存在 | [22](22-LTE-CALL-SMS-OTG.md) |
| 扬声器**没有保护限幅**（主线不加载 ACDB），建议用户态加 limiter | [28](28-AUDIO-ACDB.md) |
| chromatix XML 全是 ISP 参数，对主线**没用** | [28](28-AUDIO-ACDB.md) |
| 16 个"孤儿补丁"（存在但没进构建）已分类 | [26](26-FRONT-CAMERA-DIAGNOSIS.md) §10.7 |

---

## 今天建议的顺序

1. **前摄**（★ 最高性价比，现成补丁）：`enable-frontcam-patches.sh` → 编译 → 刷机 → 扫总线
2. **短信**：modem 稳了之后用带 WMS 的 qmicli 或给 ModemManager 一个 QMI 端口
3. **指纹**：先读 29 号文档，再决定要不要投入 TA 路线
4. **CPU 调频**：独立项目（写 OSM 驱动），别急着上

---

## 文档导航

- 全部文档地图 → **[INDEX.md](INDEX.md)**
- 总状态 → **[START-HERE.md](START-HERE.md)**
- 昨晚完整报告 → **[27-OVERNIGHT-REPORT.md](27-OVERNIGHT-REPORT.md)**
