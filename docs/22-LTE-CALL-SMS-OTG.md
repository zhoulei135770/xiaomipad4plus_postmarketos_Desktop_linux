# 22 · 4G / 通话 / 短信 / OTG 现状（2026-10-28 现场取证）

> 设备在 MoKee Android 11 + 中国移动 SIM 上，全部现场取证。
> 采集物：`artifacts/mokee-20261028/telephony.db`（APN 表）、`cam-after/`（同批 sysfs/dmesg）。

---

## 0. 一句话结论

| 项 | 状态 | 卡点 |
|---|---|---|
| **OTG** | ✅ **已完成**（14 项完全可用之一） | 无 |
| **4G 数据** | ❌ | **IPA**（`rmnet_ipa0` + `ipacm`），且设备上**没有 IPA 固件文件** |
| **通话** | ⚠️ Android 上走 **VoLTE**（不是 CS） | pmOS 没有 IMS 栈 ⇒ 只能 CS fallback，国内 2G 退网后基本不可用 |
| **短信** | 🟡 **很可能已经能用**，只是没测 | 走 QMI WMS（NAS 信令），**不需要 IPA、不需要 IMS** |

---

## 1. OTG —— 不用再管

`START-HERE.md` 的"✅ 完全可用"里已经包含：USB OTG host（hub + 3 个输入设备 + 千兆网卡全部枚举、1000 Mb/s、0% 丢包），
对应补丁：

| 补丁 | 作用 |
|---|---|
| 0085 | OTG buck-boost 使能 |
| 0086 | OTG 电流限制 1.5 A（修带载崩溃） |
| 0088 | TypeC CC 状态读取（自动 host/charge 切换） |

剩下的只有边角：大功率设备、反复热插拔压力测试。不算待办。

---

## 2. 4G 数据 —— 卡在 IPA，而且"固件已备"这个说法要修正

现场证据（本次 Android 上）：

```
/sys/class/net:  rmnet_ipa0  rmnet_data0..7  r_rmnet_data0..8  wlan0 ...
init.svc.vendor.ipacm: running           ← IPA connection manager
mDataConnectionState=2 (CONNECTED)       ← 数据确实是通的
```

⇒ 数据面 100% 走 **IPA offload**，不是 legacy rmnet。

**新发现（推翻了旧假设）**：把 `/vendor/firmware_mnt/image/`（336 个文件）、`/firmware/image`、
`/vendor/firmware` 全列过一遍，**没有任何 `ipa_fws.*` / `ipa_uc.*`**，只有 `mlipay.*`、`modem.*`、`mba.mbn`。
⇒ IPA 微码是打包进 modem 镜像的，不是独立固件文件。主线的 IPA 驱动（期望独立 `ipa_fws.elf`）
在这台机器上没有现成固件可喂。

叠加主线事实：`drivers/net/ipa` 只覆盖 IPA 4.x（sdm845 及以后），**SDM660 是 IPA 3.x，没有驱动**。
所以 4G 数据不是"补个 DT 就行"，是"要写驱动级的东西"，工作量按下限估也远超指纹。

**回 pmOS 后可以先做的廉价验证**（不改内核）：
```sh
ip link                    # 看 modem 起来后有没有 rmnet 通道
qrtr-lookup                # 确认 QMI 服务列表（含 wds/voice/wms）
```
如果 `wds` 服务在，说明 QMI 数据呼叫能建立，只是没有承载网卡 —— 那才轮到 IPA。

---

## 3. 通话 —— Android 上是 VoLTE，这点必须先认清

`dumpsys telephony.registry` 原文摘录：

```
CS domain: registrationState=HOME  accessNetworkTechnology=LTE  availableServices=[VOICE,SMS,VIDEO]
PS domain: registrationState=HOME  accessNetworkTechnology=LTE  availableServices=[DATA]
           LteVopsSupportInfo: mVopsSupport = 2
```

