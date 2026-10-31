import re

P = '/root/kbuild/linux-7.0.14-sdm660/drivers/net/ipa/data/ipa_data-v3.1.c'
s = open(P).read()
new, n = re.subn(r'\.core_clock_rate\s*=\s*16 \* 1000 \* 1000',
                 '.core_clock_rate\t= 200 * 1000 * 1000', s)
assert n >= 1, 'core_clock_rate line not found'
open(P, 'w').write(new)
print('core_clock_rate -> 200 MHz, replacements:', n)
