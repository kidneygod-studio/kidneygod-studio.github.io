# -*- coding: utf-8 -*-
"""從貼圖表切出獨立貼圖。

輸出的是「白底、不透明」的圖：貼圖本身就有一圈模切白框，白底才是它原本
被設計的樣子。之前做成透明去背，放到深色底上會看到殘留的白邊，像是沒清乾淨。
遮罩仍然要算 —— 用來把鄰格滲進來的碎片塗白，不是用來做透明通道。

三種來源各有處理方式：
  透明去背圖（5/6.png）→ 直接用 alpha 通道當遮罩，最乾淨
  白底圖（1~3.png）    → 由邊界 flood fill 去白底（貓咪本身也是白的，不能用色階門檻）
  密集白底圖（4.png）  → 排版不均勻，切線在等分線附近搜尋投影谷底，避免切進貼圖本體

共同的關鍵步驟是「只保留主體那一群」：先把遮罩膨脹一個半徑，讓貓咪與它的
文字、愛心、星星黏成同一群，再只保留含最大連通塊的那一群 —— 鄰格滲進來的
碎片離主體較遠，會被歸到別群而丟棄。半徑取格子短邊的 4.5%
（實測 3% 會誤刪合法元素、6% 則清不掉滲入的碎片）。
"""
import os, sys, json
import numpy as np
from PIL import Image
from scipy import ndimage

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"C:\Users\user\Downloads\貓咪貼圖"
GROUP_RADIUS_FRAC = 0.045

SHEETS = {
 1: dict(set="A", grid=(3,3), mode="white", labels=[
    "哈囉！","晚安囉～","謝謝你！",
    "讚！","哇！","嗚嗚…",
    "在嗎？","愛你唷！","先走囉～"]),
 2: dict(set="B", grid=(5,5), mode="white", labels=[
    "哈囉！","謝謝你！","晚安囉～","耶耶耶！","好開心！",
    "讚！","嗚嗚…","哇！","在嗎？","愛你唷！",
    "在幹嘛？","嗯…","對不起…","加油！","辛苦了～",
    "出發囉！","努力中！","餓餓…","抱抱～","工作中…",
    "我可以！","偷看…","生日快樂！","累癱了…","先走囉～"]),
 3: dict(set="C", grid=(6,5), mode="white", labels=[
    "哈囉！","謝謝你！","晚安囉～","耶耶耶！","好開心！","讚！",
    "在幹嘛？","嗯？","嗚嗚…","哇！","愛你唷！","嘿嘿～",
    "我可以！","認真中…","加油！","累癱了…","抱抱～","工作中…",
    "辛苦了～","好餓喔…","生日快樂！","哼哼！","蛤?!","得意～",
    "偷偷看…","放鬆一下～","哇嗚～","瘋掉了啦！","拜託嘛～","先走囉～"]),
 5: dict(set="D", grid=(4,4), mode="alpha", labels=[
    "哈囉！","謝謝你！","晚安囉～","耶耶耶！",
    "在嗎？","讚！","好開心！","辛苦了～",
    "嗯？","嗚嗚嗚…","我要吃！","好可愛！",
    "放鬆一下～","先走囉～","生日快樂！","累癱了…"]),
 6: dict(set="E", grid=(4,4), mode="alpha", labels=[
    "超開心！","讚爆！","偷偷看～","哈哈哈！",
    "我先睡了…","蛤?!","衝啊～","人家錯了…",
    "愛你喔！","帥啦～","在嗎？","加油！",
    "嗯？？","嘻嘻～","哼！","先走囉～"]),
 4: dict(set="F", grid=(8,7), mode="white", rows_auto=True, labels=[
    "哈囉！","謝謝你！","晚安囉～","耶耶耶！","好開心！","讚！","愛你喔！","嘿嘿～",
    "在嗎？","嗯？","嗚嗚…","哇！","真的嗎？","太棒了！","拜託嘛～","好呀！",
    "必勝！","認真中…","加油！","累癱了…","抱抱～","工作中…","辛苦了～","好餓喔…",
    "偷看…","放鬆一下～","哇嗚～","生日快樂！","蛤?!","嗚嗚嗚！","得意～","先走囉～",
    "我不懂…","讓我想想…","有了！","哈哈哈！","拜託你了～","好可愛！","生氣氣！","哼！",
    "好累喔…","不敢相信！","沒問題！","討厭啦～","要抱抱～","看到美食！","追劇中…","晚安～",
    "送你花花！","OK！","收到！","感謝！","對不起…","萬歲！","怎麼辦…","愛你們喔！"]),
}

# 有特殊造型／道具者為稀有款
SPECIAL = {
 "B14","B16","B17","B21","B23","C13","C14","C15","C21","C26","C27",
 "D05","D11","D13","D15",
 "E07","E10","E11","E12",
 "F17","F18","F19","F22","F23","F26","F27","F28","F47","F48","F49",
}
BASE  = {"A":1000, "B":600, "C":500, "D":750, "E":750, "F":500}
RARE  = {"A":1000, "B":750, "C":620, "D":900, "E":900, "F":620}
def price(sid):
    return (RARE if sid in SPECIAL else BASE)[sid[0]]


