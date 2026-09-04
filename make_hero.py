# -*- coding: utf-8 -*-
"""把長文大圖的原圖壓成網站要用的尺寸。

    hero_src/<slug>.jpg   ← 生圖工具產出的原圖（2752x1536 之類，好幾 MB）
        ↓  python make_hero.py
    hero/<slug>.jpg       ← 首頁實際載入的圖（1600x900，200 KB 上下）

為什麼要有這一層：原圖 13 張加起來 26.6 MB。首頁「深入文章」一次列 13 篇，
直接掛原圖等於叫讀者下載 26 MB——手機上會慢到看不下去，Core Web Vitals
也會直接把好不容易做起來的 SEO 拉下來。

為什麼是 1600x900：衛教站的內容欄 --maxw 是 720px，扣掉左右內距實際 680px。
封面卡片滿版 680px，1600 寬剛好超過 2 倍視網膜所需（1360）。再大只是浪費頻寬。
**如果哪天把 --maxw 調寬，這裡的 1600 要跟著檢討。**

為什麼原圖不進版控：hero_src/ 已列入 .gitignore。26 MB 的原圖進了 git 就永遠
在歷史裡拿不掉，而網站只需要壓過的那份。原圖留在本機即可，要換圖時重跑這支。

改圖之後記得跑 bump_assets.py：hero/ 在 sw.js 走快取優先、網址不帶 ?v=，
版本號沒換的話，造訪過的人會一直看到舊圖，而且不會有任何錯誤訊息。

用法：python make_hero.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow：python -m pip install Pillow")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "hero_src"
OUT = ROOT / "hero"

W, H = 1600, 900          # 16:9
QUALITY = 80              # 80 在這種柔光靜物上看不出壓縮痕跡，再高只是變大
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def fit(im: Image.Image) -> Image.Image:
    """縮放後置中裁切成 16:9。

    原圖是 1.79（2752x1536），目標 1.778，差一點點；用 cover 的邏輯裁掉多的邊，
    而不是硬拉變形。主體本來就要求置中構圖，所以裁邊不會傷到主體。
    """
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    sw, sh = im.size
    scale = max(W / sw, H / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - W) // 2, (nh - H) // 2
    return im.crop((left, top, left + W, top + H))


def main() -> int:
    if not SRC.is_dir():
        sys.exit(f"找不到 {SRC}——原圖請放這裡，檔名用文章的 slug")

    files = sorted(p for p in SRC.iterdir()
                   if p.is_file() and p.suffix.lower() in EXTS)
    if not files:
        sys.exit(f"{SRC} 裡沒有圖")

    OUT.mkdir(exist_ok=True)
    before = after = 0
    print(f"{'檔名':<40}{'原始':>10}{'輸出':>10}")
    for p in files:
        with Image.open(p) as im:
            out = fit(im)
        dst = OUT / (p.stem + ".jpg")
        # progressive：大圖在慢速連線上會由模糊漸清，而不是一列一列刷出來
        out.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        b, a = p.stat().st_size / 1024, dst.stat().st_size / 1024
        before, after = before + b, after + a
        print(f"{dst.name:<40}{b:>9,.0f}K{a:>9,.0f}K")

    print(f"\n{len(files)} 張　{before / 1024:.1f} MB → {after / 1024:.1f} MB"
          f"（{after / before:.0%}）　全部 {W}x{H}")
    print("接著跑：python bump_assets.py（不跑的話舊訪客會一直看到舊圖）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
