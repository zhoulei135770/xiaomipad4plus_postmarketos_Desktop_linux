P = '/root/kbuild/linux-7.0.14-sdm660/drivers/net/ipa/ipa_main.c'
s = open(P).read()
old = '''static int ipa_config(struct ipa *ipa, const struct ipa_data *data)
{
	int ret;

	ipa_hardware_config(ipa, data);'''
new = '''static int ipa_config(struct ipa *ipa, const struct ipa_data *data)
{
	int ret;
	u32 val;

	/* Bring-up probe: read IPA_VERSION (0x34) before touching anything
	 * else.  If this hangs, the IPA clock/power is not actually on.
	 */
	val = ioread32(ipa->reg_virt + 0x34);
	dev_info(ipa->dev, "IPA probe-only: VERSION=0x%08x, skipping config\\n",
		 val);
	return 0;

	ipa_hardware_config(ipa, data);'''
assert old in s
s = s.replace(old, new, 1)
open(P, 'w').write(s)
print('patched ipa_main.c ipa_config probe-only')