- **CS 域注册在 LTE 上**，且 `availableServices` 已经包含 VOICE ⇒ 走的是 **VoLTE / SGs**，不是 2G/3G CS。
- 佐证：`persist.dbg.ims_volte_enable=1`，且 `imsqmidaemon` / `ims_rtp_daemon` / `imsdatadaemon` / `imsrcsservice` 全在跑。

⇒ **pmOS 上要打电话，等于要在 Linux 里跑一套 IMS/VoLTE 栈**（ModemManager 目前不支持 VoLTE 通话），
现实做法只有 CS fallback（需要当地 2G/3G 还活着）。结论：**通话是四项里最难的，排最后。**

---

## 4. 短信 —— 最可能"回 pmOS 就通"的一项，应该第一个测

SMS 走的是 **NAS 信令 + QMI WMS**，不经过 IPA，也不经过 IMS。
而 LTE 射频/注册在 pmOS 上**已经验证可用**（注册中国移动、RSSI −63 dBm）。

回 pmOS 后的验证步骤（纯用户态，5 分钟）：

```sh
mmcli -m 0                                   # 看 modem 状态 / 号码
mmcli -m 0 --messaging-create-sms="text=hello,number=+86138xxxxxxxx"
mmcli -s <id> --send
mmcli -m 0 --messaging-list-sms              # 收
```
若 `mmcli` 里没有 messaging 接口，用 `qmicli -d qrtr://0 --wms-...` 直接走 QMI 验证。

---

## 5. 顺手拿到的 APN 表（China Mobile，pmOS 配 ModemManager 用）

从 `telephony.db` 的 `carriers` 表导出（51 条 460 记录），CMCC 关键项：

| APN | type | protocol | MCC/MNC |
|---|---|---|---|
| `cmnet` | default,supl | IP | 46000 / 46002 / 46007 |
| `cmnet` | default,supl,xcap | IPV4V6 | 46004 / 46008 |
| `cmwap` | default,supl | IP | 46000 / 46002 / 46007 |
| `cmwap` | mms | IP | 46000 / 46002 / 46007 / 46008 |
| `ims` | ims | IPV4V6 | 46000 / 46002 / 46007 / 46008 |

pmOS 上手工建连接（IPA 通了以后）：
```sh
mmcli -m 0 --create-profile="cmnet,apn=cmnet,ip-type=ipv4v6"
```

---

## 6. 优先级建议

1. **短信**（几乎确定能通，验证成本 5 分钟）
2. **4G 数据**（IPA 驱动，工作量大，但是"完美驱动"的硬指标之一）
3. **通话**（VoLTE 无解，等 CS fallback 或等 IMS 生态；暂时标为"已知不可达"）
4. ~~OTG~~（已完成）

---

## 2026-10-29 00:50 夜间发现：**modem 默认是关的，一条命令就能拉起**

### 现象

开机 30 分钟后（WiFi 正常）：

```
mmcli -L                      → No modems were found
qmicli -d qrtr://0 --nas-get-signal-strength   → Network 'none': -128 dBm
qmicli -d qrtr://0 --dms-get-operating-mode    → Mode: 'shutting-down'
```

即：**modem 固件在跑（QRTR 服务都在、qmicli 能通），但射频是关的。**

### 修复（一条命令）

```sh
sudo qmicli -d qrtr://0 --dms-set-operating-mode=online
```

立即生效：

```
Mode: 'online'
Signal: Network 'lte': -62 dBm        ← 中国移动 LTE，信号很好
Registration state: 'registered'
MCC: 460  MNC: 0  Description: 'CMCC'
Domain: 'cs-ps'                        ← CS 域可用（短信/通话的前提）
```

**⇒ 开机后必须执行这一条，否则 LTE 永远不注册。建议做成 systemd oneshot 服务。**

### 短信验证的阻塞点

这个版本的 `qmicli` **没有 WMS 选项**：

```
qmicli -d qrtr://0 --wms-list-messages   → error: 未知选项
qmicli -d qrtr://0 --wms-get-smsc-address → error: 未知选项
```

而 `ModemManager` 又看不到 modem（因为没有 wwan/QMI 端口注册给它）。

