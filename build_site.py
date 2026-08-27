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
AUTHOR_BIO = ("腎臟科專科醫師，臨床工作以三高、慢性腎臟病與血液透析／腹膜透析為主。"
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
ul{padding-left:22px;margin:0 0 18px}
li{margin:7px 0}
strong{font-weight:700}
code{background:var(--card);padding:1px 6px;border-radius:5px;font-size:.92em}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:22px 0}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:var(--card);font-weight:600;font-size:13.5px;color:var(--mut)}
tr:last-child td{border-bottom:0}
.callout{background:var(--card);border-left:3px solid var(--accent);
padding:14px 18px;border-radius:0 10px 10px 0;margin:22px 0;font-size:16px}

/* ── 醫師介紹（關於頁最上方）── */
.docintro{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);
gap:34px;align-items:center;margin:26px 0 40px}
.docintro.nophoto{grid-template-columns:1fr}
/* 原圖是全身直式，直接放會比旁邊的資歷欄高出一截。
   裁成 3:4 並把構圖重心往上移，取到頭部與上半身，和資歷欄的高度才平衡。
   想改成完整全身，把 aspect-ratio 與 object-fit 兩行拿掉即可。 */
/* height:auto 不可省略——HTML 上的 height 屬性（用來避免版面跳動）
   會被當成呈現提示而固定高度，那樣 aspect-ratio 就不會生效。 */
.docphoto{width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;
object-position:center 12%;
border-radius:14px;display:block;box-shadow:0 10px 30px rgba(0,0,0,.16)}
.docname{font-size:1.9rem;font-weight:800;letter-spacing:.5px;margin:0 0 18px;
color:var(--accent2)}
.docname small{display:block;font-size:.95rem;font-weight:600;color:var(--mut);
letter-spacing:0;margin-bottom:4px}
.doccred{list-style:none;padding:0;margin:0}
.doccred li{display:flex;align-items:flex-start;gap:11px;margin:0 0 13px;
font-size:1.02rem;line-height:1.55}
.doccred svg{flex-shrink:0;margin-top:2px}
.doccred li.key{font-weight:700}
@media(max-width:720px){
  .docintro{grid-template-columns:1fr;gap:22px;margin-bottom:32px}
  .docphoto{max-width:250px;margin:0 auto}
  .docname{font-size:1.55rem;text-align:center}
  .doccred li{font-size:.98rem}
}

/* ── 首頁 ── */
.hero{padding:34px 0 8px}
.hero h1{font-size:2.1rem;margin:0 0 12px}
.hero .sub{font-size:1.08rem;color:var(--mut);margin-bottom:6px}
.hero .cred{font-size:14px;color:var(--mut)}
.sect{font-size:1.15rem;margin:44px 0 4px}
.sect + .sd{font-size:14px;color:var(--mut);margin-bottom:16px}
.feat{display:block;border:1px solid var(--line);border-radius:12px;padding:18px 20px;
text-decoration:none;color:var(--fg);background:var(--card);margin-bottom:12px}
.feat:hover{border-color:var(--accent)}
.feat .t{font-weight:700;font-size:1.05rem;margin-bottom:5px;line-height:1.5}
.feat .d{font-size:14px;color:var(--mut);line-height:1.65}

/* 商城入口：刻意沿用商城本身的深色＋金框風格，在淺色頁面上形成強烈對比，
   讓它成為整個首頁最醒目的元素。
   版面以標誌為主體、文字只作為說明它的圖說，所以是置中直排、不放按鈕與箭頭。 */
