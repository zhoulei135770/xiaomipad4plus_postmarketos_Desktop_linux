# 电量图标不显示：一个启动竞态

> 2026-11-02。现象：面板上电量图标时有时无，最后彻底消失。
> 结论：**不是 UPower 坏了，也不是电量计掉了**，是 `tablet-battery-sni` 和 `lxqt-panel` 抢跑。

---

## 1. 为什么需要 `tablet-battery-sni`

这台机器的 `qcom-battery` 只暴露这几个属性：

```
capacity  voltage_now  current_now  temp  status  present  technology
charge_full_design
```

**没有 `charge_full`、`charge_now`、`charge_counter`、`health`。**

UPower 拿不到电量，算出来是 **0 Wh**，LXQt 自带的电池插件就显示不出来。所以改用
`tablet-battery-sni`（一个 StatusNotifierItem）直接读 sysfs，自己画百分比。

## 2. 症状

面板托盘里没有电量图标。但：

```sh
ps -eo pid,args | grep tablet-battery-sni      # 进程活着
busctl --user list | grep BatterySni           # 总线名被占着
```

查 watcher 的注册列表，只有 4 项，**没有电池**：

```sh
busctl --user call org.kde.StatusNotifierWatcher /StatusNotifierWatcher \
  org.freedesktop.DBus.Properties Get ss \
  org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems
# v as 4 ":1.18/...nm_applet" ":1.49/..." ":1.51/...blueman" ":1.53/..."
```

## 3. 根因

看 PID 顺序：

```
810   python3 /usr/local/bin/tablet-battery-sni
1254  lxqt-panel
```

**电量图标比面板先启动。** 它注册的时候，面板的 `StatusNotifierWatcher` 还没起来。

而脚本原本是这样写的：

```python
def register():
    try:
        watcher = bus.get_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
        watcher.RegisterStatusNotifierItem(name, dbus_interface="org.kde.StatusNotifierWatcher")
        print("registered", name, flush=True)
    except dbus.DBusException as e:
        print("register failed:", e, flush=True)
    return False                      # ← 失败也是 False

GLib.timeout_add(300, register)       # 返回 False = 不再调用
```

`GLib.timeout_add` 的回调返回 `False` 就**只执行一次**。注册失败之后没有任何重试，
于是这个进程一直活着、一直占着总线名，但永远不会出现在托盘里。

## 4. 修复

失败时返回 `True`，让 GLib 每 300ms 重试，直到面板起来、注册成功为止：

```python
    except dbus.DBusException as e:
        print("register failed:", e, flush=True)
        return True                   # ← 重试
    return False
```

改完 `/usr/local/bin/tablet-battery-sni`，重启进程即可：

```sh
kill $(pgrep -f "^python3 /usr/local/bin/tablet-battery-sni")
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/10000/bus \
  setsid nohup python3 /usr/local/bin/tablet-battery-sni >/tmp/sni.log 2>&1 &
```

> ⚠️ 别用 `pkill -f tablet-battery-sni`——你自己的 ssh 命令行里也含这个字符串，
> 会把当前会话一起杀掉。用 `^` 锚定开头，或者 `pgrep` 拿到 pid 再 kill。

## 5. 验证

```sh
$ cat /tmp/sni.log
registered org.tablet.BatterySni

$ busctl --user call org.kde.StatusNotifierWatcher /StatusNotifierWatcher \
    org.freedesktop.DBus.Properties Get ss \
    org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems
v as 5 "...nm_applet" "...:1.49" "...blueman" "...:1.53" "org.tablet.BatterySni/StatusNotifierItem"
                                                                 ↑ 出现了
```

面板托盘里出现电量数字。重启后也会自动恢复——因为现在会一直重试到面板起来。

## 6. 排查时排除掉的

| 怀疑对象 | 检查 | 结果 |
|---|---|---|
| `upower` 没起 | `systemctl is-active upower` | `active`、`enabled` |
| UPower 里没有电池设备 | `upower -e` | 有 `battery_qcom_battery` |
| 电量计驱动挂了 | `capacity` 能不能读 | 能读，数字在变 |
| 图标画不出来 | 字体 | `DejaVuSans-Bold.ttf` 在 |
| SNI 注册成功但面板不显示 | watcher 列表 | **根本没注册** ← 真因 |

---

## 附：同一次排查发现的另一个 bug（未修）

`tablet-touch-rotate` 每秒报错一次：

```
[touch] loop error: [Errno 2] No such file or directory: 'xinput'
```

它调用 `xinput list` / `xinput set-prop` 做触摸标定，但：

1. 这是 **X11** 工具，而桌面是 **Wayland（labwc）**；
2. Debian 上根本没装 `xinput`。

结果就是每秒 spawn 一个必然失败的进程，日志刷屏，**触摸标定实际没生效**。

pmOS 那边是用 libinput 的 udev 矩阵做的（`99-goodix-landscape.rules` +
`LIBINPUT_CALIBRATION_MATRIX`），Debian 这份直接搬了 X11 版本过来。

待办：要么在 Debian 上禁用它，要么改写成 libinput/Wayland 方式。
