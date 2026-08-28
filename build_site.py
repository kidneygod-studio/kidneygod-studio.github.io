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

# 自訂網域。改這一行之外，repo 根目錄要有對應的 CNAME 檔，
# 且註冊商的 DNS 要指向 GitHub Pages（見 SETUP 說明）。
BASE_URL = "https://kidneygod.net"

SITE_NAME = "護腎教室"

# Cloudflare Web Analytics 的 beacon token。
# 選它而不是 GA4 的理由：不放 cookie、不收集個人識別資料，
# 因此不需要同意橫幅，也不會和「本站不收集任何資料」的定位衝突。
# 留空時完全不輸出這段 script，網站行為不受影響。
# 取得方式：Cloudflare 免費帳號 → Web Analytics → Add a site → 複製 token。
ANALYTICS_TOKEN = "e44b1d39221d4a5085336497dbff3ce4"


def analytics_tag() -> str:
    if not ANALYTICS_TOKEN:
        return ""
    # 寫法對齊 Cloudflare 目前發的片段（type="module"，本身就是延後執行）
    return ('\n<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" '
            f'data-cf-beacon=\'{{"token": "{ANALYTICS_TOKEN}"}}\'></script>')

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

# 社群帳號。這裡同時餵給三個地方：頁尾連結、醫師簡介頁的可見連結，
# 以及 JSON-LD 的 sameAs —— sameAs 是告訴搜尋引擎「這些帳號跟本站是同一個實體」，
# 對「作者是誰」的判定有直接影響，醫療類內容尤其看重這點。
#
# note 顯示帳號代號而不是「現用／原帳號」之類的說明：兩個 IG 只差在代號，
# 直接把代號寫出來讀者自己分得出來，也不必在專業網站上交代帳號的來龍去脈。
# url 為 None 的項目會被自動略過，方便先留位置之後再補。
SOCIAL = [
    {"label": "Threads", "url": "https://www.threads.com/@kidney.godreborn",
     "note": "@kidney.godreborn"},
    {"label": "Instagram", "url": "https://www.instagram.com/kidney.god/",
     "note": "@kidney.god"},
    {"label": "Instagram", "url": "https://www.instagram.com/kidney.godreborn/",
     "note": "@kidney.godreborn"},
    {"label": "Facebook", "url": "https://www.facebook.com/kidneygod",
     "note": "粉絲專頁"},
]
SOCIAL_LIVE = [s for s in SOCIAL if s["url"]]

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

# 頁首的品牌標記。用內嵌 SVG 而不是圖檔：縮放不糊、會跟著深淺色模式換色、
# 不多一次網路請求，而且商城的標誌是為深色底設計的，放在淺色頁面上不合適。
KIDNEY_SVG = (
    '<svg viewBox="0 0 24 24" width="25" height="25" fill="currentColor" aria-hidden="true">'
    '<path d="M13.6 2.6C8.4 2.6 4.4 6.7 4.4 12s4 9.4 9.2 9.4c2.9 0 5-1.6 5-3.8 '
    '0-1.9-1.4-2.9-2.8-3.6-.9-.5-1.5-.9-1.5-2s.6-1.5 1.5-2c1.4-.7 2.8-1.7 2.8-3.6 '
    '0-2.2-2.1-3.8-5-3.8Zm0 2c1.9 0 3 .8 3 1.8 0 .8-.7 1.3-1.7 1.8-1.3.7-2.6 1.6-2.6 '
    '3.8s1.3 3.1 2.6 3.8c1 .5 1.7 1 1.7 1.8 0 1-1.1 1.8-3 1.8-4 0-7.2-3.3-7.2-7.4S9.6 '
    '4.6 13.6 4.6Z"/></svg>'
)

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
/* 錨點跳轉時要扣掉固定頁首的高度，否則標題會被壓在頁首下面。
   頁首約 60px，再加一點餘裕才不會貼著邊。 */
