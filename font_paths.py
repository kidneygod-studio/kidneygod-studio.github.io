# -*- coding: utf-8 -*-
"""圖卡產生器用的字型位置。make_gi_cards / make_knowledge_cards / make_cards 共用。

為什麼要有這一支：三支產生器原本各自把字型寫死成 `C:\\Windows\\Fonts\\...`，
搬到 Mac mini 之後一跑就 `OSError: cannot open resource`。和 asset_paths.py
同一個教訓——路徑集中到一處，換機器只要確認這裡。

解析順序（每個字型鍵各自找，找到第一個存在的就用）：
  1. 環境變數 `KIDNEYGOD_FONTS` 指向的資料夾，裡面放 Windows 那幾個字型檔
     （msjh.ttc、kaiu.ttf…）。**要和 Windows 產出一模一樣，就用這個**：
     把那台 Windows 的字型檔複製過來，設好環境變數即可。
  2. Windows 原本的位置
  3. macOS 內建的對應字型（黑體 TC／宋體 TC／楷體 TC／Apple Color Emoji）

⚠ 第 3 條是「替代」，不是「相同」：字形、字重、行高都和微軟正黑體不一樣，
重新產生的卡片**外觀會變**。只補一兩張新卡時，混用會看得出來——
這種情況請用第 1 條，或回 Windows 產生。
"""
from __future__ import annotations

import glob
import os
import pathlib

WIN = pathlib.Path(r"C:\Windows\Fonts")
MAC = pathlib.Path("/System/Library/Fonts")

# 楷體 TC 在 macOS 是「可下載字型」，位置帶雜湊，只能用萬用字元找。
# 沒裝的話到「字體簿」搜尋「楷體-繁」下載一次就有。
_MAC_KAITI = sorted(glob.glob(
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/Kaiti.ttc"))

# 鍵 → (Windows 檔名, [(macOS 路徑, collection index), ...])
# index 用字型名稱確認過（Pillow getname()），TC 才是繁體字形，別改成 SC。
_TABLE: dict[str, tuple[str, list[tuple[str, int]]]] = {
    "sans":  ("msjh.ttc",     [(str(MAC / "STHeiti Light.ttc"), 0)]),    # Heiti TC Light
    "bold":  ("msjhbd.ttc",   [(str(MAC / "STHeiti Medium.ttc"), 0)]),   # Heiti TC Medium
    "light": ("msjhl.ttc",    [(str(MAC / "STHeiti Light.ttc"), 0)]),
    "ming":  ("mingliu.ttc",  [(str(MAC / "Supplemental" / "Songti.ttc"), 7)]),  # Songti TC Regular
    "kai":   ("kaiu.ttf",     [(p, 2) for p in _MAC_KAITI]               # Kaiti TC Regular
                              + [(str(MAC / "Supplemental" / "Songti.ttc"), 7)]),
    "emoji": ("seguiemj.ttf", [(str(MAC / "Apple Color Emoji.ttc"), 0)]),
}
_TABLE["serif"] = _TABLE["ming"]

# 彩色 emoji 是點陣字，只能用字型內建的尺寸繪製再縮放。
# Segoe UI Emoji 用 109；Apple Color Emoji 只接受 20/32/40/48/64/96/160，取最大的。
_EMOJI_SIZE = {"seguiemj.ttf": 109, "Apple Color Emoji.ttc": 160}


def font(key: str) -> tuple[str, int]:
    """回傳 (字型檔路徑, collection index)。找不到就丟出寫清楚原因的錯誤。"""
    win_name, mac = _TABLE[key]
    tried: list[str] = []
    cands: list[tuple[str, int]] = []
    if env := os.environ.get("KIDNEYGOD_FONTS"):
        cands.append((str(pathlib.Path(env) / win_name), 0))
    cands.append((str(WIN / win_name), 0))
    cands += mac
    for path, idx in cands:
        if os.path.exists(path):
            return path, idx
        tried.append(path)
    raise FileNotFoundError(f"找不到字型「{key}」，試過：\n  " + "\n  ".join(tried))


def emoji_draw_size() -> int:
    """emoji 字型必須用的繪製尺寸。"""
    return _EMOJI_SIZE.get(pathlib.Path(font("emoji")[0]).name, 109)
