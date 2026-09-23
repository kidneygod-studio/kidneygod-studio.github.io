# -*- coding: utf-8 -*-
"""把後台按下的審閱紀錄抓回 articles_src/reviewed.json。

    admin.html（作者按「今天已審閱」）
        ↓  寫進 Firestore 的 review 集合
    python sync_reviews.py
        ↓
    articles_src/reviewed.json  →  build_site.py 才會把日期印在頁面上

為什麼要有這一層：網站是靜態的，Firestore 那筆紀錄不會自己變成 HTML。
作者在醫院用網頁按完之後，要有人跑這支再重新建站，日期才會出現。

為什麼用 REST 而不是 SDK：review 集合本來就是公開讀取（審閱日期是要印在
頁面上給讀者看的資訊，不是秘密），所以不需要任何憑證，一個 GET 就夠。

⚠ 這支只會「新增或更新」，不會刪掉 reviewed.json 裡雲端沒有的鍵——
  手動補過的日期不會被洗掉。真的要移除某一頁的紀錄請自己編輯那個檔。

用法：
    python sync_reviews.py            # 寫入
    python sync_reviews.py --dry-run  # 只看會變動什麼，不寫檔
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")   # 排程是 cp950，印中文以外的符號會炸

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "articles_src" / "reviewed.json"
PROJECT = "kidneygod-ea61e"
KEY = "AIzaSyCbwPTuDOYdE1TjTd7pzLI6GUXCOPpgJNU"     # 前端公開識別碼，非機密
URL = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
       f"/databases/(default)/documents/review?key={KEY}&pageSize=300")


def fetch() -> dict[str, str]:
    """回傳 {網站相對路徑: YYYY-MM-DD}。"""
    out: dict[str, str] = {}
    url = URL
    while True:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"讀取失敗（HTTP {e.code}）：{e.reason}")
        except Exception as e:                       # noqa: BLE001
            sys.exit(f"讀取失敗：{e}")
        for d in data.get("documents", []):
            f = d.get("fields", {})
            path = f.get("path", {}).get("stringValue")
            date = f.get("date", {}).get("stringValue")
            if path and date:
                out[path] = date
        token = data.get("nextPageToken")
        if not token:
            return out
        url = URL + "&pageToken=" + token


def main() -> None:
    dry = "--dry-run" in sys.argv
    cloud = fetch()
    if not cloud:
        print("雲端還沒有任何審閱紀錄。")
        return

    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            sys.exit(f"{OUT.name} 不是合法的 JSON，先修好再跑這支。")

    added = {k: v for k, v in cloud.items() if k not in old}
    changed = {k: (old[k], v) for k, v in cloud.items() if k in old and old[k] != v}

    for k, v in sorted(added.items()):
        print(f"  新增  {k}  {v}")
    for k, (a, b) in sorted(changed.items()):
        print(f"  更新  {k}  {a} → {b}")
    if not added and not changed:
        print(f"沒有變動（雲端 {len(cloud)} 筆，本機已是最新）。")
        return

    if dry:
        print(f"\n--dry-run：沒有寫檔。實際會變動 {len(added) + len(changed)} 筆。")
        return

    merged = dict(old)
    merged.update(cloud)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(f"\n已寫入 {OUT.relative_to(ROOT)}（共 {len(merged)} 筆）。")
    print("接著跑：python build_site.py && python bump_assets.py && python check_site.py")


if __name__ == "__main__":
    main()
