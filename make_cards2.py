# -*- coding: utf-8 -*-
"""補做 19 份附件，讓每個名稱寫「附」的知識商品都真的有東西可下載。

原本 60 個商品裡有 24 個名稱寫了「附」，但只有 5 個做了實體附件
（make_cards.py）。其餘 19 個的內容雖然在知識卡本文都有交代，
但使用者買了看不到 📎、也沒東西可下載，會覺得少給了。

版型沿用 make_cards.py：A4 @150dpi = 1240x1754，色帶標頭 + 內容區 +
頁尾免責與出處。差別是這裡改成資料驅動 —— 19 份只是 SHEETS 裡的
19 筆設定，不必各寫一個函式。

每份的醫學內容都對應知識卡本文，出處寫在各自的頁尾。
"""
import os, sys

from PIL import ImageFont

from make_cards import (canvas, text, wrap, box, A4, M,
                        INK, DIM, LINE, RED, OK, AMBER, F)

sys.stdout.reconfigure(encoding="utf-8")
os.makedirs("cards", exist_ok=True)

# 分類色，與知識卡的配色一致
CAT_COLOR = {
    "用藥安全": (124, 92, 255), "警訊與迷思": (178, 58, 72),
    "飲食護腎": (46, 160, 110), "生活習慣": (59, 130, 196),
    "檢查數值": (91, 110, 225), "血壓管理": (214, 51, 87),
    "血糖管理": (222, 132, 30), "血脂代謝": (190, 150, 30),
}
TINT = lambda c: tuple(min(255, int(v + (255 - v) * 0.90)) for v in c)


def header(d, title, sub, accent):
    d.rectangle([0, 0, A4[0], 150], fill=accent)
    text(d, (M, 44), title, 42, True, (255, 255, 255))
    text(d, (M, 102), sub, 19, False, (255, 255, 255))
    text(d, (A4[0] - M, 60), "護腎教室", 26, True, (255, 255, 255), anchor="ra")
    text(d, (A4[0] - M, 100), "KidneyGod.Studio", 16, False, (255, 255, 255), anchor="ra")


def foot(d, note):
    d.line([M, A4[1] - 118, A4[0] - M, A4[1] - 118], fill=LINE, width=2)
    wrap(d, (M, A4[1] - 100), note, 15, A4[0] - 2 * M, 1.5, DIM)
    text(d, (A4[0] - M, A4[1] - 46), "kidneygod-studio.github.io",
         15, False, DIM, anchor="ra")


def table(d, x, y, cols, rows, widths, accent, rowh=62):
    total = sum(widths)
    d.rectangle([x, y, x + total, y + rowh], fill=TINT(accent))
    cx = x
    for i, c in enumerate(cols):
        text(d, (cx + widths[i] / 2, y + rowh / 2), c, 20, True, accent, anchor="mm")
        cx += widths[i]
    def cell_lines(d, v, f, maxw):
        """把儲存格內容折行，同時尊重內容裡的手動換行。"""
        out = []
        for seg in v.split("\n"):
            line = ""
            for ch in seg:
                if d.textlength(line + ch, font=f) > maxw:
                    out.append(line); line = ch
                else: line += ch
            out.append(line)
        return out

    yy = y + rowh
    for ri, row in enumerate(rows):
        # 先算這一列要幾行，列高才不會壓到字
        need = 1
        for i, cell in enumerate(row):
            v, bold = (cell[0], len(cell) >= 3 and cell[2]) if isinstance(cell, tuple) else (cell, False)
            need = max(need, len(cell_lines(d, v, F(19, bold), widths[i] - 24)))
        h = max(rowh, 26 + need * 30)
        if ri % 2 == 1:
            d.rectangle([x, yy, x + total, yy + h], fill=(252, 251, 248))
        cx = x
        for i, cell in enumerate(row):
            if isinstance(cell, tuple):
                v = cell[0]
                col = cell[1] if len(cell) >= 2 else INK
                bold = cell[2] if len(cell) >= 3 else False
            else:
                v, col, bold = cell, INK, False
            f = F(19, bold)
            lines = cell_lines(d, v, f, widths[i] - 24)
            ty = yy + h / 2 - (len(lines) - 1) * 15
            for ln in lines:
                d.text((cx + widths[i] / 2, ty), ln, font=f, fill=col, anchor="mm")
                ty += 30
            cx += widths[i]
        d.line([x, yy, x + total, yy], fill=LINE, width=2)
        yy += h
    d.rectangle([x, y, x + total, yy], outline=LINE, width=2)
    cx = x
    for w_ in widths[:-1]:
        cx += w_
        d.line([cx, y, cx, yy], fill=LINE, width=2)
    d.line([x, y + rowh, x + total, y + rowh], fill=LINE, width=2)
    return yy


def render(spec):
    accent = CAT_COLOR[spec["cat"]]
    im, d = canvas()
    header(d, spec["title"], spec["sub"], accent)
    y = 210
    W = A4[0] - 2 * M
    for blk in spec["blocks"]:
        kind = blk[0]
        if kind == "para":
            y = wrap(d, (M, y), blk[1], 22, W, 1.7) + 22
        elif kind == "h":
            text(d, (M, y), blk[1], 27, True, accent); y += 52
        elif kind == "table":
            y = table(d, M, y, blk[1], blk[2], blk[3], accent) + 30
        elif kind == "bullets":
            for it in blk[1]:
                d.ellipse([M + 6, y + 9, M + 16, y + 19], fill=accent)
                y = wrap(d, (M + 34, y), it, 21, W - 34, 1.5) + 10
            y += 14
        elif kind == "steps":
            for lab, txt in blk[1]:
                d.ellipse([M, y - 2, M + 40, y + 38], fill=accent)
                text(d, (M + 20, y + 18), lab, 20, True, (255, 255, 255), anchor="mm")
                y = wrap(d, (M + 58, y + 2), txt, 21, W - 58, 1.5) + 14
            y += 12
        elif kind == "note":
            _, ttl, body, tone = blk
            col = {"warn": RED, "ok": OK, "info": accent, "amber": AMBER}[tone]
            f = F(19)
            lines, line = [], ""
            for ch in body:
                if d.textlength(line + ch, font=f) > W - 56: lines.append(line); line = ch
                else: line += ch
            if line: lines.append(line)
            h = 84 + len(lines) * 30
            box(d, M, y, A4[0] - M, y + h, fill=TINT(col), outline=col, r=16)
            text(d, (M + 26, y + 20), ttl, 22, True, col)
            wrap(d, (M + 26, y + 58), body, 19, W - 56, 1.55, INK)
            y += h + 26
        elif kind == "gap":
            y += blk[1]
    foot(d, spec["foot"])
    out = "cards/" + spec["file"]
    im.save(out, optimize=True)
    return out, y


def main():
    from gi_sheets import SHEETS
    seen, over = set(), []
    for sp in SHEETS:
        assert sp["file"] not in seen, "檔名重複: " + sp["file"]
        seen.add(sp["file"])
        out, endy = render(sp)
        # 頁尾分隔線在 y=1636，內容超過就代表排版溢出
        warn = "  ⚠ 內容溢出頁尾" if endy > A4[1] - 118 else ""
        over.append(sp["file"]) if warn else None
        print(f"{out:28} {os.path.getsize(out)//1024:>4} KB  結束 y={int(endy):<5}"
              f"← {sp['pid']}{warn}")
    print(f"完成 {len(SHEETS)} 份附件；溢出 {len(over)} 份 {over or ''}")


if __name__ == "__main__":
    main()
