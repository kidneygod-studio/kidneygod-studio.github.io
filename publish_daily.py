# -*- coding: utf-8 -*-
r"""每日新知自動發佈到護腎教室網站（kidneygod.net / GitHub Pages）。

由 nephrology 每日摘要 runner 在報告生成成功後呼叫。管線：

    import_digests.py --write     把所有尚未匯入的每日摘要收進 news.json
    （若 news.json 沒變動 → 沒有新東西，直接結束，不 build 不 push）
    build_site.py                 news.json → articles/news*.html 等
    bump_assets.py                更新快取版本號
    check_site.py                 驗證；**沒過就不 push**（不發佈壞掉的站）
    git add -A && commit && push   發佈到 GitHub Pages

刻意不加 --only：import 以 DOI 去重，跑全部＝自動補上前幾天沒發佈成功的。
所以某天 push 失敗，隔天成功時會一起補上，具自我修復性。

**只 commit 每日新知管線產生的檔案**（PUBLISH_PATHS），不用 git add -A——
否則會把作者其他還在編輯的 WIP（例如 dialysis/ 透析中心頁）一起掃上線。
「有沒有新東西」也只看 news.json 有無變動，不看整個工作區。

Exit 0 = 已發佈或沒有新東西；非 0 = 某一步失敗。

失敗時會**寄 email 警報**（見 notify()）。2026-10-05 補上，因為在那之前
呼叫端 run_daily_nephrology.ps1 只是 `Write-Output "Website publish
returned exit N"` 寫進 log，沒有通知任何人——10-01 建站 KeyError 連續失敗
三天就是這樣沒被發現的，作者是因為後台少了確認選項才察覺。
警報走 email 而不是 Telegram：醫院網路擋 api.telegram.org，警報會在最需要
它的時候送不出去（10-05 實際踩到）。

重試策略見 attempt()：分步給不同次數，確定性失敗不做無謂重試。
"""
import subprocess, sys, os, datetime, json, time

# 排程是用 powershell.exe 跑的，stdout 預設 cp950，印不出 build_site 的錯誤訊息
# （裡面常有 � 或日文假名）就會 UnicodeEncodeError。
# 2026-09-23：build_site 失敗，而「印出失敗原因」這件事自己又崩潰，於是
# log 裡只剩一行 "BUILD FAILED:" 加一段 traceback，真正的原因完全看不到。
# 診斷訊息永遠不該是會拋例外的那一段。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# 從腳本自身位置推導，換機器/換平台都不用改（原本寫死舊 Windows 機的路徑，
# 搬到 macOS 後整個發佈步驟都在 subprocess 的 cwd 上就地失敗）
ROOT = os.path.dirname(os.path.abspath(__file__))
PY   = sys.executable
# 讓 git 在無憑證時「快速失敗」而非卡在互動提示（無人值守必備）
ENV  = dict(os.environ, GIT_TERMINAL_PROMPT='0')

# 每日新知管線會動到的檔案（import_digests + build_site + bump_assets 的產出）。
# 只 stage 這些，其餘一律不碰。
# build_site.py 會重建的每一個產出都要列進來。漏掉的那些永遠不會被提交，
# 於是**每天都留在工作區裡是髒的**——而 git rebase 只要工作區有未暫存變更
# 就拒絕執行，所以漏一個就足以讓下面那個 rebase 每天失敗。
# 2026-09-14 就是這樣：about/calc/food/legal.html 不在清單裡，rebase 天天卡。
# （刻意不放進來的是作者還在編輯的 WIP，例如 dialysis/。）
PUBLISH_PATHS = ['articles_src/news.json', 'articles', 'index.html',
                 'about.html', 'calc.html', 'food.html', 'legal.html',
                 'sitemap.xml', 'robots.txt', 'sw.js', 'search_index.json']


# ── 自動重試 ──────────────────────────────────────────────────
# 2026-10-02 作者要求。重點是**分清楚哪一種失敗重試才有意義**：
#
#   會好的（暫時性）：網路不通、GitHub 短暫 5xx、另一台機器剛好也在 push
#                     造成 non-fast-forward、檔案被防毒鎖住
#   不會好的（確定性）：build_site 的 KeyError、check_site 判定不合格
#
# 對確定性失敗重試，只是把同一個錯誤原地再跑一次，浪費時間又讓 log 更難讀。
# 所以下面每一步的次數是分開給的，不是整支包一個 for 迴圈。
#
# ⚠ 10-01 那次連三天沒發出去就是確定性失敗（KeyError），**重試救不了那種**。
#   救那種的是讓失敗被看見——見檔尾 STATE_FILE 的連續失敗計數。
RETRY_WAIT = [20, 60, 180]          # 秒；第 n 次失敗後等多久再試


