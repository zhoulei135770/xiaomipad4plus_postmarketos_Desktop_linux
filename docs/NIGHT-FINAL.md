# 夜间工作最终状态（2026-10-29 04:00）

> 用户睡觉期间的自主工作，共 13 轮。这份是收尾清单。

---

## ✅ 完成的

| # | 成果 | 证据 |
|---|---|---|
| 1 | **TA 反编译环境打通** | TA 是 ARM32；多段 ELF；Ghidra 1513 个函数；完整 API 名表 |
| 2 | **采集函数反编译** | `FUN_00045654`：0xC0+IRQ0x20、{0xC4,0}、图像从 buf+2 |
| 3 | **驱动 v11**（img_skip + 参数生效）| 已编译；v10 已部署 |
| 4 | **指纹天花板定性** | 原始帧与 Android 等价；二维自相关 0.82/0.04；交织假设全排除 |
| 5 | **前摄根因** | 0032/0048 两个补丁没进 APKBUILD；设备 DT 证据吻合 |
| 6 | **前摄补丁重做并接好** | 0032 失效 → 重做为 0053；APKBUILD 已改（44 source / 46 checksum）|
| 7 | **完整构建实测** | 两个补丁都 patch 成功；构建失败是磁盘满，不是补丁 |
| 8 | **modem 开机自愈** | systemd 服务已装、已验证（CMCC -62 dBm）|
| 9 | **CPU 频率/电压表** | 从厂商 DTB 解出 silver 8 档 / gold 7 档，含电压 |
| 10 | **CPU 调频真实门槛** | 要 OSM/APM 驱动（主线没有），不是补 OPP 表 |
| 11 | **ACDB 音频分析** | 141 条 device→acdb_id；扬声器无保护限幅的风险 |
| 12 | **4G/IPA 澄清** | ipa_fws 存在；主线无 sdm660 端点表；modem 会 IPA 断言 |
| 13 | **文档体系** | INDEX（分类）+ MORNING-BRIEF（一页纸）+ 零坏链 |

---

## ⚠️ 未完成 / 受环境限制

| 项 | 原因 |
|---|---|
| 内核重编验证到底 | **VM 磁盘 100% 满**（74G/77G）。补丁本身已验证可用；需先 `pmbootstrap zap -n` 腾 14 G |
| 前摄实际出图 | 要刷入新内核（等用户在） |
| 短信验证 | 需要带 WMS 的 qmicli 或给 ModemManager 一个 QMI 端口 |
| TA 的 0x54 编码 / FIFO 布局 | **已证明从镜像里取不到**（运行时常量），只能靠动态调试 TEE |

---

## VM 磁盘现状（04:15）

```
清理前： 77G 74G   0   100%    ← 构建在这里 Bus error
清理后： 77G 72G 1.4G    99%    ← 已删 ccache（1.3 G，可再生）
```

**仍然不够编内核**（需要约 8–10 G）。占用：

| 目录 | 大小 | 能否删 |
|---|---|---|
| `chroot_native` | 14 G | ✅ `pmbootstrap zap -n`（下次构建重建）|
| `chroot_rootfs_xiaomi-clover` | 7.3 G | ⚠️ 设备 rootfs 环境，删了要重新装 |
| `cache_apk_*` | 1.2 G | ✅ `pmbootstrap zap -c` |
| `cache_distfiles` | 249 M | ✅ 会重新下载 |

**我没有替你删 chroot** —— 那是你的工作环境，什么时候删由你决定。
## ⚠️ 设备上有两处改动需要你知道

| 改动 | 位置 | 恢复方法 |
|---|---|---|
| modem 开机服务 | `/etc/systemd/system/modem-online.service` | `sudo sh patches/install-modem-online.sh --remove` |
| **ModemManager 被 mask** | `systemctl mask ModemManager` | `sudo systemctl unmask ModemManager && sudo systemctl start ModemManager` |

Mask ModemManager 是夜里做"它是不是元凶"的判定实验，**结论还没取完**（WiFi 挂了连不上）。
明早先看 `qmicli --dms-get-operating-mode`，再决定要不要恢复它。
## 明早第一件事

> 所有命令都在 **`mipad4plus/`** 目录下执行（脚本用相对路径）。

```sh
# 0. 一键体检（只读，10 秒）——列出 modem / 前摄 / 指纹 的当前状态
python tools/pad_run.py scripts/morning_check.sh --sudo

# 1. 腾磁盘（VM）
pmbootstrap zap -n

# 2. 重编内核
pmbootstrap build --arch aarch64 --force linux-postmarketos-qcom-sdm660

# 3. 刷 boot，然后验证前摄（一条命令出结论）
python tools/pad_run.py scripts/frontcam_verify.sh --sudo
```

