# -*- coding: utf-8 -*-
"""把衛福部食藥署的「台灣食品營養成分資料庫」轉成查詢工具用的精簡 JSON。

資料來源：政府資料開放平臺 dataset 8543
  https://data.fda.gov.tw/data/opendata/export/20/csv
授權：政府資料開放授權條款 第 1 版

原始檔是「長格式」（每列一個 食品×營養素 配對，22 萬列 / 62 MB），
這裡樞紐轉置成每種食品一列，只保留腎臟病飲食關心的五個欄位。

用法：
    python build_food_db.py path\to\20_2.csv
輸出：food_db.json（給 food.html 前端載入）
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "food_db.json"

# 只取這五項。腎臟病飲食衛教實務上就是看這幾個：
#   鈉—所有 CKD 與高血壓；鉀、磷—中晚期與透析；蛋白質—依分期而定（早期限制、透析增加）
WANT = {
    "鈉": "na",
    "鉀": "k",
    "磷": "p",
    "粗蛋白": "prot",
    "修正熱量": "kcal",
}


def num(s: str):
    """含量欄可能是空的、帶括號或有 '<' 之類的符號，取不到數字就回 None。"""
    if not s:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return round(float(m.group()), 1) if m else None


def clean_alias(s: str) -> str:
    """俗名欄是逗號分隔，去重並限制長度——它只是給搜尋用的，不必全塞進前端。"""
    if not s:
        return ""
    seen, out = set(), []
    for a in re.split(r"[,，、;；]", s):
        a = a.strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return ",".join(out[:6])


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = Path(sys.argv[1])
    if not src.exists():
        print(f"找不到檔案：{src}")
        return 1

    foods: dict[str, dict] = {}
    vals: dict[str, dict] = defaultdict(dict)

    with io.open(src, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            fid = row["整合編號"]
            if fid not in foods:
                foods[fid] = {
                    "name": row["樣品名稱"].strip(),
                    "alias": clean_alias(row.get("俗名", "")),
                    "cat": row["食品分類"].strip(),
                }
            key = WANT.get(row["分析項"].strip())
            if key:
                v = num(row.get("每100克含量", ""))
                if v is not None:
                    vals[fid][key] = v

    # 依「基本名稱」分組。
    #
    # 原始資料是學術取樣紀錄，同一種食物常有多筆：
    #   北蕉(0天,綠皮) 鉀 363 / 北蕉(11月取樣) 鉀 463
    # 直接列出來，使用者搜「香蕉」會看到十幾筆近乎重複、還帶著「11月取樣」
    # 這種對民眾沒意義的註記。但那些數值差異是真實的，隨便挑一筆等於捏造精確度。
    #
    # 所以：去掉括號註記後分組，數值取範圍（min–max）。既好讀，也誠實地
    # 呈現「同一種食物本來就有變異」這件事。
    groups: dict[tuple, dict] = {}
    for fid, meta in foods.items():
        v = vals.get(fid, {})
        if not any(k in v for k in ("na", "k", "p")):
            continue
        base = re.sub(r"[（(].*?[)）]", "", meta["name"]).strip()
        # 官方資料裡有 88 筆「○○平均值」的彙總列，那不是另一種食物，
        # 去掉字尾讓它併回本體，否則搜「香蕉」會看到「北蕉」和「北蕉平均值」兩筆。
        base = re.sub(r"平均值$", "", base).strip() or meta["name"]
        key = (meta["cat"], base)
        g = groups.setdefault(key, {"alias": set(), "n": 0,
                                    "v": {k: [] for k in ("na", "k", "p", "prot", "kcal")}})
        g["n"] += 1
        for a in meta["alias"].split(","):
            if a:
                g["alias"].add(a)
        for k, lst in g["v"].items():
            if k in v:
                lst.append(v[k])

    def rng(lst):
        """回傳 [代表值, 最小, 最大]；只有一筆或差異很小時只給代表值。"""
        if not lst:
            return None
        lo, hi = min(lst), max(lst)
        mid = round(sum(lst) / len(lst), 1)
        if len(lst) == 1 or hi - lo < max(1, hi * 0.08):
            return [mid]
        return [mid, lo, hi]

    # 用字變體。資料庫寫「土司」，民眾打「吐司」就查不到——同一個東西、
    # 不同寫法而已。只收錄字面變體，不做「A 可以代替 B」這種語意判斷。
    VARIANTS = {
        "土司": "吐司", "蕃茄": "番茄", "馬鈴薯": "洋芋", "花椰菜": "花耶菜",
        "鳳梨": "菠蘿", "高麗菜": "包心菜", "地瓜": "番薯", "玉米": "玉蜀黍",
    }

    rows = []
    for (cat, base), g in groups.items():
        extra = {v for k, v in VARIANTS.items() if k in base}
        extra |= {k for k, v in VARIANTS.items() if v in base}
        alias = ",".join(sorted(g["alias"] | extra)[:8])
        rows.append([base, alias, cat, g["n"]] +
                    [rng(g["v"][k]) for k in ("na", "k", "p", "prot", "kcal")])

    rows.sort(key=lambda r: (r[2], r[0]))
    cats = sorted({r[2] for r in rows})

    payload = {
        "source": "衛生福利部食品藥物管理署 台灣食品營養成分資料庫",
        "source_url": "https://data.gov.tw/dataset/8543",
        "licence": "政府資料開放授權條款 第 1 版",
        "unit": "每 100 公克可食部分",
        # 數值欄位為 [代表值] 或 [代表值, 最小, 最大]
        "fields": ["name", "alias", "cat", "samples", "na", "k", "p", "prot", "kcal"],
        "cats": cats,
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")

    have = lambda i: sum(1 for r in rows if r[i])
    ranged = sum(1 for r in rows if r[4] and len(r[4]) > 1)
    print(f"食品 {len(rows):,} 種（原始 {len(foods):,} 筆取樣，已依基本名稱分組）")
    print(f"  分類 {len(cats)} 類　有鈉 {have(4):,}　有鉀 {have(5):,}　有磷 {have(6):,}"
          f"　有蛋白質 {have(7):,}　有熱量 {have(8):,}")
    print(f"  鈉值呈現為範圍者 {ranged:,} 種（同名多次取樣且差異大於 8%）")
    print(f"輸出 {OUT.name}：{OUT.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
