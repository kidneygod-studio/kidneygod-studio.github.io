# -*- coding: utf-8 -*-
"""把外部畫好的插圖（1.jpg ~ 60.jpg）收進 gi/art/，檔名換成卡片 id。

編號對應 make_gi_prompts.py 印出來的順序（分類排序後的 01~60），
兩支程式用的是同一套排序，改動排序規則時請一起改。

原圖 2752x1536、每張 2 MB 以上，但插圖區只有 780x432，
存進 repo 會白白撐大。這裡縮到 2 倍大小（1560x864）另存 JPG，
畫質綽綽有餘，體積差一個量級。
"""
import os, sys, json

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"C:\Users\user\Downloads\知識卡插圖"
DST = "gi/art"
LONG_EDGE = 1560          # 插圖區 780 寬的兩倍
QUALITY = 88


def main():
    data = json.load(open("knowledge_export.json", encoding="utf-8"))
    order = ["血壓管理", "血糖管理", "血脂代謝", "檢查數值",
             "用藥安全", "飲食護腎", "生活習慣", "警訊與迷思"]
    data.sort(key=lambda x: (order.index(x["cat"]), -x["price"], x["id"]))

    os.makedirs(DST, exist_ok=True)
    done, missing, tot = 0, [], 0
    for i, item in enumerate(data, 1):
        src = os.path.join(SRC, f"{i}.jpg")
        if not os.path.exists(src):
            missing.append((i, item["id"])); continue
        im = Image.open(src).convert("RGB")
        r = LONG_EDGE / im.width
        if r < 1:
            im = im.resize((LONG_EDGE, round(im.height * r)), Image.LANCZOS)
        out = os.path.join(DST, item["id"] + ".jpg")
        im.save(out, quality=QUALITY, optimize=True, progressive=True)
        tot += os.path.getsize(out); done += 1

    print(f"收進 {done} 張 → {DST}／合計 {tot//1024//1024} MB"
          f"（平均 {tot//max(1,done)//1024} KB）")
    if missing:
        print("⚠ 找不到來源檔:", missing)


if __name__ == "__main__":
    main()
