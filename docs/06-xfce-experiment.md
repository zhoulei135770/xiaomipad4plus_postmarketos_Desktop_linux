# 06 · XFCE / Ubuntu 容器实验记录（2026-10-19 夜）

> 本文记录 pmOS 到手之后第一次"桌面化"尝试：在 Phosh 上叠加 Ubuntu 24.04 容器 +
> XFCE。结论是**这条路在架构上走不通**，但过程中解决了几个真问题（emergency mode、
> 根分区扩容、GPU 真相），数据也都留在这里。

---

## 0. TL;DR

| 结论 | 内容 |
|---|---|
| ✅ 成功的 | pmOS 正常启动、GPU 硬件加速（freedreno FD512）、触屏、Wi-Fi、SSH、根分区扩到 105.6 G |
| ✅ 成功的 | Ubuntu 24.04 容器可创建、apt 可用、**单个 X11 程序能在 Phosh 里显示** |
| ❌ 失败的 | **在 Phosh 上跑完整 XFCE 桌面**：Phosh 的 Xwayland 自带 root WM（`wlroots wm`），`xfwm4` 无法接管；`xfce4-panel` segfault、`xfdesktop` bus error |
| ⚠️ 失败但重要的 | 禁用 `zap-shader` 节点想绕过 GPU 固件缺失 → **secure boot panic，启动循环**（已回退） |
| 📊 性能 | 局域网 18 MB/s；WAN 直连国内源 0.33–0.4 MB/s；走代理 2.4 MB/s；内存 4 GB 是真正天花板 |
| 下一步 | 在 A/B/C 三条路线里选（见 §6） |

---

## 1. 设备与系统现状（写文档时）

```
型号      Xiaomi Mi Pad 4 Plus (clover-plus / sdm660)
系统      postmarketOS "Nura" edge (systemd)，UI = Phosh
内核      7.0.14-sdm660 #2-postmarketos-qcom-sdm660 aarch64
内存      3.6 GiB（4 GB 机型），zram swap 5.3 GiB
存储      /dev/mmcblk1p64，105.6 GB（已从 2.2 G 扩容），剩 ~98 G
电池      66%
网络      wlan0 192.168.1.123/24（Wi-Fi 已连）
SSH       ssh user@192.168.1.123  密码 <SUDO_PASSWORD>
GPU       freedreno FD512 / Mesa 26.2.5 / OpenGL ES 3.1（硬件加速）
触屏      Goodix GT9110（I2C 3-005d）
```

**开机日志里的 zap 报错是"假故障"**：

```
adreno 5000000.gpu: [drm:adreno_zap_shader_load] *ERROR* Unable to load a512_zap.mdt
msm_dpu: [drm:adreno_load_gpu] *ERROR* gpu hw init failed: -2
```

用户态第一次打开 render node 时驱动重试成功，最终 `phoc` 拿到的就是：

```
GL vendor: freedreno
GL renderer: FD512
Using OpenGL ES 3.1 Mesa 26.2.5
```

> 换句话说：**GPU 一直是好的**，那两行 ERROR 只影响首次初始化时序，不要被它误导。

---

## 2. 今晚做的事（时间线）

### 2.1 修 emergency mode（根因：fstab 里的 /boot）

现象：系统起在 initramfs/emergency 状态，屏幕提示
`You are in emergency mode ... root account is locked`，USB 网络通但 22 端口关闭。

根因：pmOS 完整磁盘镜像里有一个独立 `/boot` 分区，而我们是**只把 root 分区刷进
userdata**，设备上不存在那个 ext2 `/boot`，于是 `local-fs.target` 失败 → 进 emergency。

```fstab
# 修复前
UUID=8def993b-...  /            ext4  defaults           0 0
UUID=d563e6a5-...  /boot        ext2  nodev,nosuid,noexec 0 0

# 修复后（注释掉 /boot，因为 boot.img 直接刷在 boot 分区，不需要挂载）
#UUID=d563e6a5-... /boot        ext2  nodev,nosuid,noexec 0 0
```

操作方式：虚拟机里 `mount -o loop,rw` 改镜像 → 重新刷 userdata（UUID 不变，boot 不用动）。

> 关键经验：**pmOS 只刷 root 分区到 userdata 时，必须去掉 fstab 的 /boot 行**，
> 否则必进 emergency mode，而且 root 锁着无法登录。

### 2.2 根分区扩容

initramfs 没有自动 resize，手动做：

```bash
sudo resize2fs /dev/mmcblk1p64
# old_desc_blocks = 1, new_desc_blocks = 14
# The filesystem is now 28560215 (4k) blocks long  → 105.6 G
```

