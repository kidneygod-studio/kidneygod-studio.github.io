# -*- coding: utf-8 -*-
"""把 60 篇護腎知識做成 Greed Island 風格的卡片。

版面依照參考卡：
  ┌──────────────────────────┐  黑色圓角外框 + 銀色細內線
  │ [編號] [   名稱   ] [等級] │  三格標頭，米色底、雙線邊框
  │ ┌──────────────────────┐ │
  │ │      中央插圖         │ │  米色襯邊包住深藍插圖
  │ └──────────────────────┘ │
  │ ┌──────────────────────┐ │
  │ │  大理石紋色帶包白框    │ │  說明文字
  │ └──────────────────────┘ │
  └──────────────────────────┘

中央插圖的來源有兩種，優先用前者：
  gi/art/{id}.png  外部繪製（Gemini 等）的插圖，有檔案就直接用
  程式繪製          深藍底 + 放射線 + 網點 + 腎臟剪影 + 主題符號章

等級由價格換算（350→SS、300→S、250→A、200→B），編號依分類排序後給定。
"""
import os, sys, json, math, random, zlib
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.stdout.reconfigure(encoding="utf-8")

W, H = 900, 1080
ART_DIR = "gi/art"
OUT_DIR = "cards/gi"

FONTS = {
    "ming":  (r"C:\Windows\Fonts\mingliu.ttc", 0),    # 新細明體
    # mingliub.ttc 是 Ext-B 專用字型，不含常用中文，別用
    "serif": (r"C:\Windows\Fonts\mingliu.ttc", 0),    # 新細明體（襯線數字）
    "kai":   (r"C:\Windows\Fonts\kaiu.ttf", 0),       # 標楷體
    "sans":  (r"C:\Windows\Fonts\msjh.ttc", 0),       # 微軟正黑體
    "bold":  (r"C:\Windows\Fonts\msjhbd.ttc", 0),     # 微軟正黑體 粗
    "emoji": (r"C:\Windows\Fonts\seguiemj.ttf", 0),
}
_fc = {}
def F(key, size):
    k = (key, size)
    if k not in _fc:
        path, idx = FONTS[key]
        _fc[k] = ImageFont.truetype(path, size, index=idx)
    return _fc[k]

# 卡面配色
INK      = (18, 18, 20)
FRAME    = (13, 13, 15)
SILVER   = (176, 176, 184)
CREAM    = (243, 236, 214)
CREAM_D  = (196, 184, 150)

# 分類 →（插圖主色, 插圖底色, 大理石色帶主色, 章印符號）
THEME = {
    "用藥安全":  ((150, 210, 255), (22, 32, 92),  (86, 62, 170),  "藥"),
    "警訊與迷思": ((255, 190, 150), (78, 20, 34),  (150, 32, 48),  "警"),
    "飲食護腎":  ((186, 240, 200), (14, 60, 52),  (26, 122, 88),  "食"),
    "生活習慣":  ((190, 226, 255), (20, 44, 86),  (44, 108, 168), "習"),
    "檢查數值":  ((198, 206, 255), (26, 30, 84),  (74, 90, 190),  "檢"),
    "血壓管理":  ((255, 186, 200), (72, 18, 40),  (186, 40, 74),  "壓"),
    "血糖管理":  ((255, 214, 160), (74, 40, 12),  (196, 112, 26), "糖"),
    "血脂代謝":  ((250, 230, 160), (66, 54, 12),  (168, 132, 26), "脂"),
}
RANK = {350: "SS", 300: "S", 250: "A", 200: "B"}
BYLINE = "護腎專家 吳政哲醫師"   # 卡片與附件共用的署名


# ═══════════ 基本繪圖工具 ═══════════

def wrap(d, text, font, maxw):
    lines, line = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(line); line = ""; continue
        if d.textlength(line + ch, font=font) > maxw:
            lines.append(line); line = ch
        else:
            line += ch
    if line: lines.append(line)
    return lines


def fit_font(d, text, key, maxw, start, floor=20):
    """把字級往下調到塞得進一行為止。"""
    s = start
    while s > floor and d.textlength(text, font=F(key, s)) > maxw:
        s -= 1
    return F(key, s)


