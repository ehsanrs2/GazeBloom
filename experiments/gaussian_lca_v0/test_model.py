import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chromablur_pilot import lca_diopters, blur_sigma_px

def sig(d, c):
    return blur_sigma_px(d, {'R':617.0,'G':520.0,'B':449.0}[c], 0.6,0.27,4.0)

assert abs(lca_diopters(520)) < 1e-3
assert sig(+0.45, 'R') > sig(+0.45, 'G') > sig(+0.45, 'B')
assert sig(-0.45, 'B') > sig(-0.45, 'G') > sig(-0.45, 'R')
assert all(sig(0,c)==0 for c in 'RGB')
assert abs(sig(+0.45,'G') - sig(-0.45,'G')) < 1e-3
print('MODEL_SANITY_TESTS_PASS')