**两条路**：
1. 装更新的 `libqmi`（带 WMS）→ 直接 `--wms-*`
2. 给 ModemManager 一个可用的 QMI 端口（主线需要 `qcom_q6v5_mss` 暴露 `wwan` 或
   MM 走 QRTR 后端；Debian 的 MM 可能没编 QRTR 支持）

### 顺带记下

`s5k5e8` 驱动每次 insmod 都会打一堆 `regulator_bulk_free` WARNING 把 dmesg 刷满
（是我们夜里做实验触发的，不是新问题；清理逻辑有缺陷，见 26 号文档）。

---

## 2026-10-29 02:30 复核：4G 数据的真实卡点（修正旧结论）

### 三个旧结论的更正

| 旧记录 | 实际（已核实）|
|---|---|
| "设备上没有独立 ipa_fws 固件" | ❌ **有**：`/lib/firmware/ipa_fws.b00 … b07` 全都在 |
| "主线只支持 IPA 4.x，SDM660 是 3.x" | ❌ 主线支持 **3.0/3.1/3.5/3.5.1/4.x**，`ipa_data-v3.1.c` 存在 |
| "4G 完全做不了" | 🟡 做得了，但缺 sdm660 的板级数据 |

### 实际状态

```
CONFIG_QCOM_IPA=m                       ← 驱动编成了模块
drivers/net/ipa/ 支持:  msm8998-ipa(3.1) / sdm845-ipa(4.0) / sc7180 / sm6350 …
                    不支持: sdm660-ipa    ← 没有这个 compatible
/dev/… 里没有 ipa 平台设备               ← DT 里没有 ipa 节点，驱动从未 probe
/sys/class/net/ 只有 lo wlan0           ← 没有 rmnet 数据口
```

modem 侧的真实报错（这是关键证据）：

```
qcom-q6v5-mss 4080000.remoteproc: fatal error received:
  ipa_util.c:1089: IPA Assert: ipa_util.imm_cmd.clients[cmd_handle].init_done == ...
```

⇒ **modem 固件里的 IPA 客户端在等 AP 侧的 IPA 就绪，等不到就断言失败。**
这也解释了为什么 modem 有时会处在 `shutting-down` 状态 —— 它自己崩了。

### 要做 4G 数据，缺的是这些

1. **`ipa_data-v3.0.c`（或 3.1 变体）的 sdm660 端点表** —— 这是最大的一块：
   每个平台的 channel/endpoint 映射都不一样，vendor 的 `ipa_v3.c` 里有几百行配置
2. **DT 节点**：`ipa@1e00000 { compatible = "qcom,sdm660-ipa"; ... }`，
   要写 reg / interconnects / memory-region（IPA 共享内存）
3. **GSI 配置**：sdm660 的 GSI 版本要和驱动匹配
4. rmnet / qmi_rmnet 用户态配合

**工作量估计：1–2 周**（主要是端点表要从 vendor kernel 反推或抄厂商 `drivers/platform/msm/ipa`）。

### 短信呢？

SMS 走 **QMI WMS**（NAS 信令），**不经过 IPA**。
所以理论上只要 modem 不崩就能收发短信 —— 但现在 modem 会因为 IPA 断言崩，
所以**先解决 modem 稳定性，短信才有意义**。

建议顺序：modem 在线服务 → 观察是否还崩 → 再试短信 → 最后才考虑 IPA。

---

## ✅ 2026-10-29 02:35 已实施：modem 开机自动上线

### 装了什么

```
/usr/local/bin/modem-online.sh                     ← 设置 online + 重试 10 次
/etc/systemd/system/modem-online.service           ← oneshot，enabled
```

源文件在 `patches/modem-online.{sh,service}` +
`patches/install-modem-online.sh`（一键安装/卸载）。

### 实测结果

```
systemctl status modem-online.service
  Active: active (exited)  status=0/SUCCESS
  modem set online
  Mode: 'online'

qmicli --nas-get-serving-system
  Registration state: 'registered'
  MCC: 460  MNC: 0  Description: 'CMCC'

qmicli --nas-get-signal-strength
  Network 'lte': -62 dBm
```