_emoji_cache = {}
def emoji_img(ch, size):
    """Segoe UI Emoji 是點陣彩色字型，固定用 109px 繪製再縮放。"""
    key = (ch, size)
    if key in _emoji_cache: return _emoji_cache[key]
    try:
        f = ImageFont.truetype(FONTS["emoji"][0], 109)
        tmp = Image.new("RGBA", (170, 170), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((85, 85), ch, font=f, anchor="mm", embedded_color=True)
        bb = tmp.getbbox()
        out = tmp.crop(bb) if bb else None
        if out is not None:
            r = size / max(out.size)
            out = out.resize((max(1, round(out.width*r)), max(1, round(out.height*r))),
                             Image.LANCZOS)
    except Exception:
        out = None
    _emoji_cache[key] = out
    return out


def double_box(d, box, fill, outer=(18,18,20), gap=6):
    """雙線外框：粗外框 + 內縮細框，卡牌印刷常見的樣式。"""
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1, y1], fill=fill, outline=outer, width=4)
    d.rectangle([x0+gap, y0+gap, x1-gap, y1-gap], outline=outer, width=2)


def stable_seed(text):
    """Python 的 hash() 對字串每個行程都不一樣（PYTHONHASHSEED），
    拿來當亂數種子會導致同一張卡每次重跑都長得不同、git 每次都有 diff。
    改用 crc32，跨行程穩定。"""
    return zlib.crc32(text.encode("utf-8")) & 0xffff