html{scroll-padding-top:78px}
header.site{position:sticky;top:0;z-index:50;background:var(--bg);
background:color-mix(in srgb,var(--bg) 86%,transparent);
backdrop-filter:saturate(150%) blur(10px);-webkit-backdrop-filter:saturate(150%) blur(10px);
border-bottom:1px solid var(--line);margin-bottom:8px}
header.site .wrap{display:flex;align-items:center;justify-content:space-between;
gap:14px;padding-top:11px;padding-bottom:11px}
.brand{display:inline-flex;align-items:center;gap:9px;text-decoration:none;
color:var(--fg);font-weight:800;font-size:1.04rem;letter-spacing:.3px;white-space:nowrap}
.brand svg{color:var(--accent);flex-shrink:0}
.brand:hover{color:var(--accent2)}
header.site nav{display:flex;align-items:center;gap:3px;flex-wrap:wrap;justify-content:flex-end}
header.site nav a{font-size:14px;color:var(--mut);text-decoration:none;font-weight:500;
padding:6px 11px;border-radius:8px;white-space:nowrap;
transition:color .15s,background .15s}
header.site nav a:hover{color:var(--fg);background:var(--card)}
header.site nav a[aria-current="page"]{color:var(--accent2);background:var(--card);font-weight:700}
/* 商城是另一個世界，用它自己的金色標示，一眼看得出不同 */
header.site nav a.shoplink{color:#2b2115;background:#e8c65a;font-weight:700}
header.site nav a.shoplink:hover{color:#2b2115;filter:brightness(1.07)}
@media(max-width:600px){
  header.site .wrap{padding-top:8px;padding-bottom:8px;gap:8px}
  .brand{font-size:.95rem;gap:7px}
  .brand svg{width:22px;height:22px}
  header.site nav{gap:2px}
  /* 隱藏「衛教／關於／知識」前綴，只留兩個字，才排得下一行 */
  header.site nav .np{display:none}
  header.site nav a{padding:9px 10px;font-size:13.5px}
}
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
.social{margin-top:10px;display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center}
.social a{display:inline-flex;align-items:center;gap:6px;
padding:6px 13px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;font-size:.92rem;color:var(--mut)}
.social a:hover{border-color:var(--ink);color:var(--ink)}
.social .nt{color:var(--mut);font-size:.8rem;opacity:.85}
.sociallist a{color:var(--ink)}
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

/* ── 衛教圖卡 ── */
.galnav{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 8px}
.galnav a{font-size:13.5px;background:var(--card);border:1px solid var(--line);
border-radius:99px;padding:6px 14px;text-decoration:none;color:var(--fg)}
.galnav a:hover{border-color:var(--accent)}
.galcard{display:grid;grid-template-columns:210px minmax(0,1fr);gap:22px;
padding:24px 0;border-top:1px solid var(--line);align-items:start}
.galcard:last-of-type{border-bottom:1px solid var(--line)}
.galcard img{width:100%;height:auto;aspect-ratio:1/1;object-fit:cover;
border-radius:10px;border:1px solid var(--line);display:block;background:var(--card);
transition:transform .16s,border-color .16s}
.galcard a.shot:hover img{transform:scale(1.02);border-color:var(--accent)}
.galcard h3{font-size:1.06rem;color:var(--fg);margin:0 0 8px;line-height:1.5}
/* 原文保留換行；貼文的分行本身就是作者安排的節奏，攤平會很難讀 */
.galcard .post{white-space:pre-wrap;font-size:15px;line-height:1.8;margin:0 0 10px}
.galcard .src{font-size:12.5px;color:var(--mut)}
/* 總覽頁：每個主題一塊，配四張縮圖預覽 */
.galgroup{display:block;text-decoration:none;color:inherit;margin:0 0 16px;
border:1px solid var(--line);border-radius:12px;padding:16px 18px;background:var(--card)}
.galgroup:hover{border-color:var(--accent)}
.gg-head{display:flex;justify-content:space-between;align-items:baseline;
gap:12px;margin-bottom:12px}
.gg-head b{font-size:1.08rem}
.gg-head span{font-size:13.5px;color:var(--mut);white-space:nowrap}
.gg-sub{font-size:13.5px;color:var(--mut);line-height:1.65;margin:-6px 0 12px}
/* Day 編號做成小標籤，一眼看得出這是一堂一堂連著的課 */
.galcard .day{display:inline-block;font-size:12px;font-weight:700;color:var(--accent2);
background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:1px 7px;margin-right:8px;vertical-align:2px}
.gg-prev{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.gg-prev img{width:100%;height:auto;aspect-ratio:1/1;object-fit:cover;
border-radius:7px;display:block;border:1px solid var(--line)}
@media(max-width:640px){
  .galcard{grid-template-columns:1fr;gap:14px;padding:20px 0}
  .galcard img{max-width:280px}
  .galcard .post{font-size:14.5px}
}

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
/* 使用說明：定位在「先看這個再決定往哪走」，所以視覺上要跟一般段落分開，
   但又不能重到搶走主標題的位置 */
.howto{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:15px 18px;margin:22px 0 6px;font-size:14.8px;line-height:1.95;color:var(--mut)}
.howto b{display:block;color:var(--fg);font-size:15.2px;margin-bottom:5px}
.howto a{font-weight:700;text-decoration:none;border-bottom:1px solid transparent}
.howto a:hover{border-bottom-color:var(--accent)}
.howto .step{color:var(--fg)}
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
/* 標誌是橫幅比例，固定高度、寬度自動才不會被壓扁。 */
.gamebtn img{height:132px;width:auto;max-width:100%}
.gamebtn .cap{font-size:1.16rem;font-weight:800;color:#e8c65a;
letter-spacing:.4px;line-height:1.5}
@media(max-width:560px){
  .hero h1{font-size:1.68rem}
  .gamebtn{gap:14px;padding:26px 20px}
  .gamebtn img{height:92px}
  .gamebtn .cap{font-size:1.06rem}
}
"""


def slugify(s: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "-", s.strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def social_links() -> str:
    """社群連結。兩個 IG 只差在帳號代號，所以代號一律顯示出來，
    否則頁尾會並排兩顆看起來一模一樣的「Instagram」。

    rel 用 me：這是 IndieWeb 的作者身分標記，部分工具會用它來驗證帳號歸屬，
    和 JSON-LD 的 sameAs 是互補的兩套機制。"""
    return "".join(
        f'<a href="{s["url"]}" rel="me noopener" target="_blank">{esc(s["label"])}'
        + (f'<span class="nt">{esc(s["note"])}</span>' if s.get("note") else "")
        + "</a>"
        for s in SOCIAL_LIVE)


def page(title: str, desc: str, path: str, body: str, jsonld: dict | None = None,
         extra_head: str = "", home: bool = False) -> str:
    """所有頁面共用的骨架。canonical 與 OG 是搜尋引擎與分享預覽的基本要求。"""
    # canonical 必須和 sitemap 宣告的網址逐字相同，否則等於叫 Google 索引兩個位址。
    # sitemap 用的是目錄形式（/articles/），這裡把 index.html 收掉對齊。
    url = f"{BASE_URL}/{re.sub(r'(^|/)index\.html$', r'\1', path)}"

    # 目前所在區塊要標示出來，讀者才知道自己在哪一層
    in_gallery = "gallery" in path
    in_articles = path.startswith("articles/") and not in_gallery
    cur = {"articles": in_articles, "gallery": in_gallery,
           "about": path == "about.html"}

    # 前綴包在 span 裡，手機上隱藏起來變成「文章／圖卡／關於／商城」，
    # 否則四個四字標籤會換成兩行，固定頁首會高到 84px。
    def navlink(href: str, prefix: str, label: str, key: str, cls: str = "") -> str:
        mark = ' aria-current="page"' if cur.get(key) else ""
        c = f' class="{cls}"' if cls else ""
        return f'<a href="{href}"{c}{mark}><span class="np">{prefix}</span>{label}</a>'

    nav = (navlink("/articles/", "衛教", "文章", "articles")
           + navlink("/articles/gallery.html", "衛教", "圖卡", "gallery")
           + navlink("/about.html", "關於", "作者", "about")
           + navlink("/shop.html", "知識", "商城", "shop", "shoplink"))
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
<a class="brand" href="/">{KIDNEY_SVG}<span>{SITE_NAME}</span></a>
<nav>{nav}</nav>
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
<p class="social">{social_links()}</p>
</div></footer>{analytics_tag()}
</body>
</html>
"""


def build_category(cat: str, items: list[dict],
                   articles: list[dict] | None = None) -> tuple[str, str, str]:
    slug = CAT_SLUG[cat]
    path = f"articles/{slug}.html"
    # 用冒號而不是「與」串接：分類名本身可能就含「與」（警訊與迷思），
    # 接成「警訊與迷思與腎臟健康」會讀不順。
    title = f"{cat}：腎臟健康的 {len(items)} 個重點整理｜{SITE_NAME}"
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
<h1>{esc(cat)}：腎臟健康重點整理</h1>
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
        "headline": f"{cat}：腎臟健康重點整理",
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


def build_index(by_cat: dict[str, list[dict]], extra_pages: list[tuple[str, str]],
                n_gallery: int = 0) -> tuple[str, str]:
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

    gal = ""
    if n_gallery:
        gal = (f'<h2>衛教圖卡</h2>'
               f'<a class="feat" href="/articles/gallery.html">'
               f'<div class="t">{n_gallery} 張圖解，依主題分類</div>'
               f'<div class="d">原本發表在社群上的衛教圖，整理後收在這裡方便回頭查找。</div></a>')

    body = f"""
<h1>腎臟與三高衛教文章</h1>
<p class="lede">這裡整理慢性腎臟病、高血壓、糖尿病與高血脂相關的衛教內容，
依據國際指引與期刊文獻撰寫，目的是讓一般人也能看懂自己的身體與檢查報告。</p>
<div class="cats">{cards}</div>
{extra}
{gal}
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


def build_home(by_cat: dict[str, list[dict]], extra: list[dict], n_gallery: int = 0) -> str:
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

    feat_sect = (f'<h2 class="sect" id="deep">深入文章</h2>'
                 f'<div class="sd">完整長文，適合想把一個主題徹底搞懂的人</div>{feats}'
                 if feats else "")

    # 直接讀 logo 實際尺寸，換圖時不必再手改寫死的數字（換過一次比例就變了）
    lw = img_size(ROOT / "logo.png")
    logo_dims = f' width="{lw[0]}" height="{lw[1]}"' if lw else ""

    gal_sect = (f'<h2 class="sect" id="gallery">衛教圖卡</h2>'
                f'<div class="sd">社群上發表過的圖解，依主題整理並附上完整說明</div>'
                f'<a class="feat" href="/articles/gallery.html">'
                f'<div class="t">{n_gallery} 張衛教圖卡</div>'
                f'<div class="d">血壓、血糖、血脂、飲食、用藥安全、檢查數值…'
                f'點主題可跳到該區。</div></a>' if n_gallery else "")

    body = f"""
<div class="hero">
<h1>護腎專家－{esc(AUTHOR_NAME)}醫師的護腎教室</h1>
<p class="sub">把腎臟的事，講到你聽得懂。慢性腎臟病、高血壓、糖尿病、高血脂——
這裡用一般人看得懂的方式，說明檢查數字代表什麼、哪些習慣真的有影響、哪些說法沒有根據。</p>
<p class="cred">內容依據國際指引與期刊文獻撰寫，持續更新。
<a href="/about.html">關於{esc(AUTHOR_NAME)}醫師 →</a></p>

<p class="howto"><b>這個網站怎麼用</b>
<span class="step">不知道從哪開始</span>：先玩 <a href="/shop.html">遊戲商城</a>，邊玩邊收集護腎知識卡。<br>
<span class="step">有明確想查的問題</span>：到 <a href="#topics">依主題閱讀</a> 挑對應主題。<br>
<span class="step">想把一件事徹底弄懂</span>：看 <a href="#deep">深入文章</a>，一篇讀完不必再查。<br>
<span class="step">只想快速看重點</span>：翻 <a href="#gallery">衛教圖卡</a>，一張圖說完一件事。</p>
</div>

<h2 class="sect" id="play">從免費遊戲商城學習</h2>
<div class="sd">邊玩邊收集護腎知識卡與貓咪貼圖——不收費、沒有金流，唯一會出貨的是護腎知識</div>
<a class="gamebtn" href="/shop.html">
  <img src="/logo.png" alt="" aria-hidden="true"{logo_dims}>
  <span class="cap">護腎知識卡片收集商城</span>
</a>

<h2 class="sect" id="topics">依主題閱讀</h2>
<div class="sd">{sum(len(v) for v in by_cat.values())} 則衛教內容，分成 {len(by_cat)} 個主題，適合想直接找答案的人</div>
<div class="cats">{cards}</div>

{feat_sect}
{gal_sect}
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/",
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE,
                   "url": f"{BASE_URL}/about.html",
                   "sameAs": [s["url"] for s in SOCIAL_LIVE]},
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


GALLERY_MANIFEST = ROOT / "gallery" / "manifest.json"


def load_gallery() -> list[dict]:
    if not GALLERY_MANIFEST.exists():
        return []
    try:
        return json.loads(GALLERY_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _gal_card(it: dict) -> str:
    src = (f'<span class="src">{it["date"]}　·　'
           f'<a href="{esc(it["permalink"])}" target="_blank" rel="noopener">原始貼文 →</a>'
           f"</span>" if it.get("permalink") else f'<span class="src">{it["date"]}</span>')
    day = f'<span class="day">Day {it["day"]}</span>' if it.get("day") else ""
    return (f'<div class="galcard">'
            f'<a class="shot" href="/{it["full"]}" target="_blank" rel="noopener">'
            f'<img src="/{it["thumb"]}" alt="{esc(it["cap"])}" loading="lazy" '
            f'width="360" height="360"></a>'
            f'<div><h3>{day}{esc(it["cap"])}</h3>'
            f'<p class="post">{esc(it.get("text", ""))}</p>{src}</div>'
            f"</div>")


def build_gallery(items: list[dict]) -> list[tuple[str, str]]:
    """衛教圖卡：一頁總覽 + 每個主題各一頁。

    刻意拆成多頁而不是全部塞一頁——95 張卡片加上完整貼文約兩萬七千字，
    單頁會高達兩萬多像素，讀者滑不到底，八個主題混在一起也讓每頁的主題失焦。
    拆開後每頁三千多字、聚焦單一主題，對閱讀和搜尋都比較好。

    另外刻意不寫 JavaScript 燈箱——縮圖直接連到大圖檔，
    搜尋引擎抓得到、沒有 JS 也能用。
    """
    if not items:
        return []

    # 系列的中繼資料由 import_gallery.py 產生，這裡直接讀，避免兩邊各維護一份
    sp = ROOT / "gallery" / "series.json"
    try:
        series = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else []
    except json.JSONDecodeError:
        series = []
    by_series: dict[str, list[dict]] = {}
    for it in items:
        by_series.setdefault(it.get("series", "其他"), []).append(it)

    out: list[tuple[str, str]] = []

    for s in series:
        name, slug = s["name"], s["slug"]
        group = by_series.get(name, [])
        if not group:
            continue
        path = f"articles/gallery-{slug}.html"
        # Day 區間沒有人拿來搜尋，放標題只會把標題推過截斷長度，移到描述裡。
        rng = f"（{s['day_range']}）" if s.get("day_range") else ""
        title = f"{name}：{len(group)} 張衛教圖卡｜{SITE_NAME}"
        heads = "、".join(it["cap"] for it in group[:3])
        desc = (f"{AUTHOR_NAME}醫師的「{name}」系列{rng}共 {len(group)} 張衛教圖解，"
                f"內容包含：{heads} 等。")[:150]

        others = "".join(
            f'<a href="/articles/gallery-{o["slug"]}.html">'
            f'<div class="t">{esc(o["name"])}（{o["count"]}）</div>'
            f'<div class="d">{esc(o.get("intro", "")[:44])}…</div></a>'
            for o in series if o["name"] != name)

        body = f"""
<h1>{esc(name)}</h1>
<p class="lede">{esc(s.get("intro", ""))}以下 {len(group)} 張圖卡原本發表在社群上，
依 Day 順序整理，並附上每張圖當初的完整說明文字。點圖片可看大圖。</p>
<p class="meta">作者：<a href="/about.html">{esc(AUTHOR_NAME)}</a>（{esc(AUTHOR_TITLE)}）
　·　共 {len(group)} 張{rng}　·　更新於 {TODAY}</p>
<div class="galnav"><a href="/articles/gallery.html">← 全部系列</a>
<a href="/articles/">依主題閱讀 →</a></div>
{''.join(_gal_card(it) for it in group)}
<h2 class="backlink">其他系列</h2>
<div class="cats">{others}</div>
"""
        jsonld = {
            "@context": "https://schema.org", "@type": "ImageGallery",
            "name": name, "description": desc, "inLanguage": "zh-Hant",
            "url": f"{BASE_URL}/{path}", "dateModified": TODAY,
            "numberOfItems": len(group),
            "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE,
                       "url": f"{BASE_URL}/about.html"},
        }
        out.append((path, page(title, desc, path, body, jsonld)))

    # 總覽頁：每個主題一張卡片，配四張縮圖當預覽
    path = "articles/gallery.html"
    title = f"衛教圖卡總覽：{len(items)} 張腎臟與三高圖解｜{SITE_NAME}"
    desc = (f"{AUTHOR_NAME}醫師整理的 {len(items)} 張腎臟與三高衛教圖卡，"
            "依血壓、血糖、血脂、飲食、用藥安全、檢查數值等八個主題分類。")

    blocks = []
    for s in series:
        group = by_series.get(s["name"], [])
        if not group:
            continue
        prev = "".join(
            f'<img src="/{it["thumb"]}" alt="{esc(it["cap"])}" loading="lazy" '
            f'width="360" height="360">' for it in group[:4])
        rng = f'　{s["day_range"]}' if s.get("day_range") else ""
        blocks.append(
            f'<a class="galgroup" href="/articles/gallery-{s["slug"]}.html">'
            f'<div class="gg-head"><b>{esc(s["name"])}</b>'
            f'<span>{len(group)} 張{rng} →</span></div>'
            f'<div class="gg-sub">{esc(s.get("intro", ""))}</div>'
            f'<div class="gg-prev">{prev}</div></a>')

    body = f"""
<h1>衛教圖卡總覽</h1>
<p class="lede">社群上發表過的衛教圖解，依原本的系列整理收錄，每一張都附上當初的完整說明文字。
共 {len(items)} 張。</p>
<p class="meta">作者：<a href="/about.html">{esc(AUTHOR_NAME)}</a>（{esc(AUTHOR_TITLE)}）
　·　更新於 {TODAY}</p>
{''.join(blocks)}
"""
    jsonld = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": title, "description": desc, "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/{path}", "dateModified": TODAY,
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE,
                   "url": f"{BASE_URL}/about.html"},
    }
    out.append((path, page(title, desc, path, body, jsonld)))
    return out


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

