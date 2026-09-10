#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「腎臟病學每日精選摘要」整批匯入網站的新知資料檔。

    nephrology_digest/nephrology_daily_*.html   ← 另一支排程每天產生
        ↓  python import_digests.py
    articles_src/news.json                      ← 網站的新知資料
        ↓  python build_site.py
    articles/news*.html

**只讀得懂最新那一代格式**（含 class="paper" 的那批，2026-08-16 起）。
更早的檔案前後改過十幾種版型，各自要一套解析，作者指定不處理。
遇到解析不完整的會列出來並跳過，不會塞半空的條目進網站。

以 DOI 當唯一鍵：重跑不會產生重複，已經在 news.json 裡的不會被覆寫
（手改過的內容不會被機器蓋掉）。要強制更新某篇就先從 news.json 刪掉它。

    python import_digests.py                  預覽會匯入什麼，不寫檔
    python import_digests.py --write          真的寫進 news.json
    python import_digests.py --only 2026-09-07 [--only …]
                                              只看指定日期的摘要檔

`--only` 是給 Telegram 那條「某月某日可上線」用的：作者審過哪一天就上哪一天，
不要一次把所有還沒上的都掃進去。沒給 --only 就是全部（原本的行為）。

2026-09-07 起作者的做法是**每日三篇一律上網站**，不再逐篇挑。
所以這支變成每天要跑的一步，整套是：

    python import_digests.py --write
    python build_site.py
    python bump_assets.py
    python check_site.py
    git add -A && git commit && git push

要拿掉某一篇就從 news.json 刪掉它，再跑一次 build_site.py；
刪掉之後這支會把它當成新的重新匯入，所以順手也要把那個 DOI
留在 nephrology_digest/scripts/daily_covered.json 裡（別跑 sync_covered.py，
那支會照網站重建帳本，等於允許它明天再被挑一次）。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DIGEST = Path.home() / "nephrology_digest"
OUT = ROOT / "articles_src" / "news.json"

spec = importlib.util.spec_from_file_location("pd", ROOT / "pick_digest.py")
pd = importlib.util.module_from_spec(spec)
sys.modules["pd"] = pd
spec.loader.exec_module(pd)

# 期刊縮寫正規化。網站上顯示的標籤要一致，
# 同一本期刊在摘要裡出現過 "KI"、"Kidney Int"、"Kidney International"。
JOURNAL = {
    "THE LANCET": "THE LANCET", "LANCET": "THE LANCET",
    "NEJM": "NEJM", "JAMA": "JAMA", "BMJ": "BMJ", "NATURE": "NATURE",
    "NATURE MEDICINE": "NATURE MEDICINE", "NATURE MED": "NATURE MEDICINE",
    "NAT MED": "NATURE MEDICINE",
    "KI": "KIDNEY INT", "KIDNEY INT": "KIDNEY INT",
    "KIDNEY INTERNATIONAL": "KIDNEY INT",
    "KI REPORTS": "KI REPORTS", "KIDNEY INT REPORTS": "KI REPORTS",
    "JASN": "JASN", "CJASN": "CJASN", "AJKD": "AJKD", "NDT": "NDT",
    "KIDNEY MED": "KIDNEY MED", "CKJ": "CKJ",
}

# 主題判定。**順序有意義**：由窄到寬，先命中的贏。
# 例如「IgA 腎病變合併糖尿病」應該歸 IgA，不是糖尿病腎病變。
# 五個標籤，和 build_site.py 的 NEWS_CATS 用同一組中文字串。
# **順序有意義**：由窄到寬，先命中的贏。
# 心衰竭、肥胖、代謝症候群這一類跨器官的歸 CKM，那正是這個名詞的用意。
TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    # CKM 先判：它是傘狀概念，肥胖／脂肪肝／跨器官代謝的歸這裡。
    ("心腎糖肝代謝症候群", ("CKM", "cardiovascular-kidney-metabolic",
                            "代謝症候群", "metabolic syndrome",
                            "肥胖", "obesity", "體重", "weight",
                            "脂肪肝", "MASLD", "NAFLD", "MAFLD")),
    # 心臟本身的疾病與終點歸心血管疾病，不要被 CKM 全部吸走
    ("心血管疾病", ("心衰", "heart failure", "射血分數", "ejection fraction",
                    "心肌梗塞", "myocardial infarction", "冠狀動脈",
                    "coronary", "心房顫動", "atrial fibrillation",
                    "中風", "stroke", "瓣膜", "valv")),
    ("高血脂", ("血脂", "膽固醇", "lipid", "cholesterol", "statin",
                "LDL", "動脈硬化", "atheroscleros")),
    ("高血壓", ("血壓", "hypertens", "blood pressure", "醛固酮",
                "aldosteron")),
    ("糖尿病", ("糖尿病", "diabet", "SGLT2", "GLP-1", "gliflozin",
                "glutide", "血糖", "glycemic", "HbA1c")),
    # 最寬的放最後：前面全部沒中才落到這裡
    ("腎臟疾病", ("腎", "kidney", "renal", "透析", "dialysis", "eGFR",
                  "蛋白尿", "albuminuria", "nephro", "IgA", "移植",
                  "transplant", "AKI")),
]


