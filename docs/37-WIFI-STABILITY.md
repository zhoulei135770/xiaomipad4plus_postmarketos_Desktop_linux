# WiFi 稳定性修复（WCN3990 固件崩溃循环）

> 2026-10-29 11:50。症状：WiFi 隔一阵断一下，几秒后自己回来。
> 现在：开机后 1 次（连接瞬间），之后长时间 0 次。

---

## 1. 症状与证据

内核日志里固件**周期性崩溃**，每次启动 5 次以上：

```
ath10k_snoc 18800000.wifi: firmware crashed! (guid 6c9bbf89-...)
ath10k_snoc 18800000.wifi: failed to update channel list: -108
ath10k_snoc 18800000.wifi: failed to set 2g txpower 60: -108
ath10k_snoc 18800000.wifi: failed to setup powersave: -108
ath10k_snoc 18800000.wifi: device successfully recovered
```

`-108` 是 `ESHUTDOWN`——表示发命令时固件**已经死了**，这些是"死后余波"，
不是原因。真正的时间线是：崩溃 → 一堆 -108 → 平台恢复 → 看门狗重连 → 再崩。

两条关键线索：

```
ath10k: invalid MAC address; choosing random      ← MAC 无效，用了随机值
ath10k: board_file api 2 bmi_id N/A crc32 00000000
```

---

## 2. 排查过程

| 假设 | 检查 | 结论 |
|---|---|---|
| 板级校准数据缺失 | `board-2.bin` 有 480KB、`bdwlan.*` 在 vendor 分区 | crc32=0 是 SNOC 的正常显示，**不是原因** |
| 供电缺失 | DT 里 l5/l6/l9/l19 四路齐全 | **不是原因** |
| 固件版本 | `firmware-5.bin` 只是 60 字节版本头，真固件走 QMI 从 vendor 加载 | 版本 1.0.0.531，无处可换 |
| **MAC 随机化** | ath10k 报 MAC 无效 → 用随机 MAC；NM 默认**每次扫描再随机化** | ✅ **是主因** |
| **省电模式** | 日志反复出现 `failed to setup powersave` | ✅ 加剧问题 |
| **管制域未设** | `iw reg get` 初始为空，触发 `update channel list` | ✅ 加剧问题 |

---

## 3. 修复（三项组合，缺一不可）

### 3.1 关闭 MAC 随机化 + 省电

`/etc/NetworkManager/conf.d/99-wifi-stability.conf`：

```ini
[device]
wifi.scan-rand-mac-address=no

[connection]
wifi.powersave=2
```

### 3.2 管制域 + 省电（运行时状态，需每轮重设）

写进已有的看门狗脚本 `/usr/local/lib/wifi-watchdog.sh`（每分钟跑一次，幂等）：

```sh
iw reg set CN 2>/dev/null || true
[ -d /sys/class/net/wlan0 ] && iw dev wlan0 set power_save off 2>/dev/null || true
```

这样即使重启、挂起恢复，也会自动重新应用。

### 3.3 已有基础（之前做过，保留）

- `/etc/NetworkManager/conf.d/99-wifi-powersave-off.conf`
- `wifi-watchdog.timer`：每分钟检查，掉线自动重连

---

## 4. 效果

| | 修复前 | 修复后 |
|---|---|---|
| 开机后崩溃次数 | 5+ | **1**（仅连接瞬间） |
| 连续 4 分钟新增崩溃 | 每 6 秒一次 | **0** |
| 链路 | 反复断 | -32 dBm / 866 Mbps / 稳定 |

---

## 5. 相关文件

```
/etc/NetworkManager/conf.d/99-wifi-stability.conf     MAC 随机化 + 省电
/usr/local/lib/wifi-watchdog.sh                        管制域 + 省电 + 重连
/etc/systemd/system/wifi-watchdog.timer                每分钟触发
/run/wifi-watchdog.log                                 看门狗日志
```

## 6. 仍未根治的部分

固件本身（vendor 1.0.0.531）在**连接瞬间**仍会崩一次，随后恢复。
要彻底消除需要：

1. 用厂商 `bdwlan.bin` + `ath10k-bdencoder` 重新打包匹配本机 board_id 的
   `board-2.bin`（当前用的是通用 480KB 文件）
2. 或换用更稳定的 WCN3990 固件版本（需从其他 SDM660 机型的 vendor 分区提取）

目前的表现已经达到"日常可用"——连续使用不再看到断线。
