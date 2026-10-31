import sys

P = '/root/kbuild/linux-7.0.14-sdm660/drivers/net/ipa/ipa_smp2p.c'
s = open(P).read()
orig = s

# 1) Make SMP2P optional: if the SMEM states are not described in DT, skip it.
old = '''	valid_state = qcom_smem_state_get(dev, "ipa-clock-enabled-valid",
					  &valid_bit);
	if (IS_ERR(valid_state))
		return PTR_ERR(valid_state);'''
new = '''	valid_state = qcom_smem_state_get(dev, "ipa-clock-enabled-valid",
					  &valid_bit);
	if (IS_ERR(valid_state)) {
		dev_warn(dev, "no IPA SMP2P states; skipping SMP2P\\n");
		ipa->smp2p = NULL;
		return 0;
	}'''
assert old in s
s = s.replace(old, new, 1)

# 2) NULL guards for the paths that can be reached without SMP2P.
old = '''static void ipa_smp2p_power_release(struct ipa *ipa)
{
	struct device *dev = ipa->dev;

	if (!ipa->smp2p->power_on)
		return;'''
new = '''static void ipa_smp2p_power_release(struct ipa *ipa)
{
	struct device *dev = ipa->dev;

	if (!ipa->smp2p || !ipa->smp2p->power_on)
		return;'''
assert old in s
s = s.replace(old, new, 1)

old = '''void ipa_smp2p_exit(struct ipa *ipa)
{
	struct ipa_smp2p *smp2p = ipa->smp2p;

	if (smp2p->setup_ready_irq)'''
new = '''void ipa_smp2p_exit(struct ipa *ipa)
{
	struct ipa_smp2p *smp2p = ipa->smp2p;

	if (!smp2p)
		return;

	if (smp2p->setup_ready_irq)'''
assert old in s
s = s.replace(old, new, 1)

old = '''void ipa_smp2p_irq_disable_setup(struct ipa *ipa)
{
	struct ipa_smp2p *smp2p = ipa->smp2p;

	if (!smp2p->setup_ready_irq)'''
new = '''void ipa_smp2p_irq_disable_setup(struct ipa *ipa)
{
	struct ipa_smp2p *smp2p = ipa->smp2p;

	if (!smp2p || !smp2p->setup_ready_irq)'''
assert old in s
s = s.replace(old, new, 1)

old = '''void ipa_smp2p_notify_reset(struct ipa *ipa)
{
	struct ipa_smp2p *smp2p = ipa->smp2p;
	u32 mask;

	if (!smp2p->notified)'''
new = '''void ipa_smp2p_notify_reset(struct ipa *ipa)
{
	struct ipa_smp2p *smp2p = ipa->smp2p;
	u32 mask;

	if (!smp2p || !smp2p->notified)'''
assert old in s
s = s.replace(old, new, 1)

open(P, 'w').write(s)
print('patched', len(orig), '->', len(s))
