# -*- coding: utf-8 -*-
"""把 logo 原圖去背輸出 logo.png，另外輸出保留白底的 logo-white.png。

2026-09-04 曾經多輸出一份保留白底的 logo-white.png 給首頁遊戲入口用，
作者看過實際效果後決定維持去背版（去背的標誌浮在深色卡片上，和整張卡片
是同一個平面；白底那張是一個貼上去的方塊）。那份輸出與檔案都已移除，
記在這裡是為了不必再重新試一次。

⚠ 預設「不」覆寫 logo.png，要覆寫必須明確加 --logo。
   原因：倉庫裡的 logo.png 是 2026-08-27 手動放進去的，和這支腳本現在算出來的
   結果不一樣（684×370 vs 684×375，平均像素差 41/255）。2026-09-04 為了產白底版
   跑了一次這支，全站頁首的標誌就被悄悄換掉了，而且不會有任何錯誤訊息——
   正是本檔開頭一直在警告的那類事故。要重產 logo.png 請先確認你真的想換。


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

# ⚠ 別改回 知識卡插圖\護腎教室.jpg：那張雖然有 2752×1536，但字是改網域之前的
# KIDNEYGOD.STUDIO。2026-08-27 換成 .NET 版時，logo.png 是直接放進倉庫的，
# 這裡的 SRC 沒有跟著更新，等於留了一顆地雷——只要有人跑一次這支腳本，
# 頁首的標誌就會被悄悄換回不存在的舊網域，而且不會有任何錯誤訊息。
SRC = r"C:\Users\user\Downloads\kidneygod.png"
OUT = "logo.png"
FLOOD_T = 215      # 這個亮度以上、且與邊緣連通者視為背景
FADE_LO = 215      # alpha 漸變的下限（比這暗就是完全不透明）
MAX_W = 684        # 與倉庫現有的 logo.png 同寬。頁首顯示約 100–160px，
                   # 這個尺寸連高解析螢幕都夠；設小於此會讓標誌變糊
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
    write_logo = "--logo" in sys.argv
    if write_logo:
        # 光暈是平滑漸層，量化到 200 色看不出色階，但體積差一個量級（169→25 KB）
        rgba.quantize(colors=200, method=Image.FASTOCTREE).save(OUT, optimize=True)
    else:
        print(f"（略過 {OUT}：倉庫裡那份是手動放的，要覆寫請加 --logo）")

    # 把實際尺寸同步進 <img> 的 width/height，否則裁切一改就對不上，
    # 這兩個屬性是用來預留版面、避免載入時跳動的，寫錯等於沒寫。
    # 只有真的重產了 logo.png 才需要同步——沒重產卻改 HTML 的話，
    # 會把尺寸改成「這支腳本算出來的」而不是「檔案實際的」，反而弄錯。
    import re
    for page in ("index.html", "game.html") if write_logo else ():
        if not os.path.exists(page):
            continue
        s = open(page, encoding="utf-8").read()
        s2 = re.sub(r'(src="logo\.png"[^>]*?width=")\d+("\s+height=")\d+"',
                    lambda m: f'{m.group(1)}{rgba.width}{m.group(2)}{rgba.height}"', s)
        if s2 != s:
            open(page, "w", encoding="utf-8").write(s2)
            print(f"  已同步 {page} 的 width/height")

    if write_logo:
        print(f"{OUT}  {rgba.size}  {os.path.getsize(OUT)//1024} KB"
              f"  比例 {rgba.width/rgba.height:.2f}")
        print("改圖後記得跑 bump_assets.py（圖片走快取優先，網址不帶 ?v=）")


if __name__ == "__main__":
    main()