### 卸载

```sh
sudo sh patches/install-modem-online.sh --remove
```

### 注意

modem 现在会因为 IPA 断言崩溃（见文末），服务带 `Restart=on-failure`
`StartLimitBurst=5`，崩了会自动重试，但**重试也救不了 IPA 相关的崩溃** ——
那要等 IPA 做好。

---

## 2026-10-29 02:00 重启实测：服务能跑，但 modem **保不住在线**

### 1. 服务在开机时确实执行了 ✅

```
Oct 29 01:37:59 systemd[1]: Starting Bring the Qualcomm modem online...
Oct 29 01:37:59 modem-online.sh[2672]: modem set online
Oct 29 01:38:04 modem-online.sh[2850]:         Mode: 'online'
Oct 29 01:38:04 modem-online.sh[2855]:         Registration state: 'registered'
Oct 29 01:38:04 modem-online.sh[2855]:                 Description: 'CMCC'
```

### 2. 但 8 分钟后又变回 shutting-down ❌

```
Mode: 'shutting-down'
Registration state: 'not-registered-searching'
```

### 3. 两个元凶

**元凶 A：ModemManager 在反复抢端口**

```
[base-manager] couldn't create modem for device 'qcom-soc':
   Failed to find a net port in the QMI modem
[base-manager] couldn't create modem for device 'qcom-soc':
   Unsupported device: at least a QMI port is required
[qrtr0/probe] probe step: ...
```

它反复 release/acquire `qrtr0`、`rpmsg_ctrl3`，建不出 modem 又不停重试。

**元凶 B：modem 固件自己在崩**

```
qcom-q6v5-mss 4080000.remoteproc: fatal error received:
  dog_hb.c:266: Task starvation: diag, ping: 4
remoteproc remoteproc1: crash detected in 4080000.remoteproc: type fatal error
remoteproc remoteproc1: handling crash #3
remoteproc remoteproc1: recovering 4080000.remoteproc
MBA booted without debug policy, loading mpss
remote processor 4080000.remoteproc is now up
```

**`Task starvation: diag`** —— diag 子系统被饿死。
很可能是 AP 侧没有 diag 客户端在读那条通道（主线没有 `diag` 驱动/用户态），
modem 侧的 diag 任务等不到响应就触发看门狗。

⇒ modem 崩溃后被 remoteproc 重启，重启后回到 `shutting-down`，
所以**服务设一次 online 只能顶几分钟**。

### 4. 做的判定实验（结果未取完）

停掉并 mask 掉 ModemManager，再设 online：

```sh
sudo systemctl stop ModemManager
sudo systemctl mask ModemManager
sudo qmicli -d qrtr://0 --dms-set-operating-mode=online
```

**⚠️ 这些改动留在设备上了**，如果你想恢复：

```sh
sudo systemctl unmask ModemManager
sudo systemctl start ModemManager
```

验证被 WiFi 挂起打断（屏幕熄灭后 WiFi 会断，SSH 连不上），
**明早第一件事**：看一眼 modem 是否还保持 online：

```sh
sudo qmicli -d qrtr://0 --dms-get-operating-mode
sudo dmesg | grep -c 'crash detected'
```

- 如果保持 online、crash 计数没涨 → **ModemManager 是元凶**，别装它
- 如果又变 shutting-down、crash 计数涨了 → **diag 饿死是真问题**，要补 diag 通道

### 5. 结论对短信的影响

短信走 QMI WMS，不需要 IPA，**但需要 modem 稳定在线**。
在 diag 饿死问题解决前，短信大概率不可靠。

---

## 2026-10-29 02:20 综合结论：modem 为什么会崩 —— **AP 侧缺两个服务**

夜里先后抓到两条 modem 崩溃日志，现在能串成一条因果链：

### 两条崩溃日志

