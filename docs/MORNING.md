# 早上好 —— 今晚的成果与验证步骤

## 一句话

**自检 17/17 全部通过**。今晚修好后摄、新增 3 个驱动功能（OTG 供电 / ALS 环境光 / 霍尔翻盖），
指纹做到了**厂商 TEE 的逐字节复刻**，只差你按一下手指验证。

---

## 醒来后请按顺序试（约 5 分钟）

```sh
# 1. 全硬件自检 —— 应该 17 passed, 0 failed
sudo pad_selftest

# 2. 指纹（关键！）按住手指直到提示
sudo pad_fp_check
#    sd > 10  → 成功采到脊线，指纹通了
#    sd < 3   → 仍平坦

# 3. 环境光 —— 拿手电照一下平板顶部，读数应该变大
sudo pad_als 3

# 4. 霍尔 —— 拿磁铁靠近（或合上保护套）
sudo pad_hall

# 5. OTG 供电 —— 拔掉充电器后
sudo pad_otg on && sudo pad_otg     # usbin_v 应从 ~0V 升到 ~5V
```

---

## 今晚做了什么

### ✅ 后摄 OV13855 从"0 字节"修好
补丁 0048 给 camss 加了 `port@2`，打乱 CSI 端口编号 → 后摄连不上 csiphy0。
移除后 **16,558,080 字节全分辨率采集 PASS**。

### ⚠️ OTG 供电 —— 原来已经实现了（我一度重复造轮子）
`0010-power-supply-qcom-smbx-add-otg-vbus-control.patch`（10 月 25 日）**早就**提供了
`otg_vbus`，而且比我后来写的版本更完整（它会先设 `OTG_EN_SRC` = 命令寄存器）。
我写的 0074 已删除，`pad_otg` 现在走 `otg_vbus`。
新增的只是 **`usbin_v` ADC 电压读数**这个验证手段（免插设备就能判断有没有 5V 输出）。

### ⚠️ ALS 环境光 —— 原来就是可用的
ADSP 报的 `Capella CM3232 ALS` 挂在 `qcom-smgr-prox` 名下，**`tablet-autobright` 一直在用它**。
之前自检报 "ALS not readable" 是**脚本误判**（它找 `in_illuminance_raw`，而 smgr 驱动是纯 buffer 型）。
我一度把它改名成 `qcom-smgr-light`（补丁 0075），那会**打断自动亮度**，已撤销。
现在新增的是 `pad_als` 读取器（两种设备名都认），用来单独验证 ALS 读数。

### ✅ 霍尔/翻盖（补丁 0076）—— 这个确实是新的
`ROHM BU52061NVX Hall Effect` 没有任何驱动认领。复用 prox 驱动绑定
`qcom-smgr-hall-effect` → 新增 `qcom-smgr-hall` 设备（0=开盖，1=合盖）+ `pad_hall`。

### ✅ 系统清洁
- 禁用两个必然失败的 systemd 单元（`qcom-modem` 冗余、`usb-signaller` 需 gadget）
- 加 `/etc/modules-load.d/tablet-sensors.conf` 修开机传感器加载竞态
- **失败单元：0**

### 🔧 指纹（重大进展，待你验证）
用 Ghidra 完整反编译了厂商 TEE（1466 个函数），从中解出真正的采集实现：

| 项 | 之前（照公开驱动猜）| 现在（厂商 TA）|
|---|---|---|
| FINGER_DRIVE_CONF | 0x02 | **0x14** |
| ADC_SHIFT_GAIN | 0x1002 | **0x0000** |
| PXL_CTRL | 0x0F0A | **0x0A0F** |
| PXL_RST_DLY | 0x0F | **0x0A** |
| **0x68 SAMPLE_PX_DLY** | 8 字节 | **9 字节**（第 9 字节一直没写！）|
| IMG_CAPT_SIZE | 0x9001（无效）| **00 08 00 B0 = [0,8,0,176]** |
| 图像 | 36865 字节 | **11266 字节（64×176）** |
| 模拟使能 | 从未写 | **0x94/0xEC/0xAC/0xDC/0xD8 读-改-写** |

用户态 `fingerprint.py` 也已适配 64×176（selftest 通过）。

---

## 仍未解决

| 项 | 状态 | 说明 |
|---|---|---|
| **前摄 s5k5e8** | ❌ 硬件 | 电源/时钟/复位/引脚/CCI 时序全正常，i2c 总线零应答 |
| **venus 视频解码** | ⏳ | 原厂固件能启动（pc_ready=1），但 HFI 不握手；已排除 5 个假设 |
| 指纹图像 | 待验证 | 若 `pad_fp_check` 仍平坦，软件侧已到极限 |

---

## 资产

```
RESUME-HERE.md (66 节)               完整记录
MORNING.md / /root/MORNING.md        本文件
tools/fpc_decomp.c (2.5 MB)          指纹 TA 完整反编译
tools/boot-r181.img                  当前 boot
backup/work-20261028-1700.zip        最新备份（27.2 MB）
```

## 设备命令一览

```
sudo pad_selftest     全硬件自检（17 项）
sudo pad_fp_check     指纹单帧 + sd 分析
sudo pad_fp_vendor_setup  厂商序列四组合
sudo pad_fp_rrs_sweep     RRS 候选值扫描
sudo pad_als [n]      环境光读数
sudo pad_hall [watch] 霍尔/翻盖
sudo pad_otg on|off   OTG 供电（含电压读数）
sudo pad_cam_config.sh 后摄 pipeline
```

## 重要教训（避免踩坑）

1. **不能热重载 `qcom_smbx`** —— rmmod+modprobe 会直接重启设备
2. **不能热卸载 `fpc1020`** —— IRQ 未释放时会挂死
3. CCI 驱动是**模块**，只刷 boot 镜像不会更新它
4. Ghidra 脚本必须 `import ghidra.app.script.GhidraScript;`，否则报 cannot find symbol
5. 指纹 TA 的 `0x68` 是 **9 字节**、`0x90`/`0xD8`/`0xEC` 也远比 FPC1020 宽

---

## ⚠️ 12:00 事故：设备卡在 suspend（需要你按电源键）

我在无人值守时测试了休眠，设备进入了 suspend 但 **RTC 唤醒没生效**，现在失联。

**恢复**：按一下电源键；若无反应则长按 10~15 秒强制断电再开机。

开机后请执行 `sudo pad_selftest` 确认 17/17。

**所有成果都已落盘，重启不会丢失。**
以后 suspend 测试必须你在旁边时做。
