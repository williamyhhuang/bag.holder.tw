# 台股分析系統 (Taiwan Stock Analysis System)

全新的台股分析系統，整合資料下載、股票掃描、策略回測與期貨分析功能。採用 CSV 檔案儲存，簡化部署並提供統一 CLI 介面。

🆕 **全面重構**: CLI 統一介面、CSV 資料儲存、完整回測系統、定時任務支援！

## 🎯 專案特色

- **📥 股票資料下載**: YFinance 整合下載台股歷史資料
- **🔍 智能股票掃描**: 多策略選股 (動能、超跌、突破)
- **📈 策略回測系統**: 完整回測引擎驗證交易策略績效
- **📊 期貨分析**: 台指期貨技術分析與交易建議
- **💼 交易記錄管理**: CSV 檔案記錄個人交易與績效
- **🤖 Telegram 整合**: 分析結果即時推送與交易記錄
- **⏰ 定時任務支援**: 自動化資料下載與定期掃描
- **🐳 容器化部署**: Docker Compose 一鍵部署多服務
- **🖥️ 統一 CLI 介面**: 簡潔明瞭的命令列操作介面
- **📁 CSV 資料儲存**: 無需資料庫，簡單透明的檔案儲存

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────────┐
│                   Taiwan Stock Analysis CLI                   │
├─────────────────────────────────────────────────────────────────┤
│  📥 Downloader │  🔍 Scanner │  📈 Backtest │  📊 Futures      │
├─────────────────────────────────────────────────────────────────┤
│                        🧠 Core Services                        │
│  • CSV Storage   • YFinance   • Tech Analysis               │
│  • Telegram Bot  • User Trades • Performance Reporter        │
├─────────────────────────────────────────────────────────────────┤
│  🚀 Redis Cache  │  📁 CSV Files  │  🤖 Telegram Bot         │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 快速開始

### 支援平台

- 🍎 **macOS** (Mac Mini 2015+)
- 🪟 **Windows 11** (筆電/桌機)
- 🐧 **Linux** (Ubuntu 20.04+)

### 1. 環境需求

#### 本地開發
- Python 3.11+
- pip & venv

#### Docker 部署
- Docker & Docker Compose

### 2. 設定配置

```bash
# 複製配置檔案
cp .env.example .env

# 編輯配置檔案
nano .env
```

必要配置項目：
```env
# Telegram 設定
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Redis 設定
REDIS_URL=redis://localhost:6379

# 策略參數
STRATEGY_RSI_OVERSOLD_THRESHOLD=30
STRATEGY_RSI_OVERBOUGHT_THRESHOLD=70
STRATEGY_MIN_VOLUME_MOMENTUM=500000
```

### 3. 本地開發

```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安裝套件
pip install -r requirements.txt

# 查看可用指令
python main.py --help

# 下載股票資料
python main.py download

# 執行股票掃描
python main.py scan

# 運行回測
python main.py backtest

# 期貨分析
python main.py futures
```

### 4. Docker 部署

#### 基本部署
```bash
# 啟動核心服務
docker compose up -d redis app downloader scanner

# 查看服務狀態
docker compose ps

# 查看日誌
docker compose logs -f scanner
```

#### 完整部署
```bash
# 啟動所有服務（包含期貨監控）
docker compose --profile full up -d

# 僅啟動期貨服務
docker compose --profile futures up -d

# 手動執行回測
docker compose --profile backtest run --rm backtest
```

## 📋 功能說明

### 資料下載 (download)
使用 YFinance 下載台股歷史資料，支援 TSE 與 OTC 市場。

```bash
# 下載最近的股票資料
python main.py download

# 指定日期區間
python main.py download --start-date 2024-01-01 --end-date 2024-01-31

# 指定市場
python main.py download --markets TSE OTC
```

### 股票掃描 (scan)
基於技術指標進行股票選股，支援多種策略。

```bash
# 執行所有策略掃描
python main.py scan

# 執行特定策略
python main.py scan --strategy momentum

# 掃描並發送 Telegram 通知
python main.py scan --send-telegram
```

**支援策略:**
- **momentum**: 動能股選股（RSI、價格變化、成交量）
- **oversold**: 超跌股選股（RSI 過低、價格下跌）
- **breakout**: 突破股選股（價格突破、高成交量）

### 回測分析 (backtest)
完整的策略回測系統，驗證交易策略績效。

```bash
# 執行回測
python main.py backtest
```

**回測功能:**
- 技術指標策略回測
- 完整交易成本計算
- 風險控制（停損/停利）
- 績效分析報告
- 基準比較（TAIEX）

### 期貨分析 (futures)
台指期貨技術分析與交易建議。