```
#1  IPA Assert
qcom-q6v5-mss: fatal error received:
  ipa_util.c:1089: IPA Assert: ipa_util.imm_cmd.clients[cmd_handle].init_done == ...

#2  DIAG 饿死
qcom-q6v5-mss: fatal error received:
  dog_hb.c:266: Task starvation: diag, ping: 4
```

### 主线缺什么

| 服务 | 主线现状 | 后果 |
|---|---|---|
| **IPA** | 驱动有（`CONFIG_QCOM_IPA=m`），但 **DT 里没有 ipa 节点**、没有 sdm660 端点表 | modem 的 IPA 客户端等不到 AP 就绪 → 断言 |
| **DIAG** | **完全没有**（`drivers/` 里没有 diag 驱动）| modem 的 diag 任务写通道没人读 → 饿死 → 看门狗 |

传输层倒是齐的：

```
CONFIG_RPMSG=y            CONFIG_RPMSG_CHAR=y
CONFIG_RPMSG_CTRL=y       CONFIG_RPMSG_QCOM_GLINK_SMEM=y
CONFIG_RPMSG_QCOM_SMD=y
sdm660.dtsi 里有 smem / glink 节点
```

⇒ **通道存在，只是没有协议层消费者。**

### 因果链

```
主线不跑 IPA ──┐
              ├──→ modem 固件内部断言/饿死 ──→ remoteproc 检测到 crash
主线不跑 DIAG ─┘                                │
                                                ↓
                                        重启 modem 固件
                                                │
                                                ↓
                                    回到 'shutting-down' 状态
                                                │
                                                ↓
                              开机服务设的 'online' 只能顶几分钟
```

这也解释了为什么"设一次 online 就好了、过一会儿又没了"。

### 可能的两条修法

| 方案 | 工作量 | 说明 |
|---|---|---|
| **A. 用户态"抽干" DIAG 通道** | 小（1 天）| 用 `/dev/rpmsg_ctrl` + `RPMSG_CREATE_EPT_IOCTL` 打开 DIAG 通道并持续读取，让 modem 的 diag 任务不阻塞。**只需一个小 C 程序 + systemd 服务** |
| **B. 移植 diagchar 驱动** | 大（1–2 周）| 从下游 `drivers/char/diag/` 移植，工作量大且和主线 rpmsg 架构不匹配 |

IPA 那条（4G 数据）仍然是大工程，和 modem 稳定性是**两个独立问题**。

### 优先级建议

1. **先试 A**（抽干 DIAG）—— 成本低，可能直接让 modem 稳定
2. diag 稳了之后再验证短信（WMS 不过 IPA）
3. 最后才考虑 IPA（4G 数据）

### 明早要看的实验结果

夜里做了判定实验（停掉 + mask ModemManager），没取到结果：

```sh
sudo qmicli -d qrtr://0 --dms-get-operating-mode
sudo dmesg | grep -c 'crash detected'
```

- 保持 online、crash 没涨 → MM 的端口争抢是诱因，别装它
- 又掉、crash 涨了 → 就是上面的 IPA/diag 缺服务问题

### 方案 A 的第一步工具已备好

`scripts/modem_diag_probe.sh` —— 明天上机先跑它：

```sh
python tools/pad_run.py scripts/modem_diag_probe.sh --sudo
```

它会：

1. 列出 `/sys/bus/rpmsg/devices/` 下所有通道（名字、src/dst、绑定的驱动）
2. 找出名字里带 `DIAG` 的通道
3. 如果它没被驱动绑定，尝试 `echo <dev> > /sys/bus/rpmsg/drivers/rpmsg_chrdev/bind`
4. 绑定成功后给出"持续读取"的命令，用来验证抽干通道能否阻止崩溃

**怎么判断成功**：抽干通道后观察 10 分钟

```sh
watch -n 30 'dmesg | grep -c "crash detected"'
```

- 计数不涨、`qmicli --dms-get-operating-mode` 保持 online → **方案 A 成立**，
  把它做成 systemd 服务即可
- 计数继续涨 → diag 不是唯一原因，还要看 IPA

