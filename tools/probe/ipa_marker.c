// SPDX-License-Identifier: GPL-2.0
/*
 * ipa_marker.c - staged IPA bring-up probe with a p12-tail log block.
 *
 * Why: touching the IPA register window (0x14780000) hard-hangs this device
 * and there is no serial console, so printk is lost.  Every step below is
 * appended to an in-memory log, and the whole log block is written to the
 * last 1024 bytes of /dev/mmcblk1p12 (the 64 MiB "boot" partition; the boot
 * image ends well below that) and fsync'ed BEFORE the next risky operation.
 * After a hang + power cycle the block tells us the last step that ran.
 *
 * stage: 0  marker channel only (no IPA at all)
 *        1  find platform device          14780000.qcom,ipa
 *        2  clk_get(dev, "core")
 *        3  clk_set_rate + clk_prepare_enable
 *        4  ioremap IPA window + readl sanity from GCC
 *        5  read IPA VERSION (0x34)        <-- the risky one
 *
 * wmode: 0  kernel_write() + vfs_fsync()
 *        1  call_usermodehelper("sh -c 'printf ... | dd ...'")
 */

#include <linux/init.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/kernel.h>
#include <linux/sprintf.h>
#include <linux/string.h>
#include <linux/slab.h>
#include <linux/fs.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/dma-mapping.h>
#include <linux/dmaengine.h>
#include <linux/completion.h>
#include <linux/elf.h>
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/platform_device.h>
#include <linux/timekeeping.h>
#include <linux/umh.h>
#include <linux/interconnect.h>
#include <linux/firmware.h>
#include <linux/soc/qcom/mdt_loader.h>
#include <linux/firmware/qcom/qcom_scm.h>

#ifdef HAVE_SCM_MP_UNLOCK
extern int qcom_scm_mp_unlock(phys_addr_t phys, size_t len);
extern int qcom_scm_mp_unlock_legacy(phys_addr_t phys, size_t len);
extern int qcom_scm_is_call_available(u32 svc, u32 cmd);
#endif

#define MARK_PATH	"/dev/mmcblk1p12"
#define MARK_SEEK	131056		/* sector 131056 = byte 67100672 */
#define MARK_OFF	((loff_t)MARK_SEEK * 512)
#define MARK_LEN	1024		/* last two 512-byte sectors */

#define IPA_PA		0x14780000UL
#define IPA_NAME	"14780000.qcom,ipa"
#define IPA_VER_OFF	0x34
#define GCC_PA		0x100000UL
#define IPA_WIN		0x1000
#define GCC_WIN		0x1000

static int stage;
module_param(stage, int, 0444);
MODULE_PARM_DESC(stage, "0=marker 1=dev 2=clk_get 3=clk_on 4=ioremap+sanity 5=read VERSION 6=aperture sweep");

static int wmode;
module_param(wmode, int, 0444);
MODULE_PARM_DESC(wmode, "0=kernel_write+fsync 1=usermodehelper dd");

static int clk_hz = 75000000;
module_param(clk_hz, int, 0444);
MODULE_PARM_DESC(clk_hz, "IPA core clock rate to request before enabling");

static int sanity = 1;
module_param(sanity, int, 0444);
MODULE_PARM_DESC(sanity, "read a GCC register first to prove readl() works");

static int icc_kbps;
module_param(icc_kbps, int, 0444);
MODULE_PARM_DESC(icc_kbps, "vote this bandwidth (kB/s) on the IPA interconnect path before M5 (0=skip)");

static int skip_core;
module_param(skip_core, int, 0444);
MODULE_PARM_DESC(skip_core, "do not enable the 'core' clock (only 'smmu'), for clock-dependency tests");

static char mtext[MARK_LEN];
static size_t mlen;
static char *mpay;
static struct file *mmark;

static void mput(const char *fmt, ...)
{
	va_list args;
	int n;

	if (mlen + 2 >= MARK_LEN)
		return;
	va_start(args, fmt);
	n = vscnprintf(mtext + mlen, MARK_LEN - mlen - 2, fmt, args);
	va_end(args);
	mlen += n;
	mtext[mlen++] = '\n';
	mtext[mlen] = '\0';
}