```bash
# 期貨分析
python main.py futures

# 分析並發送 Telegram 通知
python main.py futures --send-telegram
```

## 📊 資料結構

### CSV 檔案位置
```
data/
├── stocks/              # 股票歷史資料
│   ├── 2330.csv        # 台積電
│   ├── 2454.csv        # 聯發科
│   └── ...
├── user_trades.csv      # 使用者交易記錄
└── ...
reports/
├── backtest_report_*.md # 回測報告
└── ...
```

### 交易記錄格式
```csv
trade_id,timestamp,symbol,action,quantity,price,status,notes
1,2024-03-15 09:30:00,2330,buy,1000,580.0,open,動能股買入
2,2024-03-20 14:30:00,2330,sell,1000,590.0,closed,停利出場
```

## 🤖 Telegram 整合

### 設定 Telegram Bot
1. 與 @BotFather 對話建立 Bot
2. 取得 Bot Token
3. 取得 Chat ID
4. 設定到 `.env` 檔案

### 支援的通知
- 股票掃描結果
- 期貨分析建議
- 系統運行狀態
- 錯誤警告

## ⏰ 定時任務

Docker 部署支援自動定時執行：

- **downloader**: 每日下載股票資料 (24小時)
- **scanner**: 每小時掃描分析 (1小時)
- **futures-monitor**: 每30分鐘期貨分析 (30分鐘)

## 🐳 Docker 部署詳細說明

### Docker 服務架構

本系統使用 Docker Compose 運行多個獨立服務：

**核心服務:**
- **redis** - 快取和速率限制
- **app** - 主應用程式（CLI 介面）
- **downloader** - 定時下載股票資料 (每日)
- **scanner** - 定時股票掃描分析 (每小時)
- **telegram-bot** - Telegram 整合服務
- **futures-monitor** - 期貨分析服務 (每30分鐘)
- **backtest** - 回測服務 (手動執行)

### 服務管理指令

```bash
# 查看服務狀態
docker compose ps

# 查看特定服務日誌
docker compose logs -f scanner
docker compose logs -f downloader

# 手動執行任務
docker compose exec app python main.py download
docker compose exec app python main.py scan --send-telegram
docker compose exec app python main.py futures --send-telegram

# 服務重啟
docker compose restart scanner
docker compose restart

# 停止所有服務
docker compose down
```

### 資料持久化

- `./data:/app/data` - 股票資料 CSV 檔案
- `./logs:/app/logs` - 應用程式日誌
- `./reports:/app/reports` - 回測報告
- `redis_data` - Redis 資料

### 故障排除

**常見問題:**
1. **Redis 連線失敗**: `docker compose logs redis`
2. **Telegram 無法發送**: 檢查 bot token 和 chat ID
3. **資料下載失敗**: 檢查網路連線和 yfinance API 狀態
4. **記憶體不足**: 限制單一策略執行 `--strategy momentum`

**重置環境:**
```bash
docker compose down -v  # 完全重置（會刪除所有資料）
docker compose up -d
```

## 📝 更新日誌

### v2.1.1 - 2026-04-01
- 🐛 修正 `load_from_stocks_dir` 空值欄位造成整檔載入失敗的問題（改為逐行跳過）
- 🤖 `BacktestRunner` 新增資料覆蓋率檢查：當本地 CSV 只有少數幾天時，自動觸發歷史資料下載
- 🗑️ 清除測試遺留的 `data/stocks/TEST_TW.csv`

### v2.1.0 - 2026-04-01
- 🔧 回測系統優先載入 `data/stocks/` 本地 CSV，不再重複從 yfinance 抓取
- 🆕 `YFinanceDataSource.load_from_stocks_dir()` — 批次讀取每檔獨立 CSV
- 🐛 修正 `calculate_position_size` 最小張數判斷未含手續費的問題
- ✅ 新增 `load_from_stocks_dir` 相關單元測試（3 個測試案例）

### v2.0.0 - 2024-03-15
- 🆕 全面重構為 CLI 架構
- 🆕 新增 YFinance 資料下載功能
- 🆕 CSV 檔案儲存替代 PostgreSQL
- 🆕 完整策略回測系統
- 🆕 統一 CLI 介面操作
- 🆕 Docker 定時任務支援
- 🆕 簡化 Telegram 整合
- 🆕 交易記錄管理系統
- 🔧 優化期貨分析模組
- 🔧 改進錯誤處理機制

### v1.x.x - 2024-02-XX
- 🆕 富邦證券 API 整合
- 🆕 股票掃描引擎
- 🆕 期貨監控系統
- 🆕 Telegram Bot 整合

## 🔗 相關連結

- [開發環境設定](CLAUDE.md)
- [問題回報](https://github.com/your-repo/issues)

## 📄 授權

MIT License