# 醫師審閱日期

`reviewed.json` 是人工確認的逐頁審閱紀錄，鍵為網站相對路徑（首頁用 `index.html`），值為實際完成審閱的 `YYYY-MM-DD` 日期。

只有醫師確認已完成該頁審閱後，才新增或更新日期。重新建站、匯入新知、修改版面都不能自動更新這份紀錄。缺少紀錄時不顯示審閱日期，也不輸出 lastReviewed / reviewedBy；原有作者資訊保留。

本次建立時維持空表，因舊版日期取自重建當天，不能當作人工審閱證據。更新紀錄後執行 build_site.py、bump_assets.py、check_site.py 並提交相關產出。
