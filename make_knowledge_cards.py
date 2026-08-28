# -*- coding: utf-8 -*-
"""把 60 篇護腎知識做成可收藏的卡片。

字型依情境配置（標題）：
  用藥安全・警訊與迷思 → 標楷體    傳統鄭重，像藥典警語與勸世文
  飲食護腎             → 新細明體  溫潤書卷氣
  生活習慣             → 正黑體細  輕盈日常
  檢查數值・三高三類    → 正黑體粗  數據導向，清晰精確
內文一律用微軟正黑體 —— 衛教文字的第一要求是好讀，襯線體與楷體在小字級
容易糊掉，這點不因美觀而妥協。

輸出 800x1120（收藏卡比例），含分類色帶、編號、資料依據與免責聲明。
"""
import os, sys, json, textwrap
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")

FONTS = {
    "kai":   r"C:\Windows\Fonts\kaiu.ttf",       # 標楷體
    "ming":  r"C:\Windows\Fonts\mingliu.ttc",    # 新細明體
    "sans":  r"C:\Windows\Fonts\msjh.ttc",       # 微軟正黑體
    "bold":  r"C:\Windows\Fonts\msjhbd.ttc",     # 微軟正黑體 粗
    "light": r"C:\Windows\Fonts\msjhl.ttc",      # 微軟正黑體 細
    "emoji": r"C:\Windows\Fonts\seguiemj.ttf",   # Segoe UI Emoji（中文字型無 emoji 字符）
}
_cache = {}
def F(key, size):
    k = (key, size)
    if k not in _cache:
        _cache[k] = ImageFont.truetype(FONTS[key], size)
    return _cache[k]

# 分類 →（主色, 淺色底, 標題字型, 情境說明）
THEME = {
    "用藥安全":  ((124, 92, 255),  (246, 242, 255), "kai",   "藥典警語"),
    "警訊與迷思": ((178, 58, 72),   (255, 243, 244), "kai",   "勸世提醒"),
    "飲食護腎":  ((46, 160, 110),  (238, 250, 244), "ming",  "食養書卷"),
    "生活習慣":  ((59, 130, 196),  (238, 246, 253), "light", "日常輕盈"),
    "檢查數值":  ((91, 110, 225),  (240, 242, 255), "bold",  "數據清晰"),
    "血壓管理":  ((214, 51, 87),   (255, 241, 244), "bold",  "臨床精確"),
    "血糖管理":  ((222, 132, 30),  (255, 247, 236), "bold",  "臨床精確"),
    "血脂代謝":  ((190, 150, 30),  (253, 249, 232), "bold",  "臨床精確"),
}
INK  = (48, 38, 36)
BODY = (74, 62, 58)
DIM  = (150, 132, 124)
W, H = 800, 1120
M = 58


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


def draw_body(d, text, x, y, maxw, size, lh, color=BODY, key="sans"):
    f = F(key, size)
    for ln in wrap(d, text, f, maxw):
        d.text((x, y), ln, font=f, fill=color)
        y += int(size * lh)
    return y


_emoji_cache = {}
def render_emoji(ch, size):
    """Segoe UI Emoji 是點陣彩色字型，只有 109px 這類內建尺寸畫得出來，
    因此固定用 109 繪製再縮到需要的大小。"""
    key = (ch, size)
    if key in _emoji_cache: return _emoji_cache[key]
    try:
        f = ImageFont.truetype(FONTS["emoji"], 109)
        tmp = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((80, 80), ch, font=f, anchor="mm", embedded_color=True)
        bb = tmp.getbbox()
        if not bb: raise ValueError("empty")
        out = tmp.crop(bb)
        out.thumbnail((size, size), Image.LANCZOS)
    except Exception:
        out = None
    _emoji_cache[key] = out
    return out