.gamebtn{display:flex;flex-direction:column;align-items:center;text-align:center;
gap:18px;text-decoration:none;
background:linear-gradient(120deg,#33281f,#1e1814);color:#e8c65a;
border:3px solid #c9a227;border-radius:18px;padding:32px 26px;margin:26px 0 10px;
box-shadow:inset 0 1px 0 rgba(255,236,200,.14),0 14px 34px rgba(0,0,0,.32);
position:relative;overflow:hidden;transition:transform .18s,box-shadow .18s}
.gamebtn:hover{transform:translateY(-4px);box-shadow:0 18px 42px rgba(201,162,39,.34)}
.gamebtn::after{content:"";position:absolute;top:0;left:-60%;width:40%;height:100%;
background:linear-gradient(100deg,transparent,rgba(255,240,200,.16),transparent);
animation:sheen 4.5s ease-in-out infinite}
@keyframes sheen{0%,72%{left:-60%}100%{left:130%}}
@media(prefers-reduced-motion:reduce){.gamebtn::after{animation:none}}
/* 商城的招牌是 480x257 的橫幅標誌，不能鎖成正方形，否則會被壓扁。
   固定高度、寬度自動，比例才會正確。 */
.gamebtn img{height:136px;width:auto;max-width:100%;
filter:drop-shadow(0 3px 10px rgba(0,0,0,.5))}
.gamebtn .cap{font-size:1.16rem;font-weight:800;color:#e8c65a;
letter-spacing:.4px;line-height:1.5}
@media(max-width:560px){
  .hero h1{font-size:1.68rem}
  .gamebtn{gap:14px;padding:26px 20px}
  .gamebtn img{height:96px}
  .gamebtn .cap{font-size:1.06rem}
}
"""


def slugify(s: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "-", s.strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def page(title: str, desc: str, path: str, body: str, jsonld: dict | None = None,
         extra_head: str = "", home: bool = False) -> str:
    """所有頁面共用的骨架。canonical 與 OG 是搜尋引擎與分享預覽的基本要求。"""
    url = f"{BASE_URL}/{path}"
    nav = ('<a href="/articles/">全部文章</a>' if home
           else '<a href="/">回首頁</a>')
    nav += '　·　<a href="/about.html">關於作者</a>'
    brand = ("護腎教室" if home else f"{SITE_NAME}｜衛教文章")
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
<a href="/">{brand}</a>
<nav>{nav}　·　<a href="/shop.html">知識商城</a></nav>
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


def build_category(cat: str, items: list[dict],
                   articles: list[dict] | None = None) -> tuple[str, str, str]:
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

    # 內部連結：把屬於這個分類的長文列在最前面。
    # 分類頁流量較大，是把權重導向深度文章最自然的位置。
    deep = [a for a in (articles or []) if a.get("cat") == cat]
    deep_html = ""
    if deep:
        li = "".join(
            f'<a class="feat" href="/{a["path"]}"><div class="t">{esc(a["title"])}</div>'
            f'<div class="d">{esc(a["summary"][:88])}…</div></a>' for a in deep)
        deep_html = (f'<h2 class="backlink">深入閱讀</h2>'
                     f'<div class="sd">這個主題的完整長文</div>{li}')

    body = f"""
<h1>{esc(cat)}與腎臟健康</h1>
<p class="lede">{esc(intro)}</p>
<p class="meta">作者：<a href="/about.html">{esc(AUTHOR_NAME)}</a>（{esc(AUTHOR_TITLE)}）　·　更新於 {TODAY}　·　共 {len(items)} 則</p>
{deep_html}
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


def inline(s: str) -> str:
    """行內語法：**粗體**、`程式碼`、[文字](網址)。先跳脫再還原標記，避免注入。"""
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def md_to_html(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Markdown 區塊轉 HTML，同時回傳 h2 清單供產生目錄。

    中文段落內的換行直接接合、不補空格——否則中文字之間會出現空隙。
    支援：## / ### 標題、- 清單、| 表格、> 提示框，以及行內粗體與連結。
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    out: list[str] = []
    heads: list[tuple[str, str]] = []

    for b in blocks:
        lines = [ln.rstrip() for ln in b.split("\n") if ln.strip()]
        if not lines:
            continue
        first = lines[0]

        if first.startswith("### "):
            out.append(f"<h3>{inline(first[4:].strip())}</h3>")
            if lines[1:]:
                out.append("<p>" + inline("".join(lines[1:])) + "</p>")
        elif first.startswith("## "):
            t = first[3:].strip()
            hid = slugify(t)
            heads.append((hid, t))
            out.append(f'<h2 id="{hid}">{inline(t)}</h2>')
            if lines[1:]:
                out.append("<p>" + inline("".join(lines[1:])) + "</p>")
        elif all(ln.startswith("- ") for ln in lines):
            items = "".join(f"<li>{inline(ln[2:].strip())}</li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        elif first.startswith("|") and len(lines) >= 2:
            rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines
                    if not re.fullmatch(r"\|[\s:|-]+\|", ln.strip())]
            if rows:
                th = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
                td = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                             for r in rows[1:])
                out.append(f'<div class="tw"><table><thead><tr>{th}</tr></thead>'
                           f"<tbody>{td}</tbody></table></div>")
        elif first.startswith("> "):
            body = "".join(ln.lstrip("> ").strip() for ln in lines)
            out.append(f'<div class="callout">{inline(body)}</div>')
        else:
            out.append("<p>" + inline("".join(lines)) + "</p>")

    return out, heads


PUB_DATES = SRC_MD / "published.json"


def load_pub_dates() -> dict[str, str]:
    """記住每篇文章第一次發布的日期。
    Google 會同時看 datePublished 與 dateModified；若只有後者，
    每次重新產生都會讓文章看起來像新寫的，反而不利於累積權重。"""
    if PUB_DATES.exists():
        try:
            return json.loads(PUB_DATES.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def extract_faq(text: str) -> list[tuple[str, str]]:
    """從「常見問題／常見誤解」段落抽出問答配對，用來產生 FAQPage 結構化資料。

    Google 會把 FAQPage 呈現成可展開的問答區塊，版位在一般搜尋結果之上。
    慣例：`## 常見問題`（或含「常見誤解」）底下，每個 `### 問句` 加緊接的段落。
    """
    m = re.search(r"^##\s+(.*(?:常見問題|常見誤解).*)$", text, re.M)
    if not m:
        return []
    section = text[m.end():]
    nxt = re.search(r"^##\s+", section, re.M)
    if nxt:
        section = section[:nxt.start()]

    faqs = []
    parts = re.split(r"^###\s+", section, flags=re.M)[1:]
    for p in parts:
        lines = [ln.strip() for ln in p.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        q = lines[0].strip("「」？?。 ")
        a = "".join(lines[1:])
        a = re.sub(r"\*\*([^*]+)\*\*", r"\1", a)
        faqs.append((lines[0].strip(), a))
    return faqs


def parse_article(md: Path) -> dict:
    """解析一篇 Markdown 長文。
    格式：`# 標題` / `> 一句話摘要` / `分類：檢查數值`（可省略）/ 內文。"""
    text = md.read_text(encoding="utf-8").strip()
    lines = text.split("\n")
    title = lines[0].lstrip("# ").strip() if lines else md.stem
    rest = lines[1:]

    summary, cat = "", ""
    while rest and not rest[0].strip():
        rest.pop(0)
    if rest and rest[0].startswith(">"):
        summary = rest.pop(0).lstrip("> ").strip()
    while rest and not rest[0].strip():
        rest.pop(0)
    if rest and re.match(r"^(分類|cat)\s*[:：]", rest[0]):
        cat = re.split(r"[:：]", rest.pop(0), maxsplit=1)[1].strip()

    return {"slug": md.stem, "title": title, "summary": summary,
            "cat": cat if cat in CAT_SLUG else "",
            "body": "\n".join(rest), "raw": text}


def build_markdown_articles() -> list[dict]:
    """articles_src/*.md 各自產生一頁長文。回傳每篇的中繼資料供互連與首頁使用。"""
    out: list[dict] = []
    if not SRC_MD.exists():
        return out

    pub = load_pub_dates()
    changed = False

    for md in sorted(SRC_MD.glob("*.md")):
        # 檔名以底線開頭 = 草稿，不產生頁面也不進 sitemap。
        # 醫學內容掛作者姓名發布前必須先經本人審核，審完把底線拿掉即可上線。
        if md.name.startswith("_"):
            print(f"  （草稿，未發布）{md.name}")
            continue

        a = parse_article(md)
        paras, heads = md_to_html(a["body"])
        toc = ""
        if len(heads) >= 3:
            li = "".join(f'<li><a href="#{h}">{esc(t)}</a></li>' for h, t in heads)
            toc = f'<div class="toc"><h2>本頁內容</h2><ol>{li}</ol></div>'

        path = f"articles/{a['slug']}.html"
        desc = (a["summary"] or a["title"])[:150]

        if a["slug"] not in pub:
            pub[a["slug"]] = TODAY
            changed = True
        published = pub[a["slug"]]

        datestr = (f"發布於 {published}" if published == TODAY
                   else f"發布於 {published}　·　更新於 {TODAY}")

        # 內部連結：把文章接回它所屬的分類頁，讓搜尋引擎看得出主題歸屬
        related = ""
        if a["cat"]:
            related = (f'<h2 class="backlink">延伸閱讀</h2>'
                       f'<div class="cats">'
                       f'<a href="/articles/{CAT_SLUG[a["cat"]]}.html">'
                       f'<div class="t">{esc(a["cat"])}：完整整理</div>'
                       f'<div class="d">{esc(CAT_INTRO.get(a["cat"], "")[:46])}…</div></a>'
                       f'<a href="/articles/"><div class="t">全部衛教主題</div>'
                       f'<div class="d">血壓、血糖、血脂、飲食、用藥安全…</div></a>'
                       f"</div>")

        body = f"<h1>{esc(a['title'])}</h1>"
        if a["summary"]:
            body += f"<p class='lede'>{esc(a['summary'])}</p>"
        body += (f"<p class='meta'>作者：<a href='/about.html'>{esc(AUTHOR_NAME)}</a>"
                 f"（{esc(AUTHOR_TITLE)}）　·　{datestr}</p>{toc}"
                 + "".join(paras) + related)

        jsonld = {
            "@context": "https://schema.org", "@type": "MedicalWebPage",
            "headline": a["title"], "description": desc, "inLanguage": "zh-Hant",
            "url": f"{BASE_URL}/{path}",
            "datePublished": published, "dateModified": TODAY,
            "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE,
                       "url": f"{BASE_URL}/about.html"},
            "publisher": {"@type": "Organization", "name": SITE_NAME},
            "about": {"@type": "MedicalCondition", "name": "慢性腎臟病"},
        }

        faqs = extract_faq(a["raw"])
        extra_ld = ""
        if faqs:
            faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": ans}}
                                     for q, ans in faqs]}
            extra_ld = ('<script type="application/ld+json">'
                        + json.dumps(faq_ld, ensure_ascii=False) + "</script>")

        a["path"] = path
        a["html"] = page(f"{a['title']}｜{SITE_NAME}", desc, path, body, jsonld,
                         extra_head=extra_ld)
        a["faq_count"] = len(faqs)
        out.append(a)

    if changed:
        PUB_DATES.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def build_home(by_cat: dict[str, list[dict]], extra: list[tuple[str, str, str]]) -> str:
    """網站首頁：以衛教內容為主，商城與遊戲收在一個明顯的大按鈕後面。"""
    title = f"護腎教室｜腎臟與三高衛教．{AUTHOR_NAME}{AUTHOR_TITLE}"
    desc = ("腎臟科醫師撰寫的慢性腎臟病與三高衛教：看懂 eGFR 與腎功能報告、"
            "血壓血糖血脂如何影響腎臟、傷腎藥物與飲食原則。依據國際指引，持續更新。")

    cards = "".join(
        f'<a href="/articles/{CAT_SLUG[c]}.html">'
        f'<div class="t">{esc(c)}（{len(v)} 則）</div>'
        f'<div class="d">{esc(CAT_INTRO.get(c, "")[:50])}…</div></a>'
        for c, v in by_cat.items())

    feats = "".join(
        f'<a class="feat" href="/{a["path"]}"><div class="t">{esc(a["title"])}</div>'
        f'<div class="d">{esc(a["summary"][:88])}…</div></a>' for a in extra)

    feat_sect = (f'<h2 class="sect">深入文章</h2>'
                 f'<div class="sd">完整長文，適合想把一個主題徹底搞懂的人</div>{feats}'
                 if feats else "")

    body = f"""
<div class="hero">
<h1>護腎專家－{esc(AUTHOR_NAME)}醫師的護腎教室</h1>
<p class="sub">把腎臟的事，講到你聽得懂。慢性腎臟病、高血壓、糖尿病、高血脂——
這裡用一般人看得懂的方式，說明檢查數字代表什麼、哪些習慣真的有影響、哪些說法沒有根據。</p>
<p class="cred">內容依據國際指引與期刊文獻撰寫，持續更新。
<a href="/about.html">關於{esc(AUTHOR_NAME)}醫師 →</a></p>
</div>

<a class="gamebtn" href="/shop.html">
  <img src="/logo.png" alt="" aria-hidden="true" width="480" height="257">
  <span class="cap">護腎知識卡片收集商城</span>
</a>

<h2 class="sect">依主題閱讀</h2>
<div class="sd">{sum(len(v) for v in by_cat.values())} 則衛教內容，分成 {len(by_cat)} 個主題</div>
<div class="cats">{cards}</div>

{feat_sect}
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/",
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE},
    }
    return page(title, desc, "", body, jsonld, home=True)


# 醫師介紹要條列的資歷。第一項是最強的權威訊號，刻意排在最前面。
CREDENTIALS = [
    ("台灣慢性腎臟病臨床診療指引編撰委員", True),
    ("國立成功大學醫學系畢業", False),
    ("前成大醫院主治醫師", False),
    ("郭綜合醫院腎臟內科主治醫師", True),
    ("腎臟科專科醫師", True),
    ("內科專科醫師", False),
    ("台灣腎臟醫學會會員", False),
    ("美國腎臟醫學會會員", False),
    ("戒菸醫師", False),
    ("糖尿病共照網醫師", False),
]

CHECK_SVG = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
             '<circle cx="12" cy="12" r="11" fill="currentColor" opacity=".16"/>'
             '<path d="M7 12.4l3.2 3.2L17 8.8" stroke="currentColor" stroke-width="2.4" '
             'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def img_size(p: Path) -> tuple[int, int] | None:
    """讀出 PNG/JPEG 的原始尺寸，寫進 width/height 屬性避免圖片載入時版面跳動。"""
    try:
        b = p.read_bytes()
    except OSError:
        return None
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        import struct
        w, h = struct.unpack(">II", b[16:24])
        return w, h
    if b[:2] == b"\xff\xd8":
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(b[i + 5:i + 7], "big")
                w = int.from_bytes(b[i + 7:i + 9], "big")
                return w, h
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    return None


def find_doctor_photo() -> tuple[str, int, int] | None:
    """找醫師照片。放進 repo 根目錄命名為 doctor.jpg／doctor.png 即會自動採用；
    沒有檔案時醫師介紹會退成純資歷條列，頁面不會壞掉。"""
    for name in ("doctor.jpg", "doctor.jpeg", "doctor.png", "doctor.webp"):
        p = ROOT / name
        if p.exists():
            wh = img_size(p)
            return (name, wh[0], wh[1]) if wh else (name, 0, 0)
    return None


def build_about() -> str:
    """關於作者頁。

    醫療內容（YMYL）的搜尋排名高度取決於「誰寫的、憑什麼可信」。
    只在頁尾放一個作者方塊不夠，需要一頁完整說明資歷與撰寫原則，
    並讓所有文章都連過來，形成明確的權威訊號。
    """
    title = f"關於{AUTHOR_NAME}醫師與本站｜{SITE_NAME}"
    desc = (f"{AUTHOR_NAME}，腎臟科專科醫師，臨床工作以三高、慢性腎臟病與"
            "血液透析／腹膜透析為主。本頁說明本站的內容撰寫原則、資料來源，"
            "以及本站不提供個別醫療建議的立場。")

    photo = find_doctor_photo()
    if photo:
        name, w, h = photo
        dims = f' width="{w}" height="{h}"' if w else ""
        photo_html = (f'<div><img class="docphoto" src="/{name}"{dims} '
                      f'alt="{esc(AUTHOR_NAME)}醫師" loading="eager"></div>')
        grid_cls = "docintro"
    else:
        photo_html = ""
        grid_cls = "docintro nophoto"

    creds = "".join(
        f'<li class="key">{CHECK_SVG}<span>{esc(t)}</span></li>' if key
        else f'<li>{CHECK_SVG}<span>{esc(t)}</span></li>'
        for t, key in CREDENTIALS)

    body = f"""
