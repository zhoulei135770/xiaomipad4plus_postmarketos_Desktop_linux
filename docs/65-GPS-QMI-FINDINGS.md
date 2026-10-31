# 65 — GPS 现状与 QMI 诊断（结论：与 4G 同源，暂不可用）

> 10-31 下午。用户问"GPS 可以了吗？"，本文件记录实测过程与结论。

## 1. 结论

**GPS 不可用，且与 4G 是同一个根因**：modem 的 QMI 服务对 AP 完全不可用。

## 2. 实测过程与证据

### 2.1 内核侧

```
CONFIG_GNSS=y                      # 框架在
# CONFIG_GNSS_MTK_SERIAL is not set
# CONFIG_GNSS_SIRF_SERIAL is not set
# CONFIG_GNSS_UBX_SERIAL is not set
# CONFIG_GNSS_USB is not set
```

没有任何 GNSS 传输驱动 → **没有 `/dev/gnss`**。
高通 SDM660 的 GNSS 集成在 modem 里，AP 只能通过 **QMI LOC** 访问，
所以内核 GNSS 框架在这里本来就派不上用场。

### 2.2 modem 侧：服务是"有"的

`qrtr-lookup` 列出 modem（qrtr 节点 1）的服务，其中明确包含：

```
16  2  0  0  66   Location service (~ PDS v2)
49  1  2  0  35   IPA control service
21  1  0  0  21   Modem embedded file system service
```

### 2.3 但所有 QMI 客户端都创建失败

```
$ qmicli -d qrtr://1 --loc-get-operation-mode
error: couldn't create client for the 'loc' service: QMI protocol error (3): 'Internal'

$ qmicli -d qrtr://1 --dms-get-ids
error: couldn't create client for the 'dms' service: QMI protocol error (3): 'Internal'

$ qmicli -d qrtr://1 --nas-get-signal-info
error: couldn't create client for the 'nas' service: QMI protocol error (3): 'Internal'
```

- 不是 GPS 专属问题：**DMS / NAS 同样失败**；
- 传输层是通的（QRTR 能列出服务、内核无报错）；
- 是 **modem 主动回 QMI error 3 (Internal)**。

### 2.4 排除的干扰项

| 检查 | 结果 |
|---|---|
| rmtfs 服务 | ✅ 运行中（`rmtfs -r -P -s`） |
| rmtfs 拒绝 `modem_fsg_oem_1/2` | 正常——rmtfs 的分区表是**硬编码白名单**（见 [storage.c](https://git.abscue.de/bananian/rmtfs/-/raw/d5e516a6c6e437d1a0c1b6b39c72c89c547b160d/storage.c)），不含这两个名字 |
| 分区别名 | ✅ `/dev/disk/by-partlabel/modem_fsg_oem_1 -> fsg` 已由 udev 创建 |
| 重启 modem 子系统 | ⚠️ 会连带 WiFi 掉（ath10k 依赖 modem），**不要再用这种方式测试** |
| 显式 client-id | 本机 qmicli 版本不支持该选项 |

## 3. 与 4G 的关系

pmOS SDM660 wiki 原文：

> "The thing missing to call it 'functioning modem' is mobile data driver **(IPA)**,
> and without this driver ModemManager is completely ignoring the presence of modem
> in the system... mobile data (3G/4G) is of course not working without IPA driver."

我们用 `qmicli` 绕开 ModemManager 直接连，结果依然全部 `Internal`——
说明**不只是 ModemManager 的识别问题，modem 的 QMI 服务本身在 mainline 下就不可用**。

最可能的解释：SDM660 上 AP↔modem 的 QMI 通路依赖 **IPA** 提供的 QMI 端点
（服务列表里能看到 "IPA control service"），而 IPA 在 mainline 下不可用（见 63/64 号文档）。
→ **GPS 与 4G 被同一个未完成的 IPA 集成卡住。**

## 4. 如果以后要继续

1. 先解决 IPA（见 64 号文档的结论与建议）；
2. IPA 可用后，QMI 很可能自动恢复，届时：
   ```
   qmicli -d qrtr://1 --loc-start
   qmicli -d qrtr://1 --loc-get-position-report --loc-timeout=60
   ```
   即可验证 GPS（GNSS 引擎在 modem 内，不需要额外内核驱动）；
3. 若 IPA 长期不可用，可考虑 `gnss` 子系统的 serdev 方案，但 SDM660 的 NMEA
   走的是 QMI 而不是串口，**没有可替代路径**。

## 5. 安全提示

- **不要**通过 `remoteproc0` stop/start 来"重启 modem"：会连带杀掉 WiFi，
  这台机器会直接黑屏失去网络；
- modem 相关分区（`fsg`/`modemst1`/`modemst2`）已备份到主机：
  p11/p46/p47 各 2 MB，sha256 见本轮日志。

---

## 6. ⚠️ 重要更正（2026-10-31 15:20）：**QMI 节点是 0，不是 1**

本文第 2 节"所有 QMI 客户端返回 Internal"是**测试方法错误**导致的误判：
我用的是 `qrtr://1`，而本机 modem 的 QMI 端点是 **`qrtr://0`**。

### 6.1 用 node 0 重测的结果

```
$ qmicli -d qrtr://0 --dms-get-ids
    ESN: '11223344'   IMEI: '868225041565635'        ✅

$ qmicli -d qrtr://0 --loc-get-operation-mode
    Successfully retrieved operation mode: standalone  ✅

$ qmicli -d qrtr://0 --loc-start
    Successfully started location tracking (session id 0)  ✅
```

⇒ **QMI 完全正常，GPS 的 LOC 服务可用。**

### 6.2 定位测试

```
--loc-start                      成功
--loc-get-position-report 60s    timeout（室内无卫星信号，属正常）
```

真机定位需要室外天空视野；`standalone` 模式不依赖网络辅助。

### 6.3 modem / SIM 实况（node 0）

```
serving system: not-registered-searching（未注册）
SIM:            Card state = 'absent'   ← 当前没插 SIM 卡
```

⇒ modem 与 QMI 都是好的，"没有网络"只是因为**没插卡**。

### 6.4 结论修正

| 项目 | 之前（错误） | 现在（实测） |
|---|---|---|
| QMI | 全部 Internal，不可用 | **node 0 完全正常** |
| GPS | 不可用 | **LOC 服务可用**，需室外定位 |
| modem | 不可用 | **可用**，当前仅缺 SIM |

⚠️ 教训：`qmicli -d qrtr://N` 的 N 是 QRTR 节点号，本机 modem 在 **0**；
用 `qrtr-lookup` 列服务时列出的 "Node 0" 列才是真正的节点号。