def make_card(item, idx, total, out):
    cat = item["cat"]
    main, tint, tkey, mood = THEME[cat]
    im = Image.new("RGB", (W, H), (255, 253, 250))
    d = ImageDraw.Draw(im)

    # 外框與頂部色帶
    d.rounded_rectangle([10, 10, W-10, H-10], radius=26, fill=(255, 255, 255),
                        outline=main, width=4)
    d.rounded_rectangle([10, 10, W-10, 176], radius=26, fill=main)
    d.rectangle([10, 140, W-10, 176], fill=main)

    d.text((M, 44), cat, font=F("bold", 30), fill=(255, 255, 255))
    d.text((M, 92), f"護腎教室 KidneyGod.Studio", font=F("light", 19),
           fill=(255, 255, 255, 220))
    no = f"No.{idx:02d} / {total}"
    d.text((W-M, 52), no, font=F("bold", 24), fill=(255, 255, 255), anchor="ra")
    d.text((W-M, 94), mood, font=F("light", 17), fill=(240, 234, 255), anchor="ra")

    # 圖示圓底
    cx_, cy_ = W // 2, 262
    d.ellipse([cx_-58, cy_-58, cx_+58, cy_+58], fill=tint, outline=main, width=3)
    emo = render_emoji(item["emoji"], 74)
    if emo is not None:
        im.paste(emo, (cx_ - emo.width//2, cy_ - emo.height//2), emo)
    else:
        d.text((cx_, cy_+4), item["emoji"], font=F("sans", 58), anchor="mm")

    # 標題（依情境選字型）
    y = 348
    tf = F(tkey, 42)
    tl = wrap(d, item["title"], tf, W - 2*M)
    for ln in tl:
        d.text((W//2, y), ln, font=tf, fill=INK, anchor="ma")
        y += 56
    y += 6

    # 裝飾分隔線
    d.line([W//2-90, y, W//2+90, y], fill=main, width=3)
    d.ellipse([W//2-5, y-5, W//2+5, y+5], fill=main)
    y += 30

    # 內文：先量高度，再置中於分隔線與頁尾之間
    body_top, body_bottom = y, H - 190
    bf = F("sans", 22); lh = int(22 * 1.85)
    lines = wrap(d, item["body"], bf, W - 2*M)
    block_h = len(lines) * lh
    ty = body_top + max(0, (body_bottom - body_top - block_h) // 2)
    for ln in lines:
        d.text((M, ty), ln, font=bf, fill=BODY)
        ty += lh

    # 底部：商品資訊與免責
    fy = H - 168
    d.line([M, fy, W-M, fy], fill=(236, 228, 222), width=2)
    d.rounded_rectangle([M, fy+16, M+150, fy+50], radius=10, fill=tint)
    d.text((M+75, fy+33), f"{item['price']} 腎元", font=F("bold", 19),
           fill=main, anchor="mm")
    d.text((M+168, fy+33), f"【{item['brand']}】", font=F("sans", 18),
           fill=DIM, anchor="lm")
    for j, ln in enumerate(["本卡為一般衛教參考，不能取代醫師診斷與治療建議。",
                            "腎功能異常、用藥問題請諮詢腎臟科醫師或藥師；有症狀請就醫。"]):
        d.text((M, fy+68+j*24), ln, font=F("light", 15), fill=DIM)
    d.text((W-M, H-46), "kidneygod.net", font=F("light", 15),
           fill=DIM, anchor="ra")

    im = im.quantize(colors=160, method=Image.FASTOCTREE).convert("RGB")
    im.save(out, optimize=True)


def main():
    data = json.load(open("knowledge_export.json", encoding="utf-8"))
    os.makedirs("cards/k/thumb", exist_ok=True)
    total = len(data)
    used = {}
    for i, item in enumerate(data, 1):
        out = f"cards/k/{item['id']}.png"
        make_card(item, i, total, out)
        th = Image.open(out); th.thumbnail((260, 260), Image.LANCZOS)
        th.save(f"cards/k/thumb/{item['id']}.png", optimize=True)
        used[THEME[item["cat"]][2]] = used.get(THEME[item["cat"]][2], 0) + 1

    tot = sum(os.path.getsize(f"cards/k/{d['id']}.png") for d in data)
    tht = sum(os.path.getsize(f"cards/k/thumb/{d['id']}.png") for d in data)
    print(f"完成 {total} 張知識卡｜{tot//1024} KB（平均 {tot//total//1024} KB）"
          f"／縮圖 {tht//1024} KB")
    names = {"kai":"標楷體","ming":"新細明體","sans":"正黑體","bold":"正黑體粗","light":"正黑體細"}
    print("標題字型分佈:", {names[k]: v for k, v in used.items()})


if __name__ == "__main__":
    main()