<h1>關於{esc(AUTHOR_NAME)}醫師與本站</h1>

<div class="{grid_cls}">
{photo_html}
<div>
  <div class="docname"><small>腎臟科</small>{esc(AUTHOR_NAME)}醫師</div>
  <ul class="doccred">{creds}</ul>
</div>
</div>

<h2 id="zhuan-chang">臨床專長</h2>
<p>三高（高血壓、糖尿病、高血脂）、慢性腎臟病、急性腎衰竭、血液／腹膜透析、
多囊腎、電解質異常、痛風、代謝症候群、戒菸。</p>

<h2 id="wei-shen-me">為什麼做這個網站</h2>
<p>在門診最常遇到的不是不願意配合的病人，而是<strong>被錯誤資訊嚇到、或被錯誤資訊耽誤</strong>的人。
健檢報告上一個紅字，網路上查到的答案從「沒事」到「準備洗腎」都有；而真正需要警覺的訊號，
反而常被當成小毛病。這個網站想做的很簡單：把腎臟與三高的事，用一般人看得懂的方式講清楚，
讓你在跟自己的醫師討論之前，先知道問題在哪裡、該問什麼。</p>

<h2 id="yuan-ze">內容撰寫原則</h2>
<ul>
<li><strong>以國際指引與期刊文獻為依據</strong>，主要參考 KDIGO 慢性腎臟病指引、
以及腎臟醫學與內科領域的同儕審查期刊。</li>
<li><strong>不確定的就說不確定。</strong>醫學上有很多還沒有定論的問題，
這種時候會直接寫「目前證據還不夠」，而不是給一個聽起來很篤定的答案。</li>
<li><strong>不推薦任何商品。</strong>本站不接受保健食品、藥品或醫療器材的業配與贊助，
也不會在文章中推薦特定品牌。</li>
<li><strong>內容會更新。</strong>指引改版、有新的重要證據時會回頭修改舊文，
每篇文章都標示發布與更新日期。</li>
</ul>