def marble(size, base, seed):
    """大理石／雲斑紋理：多層高斯模糊雜訊疊出來的色塊。"""
    w, h = size
    rnd = random.Random(seed)
    small = Image.new("L", (max(2, w//14), max(2, h//14)))
    small.putdata([rnd.randint(0, 255) for _ in range(small.width*small.height)])
    n1 = small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(9))
    tiny = Image.new("L", (max(2, w//5), max(2, h//5)))
    tiny.putdata([rnd.randint(0, 255) for _ in range(tiny.width*tiny.height)])
    n2 = tiny.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))
    im = Image.new("RGB", (w, h))
    p1, p2 = n1.load(), n2.load()
    px = im.load()
    r0, g0, b0 = base
    for y in range(h):
        for x in range(w):
            t = (p1[x, y] * 0.75 + p2[x, y] * 0.25) / 255.0
            k = 0.72 + t * 0.46                      # 0.72~1.18，比原本柔和
            px[x, y] = (min(255, int(r0*k)), min(255, int(g0*k)), min(255, int(b0*k)))
    return im


# ═══════════ 中央插圖（程式繪製版）═══════════

def kidney_path(cx, cy, s, tilt=-0.16):
    """腎臟輪廓：橢圓在左側挖一個腎門凹口，直立豆形，s 為半高。"""
    pts = []
    for i in range(145):
        t = i / 144 * 2 * math.pi
        dt = abs((t - math.pi + math.pi) % (2*math.pi) - math.pi)   # 與左側(π)的角距
        r = 1.0 - 0.46 * math.exp(-(dt ** 2) / 0.10)
        x, y = math.cos(t) * r * 0.70, math.sin(t) * r
        xr = x * math.cos(tilt) - y * math.sin(tilt)
        yr = x * math.sin(tilt) + y * math.cos(tilt)
        pts.append((cx + xr * s, cy + yr * s))
    return pts


def draw_art(size, item):
    """深藍底 + 放射線 + 網點 + 腎臟剪影 + 主題符號章。"""
    w, h = size
    accent, bg, band, mark = THEME[item["cat"]]
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im, "RGBA")
    cx, cy = w // 2, h // 2

    # 放射線（原本還有一圈同心橢圓，但那讓畫面糊成一團，拿掉）
    for i in range(28):
        a = i / 28 * 2 * math.pi + 0.11
        d.line([cx + math.cos(a)*w*0.12, cy + math.sin(a)*w*0.12,
                cx + math.cos(a)*w*0.90, cy + math.sin(a)*w*0.90],
               fill=accent + (22 if i % 2 else 44,), width=3)

    # 網點（越外圈越密，做出印刷感）
    rnd = random.Random(stable_seed(item["id"]))
    for _ in range(420):
        a = rnd.random() * 2 * math.pi
        rr = (0.34 + rnd.random() ** 0.5 * 0.70) * w * 0.55
        x, y = cx + math.cos(a)*rr, cy + math.sin(a)*rr*0.92
        s = rnd.choice([2, 2, 3, 4])
        d.ellipse([x-s, y-s, x+s, y+s], fill=accent + (rnd.randint(30, 90),))

    # 腎臟剪影：實心一層、粗描邊，讓豆形輪廓看得出來
    ks = h * 0.42
    d.polygon(kidney_path(cx, cy, ks), fill=accent + (46,))
    d.line(kidney_path(cx, cy, ks) + [kidney_path(cx, cy, ks)[0]],
           fill=accent + (185,), width=6, joint="curve")

    # 中央徽章：只放主題符號，不放字（參考卡的插圖裡沒有文字）
    br = int(h * 0.205)
    d.ellipse([cx-br, cy-br, cx+br, cy+br], fill=(255, 255, 255, 236),
              outline=band + (255,), width=7)
    d.ellipse([cx-br+14, cy-br+14, cx+br-14, cy+br-14], outline=band + (120,), width=2)
    emo = emoji_img(item["emoji"], int(br * 1.28))
    if emo is not None:
        im.paste(emo, (cx - emo.width//2, cy - emo.height//2), emo)

    # 四角裝飾
    for sx, sy in ((1,1), (-1,1), (1,-1), (-1,-1)):
        px_, py_ = (w*0.06 if sx>0 else w*0.94), (h*0.08 if sy>0 else h*0.92)
        d.line([px_, py_, px_ + sx*38, py_], fill=accent + (170,), width=4)
        d.line([px_, py_, px_, py_ + sy*38], fill=accent + (170,), width=4)
    return im


def seal(im, item):
    """右下角的分類小圓印，像卡牌的系列符號。外部插圖與程式繪製都會蓋上。"""
    w, h = im.size
    band, mark = THEME[item["cat"]][2], THEME[item["cat"]][3]
    d = ImageDraw.Draw(im, "RGBA")
    sr = int(h * 0.078)
    sx_, sy_ = w - sr - 26, h - sr - 26
    d.ellipse([sx_-sr, sy_-sr, sx_+sr, sy_+sr], fill=band + (235,),
              outline=(255, 255, 255, 210), width=4)
    d.text((sx_, sy_ - 1), mark, font=F("bold", int(sr * 1.05)),
           fill=(255, 255, 255), anchor="mm")
    return im


def load_art(size, item):
    """有外部插圖就用外部的，否則程式繪製。副檔名 png/jpg 都收。"""
    art = None
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(ART_DIR, item["id"] + ext)
        if os.path.exists(p):
            art = Image.open(p).convert("RGB"); break
    if art is None:
        return seal(draw_art(size, item), item)
    # 置中裁切成插圖區的比例
    tw, th = size
    r = max(tw / art.width, th / art.height)
    art = art.resize((round(art.width*r), round(art.height*r)), Image.LANCZOS)
    l, t = (art.width - tw)//2, (art.height - th)//2
    return seal(art.crop((l, t, l+tw, t+th)), item)


# ═══════════ 卡片 ═══════════

def make_card(item, no, rank, out):
    accent, bg, band, mark = THEME[item["cat"]]
    im = Image.new("RGB", (W, H), FRAME)
    d = ImageDraw.Draw(im)

    # 外框：黑底 + 銀色細內線
    d.rounded_rectangle([6, 6, W-7, H-7], radius=30, fill=FRAME,
                        outline=SILVER, width=3)
    d.rounded_rectangle([16, 16, W-17, H-17], radius=22, outline=(60, 60, 66), width=2)

    M = 44
    # ── 標頭三格 ──
    hy0, hy1 = 54, 162
    nx1 = M + 150                      # 編號格
    rx0 = W - M - 168                  # 等級格
    double_box(d, [M, hy0, nx1, hy1], CREAM)
    double_box(d, [nx1 + 10, hy0, rx0 - 10, hy1], CREAM)
    double_box(d, [rx0, hy0, W - M, hy1], CREAM)

    d.text(((M + nx1)//2, (hy0+hy1)//2 - 2), str(no),
           font=F("serif", 64), fill=INK, anchor="mm")
    tf = fit_font(d, item["title"], "bold", (rx0 - 10) - (nx1 + 10) - 44, 42, 22)
    d.text(((nx1 + rx0)//2, (hy0+hy1)//2 - 2), item["title"],
           font=tf, fill=INK, anchor="mm")
    d.text(((rx0 + W - M)//2, (hy0+hy1)//2 - 2), rank,
           font=F("serif", 48), fill=INK, anchor="mm")

    # ── 中央插圖：米色襯邊 ──
    ay0, ay1 = 182, 646
    d.rectangle([M, ay0, W-M, ay1], fill=CREAM, outline=INK, width=4)
    pad = 16
    aw, ah = (W-M-pad) - (M+pad), (ay1-pad) - (ay0+pad)
    im.paste(load_art((aw, ah), item), (M+pad, ay0+pad))
    d.rectangle([M+pad, ay0+pad, W-M-pad, ay1-pad], outline=CREAM_D, width=2)

    # ── 說明：大理石色帶包白框 ──
    ty0, ty1 = 668, 1026
    tex = marble((W-2*M, ty1-ty0), band, seed=stable_seed(item["id"]))
    im.paste(tex, (M, ty0))
    d.rectangle([M, ty0, W-M, ty1], outline=INK, width=4)
    bd = 30
    ix0, iy0, ix1, iy1 = M+bd, ty0+bd, W-M-bd, ty1-bd
    d.rectangle([ix0, iy0, ix1, iy1], fill=(252, 250, 245), outline=INK, width=3)

    # 內文：字級自動縮到塞得下
    body = item["body"]
    for size_ in range(23, 13, -1):
        f = F("sans", size_)
        lh = int(size_ * 1.68)
        lines = wrap(d, body, f, ix1 - ix0 - 44)
        if len(lines) * lh <= (iy1 - iy0 - 40): break
    y = iy0 + max(20, ((iy1-iy0) - len(lines)*lh)//2)
    for ln in lines:
        d.text((ix0 + 22, y), ln, font=f, fill=(32, 28, 30))
        y += lh

    # 底部細節：分類、署名、站名。署名放中央並降一級字，
    # 左右兩側原本就有文字，這裡只求「看得到但不搶戲」。
    d.text((M + 10, H - 50), f"【{item['cat']}】{item['brand']}",
           font=F("sans", 17), fill=(150, 150, 158))
    d.text((W // 2, H - 47), BYLINE,
           font=F("sans", 13), fill=(126, 126, 134), anchor="ma")
    d.text((W - M - 10, H - 50), "KIDNEYGOD.NET",
           font=F("sans", 17), fill=(150, 150, 158), anchor="ra")

    im.quantize(colors=224, method=Image.FASTOCTREE).convert("RGB").save(out, optimize=True)


def main():
    data = json.load(open("knowledge_export.json", encoding="utf-8"))
    order = ["血壓管理", "血糖管理", "血脂代謝", "檢查數值",
             "用藥安全", "飲食護腎", "生活習慣", "警訊與迷思"]
    data.sort(key=lambda x: (order.index(x["cat"]), -x["price"], x["id"]))

    os.makedirs(OUT_DIR + "/thumb", exist_ok=True)
    os.makedirs(ART_DIR, exist_ok=True)
    seq, meta = {}, {}
    only = sys.argv[1] if len(sys.argv) > 1 else None
    made = 0
    for i, item in enumerate(data, 1):
        r = RANK[item["price"]]
        seq[r] = seq.get(r, 0) + 1
        rank = f"{r}-{seq[r]}"
        meta[item["id"]] = {"no": i, "rank": rank}
        if only and item["id"] != only: continue
        out = f"{OUT_DIR}/{item['id']}.png"
        make_card(item, i, rank, out)
        # 大理石紋與網點讓 PNG 很難壓，用調色盤量化把體積壓下來
        th = Image.open(out); th.thumbnail((280, 280), Image.LANCZOS)
        th.quantize(colors=96, method=Image.FASTOCTREE).save(
            f"{OUT_DIR}/thumb/{item['id']}.png", optimize=True)
        made += 1
    # 編號與等級輸出一份給網頁用，知識庫的收納格才會顯示與卡面相同的編號
    json.dump(meta, open("gi/index.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)

    ext = len([f for f in os.listdir(ART_DIR)
               if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))])
    tot = sum(os.path.getsize(f"{OUT_DIR}/{f}")
              for f in os.listdir(OUT_DIR) if f.endswith(".png"))
    print(f"完成 {made} 張｜外部插圖 {ext} 張，其餘程式繪製｜合計 {tot//1024} KB")


if __name__ == "__main__":
    main()
