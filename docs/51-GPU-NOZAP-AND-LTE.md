# 51 — GPU nozap 尝试失败 + LTE 射频实测 + 稳定性取舍

- 日期：2026-10-30 12:40
- 结论：**横屏已稳定并持久化；GPU 的 nozap 刷机尝试失败已回滚；LTE 射频能注册但 modem 固件会崩，暂时保持关闭以保稳定。**

---

## 1. GPU nozap：失败，已用 fastboot 恢复

### 做了什么
用当前 `/boot/boot.img` 生成 nozap 镜像（只删 DTB 里的 `zap-shader` 节点，
内核 gz 和 ramdisk 原样，`kernel_size` 相应 -64 字节），校验通过后写入 p12。

### 结果
- 重启后**无法启动**：屏幕黑、WiFi 不上线、ping 不通。
- 说明只删 DTB 节点这条路在这台机器上不可行（至少这个 DTB 重打包方式不可行），
  或者 GPU 走 `SECVID_TRUST_CNTL` 时直接把启动卡死。

### 恢复
用 fastboot 刷回**刷机前的原镜像**：
```
fastboot flash boot mipad4plus\backup\device-boot\boot.img   # md5 55C7BCE4…
fastboot reboot
```
原镜像与刷机前 p12 逐字节一致（md5 相同），刷回后系统、横屏、触摸全部正常。

### 结论
- **没有串口/显示调试通道之前，不再尝试改 boot 分区。**
- GPU 仍是原状：启动时 `a512_zap.mdt` 加载失败，`gpu hw init failed: -2`；
  桌面继续走 llvmpipe。GPU 的 debugfs/GL 一律不碰（会整机卡死，需物理断电）。

---

## 2. LTE 射频：能注册，但 modem 固件会崩

### 已验证可用
```
qmicli -d qrtr://0 --dms-get-ids          → IMEI 868225041565635
qmicli -d qrtr://0 --dms-set-operating-mode=online
qmicli -d qrtr://0 --nas-get-serving-system
    Registration state: 'registered'   CS: attached   PS: attached
    Selected network: '3gpp'           Radio: lte
qmicli -d qrtr://0 --nas-get-signal-strength
    Network 'lte': -63 ~ -64 dBm
qmicli -d qrtr://0 --uim-get-card-status
    Card state: 'present'
```
也就是说 **ModemManager 看不到它（QRTR-only），但 QMI 本身完全可用，射频和 SIM 都正常**。

### 为什么不能一直开着
设成 online 后，modem 固件很快开始崩：
```
ipa_util.c:1089:IPA Assert: ipa_util.imm_cmd.clients[cmd_handle].init_done ==
err_qdi.c:459:EX:wlan_process:1:WLAN RT:1089:PC=b00c7394   （每 ~6 s）
dog_hb.c:266:Task starvation: diag, ping: 4 ...
```
每次崩溃都会重启 MPSS，并**连带把 ath10k/WCN3990 固件带崩**：
```
ath10k_snoc 18800000.wifi: firmware crashed!
```
WiFi 随之掉线且不一定能自愈。

根因还是 **主机侧没有 IPA（IPA v3.1）驱动**，modem 的 IPA 客户端初始化失败后进入异常循环。
（旧安装里 LTE 射频能稳定工作，说明当时的 kernel/DT 有对应处理；当前 Nura edge 没有。）

### 受控“晚设 online”实验（12:49，已做完）
假设是看护脚本设得太早才崩，于是做了对照：开机 9 分钟后、崩溃循环已停（fatal=2），
只设一次 online，然后 5 分钟不打扰。结果：

| t | mode | fatal | wlan0 |
|---|---|---|---|
| 0 | shutting-down → 设 online 成功 | 2 | UP |
| 30s | **shutting-down** | 3 | UP |
| 60s | shutting-down | 8 | **DOWN** |
| 90s | shutting-down | 13 | DOWN |
| 150s | shutting-down | 18 | DOWN |

结论：**只要设 online，IPA 断言就会触发，modem 必然进入崩溃循环并带崩 WiFi**，
和设的早晚无关。旧安装能稳，说明旧 kernel/DT 对 modem 的 IPA 客户端有不同处理，
当前 Nura edge 内核没有这套处理。

### 最终取舍
- `ModemManager`：**disabled**（它看不到 modem，重启它还会重置 modem、带崩 WiFi）。
- `modem-online` 看护脚本：**disabled**（避免 online 后进入崩溃循环）。
- modem 保持 boot 默认的 `shutting-down`：**不开机崩溃循环、WiFi 稳定**。
- QMI 仍然可用（读 IMEI/SIM/信号、扫网），只是不注册。
- 想临时看射频：手动 `qmicli --dms-set-operating-mode=online`，
  接受 WiFi 可能被带崩、需要重启的事实。

### IPA 移植的门槛（为什么不建议现在做）
| 缺的东西 | 说明 |
|---|---|
| `ipa-shared` 基址/大小 | 厂商 DT 只给 ipa-base + bam-base，主线要 3 段 |
| SMP2P 条目 | 主线要 `ipa-clock-query`/`ipa-setup-ready`，本机没有 `smp2p-mpss` |
| `memory-region` | IPA 固件加载的预留内存，大小未知 |
| 寄存器布局 | 厂商 0x4effc 与主线 v3.1 预期不同 |
| 刷机通道 | DT 在 boot 镜像里，每次迭代都要刷 p12；12:05 的 nozap 尝试已演示一次“刷完不启动” |

预计 5-15 次内核构建迭代，且每次失败都要 fastboot 救砖。**没有串口控制台之前不再刷 boot。**

---

## 3. 本次踩到的两个网络坑

1. **ath10k 固件崩了之后，WiFi 不会自己回来**：
   `nmcli connection up daan` 可以救（固件还活着时）；固件已死就重启。
2. **USB hub 有线网可用**：插上后 `eth0` 自动 DHCP（192.168.1.101），
   在 WiFi 挂掉时是可靠的救命通道。当前 TypeC/OTG 在这台 Nura edge 上是开箱可用的。

---

## 4. 当前稳定配置（2026-10-30 12:55，重启后验证）

| 项 | 状态 |
|---|---|
| 显示 | fbdev + 自编旋转驱动，1920×1200 横屏（持久化） |
| 触摸 | libinput 校准矩阵 `0 -1 1 1 0 0`（udev 自动） |
| WiFi | wlan0 已连 daan，192.168.1.100 |
| 有线 | eth0 192.168.1.101（hub） |
| 服务 | tablet-autorotate / tablet-touch-rotate / ModemManager / modem-online 均 disabled |
| modem | shutting-down，本 boot fatal=0（不设 online 就不崩），QMI 可用 |
| GPU | 未初始化（原状），不碰 |

回滚横屏：见 [50-LANDSCAPE-FBDEV.md](50-LANDSCAPE-FBDEV.md) §7。
