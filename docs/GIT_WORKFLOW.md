# Git 工作流程指南

## 🎯 概述

這個專案已經建立了自動化的 Git 工作流程，讓開發更加便捷和一致。

## 📋 可用命令

### 基本 Git 操作

```bash
# 查看專案狀態
make git-status

# 查看提交歷史
make git-log

# 設置 Git 使用者配置
make git-setup
```

### 自動化提交

```bash
# 手動指定提交訊息
make commit MSG="您的提交訊息"

# 智能自動提交（AI 生成提交訊息）
make smart-commit
```

## 🤖 智能提交系統

智能提交系統會自動分析變更並生成適當的提交訊息：

### 自動檢測變更類型

- **新功能** (`feat`) - 新增 Python 檔案
- **API 修復** (`fix(api)`) - 修改 fubon_client.py
- **相依套件** (`deps`) - 修改 requirements.txt
- **容器配置** (`ci`) - 修改 Docker 檔案
- **文件更新** (`docs`) - 修改 .md 檔案
- **測試更新** (`test`) - 修改測試檔案
- **配置更新** (`config`) - 修改 .env 檔案

### 自動生成的提交訊息格式

```
🔧 Update Fubon API client implementation

- src/api/fubon_client.py
- config/settings.py

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>
```

## 🛠️ 手動 Git 操作

如果需要更精細的控制，可以直接使用腳本：

```bash
# 自動提交腳本
./scripts/auto-commit.sh "您的提交訊息"

# 智能提交腳本（互動模式）
./scripts/smart-commit.sh

# 智能提交腳本（自動模式）
./scripts/smart-commit.sh -y
```

## 📁 忽略的檔案

`.gitignore` 已配置忽略以下檔案：

- 虛擬環境 (`venv/`, `.env`)
- 日誌檔案 (`logs/`, `*.log`)
- 資料庫檔案 (`*.db`, `*.sqlite`)
- 憑證檔案 (`*.pfx`, `*.p12`)
- 臨時檔案和快取
- IDE 配置檔案

## 🔄 開發工作流程

### 日常開發

1. **開始工作**
   ```bash
   make git-status  # 檢查目前狀態
   ```

2. **進行開發**
   - 修改程式碼
   - 測試功能

3. **提交變更**
   ```bash
   # 選擇其中一種方式
   make smart-commit                    # AI 自動生成提交訊息
   make commit MSG="描述您的變更"        # 手動指定提交訊息
   ```

4. **檢視歷史**
   ```bash
   make git-log     # 查看提交歷史
   ```

### 重大功能開發

```bash
# 開始功能開發
make commit MSG="✨ Start implementing new feature: market alerts"

# 進行中的提交
make commit MSG="🚧 WIP: Add alert notification system"
make commit MSG="🚧 WIP: Implement alert filtering logic"

# 完成功能
make commit MSG="✅ Complete market alerts feature with tests"
```

## 🎨 提交訊息風格

專案使用 Emoji 前綴的提交訊息風格：

- ✨ `:sparkles:` - 新功能
- 🔧 `:wrench:` - 配置修改
- 🐛 `:bug:` - 錯誤修復
- 📚 `:books:` - 文件更新
- 🧪 `:test_tube:` - 測試相關
- 🚀 `:rocket:` - 效能改善
- 🔒 `:lock:` - 安全性修復
- 🎨 `:art:` - 程式碼風格改善

## 🔍 故障排除

### 常見問題

**Q: 智能提交沒有正確檢測變更類型？**
A: 手動使用 `make commit MSG="..."` 指定提交訊息。

**Q: Git 使用者配置未設定？**
A: 執行 `make git-setup` 設定專案的 Git 配置。

**Q: 想要檢視特定檔案的變更？**
A: 使用 `git diff <檔案名稱>` 查看具體變更。

### 重置操作

```bash
# 取消暫存區的變更
git reset HEAD <檔案名稱>

# 丟棄工作目錄的變更
git checkout -- <檔案名稱>
```

## 📊 專案統計

```bash
# 查看專案統計
git log --stat --since="1 month ago"

# 查看貢獻者
git shortlog -sn

# 查看檔案變更頻率
git log --pretty=format: --name-only | sort | uniq -c | sort -rg
```