### 2.3 GPU 固件（last session 的坑，已解决）

`a530_pm4.fw` / `a530_pfp.fw` 原本不在 initramfs 里，内核早期请求失败。解决方式是在
chroot 里加清单后重建镜像：

```bash
# ~/.local/var/pmbootstrap/chroot_rootfs_xiaomi-clover/etc/mkinitfs/files/90-gpu-fw.files
/usr/lib/firmware/qcom/a530_pm4.fw
/usr/lib/firmware/qcom/a530_pfp.fw
/usr/lib/firmware/qcom/a530v3_gpmu.fw2
```

重建后日志出现 `loaded qcom/a530_pm4.fw from new location`。

### 2.4 失败的实验：禁用 zap-shader

想法：`a512_zap.mdt` 在这台机器的所有固件里都没有（vendor.img 2.0 G、system.img
3.0 G、NON-HLOS.bin 112 M 全搜过），而上游代码有 `-ENODEV` 的退路，于是把 DT 里
`zap-shader` 节点 `status = "disabled"`。

结果：**屏幕一闪就灭、USB 消失、启动循环**。原因——退路会写
`RBBM_SECVID_TRUST_CNTL`，这台机器 `androidboot.secureboot=1`，写该寄存器触发权限
异常 → panic。

> 已回退到可用 boot.img。**不要再试禁用 zap 这条路。**

### 2.5 容器栈：podman + distrobox

```bash
# Alpine 源卡住（mirror.postmarketos.org 404 / cdn 慢），换阿里云：
#   /etc/apk/repositories
#   https://mirrors.aliyun.com/alpine/edge/{main,community,testing}
sudo apk add podman distrobox        # podman 6.1.4, distrobox 1.8.2.5
# rootless 需要 subuid
echo "user:100000:65536" | sudo tee -a /etc/subuid /etc/subgid
```

镜像拉取（Docker Hub 直连超时，用 daocloud 镜像）：

```bash
podman pull docker.m.daocloud.io/library/ubuntu:24.04
```

### 2.6 容器里的 apt 源（三个坑）

1. **Docker Hub 的 IPv6 超时** → 用 `docker.m.daocloud.io`
2. **镜像里没有 ca-certificates** → HTTPS 源全部证书失败 → 改用 `http://`
3. **arm64 要用 ubuntu-ports** → `http://mirrors.aliyun.com/ubuntu-ports/`
   （用 `/ubuntu/` 会 404：`dists/noble/main/binary-arm64/Packages`）

最终 `/etc/distrobox-ubuntu.sources`：

```
Types: deb
URIs: http://mirrors.aliyun.com/ubuntu-ports/
Suites: noble noble-updates noble-backports noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

创建容器（把 GPU 设备透传进去）：

```bash
distrobox create --name ubuntu \
  --image docker.m.daocloud.io/library/ubuntu:24.04 \
  --additional-flags '-v /etc/distrobox-ubuntu.sources:/etc/apt/sources.list.d/ubuntu.sources:ro --device /dev/dri --group-add video' -Y
```

> 容器内普通用户**没有免密 sudo**（`sudo -n true` 失败）。装包要用：
> `podman exec -u 0 ubuntu bash -c 'apt-get install -y ...'`

### 2.7 XFCE 安装

```bash
podman exec -u 0 ubuntu bash -c 'export DEBIAN_FRONTEND=noninteractive; \
  apt-get install -y xfce4 xfce4-terminal dbus-x11 fcitx5 fcitx5-chinese-addons fonts-noto-cjk'
```

800 个包，25+ 分钟（Wi-Fi 到阿里云只有 0.33 MB/s，61 MB 的 `fonts-noto-cjk` 一个就
下了 3 分钟）。

---

## 3. XFCE 为什么起不来（核心）

### 3.1 试过的启动方式

```bash
# 第一把：DISPLAY 被 distrobox 设成 wayland-0
distrobox enter ubuntu -- bash -lc 'dbus-run-session -- xfce4-session'
# → xfwm4: cannot open display: wayland-0

# 第二把：显式 DISPLAY=:0
distrobox enter ubuntu -- bash -lc 'export DISPLAY=:0; dbus-run-session -- xfce4-session'
# → session 起来了（xfce4-session pid 40972），但 xfwm4/panel/desktop 都没起来

# 手动补窗口管理器
DISPLAY=:0 xfwm4 --replace
# → Waiting for current window manager (wlroots wm) on screen :0.0 to exit......

# 手动补面板/桌面
xfce4-panel   → Segmentation fault (core dumped)
xfdesktop     → Bus error (core dumped)
```

### 3.2 根因

Phosh 用的是 `phoc`（wlroots 合成器），它启动的 **Xwayland 自己带一个 root WM**，
在 X 里显示为 `"wlroots wm"`：

```
xwininfo -root -tree
  0x200004 "wlroots wm": ()  10x10+0+0