<h2 id="she-qun">社群帳號</h2>
<p>以下是我本人經營的帳號。日常的衛教圖卡與短文會先發在社群，
完整的長文與整理過的內容放在這個網站。</p>
<p class="social sociallist">{social_links()}</p>
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
            # 宣告這些社群帳號與本人是同一個實體，協助搜尋引擎建立作者身分
            "sameAs": [s["url"] for s in SOCIAL_LIVE],
        },
    }
    return page(title, desc, "about.html", body, jsonld)


# ---------------------------------------------------------------------------
# 食物查詢工具
#
# 這一頁的醫療風險比其他頁高，因此有三個刻意的設計決定：
#
# 1. 不給「能吃／不能吃」的二元答案。同一種食物對第 2 期、第 5 期與透析病人
#    的意義完全不同，二元答案必然對其中某一群人是錯的。改成顯示數值 + 分級
#    + 說明「誰該在意這一項」。
#
# 2. 蛋白質不做好壞分級。早期 CKD 常需限制蛋白質，透析病人反而要增加——方向
#    相反，做成紅綠燈一定會害到其中一群人，所以只顯示數值並加註提醒。
#
# 3. 門檻標示為「本站採用」而非醫學標準，並附資料來源與單位。
# ---------------------------------------------------------------------------

