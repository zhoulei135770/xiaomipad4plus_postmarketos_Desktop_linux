# 41 — Modem 与 GPS：为什么这颗 SoC 的定位必须靠 modem

- 日期：2026-10-29
- 结论：**GPS 依赖 modem 的 QMI LOC 服务；modem 起不来，且在运行时强行启动会把整机挂死。**

---

## 1. 关键事实：这颗 SoC 没有独立 GNSS

SDM660 的 GNSS 是 **modem（MSS）固件内部的 QMI LOC 服务**，不是独立 GPS 芯片。

内核里的 `CONFIG_GNSS` 那几个驱动（`GNSS_MTK_SERIAL` / `GNSS_SIRF_SERIAL` /
`GNSS_UBX_SERIAL` / `GNSS_USB`）都是给**外置** GNSS 模块用的，
本机全部未启用，也没有 `/dev/gnss*`：

```
$ ls /sys/class/gnss/
（空）
```

因此：**没有 modem，就没有 GPS。**

---

## 2. 当前 modem 状态

```
remoteproc0 = adsp    running
remoteproc1 = 4080000.remoteproc   available 但从未 boot
remoteproc2 = cdsp    running
```

启动日志里完全没有 modem 引导过程（没有 MBA 加载、没有 handover），
只有一行：

```
[30.88] remoteproc remoteproc1: 4080000.remoteproc is available
```

### 2.1 为什么不启动

驱动源码 `drivers/remoteproc/qcom_q6v5_mss.c`：

```c
rproc->auto_boot = false;      /* 硬编码，DT 属性无法覆盖 */
```

整个 `drivers/remoteproc/` 目录里，q6v5_mss **不读** `qcom,auto-boot`，
所以往 DT 里加这个属性没有任何效果（这是我先前的误判之一）。

### 2.2 设备树与固件其实是齐的

```
compatible    = qcom,sdm660-mss-pil
firmware-name = "mba.mbn", "modem.mdt"
qcom,halt-regs / memory-region / qcom,smem-states / glink-edge   全部存在
```

固件也都在（由 msm-firmware-loader 从 vendor 分区提供）：

```
/run/msm-firmware-loader/target/mba.mbn      238256 B
/run/msm-firmware-loader/target/modem.mdt      8412 B
/run/msm-firmware-loader/target/modem.b00..b05
```

### 2.3 缺的属性

| 属性 | 状态 | 影响 |
|---|---|---|
| `qcom,auto-boot` | 缺失 | 驱动不读，加了也没用 |
| `qcom,qmp` | 缺失 | 驱动视为可选（`-ENODEV` 可容忍），但缺了就少一路 AOP 电源投票 |
| AOSS QMP 节点 | **我们 DT 里根本没有** | 想加 `qcom,qmp` 得先补这个节点 |

---

## 3. 致命问题：运行时启动 modem 会挂死整机

```
$ echo start > /sys/class/remoteproc/remoteproc1/state
→ 屏幕冻结，SSH 断开，无任何内核日志残留
```

journal 里在挂死前后**一条日志都没有**（最后一条停在 12:34，挂死发生在 12:47），
说明是总线级硬挂死，连 printk 都写不出来。

相关线索：

```
gcc-sdm660 100000.clock-controller: sync_state() pending due to 4080000.remoteproc
```

GCC 一直在等 modem 投票；modem 一启动就会触发时钟树 finalize，
这一步很可能与 DPU/NoC 的死锁有关。

### 3.1 为什么难查

- 没有串口（UART）→ 挂死时拿不到任何输出
- `pstore`/`ramoops` 已挂载但是空的 → 硬挂死不触发 panic，抓不到 dump
- 每次尝试的代价是整机强制重启

---

## 4. 结论与建议

| 方案 | 可行性 | 说明 |
|---|---|---|
| 修 modem（进而拿到 GPS） | 低 | 需要串口 + 内核级调试；每次尝试都会挂死整机 |
| 外置 GNSS（USB/蓝牙模块） | **高** | gpsd 直接可用，与 modem 无关 |
| 网络定位（geoclue） | 中 | 已安装，精度依赖 Mozilla 定位服务可用性 |
| 暂时搁置 | — | 平板定位需求通常可用手机热点/网络定位代替 |

**建议**：没有串口之前不要再尝试启动 modem。
每次尝试只能得到一次强制重启，学不到任何新信息。

---

## 5. 已做的无害整理

`ModemManager.service` 之前被我软链到 `/dev/null` 屏蔽过（`masked`），
现已恢复：

```
[ -L /etc/systemd/system/ModemManager.service ] && rm -f /etc/systemd/system/ModemManager.service
systemctl unmask ModemManager
systemctl start ModemManager
```

`mmcli -L` 输出 `No modems were found` —— 符合预期（modem 未 boot）。

---

## 6. 如果将来要动 modem，先准备这些

1. **串口**：需要拆机找 UART 测试点（通常是主板上的几个焊盘）
2. 串口就绪后，先只做 `echo start`，把完整输出抓下来
3. 拿到输出后再判断是时钟、SMMU 还是 XPU 的问题
4. 在此之前，任何 DT/驱动改动都是盲改
