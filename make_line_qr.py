"""產生 LINE 官方帳號的 QR，並**反向解碼驗證**它真的掃得出正確網址。

產一個掃不出來、或掃出錯誤網址的 QR，比沒有 QR 更糟——
使用者會以為是自己手機的問題，而不會回報。所以一定要驗。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import cv2
import numpy as np
import segno

URL = "https://line.me/R/ti/p/%40511dxhiz"
OUT = Path("line_assets")
OUT.mkdir(exist_ok=True)

for ec, label in (("m", "M（15%）"), ("h", "H（30%）")):
    q = segno.make(URL, error=ec)
    print(f"  容錯 {label}：版本 {q.version}，{q.symbol_size()[0]} x "
          f"{q.symbol_size()[1]} 模組（含 4 格靜區）")

# 網頁用 SVG：任何尺寸都銳利，檔案小，顏色可控
q = segno.make(URL, error="m")
q.save(OUT / "line_qr.svg", scale=1, border=4,
       dark="#1e3a63", light="#ffffff")

# 列印／簡報用 PNG，邊長 1000px
q.save(OUT / "line_qr.png", scale=20, border=4,
       dark="#1e3a63", light="#ffffff")

print(f"\n  SVG {(OUT/'line_qr.svg').stat().st_size} bytes"
      f"　PNG {(OUT/'line_qr.png').stat().st_size//1024} KB")

# ── 反向解碼 ─────────────────────────────────────────────────────────
print("\n解碼驗證（用 OpenCV，模擬相機掃描）")
det = cv2.QRCodeDetector()
ok = True
for name in ("line_qr.png",):
    img = cv2.imread(str(OUT / name))
    data, pts, _ = det.detectAndDecode(img)
    match = data == URL
    ok &= match
    print(f"  {name:<16} 解出：{data or '（解不出來）'}")
    print(f"  {'':<16} 與原網址一致：{'是' if match else '否 ←'}")

# 縮到很小還掃不掃得到——名片、投影片角落都是這種尺寸
big = cv2.imread(str(OUT / "line_qr.png"))
for px in (300, 200, 150, 120, 100):
    small = cv2.resize(big, (px, px), interpolation=cv2.INTER_AREA)
    data, _, _ = det.detectAndDecode(small)
    good = data == URL
    ok &= good or px < 150   # 150px 以下解不出來還可接受
    print(f"  縮到 {px:>3}px：{'✓ 解得出' if good else '✗ 解不出'}")

print("\n全部通過：", ok)
