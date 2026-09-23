# -*- coding: utf-8 -*-
r"""把作者在後台按下的審閱確認同步上線。

    admin.html（作者點信裡的連結，按一下確認）
        ↓  寫進 Firestore 的 review 集合
    publish_reviews.py   ← 這支
        ↓  sync_reviews → build → bump → check → commit → push
    網站上出現「本頁內容最後由吳政哲醫師審閱於 YYYY-MM-DD」

為什麼要有這支：Firestore 那筆紀錄不會自己變成 HTML。原本得有人手動跑
sync_reviews.py 再重新建站，於是「按了確認、網站上卻什麼都沒變」——
作者以為完成了，讀者看到的還是沒有審閱日期的版本。

刻意不另外開排程（作者的原則是「能掛在現有流程就不要多一個自動化」）：
掛在 run_daily_nephrology.ps1 的每日新知之後，最慢隔天早上就會上線。
要立刻上線就手動跑這支。

冪等：雲端沒有新東西就什麼都不做，可以放心重複執行。

Exit 0 = 已發佈或沒有新的審閱紀錄；非 0 = 某一步失敗。
"""
import subprocess, sys, os, datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0')

# 審閱日期會印在每一個由 build_site.py 產生的頁面上（頁尾那行字 ＋ JSON-LD
# 的 lastReviewed），所以動到的產出跟每日新知那條管線一樣，再加上來源檔本身。
PUBLISH_PATHS = ['articles_src/reviewed.json', 'articles_src/news_reviewed.json',
                 'articles', 'index.html',
                 'about.html', 'calc.html', 'food.html', 'legal.html',
                 'sitemap.xml', 'robots.txt', 'sw.js', 'search_index.json']

# 「有沒有新東西」只看這兩個來源檔，不看整個工作區——
# 作者或另一個 AI 助手的 WIP 不該觸發發佈。
SOURCES = ['articles_src/reviewed.json', 'articles_src/news_reviewed.json']


def run_py(args):
    return subprocess.run([PY] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', errors='replace')


def git(args):
    return subprocess.run(['git'] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', env=ENV)


def main():
    # 1. 把雲端的審閱紀錄抓回 reviewed.json
    r = run_py(['sync_reviews.py'])
    sys.stdout.write((r.stdout or '')[-1500:])
    if r.returncode != 0:
        print('SYNC FAILED:', (r.stderr or r.stdout or '')[-500:]); return 1

    # 2. 兩個來源檔都沒變動 → 沒有新的確認，收工。
    if not git(['status', '--porcelain', '--'] + SOURCES).stdout.strip():
        print('沒有新的審閱確認。'); return 0

    # 3. 重建（審閱日期是建站時讀進去的，不重建不會出現在頁面上）
    b = run_py(['build_site.py'])
    if b.returncode != 0:
        print('BUILD FAILED:', (b.stderr or '')[-800:]); return 1
    run_py(['bump_assets.py'])

    # 4. 驗證；沒過就不發佈
    c = run_py(['check_site.py'])
    if c.returncode != 0:
        print('CHECK FAILED — not pushing:\n' + (c.stdout or '')[-1000:]); return 2

    # 5. 發佈。**commit 一定要帶路徑**——不帶的話用的是整個索引，會把作者或
    #    另一個 AI 助手還在暫存區的東西一起推上線（publish_daily.py 就出過
    #    這個問題，2026-09-23 修）。
    git(['add', '--'] + PUBLISH_PATHS)
    if git(['diff', '--cached', '--quiet', '--'] + PUBLISH_PATHS).returncode == 0:
        print('nothing staged to publish.'); return 0
    date = datetime.date.today().strftime('%Y-%m-%d')
    msg = (f'同步醫師審閱日期 {date}\n\n'
           f'來源：作者在 admin.html 按下的確認（Firestore review 集合）。\n\n'
           f'Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>')
    if git(['commit', '-q', '-m', msg, '--'] + PUBLISH_PATHS).returncode != 0:
        print('COMMIT FAILED'); return 1

    git(['fetch', '--quiet', 'origin', 'main'])
    rb = git(['rebase', '--autostash', 'origin/main'])
    if rb.returncode != 0:
        git(['rebase', '--abort'])
        print('REBASE CONFLICT — not pushing, 需要人工處理:\n'
              + ((rb.stdout or '') + (rb.stderr or ''))[-500:])
        return 4

    p = git(['push', 'origin', 'main'])
    if p.returncode != 0:
        print('PUSH FAILED:', (p.stderr or '')[-500:]); return 3
    print(f'審閱日期已同步上線（{date}）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
