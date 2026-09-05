# -*- coding: utf-8 -*-
"""把血液透析中心網站的原圖壓成實際要用的尺寸。

    dialysis/img_src/<名稱>.jpg   ← 生圖工具產出的原圖（好幾 MB）
        ↓  python make_dialysis_img.py
    dialysis/img/<名稱>.jpg       ← 網站實際載入的圖

和 make_hero.py 分開的理由：那支是護腎教室用的，全部壓成同一個 16:9 尺寸；
這個站每一張圖的用途與比例都不一樣（主視覺 16:9、關於中心 4:5、
流程橫幅 3:1、卡片 4:3／16:9），硬套同一個尺寸會把構圖裁壞。

原圖不進版控（dialysis/img_src/ 已列入 .gitignore），網站只需要壓過的那份。
換圖時把新原圖丟回 img_src/ 重跑這支即可。

    python make_dialysis_img.py           全部重壓
    python make_dialysis_img.py hero      只壓指定的幾張
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
SRC = ROOT / "dialysis" / "img_src"
OUT = ROOT / "dialysis" / "img"

QUALITY = 82
EXTS = (".jpg", ".jpeg", ".png", ".webp")

# 名稱 → (寬, 高)。尺寸的依據是「版面上最大顯示寬度 × 2（視網膜）」，
# 再大只是浪費頻寬。版面寬度改了，這張表要跟著檢討。
#
#   hero          滿版橫幅，最大顯示 1600 → 1920 夠用（超過 2 倍的實際需求）
#   about-center  雙欄的左半，最大約 500 → 1000
#   band-process  滿版橫幅但上面壓深藍遮罩，細節看不出來，2000 寬綽綽有餘
#   svc-/col-     卡片縮圖，四欄時每張約 265，單欄時滿版約 340 → 900
SIZES: dict[str, tuple[int, int]] = {
    "hero":          (1920, 1080),   # 16:9
    "about-center":  (1200, 900),    # 4:3（空間感的橫式，不是人像的直式）
    "band-process":  (2000, 667),    # 3:1
    "svc-hd":        (900, 675),     # 4:3
    "svc-hdf":       (900, 675),
    "svc-access":    (900, 675),
    "svc-care":      (900, 675),
    "col-diet":      (900, 506),     # 16:9
    "col-fluid":     (900, 506),
    "col-fistula":   (900, 506),
    "col-travel":    (900, 506),
}
# 標誌保持 PNG：要去背，轉成 JPEG 會多一塊白底
LOGOS = {"logo": 512, "logo-white": 512}
OG = (1200, 630)   # 由 hero 裁出來，不必另外生圖


def plan(sw: int, sh: int, w: int, h: int) -> tuple[int, int]:
    """來源不夠大時，把目標等比縮小到剛好不放大為止。

    寧可輸出小一點也不放大：放大出來的圖在視網膜螢幕上是糊的，
    而且檔案還變大——兩頭都輸。輸出比理想值小的，main() 會列出來。
    """
    scale = max(w / sw, h / sh)
    return (round(w / scale), round(h / scale)) if scale > 1 else (w, h)


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """縮放後置中裁切（cover），不拉伸變形。

    prompt 裡已經要求主體壓在畫面中間 60%，所以置中裁邊不會傷到主體。
    """
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    sw, sh = im.size
    scale = max(w / sw, h / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def main() -> int:
    if not SRC.is_dir():
        SRC.mkdir(parents=True, exist_ok=True)
        sys.exit(f"原圖請放這裡：{SRC}\n檔名見「網站圖片_Prompt.txt」，一個字都不能改。")

    want = set(sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in SRC.iterdir()
                   if p.is_file() and p.suffix.lower() in EXTS)
    if not files:
        sys.exit(f"{SRC} 裡沒有圖")

    known = set(SIZES) | set(LOGOS)
    before = after = 0
    done, skipped, unknown, small = [], [], [], []
    print(f"{'檔名':<24}{'尺寸':>12}{'原始':>10}{'輸出':>10}")

    for p in files:
        name = p.stem
        if want and name not in want:
            skipped.append(name)
            continue
        if name not in known:
            unknown.append(p.name)
            continue

        with Image.open(p) as im:
            if name in LOGOS:
                # 去背 PNG：等比縮到指定邊長，不裁切
                side = LOGOS[name]
                im = im.convert("RGBA")
                im.thumbnail((side, side), Image.LANCZOS)
                dst = OUT / f"{name}.png"
                im.save(dst, "PNG", optimize=True)
                dim = f"{im.width}x{im.height}"
            else:
                ideal = SIZES[name]
                w, h = plan(im.width, im.height, *ideal)
                if (w, h) != ideal:
                    small.append((name, f"{im.width}x{im.height}",
                                  f"{w}x{h}", f"{ideal[0]}x{ideal[1]}"))
                out = fit(im, w, h)
                dst = OUT / f"{name}.jpg"
                # progressive：大圖在慢速連線上由模糊漸清，不是一列一列刷
                out.save(dst, "JPEG", quality=QUALITY, optimize=True,
                         progressive=True)
                dim = f"{w}x{h}"

        b, a = p.stat().st_size / 1024, dst.stat().st_size / 1024
        before, after = before + b, after + a
        done.append(name)
        print(f"{dst.name:<24}{dim:>12}{b:>9,.0f}K{a:>9,.0f}K")

    # 分享預覽圖：直接從主視覺裁 1200x630，不必另外生一張
    hero = OUT / "hero.jpg"
    if hero.exists() and (not want or "hero" in want):
        with Image.open(hero) as im:
            fit(im, *OG).save(OUT / "og.jpg", "JPEG", quality=QUALITY,
                              optimize=True, progressive=True)
        print(f"{'og.jpg':<24}{f'{OG[0]}x{OG[1]}':>12}"
              f"{'（由 hero 裁出）':>21}")

    if before:
        print(f"\n{len(done)} 張　{before / 1024:.1f} MB → {after / 1024:.1f} MB"
              f"（{after / before:.0%}）")
    if small:
        print("\n⚠ 原圖不夠大，輸出比理想尺寸小（不放大，放大只會糊）：")
        print(f"    {'檔名':<16}{'原圖':>12}{'實際輸出':>12}{'理想':>12}")
        for n, s, a, i in small:
            print(f"    {n:<16}{s:>12}{a:>12}{i:>12}")
        print("  版面照樣正常，只是在高解析螢幕上會偏軟。"
              "重生一張大的丟回 img_src/ 重跑即可。")
    if unknown:
        print(f"\n⚠ 檔名不認得，沒有處理：{'、'.join(unknown)}")
        print("  檔名必須和 prompt 裡那一行完全一樣，程式靠檔名決定尺寸。")
        print(f"  認得的有：{'、'.join(sorted(known))}")
    missing = sorted(k for k in known
                     if not (OUT / f"{k}.jpg").exists()
                     and not (OUT / f"{k}.png").exists())
    if missing:
        print(f"\n還沒放的圖（版面會顯示漸層佔位塊，不會破圖）：{'、'.join(missing)}")
    print("\n接著跑：python build_dialysis.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
