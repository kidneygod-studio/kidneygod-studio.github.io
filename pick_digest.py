#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""從「腎臟病學每日精選摘要」挑一篇，轉成護腎教室新知頁要用的格式。

那份摘要在 C:\\Users\\user\\nephrology_digest\\，由另一支排程每天產生
（nephrology_daily_YYYY-MM-DD.html，每份 2–3 篇）。這支只做「挑出來、
轉格式、印出來讓你貼」，**不會自己改 build_site.py，也不抓網路**。

刻意做成手動兩步（先看清單、再挑一篇），不做自動匯入：
掛上網站的東西應該有人看過一眼才上去，而不是排程說什麼就放什麼。

    python pick_digest.py                     列出最近 10 天有哪些
    python pick_digest.py 2026-09-05          列出那天的篇目
    python pick_digest.py 2026-09-05 1        印出第 1 篇，轉成可貼的格式

印出來的東西直接貼進 build_site.py 的 PAPERS 最前面（新的排前面），
再跑 build_site.py 與 bump_assets.py。貼之前記得看一遍：
    · topic 是程式猜的，多半要自己改
    · url 由 DOI 組出來，沒有 DOI 的要自己補
"""
from __future__ import annotations

import html as htmllib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DIGEST = Path(r"C:\Users\user\nephrology_digest")

# 期刊縮寫 → 顯示用標籤。查不到就用原文的 jtag。
JTAG = {
    "THE LANCET": "THE LANCET", "NEJM": "NEJM", "JAMA": "JAMA",
    "NATURE": "NATURE", "KI": "KIDNEY INT", "JASN": "JASN",
    "CJASN": "CJASN", "AJKD": "AJKD", "NDT": "NDT",
}

# 標題關鍵字 → 主題標籤。猜錯很正常，貼之前自己改。
TOPIC = [
    ("移植", "腎臟移植"), ("xeno", "腎臟移植"), ("豬腎", "腎臟移植"),
    ("IgA", "IgA 腎病變"), ("透析", "透析"), ("dialysis", "透析"),
    ("糖尿病", "糖尿病腎病變"), ("SGLT2", "糖尿病腎病變"),
    ("血壓", "高血壓"), ("hypertension", "高血壓"),
    ("急性腎損傷", "急性腎損傷"), ("AKI", "急性腎損傷"),
]


CJK = r"[一-鿿　-〿]"


def zh_punct(s: str) -> str:
    """接在中文後面的半形標點換成全形。

    那份每日摘要用半形逗號（「…271天,第14天…」），在中文段落裡看起來字距
    會忽大忽小。只在前一個字是中文時才換，避免動到 "EGEN-2784, 10.1016/..."
    這類西文與識別碼。括號不動——括號裡常常是英文或數字。
    """
    for half, full in ((",", "，"), (";", "；"), ("?", "？"), ("!", "！")):
        s = re.sub(f"({CJK}){re.escape(half)}", rf"\1{full}", s)
    # 冒號要排除 "DOI: 10.x" 這種，所以限定後面不是空白
    s = re.sub(f"({CJK}):(?!\\s)", r"\1：", s)
    return s


def strip(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return zh_punct(re.sub(r"\s+", " ", htmllib.unescape(s)).strip())


def by_class(blk: str, cls: str) -> list[str]:
    """抓某個 class 的元素內容，**不管它用什麼標籤**。

    這份摘要的產生器改過十幾版：zh-title 在新版是 <div>、舊版是 <h2>；
    en-title 有時是 <div> 有時是 <p>。寫死標籤名的話，一改版就整批抓不到，
    而且不會噴錯——只會安靜地產出一堆空欄位。
    """
    return [m.group(2) for m in
            re.finditer(rf'<(\w+)[^>]*class="{cls}"[^>]*>(.*?)</\1>', blk, re.S)]


def parse(path: Path) -> list[dict]:
    h = path.read_text("utf-8", "replace")
    out = []
    for blk in re.findall(r'<article class="paper">(.*?)</article>', h, re.S):
        def one(cls):
            v = by_class(blk, cls)
            return strip(v[0]) if v else ""

        kp = {}
        for k in by_class(blk, "keypoints"):
            for dt, dd in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", k, re.S):
                kp[strip(dt)] = strip(dd)

        # 段落標題與內容是**兄弟節點**，不是父子：
        #   <div class="sec">研究背景 BACKGROUND</div>
        #   <p class="sec-body">……</p>
        # 第一版當成父子去抓，所以背景與方法從來沒抓到過，而且不會噴錯。
        secs = {}
        for lab, body in re.findall(
                r'<(?:\w+)[^>]*class="sec"[^>]*>(.*?)</\w+>\s*'
                r'<(?:\w+)[^>]*class="sec-body"[^>]*>(.*?)</\w+>', blk, re.S):
            secs[strip(lab)] = strip(body)

        items = []
        for ul in by_class(blk, "findings"):
            items += [strip(li) for li in re.findall(r"<li>(.*?)</li>", ul, re.S)]

        byline = one("byline")
        doi = ""
        md = re.search(r"10\.\d{4,9}/[^\s<\"]+", byline)
        if md:
            doi = md.group(0).rstrip(".,;")

        out.append({
            "jtag": one("jtag"),
            "zh": one("zh-title"),
            "en": one("en-title"),
            "byline": byline,
            "doi": doi,
            "kp": kp,
            "secs": secs,
            "items": items,
            "clin": one("clin"),
            "limit": one("limit"),
        })
    return out


def pick_key(d: dict, *names: str) -> str:
    """Key Points 的 dt 寫法可能是「問題 Question」也可能只有「問題」。"""
    for k, v in d.items():
        if any(n in k for n in names):
            return v
    return ""


def guess_topic(zh: str, en: str) -> str:
    for kw, t in TOPIC:
        if kw.lower() in (zh + en).lower():
            return t
    return "（自己填）"


def py(s: str, indent: int = 8) -> str:
    """折成看得懂的 Python 字串常值。"""
    if not s:
        return '""'
    pad = " " * indent
    parts, line = [], ""
    for ch in s:
        line += ch
        if len(line) >= 30 and ch in "，。；、）":
            parts.append(line)
            line = ""
    if line:
        parts.append(line)
    esc = [p.replace("\\", "\\\\").replace('"', '\\"') for p in parts]
    return ("\n" + pad).join(f'"{p}"' for p in esc)


def emit(e: dict, date: str) -> None:
    jt = JTAG.get(e["jtag"].upper(), e["jtag"].upper())
    url = f"https://doi.org/{e['doi']}" if e["doi"] else "（沒有 DOI，自己補網址）"
    cite = e["byline"] or "（自己補出處）"
    print("    {")
    print(f'        "journal": "{jt}",')
    print(f'        "date": "{date}",')
    print(f'        "topic": "{guess_topic(e["zh"], e["en"])}",')
    print(f'        "zh": {py(e["zh"])},')
    print(f'        "en": {py(e["en"])},')
    print(f'        "cite": {py(cite)},')
    print(f'        "url": "{url}",')
    for key, names in (("q", ("問題", "Question")), ("f", ("發現", "Findings")),
                       ("m", ("意義", "Meaning"))):
        v = pick_key(e["kp"], *names)
        if v:
            print(f'        "{key}": {py(v)},')
    for key, names in (("bg", ("背景", "BACKGROUND")),
                       ("me", ("方法", "METHODS"))):
        v = pick_key(e["secs"], *names)
        if v:
            print(f'        "{key}": {py(v)},')
    if e["items"]:
        print('        "r": [')
        for it in e["items"]:
            print(f"            {py(it, 16)},")
        print("        ],")
    if e["clin"]:
        print(f'        "sig": {py(e["clin"])},')
    if e["limit"]:
        lim = re.sub(r"^(限制|侷限性?)[：:]\s*", "", e["limit"])
        print(f'        "lim": {py(lim)},')
    print("    },")


def main() -> int:
    if not DIGEST.is_dir():
        sys.exit(f"找不到 {DIGEST}")
    files = sorted(DIGEST.glob("nephrology_daily_*.html"), reverse=True)
    if not files:
        sys.exit(f"{DIGEST} 裡沒有每日摘要")

    args = sys.argv[1:]
    if not args:
        print("最近的每日摘要（挑一天再跑一次）\n")
        for f in files[:10]:
            d = f.stem.replace("nephrology_daily_", "")
            try:
                n = len(parse(f))
            except Exception:
                n = -1
            print(f"  {d}　{n} 篇")
        print(f"\n  python pick_digest.py {files[0].stem[-10:]}")
        return 0

    date = args[0]
    f = DIGEST / f"nephrology_daily_{date}.html"
    if not f.exists():
        sys.exit(f"沒有 {f.name}。先不帶參數跑一次看有哪些日期。")
    papers = parse(f)
    if not papers:
        sys.exit(f"{f.name} 解析不出任何一篇——格式可能改了，這支要跟著改。")

    if len(args) == 1:
        print(f"{date}　共 {len(papers)} 篇\n")
        for i, e in enumerate(papers, 1):
            print(f"  [{i}] {e['jtag']}　{e['zh'][:52]}")
            print(f"      {e['byline'][:76]}")
            miss = [n for n, v in (("Key Points", e["kp"]), ("結果", e["items"]))
                    if not v]
            if miss:
                print(f"      ⚠ 缺：{'、'.join(miss)}")
        print(f"\n  python pick_digest.py {date} 1")
        return 0

    try:
        idx = int(args[1])
        e = papers[idx - 1]
    except (ValueError, IndexError):
        sys.exit(f"篇號要是 1–{len(papers)}")

    print(f"貼進 build_site.py 的 PAPERS 最前面（新的排前面）：\n")
    emit(e, date)
    print("\n貼完跑：python build_site.py && python bump_assets.py"
          " && python check_site.py")
    print("貼之前檢查：topic 是猜的、url 由 DOI 組出來、"
          "有沒有哪一段其實是空的。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
