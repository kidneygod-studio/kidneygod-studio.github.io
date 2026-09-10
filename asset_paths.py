# -*- coding: utf-8 -*-
"""原始素材的位置解析。所有產生器共用這一支。

素材（logo 原圖、知識卡插圖、貓咪貼圖）**不進版控**：太大，而且進了 git
歷史就永遠拿不掉。repo 裡只留壓過的產出，素材本身放在雲端同步資料夾，
兩台機器共用。

為什麼要有這一支：原本五支產生器各自把路徑寫死成
`C:\\Users\\user\\Downloads\\...`。搬到 macOS 之後那些路徑全部失效，
而且是**五個地方各壞各的**。更糟的是 check_site.py 會因此回傳 1，
publish_daily.py 看到非 0 就拒絕發佈——每日新知從搬機之後就一次都沒上線過。
路徑集中到這裡之後，換機器只要確認一個地方。

解析順序：
  1. 環境變數 `KIDNEYGOD_ASSETS`——任何機器、任何平台都能用它覆寫
  2. Google Drive 的預設位置（macOS 與 Windows 的常見路徑都試）
  3. repo 內的 `assets_src/`——單機備援，.gitignore 擋著

**找不到不是錯誤。** 素材只有在「重新產生」時才需要（重做 logo、重新匯入
插圖）。網站本身跑不到它們——線上要的是 `og/`、`cards/`、`gi/` 這些已經
壓好、已經進版控的產出。所以這裡回傳的路徑可能不存在，呼叫端要自己判斷，
而 check_site.py 對這一項只警告、不擋發佈。
"""
from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

# 資料夾名稱。雲端與本機備援都用同一個名字，換機器時比較不會找錯。
ASSETS_DIRNAME = "kidneygod_assets"

# 素材檔名／子資料夾名。集中在這裡，改名時只改一處。
LOGO_PNG = "kidneygod.png"          # 1678×937 白底 .NET 版
GI_ART = "知識卡插圖"                # 知識卡插圖（第一批）
GI_ART2 = ("知識卡插圖", "知識卡插圖2")   # 第二批，原本就是巢狀在第一批底下
STICKERS = "貓咪貼圖"


def _candidates() -> list[pathlib.Path]:
    """可能的素材根目錄，依優先序。"""
    out: list[pathlib.Path] = []

    env = os.environ.get("KIDNEYGOD_ASSETS")
    if env:
        out.append(pathlib.Path(env).expanduser())

    home = pathlib.Path.home()

    # macOS 的 Google Drive for Desktop。~/Google Drive 是指向
    # ~/Library/CloudStorage/GoogleDrive-<帳號>/ 的符號連結，兩條都試——
    # 有些機器只有其中一條。帳號 email 不寫死，用 glob。
    for drive in [home / "Google Drive",
                  *sorted((home / "Library" / "CloudStorage").glob("GoogleDrive-*"))]:
        for mydrive in ("我的雲端硬碟", "My Drive"):
            out.append(drive / mydrive / ASSETS_DIRNAME)

    # Windows：Google Drive 常掛成 G:\，也可能在使用者目錄底下
    for drive in (pathlib.Path("G:/"), pathlib.Path("H:/"), home / "Google Drive"):
        for mydrive in ("我的雲端硬碟", "My Drive"):
            out.append(drive / mydrive / ASSETS_DIRNAME)

    # 單機備援：repo 內的 assets_src/（.gitignore 擋著）
    out.append(ROOT / "assets_src")

    # 去重但保留順序
    seen, uniq = set(), []
    for p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def assets_root() -> pathlib.Path:
    """素材根目錄。找不到任何存在的候選時，回傳第一個候選當作「應該放這裡」，
    好讓錯誤訊息能告訴使用者該把檔案放到哪。"""
    cands = _candidates()
    for p in cands:
        if p.is_dir():
            return p
    return cands[0]


def asset(*parts: str) -> pathlib.Path:
    """素材路徑。回傳的路徑不保證存在——呼叫端要自己檢查。"""
    return assets_root().joinpath(*parts)


def describe() -> str:
    """給錯誤訊息用的一句話。"""
    root = assets_root()
    state = "存在" if root.is_dir() else "不存在"
    return (f"素材根目錄：{root}（{state}）\n"
            f"  可用環境變數 KIDNEYGOD_ASSETS 指到別的地方。\n"
            f"  素材不進版控，需要時從雲端同步資料夾取得。")


if __name__ == "__main__":
    print(describe())
    print()
    for label, p in (("logo 原圖", asset(LOGO_PNG)),
                     ("知識卡插圖", asset(GI_ART)),
                     ("知識卡插圖2", asset(*GI_ART2)),
                     ("貓咪貼圖", asset(STICKERS))):
        print(f"  {'✓' if p.exists() else '✗'} {label:<12} {p}")
