# -*- coding: utf-8 -*-
"""從三張貼圖表切出 64 張獨立貼圖。

切法：網格切割 → 由邊界 flood fill 去白底 → 只保留「主體那一群」→ 裁邊。
「主體那一群」是關鍵：先把遮罩膨脹一個半徑，讓貓咪與它的文字、愛心、星星
黏成同一群，再只保留含最大連通塊的那一群 —— 鄰格滲進來的碎片離主體較遠，
會被歸到別群而丟棄。半徑取格子短邊的 4.5%（實測 3% 會誤刪合法元素、
6% 則清不掉滲入的碎片）。
"""
import os, sys, json
import numpy as np
from PIL import Image
from scipy import ndimage

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"C:\Users\user\Downloads\貓咪貼圖"
GROUP_RADIUS_FRAC = 0.045

SHEETS = {
 1: dict(grid=(3,3), set="A", labels=[
    "哈囉！","晚安囉～","謝謝你！",
    "讚！","哇！","嗚嗚…",
    "在嗎？","愛你唷！","先走囉～"]),
 2: dict(grid=(5,5), set="B", labels=[
    "哈囉！","謝謝你！","晚安囉～","耶耶耶！","好開心！",
    "讚！","嗚嗚…","哇！","在嗎？","愛你唷！",
    "在幹嘛？","嗯…","對不起…","加油！","辛苦了～",
    "出發囉！","努力中！","餓餓…","抱抱～","工作中…",
    "我可以！","偷看…","生日快樂！","累癱了…","先走囉～"]),
 3: dict(grid=(6,5), set="C", labels=[
    "哈囉！","謝謝你！","晚安囉～","耶耶耶！","好開心！","讚！",
    "在幹嘛？","嗯？","嗚嗚…","哇！","愛你唷！","嘿嘿～",
    "我可以！","認真中…","加油！","累癱了…","抱抱～","工作中…",
    "辛苦了～","好餓喔…","生日快樂！","哼哼！","蛤?!","得意～",
    "偷偷看…","放鬆一下～","哇嗚～","瘋掉了啦！","拜託嘛～","先走囉～"]),
}
SPECIAL = {"B14","B16","B17","B21","B23","C13","C14","C15","C21","C26","C27"}
def price(sid):
    s = sid[0]
    if s == "A": return 200
    if s == "B": return 160 if sid in SPECIAL else 120
    return 110 if sid in SPECIAL else 80


def fg_mask(cell):
    """去白底：只有連到格子邊界的白才算背景（貓咪本身也是白的，不能用色階門檻）。"""
    a = np.asarray(cell.convert("RGB")).astype(int)
    white = a.min(axis=2) > 232
    lab, _ = ndimage.label(white)
    border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    border.discard(0)
    fg = ~np.isin(lab, list(border))
    fg = ndimage.binary_closing(fg, structure=np.ones((3, 3)))
    return ndimage.binary_fill_holes(fg)


def keep_main_group(fg, rd):
    """只保留含最大連通塊的那一群，丟掉鄰格滲入的碎片。"""
    lab, n = ndimage.label(fg)
    if n <= 1:
        return fg, 0
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    main = int(np.argmax(sizes)) + 1
    y, x = np.ogrid[-rd:rd + 1, -rd:rd + 1]
    grp, _ = ndimage.label(ndimage.binary_dilation(fg, structure=(x * x + y * y <= rd * rd)))
    tg = np.bincount(grp[lab == main]).argmax()
    kept = fg & (grp == tg)
    return kept, int(fg.sum() - kept.sum())


def main():
    os.makedirs("stickers/thumb", exist_ok=True)
    meta, cleaned = [], []
    for sh, cfg in SHEETS.items():
        cols, rows = cfg["grid"]
        im = Image.open(os.path.join(SRC, f"{sh}.png")).convert("RGB")
        W, H = im.size
        cw, ch = W / cols, H / rows
        for r in range(rows):
            for c in range(cols):
                i = r * cols + c
                sid = f"{cfg['set']}{i+1:02d}"
                cell = im.crop((int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch)))

                fg = fg_mask(cell)
                rd = max(3, int(min(cell.size) * GROUP_RADIUS_FRAC))
                fg, dropped = keep_main_group(fg, rd)
                if dropped > 300:
                    cleaned.append((sid, dropped))

                rgba = cell.convert("RGBA")
                rgba.putalpha(Image.fromarray((fg * 255).astype(np.uint8)))
                bb = rgba.getbbox()
                if not bb:
                    continue
                rgba = rgba.crop(bb)

                m = max(rgba.size)
                if m > 320:
                    rgba = rgba.resize((round(rgba.width * 320 / m),
                                        round(rgba.height * 320 / m)), Image.LANCZOS)
                rgba.save(f"stickers/{sid}.png", optimize=True)

                th = rgba.copy()
                th.thumbnail((150, 150), Image.LANCZOS)
                th.save(f"stickers/thumb/{sid}.png", optimize=True)

                meta.append(dict(id=sid, set=cfg["set"], label=cfg["labels"][i],
                                 file=f"stickers/{sid}.png",
                                 thumb=f"stickers/thumb/{sid}.png",
                                 price=price(sid), rare=sid in SPECIAL,
                                 w=rgba.width, h=rgba.height))

    json.dump(meta, open("stickers_meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    tot = sum(os.path.getsize(m["file"]) for m in meta)
    tht = sum(os.path.getsize(m["thumb"]) for m in meta)
    print(f"完成 {len(meta)} 張｜原圖 {tot//1024} KB／縮圖 {tht//1024} KB")
    print(f"清掉鄰格碎片的有 {len(cleaned)} 張：")
    for sid, px in sorted(cleaned, key=lambda x: -x[1]):
        print(f"   {sid}  移除 {px:6d} px")


if __name__ == "__main__":
    main()
