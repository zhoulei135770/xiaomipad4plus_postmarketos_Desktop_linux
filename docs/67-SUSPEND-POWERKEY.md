# 67 — 电源键 / 锁屏 / 休眠：现状与设计

> 10-31。用户问"锁屏和休眠结合按键是不是还没解决"。结论：**是"用禁用+替代方案解决"的**，
> 真正没解决的只有**内核真休眠**。

## 1. 设计（当前生效）

| 项 | 实现 | 位置 |
|---|---|---|
| 真休眠 | **完全禁用** | 三个 target masked；`/etc/systemd/sleep.conf.d/00-clover-suspend-safety.conf` 里 `AllowSuspend=no` |
| logind 电源键/睡键 | **ignore** | `/etc/systemd/logind.conf.d/{90-clover-powerkey,90-no-idle,91-no-suspend}.conf` |
| 电源键 | **自研守护进程** `tablet-powerkeyd` | `/usr/local/bin/tablet-powerkeyd` + systemd 单元 |
| 休眠替代 | **伪休眠** `tablet-sleep` | 关背光 + DPMS Off + 停帧 |
| 锁屏 | **没有**（无密码锁） | 电源键只关背光 |
| 唤醒 | 电源键任意键 / 触摸 / 键盘鼠标 | `tablet-powerkeyd` 监听所有 input 设备 |

### 为什么电源键不交给 logind

所在这版 systemd **拒绝** `HandlePowerKey=lock-session`（报 `Invalid argument`），
所以用 `HandlePowerKey=ignore` + 自研 daemon。

### 为什么不能真休眠

`mdss_runtime_suspend` 会让内核硬挂死（CPU5 被锁，watchdog trace 记录在
`/var/log/mdss-suspend-bug.txt`）。历史上两次远程 suspend 测试都导致设备失联，
只能物理按电源键恢复。

```
clk_branch_toggle -> clk_core_disable -> mdss_runtime_suspend [msm]
  -> mdss_pm_suspend -> device_suspend -> dpm_suspend -> pm_suspend
```

修复方向（上游）：suspend 前先 `drm_atomic_helper_suspend()`（主线后来的做法），
或让 msm/DPU 的 `runtime_suspend` 不要直接关时钟。

## 2. 伪休眠 `tablet-sleep`

```
tablet-sleep          # 关背光 + DPMS off（瞬间）
tablet-sleep wake     # 恢复
tablet-sleep status   # 查看状态
```

- 优点：**零风险**、瞬间唤醒、背光与渲染都停；
- 缺点：CPU 仍在跑（约 1–2 W），不是真休眠的 0.1 W 级。

## 3. 电源键 `tablet-powerkeyd`

- 短按：面板在「关背光 / 点亮」之间切换；
- 任意输入（触摸、键盘、鼠标）：面板若关着则点亮；
- 状态从 DRM connector 读取（因为 `xset q` 永远显示 `Monitor is On`）。

## 4. 仍然没解决的

1. **真休眠**（内核 DPU 死锁）——需要上游修复；
2. **锁屏/安全锁**——当前无锁屏；若要需要另装 locker（会和自动登录冲突）。

## 5. 若要测真休眠（危险，必须人在旁边）

```sh
sudo systemctl unmask sleep.target suspend.target
sudo sh -c 'echo +30 > /sys/class/rtc/rtc0/wakealarm'   # 先设 RTC 闹钟
sudo systemctl suspend
# 30 秒内无响应 = 死锁，长按电源键 10 秒硬重启
```

⚠️ 历史上 RTC 闹钟**并不能唤醒**这台机器（只有电源键能），所以务必人在旁边。