### 方案 A 的完整工具链（两个文件）

| 步骤 | 工具 | 作用 |
|---|---|---|
| 1. 探测 | `scripts/modem_diag_probe.sh` | 列出 rpmsg 通道、找 DIAG、试 sysfs 绑定 |
| 2. 接管 | `tools/rpmsg_drain.py` | 纯 Python 创建端点并持续读取（不用编译）|

**为什么是 Python**：平板上没有编译器，而 `RPMSG_CREATE_EPT_IOCTL`
就是个普通 ioctl，Python 的 `fcntl.ioctl` 完全够用。

用法：

```sh
# 1) 看有哪些通道（名字、src、dst、绑定的驱动）
python3 rpmsg_drain.py list

# 2) 接管 DIAG（src/dst 用上一步查到的）
python3 rpmsg_drain.py drain DIAG <src> <dst>
```

ioctl 编号已核对：

```
struct rpmsg_endpoint_info { char name[32]; u32 src; u32 dst; }   // 40 字节
_IOW(0xB5, 0x01, 40) = 0x4028B501     ✅ 与脚本中的常量一致
```

工具只读不写，不会给 modem 发数据。

**验证成功与否**（抽干 10 分钟）：

```sh
watch -n 30 'dmesg | grep -c "crash detected"'
sudo qmicli -d qrtr://0 --dms-get-operating-mode
```

- 计数不涨 + 保持 online → 把它做成 systemd 服务（`rpmsg_drain.py drain DIAG ... &`）
- 计数继续涨 → diag 不是唯一原因，还要处理 IPA

### 补：modem 的 glink 通路在 DT 里是齐的

主线 `sdm630.dtsi`（sdm660 继承）里 modem 节点：

```dts
remoteproc_mss: remoteproc@4080000 {
	compatible = "qcom,sdm660-mss-pil";
	reg = <0x04080000 0x100>, <0x04180000 0x40>;
	interrupts-extended = ... <&modem_smp2p_in 0..3>,
			      <&modem_smp2p_in 7>;   /* fatal/ready/handover/stop-ack */
	memory-region = <&mba_region>, <&mpss_region>, <&mdata_mem>;
	status = "disabled";                    /* clover-plus 里设成 okay */

	glink-edge {
		interrupts = <GIC_SPI 452 IRQ_TYPE_EDGE_RISING>;
		label = "modem";
		qcom,remote-pid = <1>;
		mboxes = <&apcs_glb 15>;
	};
};
```

**要点**：

1. glink-edge 是存在的（`label = "modem"`、pid 1、`apcs_glb 15`）
2. **但没有 `qcom,glink-channels`** —— 主线不预先建通道，
   通道要靠运行时**发现**（modem announce 或 AP 主动请求）
3. 所以"能不能抽干 DIAG"取决于设备上 `/sys/bus/rpmsg/devices/` 里到底有什么
   —— 这正是 `scripts/modem_diag_probe.sh` 第一步在查的东西

### 顺带确认：`0031` 补丁确实是冗余的

主线 `sdm660-xiaomi-clover-plus.dts` 自己就有：

```dts
&remoteproc_mss {
	firmware-name = "mba.mbn", "modem.mdt";
	status = "okay";
};
```

（非 Plus 的 clover 用 `modemnm.mdt`，名字不同。）

---

## 🎯 2026-10-29 05:15：实验结论（设备短暂上线时取得）

### 结论 1：ModemManager **不是元凶**（假设被推翻）

夜里把 ModemManager 停掉 + mask，然后观察：

```
ModemManager : inactive / masked
modem-online : active
operating    : 'shutting-down'      ← 还是掉了
注册         : 'not-registered-searching'
modem 崩溃   : 9 次  / uptime 26 分钟
```

**MM 完全不在场，modem 照样崩，26 分钟崩 9 次（约每 3 分钟一次）。**

⇒ 之前"MM 抢端口导致崩溃"的猜测**排除**。
⇒ 坐实了 §"综合结论"里的判断：**崩溃是 AP 侧缺 diag/IPA 服务导致的**。