```

这个 root WM 不会退出，所以 `xfwm4 --replace` 永远等不到接管；而 XFCE 的会话管理
假定自己拥有窗口管理权，于是面板/桌面组件在初始化时崩溃（segfault / SIGBUS）。

**结论：不是配置问题，是架构冲突。** Phosh 的 Xwayland 只能跑"独立应用窗口"，不能
承载"一个自己的桌面会话"。

### 3.3 唯一验证成功的

单个 X11 程序可以正常显示：

```bash
DISPLAY=:0 xfce4-terminal     # 屏幕上确实出现窗口，用户已确认
```

所以 X11 通路是好的，缺的是"谁来做窗口管理"。

---

## 4. 性能实测（2026-10-19 23:00 左右）

### 4.1 网络

| 链路 | 实测 | 说明 |
|---|---|---|
| 平板 → 虚拟机（局域网，20 MB 文件） | **18 MB/s** | 平板的 Wi-Fi 本身很快 |
| 平板 → 阿里云（直连） | 0.33 MB/s | 1.7 MB 文件 5.23 s |
| 虚拟机 → 阿里云（直连） | 0.4 MB/s | 24 MB 跑满 60 s 超时 |
| 平板 → 阿里云（走 `192.168.1.151:16514` 代理） | 0.38 MB/s | 1.7 MB 文件 4.56 s，只快 13% |
| 走代理访问 GitHub | ~2.4 MB/s | 代理对国外资源快，对国内源没用 |

**结论：瓶颈是家里的 WAN 出口（约 0.4 MB/s），不是平板 Wi-Fi。**
虚拟机做 apt 缓存代理（`apt-cacher-ng` + 上游代理）理论上能把后续安装提到 2.4 MB/s。

### 4.2 内存 / CPU

| 项 | 值 |
|---|---|
| 物理内存 | 3.6 GiB（4 GB 机型） |
| 系统空闲占用 | ~1.0 GiB |
| Ubuntu 容器空闲 | ~187 MiB |
| zram swap | 5.3 GiB |
| GPU | freedreno FD512，GLES 3.1（硬件加速） |

---

## 5. 现在的状态怎么恢复

设备是好的，只是没桌面环境：

```bash
ssh user@192.168.1.123        # 密码 <SUDO_PASSWORD>

# 容器
podman ps -a                     # ubuntu 容器
podman exec -it ubuntu bash      # 进容器（root: podman exec -u 0 -it ubuntu bash）

# 清掉残留的 XFCE 进程（如果还占着）
pkill -x xfce4-session; pkill -x xfwm4
```

Phosh 桌面正常，触屏、Wi-Fi、SSH 都在。

---

## 6. 三条路线取舍

### A. Phosh 当桌面，直接跑 Linux 应用（改动最小）

- 做法：不装 XFCE 会话，只把 Firefox / LibreOffice / 终端当独立窗口跑
- 优点：今天就能验证；Phosh 本身就是为触屏设计的，虚拟键盘、手势都在
- 缺点：不是传统桌面（没有任务栏/面板、窗口管理靠 Phosh），多窗口体验弱
- 适合：只想"能写文档、上网"

### B. 换掉 Phosh，做真正的桌面（1–2 天）

- 做法：用 `labwc` / `sway` / `weston` 当合成器（或直接 Xorg + modesetting），
  上面跑 XFCE 组件；改 greetd 自动登录到新会话
- 优点：真正的桌面平板，窗口管理、面板、输入法都正常
- 缺点：要重做启动流程、HiDPI 缩放、输入法集成；`labwc`/`sway` 在 sdm660 上的
  稳定性未知
- 适合：确定要把这台机器当办公平板

### C. 原生 Debian rootfs（不建议）

- 做法：Debian arm64 rootfs + 现在的 pmOS 内核 + initramfs（Armbian 模式）
- 优点：没有容器层，最"正统"
- 缺点：pmOS 的设备集成（Wi-Fi/BT 固件、音频 UCM、面板时序、触屏配置）要自己搬；
  内核与用户态 mesa 要手动对齐；升级内核容易崩
- 结论：**收益小、风险高**，除非 B 也走不通

### 决策建议

```
只想"能写文档/上网"           → A（今天就能试）
要当主力办公平板              → B（明天做，先花 2 小时验证 labwc 能否跑起来）
追求"纯正 Debian"            → 不建议，除非你有时间维护
```

---

## 7. 未验证 / 待办

- [ ] labwc / sway 在 sdm660 + mainline 上能否稳定跑（B 路线的前置验证）
- [ ] 蓝牙键鼠配对（预期可用，wiki 标 Bluetooth works）
- [ ] USB OTG / hub（wiki 标 Broken，基本可以放弃）
- [ ] 音频（扬声器 / 麦克风，wiki 标 Partial）
- [ ] 休眠唤醒
- [ ] apt-cacher-ng 缓存代理（虚拟机侧，加速后续大包安装）
- [ ] 输入法（fcitx5 已装进容器，但没在桌面里验证过）

---

## 8. 附：今晚踩过的坑（速查）

| 现象 | 根因 | 处理 |
|---|---|---|
| emergency mode，console 锁死 | fstab 有 `/boot`，设备无此分区 | 注释掉 `/boot` 行，重刷 rootfs |
| 根分区只有 2.2 G | initramfs 未自动 resize | `resize2fs /dev/mmcblk1p64` |
| `gpu hw init failed: -2` 但桌面正常 | zap 失败非致命，用户态重试成功 | 不用管 |
| 禁用 zap → 启动循环 | secure boot 禁止写 `SECVID_TRUST_CNTL` | 回退 boot.img，不要再试 |
| `apk add` 卡死 10 分钟 | pmOS 镜像源不可用 | 换阿里云 Alpine 源 |
| Docker Hub 拉取超时 | IPv6 到 registry-1.docker.io 不通 | 用 `docker.m.daocloud.io` |
| apt 证书错误 | 镜像无 ca-certificates | 源改 `http://` |
| apt 404 arm64 | 用了 `/ubuntu/` 路径 | 改 `/ubuntu-ports/` |
| xfwm4 等不到 WM | Phosh Xwayland 自带 `wlroots wm` | 架构冲突，无解（见 §3） |