static int mopen(void)
{
	if (mmark)
		return 0;
	mmark = filp_open(MARK_PATH, O_RDWR | O_LARGEFILE, 0);
	if (IS_ERR(mmark)) {
		int err = PTR_ERR(mmark);

		mmark = NULL;
		pr_err("ipa_marker: open %s: %d\n", MARK_PATH, err);
		return err;
	}
	return 0;
}

static int mflush_wr(void)
{
	loff_t pos = MARK_OFF;
	ssize_t n;

	n = kernel_write(mmark, mpay, MARK_LEN, &pos);
	if (n != MARK_LEN) {
		pr_err("ipa_marker: kernel_write -> %zd\n", n);
		return n < 0 ? (int)n : -EIO;
	}
	return vfs_fsync(mmark, 1);
}

static int mflush_umh(void)
{
	char *argv[4] = { "/bin/sh", "-c", NULL, NULL };
	char *envp[] = { "HOME=/", "PATH=/sbin:/bin:/usr/sbin:/usr/bin", NULL };
	char *cmd;
	size_t i;
	int ret;

	cmd = kmalloc(MARK_LEN + 160, GFP_KERNEL);
	if (!cmd)
		return -ENOMEM;

	for (i = 0; i < MARK_LEN; i++)
		mpay[i] = i < mlen ? mtext[i] : ' ';
	mpay[MARK_LEN - 1] = '\n';

	scnprintf(cmd, MARK_LEN + 160,
		  "printf '%%s' \"%s\" | dd of=%s bs=512 seek=%d count=2 conv=fsync 2>/dev/null",
		  mpay, MARK_PATH, MARK_SEEK);
	argv[2] = cmd;
	ret = call_usermodehelper(argv[0], argv, envp, UMH_WAIT_PROC);
	kfree(cmd);
	return ret;
}

static int mflush(void)
{
	int ret;

	ret = mopen();
	if (ret)
		return ret;

	memset(mpay, 0, MARK_LEN);
	memcpy(mpay, mtext, mlen < MARK_LEN ? mlen : MARK_LEN);

	if (wmode == 0)
		ret = mflush_wr();
	else
		ret = mflush_umh();

	if (ret)
		pr_err("ipa_marker: flush(wmode=%d) ret=%d\n", wmode, ret);
	return ret;
}

/* append one line, persist the block, echo to dmesg */

static void ipa_dma_done(void *arg)
{
	complete((struct completion *)arg);
}

static void mstep(const char *fmt, ...)
{
	va_list args;
	int n;

	if (mlen + 2 >= MARK_LEN)
		return;
	va_start(args, fmt);
	n = vscnprintf(mtext + mlen, MARK_LEN - mlen - 2, fmt, args);
	va_end(args);
	mlen += n;
	mtext[mlen++] = '\n';
	mtext[mlen] = '\0';

	pr_info("IPA-MARK: %s", mtext + mlen - n - 1);
	mflush();
}

