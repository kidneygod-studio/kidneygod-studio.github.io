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
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")   # 排程是 cp950，印中文以外的符號會炸
# stderr 也要：sys.exit("中文訊息") 寫的是 stderr，只轉 stdout 的話
# 錯誤訊息會變成一堆亂碼——偏偏那正是出事時唯一看得到的東西。
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "articles_src" / "reviewed.json"
NEWS_OUT = ROOT / "articles_src" / "news_reviewed.json"
PROJECT = "kidneygod-ea61e"
KEY = "AIzaSyCbwPTuDOYdE1TjTd7pzLI6GUXCOPpgJNU"     # 前端公開識別碼，非機密
BASE = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
        f"/databases/(default)/documents")


def coll_url(name: str) -> str:
    return f"{BASE}/{name}?key={KEY}&pageSize=300"


URL = coll_url("review")

# 內容由排程自動接上去的頁面（每日新知、衛教圖卡）不收進 reviewed.json。
# build_site.py 的 reviewed_ld() 也擋了一層——那裡是權威，這裡只是不要讓
# 檔案裡躺著一堆不會生效的鍵。雲端那幾筆留著不管（這支沒有刪除權限，
# 而且留著也無害）。理由見 build_site.py 的 AUTO_UPDATED 註解。
AUTO_UPDATED = re.compile(r"^articles/(news|gallery)")


def fetch_coll(name: str, key_field: str, skip=None,
               optional: bool = False) -> dict[str, str]:
    """回傳 {key_field 的值: YYYY-MM-DD}。skip 是要略過的 key 判斷函式。

    optional=True 時，權限不足（403）不算失敗——代表 firestore.rules 裡
    這個集合的規則還沒發布到 Firebase console。這種情況要**講清楚**再繼續，
    不能讓它把另一份已經抓成功的紀錄一起拖垮：兩份是獨立的。
    """
    out: dict[str, str] = {}
    url = coll_url(name)
    while True:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            if optional and e.code in (403, 404):
                print(f"[{name}] 讀不到（HTTP {e.code}）——"
                      f"很可能是 firestore.rules 還沒發布到 Firebase console。"
                      f"這一份先跳過，其餘照常。")
                return {}
            # 集合一筆資料都沒有時 Firestore 回 200 加空物件，不會 404；
            # 真的 404 代表網址打錯，那要讓它響。
            sys.exit(f"讀取 {name} 失敗（HTTP {e.code}）：{e.reason}")
        except Exception as e:                       # noqa: BLE001
            sys.exit(f"讀取 {name} 失敗：{e}")
        for d in data.get("documents", []):
            f = d.get("fields", {})
            key = f.get(key_field, {}).get("stringValue")
            date = f.get("date", {}).get("stringValue")
            if key and date and not (skip and skip(key)):
                out[key] = date
        token = data.get("nextPageToken")
        if not token:
            return out
        url = coll_url(name) + "&pageToken=" + token


def fetch() -> dict[str, str]:
    """回傳 {網站相對路徑: YYYY-MM-DD}。"""
    return fetch_coll("review", "path", skip=AUTO_UPDATED.match)


def sync_one(label: str, cloud: dict[str, str], out: Path, dry: bool) -> bool:
    """把一份雲端紀錄併進本機檔案。回傳有沒有實際變動。"""
    old = {}
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            sys.exit(f"{out.name} 不是合法的 JSON，先修好再跑這支。")

    added = {k: v for k, v in cloud.items() if k not in old}
    changed = {k: (old[k], v) for k, v in cloud.items() if k in old and old[k] != v}

    if not cloud:
        print(f"[{label}] 雲端還沒有任何紀錄。")
        return False
    for k, v in sorted(added.items()):
        print(f"  [{label}] 新增  {k}  {v}")
    for k, (a, b) in sorted(changed.items()):
        print(f"  [{label}] 更新  {k}  {a} → {b}")
    if not added and not changed:
        print(f"[{label}] 沒有變動（雲端 {len(cloud)} 筆，本機已是最新）。")
        return False
    if dry:
        print(f"[{label}] --dry-run：沒有寫檔，實際會變動 "
              f"{len(added) + len(changed)} 筆。")
        return False

    merged = dict(old)
    merged.update(cloud)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(f"[{label}] 已寫入 {out.relative_to(ROOT)}（共 {len(merged)} 筆）。")
    return True


def main() -> None:
    dry = "--dry-run" in sys.argv
    # 兩份分開抓：頁面層級的審閱日期（長文與衛教分類頁），
    # 以及每日新知逐篇的確認。兩者的單位不同，不要混在同一個檔案裡。
    changed = sync_one("頁面審閱", fetch(), OUT, dry)
    changed |= sync_one("新知逐篇",
                        fetch_coll("newsreview", "doi", optional=True),
                        NEWS_OUT, dry)
    if changed:
        print("\n接著跑：python build_site.py && python bump_assets.py "
              "&& python check_site.py")


if __name__ == "__main__":
    main()
