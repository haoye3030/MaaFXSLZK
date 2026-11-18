# -*- coding: utf-8 -*-
"""从咨询中心满员房间截图裁「?」徽章模板并做三项校验。

用法: python tmp/make_quiz_mark.py
输出: assets/resource/image/quiz/quiz_mark.png
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(r"E:\DSH\MaaFX\MaaFXSLZK")
SRC = Path(r"E:\DSH\MaaFX\tmp\quiz_out\20_after_refresh.png")
DST = ROOT / "assets" / "resource" / "image" / "quiz" / "quiz_mark.png"


def fft_ncc(img, tpl):
    """FFT 版归一化互相关，返回全图每个位置的 NCC（与模板同尺寸的滑动窗口）。"""
    img = img.astype(np.float64)
    tpl = tpl.astype(np.float64)
    if img.ndim == 3:
        img = img.mean(axis=2)
    if tpl.ndim == 3:
        tpl = tpl.mean(axis=2)
    h, w = img.shape
    th, tw = tpl.shape
    tpl0 = tpl - tpl.mean()
    tpl_norm = np.sqrt((tpl0 ** 2).sum())
    fh, fw = h + th - 1, w + tw - 1
    F = np.fft.rfft2(img, s=(fh, fw))
    T = np.fft.rfft2(tpl0[::-1, ::-1], s=(fh, fw))
    corr = np.fft.irfft2(F * T, s=(fh, fw))
    corr = corr[th - 1:h, tw - 1:w]
    ii = np.zeros((h + 1, w + 1))
    ii[1:, 1:] = img.cumsum(0).cumsum(1)
    ii2 = np.zeros((h + 1, w + 1))
    ii2[1:, 1:] = (img ** 2).cumsum(0).cumsum(1)

    def s(ii_, y, x):
        return ii_[y + th, x + tw] - ii_[y, x + tw] - ii_[y + th, x] + ii_[y, x]

    ys = np.arange(corr.shape[0])[:, None]
    xs = np.arange(corr.shape[1])[None, :]
    sum1 = s(ii, ys, xs)
    sum2 = s(ii2, ys, xs)
    var = sum2 - sum1 ** 2 / (th * tw)
    var = np.maximum(var, 1e-9)
    return corr / (np.sqrt(var) * tpl_norm + 1e-9)


def main():
    shot = np.array(Image.open(SRC).convert("RGB"))
    # 徽章在 (847..887, 168..207) 附近，先在小区里找黄色像素确定精确包围盒
    x0, y0, x1, y1 = 810, 140, 930, 250
    sub = shot[y0:y1, x0:x1].astype(np.int16)
    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    mask = (r > 140) & (g > 90) & (b < 130) & (r - b > 60)
    ys, xs = np.nonzero(mask)
    print("yellow px count:", len(xs))
    if len(xs) == 0:
        print("no yellow found")
        return 1
    bx0, bx1 = xs.min() + x0, xs.max() + x0
    by0, by1 = ys.min() + y0, ys.max() + y0
    print("badge bbox:", (bx0, by0, bx1 - bx0 + 1, by1 - by0 + 1))

    pad = 2
    crop = shot[by0 - pad:by1 + pad + 1, bx0 - pad:bx1 + pad + 1]
    DST.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop).save(DST)
    print("saved", DST, crop.shape, "std=%.1f" % crop.astype(np.float64).std())

    tpl = crop
    # 1) 目标位：满员房间截图里的最佳匹配
    ncc = fft_ncc(shot, tpl)
    score = ncc.max()
    y, x = np.unravel_index(ncc.argmax(), ncc.shape)
    print("target self-match %.4f @(%d,%d)  expected around (%d,%d)" % (score, x, y, bx0 - pad, by0 - pad))
    # 2) 干扰位：空房间 / 题目界面 / 主界面
    for name in ["71_consult_again.png", "42_tap_640_600.png", "41_after_confirm2.png",
                 "21_port.png", "80_help.png"]:
        p = src_dir = SRC.parent / name
        if not p.is_file():
            print("skip missing", name)
            continue
        other = np.array(Image.open(p).convert("RGB"))
        if other.shape[:2] != shot.shape[:2]:
            print("skip size mismatch", name)
            continue
        n2 = fft_ncc(other, tpl)
        yy, xx = np.unravel_index(n2.argmax(), n2.shape)
        print("interf %-24s max %.4f @(%d,%d)" % (name, n2.max(), xx, yy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