static int __init ipa_marker_init(void)
{
	struct device *dev;
	struct clk *clk;
	struct clk *clk2;
	unsigned long win = IPA_WIN;
	void __iomem *ipa = NULL;
	void __iomem *gcc;
	u32 val;
	int ret = 0;

	mpay = kmalloc(MARK_LEN + 1, GFP_KERNEL);
	if (!mpay)
		return -ENOMEM;

	mstep("BEGIN stage=%d wmode=%d clk_hz=%d sanity=%d icc=%d ts=%llu",
	      stage, wmode, clk_hz, sanity, icc_kbps, ktime_get_real_seconds());

	if (stage <= 0) {
		mstep("M0 marker channel ok (no IPA touched)");
		goto out;
	}

	if (stage == 25) {
		/* Dump the ramoops region (0x9fe00000, 1 MiB) to /tmp so the
		 * previous (failed) kernel's console log can be recovered.
		 */
		const phys_addr_t pa = 0x9fe00000UL;
		const size_t len = 0x100000;
		void *m;
		loff_t pos = 0;
		struct file *f;
		ssize_t n;

		m = memremap(pa, len, MEMREMAP_WB);
		if (!m) {
			mstep("memremap(0x%llx) FAILED", (u64)pa);
			goto out;
		}
		f = filp_open("/tmp/ramoops.bin",
			      O_WRONLY | O_CREAT | O_TRUNC, 0600);
		if (IS_ERR(f)) {
			mstep("open /tmp/ramoops.bin failed %ld", PTR_ERR(f));
		} else {
			n = kernel_write(f, m, len, &pos);
			vfs_fsync(f, 0);
			filp_close(f, NULL);
			mstep("dumped %zd bytes to /tmp/ramoops.bin", n);
		}
		memunmap(m);
		goto out;
	}

	if (stage == 28) {
		static const u32 q[][2] = {
			{ 0x0c, 0x10 },	/* the vendor IPA unlock */
			{ 0x0c, 0x01 },	/* MP video var */
			{ 0x0c, 0x00 },
			{ 0x0a, 0x01 },	/* PIL */
			{ 0x7f, 0x7f },	/* bogus control */
		};
		unsigned int i;

		for (i = 0; i < ARRAY_SIZE(q); i++)
			mstep("avail svc=0x%02x cmd=0x%02x -> %d",
			      q[i][0], q[i][1],
			      qcom_scm_is_call_available(q[i][0], q[i][1]));
		goto out;
	}

	if (stage == 30) {
		/* Read IPA registers through the BAM DMA engine, bypassing the
		 * CPU master's access rules.  A failed transfer just errors out
		 * (no CPU stall), so this is safe to try.
		 */
		static const unsigned long offs30[] = { 0x34, 0x0, 0x0 };
		struct dma_chan *ch;
		dma_cap_mask_t mask;
		void *buf;
		dma_addr_t dma;
		unsigned int i;

		dma_cap_zero(mask);
		dma_cap_set(DMA_MEMCPY, mask);
		ch = dma_request_channel(mask, NULL, NULL);
		if (!ch) {
			mstep("S30 no DMA channel");
			goto out;
		}
		buf = dma_alloc_coherent(ch->device->dev, 64, &dma, GFP_KERNEL);
		if (!buf) {
			mstep("S30 dma alloc failed");
			dma_release_channel(ch);
			goto out;
		}
		mstep("S30 channel ok, reading IPA regs via BAM");

		for (i = 0; i < 2; i++) {
			struct dma_async_tx_descriptor *tx;
			struct completion done;
			long left;

			memset(buf, 0, 64);
			init_completion(&done);
			tx = dmaengine_prep_dma_memcpy(ch, dma,
					(dma_addr_t)(IPA_PA + offs30[i]), 4,
					DMA_CTRL_ACK);
			if (!tx) {
				mstep("S30 prep failed +0x%lx", offs30[i]);
				continue;
			}
			tx->callback = ipa_dma_done;
			tx->callback_param = &done;
			dmaengine_submit(tx);
			dma_async_issue_pending(ch);
			left = wait_for_completion_timeout(&done, msecs_to_jiffies(2000));
			if (!left)
				mstep("S30 +0x%lx DMA TIMEOUT", offs30[i]);
			else
				mstep("S30 +0x%lx = 0x%08x", offs30[i],
				      *(u32 *)buf);
		}
		dma_free_coherent(ch->device->dev, 64, buf, dma);
		dma_release_channel(ch);
		goto out;
	}

	if (stage == 27) {
		/* Control experiment: SVC_MP is also used by the venus driver
		 * (MP_VIDEO_VAR).  If this succeeds, the MP service is open to
		 * APPS and only cmd 0x10 is special.
		 */
		int r = qcom_scm_mem_protect_video_var(0x1000, 0x1000,
						       0x2000, 0x1000);

		mstep("mem_protect_video_var ret=%d", r);
		goto out;
	}

	if (stage == 24 || stage == 26) {
#ifdef HAVE_SCM_MP_UNLOCK
		/* Reproduce the vendor's ipa3_tz_unlock_reg(): build 28-byte
		 * descriptors {addr, addr, size, 0xC00311} and ask TZ (SCM_SVC_MP
		 * cmd 0x10) to unlock them, then read VERSION.
		 */
		/* 28-byte entry, verified against the vendor disassembly:
		 * {u64 addr; u64 addr; u64 size; u32 flags;} = 8+8+8+4
		 */
		struct unlock_desc {
			u64 addr;
			u64 addr2;
			u64 size;
			u32 flags;
		} __packed *desc;
		phys_addr_t phys;
		void __iomem *reg;
		int r;

		/* TZ can only address 32-bit physical memory -> force DMA32 */
		desc = kmalloc(sizeof(*desc), GFP_KERNEL | GFP_DMA32);
		if (!desc) {
			mstep("kmalloc FAILED");
			goto out;
		}
		memset(desc, 0, sizeof(*desc));
		desc->addr = 0x14780000UL & ~0xFFFUL;
		desc->addr2 = desc->addr;
		desc->size = 0x4effc;
		desc->flags = 0x000C0311;
		phys = virt_to_phys(desc);
		mstep("desc phys=0x%llx size=0x%x", (u64)phys, desc->size);

		r = (stage == 26)
			? qcom_scm_mp_unlock_legacy(phys, sizeof(*desc))
			: qcom_scm_mp_unlock(phys, sizeof(*desc));
		mstep("qcom_scm_mp_unlock ret=%d", r);
		if (r) {
			mstep("unlock failed -> NOT reading registers");
			kfree(desc);
			goto out;
		}

		reg = ioremap(IPA_PA, IPA_WIN);
		if (reg) {
			mstep("unlocked! VERSION=0x%08x",
			      ioread32(reg + IPA_VER_OFF));
			iounmap(reg);
		}
		kfree(desc);
#else
		mstep("stage24 needs kernel patch (HAVE_SCM_MP_UNLOCK)");
#endif
		goto out;
	}

	if (stage == 23) {
		/* Ask TZ to read the registers for us.  If TZ can read them but
		 * the AP cannot, the block is XPU-protected rather than dead.
		 * Zero risk: no direct MMIO from the AP.
		 */
		unsigned int v;
		int r;

		v = 0;
		r = qcom_scm_io_readl(0x100000UL, &v);
		mstep("TZ read GCC+0x0    ret=%d val=0x%08x", r, v);

		v = 0;
		r = qcom_scm_io_readl(0x14784000UL, &v);
		mstep("TZ read GSI+0x0    ret=%d val=0x%08x", r, v);

		v = 0;
		r = qcom_scm_io_readl(0x14780034UL, &v);
		mstep("TZ read IPA+0x34   ret=%d val=0x%08x", r, v);

		v = 0;
		r = qcom_scm_io_readl(0x14780000UL, &v);
		mstep("TZ read IPA+0x0    ret=%d val=0x%08x", r, v);
		goto out;
	}

	if (stage == 22) {
		/* Vote all three vendor ICC paths, then read VERSION.
		 * Requires DT interconnects = memory/imem/config.
		 */
		static const char *const names[] = { "memory", "imem", "config" };
		struct device *idev = bus_find_device_by_name(&platform_bus_type,
							      NULL, IPA_NAME);
		void __iomem *reg;
		unsigned int i;

		if (!idev) {
			mstep("no ipa platform device");
			goto out;
		}
		for (i = 0; i < ARRAY_SIZE(names); i++) {
			struct icc_path *p = of_icc_get(idev, names[i]);

			if (IS_ERR(p)) {
				mstep("icc %s ERR %ld", names[i], PTR_ERR(p));
				continue;
			}
			if (!p) {
				mstep("icc %s NULL (no such path)", names[i]);
				continue;
			}
			ret = icc_set_bw(p, 1000000, 1000000);
			mstep("icc %s bw ret=%d", names[i], ret);
		}
		msleep(50);

		reg = ioremap(IPA_PA, IPA_WIN);
		if (!reg) {
			mstep("ioremap FAILED");
			goto out;
		}
		mstep("reading VERSION after 3-path vote (may hang)");
		mstep("VERSION = 0x%08x", ioread32(reg + IPA_VER_OFF));
		iounmap(reg);
		goto out;
	}

	if (stage == 20) {
		/* isolate the -22: metadata construction vs the SCM call */
		struct device *idev = bus_find_device_by_name(&platform_bus_type,
							      NULL, IPA_NAME);
		const struct firmware *fw = NULL;
		size_t mlen = 0;
		void *meta;
		int r;

		if (!idev) {
			mstep("no ipa platform device");
			goto out;
		}
		r = request_firmware(&fw, "ipa_fws.mdt", idev);
		mstep("fw ret=%d", r);
		if (!r && fw) {
			meta = qcom_mdt_read_metadata(fw, &mlen, "ipa_fws.mdt",
						      idev);
			if (IS_ERR(meta)) {
				mstep("read_metadata ERR %ld", PTR_ERR(meta));
			} else {
				mstep("metadata ok len=%zu", mlen);
				r = qcom_scm_pas_init_image(15, meta, mlen,
							    NULL);
				mstep("pas_init_image(15) ret=%d", r);
				kfree(meta);
			}
			release_firmware(fw);
		}
		goto out;
	}

	if (stage == 17 || stage == 18) {
		/* Full TZ PAS flow through qcom_mdt_load(): builds the proper
		 * metadata, authenticates and resets the IPA subsystem.
		 * stage 17 reports only; stage 18 also reads VERSION.
		 */
		struct device *idev = bus_find_device_by_name(&platform_bus_type,
							      NULL, IPA_NAME);
		const struct firmware *fw = NULL;
		void *virt;
		phys_addr_t phys;
		ssize_t fwsize;
		int r;

		if (!idev) {
			mstep("no ipa platform device");
			goto out;
		}
		r = request_firmware(&fw, "ipa_fws.mdt", idev);
		mstep("fw ret=%d", r);
		if (r)
			goto p17_done;

		fwsize = qcom_mdt_get_size(fw);
		mstep("mdt size=%zd", fwsize);
		if (fwsize <= 0) {
			ret = fwsize;
			goto p17_fw;
		}
		virt = dma_alloc_coherent(idev, fwsize, &phys, GFP_KERNEL);
		if (!virt) {
			mstep("dma_alloc FAILED size=%zd", fwsize);
			ret = -ENOMEM;
			goto p17_fw;
		}
		mstep("dma ok phys=0x%llx", (u64)phys);

		r = qcom_mdt_load(idev, fw, "ipa_fws.mdt", 15, virt, phys,
				  fwsize, NULL);
		mstep("qcom_mdt_load ret=%d", r);

		if (stage == 18 && r == 0) {
			void __iomem *reg = ioremap(IPA_PA, IPA_WIN);

			if (reg) {
				mstep("VERSION now = 0x%08x",
				      ioread32(reg + IPA_VER_OFF));
				iounmap(reg);
			}
		}
		dma_free_coherent(idev, fwsize, virt, phys);
p17_fw:
		release_firmware(fw);
p17_done:
		goto out;
	}

	if (stage == 16) {
		/* bring the block up the way the vendor driver does first */
		{
			struct device *idev16 = bus_find_device_by_name(&platform_bus_type, NULL, IPA_NAME);
			static const char *const iccn16[] = { "memory", "imem", "config" };
			struct clk *c1, *c2;
			unsigned int k;

			if (idev16) {
				c1 = clk_get(idev16, "core");
				if (!IS_ERR(c1)) {
					int er = clk_prepare_enable(c1);

					mstep("R core enable ret=%d", er);
					er = clk_set_rate(c1, clk_hz);
					mstep("R core set_rate ret=%d rate=%lu", er,
					      (unsigned long)clk_get_rate(c1));
				}
				c2 = clk_get(idev16, "smmu");
				if (!IS_ERR(c2)) {
					clk_prepare_enable(c2);
					mstep("R clk smmu on");
				}
				for (k = 0; k < ARRAY_SIZE(iccn16); k++) {
					struct icc_path *pp = of_icc_get(idev16, iccn16[k]);
					if (!IS_ERR_OR_NULL(pp))
						mstep("R icc %s ret=%d", iccn16[k],
						      icc_set_bw(pp, INT_MAX, INT_MAX));
				}
				msleep(30);
			}
		}

		/* Map the IPA register page one offset at a time.  A marker is
		 * flushed *before* each read, so after a power cycle the last
		 * marker identifies the first offset that stalls.
		 */
		static const unsigned long offs[] = {
			0x0000, 0x0004, 0x0008, 0x0034, 0x0040,
			0x0100, 0x1000, 0x2000, 0x3000, 0x3800,
		};
		void __iomem *reg = ioremap(IPA_PA, IPA_WIN);
		unsigned int i;

		if (!reg) {
			mstep("R ioremap FAILED");
			goto out;
		}
		mstep("R ioremap ok");
		for (i = 0; i < ARRAY_SIZE(offs); i++) {
			u32 v;

			mstep("R +0x%04lx read...", offs[i]);
			v = ioread32(reg + offs[i]);
			mstep("R +0x%04lx = 0x%08x OK", offs[i], v);
		}
		iounmap(reg);
		goto out;
	}

	if (stage == 14) {
		/* Manual IPA firmware load, mirroring downstream
		 * ipa3_manual_load_ipa_fws(): the .mdt holds the ELF headers,
		 * the .bNN files hold the segments, and the UC address space
		 * maps at the IPA SRAM window.
		 */
		const struct firmware *mdt = NULL;
		const struct elf32_hdr *eh;
		const struct elf32_phdr *ph;
		void __iomem *sram;
		int r, i;

		sram = ioremap(0x14787000UL, 0x50000);
		if (!sram) {
			mstep("SRAM ioremap FAILED");
			goto out;
		}
		mstep("SRAM ioremap ok");

		r = request_firmware(&mdt, "ipa_fws.mdt", NULL);
		mstep("mdt req ret=%d", r);
		if (r)
			goto fw_done;

		eh = (const struct elf32_hdr *)mdt->data;
		if (memcmp(eh->e_ident, ELFMAG, SELFMAG)) {
			mstep("mdt not ELF");
			goto fw_done;
		}
		ph = (const struct elf32_phdr *)(mdt->data + eh->e_phoff);
		mstep("mdt phnum=%d", (int)eh->e_phnum);

		for (i = 0; i < eh->e_phnum && i < 8; i++) {
			char name[32];
			const struct firmware *seg = NULL;
			size_t n;

			if (ph[i].p_type != PT_LOAD)
				continue;
			snprintf(name, sizeof(name), "ipa_fws.b%02d", i);
			r = request_firmware(&seg, name, NULL);
			if (r) {
				mstep("seg %s missing %d", name, r);
				continue;
			}
			n = min_t(size_t, seg->size, ph[i].p_filesz);
			memcpy_toio(sram + ph[i].p_paddr, seg->data, n);
			mstep("seg %d -> 0x%x (%zu B)", i,
			      (unsigned int)ph[i].p_paddr, n);
			release_firmware(seg);
		}
		mstep("firmware copied; SRAM[0]=0x%08x SRAM[4]=0x%08x",
		      ioread32(sram), ioread32(sram + 4));
		mstep("reading VERSION (may hang)");
		{
			void __iomem *reg = ioremap(IPA_PA, IPA_WIN);

			if (reg) {
				u32 v = ioread32(reg + IPA_VER_OFF);

				mstep("VERSION now = 0x%08x", v);
				iounmap(reg);
			}
		}
fw_done:
		if (mdt)
			release_firmware(mdt);
		iounmap(sram);
		goto out;
	}

	if (stage == 13) {
		/* brute-force the IPA PAS id: only TZ calls, no IPA access */
		const struct firmware *fw = NULL;
		int r = request_firmware(&fw, "ipa_fws.mdt", NULL);

		mstep("fw ret=%d", r);
		if (!r && fw) {
			unsigned int id;

			for (id = 10; id <= 20; id++) {
				int rr = qcom_scm_pas_init_image(id, fw->data,
								 fw->size, NULL);

				mstep("pas%d -> %d", id, rr);
			}
			release_firmware(fw);
		}
		goto out;
	}

	if (stage == 12) {
		/* real TZ probe: hand the IPA firmware metadata to PAS.
		 * No IPA register access, no reboot needed.
		 */
		const struct firmware *fw = NULL;
		int r = request_firmware(&fw, "ipa_fws.mdt", NULL);

		mstep("request_firmware(ipa_fws.mdt) ret=%d", r);
		if (!r && fw) {
			int r2 = qcom_scm_pas_init_image(15, fw->data, fw->size,
							 NULL);

			mstep("pas_init_image(15) ret=%d size=%zu", r2, fw->size);
		}
		if (fw)
			release_firmware(fw);
		goto out;
	}

	if (stage == 10) {
		mstep("PAS15 supported=%d (TZ query only, no IPA access)",
		      qcom_scm_pas_supported(15) ? 1 : 0);
		goto out;
	}

	if (stage == 11) {
		/* control test: is the PAS_IS_SUPPORTED SCM call working at all?
		 * 1=WCNSS 4=ADSP 5=CDSP 6=MODEM(?) 15=IPA on many SoCs
		 */
		static const u32 ids[] = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 15 };
		unsigned int i;

		for (i = 0; i < ARRAY_SIZE(ids); i++)
			mstep("PAS%-2u = %d", ids[i],
			      qcom_scm_pas_supported(ids[i]) ? 1 : 0);
		goto out;
	}

	dev = bus_find_device_by_name(&platform_bus_type, NULL, IPA_NAME);
	if (!dev) {
		mstep("M1 dev MISSING %s", IPA_NAME);
		ret = -ENODEV;
		goto out;
	}
	mstep("M1 dev found %s", dev_name(dev));

	clk = clk_get(dev, "core");
	if (IS_ERR(clk)) {
		mstep("M2 clk_get FAILED %ld", PTR_ERR(clk));
		ret = PTR_ERR(clk);
		goto out;
	}
	mstep("M2 clk_get ok rate=%lu", (unsigned long)clk_get_rate(clk));

	if (stage >= 3) {
		if (skip_core) {
			mstep("M3a core enable SKIPPED (skip_core=1) rate=%lu",
			      (unsigned long)clk_get_rate(clk));
		} else {
			ret = clk_set_rate(clk, clk_hz);
			mstep("M3a clk_set_rate(%d) ret=%d rate=%lu",
			      clk_hz, ret, (unsigned long)clk_get_rate(clk));

			ret = clk_prepare_enable(clk);
			mstep("M3b clk_prepare_enable ret=%d rate=%lu",
			      ret, (unsigned long)clk_get_rate(clk));
			if (ret)
				goto out;
		}

		clk2 = clk_get(dev, "smmu");
		if (IS_ERR(clk2)) {
			mstep("M3c clk_get(smmu) MISSING %ld", PTR_ERR(clk2));
		} else {
			ret = clk_prepare_enable(clk2);
			mstep("M3c clk(smmu) enable ret=%d rate=%lu",
			      ret, (unsigned long)clk_get_rate(clk2));
		}
		msleep(20);
	}

	if (stage >= 4) {
		win = stage >= 6 ? 0x50000 : IPA_WIN;
		ipa = ioremap(IPA_PA, win);
		if (!ipa) {
			mstep("M4 ioremap FAILED");
			ret = -ENOMEM;
			goto out;
		}
		mstep("M4 ioremap ok addr=0x%lx", (unsigned long)ipa);

		if (sanity) {
			gcc = ioremap(GCC_PA, GCC_WIN);
			if (!gcc) {
				mstep("M4s GCC ioremap FAILED");
			} else {
				val = ioread32(gcc);
				mstep("M4s GCC[0x0]=0x%08x (readl ok)", val);
				iounmap(gcc);
			}
		}
	}

	if (stage >= 4 && icc_kbps) {
		struct icc_path *path = of_icc_get(dev, "memory");

		if (IS_ERR(path)) {
			mstep("M4i of_icc_get(memory) FAILED %ld", PTR_ERR(path));
		} else if (!path) {
			mstep("M4i of_icc_get(memory)=NULL (no interconnects in DT)");
		} else {
			ret = icc_set_bw(path, icc_kbps, icc_kbps);
			mstep("M4i icc_set_bw(%d) ret=%d", icc_kbps, ret);
			/* keep the vote: no icc_put() on purpose */
		}
	}

	if (stage >= 5 && stage < 6) {
		mstep("M5 read BEGIN addr=0x%lx", IPA_PA + IPA_VER_OFF);
		val = ioread32(ipa + IPA_VER_OFF);
		mstep("M5 VERSION=0x%08x", val);
	}

	if (stage == 6) {
		static const unsigned long sweep[] = {
			0x14784000,	/* gsi        */
			0x14787000,	/* sram (vendor) */
			0x147ce000,	/* ipa-shared (our DT) */
			0x14780034,	/* VERSION    */
		};
		unsigned int i;

		for (i = 0; i < ARRAY_SIZE(sweep); i++) {
			unsigned long off = sweep[i] - IPA_PA;

			mstep("S%u read BEGIN 0x%lx (+0x%lx)", i, sweep[i], off);
			val = ioread32(ipa + off);
			mstep("S%u = 0x%08x", i, val);
		}
	}

	if (stage >= 7) {
		/* all offsets below are inside 0x14784000, which reads fine:
		 * safe probe of the second register page
		 */
		static const unsigned long gsi_off[] = {
			0x4000 + 0x0, 0x4000 + 0x4, 0x4000 + 0x8, 0x4000 + 0xc,
			0x4000 + 0x10, 0x4000 + 0x34, 0x4000 + 0x100, 0x4000 + 0x1000,
		};
		unsigned int i;

		for (i = 0; i < ARRAY_SIZE(gsi_off); i++) {
			mstep("G%u @+0x%lx", i, gsi_off[i]);
			val = ioread32(ipa + gsi_off[i]);
			mstep("G%u = 0x%08x", i, val);
		}
	}

	if (stage == 8) {
		/* 0x14785000 responded earlier, so its page is decoded: safe */
		static const unsigned long p5[] = {
			0x5000, 0x5004, 0x5008, 0x500c, 0x5010, 0x5034, 0x5100, 0x5ffc,
		};
		unsigned int i;

		for (i = 0; i < ARRAY_SIZE(p5); i++) {
			val = ioread32(ipa + p5[i]);
			mstep("P5 %u @+0x%lx = 0x%08x", i, p5[i], val);
		}
	}

	if (stage == 9) {
		/* first 16 bytes of the dead-looking page: 0x0 is COMP_HW_VERSION
		 * on IPA 3.5, so a readable 0x0 would mean the page is partly alive
		 */
		static const unsigned long pg0[] = { 0x0, 0x4, 0x8, 0xc };
		unsigned int i;

		for (i = 0; i < ARRAY_SIZE(pg0); i++) {
			mstep("Z%u read BEGIN +0x%lx", i, pg0[i]);
			val = ioread32(ipa + pg0[i]);
			mstep("Z%u = 0x%08x", i, val);
		}
	}

out:
	mstep("END stage=%d ret=%d", stage, ret);
	if (mmark) {
		filp_close(mmark, NULL);
		mmark = NULL;
	}
	kfree(mpay);
	mpay = NULL;
	return ret;
}

static void __exit ipa_marker_exit(void)
{
}

module_init(ipa_marker_init);
module_exit(ipa_marker_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("IPA bring-up probe with p12-tail log block");
