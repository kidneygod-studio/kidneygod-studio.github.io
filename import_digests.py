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

    python import_digests.py            預覽會匯入什麼，不寫檔
    python import_digests.py --write    真的寫進 news.json
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DIGEST = Path(r"C:\Users\user\nephrology_digest")
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
    "KI": "KIDNEY INT", "KIDNEY INT": "KIDNEY INT",
    "KIDNEY INTERNATIONAL": "KIDNEY INT",
    "KI REPORTS": "KI REPORTS", "KIDNEY INT REPORTS": "KI REPORTS",
    "JASN": "JASN", "CJASN": "CJASN", "AJKD": "AJKD", "NDT": "NDT",
    "KIDNEY MED": "KIDNEY MED", "CKJ": "CKJ",
}

# 主題判定。**順序有意義**：由窄到寬，先命中的贏。
# 例如「IgA 腎病變合併糖尿病」應該歸 IgA，不是糖尿病腎病變。
TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("IgA 腎病變", ("IgA", "IgAN")),
    ("遺傳性腎病", ("Alport", "多囊", "polycystic", "ADPKD", "基因體", "genom",
                    "genetic", "轉錄體", "transcriptom", "遺傳")),
    ("腎臟移植", ("移植", "transplant", "xenotransplant", "異種",
                  "供腎", "捐腎", "捐贈", "donor")),
    ("急性腎損傷", ("急性腎損傷", "AKI", "acute kidney injury")),
    ("透析", ("透析", "dialysis", "血液透析過濾", "HDF", "腹膜", "peritoneal",
              "血管通路", "廔管", "fistula")),
    ("電解質異常", ("血鉀", "potassium", "血鈉", "sodium", "電解質",
                    "electrolyte", "酸中毒", "acidosis")),
    ("腎絲球腎炎", ("腎絲球", "glomerul", "膜性", "membranous", "FSGS",
                    "狼瘡", "lupus", "血管炎", "vasculitis", "ANCA",
                    "腎病症候群", "nephrotic", "微血管病變", "TMA")),
    ("糖尿病腎病變", ("糖尿病", "diabet", "SGLT2", "GLP-1", "finerenone",
                      "canagliflozin", "dapagliflozin", "empagliflozin",
                      "gliflozin")),
    ("高血壓", ("血壓", "hypertens", "blood pressure")),
    ("血脂與心血管", ("血脂", "膽固醇", "lipid", "statin", "心血管",
                      "cardiovascular", "心衰", "heart failure", "射血分數")),
    ("礦物質與骨病變", ("副甲狀腺", "parathyroid", "磷", "phosphate", "骨",
                        "bone", "鈣化", "calcificat")),
    ("貧血", ("貧血", "anemia", "anaemia", "EPO", "紅血球生成", "鐵劑",
              "iron")),
    ("用藥安全", ("氫離子幫浦", "質子幫浦", "PPI", "腎毒", "nephrotox",
                  "藥物安全", "止痛藥", "NSAID")),
    ("檢查與生物標記", ("生物標記", "biomarker", "蛋白質體", "proteomic",
                        "心電圖", "定序", "sequenc")),
    ("營養", ("營養", "nutrition", "蛋白質攝取", "protein intake", "飲食")),
    ("支持性照護", ("支持性照護", "保守治療", "conservative", "安寧",
                    "palliative", "共享決策", "溝通")),
    # 最寬的放最後：前面全部沒中才落到這裡
    ("慢性腎臟病", ("慢性腎臟病", "CKD", "eGFR", "蛋白尿", "albuminuria",
                    "腎功能", "腎臟病", "kidney disease", "腎臟衰竭",
                    "kidney failure", "腎臟預後")),
]


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
    return fallback


def convert(e: dict, filedate: str) -> dict | None:
    """一篇摘要 → 網站的資料結構。缺關鍵欄位就回 None。"""
    zh, doi = e["zh"], e["doi"]
    if not zh or not doi:
        return None
    q = pd.pick_key(e["kp"], "問題", "Question")
    f = pd.pick_key(e["kp"], "發現", "Findings")
    m = pd.pick_key(e["kp"], "意義", "Meaning")
    # 「意義」是網站上唯一會出現在首頁的那一段，沒有它這篇就沒有價值
    if not m:
        return None
    d = {
        "journal": JOURNAL.get(e["jtag"].upper().strip(),
                               e["jtag"].upper().strip()),
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


def main() -> int:
    write = "--write" in sys.argv
    if not DIGEST.is_dir():
        sys.exit(f"找不到 {DIGEST}")

    old = []
    if OUT.exists():
        old = json.loads(OUT.read_text("utf-8"))
    have = {x.get("doi") or x.get("url") for x in old}

    files = [f for f in sorted(DIGEST.glob("nephrology_daily_*.html"))
             if 'class="paper"' in f.read_text("utf-8", "replace")]
    print(f"最新格式的檔案 {len(files)} 份"
          f"（{files[0].stem[-10:]} … {files[-1].stem[-10:]}）")
    print(f"news.json 現有 {len(old)} 篇\n")

    new, skipped, dup = [], [], 0
    for f in files:
        fd = f.stem[-10:]
        for e in pd.parse(f):
            d = convert(e, fd)
            if d is None:
                skipped.append((fd, e["jtag"], (e["zh"] or "（無標題）")[:34]))
                continue
            if d["doi"] in have:
                dup += 1
                continue
            have.add(d["doi"])
            new.append(d)

    new.sort(key=lambda x: x["date"], reverse=True)
    print(f"可匯入 {len(new)} 篇　已存在略過 {dup} 篇　"
          f"欄位不全略過 {len(skipped)} 篇")

    if skipped:
        print("\n略過的（缺標題／DOI／意義）")
        for fd, j, t in skipped:
            print(f"  {fd}　{j:<12}{t}")

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
