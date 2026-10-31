P = '/root/kbuild/linux-7.0.14-sdm660/drivers/net/ipa/ipa_mem.c'
s = open(P).read()
orig = s

old = '''	reg = ipa_reg(ipa, SHARED_MEM_SIZE);
	val = ioread32(ipa->reg_virt + reg_offset(reg));

	/* The fields in the register are in 8 byte units */'''
new = '''	reg = ipa_reg(ipa, SHARED_MEM_SIZE);
	val = ioread32(ipa->reg_virt + reg_offset(reg));

	/* Bring-up hack: if the IPA firmware/bootloader did not initialize
	 * the shared memory size register, skip the memory configuration
	 * instead of failing the whole probe.
	 */
	if (!val) {
		dev_warn(dev, "IPA shared memory size is zero; skipping memory config\\n");
		return 0;
	}

	/* The fields in the register are in 8 byte units */'''
assert old in s
s = s.replace(old, new, 1)
open(P, 'w').write(s)
print('patched ipa_mem.c', len(orig), '->', len(s))