三种结果对应三种结论见 [26-FRONT-CAMERA-DIAGNOSIS.md](26-FRONT-CAMERA-DIAGNOSIS.md) §10.5。

---

## 设备当前状态

```
modem    online，注册 CMCC，LTE -62 dBm，开机自启已配置
指纹     v10 模块（img_skip=2），参数默认
电量     85% 充电中
uptime   数小时，无异常重启
```

---

## 写文档的教训（本轮新增）

1. **别信"看起来像"的结论** —— 我夜里两次把"已经修好的东西"当成新发现
   （前摄供电轨、0032 补丁），都是因为没先查现有补丁列表
2. **验证要跑真东西** —— 实跑一次编译才发现 0032 已失效、磁盘已满
3. **别用 `grep '\.patch$'`** 找 source 列表（会匹配到校验行）

详见 [INDEX.md](INDEX.md) §6。

## 夜里抓到的第三个教训（工程类）

**假通过比报错更危险。**

`tools/check_links.py` 最初写死了 `glob('mipad4plus/*.md')`。
从仓库根跑是对的，但从 `mipad4plus/` 里跑时匹配到 0 个文件，
却照样输出 `broken links: 0` —— 看起来一切正常。

现在所有分析脚本都改成以脚本自身位置为基准：

```python
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

并且 `check_links.py` 会打印 `checked N files`，N=0 时直接报错退出。

---

## 设备短暂上线时取得的实验结果（补）

夜里设备恢复过两次网络，抢到了两个结论：

| 实验 | 结果 |
|---|---|
| **ModemManager 是不是元凶？** | ❌ **不是**。mask 掉 MM 后，26 分钟里 modem 仍崩 **9 次**，照样掉回 shutting-down |
| **modem 有没有 DIAG 通道？** | ❌ **没有**。通道只有 `DATA1..4 / DS / IPCRTR / apr_* / glink_ssr` |

⇒ 崩溃原因锁定：**AP 侧没有 diag 消费者 + 没有 IPA**，modem 固件等不到就崩。
MM 的嫌疑排除，可以不恢复（它建不出 modem，只会刷日志）。

唯一没跑完的：主动请求 DIAG 通道（`rpmsg_drain.py drain DIAG 0 0` 挂住 60 秒，
加 timeout 重试时设备已熄屏断网）。下次上机第一件事就是它。

详见 [22-LTE-CALL-SMS-OTG.md](22-LTE-CALL-SMS-OTG.md) 最后一节。

---

## 🚧 状态：离线可做的已全部完成，剩余被外部条件阻塞

### 已经做完的（不需要你也在场）

- 指纹：TA 反编译环境、采集序列、0x54 值定案、配置机制、天花板定性
- 前摄：根因定位 + 补丁接进 APKBUILD + 构建实测 + 验证脚本
- modem：开机服务、崩溃机制、MM 假设排除、DIAG 通道缺失证据
- CPU：完整频率电压表 + OSM 驱动缺口分析
- 音频/传感器/IPA：结论齐备
- 文档：13 份当前权威 + 索引 + 三件套体检全绿

### 被阻塞的三件事（都需要你或设备）

| 事项 | 为什么现在做不了 |
|---|---|
| **前摄验证** | 需要编内核 + 刷 boot。血泪教训 #7：**绝不在无人值守时刷机** |
| **指纹实验** | 需要你按手指；且你明确说了不做耗电/按手指的实验 |
| **modem DIAG 实验** | 设备熄屏后 WiFi 挂起，SSH 连不上；`rpmsg_drain.py drain DIAG 0 0` 还没跑完 |
| **TA 再深入** | 需要动态调试 TEE（安全世界），主线内核做不到 |

### 你醒来后最短路径

```sh
cd mipad4plus

# 1. 体检（10 秒，只读）
python tools/pad_run.py scripts/morning_check.sh --sudo

# 2. 如果 modem 又是 shutting-down：跑 DIAG 探测
python tools/pad_run.py scripts/modem_diag_probe.sh --sudo
sudo timeout 20 python3 /tmp/rpmsg_drain.py drain DIAG 0 0     # 一定要加 timeout

# 3. 前摄（需要刷机，你在场时做）
pmbootstrap zap -n
pmbootstrap build --arch aarch64 --force linux-postmarketos-qcom-sdm660
python tools/pad_run.py scripts/frontcam_verify.sh --sudo
```
