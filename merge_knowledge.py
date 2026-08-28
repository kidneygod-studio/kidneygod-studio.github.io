# -*- coding: utf-8 -*-
"""把 new_knowledge_40.py 的 40 則併入 knowledge_export.json 與 data.js。

**為什麼要寫進兩個檔案**：站上的衛教內容存了兩份且不會互相同步——
knowledge_export.json 給 build_site.py 產生分類頁，data.js 給商城與知識庫。
只改一邊，另一邊會靜默地停留在舊資料，而且沒有任何錯誤訊息。

作法：依分類附加在陣列末尾並加註解標頭。不插進中間，差異才好讀、
也不會動到既有 60 則的任何一個字。

可重複執行：已存在的 id 會自動略過。
執行前會先備份成 *.bak。
"""
from __future__ import annotations

import io
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from new_knowledge_40 import NEW  # noqa: E402

ROOT = Path(__file__).resolve().parent
KE = ROOT / "knowledge_export.json"
DJ = ROOT / "data.js"

CAT_ORDER = ["血壓管理", "血糖管理", "血脂代謝", "檢查數值",
             "用藥安全", "飲食護腎", "生活習慣", "警訊與迷思"]


def js(s: str) -> str:
    """JS 雙引號字串的跳脫。內容裡有反斜線或雙引號時才會用到，但不能不做。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def merge_json() -> int:
    data = json.loads(KE.read_text(encoding="utf-8"))
    have = {x["id"] for x in data}
    added = 0
    for x in NEW:
        if x["id"] in have:
            continue
        data.append({
            "id": x["id"], "cat": x["cat"], "emoji": x["emoji"],
            "brand": x["brand"], "title": x["title"], "body": x["body"],
            "price": x["price"],
        })
        added += 1
    KE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return added


def merge_js() -> int:
    s = DJ.read_text(encoding="utf-8")
    have = set(re.findall(r'\{id:"([^"]+)"', s))
    todo = [x for x in NEW if x["id"] not in have]
    if not todo:
        return 0

    blocks = []
    for cat in CAT_ORDER:
        items = [x for x in todo if x["cat"] == cat]
        if not items:
            continue
        blocks.append(f"\n /* {cat}（2026-08 新增） */")
        for x in items:
            blocks.append(
                f' {{id:"{js(x["id"])}",c:"{js(x["cat"])}",e:"{x["emoji"]}",'
                f'b:"{js(x["brand"])}",n:"{js(x["name"])}",p:{x["price"]},\n'
                f'  k:{{t:"{js(x["title"])}",b:"{js(x["body"])}"}}}},'
            )

    # 插在 PRODUCTS 陣列的收尾 "];" 之前
    start = s.index("const PRODUCTS")
    end = s.index("\n];", start)
    s = s[:end] + "\n" + "\n".join(blocks) + s[end:]
    DJ.write_text(s, encoding="utf-8")
    return len(todo)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    for p in (KE, DJ):
        shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
    print("已備份為 *.bak\n")

    n1 = merge_json()
    n2 = merge_js()
    print(f"knowledge_export.json　新增 {n1} 則")
    print(f"data.js　　　　　　　　新增 {n2} 則")

    # 驗證：兩邊的 id 集合必須完全一致，否則就是又出現不同步
    data = json.loads(KE.read_text(encoding="utf-8"))
    ids_json = {x["id"] for x in data}
    s = DJ.read_text(encoding="utf-8")
    prod = s[s.index("const PRODUCTS"):s.index("\n];", s.index("const PRODUCTS"))]
    ids_js = set(re.findall(r'\{id:"([^"]+)"', prod))

    print(f"\nknowledge_export.json　{len(ids_json)} 則")
    print(f"data.js 的 PRODUCTS　　{len(ids_js)} 則")
    only_json = ids_json - ids_js
    only_js = ids_js - ids_json
    print(f"只在 json：{sorted(only_json) or '無'}")
    print(f"只在 js：　{sorted(only_js) or '無'}")
    return 0 if not (only_json or only_js) else 1


if __name__ == "__main__":
    raise SystemExit(main())