FOOD_DB = ROOT / "food_db.json"

# 每 100 公克的分級門檻，腎臟病飲食衛教常用的區間。改這裡前端就會跟著變。
FOOD_TIERS = {
    "na": {"label": "鈉", "unit": "mg", "mid": 100, "high": 400},
    "k":  {"label": "鉀", "unit": "mg", "mid": 150, "high": 250},
    "p":  {"label": "磷", "unit": "mg", "mid": 50,  "high": 150},
}

FOOD_CSS_JS = r"""
<style>
.warnbox{background:#fff6f0;border-left:4px solid #c05621;padding:16px 18px;
border-radius:0 8px 8px 0;margin:22px 0}
.warnbox b{color:#9c4221;display:block;margin-bottom:8px;font-size:1.05rem}
.warnbox p{margin:0 0 8px;font-size:.96rem}
.warnbox p:last-child{margin:0}
.foodtool{margin:26px 0 34px}
.fsearch{display:flex;gap:10px;flex-wrap:wrap}
.fsearch input{flex:1 1 240px;min-width:0;padding:13px 15px;font-size:1.05rem;
border:2px solid var(--line);border-radius:10px;background:#fff;color:var(--ink)}
.fsearch input:focus{outline:none;border-color:var(--accent2)}
.fsearch select{padding:13px 12px;font-size:1rem;border:2px solid var(--line);
border-radius:10px;background:#fff;color:var(--ink)}
.fhint{color:var(--mut);font-size:.9rem;margin:10px 2px 0}
.fres{margin-top:14px;display:flex;flex-direction:column;gap:10px}
.fcard{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fff}
.fcard h3{margin:0 0 3px;font-size:1.06rem}
.fcard .fmeta{color:var(--mut);font-size:.83rem;margin:0 0 10px}
.fvals{display:flex;flex-wrap:wrap;gap:8px}
.fv{display:flex;align-items:baseline;gap:6px;padding:6px 11px;border-radius:999px;
font-size:.9rem;border:1px solid var(--line);background:#fafafa}
.fv .num{font-variant-numeric:tabular-nums;font-weight:700}
.fv .rng{font-variant-numeric:tabular-nums;font-size:.78rem;color:var(--mut)}
.fv.lo{background:#f0f8f1;border-color:#bcdcc0}
.fv.mid{background:#fdf7e6;border-color:#e8d59a}
.fv.hi{background:#fdf0ee;border-color:#e9b4aa}
.fv .tag{font-size:.76rem;color:var(--mut)}
/* 全站的 th,td 是 white-space:nowrap（給分期表那種短欄位用的）。
   這張表的第三欄是長句子，必須允許換行，否則會把版面撐到 1,200px 以上。 */
.ftiers th,.ftiers td{white-space:normal;vertical-align:top}
.ftiers td:first-child,.ftiers th:first-child{white-space:nowrap}
@media(max-width:560px){ .fsearch select{flex:1 1 100%} }
</style>
<script>
const TIERS = __TIERS__;
let DB = null;

const tier = (key, v) => {
  if(v === null || v === undefined) return "";
  const t = TIERS[key];
  return v >= t.high ? "hi" : (v >= t.mid ? "mid" : "lo");
};
const tierWord = c => c === "hi" ? "偏高" : (c === "mid" ? "中等" : "偏低");

/* 數值欄是 [代表值] 或 [代表值, 最小, 最大]。同一種食物多次取樣且差異大時
   顯示範圍，而不是挑一個數字假裝很精確。 */
function card(r){
  const [name, alias, cat, samples, na, k, p, prot, kcal] = r;
  /* 括號不可省：「352.7 303–463」會讓人分不出哪個是代表值 */
  const span = v => (v.length > 1) ? ('<span class="rng">(' + v[1] + '–' + v[2] + ')</span>') : '';
  const chip = (key, v) => {
    if(!v) return "";
    const t = TIERS[key], c = tier(key, v[0]);
    return '<span class="fv ' + c + '">' + t.label +
           '<span class="num">' + v[0] + '</span>' + span(v) +
           '<span class="tag">' + t.unit + '・' + tierWord(c) + '</span></span>';
  };
  const plain = (label, v, unit) => !v ? "" :
    '<span class="fv">' + label + '<span class="num">' + v[0] + '</span>' + span(v) +
    '<span class="tag">' + unit + '</span></span>';
  const note = samples > 1 ? ('　·　' + samples + ' 次取樣') : '';
  return '<div class="fcard"><h3>' + name + '</h3>' +
         '<p class="fmeta">' + cat + (alias ? '　俗名：' + alias : '') +
         '　·　每 100 公克' + note + '</p>' +
         '<div class="fvals">' + chip("na", na) + chip("k", k) + chip("p", p) +
         plain("蛋白質", prot, "g") + plain("熱量", kcal, "kcal") + '</div></div>';
}

function render(){
  const q = document.getElementById("fq").value.trim();
  const cat = document.getElementById("fcat").value;
  const hint = document.getElementById("fhint");
  const box = document.getElementById("fres");
  if(!DB){ hint.textContent = "資料載入中…"; return; }
  if(q.length < 2 && !cat){
    box.innerHTML = "";
    hint.textContent = "共 " + DB.rows.length.toLocaleString() + " 種食物。輸入兩個字以上開始搜尋。";
    return;
  }
  let hits = DB.rows;
  if(cat) hits = hits.filter(r => r[2] === cat);
  if(q)   hits = hits.filter(r => r[0].includes(q) || (r[1] && r[1].includes(q)));
  /* 「查不到」多半不是打錯字，而是使用者搜了一道菜。這是食材資料庫，
     沒有「滷肉飯」「牛肉麵」這種組合料理，講清楚比叫人再試一次有用。 */
  hint.innerHTML = hits.length
    ? ("找到 " + hits.length + " 筆")
    : '查不到「' + q + '」。這是<b>食材</b>資料庫，沒有收錄組合料理——'
      + '例如查不到「滷肉飯」，但查得到「豬肉」「白米」「醬油」。試著搜食材看看。';
  box.innerHTML = hits.slice(0, 60).map(card).join("");
  if(hits.length > 60) box.insertAdjacentHTML("beforeend",
    '<p class="fhint">只顯示前 60 筆，請輸入更完整的名稱縮小範圍。</p>');
}

/* 這段是從 <head> 載入的，執行時 body 還沒解析，直接抓元素會拿到 null。
   全部等 DOMContentLoaded 之後再做。 */
function init(){
  document.getElementById("fq").addEventListener("input", render);
  document.getElementById("fcat").addEventListener("change", render);
  (async () => {
    try{
      DB = await (await fetch("/food_db.json")).json();
      const sel = document.getElementById("fcat");
      DB.cats.forEach(c => {
        const o = document.createElement("option");
        o.value = c; o.textContent = c; sel.appendChild(o);
      });
      render();
    }catch(e){
      document.getElementById("fhint").textContent = "資料載入失敗，請重新整理頁面。";
    }
  })();
}
if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
</script>
"""


