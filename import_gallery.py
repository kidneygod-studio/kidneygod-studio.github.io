"""把 Threads 備份裡的衛教圖匯入網站。

來源：kidneygod_social 的備份與 LLM 分類結果（只取判定為衛教的貼文）。
輸出：gallery/ 底下的縮圖與大圖，加上 manifest.json 供 build_site.py 產生頁面。

為什麼要重新壓縮：原圖多為 1024–3072px、平均 200KB，一頁放上百張會爆掉。
縮圖只需 360px、大圖 1000px 就足夠，同時一併清掉 EXIF。

用法：
    python import_gallery.py            # 增量（已存在的檔案跳過）
    python import_gallery.py --force    # 全部重新產生
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
BACKUP = Path(r"C:\Users\user\kidneygod_social\data\threads")
SRC_MEDIA = BACKUP / "media"

OUT = ROOT / "gallery"
THUMB = OUT / "thumb"
MANIFEST = OUT / "manifest.json"

THUMB_W, THUMB_Q = 360, 78
FULL_W, FULL_Q = 1000, 82

# 系列名稱在貼文裡寫法不一致（護腎健康教室Pro / ProDay / pro—Day / 護腎進階計畫…），
# 這裡把它們正規化回同一個系列。順序有意義：先比對 Pro，再比對非 Pro，
# 否則「護腎健康教室Pro」會被「護腎健康教室」先攔截。
SERIES_RULES = [
    (r"三高(健康|進階|衛教)?\s*教室\s*[Pp]ro", "三高健康教室 Pro", "metabolic-pro"),
    (r"護腎(健康|進階)?\s*(教室|計畫)\s*[Pp]ro", "護腎健康教室 Pro", "kidney-pro"),
    # 護腎進階計畫是同一個系列的另一種寫法（作者確認）
    (r"護腎進階計畫", "護腎健康教室 Pro", "kidney-pro"),
    # 【護腎健康教室 Day 2】這種漏打 Pro 的，Day 4 之後都標了 Pro，歸同一系列
    (r"【\s*護腎健康教室\s*[Dd]ay", "護腎健康教室 Pro", "kidney-pro"),
    (r"三高(健康|衛教)?\s*教室\s*[—–-]\s*[Dd]ay", "三高健康教室", "metabolic"),
    (r"三高知識小教室", "三高健康教室", "metabolic"),
    (r"護腎陪伴日常", "護腎陪伴日常", "companion"),
    # 開頭可能有 📌 之類的裝飾字元，所以先允許少量非文字字元
    (r"^[\s\W]{0,4}[Dd]ay\s*\d+\s*[：:]", "腎臟健康教室", "kidney"),
]

# 內文完全沒寫「Day N」的貼文（早期只把編號放在圖片裡），只能人工對應。
# key 是 Threads 貼文 id，值是 (系列, Day)。
MANUAL_SERIES = {
    "17955075309132469": ("腎臟健康教室", 1),   # 代謝症候群篩檢
    "18075115397279817": ("腎臟健康教室", 2),   # 血壓控制標準
}

# 總覽與各頁的排列順序
SERIES_ORDER = ["腎臟健康教室", "護腎健康教室 Pro", "三高健康教室",
                "三高健康教室 Pro", "護腎陪伴日常", "其他"]

SERIES_INTRO = {
    "腎臟健康教室": "最早的一輪護腎衛教，從最基本的觀念開始，一天一個主題。",
    "護腎健康教室 Pro": "進階版，依據 KDIGO 指引逐日展開：藥物四大支柱、飲食個人化、"
                        "併發症處理，一路走到腎臟替代治療的提前規劃。",
    "三高健康教室": "高血壓、高血糖、高血脂的基礎觀念與日常控制。",
    "三高健康教室 Pro": "進階版，從最新指引的分類、診斷標準到心血管風險評估工具。",
    "護腎陪伴日常": "日常生活裡的護腎提醒，輕鬆一點的一系列。",
    "其他": "沒有歸入固定系列的單篇衛教圖。",
}


def detect_series(text: str, post_id: str = "") -> tuple[str, str, int | None]:
    """回傳 (系列名稱, 網址代稱, Day 編號)。抓不到系列就歸「其他」。"""
    if post_id in MANUAL_SERIES:
        name, day = MANUAL_SERIES[post_id]
        slug = next((s for pat, nm, s in SERIES_RULES if nm == name), "others")
        return name, slug, day

    t = (text or "").strip()
    name, slug = "其他", "others"
    for pat, nm, sl in SERIES_RULES:
        if re.search(pat, t):
            name, slug = nm, sl
            break
    m = re.search(r"[Dd]ay\s*(\d+)", t) or re.search(r"第\s*(\d+)\s*天", t)
    return name, slug, int(m.group(1)) if m else None


def save_optimised(src: Path, dst: Path, width: int, quality: int) -> tuple[int, int]:
    """縮放並移除中繼資料。回傳輸出尺寸。"""
    im = ImageOps.exif_transpose(Image.open(src))
    if im.mode != "RGB":
        im = im.convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    clean = Image.new("RGB", im.size)
    clean.putdata(list(im.getdata()))
    dst.parent.mkdir(parents=True, exist_ok=True)
    clean.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    return clean.size


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    posts = json.loads((BACKUP / "posts.json").read_text(encoding="utf-8"))["posts"]
    labels_path = BACKUP / "media_labels.json"
    if not labels_path.exists():
        print("找不到 media_labels.json，請先執行 kidneygod_social/scripts/classify_media.py")
        return 1
    labels = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]

    if args.force and OUT.exists():
        shutil.rmtree(OUT)

    entries, skipped_new, reused = [], 0, 0
    for pid, meta in labels.items():
        if not meta.get("edu") or not meta.get("cat"):
            continue
        p = posts.get(pid)
        if not p:
            continue
        files = [f for f in (p.get("media_files") or []) if not f.lower().endswith(".mp4")]
        for idx, fname in enumerate(files):
            src = SRC_MEDIA / fname
            if not src.exists():
                continue
            stem = Path(fname).stem
            full_p, thumb_p = OUT / f"{stem}.jpg", THUMB / f"{stem}.jpg"

            if full_p.exists() and thumb_p.exists():
                with Image.open(full_p) as im:
                    fw, fh = im.size
                reused += 1
            else:
                fw, fh = save_optimised(src, full_p, FULL_W, FULL_Q)
                save_optimised(src, thumb_p, THUMB_W, THUMB_Q)
                skipped_new += 1

            cap = meta.get("cap") or (p.get("text") or "")[:24]
            # 同一則貼文有多張圖時，在圖說後面標序號以免重複
            if len(files) > 1:
                cap = f"{cap}（{idx + 1}/{len(files)}）"

            s_name, s_slug, s_day = detect_series(p.get("text") or "", pid)

            entries.append({
                "id": stem, "cat": meta["cat"], "cap": cap,
                "series": s_name, "series_slug": s_slug, "day": s_day,
                # 原始貼文全文一併帶進來：它是圖片的說明，
                # 同時也是網站目前完全沒有的原創文字內容
                "text": (p.get("text") or "").strip(),
                "full": f"gallery/{stem}.jpg", "thumb": f"gallery/thumb/{stem}.jpg",
                "w": fw, "h": fh,
                "date": (p.get("timestamp") or "")[:10],
                "permalink": p.get("permalink") or "",
            })

    # 系列內依 Day 編號排序（沒編號的排最後、按日期），才讀得出課程順序
    order = {s: i for i, s in enumerate(SERIES_ORDER)}
    # 人工補充的圖：有些貼文先發在 IG 再分享到 Threads，Threads API 只看到文字，
    # 圖片抓不到。這些由 manual_media.json 指定圖檔，文字仍取自備份。
    mm_path = ROOT / "manual_media.json"
    if mm_path.exists():
        mm = json.loads(mm_path.read_text(encoding="utf-8")).get("cards", [])
        have = {e["id"].rsplit("_", 1)[0] for e in entries}
        added = 0
        for c in mm:
            pid = c["post_id"]
            if pid in have:
                continue
            p = posts.get(pid)
            if not p:
                print(f"  ! 跳過人工補充 {pid}：備份裡找不到這則貼文")
                continue
            # file 省略時，代表圖片其實在備份裡（只是被分類器排除），直接沿用
            if c.get("file"):
                src = ROOT / "manual_media" / c["file"]
                if not src.exists():
                    print(f"  ! 跳過人工補充 {pid}：找不到圖檔 {c['file']}")
                    continue
            else:
                own = [f for f in (p.get("media_files") or [])
                       if not f.lower().endswith(".mp4")]
                if not own:
                    print(f"  ! 跳過人工補充 {pid}：備份裡也沒有圖，需要提供 file")
                    continue
                src = SRC_MEDIA / own[0]
            stem = f"{pid}_m0"
            full_p, thumb_p = OUT / f"{stem}.jpg", THUMB / f"{stem}.jpg"
            if args.force or not (full_p.exists() and thumb_p.exists()):
                fw, fh = save_optimised(src, full_p, FULL_W, FULL_Q)
                save_optimised(src, thumb_p, THUMB_W, THUMB_Q)
            else:
                with Image.open(full_p) as im:
                    fw, fh = im.size
            entries.append({
                "id": stem, "cat": "", "cap": c["cap"],
                "series": c["series"],
                "series_slug": next((s for _p, nm, s in SERIES_RULES
                                     if nm == c["series"]), "others"),
                "day": c.get("day"),
                # text_override：圖片改過時，文字要一起改，否則兩邊說法不一致
                "text": (c.get("text_override") or (p.get("text") or "")).strip(),
                "full": f"gallery/{stem}.jpg", "thumb": f"gallery/thumb/{stem}.jpg",
                "w": fw, "h": fh,
                "date": (p.get("timestamp") or "")[:10],
                "permalink": p.get("permalink") or "",
            })
            added += 1
        if added:
            print(f"人工補充圖片：{added} 張")

    entries.sort(key=lambda e: (order.get(e["series"], 99),
                                e["day"] if e["day"] is not None else 9999,
                                e["date"]))
    MANIFEST.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")

    # 系列的中繼資料另存一份，build_site.py 直接讀，不必兩邊各維護一份名單
    seen: dict[str, dict] = {}
    for e in entries:
        s = seen.setdefault(e["series"], {
            "name": e["series"], "slug": e["series_slug"],
            "intro": SERIES_INTRO.get(e["series"], ""), "count": 0, "days": [],
        })
        s["count"] += 1
        if e["day"]:
            s["days"].append(e["day"])
    series = []
    for name in SERIES_ORDER:
        if name in seen:
            s = seen[name]
            d = sorted(s.pop("days"))
            s["day_range"] = f"Day {d[0]}–{d[-1]}" if d else ""
            series.append(s)
    (OUT / "series.json").write_text(
        json.dumps(series, ensure_ascii=False, indent=1), encoding="utf-8")

    total_mb = sum(f.stat().st_size for f in OUT.rglob("*.jpg")) / 1024 / 1024
    print(f"新產生 {skipped_new} 張、沿用 {reused} 張")
    print(f"manifest：{len(entries)} 筆　gallery 目錄合計 {total_mb:.1f} MB")

    from collections import Counter
    print("\n依系列：")
    by_s = Counter(e["series"] for e in entries)
    for s in SERIES_ORDER:
        if not by_s.get(s):
            continue
        days = sorted(e["day"] for e in entries if e["series"] == s and e["day"])
        rng = f"Day {days[0]}–{days[-1]}" if days else "無編號"
        missing = ([d for d in range(days[0], days[-1] + 1) if d not in days]
                   if days else [])
        gap = f"　缺 Day {','.join(map(str, missing))}" if missing else ""
        print(f"  {s:<16}{by_s[s]:>4} 張　{rng}{gap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