<h2 id="bu-ti-gong">本站不提供什麼</h2>
<p>本站的內容是<strong>一般性的健康衛教</strong>，不是針對任何特定個人的診療建議。
具體而言：</p>
<ul>
<li>不提供線上診斷、不解讀個人的檢查報告</li>
<li>不提供個別的用藥建議或劑量調整</li>
<li>不回覆與個人病情有關的私訊或留言諮詢</li>
</ul>
<p>每個人的狀況都不一樣——同樣一個 eGFR 數值，在不同年齡、有沒有蛋白尿、
有沒有其他共病的人身上，意義可能完全不同。這些判斷需要完整的病史、
檢查結果與當面評估，不是任何網站能取代的。<strong>請與你的主治醫師討論。</strong></p>

<h2 id="lian-luo">關於引用</h2>
<p>本站文章歡迎在註明出處與連結原文的前提下引用。若為媒體採訪或授權轉載，
請透過本站說明的方式聯絡。</p>
"""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "AboutPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/about.html",
        "dateModified": TODAY,
        # 結構化資料把資歷寫成機器讀得懂的欄位。醫療內容的可信度評估
        # 很吃「作者是誰、憑什麼」，學歷、任職與指引編撰身分都是可查證的訊號。
        "mainEntity": {
            "@type": "Physician",
            "name": AUTHOR_NAME,
            "jobTitle": AUTHOR_TITLE,
            "description": AUTHOR_BIO,
            "medicalSpecialty": ["Nephrologic", "InternalMedicine"],
            "knowsAbout": ["慢性腎臟病", "急性腎衰竭", "血液透析", "腹膜透析", "多囊腎",
                           "電解質異常", "高血壓", "糖尿病", "高血脂", "痛風",
                           "代謝症候群", "戒菸"],
            "alumniOf": {"@type": "CollegeOrUniversity", "name": "國立成功大學醫學系"},
            "worksFor": {"@type": "Hospital", "name": "郭綜合醫院",
                         "department": {"@type": "MedicalOrganization", "name": "腎臟內科"}},
            "memberOf": [
                {"@type": "Organization", "name": "台灣慢性腎臟病臨床診療指引編撰委員會"},
                {"@type": "MedicalOrganization", "name": "台灣腎臟醫學會"},
                {"@type": "MedicalOrganization", "name": "美國腎臟醫學會",
                 "alternateName": "American Society of Nephrology"},
            ],
            "url": f"{BASE_URL}/about.html",
        },
    }
    return page(title, desc, "about.html", body, jsonld)


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

    # 長文先產生，分類頁才知道要把哪幾篇列為「深入閱讀」
    md_pages = build_markdown_articles()
    for a in md_pages:
        (ROOT / a["path"]).write_text(a["html"], encoding="utf-8")
        written.append(a["path"])
        faq = f"，FAQ {a['faq_count']} 題" if a["faq_count"] else ""
        print(f"  {a['path']}　(長文，分類：{a['cat'] or '未指定'}{faq})")

    for cat, items in by_cat.items():
        path, htm, _t = build_category(cat, items, md_pages)
        (ROOT / path).write_text(htm, encoding="utf-8")
        written.append(path)
        print(f"  {path}　({len(items)} 則，約 {sum(len(i['body']) for i in items):,} 字)")

    idx_path, idx_html = build_index(by_cat, [(a["path"], a["title"]) for a in md_pages])
    (ROOT / idx_path).write_text(idx_html, encoding="utf-8")
    written.insert(0, idx_path)
    print(f"  {idx_path}")

    (ROOT / "about.html").write_text(build_about(), encoding="utf-8")
    print("  about.html　(關於作者，E-E-A-T 權威訊號)")

    (ROOT / "index.html").write_text(build_home(by_cat, md_pages), encoding="utf-8")
    print("  index.html　(網站首頁，衛教為主 + 商城大按鈕)")

    # sitemap：讓搜尋引擎一次拿到所有網址
    urls = ["", "articles/", "about.html", "shop.html"] + [
        p for p in written if not p.endswith("index.html")]
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