def attempt(what, fn, tries):
    """跑 fn()，回傳 (成功?, 最後一次的結果)。fn 要回傳 subprocess 的結果。"""
    last = None
    for i in range(tries):
        last = fn()
        if last.returncode == 0:
            if i:
                print(f'    {what}: 第 {i + 1} 次嘗試成功')
            return True, last
        if i < tries - 1:
            wait = RETRY_WAIT[min(i, len(RETRY_WAIT) - 1)]
            print(f'    {what}: 第 {i + 1} 次失敗，{wait} 秒後重試')
            time.sleep(wait)
    if tries > 1:
        print(f'    {what}: 重試 {tries} 次仍失敗')
    return False, last


# ── 連續失敗計數 ──────────────────────────────────────────────
# 重試擋得住暫時性故障，擋不住程式錯誤。10-01 那次是 KeyError，重試幾次都一樣，
# 而呼叫端只是 Write-Output 到 log——結果連續三天沒發出去，沒有人知道。
#
# 所以每次失敗都把「連續第幾天」記下來，並在輸出最前面印一行醒目的訊息。
# 這不是通知機制（作者還沒要），但至少讓看 log 的人一眼知道這不是今天才壞的。
STATE_FILE = os.path.join(ROOT, '.publish_state.json')

# 警報交給每日摘要那邊的 send_alert.py（email 優先、Telegram 備援、都不通就落地
# 存檔）。刻意用 subprocess 而不是 import：那支程式在另一個專案資料夾，而這支
# 腳本必須在「沒有那個專案」的機器上也能照常發佈，所以找不到就只印一行帶過。
ALERT_CANDIDATES = [
    os.path.join(os.path.expanduser('~'), 'nephrology_digest', 'scripts', 'send_alert.py'),
    os.path.join(os.path.dirname(ROOT), 'nephrology_digest', 'scripts', 'send_alert.py'),
]


def notify(msg):
    """寄警報。**絕對不能讓通知失敗變成發佈失敗**，所以整段包起來。"""
    script = next((p for p in ALERT_CANDIDATES if os.path.exists(p)), None)
    if not script:
        print('    （找不到 send_alert.py，略過警報通知）')
        return
    try:
        r = subprocess.run([PY, script, msg], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=180)
        print('    警報已寄出' if r.returncode == 0
              else f'    警報寄送失敗：{(r.stderr or "").strip()[-200:]}')
    except Exception as e:
        print(f'    警報寄送失敗：{e}')


def _state():
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def fail(code, msg):
    """印出失敗原因、累計連續失敗次數，回傳 exit code。"""
    st = _state()
    streak = int(st.get('fail_streak', 0)) + 1
    today = datetime.date.today().isoformat()
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'fail_streak': streak, 'last_fail': today,
                       'last_error': msg[:300]}, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    if streak > 1:
        print(f'*** 注意：每日新知已連續 {streak} 次發佈失敗'
              f'（最早一次之後就沒有新內容上站）***')
    print(msg)
    # 連續失敗次數寫進主旨：一眼看出是今天才壞的，還是已經壞了好幾天
    head = (f'護腎教室每日新知發佈失敗'
            + (f'（已連續 {streak} 次）' if streak > 1 else ''))
    notify(f'{head}\n\n{msg}')
    return code


def ok_done(msg):
    """成功時把連續失敗計數清掉。"""
    st = _state()
    if st.get('fail_streak'):
        print(f"    （先前已連續失敗 {st['fail_streak']} 次，這次成功，計數歸零）")
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'fail_streak': 0,
                       'last_ok': datetime.date.today().isoformat()},
                      f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    print(msg)
    return 0


