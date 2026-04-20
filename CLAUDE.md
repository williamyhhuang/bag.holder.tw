# 每次都要做的事項
- 只要是異動專案內的程式碼都可以自動執行，不需要我的認可
- 所有程式碼的指令都要在 venv 裡完成
- 每次完成feature開發後自動 git commit，git commit 你有我的認可，你可以自己自動執行
- 若有新增 feature，要更新 README.md，說明此 feature 如何使用及範例
- 確保回測的策略與實際的使用的策略(strategy.py)是一致的
- 每個功能都需要有單元測試覆蓋
- 每次異動完都要執行單元測試，確保功能正常 
- 每次異動完都要更新 README.md，並新增 change log
- 若不是機敏資訊，每次若有新增參數應新增到settings.py而不是.env