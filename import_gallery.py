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

            entries.append({
                "id": stem, "cat": meta["cat"], "cap": cap,
                # 原始貼文全文一併帶進來：它是圖片的說明，
                # 同時也是網站目前完全沒有的原創文字內容
                "text": (p.get("text") or "").strip(),
                "full": f"gallery/{stem}.jpg", "thumb": f"gallery/thumb/{stem}.jpg",
                "w": fw, "h": fh,
                "date": (p.get("timestamp") or "")[:10],
                "permalink": p.get("permalink") or "",
            })

    entries.sort(key=lambda e: (e["cat"], e["date"]))
    MANIFEST.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")

    total_mb = sum(f.stat().st_size for f in OUT.rglob("*.jpg")) / 1024 / 1024
    print(f"新產生 {skipped_new} 張、沿用 {reused} 張")
    print(f"manifest：{len(entries)} 筆　gallery 目錄合計 {total_mb:.1f} MB")
    from collections import Counter
    for c, n in Counter(e["cat"] for e in entries).most_common():
        print(f"  {c:<10}{n:>4} 張")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
