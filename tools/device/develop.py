#!/usr/bin/env python3
"""Convert an OV13855 RAW10 (SGRBG10 packed) frame to a well-developed PNG.

Differences from raw10_to_png.py:

  * keeps full resolution (Malvar-He-Cutler demosaic instead of 2x2 binning)
  * subtracts the measured black pedestal (64) and normalises to 10-bit white
  * white balance computed on unsaturated pixels only (a grey-world average
    that ignores blown-out sky and pure black)
  * proper sRGB transfer curve instead of a percentile stretch
  * optional unsharp mask

Usage:
    python raw10_to_png2.py in.raw out.png [--exposure-ev 0] [--sharp 0.5]
"""
import argparse
import sys

import numpy as np
from PIL import Image

W, H = 4224, 3136
BLACK = 64.0
WHITE = 1023.0


def unpack_raw10(buf, w, h):
    """MIPI RAW10: 5 bytes carry 4 ten-bit samples (LSBs packed in byte 5)."""
    groups = np.frombuffer(buf, dtype=np.uint8)[: (w * h // 4) * 5].reshape(-1, 5)
    out = np.empty((groups.shape[0], 4), dtype=np.uint16)
    for i in range(4):
        out[:, i] = (groups[:, i].astype(np.uint16) << 2) | ((groups[:, 4] >> (i * 2)) & 0x03)
    return out.reshape(h, w).astype(np.float32)


PHASES = {
    # name: (row0_col0, row0_col1, row1_col0, row1_col1)
    'RGGB': ('R', 'G', 'G', 'B'),
    'BGGR': ('B', 'G', 'G', 'R'),
    'GRBG': ('G', 'R', 'B', 'G'),
    'GBRG': ('G', 'B', 'R', 'G'),
}


def phase_masks(shape, phase):
    """Build R/G/B masks for a named Bayer phase."""
    p00, p01, p10, p11 = PHASES[phase]
    h, w = shape
    masks = {'R': np.zeros((h, w), bool),
             'G': np.zeros((h, w), bool),
             'B': np.zeros((h, w), bool)}
    # (0,0) and (1,1) sit on the same parity class; (0,1) and (1,0) on the other
    masks[p00][0::2, 0::2] = True
    masks[p11][1::2, 1::2] = True
    masks[p01][0::2, 1::2] = True
    masks[p10][1::2, 0::2] = True
    return masks


def bin2_phase(cfa, phase):
    """2x2 binning with an explicit Bayer phase.

    Works on 2x2 *blocks* (cfa.reshape(h2, 2, w2, 2)) instead of boolean-mask
    flattening: for GRBG the two green samples sit at (0,0) and (1,1) of a
    block, so they are not adjacent in row-major flatten order.
    """
    m = phase_masks(cfa.shape, phase)
    h2, w2 = cfa.shape[0] // 2, cfa.shape[1] // 2
    blocks = cfa.reshape(h2, 2, w2, 2)
    out = []
    for colour in ('R', 'G', 'B'):
        mb = m[colour].reshape(h2, 2, w2, 2)
        num = (blocks * mb).sum(axis=(1, 3))
        den = mb.sum(axis=(1, 3))
        out.append(num / np.maximum(den, 1))
    return np.stack(out, axis=-1)


def malvar_demosaic(cfa, phase='GRBG'):
    """Malvar-He-Cutler 5x5 gradient-corrected linear demosaic.

    Works for any Bayer phase: the channel masks come from `phase`, and the
    directional kernels are selected by the row parity on which R (or B) sits.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    h, w = cfa.shape
    m = phase_masks(cfa.shape, phase)
    r_mask, g_mask, b_mask = m['R'], m['G'], m['B']
    out = np.zeros((h, w, 3), dtype=np.float32)

    # rows carrying R vs B
    r_row_parity = 0 if r_mask[0].any() else 1
    b_row_parity = 1 - r_row_parity

    k_g_at_rb = np.array([[0, 0, -1, 0, 0],
                          [0, 0, 2, 0, 0],
                          [-1, 2, 4, 2, -1],
                          [0, 0, 2, 0, 0],
                          [0, 0, -1, 0, 0]], np.float32) / 8.0

    # channel sampled in the SAME row as the target G site (horizontal neighbours)
    k_same_row = np.array([[0, 0, 0.5, 0, 0],
                           [0, -1, 0, -1, 0],
                           [-1, 4, 5, 4, -1],
                           [0, -1, 0, -1, 0],
                           [0, 0, 0.5, 0, 0]], np.float32) / 8.0
    # channel sampled in the SAME column (vertical neighbours)
    k_same_col = k_same_row.T
    # channel sampled diagonally (target site carries the opposite colour)
    k_diag = np.array([[-1.5, 0, 2, 0, -1.5],
                       [0, 0, 0, 0, 0],
                       [2, 0, 0, 0, 2],
                       [0, 0, 0, 0, 0],
                       [-1.5, 0, 2, 0, -1.5]], np.float32) / 8.0

    def conv(img, k):
        pad = k.shape[0] // 2
        p = np.pad(img, pad, mode='reflect')
        win = sliding_window_view(p, k.shape)
        return (win * k).sum(axis=(-1, -2))

    # --- green everywhere ---
    g = cfa.copy()
    g_at_rb = conv(cfa, k_g_at_rb)
    g[r_mask | b_mask] = g_at_rb[r_mask | b_mask]

    # --- red ---
    r = np.where(r_mask, cfa, 0.0)
    g_on_r_row = g_mask & (np.arange(h)[:, None] % 2 == r_row_parity)
    r_at_g_same_row = conv(cfa, k_same_row)
    r_at_g_same_col = conv(cfa, k_same_col)
    r[g_on_r_row] = r_at_g_same_row[g_on_r_row]
    r[g_mask & ~g_on_r_row] = r_at_g_same_col[g_mask & ~g_on_r_row]
    r_at_b = conv(cfa, k_diag)
    r[b_mask] = r_at_b[b_mask]

    # --- blue ---
    b = np.where(b_mask, cfa, 0.0)
    g_on_b_row = g_mask & (np.arange(h)[:, None] % 2 == b_row_parity)
    b[g_on_b_row] = r_at_g_same_row[g_on_b_row]
    b[g_mask & ~g_on_b_row] = r_at_g_same_col[g_mask & ~g_on_b_row]
    b_at_r = conv(cfa, k_diag)
    b[r_mask] = b_at_r[r_mask]

    out[..., 0] = r
    out[..., 1] = g
    out[..., 2] = b
    return out


def grey_world(rgb):
    """Average the unsaturated pixels of each channel and neutralise."""
    lum = rgb.mean(axis=2)
    valid = (lum > 0.02) & (lum < 0.85)
    if valid.sum() < 1000:
        valid = lum > 0.02
    means = np.array([rgb[..., c][valid].mean() for c in range(3)])
    means = np.maximum(means, 1e-6)
    gain = means.mean() / means
    return rgb * gain[None, None, :], gain


def shades_of_grey(rgb, p=6.0):
    """Minkowski-norm AWB (Finlayson).  Less aggressive than grey-world on
    scenes dominated by one large uniform area, so some colour survives."""
    lum = rgb.mean(axis=2)
    valid = (lum > 0.02) & (lum < 0.85)
    if valid.sum() < 1000:
        valid = lum > 0.02
    est = []
    for c in range(3):
        v = rgb[..., c][valid]
        est.append((np.power(v, p).mean()) ** (1.0 / p))
    est = np.maximum(np.array(est), 1e-6)
    gain = est.mean() / est
    return rgb * gain[None, None, :], gain


def denoise(rgb, strength=0.0):
    """Light edge-preserving smoothing on the linear image.

    A 3x3 median on the luminance ratio keeps edges while killing the chroma
    speckle that high analogue gain produces.
    """
    if strength <= 0:
        return rgb
    from PIL import Image, ImageFilter
    lum = rgb.mean(axis=2)
    lo = np.percentile(lum, 0.1)
    hi = np.percentile(lum, 99.9)
    norm = np.clip((lum - lo) / max(1e-6, hi - lo), 0, 1)
    img = Image.fromarray((norm * 255).astype(np.uint8))
    med = np.asarray(img.filter(ImageFilter.MedianFilter(3)), dtype=np.float32) / 255.0
    # blend toward the median, weighted by strength
    new_lum = norm * (1 - strength) + med * strength
    scale = (new_lum + 1e-6) / (norm + 1e-6)
    return rgb * scale[..., None]


def tone_map(rgb, amount=1.0):
    """Filmic-ish curve: lift shadows, roll off highlights, keep midtones.

    Phones apply something similar; without it a raw linear image looks both
    flat and harsh at the same time.
    """
    if amount <= 0:
        return rgb
    x = np.clip(rgb, 0, None)
    # shadow lift (log-ish), then a soft shoulder
    lifted = np.power(x, 0.85)
    shoulder = 1.0 - np.exp(-lifted * 1.35)
    mixed = lifted * (1 - amount) + shoulder * amount
    return np.clip(mixed, 0, 1)



def srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def bin2(cfa):
    """2x2 binning: half resolution, quarter the work.  Good enough on-device."""
    h, w = cfa.shape
    h2, w2 = h // 2, w // 2
    a = cfa[1:2 * h2:2, 0:2 * w2:2]        # R
    b = cfa[0:2 * h2:2, 0:2 * w2:2]        # G
    c = cfa[1:2 * h2:2, 1:2 * w2:2]        # G
    d = cfa[0:2 * h2:2, 1:2 * w2:2]        # B
    return np.stack([a, (b + c) * 0.5, d], axis=-1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('raw')
    ap.add_argument('out')
    ap.add_argument('--exposure-ev', type=float, default=0.0)
    ap.add_argument('--sharp', type=float, default=0.4)
    ap.add_argument('--scale', type=int, default=0, help='downscale factor (0=full)')
    ap.add_argument('--awb', choices=('grey', 'sog'), default='sog')
    ap.add_argument('--denoise', type=float, default=0.5)
    ap.add_argument('--tone', type=float, default=0.7)
    ap.add_argument('--bin2', action='store_true', help='2x2 bin instead of demosaic (fast)')
    ap.add_argument('--phase', choices=tuple(PHASES), default='BGGR',
                    help='Bayer phase of the sensor output (default GRBG)')
    a = ap.parse_args()

    buf = open(a.raw, 'rb').read()
    need = W * H * 5 // 4
    if len(buf) < need:
        sys.exit(f'{a.raw}: {len(buf)} 字节，至少需要 {need}')
    cfa = unpack_raw10(buf, W, H)
    print(f'  RAW {len(buf)} B, 黑电平 {BLACK}, 白点 {WHITE}, 相位 {a.phase}')

    lin = np.clip((cfa - BLACK) / (WHITE - BLACK), 0, 1)
    del cfa
    if a.bin2:
        rgb = bin2_phase(lin, a.phase)
        print(f'  2x2 合并 → {rgb.shape[1]}x{rgb.shape[0]}')
    else:
        rgb = malvar_demosaic(lin, a.phase)
        print(f'  去马赛克完成 {rgb.shape[1]}x{rgb.shape[0]}')
    del lin

    if a.denoise > 0:
        rgb = denoise(rgb, a.denoise)
        print(f'  降噪强度 {a.denoise}')

    if a.awb == 'sog':
        rgb, gain = shades_of_grey(rgb)
        print('  白平衡(SoG) 增益 R=%.3f G=%.3f B=%.3f' % tuple(gain))
    else:
        rgb, gain = grey_world(rgb)
        print('  白平衡(灰世界) 增益 R=%.3f G=%.3f B=%.3f' % tuple(gain))

    rgb = rgb * (2.0 ** a.exposure_ev)
    if a.tone > 0:
        rgb = tone_map(rgb, a.tone)
        print(f'  色调映射强度 {a.tone}')
    srgb8 = (srgb(rgb) * 255.0)

    if a.sharp > 0:
        from PIL import ImageFilter
        img = Image.fromarray(np.clip(srgb8, 0, 255).astype(np.uint8))
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(a.sharp * 100), threshold=2))
    else:
        img = Image.fromarray(np.clip(srgb8, 0, 255).astype(np.uint8))

    if a.scale > 1:
        img = img.resize((img.width // a.scale, img.height // a.scale), Image.LANCZOS)
    img.save(a.out)
    print(f'  写出 {a.out}  {img.width}x{img.height}')


if __name__ == '__main__':
    main()
