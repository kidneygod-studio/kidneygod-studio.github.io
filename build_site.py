"""把 knowledge_export.json 的衛教內容產生成可被搜尋引擎索引的靜態網頁。

為什麼需要這支程式：
  站上 60 篇衛教內容目前全部包在 data.js 裡、還鎖在腎元購買機制後面，
  Google 讀不到任何一個字。這支程式把同樣的內容輸出成純靜態 HTML，
  不需要 JavaScript 就能閱讀，搜尋引擎才索引得到。

架構（hub and spoke）：
  articles/index.html          總覽（hub）
  articles/<分類>.html          8 個分類主題頁，每頁彙整該分類全部內容（約 1,800 字）
  articles/<文章>.html          日後擴寫的單篇長文（放 articles_src/*.md 就會自動產生）
  sitemap.xml / robots.txt     搜尋引擎入口

為什麼是分類頁而不是 60 個單篇頁：
  單篇平均只有 182 字，屬於「薄內容」，在 Google 的醫療內容標準下不會有排名。
  彙整成分類頁後每頁約 1,800 字，才有機會。等單篇擴寫到 1,500 字以上，
  再放進 articles_src/ 獨立成頁。

用法：
    python build_site.py            產生檔案
    python build_site.py --serve    產生後開本機預覽
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "articles"
SRC_MD = ROOT / "articles_src"

# 改用自訂網域時，只要改這一行（並在 repo 根目錄放 CNAME 檔）
BASE_URL = "https://kidneygod-studio.github.io"

SITE_NAME = "護腎教室"

# ---------------------------------------------------------------------------
# 作者資訊：醫療類內容（YMYL）的搜尋排名高度依賴作者專業身分（E-E-A-T）。
# 匿名的醫療網站在 Google 眼中可信度低，很難排上去。
# 發布前請確認以下內容正確且你同意公開。
# ---------------------------------------------------------------------------
AUTHOR_NAME = "吳政哲"
AUTHOR_TITLE = "腎臟科醫師"
AUTHOR_BIO = ("腎臟科專科醫師，臨床工作以慢性腎臟病與血液透析為主。"
              "在這裡整理腎臟與三高相關的衛教內容，內容依據國際指引與期刊文獻，"
              "並持續更新。")

DISCLAIMER = ("本站內容為一般健康衛教資訊，不針對任何個人提供診斷或治療建議，"
              "亦不能取代您與主治醫師的討論。若您有健康疑慮或正在服藥，"
              "請與您的醫師或藥師討論後再做決定。")

CAT_SLUG = {
    "血壓管理": "blood-pressure",
    "血糖管理": "blood-sugar",
    "血脂代謝": "lipids",
    "飲食護腎": "diet",
    "用藥安全": "medication-safety",
    "生活習慣": "lifestyle",
    "檢查數值": "lab-values",
    "警訊與迷思": "myths",
}

CAT_INTRO = {
    "血壓管理": "血壓與腎臟是雙向的關係：高血壓會傷腎，腎功能變差又會讓血壓更難控制。這一頁整理血壓與腎臟之間最常被問到的問題。",
    "血糖管理": "糖尿病是台灣洗腎最主要的原因。血糖控制得好不好，直接決定腎臟能撐多久。這一頁整理血糖與腎臟的關聯與實際做法。",
    "血脂代謝": "血脂異常對腎臟的影響常被忽略，但它同時牽動心血管與腎臟的長期風險。這一頁整理血脂與腎臟保護的重點。",
    "飲食護腎": "「腎不好要吃什麼」是最常見的問題，答案卻會隨腎功能階段而改變。這一頁整理飲食上真正有證據的原則與常見誤解。",
    "用藥安全": "很多腎損傷來自可以避免的用藥。這一頁整理常見的傷腎藥物、危險組合，以及什麼情況下該先問過醫師。",
    "生活習慣": "腎臟的保養沒有捷徑，但有幾個生活習慣的影響比多數人想的大。這一頁整理實際有幫助的部分。",
    "檢查數值": "肌酸酐、eGFR、蛋白尿——健檢報告上的腎功能數字到底代表什麼。這一頁教你看懂自己的報告。",
    "警訊與迷思": "哪些症狀該就醫、哪些流傳很廣的說法其實沒有根據。這一頁整理腎臟相關的警訊與常見迷思。",
}

TODAY = date.today().isoformat()

CSS = """
:root{--bg:#fdfcfa;--fg:#22201d;--mut:#6b645c;--line:#e6e1d8;--card:#f6f3ed;
--accent:#0f766e;--accent2:#0d5f59;--warn:#8a5a00;--maxw:720px}
@media (prefers-color-scheme:dark){:root{--bg:#16140f;--fg:#eae5dc;--mut:#a3998a;
--line:#332e26;--card:#1e1b15;--accent:#5eead4;--accent2:#2dd4bf;--warn:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:17px/1.85 -apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;
-webkit-text-size-adjust:100%}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 20px}
header.site{border-bottom:1px solid var(--line);padding:14px 0;margin-bottom:8px}
header.site .wrap{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
header.site a{color:var(--fg);text-decoration:none;font-weight:700}
header.site nav a{font-weight:400;color:var(--mut);font-size:14px}
h1{font-size:1.85rem;line-height:1.35;margin:28px 0 10px;letter-spacing:-.01em}
h2{font-size:1.28rem;line-height:1.45;margin:38px 0 10px;padding-top:6px}
h3{font-size:1.05rem;margin:26px 0 8px;color:var(--mut)}
p{margin:0 0 18px}
a{color:var(--accent)}
.lede{font-size:1.06rem;color:var(--mut);margin-bottom:26px}
.meta{font-size:13.5px;color:var(--mut);margin:0 0 26px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.toc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:26px 0}
.toc h2{font-size:14px;margin:0 0 8px;color:var(--mut);text-transform:none}
.toc ol{margin:0;padding-left:20px}
.toc li{margin:5px 0;font-size:15px}
article.card{border-top:1px solid var(--line);padding-top:6px}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin:26px 0}
.cats a{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;text-decoration:none;color:var(--fg)}
.cats a:hover{border-color:var(--accent)}
.cats .t{font-weight:700;margin-bottom:4px}
.cats .d{font-size:13.5px;color:var(--mut);line-height:1.6}
.author{display:flex;gap:14px;background:var(--card);border:1px solid var(--line);
border-radius:12px;padding:16px 18px;margin:40px 0 20px;font-size:14.5px;line-height:1.7}
.author .n{font-weight:700}
.author .r{color:var(--mut);font-size:13px}
.disclaimer{font-size:13.5px;color:var(--mut);background:var(--card);border-left:3px solid var(--warn);
padding:14px 16px;border-radius:0 8px 8px 0;margin:26px 0}
footer.site{border-top:1px solid var(--line);margin-top:50px;padding:24px 0 60px;
font-size:13.5px;color:var(--mut)}
footer.site a{color:var(--mut)}
.backlink{margin:34px 0}
"""


def slugify(s: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "-", s.strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def page(title: str, desc: str, path: str, body: str, jsonld: dict | None = None,
         extra_head: str = "") -> str:
    """所有頁面共用的骨架。canonical 與 OG 是搜尋引擎與分享預覽的基本要求。"""
    url = f"{BASE_URL}/{path}"
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>{CSS}</style>{extra_head}
{ld}
</head>
<body>
<header class="site"><div class="wrap">
<a href="/articles/">{SITE_NAME}｜衛教文章</a>
<nav><a href="/">回護腎教室主站</a></nav>
</div></header>
<main class="wrap">
{body}
<div class="author">
  <div>
    <div class="n">{esc(AUTHOR_NAME)}　<span class="r">{esc(AUTHOR_TITLE)}</span></div>
    <div>{esc(AUTHOR_BIO)}</div>
  </div>
</div>
<div class="disclaimer">{esc(DISCLAIMER)}</div>
</main>
<footer class="site"><div class="wrap">
<p>{SITE_NAME}　·　最後更新 {TODAY}　·　<a href="/articles/">全部文章</a>　·　<a href="/">主站</a></p>
</div></footer>
</body>
</html>
"""


def build_category(cat: str, items: list[dict]) -> tuple[str, str, str]:
    slug = CAT_SLUG[cat]
    path = f"articles/{slug}.html"
    title = f"{cat}與腎臟健康：{len(items)} 個重點整理｜{SITE_NAME}"
    intro = CAT_INTRO.get(cat, "")
    # description 同時要有足夠長度與關鍵字覆蓋，所以用「簡介＋前三篇標題」組成。
    # 中文搜尋結果約顯示 80 字，超過會被截斷，因此上限抓 150 字。
    heads = "、".join(it["title"] for it in items[:3])
    desc = f"{intro}內容包含：{heads} 等 {len(items)} 個主題。"
    desc = desc.replace("\n", " ")[:150]

    toc = "".join(
        f'<li><a href="#{slugify(it["id"])}">{esc(it["title"])}</a></li>' for it in items)
    secs = []
    for it in items:
        secs.append(
            f'<article class="card">'
            f'<h2 id="{slugify(it["id"])}">{esc(it["title"])}</h2>'
            f'<p>{esc(it["body"])}</p>'
            f'</article>')

    others = "".join(
        f'<a href="/articles/{CAT_SLUG[c]}.html"><div class="t">{esc(c)}</div>'
        f'<div class="d">{esc(CAT_INTRO.get(c, "")[:46])}…</div></a>'
        for c in CAT_SLUG if c != cat)

    body = f"""
<h1>{esc(cat)}與腎臟健康</h1>
<p class="lede">{esc(intro)}</p>
<p class="meta">作者：{esc(AUTHOR_NAME)}（{esc(AUTHOR_TITLE)}）　·　更新於 {TODAY}　·　共 {len(items)} 則</p>
<div class="toc"><h2>本頁內容</h2><ol>{toc}</ol></div>
{''.join(secs)}
<h2 class="backlink">其他主題</h2>
<div class="cats">{others}</div>
"""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "headline": f"{cat}與腎臟健康",
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/{path}",
        "dateModified": TODAY,
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "about": {"@type": "MedicalCondition", "name": "慢性腎臟病"},
        "audience": {"@type": "PeopleAudience", "geographicArea": {"@type": "Country", "name": "台灣"}},
    }
    return path, page(title, desc, path, body, jsonld), title