### 结论 2：modem 的 glink 通道里**没有 DIAG**

在现场列出 `4080000.remoteproc`（modem）的全部 rpmsg 通道：

```
DATA1   DATA11  DATA2  DATA3  DATA4  DS
IPCRTR  LOOPBACK_CTL_MPSS  apr_apps2  apr_voice_svc
glink_ssr  rpmsg_ctrl
```

（`DATA1..DATA4`、`DS` 是 IPA/rmnet 数据通道，全部 unbound；
`IPCRTR` 被 `qcom_smd_qrtr` 绑定，这就是 qmicli 能工作的原因。）

**没有 `DIAG` 通道。**

⇒ 印证了 `dog_hb.c:266: Task starvation: diag`：
modem 侧的 diag 服务在等一个 AP 从没请求过的通道。

### 结论 3：主动请求 DIAG 通道的尝试（未完成）

用 `tools/rpmsg_drain.py drain DIAG 0 0` 主动创建端点：

- 第一次（前台）跑了 60 秒没返回 → 可能 ioctl 阻塞，也可能创建成功后进入读取循环
- 想加 `timeout 15` 重试时设备已因熄屏断网

**下次上机第一件事**：

```sh
cd mipad4plus
python tools/pad_run.py scripts/modem_diag_probe.sh --sudo     # 确认没有 DIAG
# 然后手动试（注意一定加 timeout，否则会挂住）：
sudo timeout 20 python3 /tmp/rpmsg_drain.py drain DIAG 0 0
```

观察点：`/dev/rpmsgN` 有没有新设备出现、`dmesg` 里 glink 有没有 "open channel" 日志。

### 4. ModemManager 要不要恢复？

它是被我做实验 mask 的，现在证明**它既不是元凶、也帮不上忙**（建不出 modem）。
恢复方法：

```sh
sudo systemctl unmask ModemManager && sudo systemctl start ModemManager
```

**建议先别恢复** —— 它只会反复抢端口刷日志，对功能没帮助。
等 diag 问题解决、modem 能稳定在线之后再说。

---

## ⛔ 2026-10-29 07:40：DIAG 实验**把平板弄死了**，永久放弃这条路

### 发生了什么

```
sudo timeout 20 python3 -u /tmp/rpmsg_drain.py drain DIAG 0 0
```

用 `src=0, dst=0` 这种伪造地址去调 `RPMSG_CREATE_EPT_IOCTL`，结果：

```
黑屏 + ping 不通 + SSH 不通
```

⇒ **内核级死锁**，只能长按电源 15 秒强重启。

### 为什么

- rpmsg/glink 的端点地址必须来自**已存在的通道**
  （`/sys/bus/rpmsg/devices/*/{src,dst}`），不能猜
- `rpmsg_ctrl` 的 ioctl 一旦在 glink 侧阻塞，持锁等待 → 整机 hang

### 结论：DIAG 这条路放弃

之前 §"方案 A" 写着"用 rpmsg_ctrl 接管 DIAG 通道"，**现在明确不可行**：

1. 通道列表里**根本没有 DIAG**（现场枚举过：只有 DATA1..4 / DS / IPCRTR / apr_* / glink_ssr）
2. 用伪造地址硬创 = 死机
3. 唯一正路是移植真正的 diagchar 驱动（工作量 1–2 周，且和主线 rpmsg 架构不匹配）

### 那 modem 还能救吗

| 方案 | 可行性 |
|---|---|
| ~~用户态抽干 DIAG~~ | ⛔ **已证明会死机，放弃** |
| 移植 diagchar 驱动 | 大工程，不建议 |
| 接受"modem 会周期性崩溃" | 目前唯一现实选项 |
| 4G 数据（IPA） | 独立大工程，不建议 |

⇒ **modem 这块到此为止**：能注册、能看信号，但不能稳定保持。
   想稳定用 4G 得走 Android（或等主线 IPA/diag 支持成熟）。
