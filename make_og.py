"""產生每一頁的分享預覽圖（Open Graph，1200×630）。

為什麼要做：連結貼到 Threads、Facebook、LINE 時，有沒有預覽圖決定了
別人會不會點。純文字連結在動態牆上幾乎是隱形的。

輸出到 og/，檔名規則與 build_site.py 的 og_slug 一致——網址去掉 .html、
斜線換成減號，首頁叫 index。兩邊的規則不一致就會變成破圖，所以最後
會用 build 出來的 HTML 反查一次，確認每個被引用的檔案都真的存在。

設計上刻意不放整張卡片圖：卡片是 900×1080 直式，硬塞進橫式會變形。
改成右側裁切出一條直幅，左側留給標題——社群動態牆上字要夠大才讀得到。
"""
import pathlib
import re
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "og"
CARDS = ROOT / "cards" / "gi"

W, H = 1200, 630
PAD = 64
ART_W = 430                      # 右側圖片寬度

# 衛教站的色票，與 build_site.py 的 :root 一致
BG = "#fdfcfa"
FG = "#22201d"
MUT = "#6b645c"
LINE = "#e6e1d8"
ACCENT = "#0f766e"
CARDBG = "#f6f3ed"               # 右側面板底色，與站上 --card 同一個值

FONT_BD = "C:/Windows/Fonts/msjhbd.ttc"     # 微軟正黑體 Bold
FONT_RG = "C:/Windows/Fonts/msjh.ttc"

# 每頁配一張主題相符的卡片圖。挑的原則是「一眼看得出這篇在講什麼」，
# 不是好不好看——預覽圖在動態牆上只有半秒的時間說明自己是什麼。
ART = {
    "index":                        "egfr",
    "about":                        None,          # 用醫師本人照片
    "calc":                         "egfr",
    "food":                         "eatout",
    "articles-index":               "five-signs",
    "articles-gallery":             "bp-howto",
    "articles-blood-pressure":      "bp",
    "articles-blood-sugar":         "dm-a1c",
    "articles-diet":                "salt",
    "articles-lab-values":          "bun",
    "articles-lifestyle":           "exercise",
    "articles-lipids":              "lp-ldl",
    "articles-medication-safety":   "nsaid",
    "articles-myths":               "detox",
    "articles-creatinine-high-what-to-do":  "bun",
    "articles-egfr-meaning-ckd-stages":     "egfr",
    "articles-foamy-urine-proteinuria":     "proteinuria",
    "articles-taiwan-eating-out-sodium":    "eatout",
    "articles-gallery-kidney":      "water",
    "articles-gallery-kidney-pro":  "dialysis-myth",
    "articles-gallery-metabolic":   "ms-cluster",
    "articles-gallery-metabolic-pro": "ms-kidney",
    "articles-gallery-companion":   "sleep",
    # 商城側三頁是手寫的，不走 build_site.py，但一樣需要像樣的預覽圖：
    # 原本掛的 logo.png 只有 684×370，比社群要求的 1200×630 小，會被放大糊掉。
    "shop":                         "five-signs",
    "game":                         "exercise",
    "library":                      "water",
}

