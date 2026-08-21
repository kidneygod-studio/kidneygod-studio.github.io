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
CROP_T = 55        # 裁切時視為「實心內容」的 alpha 門檻（低於此的只是暈光）
CROP_PAD = 0.025   # 裁切框外留的邊，讓光暈自然收尾


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

    # 裁切基準用「實心內容」而不是 getbbox()。光暈拖得很遠，用 alpha>0 去裁
    # 會讓四成的高度都是幾乎看不見的暈光，字在頁首就顯得很小。
    # 抓 alpha > CROP_T 的範圍再留一點邊，光暈收在邊緣不會出現硬切口。
    ys, xs = np.where(alpha > CROP_T)
    pad = int(min(xs.max() - xs.min(), ys.max() - ys.min()) * CROP_PAD)
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
           min(alpha.shape[1], xs.max() + 1 + pad),
           min(alpha.shape[0], ys.max() + 1 + pad))
    rgba = rgba.crop(box)
    if rgba.width > MAX_W:
        rgba = rgba.resize((MAX_W, round(rgba.height * MAX_W / rgba.width)),
                           Image.LANCZOS)
    # 光暈是平滑漸層，量化到 200 色看不出色階，但體積差一個量級（169→25 KB）
    rgba.quantize(colors=200, method=Image.FASTOCTREE).save(OUT, optimize=True)

    # 把實際尺寸同步進 <img> 的 width/height，否則裁切一改就對不上，
    # 這兩個屬性是用來預留版面、避免載入時跳動的，寫錯等於沒寫。
    import re
    for page in ("index.html", "game.html"):
        if not os.path.exists(page):
            continue
        s = open(page, encoding="utf-8").read()
        s2 = re.sub(r'(src="logo\.png"[^>]*?width=")\d+("\s+height=")\d+"',
                    lambda m: f'{m.group(1)}{rgba.width}{m.group(2)}{rgba.height}"', s)
        if s2 != s:
            open(page, "w", encoding="utf-8").write(s2)
            print(f"  已同步 {page} 的 width/height")

    print(f"{OUT}  {rgba.size}  {os.path.getsize(OUT)//1024} KB"
          f"  比例 {rgba.width/rgba.height:.2f}")


if __name__ == "__main__":
    main()