# 頂尖綜合期刊才進網站；專科期刊（KI Reports、CJASN、NDT、AJKD…）不進。
# 2026-09-09 加入 Nature／Nature Medicine（每日摘要同步加入搜尋這兩本，
# 限臨床／轉譯型研究）。
ALLOWED_JOURNALS = {"NEJM", "THE LANCET", "JAMA", "NATURE", "NATURE MEDICINE"}

# 每日摘要改成也只搜這三本的第一天（digest_prompt.txt 於 2026-09-05 晚間改，
# 隔天的排程才是第一份照新規則產的）。這一天之後的摘要，三篇理應全部收得進來；
# 收不進來會在報表最後單獨列出來。更早的檔案還混著專科期刊，被擋掉是正常的。
NEW_RULES_FROM = "2026-09-06"


def guess_topic(zh: str, en: str) -> str:
    hay = (zh + " " + en).lower()
    for topic, kws in TOPIC_RULES:
        if any(k.lower() in hay for k in kws):
            return topic
    return ""


def pub_date(byline: str, fallback: str) -> str:
    """從出處行取發表日期。用發表日、不是摘要產生日——
    同一天的摘要可能收前幾天發表的文章，排序要照發表日才對。"""
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", byline)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(20\d\d)[-/](\d{1,2})[-/](\d{1,2})", byline)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 只有年份的引用格式：N Engl J Med 2020;383:240-251。
    # 回退到「摘要產生日」很危險——2020 年的 STARRT-AKI 會被標成今天，
    # 排在最上面變成「最新研究」，首頁那張卡也會選到它。
    # \b 兩側都要邊界，所以 PMID 42684836、DOI 裡的 NEJMoa2000741
    # 這種夾在長數字或字母中間的四位數不會被誤認。
    # 取第一個而不是最大的：引用格式裡發表年在最前面，後面的頁碼
    # 可能長得像年份（…2015;372:2010-2020 的 2010、2020 都是頁碼）。
    m = re.search(r"\b(19\d\d|20[0-3]\d)\b", byline)
    if m:
        return m.group(1)
    return fallback


def convert(e: dict, filedate: str) -> dict | str:
    """一篇摘要 → 網站的資料結構。不能收的回傳「原因」字串。

    2026-09-07 起作者的做法是「每日三篇一律上網站」，所以「這篇沒進來」
    變成一件需要被看見的事。原本兩種情況都回 None，在報表上混成同一堆
    「欄位不全」，期刊不對被擋掉的看起來像解析失敗。
    """
    zh, doi = e["zh"], e["doi"]
    if not zh or not doi:
        return "缺標題或 DOI"
    journal = JOURNAL.get(e["jtag"].upper().strip(), e["jtag"].upper().strip())
    if journal not in ALLOWED_JOURNALS:
        return f"期刊不收（{journal or '標籤空白'}）"
    q = pd.pick_key(e["kp"], "問題", "Question")
    f = pd.pick_key(e["kp"], "發現", "Findings")
    m = pd.pick_key(e["kp"], "意義", "Meaning")
    # 「意義」是網站上唯一會出現在首頁的那一段，沒有它這篇就沒有價值
    if not m:
        return "缺「意義 Meaning」"
    d = {
        "journal": journal,
        "date": pub_date(e["byline"], filedate),
        "topic": guess_topic(zh, e["en"]),
        "zh": zh,
        "en": e["en"],
        "cite": e["byline"],
        "url": f"https://doi.org/{doi}",
        "doi": doi,
        "q": q, "f": f, "m": m,
        "bg": pd.pick_key(e["secs"], "背景", "BACKGROUND"),
        "me": pd.pick_key(e["secs"], "方法", "METHODS"),
        "r": e["items"],
        "sig": e["clin"],
        "lim": re.sub(r"^(限制性?|侷限性?)[：:]\s*", "", e["limit"]),
    }
    return {k: v for k, v in d.items() if v}