def build_index(by_cat: dict[str, list[dict]], extra_pages: list[tuple[str, str]]) -> tuple[str, str]:
    path = "articles/index.html"
    title = f"腎臟與三高衛教文章總覽｜{SITE_NAME}"
    desc = ("腎臟科醫師整理的慢性腎臟病與三高衛教文章：血壓、血糖、血脂、飲食、用藥安全、"
            "檢查數值判讀與常見迷思，依據國際指引，持續更新。")
    cards = "".join(
        f'<a href="/articles/{CAT_SLUG[c]}.html">'
        f'<div class="t">{esc(c)}（{len(v)} 則）</div>'
        f'<div class="d">{esc(CAT_INTRO.get(c, "")[:52])}…</div></a>'
        for c, v in by_cat.items())
    extra = ""
    if extra_pages:
        li = "".join(f'<li><a href="/{p}">{esc(t)}</a></li>' for p, t in extra_pages)
        extra = f"<h2>深入文章</h2><div class='toc'><ol>{li}</ol></div>"

    body = f"""
<h1>腎臟與三高衛教文章</h1>
<p class="lede">這裡整理慢性腎臟病、高血壓、糖尿病與高血脂相關的衛教內容，
依據國際指引與期刊文獻撰寫，目的是讓一般人也能看懂自己的身體與檢查報告。</p>
<div class="cats">{cards}</div>
{extra}
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/{path}",
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE},
    }
    return path, page(title, desc, path, body, jsonld)


def build_markdown_articles() -> list[tuple[str, str, str]]:
    """articles_src/*.md 會各自產生一頁長文。
    格式：第一行 `# 標題`，第二行起 `> 一句話摘要`（用於 meta description），其後為內文。"""
    out = []
    if not SRC_MD.exists():
        return out
    for md in sorted(SRC_MD.glob("*.md")):
        text = md.read_text(encoding="utf-8").strip()
        lines = text.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else md.stem
        summary = ""
        rest = lines[1:]
        if rest and rest[0].startswith(">"):
            summary = rest[0].lstrip("> ").strip()
            rest = rest[1:]
        paras, buf = [], []
        for ln in rest:
            if ln.startswith("## "):
                if buf:
                    paras.append("<p>" + esc("\n".join(buf).strip()) + "</p>")
                    buf = []
                paras.append(f'<h2 id="{slugify(ln[3:])}">{esc(ln[3:].strip())}</h2>')
            elif ln.strip():
                buf.append(ln.strip())
            else:
                if buf:
                    paras.append("<p>" + esc(" ".join(buf)) + "</p>")
                    buf = []
        if buf:
            paras.append("<p>" + esc(" ".join(buf)) + "</p>")

        path = f"articles/{md.stem}.html"
        desc = summary or title
        body = (f"<h1>{esc(title)}</h1>"
                f"<p class='lede'>{esc(summary)}</p>" if summary else f"<h1>{esc(title)}</h1>")
        body += (f"<p class='meta'>作者：{esc(AUTHOR_NAME)}（{esc(AUTHOR_TITLE)}）"
                 f"　·　更新於 {TODAY}</p>" + "".join(paras))
        jsonld = {
            "@context": "https://schema.org", "@type": "MedicalWebPage",
            "headline": title, "description": desc, "inLanguage": "zh-Hant",
            "url": f"{BASE_URL}/{path}", "dateModified": TODAY,
            "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE},
        }
        out.append((path, page(f"{title}｜{SITE_NAME}", desc, path, body, jsonld), title))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    args = ap.parse_args()

    data = json.loads((ROOT / "knowledge_export.json").read_text(encoding="utf-8"))
    by_cat: dict[str, list[dict]] = {}
    for it in data:
        by_cat.setdefault(it["cat"], []).append(it)
    by_cat = {c: by_cat[c] for c in CAT_SLUG if c in by_cat}

    OUT.mkdir(exist_ok=True)
    written: list[str] = []

    for cat, items in by_cat.items():
        path, htm, _t = build_category(cat, items)
        (ROOT / path).write_text(htm, encoding="utf-8")
        written.append(path)
        print(f"  {path}　({len(items)} 則，約 {sum(len(i['body']) for i in items):,} 字)")

    md_pages = build_markdown_articles()
    for path, htm, _t in md_pages:
        (ROOT / path).write_text(htm, encoding="utf-8")
        written.append(path)
        print(f"  {path}　(擴寫長文)")

    idx_path, idx_html = build_index(by_cat, [(p, t) for p, _h, t in md_pages])
    (ROOT / idx_path).write_text(idx_html, encoding="utf-8")
    written.insert(0, idx_path)
    print(f"  {idx_path}")

    # sitemap：讓搜尋引擎一次拿到所有網址
    urls = ["", "articles/"] + [p for p in written if not p.endswith("index.html")]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemap.org/schemas/sitemap/0.9">'.replace(
              "www.sitemap.org", "www.sitemaps.org")]
    for u in dict.fromkeys(urls):
        pri = "1.0" if u == "" else ("0.9" if u == "articles/" else "0.8")
        sm.append(f"  <url><loc>{BASE_URL}/{u}</loc><lastmod>{TODAY}</lastmod>"
                  f"<changefreq>monthly</changefreq><priority>{pri}</priority></url>")
    sm.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    print(f"  sitemap.xml　({len(urls)} 個網址)")

    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")
    print("  robots.txt")

    total = sum(len(i["body"]) for i in data)
    print(f"\n完成：{len(written)} 頁，內容共 {total:,} 字")
    print(f"預覽： {ROOT / 'articles' / 'index.html'}")

    if args.serve:
        import http.server
        import socketserver
        import webbrowser
        import os
        os.chdir(ROOT)
        with socketserver.TCPServer(("", 8902), http.server.SimpleHTTPRequestHandler) as httpd:
            print("預覽伺服器 http://localhost:8902/articles/ （Ctrl+C 結束）")
            webbrowser.open("http://localhost:8902/articles/")
            httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
