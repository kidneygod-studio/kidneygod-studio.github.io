"""產生每一頁的分享預覽圖（Open Graph，1200×630）。

為什麼要做：連結貼到 Threads、Facebook、LINE 時，有沒有預覽圖決定了
別人會不會點。純文字連結在動態牆上幾乎是隱形的。

輸出到 og/，檔名規則與 build_site.py 的 og_slug 一致——網址去掉 .html、
斜線換成減號，首頁叫 index。兩邊的規則不一致就會變成破圖，所以最後
會用 build 出來的 HTML 反查一次，確認每個被引用的檔案都真的存在。

2026-09-04 起分成兩種：

  · 有大圖的長文（hero_src/<slug>.jpg）→ 用那張大圖裁成 1200×630
  · 其餘所有頁面 → 沿用商城的那張 logo（原本的全站共用版）

長文改用自己的圖，是因為分享卡片上「一張跟內容有關的照片」點閱率遠高於
一個到處都一樣的標誌。其餘頁面沒有專屬圖，維持 logo 比硬湊一張好。

裁切用中央裁：大圖的構圖規格本來就要求主體壓在中間 60%，所以 1.91:1 甚至
LINE 那種接近 1:1 的裁法都不會切到主體。來源取 hero_src/ 的原圖而不是
hero/ 的 1600×900，多一點像素裁起來比較銳利；hero_src/ 不在時自動退回 hero/。

⚠ 別改回 make_logo.py 指的那份原圖（Downloads/知識卡插圖/護腎教室.jpg）：
它雖然有 2752×1536，但字是舊的 KIDNEYGOD.STUDIO，而網站在 kidneygod.net，
拿它當預覽圖等於每一則分享都印一個不存在的網域。這裡用的是作者另外提供的
.NET 版原圖，1678×937 縮到 1200×630 是縮小，所以邊緣銳利。
"""
import pathlib
import re
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "og"

W, H = 1200, 630

LOGO = pathlib.Path(r"C:\Users\user\Downloads\kidneygod.png")   # 1678×937 白底

# logo 只放在「中央正方形」裡，不橫跨滿版。
#
# 各家社群裁法不同：Facebook／Threads 大致照 1.91:1 顯示，Twitter 用 2:1，
# LINE 與部分動態牆會裁成接近 1:1。滿版的 logo 遇到正方形裁切，左右兩端的
# 「護」和「.NET」就會被切掉。改成塞進以短邊為準的中央方形，最嚴苛的 1:1
# 裁切也還是完整的——代價是滿版顯示時周圍留白較多，但白底本來就是這張圖的
# 底色，看起來像刻意的留白而不是破圖。
SAFE = 0.92                      # 佔中央方形的比例，留一點呼吸空間

HERO_SRC = ROOT / "hero_src"     # 原圖（2752×1536），沒有的話退回壓過的 hero/
HERO_OUT = ROOT / "hero"
HERO_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def hero_file(slug: str):
    """og slug 形如 articles-<文章slug>；反查對應的大圖原檔。"""
    if not slug.startswith("articles-"):
        return None
    name = slug[len("articles-"):]
    for d in (HERO_SRC, HERO_OUT):
        for ext in HERO_EXTS:
            p = d / (name + ext)
            if p.exists():
                return p
    return None


def make_photo(path: pathlib.Path) -> Image.Image:
    """把大圖縮放後置中裁成 1200×630。"""
    im = Image.open(path)
    im = im.convert("RGB")
    scale = max(W / im.width, H / im.height)
    nw, nh = round(im.width * scale), round(im.height * scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - W) // 2, (nh - H) // 2
    return im.crop((left, top, left + W, top + H))


def make_card() -> Image.Image:
    """白底 + 置中的 logo，整體塞進中央正方形安全區。"""
    im = Image.open(LOGO)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, "white")
        flat.paste(im, mask=im.split()[-1])
        im = flat
    else:
        im = im.convert("RGB")

    box = min(W, H) * SAFE
    scale = min(box / im.width, box / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)

    # 底色取原圖角落，補出來的邊才會跟 logo 自己的底無縫接上
    card = Image.new("RGB", (W, H), im.getpixel((0, 0)))
    card.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    return card


def main():
    src = (ROOT / "build_site.py").read_text("utf-8")
    if "og_slug" not in src:
        sys.exit("build_site.py 沒有 og_slug，先套用 og:image 的修改再跑這支")

    OUT.mkdir(exist_ok=True)

    # 檔名仍取自實際 build 出來的頁面，才不會與 og:image 的引用對不上
    slugs = set()
    for p in ROOT.rglob("*.html"):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if "/gi/" in "/" + rel or rel in {"dash.html"}:
            continue
        h = p.read_text("utf-8", "replace")
        if not re.search(r"(?s)<h1[^>]*>(.*?)</h1>", h):
            continue
        slugs.add(re.sub(r"[^a-z0-9]+", "-",
                         rel.replace(".html", "").replace("/", "-")).strip("-"))

    card = make_card()
    n_photo = 0
    for slug in sorted(slugs):
        hp = hero_file(slug)
        im = make_photo(hp) if hp else card
        if hp:
            n_photo += 1
        # 用 JPEG 不用 PNG：連續色調的照片與插畫，同畫質下 JPEG 小得多。
        # 預覽圖是別人滑手機時才載入的，小一點就是多一點機會在滑過去之前顯示。
        im.save(OUT / f"{slug}.jpg", quality=88, optimize=True, progressive=True)
    print(f"產生 {len(slugs)} 張（{W}×{H}）："
          f"{n_photo} 張用長文大圖，{len(slugs) - n_photo} 張用 logo")

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