def wanted_dates(argv: list[str]) -> set[str]:
    """--only 2026-09-07 可重複。空集合＝不限制。"""
    out = set()
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            d = argv[i + 1].strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                sys.exit(f"--only 的日期要寫成 YYYY-MM-DD，收到：{d}")
            out.add(d)
    return out


def main() -> int:
    write = "--write" in sys.argv
    only = wanted_dates(sys.argv)
    if not DIGEST.is_dir():
        sys.exit(f"找不到 {DIGEST}")

    old = []
    if OUT.exists():
        old = json.loads(OUT.read_text("utf-8"))
    have = {x.get("doi") or x.get("url") for x in old}

    files = [f for f in sorted(DIGEST.glob("nephrology_daily_*.html"))
             if 'class="paper"' in f.read_text("utf-8", "replace")]
    if only:
        files = [f for f in files if f.stem[-10:] in only]
        missing = only - {f.stem[-10:] for f in files}
        if missing:
            # 檔案不存在、或存在但是舊版型（沒有 class="paper"）——
            # 兩種都不能默默當成「那天沒東西」，會讓人以為已經上線了。
            sys.exit("這些日期沒有可解析的摘要檔：" + "、".join(sorted(missing)))
    if not files:
        sys.exit("沒有符合條件的摘要檔")
    print(f"最新格式的檔案 {len(files)} 份"
          f"（{files[0].stem[-10:]} … {files[-1].stem[-10:]}）"
          + ("　※ 只看 " + "、".join(sorted(only)) if only else ""))
    print(f"news.json 現有 {len(old)} 篇\n")

    new, skipped, dup = [], [], 0
    for f in files:
        fd = f.stem[-10:]
        for e in pd.parse(f):
            d = convert(e, fd)
            if isinstance(d, str):
                skipped.append((fd, d, (e["zh"] or "（無標題）")[:34]))
                continue
            if d["doi"] in have:
                dup += 1
                continue
            have.add(d["doi"])
            new.append(d)

    new.sort(key=lambda x: x["date"], reverse=True)
    print(f"可匯入 {len(new)} 篇　已存在略過 {dup} 篇　收不了 {len(skipped)} 篇")

    if skipped:
        from collections import Counter
        print("\n收不了的，依原因分組")
        for why, n in Counter(w for _fd, w, _t in skipped).most_common():
            print(f"  ── {why}　{n} 篇")
            for fd, w, t in skipped:
                if w == why:
                    print(f"       {fd}　{t}")

    # 現在的做法是「每日三篇一律上網站」，所以有東西沒收進來就是要處理的事。
    # 但只從新規則生效那天起算：更早的摘要還在收專科期刊（JASN、CJASN、
    # KI Reports…），那些被擋掉是預期的，每次都跳出來喊只會變成雜訊。
    hot = [(fd, w, t) for fd, w, t in skipped if fd >= NEW_RULES_FROM]
    if hot:
        print(f"\n⚠ {NEW_RULES_FROM} 之後有 {len(hot)} 篇沒收進來："
              "現在的規則是每日三篇一律上網站，這幾篇要看一下")
        for fd, w, t in hot:
            print(f"    {fd}　{w}　{t}")

    from collections import Counter
    tc = Counter(x.get("topic") or "（未分類）" for x in new)
    print("\n主題分布")
    for t, n in tc.most_common():
        print(f"  {t or '（未分類）':<14}{n}")
    jc = Counter(x["journal"] for x in new)
    print("\n期刊分布")
    for j, n in jc.most_common():
        print(f"  {j:<16}{n}")

    if not write:
        print("\n這是預覽，沒有寫檔。確定的話加 --write")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged = new + old          # 新的排前面
    merged.sort(key=lambda x: x.get("date", ""), reverse=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n寫入 {OUT}　共 {len(merged)} 篇")
    print("接著跑：python build_site.py && python bump_assets.py"
          " && python check_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
