# 今晚交接（2026-10-27 夜 → 10-28 中午）

> 这一夜约 34 轮，重点在**指纹攻坚**、**修后摄**、**传感器补齐**、**自查纠错**。
> 本文是浓缩版；细节见 `RESUME-HERE.md` 第 55~69 节。

---

## 一、当前设备状态

```
boot r181（当前已刷）
模块：fpc1020 r188 → r196 已构建待装（寄存器顺序修正版）
      qcom_smgr_prox r195 已构建待装（霍尔，prox 名字不变）
      qcom_smbx r195 已构建待装（otg_vbus）
自检：最后一次运行 17/17 PASS
```

⚠️ **设备当前卡在 suspend**（我远程测试休眠导致，RTC 唤醒未生效）。
需要**按一下电源键**；若无反应则长按 10~15 秒强制断电再开机。
所有成果都已落盘，重启不会丢失。

---

## 二、今晚的真实成果（已核实）

### ✅ 后摄 OV13855 修复
`0048-arm64-dts-clover-front-camera-endpoint.patch` 给 camss 加了 `port@2`，
打乱 CSI 端口编号 → 后摄连不上 csiphy0。移除后 **16,558,080 字节采集 PASS**。

**禁止**再加 camss 的 `port@2`。

### ✅ 霍尔/翻盖传感器（补丁 0076，新的）
ADSP 报 `ROHM BU52061NVX Hall Effect`，mainline 无驱动。
复用 smgr prox 驱动绑定 `qcom-smgr-hall-effect` → `qcom-smgr-hall` 设备（0/1）。
读取器 `pad_hall`（非阻塞 + select，因为该传感器只在状态变化时发样本）。

### ✅ 开机失败单元清零
- `qcom-modem.service` 冗余（remoteproc1 上电自动 running）→ disable
- `usb-signaller.service` 需要 gadget → disable + **mask**
- `/etc/modules-load.d/tablet-sensors.conf` 修传感器模块加载竞态

### 🔧 指纹：厂商 TEE 逐字节复刻（重大进展，待手指验证）
Ghidra 完整反编译厂商 TA（1466 函数），解出真正的采集实现：

| 项 | 之前（公开驱动）| 现在（厂商 TA）|
|---|---|---|
| `0x8C` FINGER_DRIVE_CONF | 0x02 | **0x14** |
| `0xA0` ADC_SHIFT_GAIN | 0x1002 | **0x0000** |
| `0xA8` PXL_CTRL | 0x0F0A | **0x0A0F** |
| `0x6C` PXL_RST_DLY | 0x0F | **0x0A** |
| `0x78` | 未写 | **0x0000** |
| `0x90` FINGER_DRIVE_DLY | 0x18（1B）| **3f×4 00×4（8B）** |
| `0x68` SAMPLE_PX_DLY | 8 字节 | **9 字节** `01 3f 3f 3f 14×5` |
| `0x54` IMG_CAPT_SIZE | 0x9001 | **00 08 00 B0 = [0,8,0,176]** |
| 图像大小 | 36865 | **11266（64×176+2）** |
| `0x94/0xEC/0xAC/0xDC/0xD8` | 未写 | **读-改-写模拟使能位** |
| 写入顺序 | 配置→0x54 | **0x54→0x5C→配置→使能**（按 TA）|

用户态 `fingerprint.py` 已适配 176×64（`FP_W`/`FP_H` 可覆盖），selftest 通过。

---

## 三、⚠️ 我今晚犯的两个错误（已纠正）

### 1. OTG 补丁重复
`0010-power-supply-qcom-smbx-add-otg-vbus-control.patch` **10 月 25 日就存在**，
提供 `otg_vbus` 且包含设置 `OTG_EN_SRC` 的步骤。
我写的 `0074`（`otg_power`）是重复实现且**少了设置源那一步**。
→ 已删除 0074，`pad_otg` 改用 `otg_vbus`。

### 2. ALS 改名打断了自动亮度
`tablet-autobright` 早已工作，读的是 `qcom-smgr-prox` 的 buffer（CM3232 挂这个名）。
我的 `0075` 把它改名成 `qcom-smgr-light` → 自动亮度会失效。
→ 已撤销 0075。

**另外**：`pad_selftest` 之前报"ALS not readable"是**误判** ——
它找 `in_illuminance_raw`，而 smgr 驱动是纯 buffer 型。ALS 一直是可用的。

### 3. 远程 suspend 测试
在无人值守时测试休眠，RTC 唤醒没生效，设备失联至今。
**教训：suspend 只能人在旁边时测。**

---

## 四、设备恢复后立刻做（3 分钟）

```sh
# 1. 安装三个模块并重启
cp fpc1020-r196.ko.zst        /usr/lib/modules/7.0.14-sdm660/kernel/drivers/input/misc/fpc1020.ko.zst
cp qcom_smgr_prox-r195.ko.zst /usr/lib/modules/7.0.14-sdm660/kernel/drivers/iio/proximity/qcom_smgr_prox.ko.zst
cp qcom_smbx-r195.ko.zst      /usr/lib/modules/7.0.14-sdm660/kernel/drivers/power/supply/qcom_smbx.ko.zst
reboot

# 2. 验证
sudo pad_selftest      # 期望 17/17
sudo pad_als 3         # 手电照一下，读数应变大
sudo pad_hall          # 磁铁靠近应变 1
sudo pad_otg on        # 拔掉充电器，usbin_v 应升到 ~5V

# 3. 指纹（关键）
sudo pad_fp_check      # 手指按住，sd > 10 = 通
```

---

## 五、仍无解的三项

| 项 | 结论 | 证据 |
|---|---|---|
| **前摄 S5K5E8** | 硬件 | 电源/时钟/复位/引脚/CCI 全正常，i2c 零应答 |
| **venus 硬解** | 未解 | 原厂固件能启动（pc_ready=1），HFI 不握手；已排除固件版本/表头/超时/寄存器/发包版本 5 项 |
| **4G 数据** | mainline 缺口 | 缺 IPA 固件 |

---

## 六、踩坑清单（重要）

1. **不能热重载 `qcom_smbx`** —— 会直接重启设备
2. **不能热卸载 `fpc1020`** —— IRQ 未释放会挂死
3. CCI 驱动是**模块**，只刷 boot 镜像不更新它
4. Ghidra 脚本必须 `import ghidra.app.script.GhidraScript;`
5. 指纹芯片寄存器**比 FPC1020 宽得多**：0x68=9B、0x90=8B、0xD8=10B、0xEC=5B
6. **改驱动前先 grep 现有补丁**，先读历史文档
7. **suspend 不要远程测**

---

## 七、关键文件

```
RESUME-HERE.md          69 节完整记录
MORNING.md              打开就能照着做的 5 步验证
HANDOVER-TONIGHT.md     本文件
tools/fpc_decomp.c      指纹 TA 完整反编译（2.5 MB，可全文搜索）
tools/fpc1020.c         我们的指纹驱动（现为厂商实现）
tools/ghidra_DumpDecomp.java  反编译脚本
backup/work-20261028-*.zip    每轮备份
```
