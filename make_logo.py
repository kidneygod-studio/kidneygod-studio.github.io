# -*- coding: utf-8 -*-
"""把 logo 原圖去背，輸出網頁用的 PNG。

不能用「夠白就設成透明」那種門檻法 —— 護腎教室這四個字本身就是白色的，
會被整個挖空。改成從畫布邊緣做 flood fill：只有「與邊緣連通的白」才算
背景，字裡面的白被暗紅描邊圍住、連不出去，所以會留下來。

光暈的處理：原圖是為白底設計的，外圈有一層白色光暈。直接切掉會留下硬邊，
所以背景區的 alpha 依「離純白多遠」漸變 —— 純白全透明、越有顏色越不透明，
放到深色冊頁上就變成一圈柔和的暈光。
"""
import os, sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"C:\Users\user\Downloads\知識卡插圖\護腎教室.jpg"
OUT = "logo.png"
FLOOD_T = 215      # 這個亮度以上、且與邊緣連通者視為背景
FADE_LO = 215      # alpha 漸變的下限（比這暗就是完全不透明）
MAX_W = 480        # 頁首顯示約 100–160px 寬，480 已足夠三倍圖


def main():
    im = Image.open(SRC).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    mn = a.min(axis=2)

    # 與畫布邊緣連通的亮區 = 真正的背景
    bright = mn > FLOOD_T
    lab, _ = ndimage.label(bright)
    edge = np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])
    outer = np.isin(lab, [v for v in np.unique(edge) if v])

    # 背景區依「離純白多遠」給 alpha，光暈才不會有硬邊
    fade = np.clip((255 - mn) * (255.0 / (255 - FADE_LO)), 0, 255)
    alpha = np.full(mn.shape, 255, dtype=np.uint8)
    alpha[outer] = fade[outer].astype(np.uint8)

    rgba = im.convert("RGBA")
    rgba.putalpha(Image.fromarray(alpha))
    bb = rgba.getbbox()
    rgba = rgba.crop(bb)
    if rgba.width > MAX_W:
        rgba = rgba.resize((MAX_W, round(rgba.height * MAX_W / rgba.width)),
                           Image.LANCZOS)
    # 光暈是平滑漸層，量化到 200 色看不出色階，但體積差一個量級（169→25 KB）
    rgba.quantize(colors=200, method=Image.FASTOCTREE).save(OUT, optimize=True)

    kept = (alpha > 8).mean() * 100
    print(f"{OUT}  {rgba.size}  {os.path.getsize(OUT)//1024} KB")
    print(f"裁切前保留（alpha>8）{kept:.1f}%；比例 {rgba.width/rgba.height:.2f}")


if __name__ == "__main__":
    main()
