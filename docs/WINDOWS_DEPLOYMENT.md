# Windows 11 部署指南

## 🎯 系統需求

### 硬體需求
- **CPU**: Intel Core i5 或 AMD Ryzen 5 以上
- **記憶體**: 8GB RAM 以上 (建議 16GB)
- **儲存空間**: 10GB 可用空間
- **網路**: 穩定網際網路連線

### 軟體需求
- Windows 11 (21H2 或更新版本)
- Windows Terminal (建議)
- 系統管理員權限

## 📦 安裝步驟

### 1. 快速安裝 (推薦)

```batch
# 下載專案
git clone https://github.com/your-repo/bag.holder.tw.git
cd bag.holder.tw

# 以系統管理員身份執行安裝腳本
deploy\install-windows.bat
```

### 2. 手動安裝

#### 步驟 1: 安裝 Python 3.11

1. 前往 [python.org](https://python.org/downloads/)
2. 下載 Python 3.11.x for Windows
3. **重要**: 勾選「Add to PATH」
4. 選擇「Customize installation」→ 勾選「pip」

#### 步驟 2: 安裝 Docker Desktop

1. 前往 [docker.com](https://www.docker.com/products/docker-desktop)
2. 下載 Docker Desktop for Windows
3. 安裝並重新啟動電腦
4. 啟用 WSL 2 後端 (如提示)

#### 步驟 3: 設置專案環境

```batch
# 創建虛擬環境
python -m venv venv

# 啟動虛擬環境
venv\Scripts\activate.bat

# 安裝相依套件
pip install --upgrade pip
pip install -r requirements.txt
```

#### 步驟 4: 配置環境變數

```batch
# 複製配置檔案
copy .env.example .env

# 使用記事本編輯
notepad .env
```

編輯 `.env` 檔案，填入您的 API 金鑰：

```env
FUBON_API_KEY=your_actual_api_key
FUBON_API_SECRET=your_actual_api_secret
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

## 🚀 啟動方式

### 開發環境

```batch
# 方式 1: 使用便捷腳本
start_development.bat

# 方式 2: 手動啟動
docker-compose up --build
```

### 生產環境

```batch
# 方式 1: 使用便捷腳本
start_production.bat

# 方式 2: 手動啟動
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

### 停止服務

```batch
# 使用便捷腳本
stop_services.bat

# 手動停止
docker-compose down
```

## 🔧 Windows 特定配置

### PowerShell 執行政策

如果遇到 PowerShell 執行政策問題：

```powershell
# 以系統管理員身份開啟 PowerShell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 檔案路徑配置

Windows 版本會自動調整以下路徑：

```yaml
# docker-compose.override.yml (Windows)
volumes:
  - .\data:/app/data          # Windows 路徑格式
  - .\logs:/app/logs
  - .\config:/app/config:ro
```

### WSL 2 配置 (可選)

為了更好的 Docker 效能，建議啟用 WSL 2：

```batch
# 以系統管理員身份執行
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 重新啟動電腦後
wsl --set-default-version 2
```

## 📊 效能最佳化

### Windows 11 筆電優化

```yaml
# docker-compose.override.yml
services:
  app:
    environment:
      - MAX_WORKERS=4              # 調整為筆電 CPU 核心數
      - MEMORY_LIMIT_MB=4096       # 8GB RAM 系統建議值
      - CPU_LIMIT=4.0              # 使用更多 CPU 資源
      - BATCH_PROCESSING_DELAY=1.0 # 較快的批次處理

  scanner:
    environment:
      - SCAN_INTERVAL_SECONDS=300  # 5 分鐘掃描間隔
      - SCAN_BATCH_SIZE=50         # 較大的批次大小
      - SCAN_MAX_CONCURRENT=8      # 更多並發連線
```

### 記憶體管理

```batch
# 監控記憶體使用量
docker stats

# 清理未使用的 Docker 資源
docker system prune -f
```

## 🛠️ 開發工具整合

### Visual Studio Code

推薦安裝的擴充套件：

- Python
- Docker
- GitLens
- REST Client

### 設置 VS Code

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/Scripts/python.exe",
    "python.terminal.activateEnvironment": true,
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    }
}
```

## 🔍 故障排除

### 常見問題

**Q: Docker 無法啟動？**
```batch
# 檢查 Docker 服務
sc query docker

# 重新啟動 Docker Desktop
# 透過工作管理員 > 服務 > Docker Desktop Service
```

**Q: Python 套件安裝失敗？**
```batch
# 升級 pip
python -m pip install --upgrade pip

# 使用國內鏡像 (可選)
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

**Q: 虛擬環境啟動失敗？**
```batch
# 刪除並重新創建虛擬環境
rmdir /s venv
python -m venv venv
venv\Scripts\activate.bat
```

**Q: 權限問題？**
```batch
# 以系統管理員身份開啟命令提示字元
# 或在檔案總管中右鍵 > 以系統管理員身份執行
```

### 日誌檢查

```batch
# 查看容器日誌
docker-compose logs app
docker-compose logs scanner
docker-compose logs telegram-bot

# 查看系統日誌
dir logs\*.log
type logs\app.log | more
```

## 📱 Telegram Bot 設定

### 創建 Bot

1. 開啟 Telegram，搜尋 @BotFather
2. 傳送 `/newbot`
3. 按照指示設定機器人名稱
4. 複製取得的 Token 到 `.env` 檔案

### 測試 Bot

```batch
# 啟動 Telegram Bot (單獨測試)
python -m src.telegram.main
```

## 🔐 安全性考量

### 防火牆設定

Windows Defender 防火牆可能需要允許：
- Docker Desktop
- Python.exe
- 連接埠 8000 (API 服務)
- 連接埠 5432 (PostgreSQL)
- 連接埠 6379 (Redis)

### 資料保護

```batch
# 備份重要資料
xcopy data\*.* backup\ /s /i

# 定期備份資料庫
docker-compose exec postgres pg_dump -U postgres tw_stock > backup\database_backup.sql
```

## 📊 監控與維護

### 系統監控

```batch
# 檢查系統資源
docker stats

# 檢查服務狀態
docker-compose ps

# 檢查應用程式健康狀態
curl http://localhost:8000/health
```

### 定期維護

```batch
# 清理 Docker 資源
docker system prune -a -f

# 更新 Docker 映像檔
docker-compose pull
docker-compose up -d --build

# 清理日誌檔案 (超過 30 天)
forfiles /p logs /m *.log /d -30 /c "cmd /c del @path"
```

## 🆕 更新與升級

### 專案更新

```batch
# 停止服務
stop_services.bat

# 更新程式碼
git pull origin main

# 重新啟動
start_production.bat
```

### Python 套件更新

```batch
# 啟動虛擬環境
venv\Scripts\activate.bat

# 更新套件
pip install --upgrade -r requirements.txt
```

## 📞 技術支援

- 📧 問題回報: 透過 GitHub Issues
- 📚 文件: 查看 `docs/` 目錄
- 🐛 錯誤日誌: 查看 `logs/` 目錄

---

🎉 恭喜！您已成功在 Windows 11 上部署台股監控機器人！