def build_food() -> str:
    """食物營養查詢頁。資料在建置時就轉好放進 food_db.json，
    前端只做搜尋與篩選——沒有後端，也不記錄使用者查了什麼。"""
    if not FOOD_DB.exists():
        return ""

    db = json.loads(FOOD_DB.read_text(encoding="utf-8"))
    n = len(db["rows"])
    title = f"腎臟病飲食查詢：{n:,} 種食物的鈉鉀磷含量｜{SITE_NAME}"
    desc = (f"查詢 {n:,} 種食物的鈉、鉀、磷與蛋白質含量，資料來自衛福部食藥署"
            f"台灣食品營養成分資料庫。該注意哪一項，取決於你的腎功能分期。")

    body = f"""
<h1>腎臟病飲食查詢</h1>
<p class="lede">查詢食物的<strong>鈉、鉀、磷</strong>含量。這三項是腎臟病飲食最需要注意的，
但<strong>該注意哪一項，取決於你的腎功能分期</strong>——不是每個人都要限制同樣的東西。</p>

<div class="warnbox">
  <b>這個工具不會告訴你「能不能吃」</b>
  <p>因為同一種食物，對第 2 期、第 5 期、以及透析中的病人，意義完全不同。
  給一個二元答案，必然會對其中一群人是錯的。</p>
  <p>它做的是把數值攤開，並說明<strong>哪些人需要在意哪一項</strong>。
  實際的飲食計畫請與你的醫師或營養師討論。</p>
</div>

<div class="foodtool">
  <div class="fsearch">
    <input id="fq" type="search" placeholder="輸入食物名稱，例如 香蕉、豆腐、吐司…"
           autocomplete="off" spellcheck="false" aria-label="搜尋食物">
    <select id="fcat" aria-label="依分類篩選"><option value="">全部分類</option></select>
  </div>
  <p class="fhint" id="fhint">共 {n:,} 種食物。輸入兩個字以上開始搜尋。</p>
  <div id="fres" class="fres"></div>
</div>

<h2 id="san-xiang">這三項分別是誰要注意</h2>
<div class="tw">
<table class="ftiers">
  <thead><tr><th>營養素</th><th>誰需要注意</th><th>為什麼</th></tr></thead>
  <tbody>
    <tr><td><b>鈉</b></td><td>幾乎所有人</td>
        <td>升高血壓、增加腎絲球負擔、加重蛋白尿，還會削弱降血壓藥的效果。
        詳見<a href="/articles/taiwan-eating-out-sodium.html">外食減鈉指南</a></td></tr>
    <tr><td><b>鉀</b></td><td>中晚期（eGFR 低於 45）與透析患者</td>
        <td>腎功能下降時排鉀能力變差，血鉀過高可能造成心律不整，且初期沒有症狀。
        <strong>早期患者通常不需要限鉀</strong>，過度限制反而會少吃了蔬果</td></tr>
    <tr><td><b>磷</b></td><td>中晚期與透析患者</td>
        <td>磷排不掉會影響骨骼與血管。加工食品的「磷酸鹽添加物」吸收率遠高於
        天然食物中的磷，是最該優先避開的來源</td></tr>
  </tbody>
</table>
</div>

<div class="note">
  <p><b>蛋白質為什麼不做分級？</b>因為方向是相反的：<strong>早期腎臟病常需要限制蛋白質，
  透析患者反而需要增加</strong>。做成紅綠燈一定會害到其中一群人，所以這裡只顯示數值。
  你的蛋白質目標請直接問你的醫師或營養師。</p>
</div>

<h2 id="lai-yuan">資料來源與限制</h2>
<ul>
<li>資料來自<strong>衛生福利部食品藥物管理署「台灣食品營養成分資料庫」</strong>
（<a href="{db['source_url']}" rel="noopener" target="_blank">政府資料開放平臺</a>，
{db['licence']}），共 {n:,} 種食物</li>
<li>所有數值為<strong>{db['unit']}</strong>的含量</li>
<li><strong>烹調方式會大幅改變結果</strong>：水煮會讓鉀溶進水裡，所以「先燙過再炒」
是常見的降鉀做法；反之滷、醃、加工會大幅增加鈉</li>
<li><strong>這是食材資料庫，不是料理資料庫</strong>。查得到「豬肉」「白米」「醬油」，
但查不到「滷肉飯」「牛肉麵」這類組合料理</li>
<li>同一種食物多次取樣且差異較大時，會同時顯示<strong>代表值與範圍</strong>，
不挑單一數字假裝精確</li>
<li>本站不記錄你查詢了什麼，搜尋完全在你的瀏覽器內完成</li>
</ul>
"""

    extra = FOOD_CSS_JS.replace("__TIERS__", json.dumps(FOOD_TIERS, ensure_ascii=False))
    jsonld = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/food.html",
        "dateModified": TODAY,
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_TITLE,
                   "url": f"{BASE_URL}/about.html"},
        "citation": {"@type": "Dataset", "name": db["source"], "url": db["source_url"]},
    }
    return page(title, desc, "food.html", body, jsonld, extra_head=extra)


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

    gallery_items = load_gallery()
    for gpath, ghtml in build_gallery(gallery_items):
        (ROOT / gpath).write_text(ghtml, encoding="utf-8")
        written.append(gpath)
        print(f"  {gpath}")

    idx_path, idx_html = build_index(by_cat, [(a["path"], a["title"]) for a in md_pages],
                                     len(gallery_items))
    (ROOT / idx_path).write_text(idx_html, encoding="utf-8")
    written.insert(0, idx_path)
    print(f"  {idx_path}")

    (ROOT / "about.html").write_text(build_about(), encoding="utf-8")
    print("  about.html　(關於作者，E-E-A-T 權威訊號)")

    (ROOT / "index.html").write_text(
        build_home(by_cat, md_pages, len(gallery_items)), encoding="utf-8")
    print("  index.html　(網站首頁，衛教為主 + 商城大按鈕)")

    food_html = build_food()
    if food_html:
        (ROOT / "food.html").write_text(food_html, encoding="utf-8")
        print("  food.html　(食物營養查詢工具)")

    # sitemap：讓搜尋引擎一次拿到所有網址
    urls = ["", "articles/", "about.html", "shop.html"] + (
        ["food.html"] if food_html else []) + [
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