EYEBROW = "護腎教室　·　kidneygod.net"
BYLINE = "腎臟科專科醫師　吳政哲"


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, f, maxw):
    """中文逐字斷行。中文沒有空格，用英文的斷詞邏輯會整段不換行。"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=f) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def art_strip(name):
    """右側面板：整張卡片縮進去，不裁切。

    一開始是裁成滿版直幅，但卡片本身有標題列與頁尾字，裁完邊緣會出現
    半個字，看起來像出錯而不像設計。寧可留白邊也要讓卡片完整。
    """
    src = CARDS / f"{name}.png" if name else ROOT / "doctor.jpg"
    if not src.exists():
        return None

    panel = Image.new("RGB", (ART_W, H), CARDBG)
    inner_w, inner_h = ART_W - 44, H - 44
    im = Image.open(src).convert("RGB")
    scale = min(inner_w / im.width, inner_h / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    panel.paste(im, ((ART_W - im.width) // 2, (H - im.height) // 2))
    return panel


def build(slug, title, art_name):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    strip = art_strip(art_name)
    if strip:
        img.paste(strip, (W - ART_W, 0))
        # 圖與底色之間拉一條細線，避免兩塊淺色糊在一起
        d.line([(W - ART_W, 0), (W - ART_W, H)], fill=LINE, width=2)

    text_w = W - ART_W - PAD * 2

    # 頂部的品牌色錨點，與網站上 h2 前面那條短線是同一個語彙
    d.rectangle([PAD, PAD, PAD + 52, PAD + 6], fill=ACCENT)

    y = PAD + 30
    f_eye = font(FONT_RG, 25)
    d.text((PAD, y), EYEBROW, font=f_eye, fill=MUT)
    y += 54

    # 標題字級依長度調整：短標題放大，長標題縮小，都要能塞進版面
    for size in (60, 54, 48, 43, 38):
        f_title = font(FONT_BD, size)
        lines = wrap(d, title, f_title, text_w)
        if len(lines) * (size + 14) <= 330:
            break
    for ln in lines:
        d.text((PAD, y), ln, font=f_title, fill=FG)
        y += size + 14

    # 署名固定貼在底部，不隨標題長度浮動
    f_by = font(FONT_RG, 27)
    by_y = H - PAD - 34
    d.line([(PAD, by_y - 24), (PAD + text_w, by_y - 24)], fill=LINE, width=2)
    d.text((PAD, by_y), BYLINE, font=f_by, fill=ACCENT)
    return img


def main():
    src = (ROOT / "build_site.py").read_text("utf-8")
    if "og_slug" not in src:
        sys.exit("build_site.py 沒有 og_slug，先套用 og:image 的修改再跑這支")

    OUT.mkdir(exist_ok=True)

    # 標題取自實際 build 出來的 H1，不另外維護一份，避免兩邊對不上
    titles = {}
    for p in ROOT.rglob("*.html"):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if "/gi/" in "/" + rel or rel in {"dash.html"}:
            continue
        h = p.read_text("utf-8", "replace")
        m = re.search(r"(?s)<h1[^>]*>(.*?)</h1>", h)
        if not m:
            continue
        # 與 build_site.py 的 og_slug 逐字相同的規則。首頁在那邊的 path 是
        # 空字串，這裡是 index.html，兩邊都會得到 index。
        slug = re.sub(r"[^a-z0-9]+", "-",
                      rel.replace(".html", "").replace("/", "-")).strip("-")
        t = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", "", m.group(1))).strip()
        titles[slug] = t

    made = 0
    for slug, title in sorted(titles.items()):
        if slug not in ART:
            print(f"  ！ {slug} 沒有指定配圖，用預設")
        img = build(slug, title, ART.get(slug, "egfr"))
        # 用 JPEG 不用 PNG：卡片圖是連續色調的插畫，PNG 存成一張要 230 KB，
        # 同樣畫質的 JPEG 只要五分之一。預覽圖是別人滑手機時才載入的，
        # 檔案小一點就是多一點機會在他滑過去之前顯示出來。
        img.save(OUT / f"{slug}.jpg", quality=88, optimize=True, progressive=True)
        made += 1
        print(f"  {slug}.jpg　{title[:26]}")

    print(f"\n產生 {made} 張")

    # 反查：HTML 引用的每一張 og:image 都要真的存在
    missing = []
    for p in ROOT.rglob("*.html"):
        h = p.read_text("utf-8", "replace")
        for m in re.finditer(r'property="og:image" content="[^"]*/og/([^"]+)"', h):
            # 檔名規則兩邊各寫一次就會有對不上的一天，所以這裡實際去檔案系統確認
            if not (OUT / m.group(1)).exists():
                missing.append((str(p.relative_to(ROOT)), m.group(1)))
    print("破圖檢查：" + ("全部存在" if not missing else f"缺 {missing}"))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
