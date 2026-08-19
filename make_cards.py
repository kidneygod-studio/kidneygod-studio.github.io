# -*- coding: utf-8 -*-
"""產生五份可下載/可列印的護腎教室附件。
A4 @150dpi = 1240x1754。醫學依據：
- 2022 台灣高血壓治療指引（居家血壓 130/80、722 原則）
- ADAG study, Diabetes Care 2008：eAG(mg/dL) = 28.7 x A1C - 46.7
- KDIGO / 糖尿病照護指引：UACR 30 / 300 分級
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
os.makedirs("cards", exist_ok=True)

REG = r"C:\Windows\Fonts\msjh.ttc"
BLD = r"C:\Windows\Fonts\msjhbd.ttc"
F = lambda s, b=False: ImageFont.truetype(BLD if b else REG, s)

ACCENT = (124, 92, 255)
INK    = (61, 44, 41)
DIM    = (138, 114, 104)
LINE   = (232, 222, 214)
BG     = (255, 253, 250)
RED    = (214, 51, 87)
OK     = (46, 194, 126)
AMBER  = (232, 161, 60)

A4 = (1240, 1754)
M  = 92


def canvas(size=A4, bg=BG):
    im = Image.new("RGB", size, bg)
    return im, ImageDraw.Draw(im)


def text(d, xy, s, size=26, bold=False, color=INK, anchor="la"):
    d.text(xy, s, font=F(size, bold), fill=color, anchor=anchor)


def wrap(d, xy, s, size, maxw, lh=1.65, color=INK, bold=False):
    """簡易中文斷行，回傳結束 y。"""
    f = F(size, bold)
    x, y = xy
    line = ""
    for ch in s:
        if ch == "\n":
            d.text((x, y), line, font=f, fill=color); line = ""; y += size * lh; continue
        if d.textlength(line + ch, font=f) > maxw:
            d.text((x, y), line, font=f, fill=color)
            line = ch; y += size * lh
        else:
            line += ch
    if line:
        d.text((x, y), line, font=f, fill=color); y += size * lh
    return y


def header(d, title, sub, w=A4[0]):
    d.rectangle([0, 0, w, 150], fill=ACCENT)
    text(d, (M, 46), title, 44, True, (255, 255, 255))
    text(d, (M, 104), sub, 20, False, (226, 216, 255))
    text(d, (w - M, 62), "護腎教室", 26, True, (255, 255, 255), anchor="ra")
    text(d, (w - M, 100), "KidneyGod.Studio", 16, False, (216, 204, 255), anchor="ra")


def footer(d, note, w=A4[0], h=A4[1]):
    d.line([M, h - 118, w - M, h - 118], fill=LINE, width=2)
    y = wrap(d, (M, h - 100), note, 15, w - 2 * M, 1.5, DIM)
    text(d, (w - M, h - 46), "kidneygod-studio.github.io", 15, False, DIM, anchor="ra")


def box(d, x0, y0, x1, y1, fill=None, outline=LINE, r=16, width=2):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=width)


def table(d, x, y, cols, rows, widths, rowh=64, head_bg=(246, 242, 255)):
    """畫表格，回傳結束 y。"""
    total = sum(widths)
    d.rectangle([x, y, x + total, y + rowh], fill=head_bg)
    cx = x
    for i, c in enumerate(cols):
        text(d, (cx + widths[i] / 2, y + rowh / 2), c, 21, True, ACCENT, anchor="mm")
        cx += widths[i]
    yy = y + rowh
    for r_i, row in enumerate(rows):
        if r_i % 2 == 1:
            d.rectangle([x, yy, x + total, yy + rowh], fill=(252, 250, 255))
        cx = x
        for i, cell in enumerate(row):
            val, col = (cell if isinstance(cell, tuple) else (cell, INK))
            text(d, (cx + widths[i] / 2, yy + rowh / 2), val, 20, False, col, anchor="mm")
            cx += widths[i]
        yy += rowh
    d.rectangle([x, y, x + total, yy], outline=LINE, width=2)
    cx = x
    for w_ in widths[:-1]:
        cx += w_
        d.line([cx, y, cx, yy], fill=LINE, width=2)
    for i in range(len(rows) + 1):
        d.line([x, y + rowh * i, x + total, y + rowh * i], fill=LINE, width=2)
    return yy


# ══════════ 1. 「先問藥師」提示卡 ══════════
def card_pharmacist():
    W, H = 1050, 660
    im, d = canvas((W, H), (255, 255, 255))
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=28, outline=ACCENT, width=5)
    d.rounded_rectangle([8, 8, W - 8, 124], radius=28, fill=ACCENT)
    d.rectangle([8, 96, W - 8, 124], fill=ACCENT)
    text(d, (46, 40), "用藥前，先問藥師", 42, True, (255, 255, 255))
    text(d, (W - 46, 52), "腎臟保護卡", 22, True, (226, 216, 255), anchor="ra")

    y = 156
    text(d, (46, y), "① 主動告訴藥師／醫師", 24, True, ACCENT); y += 44
    for s in ("我有腎臟病／腎功能不好（可出示最近一次 eGFR）",
              "我正在吃的藥：降壓藥、利尿劑、糖尿病藥、中草藥、保健食品",
              "我最近有腹瀉、嘔吐、發燒或流汗很多（可能脫水）"):
        d.ellipse([50, y + 10, 62, y + 22], fill=INK)
        wrap(d, (78, y), s, 21, W - 130, 1.5)
        y += 40

    y += 18
    text(d, (46, y), "② 一定要問的三句話", 24, True, ACCENT); y += 44
    for s in ("這個藥傷腎嗎？", "以我的腎功能，可以吃嗎？", "劑量需要調整嗎？"):
        d.ellipse([50, y + 10, 62, y + 22], fill=INK)
        wrap(d, (78, y), s, 21, W - 130, 1.5)
        y += 38

    y += 16
    box(d, 40, y, W - 40, y + 96, fill=(255, 242, 245), outline=RED, r=16)
    text(d, (62, y + 18), "※ 紅線", 20, True, RED)
    wrap(d, (62, y + 48), "不自行購買止痛藥（NSAID）、不吃來路不明的止痛粉與草藥。"
                          "止痛請先問過藥師或醫師。", 18, W - 130, 1.45, INK)

    text(d, (46, H - 46), "護腎教室 KidneyGod.Studio｜衛教用途，不取代醫囑",
         15, False, DIM)
    im.save("cards/card-nsaid.png", optimize=True)
    return "cards/card-nsaid.png"


# ══════════ 2. 居家血壓量測對照表 ══════════
def table_bp():
    im, d = canvas()
    header(d, "居家血壓對照表", "依 2022 台灣高血壓治療指引｜以居家血壓為判讀依據")
    y = 210
    y = wrap(d, (M, y), "新版指引改以「居家血壓」為主要判斷依據，"
                        "並把高血壓診斷標準下修至 130/80 mmHg。"
                        "請以連續 7 天的平均值判讀，而非單次數值。", 22, A4[0] - 2 * M, 1.7)
    y += 24
    y = table(d, M, y,
              ["居家血壓平均（mmHg）", "判讀", "建議"],
              [[("< 120 / < 80", OK), "理想", "維持生活型態"],
               ["120–129 / < 80", "偏高", "調整飲食與運動，持續追蹤"],
               [("≧ 130 或 ≧ 80", AMBER), "達高血壓標準", "帶紀錄就醫評估"],
               [("≧ 180 或 ≧ 120", RED), "危險", "立即就醫"]],
              [430, 250, 376], rowh=72)

    y += 56
    text(d, (M, y), "722 量測原則", 30, True, ACCENT); y += 52
    for n, s in (("7", "連續 7 天量測"), ("2", "早、晚各 2 次"), ("2", "每次量 2 遍，間隔 1 分鐘取平均")):
        d.ellipse([M, y - 2, M + 40, y + 38], fill=ACCENT)
        text(d, (M + 20, y + 18), n, 24, True, (255, 255, 255), anchor="mm")
        wrap(d, (M + 60, y + 2), s, 22, A4[0] - 2 * M - 60, 1.5)
        y += 58

    y += 20
    text(d, (M, y), "量測前後注意事項", 30, True, ACCENT); y += 52
    for s in ("量測前靜坐休息 5 分鐘，先上廁所（膀胱脹會使血壓偏高）",
              "背靠椅背、雙腳平放地面，不翹腳",
              "手臂與心臟同高，袖帶直接綁在上臂，不隔厚衣服",
              "早上：起床後 1 小時內、服藥前；晚上：睡前",
              "量測前 30 分鐘不喝咖啡因飲料、不抽菸、不運動"):
        d.ellipse([M + 4, y + 11, M + 15, y + 22], fill=ACCENT)
        y = wrap(d, (M + 34, y), s, 21, A4[0] - 2 * M - 34, 1.5)
        y += 8

    footer(d, "本表為一般衛教參考，血壓目標可能因年齡、糖尿病、慢性腎臟病等狀況而個別化，"
              "請以主治醫師建議為準。資料依據：2022 台灣高血壓治療指引"
              "（台灣高血壓學會、中華民國心臟學會）。")
    im.save("cards/table-bp.png", optimize=True)
    return "cards/table-bp.png"


# ══════════ 3. 722 血壓紀錄表 ══════════
def sheet_722():
    im, d = canvas()
    header(d, "722 居家血壓紀錄表", "連續 7 天．早晚各 2 次．每次量 2 遍取平均")
    y = 196
    text(d, (M, y), "姓名：", 22, True); d.line([M + 76, y + 34, M + 380, y + 34], fill=INK, width=2)
    text(d, (M + 420, y), "紀錄期間：", 22, True)
    d.line([M + 540, y + 34, A4[0] - M, y + 34], fill=INK, width=2)
    y += 74

    colw = [96, 168, 168, 172, 168, 168, 172]
    heads = ["日期", "早 第1遍", "早 第2遍", "早 平均", "晚 第1遍", "晚 第2遍", "晚 平均"]
    total = sum(colw)
    d.rectangle([M, y, M + total, y + 62], fill=(246, 242, 255))
    cx = M
    for i, h in enumerate(heads):
        text(d, (cx + colw[i] / 2, y + 31), h, 18, True, ACCENT, anchor="mm")
        cx += colw[i]
    yy = y + 62
    ROWH = 92
    for i in range(7):
        if i % 2 == 1:
            d.rectangle([M, yy, M + total, yy + ROWH], fill=(252, 250, 255))
        text(d, (M + colw[0] / 2, yy + ROWH / 2), f"第 {i+1} 天", 17, False, DIM, anchor="mm")
        # 平均欄底色標示
        cx = M
        for j, w_ in enumerate(colw):
            if j in (3, 6):
                d.rectangle([cx, yy, cx + w_, yy + ROWH], fill=(240, 255, 248))
            cx += w_
        yy += ROWH
    d.rectangle([M, y, M + total, yy], outline=INK, width=2)
    cx = M
    for w_ in colw[:-1]:
        cx += w_
        d.line([cx, y, cx, yy], fill=LINE, width=2)
    for i in range(8):
        d.line([M, y + 62 + ROWH * i, M + total, y + 62 + ROWH * i], fill=LINE, width=2)
    d.line([M, y + 62, M + total, y + 62], fill=INK, width=2)

    yy += 40
    box(d, M, yy, A4[0] - M, yy + 168, fill=(246, 242, 255), outline=ACCENT, r=16)
    text(d, (M + 28, yy + 22), "一週平均值", 24, True, ACCENT)
    text(d, (M + 28, yy + 74), "收縮壓　　　　　　　／　舒張壓　　　　　　　mmHg", 24, True, INK)
    wrap(d, (M + 28, yy + 118), "判讀：平均 ≧ 130 / 80 mmHg 即達高血壓標準，"
                                "請帶著本表回診與醫師討論。", 18, A4[0] - 2 * M - 56, 1.4, DIM)
    yy += 196
    wrap(d, (M, yy), "填寫提醒：量測前靜坐 5 分鐘、先上廁所；背靠椅背、雙腳平放、不翹腳；"
                     "手臂與心臟同高。早上於起床後 1 小時內、服藥前量；晚上於睡前量。"
                     "每次量 2 遍，間隔約 1 分鐘，兩遍取平均填入綠色欄位。",
         18, A4[0] - 2 * M, 1.6, DIM)

    footer(d, "本表為一般衛教用途，不取代醫師診斷與治療建議。"
              "依據 2022 台灣高血壓治療指引之 722 居家血壓量測原則。")
    im.save("cards/sheet-722.png", optimize=True)
    return "cards/sheet-722.png"


# ══════════ 4. HbA1c 換算表 ══════════
def table_a1c():
    im, d = canvas()
    header(d, "HbA1c 平均血糖換算表", "依 ADAG 研究：eAG(mg/dL) = 28.7 × A1C - 46.7")
    y = 210
    y = wrap(d, (M, y), "糖化血色素（HbA1c）反映近二至三個月的平均血糖。"
                        "下表把 HbA1c 換算成「估計平均血糖（eAG）」，"
                        "讓你把化驗數字對應到平常自測的血糖機讀數。", 22, A4[0] - 2 * M, 1.7)
    y += 26

    rows = []
    for i in range(15):
        a1c = 5.0 + i * 0.5
        eag = 28.7 * a1c - 46.7
        mmol = eag / 18.0
        if a1c < 5.7:      note, col = "正常範圍", OK
        elif a1c < 6.5:    note, col = "糖尿病前期", AMBER
        elif a1c <= 7.0:   note, col = "多數成人控制目標", ACCENT
        else:              note, col = "高於一般目標", RED
        rows.append([f"{a1c:.1f} %", f"{eag:.0f}", f"{mmol:.1f}", (note, col)])
    y = table(d, M, y, ["HbA1c", "eAG (mg/dL)", "eAG (mmol/L)", "一般判讀"],
              rows, [230, 260, 260, 306], rowh=62)

    y += 40
    box(d, M, y, A4[0] - M, y + 150, fill=(255, 250, 240), outline=AMBER, r=16)
    text(d, (M + 26, y + 20), "重要提醒", 22, True, AMBER)
    wrap(d, (M + 26, y + 58),
         "控制目標需個別化：年輕、病程短、無併發症者可更嚴格；"
         "年長、有心血管疾病、易低血糖或獨居者，醫師可能放寬至 7.5–8%。"
         "腎功能不佳者因藥物清除變慢，低血糖風險較高，目標通常較寬鬆。",
         18, A4[0] - 2 * M - 52, 1.5, INK)

    footer(d, "eAG 為統計估計值，與個人實際血糖仍可能有差異；貧血、腎臟病、"
              "血色素變異等狀況會影響 HbA1c 準確度。控制目標請以主治醫師設定為準。"
              "公式來源：Nathan DM et al., Diabetes Care 2008（ADAG study）。")
    im.save("cards/table-a1c.png", optimize=True)
    return "cards/table-a1c.png"


# ══════════ 5. 糖尿病腎病變路徑圖 ══════════
def chart_dn():
    im, d = canvas()
    header(d, "糖尿病腎病變 進程路徑圖", "越早發現，越有機會延緩甚至逆轉")
    y = 206
    y = wrap(d, (M, y), "糖尿病傷腎的過程幾乎沒有症狀。下圖標出各階段的檢驗表現與可介入程度——"
                        "真正能改變結果的窗口，在前兩個階段。", 22, A4[0] - 2 * M, 1.7)
    y += 30

    stages = [
        ("第 1 階段", "腎絲球高過濾", "eGFR 正常或偏高、UACR < 30",
         "血糖與血壓控制良好即可維持", OK, "可逆"),
        ("第 2 階段", "微量白蛋白尿", "UACR 30–300 mg/g、eGFR 多半仍正常",
         "介入黃金期：控糖控壓、ACEI/ARB、SGLT2i", AMBER, "可延緩、部分可逆"),
        ("第 3 階段", "巨量白蛋白尿", "UACR > 300 mg/g、eGFR 開始下降",
         "積極用藥延緩惡化，評估 finerenone", (232, 120, 60), "難以逆轉"),
        ("第 4 階段", "腎功能持續惡化", "eGFR < 60 並逐年下降",
         "腎臟科追蹤、控制併發症、準備長期照護", RED, "不可逆"),
        ("第 5 階段", "末期腎病", "eGFR < 15",
         "透析或腎臟移植", (150, 40, 70), "需替代療法"),
    ]
    for i, (no, name, lab, act, col, rev) in enumerate(stages):
        h = 148
        box(d, M, y, A4[0] - M, y + h, fill=(255, 255, 255), outline=col, r=18, width=3)
        d.rounded_rectangle([M, y, M + 14, y + h], radius=7, fill=col)
        text(d, (M + 40, y + 20), no, 18, True, col)
        text(d, (M + 40, y + 50), name, 30, True, INK)
        text(d, (M + 40, y + 94), lab, 19, False, DIM)
        text(d, (M + 40, y + 120), "→ " + act, 19, False, INK)
        tw = d.textlength(rev, font=F(18, True))
        d.rounded_rectangle([A4[0] - M - tw - 44, y + 18, A4[0] - M - 18, y + 56],
                            radius=10, fill=col)
        text(d, (A4[0] - M - tw / 2 - 31, y + 37), rev, 18, True, (255, 255, 255), anchor="mm")
        y += h
        if i < len(stages) - 1:
            cx = A4[0] // 2
            d.polygon([(cx - 16, y + 6), (cx + 16, y + 6), (cx, y + 30)], fill=LINE)
            y += 38

    y += 16
    box(d, M, y, A4[0] - M, y + 116, fill=(240, 255, 248), outline=OK, r=16)
    text(d, (M + 26, y + 18), "你唯一要記住的事", 22, True, OK)
    wrap(d, (M + 26, y + 54),
         "尚未有腎病變者每年檢查一次 UACR 與 eGFR；已診斷者每 3–6 個月追蹤一次。"
         "前兩階段完全沒有症狀，只能靠驗尿抓到。", 19, A4[0] - 2 * M - 52, 1.5, INK)

    footer(d, "本圖為一般衛教示意，實際分期與治療需由醫師依完整檢查結果判斷。"
              "分級依據：UACR 30 / 300 mg/g 與 eGFR 分期（KDIGO）；"
              "追蹤頻率依糖尿病照護指引。")
    im.save("cards/chart-dn.png", optimize=True)
    return "cards/chart-dn.png"


if __name__ == "__main__":
    for fn in (card_pharmacist, table_bp, sheet_722, table_a1c, chart_dn):
        p = fn()
        print(f"{p}  {os.path.getsize(p)//1024} KB")
