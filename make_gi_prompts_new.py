# -*- coding: utf-8 -*-
"""只輸出「新增 40 則」的生圖 prompt。

make_gi_prompts.py 會輸出全部 100 段（含既有 60 則已經畫好的），
要在裡面找出新的那 40 段很花時間，所以另外產一份。

用法：python make_gi_prompts_new.py
輸出：GI插圖_新增40張_Prompt.txt
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from make_gi_prompts import BG, SCENE, STYLE  # noqa: E402
from new_knowledge_40 import NEW  # noqa: E402

ORDER = ["血壓管理", "血糖管理", "血脂代謝", "檢查數值",
         "用藥安全", "飲食護腎", "生活習慣", "警訊與迷思"]

OUT = Path("GI插圖_新增40張_Prompt.txt")

items = sorted(NEW, key=lambda x: (ORDER.index(x["cat"]), x["id"]))
missing = [x["id"] for x in items if x["id"] not in SCENE]
if missing:
    sys.exit(f"尚未寫畫面描述：{missing}")

lines = [
    f"護腎教室 — 新增 {len(items)} 張卡片的中央插圖 生圖 Prompt",
    "=" * 78,
    "用法：每一段的 Prompt 整段複製丟給生圖服務，出圖比例選 16:9，",
    "      存成 gi/art/<檔名>.png（檔名就是每段標示的那個），",
    "      全部存好後告訴我，我會重跑 make_gi_cards.py 換上。",
    "",
    "插圖區實際尺寸 780x432 px（約 16:9），出圖大一點沒關係，程式會置中裁切。",
    "沒有畫的那幾張會沿用程式繪製的後備插圖，不影響卡片能用。",
    "=" * 78,
    "",
]

cur = None
for i, x in enumerate(items, 1):
    if x["cat"] != cur:
        cur = x["cat"]
        lines += ["", f"■■■ {cur} ■■■", ""]
    lines += [
        f"── {i:02d}. {x['title']}",
        f"   檔名：gi/art/{x['id']}.png",
        f"   Prompt：{STYLE} {BG[x['cat']]}. {SCENE[x['id']]}",
        "",
    ]

OUT.write_text("\n".join(lines), encoding="utf-8")
json.dump({x["id"]: f"{STYLE} {BG[x['cat']]}. {SCENE[x['id']]}" for x in items},
          open("gi/prompts_new.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"完成 {len(items)} 段 → {OUT} / gi/prompts_new.json")
