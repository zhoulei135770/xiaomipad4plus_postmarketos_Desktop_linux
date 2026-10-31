# 57 — 原厂内核反编译工具链（VM + REA + Ghidra）

> 目的：在没有 IDA、Windows 上 Ghidra 又不支持 raw arm64 的情况下，用 **VM** 做 aarch64 反编译。
> 本文件记录环境、关键发现和可复现的命令。

---

## 1. 关键发现：我们从没拿到过“解压后的内核”

`artifacts/rom/vendor-kernel.bin` 与 `vendor-kernel.decompressed` **是同一个文件**（13,674,192 字节），
且：

- 前 `0x800` 字节全 0；
- `0x800` 开始是 `1f 8b 08 00` = **gzip**；
- 全文件没有 `Linux version` / `ARM\x64` 魔数。

→ 它是从 boot 镜像里切出来的**压缩片段**，`.decompressed` 只是同名复制。

**正确解压**（`tools/vendor_gunzip.py`，zlib `16+MAX_WBITS`，从 `0x800` 开始）：

```
decompressed size 42,301,460
magic@0x38  = ARMd
text_offset = 0x80000        image_size = 0x2ddf000     flags = 0xa
Linux version @ 0x137f00f
```

得到 `build/vendor-kernel.raw.img`（42.3 MB 真 Image）。
**VA 映射：`va = 0xffff800010080000 + file_offset`**（`text_offset=0x80000`，基址 `0xffff800010000000`）。

## 2. VM 上的 REA 环境（已固化）

VM：`192.168.1.200`（user / <VM_PASSWORD>），Ubuntu 22.04，node 22.20，npm 10.9.3，
**Ghidra 12.1.4 在 `/opt/ghidra_12.1.4_PUBLIC`**，能直连 npm registry。

```bash
npx -y rea-agents@6.7.0 --help          # 首次运行会装到 /usr/local/bin/rea
export GHIDRA_INSTALL_DIR=/opt/ghidra_12.1.4_PUBLIC   # 已写进 ~/.bashrc
rea doctor                              # ghidra: ok / ghidra-platform: ok
```

辅助脚本（已在 VM 上，`~/rea-tools/`）：

| 脚本 | 作用 |
|---|---|
| `disasm.sh <elf> <start> <stop>` | `llvm-objdump -d` 线性反汇编（最可靠） |
| `decomp.sh <file> <entry> [arch]` | `rea decompile` 并只打印伪代码 |

## 3. 可复现流程

### 3.1 反汇编任意地址（推荐）

```bash
# 1) 在主机上切窗口（tools/vendor_carve.py），2) 包成最小 ELF（tools/elf_wrap.py）
#    elf_wrap.py <bin> <elf> <base_va>
# 3) 上传到 VM 后：
llvm-objdump -d --start-address=0xffff800010d88600 --stop-address=0xffff800010d88720 ipa_win.elf
```

为什么需要 ELF 包装：VM 上的 `objcopy` 不支持 `aarch64`、`llvm-objdump` 不接受 `-b binary`；
`tools/elf_wrap.py` 手工写一个 ELF64 头（`EM_AARCH64`、一个 `PT_LOAD` R+X）即可。

### 3.2 伪代码

```bash
rea analyze  <file> --target-format raw-binary --architecture arm64 --entry-point 0x...
rea decompile <file> 0x... --target-format raw-binary --architecture arm64 --entry-point 0x...
```

**坑**：对“切片窗口”做 raw 导入时，Ghidra 的函数识别不可靠（常见 `halt_baddata`、
把整个窗口当成一个 `entry`）。要么给**足够大的窗口**、要么给**真正的函数起点**，
要么老老实实用 `llvm-objdump` 线性反汇编。

## 4. 已做过的定位（供下一步参考）

- 主机侧 `ADRP+ADD` 扫描（`tools/vendor_xref2.py`）：在真 Image 上找到 35 处
  `core_clk`/`smmu_clk` 引用，其中 `smmu_clk`（IPA 专属）位于：
  `file 0xd08664 / 0xd08798` → `va 0xffff800010d88664 / 0xffff800010d88798`。
- 对 `0xffff800010d88664` 附近的线性反汇编已经能读到真实代码，例如：

```
ffff800010d8865c: mov  w9, #0x3c78
ffff800010d88660: ldr  x19, [x20, #0xb0]
ffff800010d88664: adrp x1, ...            ; 时钟名字符串
ffff800010d88668: add  x1, x1, #0xda4
ffff800010d8866c: mov  w10, #1
ffff800010d88670: strb w10, [x8, x9]      ; 置位
ffff800010d88674: mov  x0, x19
ffff800010d88678: bl   0xffff800010e8c778  ; 疑似 clk_get(dev, "…_clk")
```

尚未确认这段就是 IPA 驱动（没有符号）。**下一步优先事项**：从 Image 里恢复 **kallsyms**
（`kallsyms_names/token_table` 压缩表），拿到 `ipa_probe`、`ipa_power_init`、`clk_*` 的地址后，
所有分析都会变得直接。

## 5. 快速核对清单

- [x] VM 上 `rea doctor` → ghidra ok
- [x] 原厂内核正确解压 + VA 映射确定
- [x] 可对任意地址出汇编（ELF 包装法）
- [x] 可出伪代码（raw 导入，注意函数边界）
- [ ] kallsyms 恢复（下一步）
- [ ] 用符号核对 IPA 驱动的时钟/电源序列