---

## 9. 中文化（2026-10-19 23:35 完成）

### 9.1 做了什么

```bash
# 1) 字体（72 MB 的包，走虚拟机代理下载再经局域网传过去，6 秒 + 4 秒）
#    VM: curl -x http://192.168.1.151:16514 -o /tmp/font-noto-cjk.apk \
#        https://mirrors.aliyun.com/alpine/edge/community/aarch64/font-noto-cjk-0_git20220127-r1.apk
#    VM → 平板: sshpass ... ssh user@192.168.1.123 "cat > /tmp/font.apk" < /tmp/font-noto-cjk.apk
sudo apk add --allow-untrusted /tmp/font.apk      # font-noto-cjk，30 个 CJK 字体

# 2) locale 支持
sudo apk add lang musl-locales

# 3) 会话语言
# /etc/environment 末尾追加
LANG=zh_CN.UTF-8
# 以及
mkdir -p ~/.config/environment.d
echo 'LANG=zh_CN.UTF-8' > ~/.config/environment.d/10-locale.conf

# 4) 重启生效
sudo reboot
```

### 9.2 验证结果

```
phoc 进程环境:  LANG=zh_CN.UTF-8
locale:        LANG/LC_CTYPE/LC_NUMERIC = zh_CN.UTF-8
fc-list :lang=zh → Noto Sans CJK SC/TC/HK/JP/KR
翻译包:        gtk30.mo / gtk40.mo / phosh-mobile-settings.mo（zh_CN）
```

**注意**：Phosh 主界面翻译覆盖率不是 100%，部分条目仍会是英文，这是上游翻译进度问题。

### 9.3 中文输入法（仍未解决）

| 场景 | 状态 |
|---|---|
| 蓝牙键盘 + fcitx5 | ✅ 可行（容器里已装 `fcitx5` + `fcitx5-chinese-addons`） |
| 纯触屏打中文 | ❌ **Phosh 的虚拟键盘（squeekboard / stevia）不支持拼音输入**，只能外接键盘或换桌面（B 路线） |

用法（容器内，X11 程序）：

```bash
podman exec -it ubuntu bash
export DISPLAY=:0 GTK_IM_MODULE=fcitx QT_IM_MODULE=fcitx XMODIFIERS=@im=fcitx
fcitx5 -d        # Ctrl+空格 切换中英文
```

### 9.4 中文化踩的坑

| 现象 | 根因 | 处理 |
|---|---|---|
| `apk add font-noto-cjk` 卡在 Downloading 后失败 | 72 MB × 0.4 MB/s，下载中断 | 虚拟机走代理下载 → SSH 管道传过去 → `apk add --allow-untrusted` |
| 虚拟机没有 `scp` | 只装了 ssh 客户端 | 用 `ssh "cat > /tmp/x" < 本地文件` 代替 |
| panel segfault / desktop SIGBUS | 同上 | 同上 |