def sheet_mask(im, mode):
    """整張表的內容遮罩。"""
    if mode == "alpha":
        return np.asarray(im.convert("RGBA"))[:, :, 3] > 40
    a = np.asarray(im.convert("RGB")).astype(int)
    return a.min(axis=2) < 238


def refine_cuts(proj, n, frac=0.18):
    """在每條等分線附近搜尋投影谷底當切線。

    貼圖排版常常不是均勻等分（列高不等、間距不一），直接等分會切進貼圖本體，
    把鄰格內容帶進來。改在等分線 ±18% 範圍內找投影最低點，切在縫隙上。
    """
    L = len(proj); step = L / n
    cuts = [0]
    for k in range(1, n):
        nom = int(k * step); w = max(3, int(step * frac))
        lo, hi = max(1, nom - w), min(L - 1, nom + w)
        cuts.append(lo + int(np.argmin(proj[lo:hi])))
    cuts.append(L)
    return cuts


def cell_mask(cell, mode):
    """單格的前景遮罩。"""
    if mode == "alpha":
        return np.asarray(cell)[:, :, 3] > 40
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
    meta, cleaned, warn = [], [], []
    for sh in sorted(SHEETS):
        cfg = SHEETS[sh]
        cols, rows = cfg["grid"]
        mode = cfg["mode"]
        im = Image.open(os.path.join(SRC, f"{sh}.png"))
        im = im.convert("RGBA") if mode == "alpha" else im.convert("RGB")
        W, H = im.size

        smask = sheet_mask(im, mode)
        ycuts = refine_cuts(smask.sum(axis=1), rows)
        xcuts = refine_cuts(smask.sum(axis=0), cols)

        for r in range(rows):
            for c in range(cols):
                i = r * cols + c
                if i >= len(cfg["labels"]): continue
                sid = f"{cfg['set']}{i+1:02d}"
                cell = im.crop((xcuts[c], ycuts[r], xcuts[c+1], ycuts[r+1]))

                fg = cell_mask(cell, mode)
                if fg.sum() < 400:
                    warn.append((sid, "幾乎沒有內容")); continue
                rd = max(3, int(min(cell.size) * GROUP_RADIUS_FRAC))
                fg, dropped = keep_main_group(fg, rd)
                if dropped > 300: cleaned.append((sid, dropped))

                # 保留白底、不做透明：把「不是主體」的區域（含鄰格滲進來的碎片）
                # 直接塗白。貼圖本身就有一圈模切白框，白底才是它原本的樣子；
                # 透明去背在深色底上會露出殘留的白邊，反而像沒清乾淨。
                arr = np.asarray(cell.convert("RGB")).copy()
                arr[~fg] = 255
                ys, xs = np.where(fg)
                pad = max(6, int(min(cell.size) * 0.03))
                x0, x1 = max(0, xs.min()-pad), min(arr.shape[1], xs.max()+1+pad)
                y0, y1 = max(0, ys.min()-pad), min(arr.shape[0], ys.max()+1+pad)
                out = Image.fromarray(arr[y0:y1, x0:x1])

                m = max(out.size)
                if m > 320:
                    out = out.resize((round(out.width * 320 / m),
                                      round(out.height * 320 / m)), Image.LANCZOS)
                # 白底讓 PNG 的壓縮效率變差，用調色盤量化把體積壓回來
                out.quantize(colors=192, method=Image.FASTOCTREE).save(
                    f"stickers/{sid}.png", optimize=True)
                th = out.copy(); th.thumbnail((150, 150), Image.LANCZOS)
                th.quantize(colors=128, method=Image.FASTOCTREE).save(
                    f"stickers/thumb/{sid}.png", optimize=True)
                rgba = out

                meta.append(dict(id=sid, set=cfg["set"], label=cfg["labels"][i],
                                 file=f"stickers/{sid}.png", thumb=f"stickers/thumb/{sid}.png",
                                 price=price(sid), rare=sid in SPECIAL,
                                 w=rgba.width, h=rgba.height))

    json.dump(meta, open("stickers_meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    tot = sum(os.path.getsize(m["file"]) for m in meta)
    tht = sum(os.path.getsize(m["thumb"]) for m in meta)
    from collections import Counter
    print(f"完成 {len(meta)} 張｜原圖 {tot//1024} KB／縮圖 {tht//1024} KB")
    print("各組:", dict(Counter(m["set"] for m in meta)))
    print(f"清掉鄰格碎片 {len(cleaned)} 張，最大 "
          f"{max(cleaned, key=lambda x: x[1]) if cleaned else '-'}")
    if warn: print("⚠ 需檢查:", warn)


if __name__ == "__main__":
    main()