def run_py(args):
    return subprocess.run([PY] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', errors='replace')


def git(args):
    return subprocess.run(['git'] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', env=ENV)


def main():
    # 1. 匯入所有尚未進站的每日摘要
    # 匯入要連外抓摘要，網路不穩是真的會發生 → 重試 3 次
    ok, r = attempt('import', lambda: run_py(['import_digests.py', '--write']), 3)
    sys.stdout.write((r.stdout or '')[-1500:])
    if not ok:
        return fail(1, 'IMPORT FAILED: ' + (r.stderr or '')[-500:])

    # 2. news.json 沒變動 → 沒有新研究，收工（只看 news.json，不看整個工作區，
    #    才不會被作者其他 WIP 檔案誤觸發）
    if not git(['status', '--porcelain', 'articles_src/news.json']).stdout.strip():
        return ok_done('nothing new to publish.')

    # 3. 重建網站
    # 建站幾乎都是確定性的（KeyError 那種重試一百次也一樣），只給 2 次：
    # 純粹擋偶發的檔案鎖／防毒掃描，不是指望它把程式錯誤跑好。
    ok, b = attempt('build', lambda: run_py(['build_site.py']), 2)
    if not ok:
        return fail(1, 'BUILD FAILED: ' + (b.stderr or '')[-500:])
    run_py(['bump_assets.py'])

    # 4. 驗證；沒過就不發佈
    # check_site 是純驗證，失敗代表產出真的有問題——**刻意不重試**，
    # 再跑一次只會得到同一個答案。
    c = run_py(['check_site.py'])
    if c.returncode != 0:
        return fail(2, 'CHECK FAILED - not pushing:\n' + (c.stdout or '')[-1000:])

    # 5. 發佈——只 stage 每日新知的產出檔，不碰其他 WIP
    git(['add', '--'] + PUBLISH_PATHS)
    # 判斷「有沒有東西要發」也要限定在 PUBLISH_PATHS，否則別人暫存中的檔案
    # 會讓這裡誤以為有東西要發。
    if git(['diff', '--cached', '--quiet', '--'] + PUBLISH_PATHS).returncode == 0:
        return ok_done('nothing staged to publish.')
    date = datetime.date.today().strftime('%Y-%m-%d')
    msg = (f'每日新知自動發佈 {date}\n\n'
           f'Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>')
    # **commit 一定要帶路徑。** 上面那行 add 很小心只 stage 每日新知的產出，
    # 但 `git commit -m` 不帶路徑用的是**整個索引**——作者或另一個 AI 助手
    # 只要有東西還在暫存區，就會被這支無人值守的腳本一起推上線。
    # 2026-09-23 發現時，索引裡正躺著 146 個還沒完成的台南美食通改版檔案。
    if git(['commit', '-q', '-m', msg, '--'] + PUBLISH_PATHS).returncode != 0:
        return fail(1, 'COMMIT FAILED')
    # 推之前先跟遠端對齊。醫院那台現在**只做網站編輯**，白天隨時可能推新的
    # commit；不先 rebase 的話這裡會 non-fast-forward 失敗，而且會一直失敗到
    # 有人手動處理（自我修復性就沒了）。
    # 本地只有上面那個剛做的 commit，rebase 很乾淨；真的衝突就中止不推，
    # 交給人處理——自動解衝突比推不上去更危險。
    # fetch -> rebase -> push 當成一個單位重試。**這一段重試是真的有用**：
    # 醫院那台白天也會推 commit，撞在一起時第一次 push 會 non-fast-forward，
    # 但重新 fetch+rebase 之後第二次通常就過了。只重推不重新 rebase 沒有用——
    # 遠端已經變了，所以每次都要從 fetch 重來。
    def sync_and_push():
        git(['fetch', '--quiet', 'origin', 'main'])
        # --autostash：工作區只要有任何未暫存變更，rebase 就整個拒絕執行，即使
        # 那些檔案跟這次要 rebase 的東西毫無關係（作者正在編輯的 WIP 就是這樣）。
        rb = git(['rebase', '--autostash', 'origin/main'])
        if rb.returncode != 0:
            git(['rebase', '--abort'])
            return rb                      # 衝突：交給外層判斷，不要重試硬解
        return git(['push', 'origin', 'main'])

    ok, p_ = attempt('push', sync_and_push, 3)
    if not ok:
        out = ((p_.stdout or '') + (p_.stderr or ''))[-500:]
        if 'CONFLICT' in out or 'could not apply' in out:
            return fail(4, 'REBASE CONFLICT - not pushing, 需要人工處理:\n' + out)
        return fail(3, 'PUSH FAILED: ' + out)
    return ok_done(f'published {date} to kidneygod.net')


if __name__ == '__main__':
    sys.exit(main())
