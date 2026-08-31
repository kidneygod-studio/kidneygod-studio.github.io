# -*- coding: utf-8 -*-
"""把第二批 40 張知識卡插圖收進 gi/art/。

來源：Downloads/知識卡插圖/知識卡插圖2/61.jpg … 100.jpg
對應：檔案編號 61..100 依序對到 GI插圖_新增40張_Prompt.txt 裡的第 1..40 段，
      卡片 id 取自每段的「檔名：gi/art/<id>.png」。

為什麼要用 prompt 檔而不是憑編號猜：61.jpg 是腳踝水腫，但卡片陣列的第 61
張是「血壓計袖帶」，兩者無關——檔案編號跟卡片順序本來就不一致。用 prompt
檔對應之後，另外用兩個獨立證據確認過：
  1. 缺插圖的 40 張卡，正好等於這份 prompt 的 40 筆，且與現有 60 張零重疊
  2. 61.jpg（腳踝水腫）對到 bp-ccb-edema、100.jpg（腰痠）對到 shenkui，圖文相符

輸出規格對齊現有的 60 張：1560x871 JPEG。原圖 2752x1536 是同樣的 16:9，
所以只縮放不裁切；順便重存以去掉 EXIF。
"""
import os
import re
import sys

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"C:\Users\user\Downloads\知識卡插圖\知識卡插圖2"
PROMPT = "GI插圖_新增40張_Prompt.txt"
ART_DIR = "gi/art"
SIZE = (1560, 871)          # 與既有 60 張相同
FIRST, LAST = 61, 100
QUALITY = 82                # 既有檔案落在 120–230 KB，這個品質相當


def main() -> int:
    ids = re.findall(r"檔名：gi/art/([A-Za-z0-9_-]+)\.png",
                     open(PROMPT, encoding="utf-8").read())
    expect = LAST - FIRST + 1
    if len(ids) != expect:
        print(f"中止：prompt 檔有 {len(ids)} 筆，預期 {expect} 筆")
        return 1

    existing = {os.path.splitext(f)[0] for f in os.listdir(ART_DIR)}

    # 先全部檢查過再動手，避免寫到一半才發現有問題
    plan = []
    for n in range(FIRST, LAST + 1):
        src = os.path.join(SRC, f"{n}.jpg")
        cid = ids[n - FIRST]
        if not os.path.exists(src):
            print(f"中止：找不到 {src}")
            return 1
        if cid in existing:
            print(f"中止：{cid} 已經有插圖了，不覆蓋既有的 60 張")
            return 1
        plan.append((n, src, cid))

    total = 0
    for n, src, cid in plan:
        im = Image.open(src)
        w, h = im.size
        # 長寬比差 1% 以內就直接縮放；差太多要先裁切，這裡不該發生
        if abs(w / h - SIZE[0] / SIZE[1]) > 0.02:
            print(f"  ！{n}.jpg 比例 {w}x{h} 與預期不符，置中裁切")
            tw = int(h * SIZE[0] / SIZE[1])
            im = im.crop(((w - tw) // 2, 0, (w + tw) // 2, h))
        im = im.convert("RGB").resize(SIZE, Image.LANCZOS)
        out = os.path.join(ART_DIR, f"{cid}.jpg")
        im.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        kb = os.path.getsize(out) / 1024
        total += kb
        print(f"  {n:>3}.jpg → {cid + '.jpg':<26}{kb:>6.0f} KB")

    print(f"\n匯入 {len(plan)} 張，合計 {total / 1024:.1f} MB")
    print(f"gi/art 現有 {len(os.listdir(ART_DIR))} 張")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
