# 台股分析系統 (Taiwan Stock Analysis System)

全新的台股分析系統，整合資料下載、股票掃描、策略回測與期貨分析功能。採用 CSV 檔案儲存，簡化部署並提供統一 CLI 介面。

🆕 **全面重構**: CLI 統一介面、CSV 資料儲存、完整回測系統、定時任務支援！

## 🎯 專案特色

- **📥 股票資料下載**: YFinance 整合下載台股歷史資料（上市 + 上櫃）
- **🚦 今日買賣訊號**: P1 完整策略過濾，直接輸出「建議買入」與「賣出警示」
- **🔍 股票觀察清單**: 寬鬆條件快速篩選動能、超賣、突破股
- **📈 策略回測系統**: 完整回測引擎 (P1 策略 + 成交量≥1000張，585天 +34.10%，Sharpe 1.20)
- **📊 期貨分析**: 台指期貨技術分析與交易建議
- **💼 交易記錄管理**: CSV 檔案記錄個人交易與績效
- **🤖 Telegram 整合**: 分析結果即時推送與交易記錄
- **⏰ 定時任務支援**: 自動化資料下載與定期掃描
- **🐳 容器化部署**: Docker Compose 一鍵部署多服務
- **☁️ GCP 生產部署**: Terraform IaC 自動佈建 Cloud Run Jobs/Service、GCP Workflows、Cloud Scheduler
- **🖥️ 統一 CLI 介面**: 簡潔明瞭的命令列操作介面
- **📁 CSV 資料儲存**: 無需資料庫，簡單透明的檔案儲存

## 🏗️ 系統架構

本專案採用 **DDD (Domain-Driven Design) / Hexagonal Architecture（六角形架構 / Ports and Adapters）** 設計模式：

```
src/
├── domain/              # 領域層（最內層，無外部依賴）
│   ├── models/          # 領域模型：StockData, TradingSignal, Portfolio, BacktestResult
│   ├── services/        # 領域服務：IndicatorCalculator, SignalDetector
│   └── ports/           # 抽象介面：IMarketDataProvider, INotificationService, IAIAnalyzer
├── application/         # 應用層（協調領域服務）
│   └── use_cases/       # ScanStocksUseCase, RunBacktestUseCase, DownloadDataUseCase, AnalyzeFuturesUseCase
├── infrastructure/      # 基礎設施層（實作外部依賴）
│   ├── persistence/     # DatabaseManager, ORM Models
│   ├── market_data/     # YFinanceAdapter, FubonAdapter
│   ├── notification/    # TelegramAdapter
│   └── ai/              # ClaudeAnalyzer, OpenAIAnalyzer, GeminiAnalyzer, OpenRouterAnalyzer
└── interfaces/          # 介面層（CLI 入口）
    └── cli/             # main.py CLI 入口
```

向下相容：舊有 `src/database/`, `src/indicators/` 等路徑透過 re-export shim 保持相容。

```
┌─────────────────────────────────────────────────────────────────┐
│                   Taiwan Stock Analysis CLI                   │
├─────────────────────────────────────────────────────────────────┤
│  📥 Download │ 🚦 Signals │ 🔍 Scan │ 📈 Backtest │ 📊 Futures  │
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

# 今日買賣訊號（P1 完整策略，建議進出場）
python main.py signals

# 持倉賣出檢查（讀 Google Sheets，判斷是否應賣出，含 AI 分析）
python main.py check-holdings
python main.py check-holdings --send-telegram

# 執行股票觀察清單
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
下載台股歷史資料，支援 TSE 與 OTC 市場。預設資料來源為 **YFinance**，可透過 `--source fubon` 切換至**富邦 Neo API**。

```bash
# 下載最近的股票資料（預設 yfinance）
python main.py download

# 指定日期區間
python main.py download --start-date 2024-01-01 --end-date 2024-01-31

# 指定市場
python main.py download --markets TSE OTC

# 使用富邦 API 下載（需設定 FUBON_* 環境變數）
python main.py download --source fubon

# 富邦 API 指定日期
python main.py download --source fubon --start-date 2024-01-01 --end-date 2024-01-31
```

#### 資料來源說明

| 來源 | 特性 | 適用情境 |
|------|------|---------|
| `yfinance`（預設）| 批次下載，速度快 | 一般使用 |
| `fubon` | 逐支查詢，每分鐘 30 次限制 | 需要富邦 API 原始資料 |

**環境變數設定（富邦 API）：**
```bash
FUBON_USER_ID=你的身分證字號
FUBON_API_KEY=你的 API Key
FUBON_CERT_PATH=docs/fubon.cert.p12
FUBON_CERT_PASSWORD=你的憑證密碼
```

也可透過 `DOWNLOAD_DATA_SOURCE=fubon` 環境變數設為全域預設值。

### 今日買賣訊號 (signals) ⭐
使用 P1 完整策略過濾，直接輸出「今日建議買入」與「賣出警示」，是每日操盤的主要參考指令。

```bash
# 今日買賣訊號（最常用）
python main.py signals

# 同時顯示觀察清單（訊號觸發但未完全達標）
python main.py signals --watch

# 發送到 Telegram
python main.py signals --send-telegram

# 使用 AI 進行二次過濾分析（provider 由 AI_PROVIDER 設定，預設 claude）
python main.py signals --ai-filter

# AI 分析 + 發送到 Telegram
python main.py signals --ai-filter --send-telegram
```

**買入訊號條件（必須同時通過）：**
1. 技術訊號觸發：BB Squeeze Break / Donchian Breakout / Golden Cross / MACD Golden Cross
2. 個股在 MA60 上方（長期上升趨勢）
3. 均線多頭排列：MA5 > MA10 > MA20
4. RSI ≥ 50（具備上漲動能）
5. 近 20 日動能排名前 30（避免動能衰退的假突破）
6. 成交量 ≥ 1000 張（流動性過濾）
7. 族群強勢（族群內 > 50% 股票收盤在 MA20 上方）
8. 月營收 ≥ 門檻（預設 1 億元，可設年增率門檻）
9. **排除處置股/注意股**：自動從 TWSE 每日更新排除，無法進場（硬過濾）
10. 三大法人買超（選用，預設停用；啟用後不足者降級至觀察清單）

> **注意**：買入過濾器只影響「建議買入」和「觀察清單」，不影響賣出警示。

**AI 二次過濾（`--ai-filter`）：**

在 P1 技術指標篩選後，可選擇加入 AI 做進一步的綜合判斷，將股票重新分為四個等級：

| 等級 | 說明 |
|------|------|
| 🔥 強烈建議買入 | 多訊號共振、RSI 健康、族群強勢、基本面良好 |
| ✅ 建議買入 | 訊號有效，可考慮小量布局 |
| 👀 觀察 | 訊號偏弱或有疑慮，宜等待確認 |
| ⛔ 不建議 | 處置股/注意股/RSI 極端/訊號可疑 |

**支援 provider：**

| Provider | 預設模型 | API Key 設定 |
|----------|----------|-------------|
| `claude`（預設） | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| `gemini` | `gemini-2.5-flash-preview-04-17` | `GEMINI_API_KEY` |
| `openrouter` | `google/gemini-2.5-flash-preview` | `OPENROUTER_API_KEY` |

**設定方式：**
```bash
# .env — 選擇 provider 並填入對應 API Key
AI_PROVIDER=openrouter      # 或 claude、openai、gemini
OPENROUTER_API_KEY=sk-or-...
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...

# 可選：指定模型（空白 = 使用預設）
AI_MODEL=

# 執行（AI 分析會包含 buy + watch 清單，再重新分級）
python main.py signals --ai-filter
```

Telegram 訊息採用手機友善格式，每支股票附上一行中文理由。

**訊號歷史記錄：**
每次執行 `python main.py signals` 會自動將結果存為 JSON 至 `data/signals_log/signals_YYYYMMDD_HHMMSS.json`，可供後續查閱與比較。

**賣出警示訊號（持有中請注意）：**
- MACD Death Cross（最嚴重）
- Death Cross（MA5 跌破 MA20）
- RSI Momentum Loss（RSI 跌破 50）

> **設計原則**：賣出警示**不受**月營收、處置股等買入過濾器限制。若持有的股票變成處置股並觸發賣出訊號，仍會正常顯示並標記「⚠️處置股」提醒優先處理。

**開關控制（預設關閉）：**
```bash
# settings.py / 環境變數
SIGNALS_SHOW_SELL=true    # 開啟賣出警示顯示（終端機與 Telegram）
SIGNALS_SHOW_SELL=false   # 關閉（預設）
```

### 股票觀察清單 (scan)
寬鬆條件篩選，適合找尋潛力標的，不代表可直接進場。

```bash
# 執行所有策略掃描
python main.py scan

# 執行特定策略
python main.py scan --strategy momentum

# 掃描並發送 Telegram 通知
python main.py scan --send-telegram
```

**支援策略:**
- **momentum**: 動能股（漲幅 > 3%、成交量 > 50萬、RSI > 50）
- **oversold**: 超賣股（RSI < 30、跌幅 > 2%、成交量 > 30萬）
- **breakout**: 突破股（成交量 > 100萬、收盤 > MA20）

> **signals vs scan 的差異**: `signals` 使用 P1 完整策略（含 7 道進場過濾），輸出可直接參考的進出場建議；`scan` 使用簡單閾值，僅作為觀察清單。

#### 族群趨勢過濾

`signals` 指令內建族群強弱過濾，只保留強勢族群的買入訊號：

- **族群分組**：依台灣股票代碼前兩碼自動分類（水泥工業、食品工業、半導體業、金融保險、航運業等 20+ 族群）
- **強度計算**：族群內「收盤 > MA20」的股票比例，達 50% 以上即為強勢族群
- **過濾邏輯**：弱勢族群的買入訊號自動移入觀察清單，標示「族群偏弱（XXX）」
- **輸出**：買入清單新增族群欄位，底部顯示各族群強弱摘要

**設定方式（`config/settings.py` → `BacktestSettings`）：**
```python
enable_sector_trend_filter: bool = True   # 啟用族群過濾
sector_trend_threshold: float = 0.5       # 強勢族群門檻（50%）
```

若希望停用族群過濾，可透過環境變數覆蓋：`BACKTEST_ENABLE_SECTOR_TREND_FILTER=false`。

#### 月營收過濾

`signals` 指令新增第 7 道進場過濾，自動排除月營收過低的股票：

- **資料來源**：即時從證交所（TSE）/ 櫃買中心（OTC）OpenAPI 取得最新月營收，當日快取至 `data/revenue_cache.json`
- **過濾邏輯**：月營收低於門檻的股票買入訊號自動移入觀察清單，標示「月營收 XXM < 100M」
- **單位**：百萬元（NTD million）；1 億元 = 100

**設定方式：** 直接編輯 `config/settings.py` 中的 `BacktestSettings`：
```python
min_monthly_revenue_million: float = 100.0  # 1 億元；改為 0 可停用
```

若 API 無法連線（非交易時間或網路問題），過濾器自動略過，不影響其他訊號輸出。

#### 月營收年增率門檻（選用）

同時可設定年增率過濾，排除月營收金額達標但成長動能不足的股票：

```python
min_revenue_yoy_pct: float = 0.0   # 0 = 停用；20.0 = 需年增率 ≥ 20%
```

#### 處置股/注意股過濾

`signals` 指令自動排除目前受 TWSE 處置措施或列為注意股的標的：

- **資料來源（雙來源）**：
  - 主要：富邦 SDK `intraday.tickers(isDisposition=True / isAttention=True)`（需登入）
  - Fallback：TWSE OpenAPI `/announcement/punish` + `/announcement/notetrans`（免登入）
- **快取**：每日更新至 `data/cache/disposal_cache.json`
- **過濾邏輯**：處置/注意股**完全不進**買入或觀察清單（硬過濾）
- **賣出例外**：若持有股票變成處置股仍會顯示賣出警示，並標記「⚠️處置股」

**設定方式（`config/settings.py` → `BacktestSettings`）：**
```python
enable_disposal_filter: bool = True   # 預設啟用
filter_attention_stocks: bool = False  # 是否也過濾注意股（比處置股寬鬆）
```

#### 三大法人籌碼過濾（選用）

法人買超通常比散戶早 3-10 天，可作為早期信號確認指標：

- **資料來源**：TWSE T86 API（每交易日更新，免費）
- **欄位**：外資買賣超、投信買賣超、自營商買賣超（單位：股）
- **過濾邏輯**：法人買超不足者降級至觀察清單（非硬過濾），標示法人張數
- **非交易日**：API 無資料時自動 fail-open，不阻斷掃描

**設定方式：**
```python
enable_institutional_filter: bool = False          # 預設停用（建議先觀察數週）
institutional_min_foreign_net_shares: int = 500_000  # 外資門檻 500 張
institutional_min_trust_net_shares: int = 200_000    # 投信門檻 200 張
institutional_require_any: bool = True               # OR 邏輯（外資或投信擇一達標即可）
```

> **建議**：先以 `enable_institutional_filter=False` 跑 1-2 週觀察法人數字分佈，再決定門檻。

### 買入冷卻期（Signal Cooldown）

同一支股票在最近 N 個交易日內已觸發過買入訊號時，後續的買入訊號會自動降級為 WATCH，避免同一波上漲中反覆進場。

**設定方式（`config/settings.py` → `BacktestSettings`）：**
```python
signal_cooldown_days: int = 0   # 冷卻期交易日數（0 = 停用）
```

- **預設值 10**：約 2 個交易週
- **停用**：設定 `BACKTEST_SIGNAL_COOLDOWN_DAYS=0`
- **適用範圍**：策略掃描（`signals`）與回測（`backtest`）皆有效
- **歷史感知**：Scanner 即使只看今日訊號，冷卻期也會回溯歷史資料確認先前是否已觸發

### 回測分析 (backtest)
完整的策略回測系統，驗證交易策略績效。

```bash
# 執行回測
python main.py backtest

# 略過下載，直接使用本地資料（加速重跑回測）
python main.py backtest --skip-download
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

---

## 📝 Telegram 交易記錄 Bot（Google Sheets 同步）

使用者在 Telegram 輸入買入/賣出指令，系統自動記錄至 CSV 及 Google Sheets。

### 指令格式

| 指令 | 說明 | 範例 |
|------|------|------|
| `買入 股票代號 價格 [股數]` | 記錄買入（股數預設 1000） | `買入 2330 150.5 1000` |
| `賣出 股票代號 價格 [股數]` | 記錄賣出 | `賣出 2330 165` |
| `/scan` | 觸發 GCP download + signals，結果自動傳送至 Telegram | `/scan` |
| `/pnl` | 查看未實現損益與已實現損益摘要 | `/pnl` |
| `/stats` | 近 30 天交易統計 | `/stats` |
| `/trades` | 最近 10 筆記錄 | `/trades` |
| `/help` | 顯示說明 | `/help` |

### `/pnl` — 損益查詢

在 Telegram 輸入 `/pnl` 後，系統會：
1. 讀取 Google Sheets 全部交易記錄
2. 以 FIFO 配對計算**已實現損益**（歷史賣出配對買入）
3. 從 yfinance 取得即時股價，計算**未實現損益**（現有持倉）
4. 以手機易讀格式回傳摘要

**回應格式範例：**
```
📊 損益摘要
🕐 2026-05-08 14:30

━━━ 未實現損益 ━━━
📈 2330 台積電
  買入 150.00 → 現價 180.00
  1,000 股｜+30,000 (+20.0%)

未實現合計：+30,000

━━━ 已實現損益 ━━━
✅ 2330 台積電 (2026-04-10)
  140.00 → 160.00｜1,000 股
  +20,000 (+14.3%)

已實現合計：+20,000

💰 總損益：+50,000
```

**需求：**
- Google Sheets 需啟用（`GOOGLE_SHEETS_ENABLED=true`）且已有交易記錄
- yfinance 需可連線（取得即時股價），若無法取得則顯示「無法取得即時股價」

### `/scan` — 手動觸發掃描

在 Telegram 輸入 `/scan` 後，webhook 會：
1. 立即回覆「⏳ 正在觸發掃描，請稍候...」
2. 在背景呼叫 GCP Workflows API，啟動 `bag-holder-run-jobs` 工作流程
3. 工作流程依序執行 `bag-holder-download` → `bag-holder-signals` Cloud Run Job
4. `signals` Job 完成後自動將訊號結果推送至 Telegram

**需求：**
- `GCP_PROJECT_ID` 環境變數需設定（已有 Cloud Run 部署即已設定）
- Webhook Service Account 需有 `roles/workflows.invoker` 權限

**選用設定（預設值即可用）：**

| 環境變數 | 預設值 | 說明 |
|----------|--------|------|
| `GCP_WORKFLOW_NAME` | `bag-holder-run-jobs` | 要觸發的 GCP Workflow 名稱 |
| `GCP_WORKFLOW_LOCATION` | `asia-east1` | Workflow 所在 Region |

### Google Sheets 設定

#### 步驟一：建立 Google Service Account

1. 至 [Google Cloud Console](https://console.cloud.google.com/) → IAM & Admin → Service Accounts
2. 建立新的 Service Account（名稱例如 `trade-recorder`）
3. 下載 JSON 金鑰檔案

#### 步驟二：啟用 Google Sheets API

```bash
gcloud services enable sheets.googleapis.com drive.googleapis.com
```

#### 步驟三：建立 Google Sheet 並共用

1. 建立新的 Google 試算表
2. 取得試算表 ID（URL 中 `/d/` 後面的部分）
3. 將試算表共用給 Service Account 的 email（賦予「編輯者」權限）

#### 步驟四：設定 `.env`

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# Google Sheets
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_SPREADSHEET_ID=你的試算表ID
GOOGLE_SHEETS_WORKSHEET_NAME=交易記錄

# 方式一：直接貼上 JSON 字串（推薦 Cloud Run / Docker）
GOOGLE_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}

# 方式二：指定 JSON 檔案路徑（本地開發）
# GOOGLE_CREDENTIALS_FILE=/path/to/service_account.json
```

### 本地啟動

```bash
source venv/bin/activate
python -m src.interfaces.trade_bot_main
```

### Docker 啟動

```bash
docker compose up trade-recorder
```

### 持倉賣出檢查

每日 10:00 自動檢查 Google Sheets 記錄的持倉，判斷是否應賣出。

**流程：**
1. 讀取 Google Sheets 交易記錄，取每支股票最後一筆 action：`買入` = 未平倉，`賣出` = 已平倉（略過）
2. 執行全市場 P1 訊號掃描，取得賣出訊號（RSI Momentum Loss / MACD Death Cross / Death Cross）
3. 篩選持倉中有賣出訊號的股票，enrichment：現金損益%、持有天數、族群強弱、月營收年增率
4. 呼叫 AI（Claude/OpenAI/Gemini）做最終判斷：**確認賣出 / 設停損觀察 / 繼續持有**
5. 發送 Telegram 通知

**本地執行：**
```bash
# 僅顯示結果
python main.py check-holdings

# 同時發送 Telegram
python main.py check-holdings --send-telegram
```

**Telegram 通知範例：**
```
📋 持倉賣出檢查 2024-05-01
持倉 3 支，賣出訊號 1 支

⚠️ P1 賣出訊號（持倉中）1 支
  2330 台積電 [MACD Death Cross] -2.3% 持有15天

🤖 AI 持倉分析

🔴 建議出場 (1 支)
【2330 台積電】
└ 族群轉弱、MACD 訊號明確，建議立即出場

✅ 繼續持有 (0 支)
```

> **說明：** 若 Google Sheets 無任何持倉記錄，或持倉股票今日無賣出訊號，則發送「無賣出訊號」的簡短通知。

### GCP 生產部署（Terraform IaC）

本專案使用 Terraform 管理所有 GCP 資源，CI/CD（GitHub Actions）於每次推送 `main` 分支時自動執行 `terraform apply`。

#### 架構

```
Cloud Scheduler (台北時間 14:35 週一至五)
    │
    ▼
GCP Workflows (bag-holder-sync-trades)
    └─ Cloud Run Job: bag-holder-sync-trades  # 同步 Fubon 今日成交記錄至 Google Sheets

Cloud Scheduler (台北時間 14:40 週一至五)
    │
    ▼
GCP Workflows (bag-holder-run-jobs)
    ├─ Cloud Run Job: bag-holder-download   # 下載台股資料
    └─ Cloud Run Job: bag-holder-signals    # 產生買賣訊號並推送 Telegram

Cloud Scheduler (台北時間 10:00 週一至五)
    │
    ▼
GCP Workflows (bag-holder-run-jobs-10)
    ├─ Cloud Run Job: bag-holder-download        # 重新下載最新資料
    ├─ Cloud Run Job: bag-holder-signals         # 再次產生買賣訊號
    └─ Cloud Run Job: bag-holder-check-holdings  # 持倉賣出檢查（含 AI 判斷）

Cloud Run Service: bag-holder-webhook       # Telegram Webhook Bot
```

#### 資源清單

| 資源類型 | 名稱 | 說明 |
|---|---|---|
| Cloud Run Job | `bag-holder-download` | 每日下載股票資料 |
| Cloud Run Job | `bag-holder-signals` | 每日產生買賣訊號 |
| Cloud Run Job | `bag-holder-check-holdings` | 持倉賣出檢查（含 AI 判斷） |
| Cloud Run Job | `bag-holder-sync-trades` | 同步 Fubon 今日成交記錄至 Google Sheets |
| Cloud Run Service | `bag-holder-webhook` | Telegram Webhook Bot |
| GCP Workflows | `bag-holder-sync-trades` | 14:35 執行 sync-trades |
| GCP Workflows | `bag-holder-run-jobs` | 14:40 依序執行 download → signals |
| GCP Workflows | `bag-holder-run-jobs-10` | 10:00 依序執行 download → signals → check-holdings |
| Cloud Scheduler | `bag-holder-sync-trades-trigger` | 台北 14:35 觸發成交記錄同步 |
| Cloud Scheduler | `bag-holder-run-jobs-trigger` | 台北 14:40 觸發收盤後下載+訊號 |

#### Terraform 結構

```
terraform/
├── bootstrap/      # 一次性基礎建設（GCS backend、IAM SA）
└── deployable/     # 每次部署更新的資源
    ├── main.tf
    ├── variables.tf
    ├── backend.tf
    ├── run-jobs.workflow.yaml          # GCP Workflows 定義（download → signals）
    ├── run-sync-trades.workflow.yaml   # GCP Workflows 定義（sync-trades）
    └── modules/
        ├── cloud_run_job/
        └── cloud_run_service/
```

#### 手動部署（緊急）

```bash
cd terraform/deployable
terraform init
terraform apply -var="project_id=bag-holder-tw" -var="image_tag=<commit_sha>"
```

---

### Cloud Run 部署（方案 A：Webhook + Cloud Run Service）

生產環境建議使用 Webhook 模式，成本幾乎為零（按請求計費，個人用量通常在免費額度內）。

#### 架構圖

```
Telegram ──POST──▶ Cloud Run Service (bag-holder-webhook)
                        │
                        ▼
              HandleTelegramWebhookUseCase  [Application]
                        │
                        ▼
                  TradingBot               [Infrastructure]
                  ├─ UserTradesRecorder    [Infrastructure / CSV]
                  └─ GoogleSheetsRecorder  [Infrastructure / GSheets]
```

#### 部署步驟

**步驟一：設定 GCP Secret Manager**

在 `APP_SECRETS` JSON 中新增以下欄位（Webhook URL 可在 Service 建立後再填入）：

```json
{
  "TELEGRAM_BOT_TOKEN": "your_bot_token",
  "TELEGRAM_WEBHOOK_SECRET": "自訂一個隨機字串（用於驗證 Telegram 請求）",
  "TELEGRAM_WEBHOOK_URL": "https://bag-holder-webhook-<hash>-de.a.run.app",
  "GOOGLE_SHEETS_ENABLED": "true",
  "GOOGLE_SHEETS_SPREADSHEET_ID": "你的試算表ID",
  "GOOGLE_CREDENTIALS_JSON": "{...service account json...}"
}
```

> `TELEGRAM_WEBHOOK_URL` 是 Cloud Run Service URL，首次部署後可從 Console 取得，再更新 Secret。

**步驟二：推送到 main 分支**

CI/CD 會自動完成：
1. 建立/更新 Docker image
2. 部署 `bag-holder-webhook` Cloud Run Service（min-instances=0）
3. 啟動時 `entrypoint-webhook.sh` 自動向 Telegram 註冊 webhook URL

**步驟三：確認 Webhook 已設定**

```bash
# 查詢目前 webhook 狀態
curl https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

成功後，在 Telegram 頻道輸入 `買入 2330 150.5 1000` 即可觸發 Cloud Run。

### Google Sheets 欄位說明

記錄寫入後，試算表「交易記錄」工作表會包含以下欄位：

| 欄位 | 說明 |
|------|------|
| timestamp | ISO 8601 時間戳 |
| date | 交易日期 (YYYY-MM-DD) |
| time | 交易時間 (HH:MM:SS) |
| stock_code | 股票代號 |
| stock_name | 股票名稱（從 TWSE/TPEX 查詢，查無則空白） |
| action | 買入 / 賣出 |
| price | 成交價格 |
| quantity | 股數 |
| amount | 總金額（price × quantity） |
| notes | 備註（含 Telegram chat ID） |

### 範例對話

```
User:  買入 2330 150.5 1000
Bot:   ✅ 交易記錄已確認
       📈 股票: 2330
       操作: 買入
       價格: 150.50
       股數: 1,000
       金額: 150,500
       時間: 2026-04-25 14:30
       📊 已同步 Google Sheets

User:  賣出 2454 215
Bot:   ✅ 交易記錄已確認
       📉 股票: 2454
       操作: 賣出
       ...

User:  /stats
Bot:   📊 交易統計 (近30天)
       總交易數: 5
       買入: 3 | 賣出: 2
       ...
```

## 🤖 MTX 微台指自動交易

### 概述

依照 `docs/SKILL.md` 極短線策略，全自動判斷進出場並透過 Fubon e01 API 下單。

| 項目 | 說明 |
|------|------|
| 商品 | 微台指期貨（FIMTX 近月合約） |
| 日盤 | 08:45–13:30 台灣時間 |
| 夜盤 | 15:00–05:00 台灣時間（含跨日） |
| 最大口數 | 3 口 |
| 進場條件 | 日K偏多 + 5分K KD黃金交叉 + 1分K黃金交叉且收復MA5 |
| 出場條件 | 獲利 ≥ 50 點 / 停損 ≥ 30 點 / 1分K KD反向交叉 |
| 報價頻道 | Fubon WebSocket `aggregates`（日盤/夜盤自動切換） |

### 使用方式

```bash
# 自動偵測當前時段（日盤或夜盤）
python scripts/run_mtx_trader.py

# 強制指定時段
python scripts/run_mtx_trader.py --session day
python scripts/run_mtx_trader.py --session night

# 模擬模式（不下單，僅輸出訊號）
python scripts/run_mtx_trader.py --dry-run
python scripts/run_mtx_trader.py --session night --dry-run
```

### 環境變數設定

所有敏感憑證已在 `.env` 設定，非敏感參數可在 `config/settings.py` 調整。
富邦 API 憑證必填：

```
FUBON_USER_ID=<身分證字號>
FUBON_API_KEY=<API Key>
FUBON_CERT_PATH=<.p12 憑證路徑>
FUBON_CERT_PASSWORD=<憑證密碼>
FUBON_IS_SIMULATION=False   # False = 實單；True = 測試環境

# MTX Feature Toggle（非敏感，可直接設在 Cloud Run 環境變數）
MTX_LIVE_ORDER=false         # false = 模擬（寫 Google Sheets）；true = 實際下單
MTX_SIM_WORKSHEET=微台交易紀錄  # 模擬模式寫入的 Google Sheets 頁籤名稱
MTX_STOP_LOSS_PTS=15         # 停損點數（預設 15pt）
MTX_TAKE_PROFIT_PTS=50       # 停利點數
MTX_MAX_LOTS=3               # 最大持倉口數
MTX_MIN_PROFIT_BEFORE_KD_EXIT=8  # KD 叉出場前需達到的最小獲利點數（0 = 停用門檻）
MTX_LATE_SESSION_NO_ENTRY_MINUTES=30  # 距收盤 N 分鐘內禁止開新倉（0 = 停用）
```

### 策略邏輯（SKILL.md）

```
日K定方向：close > MA5 > MA10 且 KD向上 → 偏多；反之偏空
           KD > 80 → 超買警示；KD < 20 → 超賣警示

5分K確認：KD低檔（< 60）黃金交叉 或 MA5上穿MA10 → 短多
           KD高檔（> 40）死亡交叉 或 MA5下穿MA10 → 短空

1分K進場：KD黃金交叉 + close > MA5 → 做多觸發
           KD死亡交叉 + close < MA5 → 做空觸發

三層均滿足 → 送出 IOC 市價委託 1 口
```

### GCP 雲端部署（自動排程）

使用 Cloud Run Job 執行，Cloud Scheduler 每個交易日自動觸發：

| 任務名稱 | 觸發時間（台北） | 最長執行 |
|---------|----------------|---------|
| `bag-holder-mtx-trader-day` | 週一至五 08:44 | 5 小時 |
| `bag-holder-mtx-trader-night` | 週一至五 14:59 | 14.3 小時 |

部署：

```bash
cd terraform/deployable
terraform apply -target=module.job_mtx_trader_day -target=module.job_mtx_trader_night \
  -target=google_cloud_scheduler_job.mtx_trader_day \
  -target=google_cloud_scheduler_job.mtx_trader_night
```

Cloud Run Job 使用固定出口 IP（Cloud NAT），需將此 IP 加入 Fubon API Key 白名單。

---

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

### v5.16.0 - 2026-05-30

**Phase 2：IC 驗證 Pipeline**

新增 `ic-report` CLI 指令，對所有選股因子計算 IC（資訊係數），在正式使用前驗證預測力。

**使用方式：**
```bash
python main.py ic-report
python main.py ic-report --forward-days 5 10 20 --sampling-freq 5
python main.py ic-report --factors rps_3m vol_ratio --forward-days 20
```

**實際驗證結果（1981 支股票，2022-2026）：**

| 因子 | 預測期 | IC均值 | t-stat | IC>0率 | 結論 |
|---|---|---|---|---|---|
| vol_ratio | 20d | **+0.0144** | **3.77** | **63.2%** | 最強因子 |
| vol_ratio | 10d | +0.0111 | 3.04 | 57.8% | 顯著 |
| rps_6m | 20d | +0.0100 | 1.33 | 55.5% | 方向正確但不顯著 |
| momentum_20d | 全部 | 負值 | 負值 | <55% | 反效果 |
| momentum_5d | 全部 | 強負值 | -6 | 31% | 均值回歸效應 |

**關鍵發現：**
- **量能比率（vol_ratio）是全市場截面中唯一統計顯著的正向因子**（20日預測期，t=3.77）
- **RPS（相對強度）**方向正確但 t-stat 未達顯著，需更長觀察窗口
- **短期動能（5/20日）呈現負 IC**，台股有明顯均值回歸傾向，短期追漲反效果

**重要洞察（因子排名 vs IC 驗證的作用域差異）：**
IC 驗證是對全市場 1981 支股票計算截面相關，而 Phase 1 因子排名是對已通過技術訊號的
BUY 候選（30~100 支）做排名。候選池已由技術訊號完成量能篩選，在候選池中 RPS 的區分度
更高，直接套用全市場 IC 權重反而讓績效退步。**FactorEngine 維持原始權重（RPS 各 25%）。**

**新增檔案：**
- `src/application/services/ic_validator.py` — IC 計算引擎（Spearman 相關，純 Python 無需 scipy）
- `reports/ic_report.md` — IC 驗證報告輸出
- `tests/test_ic_validator.py` — 27 個單元測試

---

### v5.15.0 - 2026-05-30

**Phase 1 回測整合：因子排名接入回測引擎**

將截面因子排名（Phase 1）整合進回測流程，可在回測中驗證因子排名的實際效果。

**回測結果對比（2022-01-01 ~ 2026-05-30）：**

| 指標 | 基準（無排名） | top_n=15 | top_n=30 |
|---|---|---|---|
| 總報酬率 | 38.16% | 20.78% | 23.29% |
| 夏普比率 | 0.64 | **1.00** | 0.72 |
| 最大回撤 | 10.68% | **4.06%** | 5.61% |
| 勝率 | 53.08% | **59.04%** | 53.66% |
| 交易次數 | 422 | 83 | 164 |

**新增設定：**
```env
BACKTEST_ENABLE_FACTOR_RANKING=true   # 啟用因子排名
BACKTEST_FACTOR_RANKING_TOP_N=30      # 保留前 N 名
```

**回測起始日更新：** 2024-09-01 → 2022-01-01（更長樣本，422 次交易）

---

### v5.14.0 - 2026-05-30

**Phase 1：截面因子排名 (Factor Ranking)**

在現有技術訊號規則篩選出 BUY 候選後，新增截面因子排名層，依四個因子的綜合分數排序並保留前 N 名，提升選股品質。

**新增因子：**

| 因子 | 權重 | 說明 |
|------|------|------|
| RPS 3個月 | 25% | 股價 63 交易日報酬在候選池的百分位排名 |
| RPS 6個月 | 25% | 股價 126 交易日報酬在候選池的百分位排名 |
| 量能比率 | 20% | 今日量 / 20日均量的截面百分位 |
| 法人連續買超 | 30% | 外資×0.6 + 投信×0.4 連續買超天數截面百分位 |

**法人資料來源：** TWSE T86 API（免費），快取至 `data/cache/institutional_history/`，無需 FinMind 付費帳號。

**使用方式：**

```bash
# 啟用截面因子排名（預設關閉）
export BACKTEST_ENABLE_FACTOR_RANKING=true

# 保留前 N 名（預設 15；0 = 不限制）
export BACKTEST_FACTOR_RANKING_TOP_N=15

# 法人歷史資料天數（預設 30 自然日）
export BACKTEST_FACTOR_INST_HISTORY_DAYS=30
```

或在 `.env` 中設定：

```env
BACKTEST_ENABLE_FACTOR_RANKING=true
BACKTEST_FACTOR_RANKING_TOP_N=15
BACKTEST_FACTOR_INST_HISTORY_DAYS=30
```

啟用後，掃描結果的每支股票會附加 `factor_score`（0~1）與 `factor_detail`（各子因子分數）欄位，並依 `factor_score` 降序排列。

**新增檔案：**
- `src/application/services/factor_engine.py` — 截面因子計算引擎
- `src/infrastructure/market_data/institutional_history.py` — T86 歷史法人資料載入器
- `tests/test_factor_engine.py` — 24 個單元測試

---

### v5.13.0 - 2026-05-30

**min_holding_days 最佳值調整：5 → 21 天**

- 🔧 掃描 min_holding_days ∈ {0,3,5,7,10,14,21,30} 的5年回測結果
- 最佳化目標：Sharpe 最高 + 回撤可控

  | min_holding_days | 勝率 | 總報酬 | Sharpe | 最大回撤 |
  |:---:|:---:|:---:|:---:|:---:|
  | 5 (舊預設) | 43.3% | -16.6% | -0.40 | 22.1% |
  | 10 | 47.5% | +5.1% | +0.13 | 15.1% |
  | **21 (新預設)** | **52.4%** | **+29.1%** | **+0.40** | **19.7%** |
  | 30 | 52.4% | +31.3% | +0.39 | 20.0% |

- 21天為甜蜜點：Sharpe最高(0.40)，回撤比30天更小，勝率52.4%
- 設定：`BACKTEST_MIN_HOLDING_DAYS=21`

### v5.12.0 - 2026-05-30

**修正持倉時間過短（平均 2.1 天 → 6.4 天）**

- 🐛 **根本原因：三層出場機制皆繞過 min_holding_days**
  - SELL 訊號觸發出場（`process_signals`）未檢查 min_holding_days → 修正
  - 固定停損觸發出場（`check_position_exits`）未檢查 min_holding_days → 修正
  - Trailing stop ratcheting 在鎖定期間繼續運作 → 修正

- 🆕 **min_holding_days 語意改為硬鎖定**
  - 前 N 個日曆天：完全封鎖所有停損出場（固定停損、trailing stop、SELL 訊號）
  - 僅允許停利（Take Profit）在鎖定期間提前出場
  - 設定：`BACKTEST_MIN_HOLDING_DAYS=5`（預設 5 個日曆天）

- 🔧 **調整出場參數**
  - Trailing stop：5% → **10%**（給趨勢更多呼吸空間）
  - ATR 動態停損：停用（`atr_stop_multiplier=0`，改用固定 10% 停損）

- **5年回測結果三代對比（2021-05-30 ~ 2026-05-30）**

  | 指標 | 原始 | v5.11 改善 | v5.12 改善 |
  |------|------|-----------|-----------|
  | 總報酬率 | -83.15% | -31.95% | **-16.63%** |
  | 最大回撤 | 83.21% | 32.59% | **22.07%** |
  | 夏普比率 | -1.73 | -1.41 | **-0.40** |
  | 平均持倉天數 | 2.1 天 | 2.3 天 | **6.4 天** |
  | 獲利因子 | 0.64 | 0.67 | **0.88** |
  | 平均獲利幅度 | 4.41% | 4.48% | **8.62%** |

- ✅ 單元測試：新增 `test_min_holding_days_prevents_early_trailing_exit`，共 144 個測試通過

### v5.11.0 - 2026-05-30

**訊號系統全面翻新 + 多訊號確認進場**

- 🐛 **修正 RSI Oversold 悖論（Filter 5 平均回歸豁免）**
  - `RSI Oversold` 訊號在定義上於 RSI < 30 時觸發，但 Filter 5 要求 RSI ≥ 60 進場
  - 修正：新增 `MEAN_REVERSION_SIGNALS` 類別變數，平均回歸訊號豁免 RSI min entry 門檻
  - 設定：可擴充（目前包含 `RSI Oversold`）

- 🐛 **修正 BB Squeeze Break / Volume Surge 被 MA 對齊過濾器封鎖**
  - `BB Squeeze Break` 與 `Volume Surge` 均為突破型訊號，不應受 MA5 > MA10 > MA20 限制
  - 修正：將兩者加入 `TREND_SIGNAL_NAMES`，與 Donchian Breakout 同等待遇（跳過 Filter 4）
  - 效果：`BB Squeeze Break` 從 0 交易 → **431 筆交易（勝率 42.9%）**

- 🆕 **多訊號確認進場（Filter 15）**
  - 要求同一天同一股票有 **≥ N 個獨立 BUY 訊號**才進場，大幅降低假突破率
  - 預設 `BACKTEST_MIN_CONFIRMING_SIGNALS=2`（2 個訊號確認）
  - 設定：`BACKTEST_MIN_CONFIRMING_SIGNALS`（1 = 停用，2 = 雙訊號確認）

- 🔧 **延長持倉周期**
  - `max_holding_days` 從 15 天 → **30 天**（讓趨勢有更多發展空間）
  - `trailing_stop_pct` 從 3% → **5%**（減少過早止損）

- 🆕 **重新啟用 BB Squeeze Break**
  - 從 `disabled_signals` 移除 `BB Squeeze Break`
  - 同步更新 `.env` 與 `config/settings.py` 預設值

- **5年回測結果對比（2021-05-30 ~ 2026-05-30）**

  | 指標 | 修改前 | 修改後 |
  |------|--------|--------|
  | 總報酬率 | -83.15% | **-31.95%** (+51.2%) |
  | 最大回撤 | 83.21% | **32.59%** |
  | 夏普比率 | -1.73 | **-1.41** |
  | 勝率 | 40.80% | **43.10%** |
  | BB Squeeze Break 交易 | 0 次 | **431 次** |
  | Donchian Breakout 勝率 | 40.9% | **44.5%** |

- ✅ 單元測試：新增 4 個測試（`test_trend_signals_skip_ma_alignment`、`test_rsi_oversold_exempt_from_rsi_min_entry`、`test_min_confirming_signals_blocks_single_signal`、`test_min_confirming_signals_allows_two_signals`），共 143 個測試通過

### v5.10.0 - 2026-05-29
- 🆕 **Minervini 52 週高低點過濾（Filter 9）**
  - 新增 `require_52w_filter`（預設 `True`）：股價需在 52 週低點 30% 以上，且距 52 週高點不超過 35%
  - 設定：`BACKTEST_REQUIRE_52W_FILTER`, `BACKTEST_ABOVE_52W_LOW_PCT`（預設 0.30），`BACKTEST_NEAR_52W_HIGH_PCT`（預設 0.35）
  - 回測驗證：啟用後報酬由 49.14% → 51.87%，同時維持勝率與夏普比率

- 🆕 **族群動能排名式過濾（可選）**
  - `SectorTrendAnalyzer` 新增 `compute_sector_momentum()`：計算各族群近期平均漲幅
  - `get_strong_sectors_by_momentum(top_pct=0.20)`：取前 N% 強勢族群（取代二元 MA20 門檻）
  - 設定：`BACKTEST_SECTOR_USE_MOMENTUM`（預設 `False`），`BACKTEST_SECTOR_MOMENTUM_LOOKBACK_DAYS`（60），`BACKTEST_SECTOR_TOP_PCT`（0.20）

- 🆕 **VCP 收縮形態偵測（可選）**
  - `_detect_vcp()` 偵測 Volatility Contraction Pattern：波動率與成交量收縮，視為進場訊號
  - 設定：`BACKTEST_ENABLE_VCP`（預設 `False`），`BACKTEST_VCP_LOOKBACK`（60）

- 🆕 **CANSLIM EPS 過濾（signals_scanner 專用）**
  - `FinMindEpsLoader`：透過 FinMind API 取得台股季 EPS 歷史，計算同季 YoY 成長率
  - 設定：`BACKTEST_ENABLE_EPS_FILTER`（預設 `False`），`BACKTEST_MIN_EPS_YOY_PCT`（預設 25.0%）
  - 注意：僅於即時訊號掃描（signals_scanner）使用，回測不支援

- ✅ 單元測試：新增 26 個測試（`Test52WFilter`、`TestVCPDetection`、`TestSectorMomentumWhitelist`、`TestComputeSectorMomentum`、`TestGetStrongSectorsByMomentum`），共 715 個測試通過

### v5.9.0 - 2026-05-28
- 🆕 **Option B：周線趨勢確認過濾（Filter 8）**
  - `TechnicalStrategy` 新增 `require_weekly_trend` 參數（預設 `False`）
  - 啟用後要求**周線 MA5 > MA20**才允許進場，過濾日線假突破（周線空頭中的個股）
  - 周線定義：每個 ISO 週最後一個交易日的收盤價，MA5 = 5週均線（約1個月），MA20 = 20週均線（約5個月）
  - 設定：`BACKTEST_REQUIRE_WEEKLY_TREND=true`（`.env`）或 `config/settings.py` 中 `require_weekly_trend`
  - 新增 11 個單元測試（`TestWeeklyTrendFilter`、`TestFinMindSettings`）

- 🆕 **Option A：FinMind 歷史財務資料客戶端**
  - 新增 `src/infrastructure/market_data/finmind_client.py`
    - `FinMindRevenueLoader`：取得歷史月營收（含 YoY 計算），供回測各日期精確查詢
    - `FinMindInstitutionalLoader`：取得歷史三大法人資料，計算**外資/投信連續買超天數**
  - 當日磁碟快取（`data/cache/finmind_*.json`），避免重複 API 呼叫
  - 設定：`FINMIND_API_TOKEN`（免費帳號，finmindtrade.com 註冊，每小時 600 次請求）

- 🆕 **法人連續買超設定**
  - `BacktestSettings` 新增：
    - `institutional_consecutive_min_days`（預設 0，停用）
    - `institutional_trust_consecutive_min_days`（預設 0，停用）
  - 搭配 `enable_institutional_filter=True` 與 FinMind token 使用

### v5.8.9 - 2026-05-21
- 🐛 **修正盤中 /scan 結果不一致（有時 0 支、有時正常）**：兩個根本原因同步修復
  - **`entrypoint-download.sh` 空目錄上傳 GCS**：若 `tar xzf` 解壓失敗（磁碟空間、corrupt archive），腳本因 `||` 繼續執行，最終把空的 `stocks/` 打包上傳至 GCS，覆蓋正常資料，導致下次 signals job 讀到 0 支股票；改為在上傳前檢查 CSV 檔案數量，低於 1000 支時跳過上傳保留既有 GCS 資料
  - **AI provider 未設 `temperature=0`**：同樣的訊號輸入，AI 分類（buy/watch/avoid）每次略有不同，導致「推薦 0 支」vs「正常結果」的隨機差異；所有四個 provider（Claude、OpenAI、OpenRouter、Gemini）均加入 `temperature=0`
  - 修正 `tests/test_mtx_auto_trader.py::test_long_signal_reverses_short`：測試在尾盤時段執行時因 `_is_late_session=True` 被誤封鎖，加入 `late_session_no_entry_minutes=0` 隔離測試範圍

### v5.8.14 - 2026-05-22
- ✅ **新增 `_load_stock_data` 最新交易日邏輯回歸測試（5 個測試案例）**
  - `test_fubon_intraday_today_data_is_used_as_latest`：Fubon 盤中資料在盤中時段應選為 latest（確保不被二次過濾）
  - `test_yfinance_only_previous_day_data_gives_correct_latest`：CSV 只有前一交易日時 latest 正確回傳
  - `test_weekend_dates_are_skipped`：週末資料應跳過，latest 取最近工作日
  - `test_no_time_of_day_filter_applied`：確認 signals_scanner 不依賴當下時間決定 latest
  - `test_old_bug_would_filter_today_before_14`：明確重現舊 Bug（盤中舊邏輯給前一日），驗證新版已修復

### v5.8.13 - 2026-05-22
- 🐛 **修正盤中排程（09:30~12:30）持續收到前一交易日訊號的問題**
  - 根本原因：`signals_scanner._load_stock_data()` 在 14:00 前會過濾掉當日資料，但 Fubon 下載端已透過 `allow_today=True` 將當日盤中真實成交資料寫入 CSV；此重複過濾導致盤中訊號永遠顯示前一日
  - 修正：移除 `signals_scanner` 的盤前今日過濾邏輯，改由下載端統一控制（yfinance 盤前前填過濾 + Fubon `allow_today=True` 寫入真實盤中資料）
- 🔧 **修正 CI/CD TA-Lib 安裝失敗**
  - `requirements.txt` 使用 TA-Lib==0.6.8，已內建 C 函式庫；移除 CI/CD 中手動從 sourceforge 安裝舊版 TA-Lib 0.4.0 C library 的步驟（版本不相容導致建置失敗）

### v5.8.12 - 2026-05-22
- ⚡ **MTX 停損從 15pt 改回 30pt**（`MTX_STOP_LOSS_PTS`）
  - 回測（TAIFEX 前 30 交易日）顯示 15pt 停損勝率 49.3%、淨損益 -846元；30pt 停損勝率 60.8%、淨損益 +6,788元
  - 15pt 停損過緊導致被洗掉次數更多，手續費侵蝕後反而虧損

### v5.8.11 - 2026-05-22
- 🐛 **修正 IOC 未成交後同一根 1m K 棒內重複送單**
  - IOC 未成交時，同一根 1m K 棒每個 tick 都會觸發進場條件（`golden_cross` 持續為 True），導致幾秒內重複送出數十張委託
  - 修正：IOC 未成交時記錄當前 1m K 棒時間戳（`_ioc_failed_bar_ts`），下一根 K 棒前封鎖所有進場嘗試
  - Telegram 通知新增「本根K棒不再重試」提示
  - 新增 4 個單元測試：`TestIOCFillValidation.test_ioc_unfilled_sets_cooldown`、`test_ioc_cooldown_blocks_next_entry`、`test_ioc_cooldown_expires_next_bar`

### v5.8.10 - 2026-05-22
- 🐛 **修正 IOC 未成交時仍建立倉位的 bug**
  - 原本 `_open_position` 在 `place_futures_order` 回傳後不檢查 `filled_lot`，即使 IOC 0口成交也會設定 `self.position`，導致後續平倉指令試圖平一個不存在的倉
  - 修正：`filled_lot == 0` → 不設 position，發送 Telegram 警告
  - 修正：`filled_lot < requested` → position 使用實際成交口數，而非請求口數
  - 修正：進場價改用 `filled_money / filled_lot` 實際成交均價，`filled_money=0` 時才 fallback 至 signal 報價（修正夜盤滑價導致損益計算偏差）
  - 新增 4 個單元測試：`TestIOCFillValidation`

### v5.8.9 - 2026-05-22
- ⚡ **MTX 5m 信號記憶參數化** — 新增 `signal_5m_memory_bars` 參數，預設 0（嚴格模式）
  - 回測（TAIFEX 前 30 交易日 tick，60 sessions）比較 4 種策略，手續費 44元/次、1pt=10元：
    - 策略A（嚴格，預設）：淨損益 **+6,788元**，勝率 60.8%，613 次
    - 策略C（記憶3根）：淨損益 +2,996元，勝率 60.2%，906 次
    - 結論：手續費考量下嚴格模式反而更賺，多進場次數被手續費侵蝕
  - `signal_5m_memory_bars > 0` 可啟用記憶模式（若未來降低手續費可重新評估）
  - 新增 `scripts/backtest_mtx_strategies.py`：可從 TAIFEX tick zip 重建分鐘K，比較4種策略變體
  - 新增 2 個單元測試：`test_5m_signal_memory_keeps_signal_active`、`test_5m_signal_memory_zero_is_strict_mode`

### v5.8.8 - 2026-05-21
- 🐛 **修正 Cloud Run 盤中 download job 不更新今日資料**：兩個根本原因同步修復
  - **`closePrice = 0`（盤中）**：`FubonDownloadClient.download_snapshot()` 只讀 `closePrice`，但 Fubon API 在收盤前 `closePrice` 為 0；改用 `closePrice or lastPrice` 作為 close，並跳過兩者皆 0 的無效行
  - **`save_stock_data()` 盤前濾鏡**：`yfinance_client.py` 有 `_before_close` 邏輯，14:00 前丟棄所有今日資料（原為防 yfinance 前填假資料），但也連 Fubon snapshot 的盤中資料一起丟掉；新增 `allow_today: bool = False` 參數，`download_snapshot()` 傳 `True` 繞過此濾鏡
  - 更新 `FubonDownloadClient.save_stock_data()` 透傳 `allow_today` 至 `YFinanceClient.save_stock_data()`
  - 新增 7 個單元測試：`TestSnapshotIntradayFix` + `TestSaveStockDataAllowToday`

### v5.8.7 - 2026-05-21
- ⚡ **MTX 策略改進 — 修正 R:R 不對稱、尾盤過濾**
  - **停損縮小 30pt → 15pt**（`MTX_STOP_LOSS_PTS`）：原本 KD 出場平均 +4pt 獲利卻承擔 30pt 停損，R:R 達 1:7.5；縮小停損使 R:R 更合理
  - **KD 出場最小獲利門檻 8pt**（`MTX_MIN_PROFIT_BEFORE_KD_EXIT`）：1mKD 死叉/黃金叉出場前需 PnL ≥ 8pt，避免 +2pt 就出場但停損仍高達 15pt；不足時繼續持倉等停損或停利
  - **尾盤禁開倉 30 分鐘**（`MTX_LATE_SESSION_NO_ENTRY_MINUTES`）：日盤 13:01 後、夜盤 04:31 後禁止開新倉（平倉不受影響），防止類似昨日 04:52 進場 8.5 分鐘後被停損 -30pt 的情況
  - 三項參數均可透過 `.env` 覆蓋，詳見下方「MTX 進階設定」
  - 新增 16 個單元測試：`TestMinProfitKDExitGuard` + `TestLateSessionFilter`

### v5.8.6 - 2026-05-20
- 🐛 **修正微型臺指 symbol root `FIMTX` → `TMF`**：`FIMTX` 在 Fugle API 不存在，WebSocket 訂閱雖不報錯但永遠沒有 tick 資料；正確 product code 為 `TMF`（微型臺指期貨），近月合約 `TMFF6` 可正常訂閱並收到行情

### v5.8.5 - 2026-05-20
- 🐛 **修復 WebSocket 重連 — 正確事件名稱 + reconnect 先 disconnect**：三個根本問題同步修復
  - `on("open")` 應為 `on("authenticated")`，`on("close")` 應為 `on("disconnect")`（fugle SDK 用 pyee，事件名稱為 `"connect"/"disconnect"/"authenticated"`）
  - 因事件名稱錯誤，`ws_connected` 從未設為 `True`，導致每 10 秒持續觸發重連，引發 `WebSocketException: socket is already opened`
  - 重連前先呼叫 `disconnect()` + `sleep(1)`，讓舊 `run_forever` 執行緒退出後再重建連線

### v5.8.7 - 2026-05-30
- 🐛 **修正 CI 測試失敗（BACKTEST_DISABLED_SIGNALS 與 production config 不一致）**：`settings.py` 的 `disabled_signals` 預設值從 `""` 改為 `"BB Squeeze Break"`，使 CI 環境（無 `.env`）與生產設定一致
- 🐛 **修正測試寫入 Google Sheets「交易記錄」頁籤**：
  - `GoogleSheetsRecorder` 新增 `worksheet_name` constructor 參數（與 `MTXSheetsRecorder` 一致），允許測試指定目標頁籤
  - `tests/conftest.py` 頂端加入 `os.environ.setdefault("GOOGLE_SHEETS_WORKSHEET_NAME", "單元測試")`，確保所有測試寫入「單元測試」頁籤而非「交易記錄」
  - 733 個單元測試全數通過

### v5.8.6 - 2026-05-30
- 🐛 **修復 Fubon 非交易日下載失敗導致 GCP Workflow 中斷**：週六/假日 Fubon WebSocket 不開放，`download` Job 以 exit(1) 失敗，整個 workflow 停止
  - 更新 `src/interfaces/cli/download_main.py`：Fubon 下載失敗時自動 fallback 至 yfinance，只有兩個 source 都失敗才以 exit(1) 退出
  - 更新 `scripts/diagnose_filters.py`：新增 Scenario 9（Donchian Only，停用 BB Squeeze Break）作為最新生產設定
  - 733 個單元測試全數通過

### v5.8.5 - 2026-05-29
- 🔧 **signals_scanner 策略參數與 backtest 完整同步**：`SignalsScanner` 建構 `TechnicalStrategy` 時新增傳入所有缺漏參數，確保即時掃描與回測採用相同策略邏輯
  - 補齊參數：`rsi_overbought_threshold`、`min_volume_lots`、`pre_breakout_mode`、`enable_momentum_signal`、`momentum_signal_days`、`momentum_signal_min_return`、`require_weekly_rsi`、`weekly_rsi_min`、`require_revenue_growth`、`revenue_yoy_min_pct`、`finmind_api_token`、`require_minervini_trend`
  - `weekly_close_only` 刻意不傳入（即時掃描不適用「只在週五進場」的日期門檻）
  - 733 個單元測試全數通過

### v5.8.4 - 2026-05-20
- 🐛 **修復 MTX WebSocket 斷線後不重連**：夜盤連線約 30 分鐘後 Fubon 伺服器送 `Connection reset by peer`，原本無重連邏輯，整個盤收不到 tick，導致 0 訊號
  - 更新 `src/application/services/mtx_auto_trader.py`：加入 `on_error` / `on_close` callback 設 `ws_connected=False`；main loop 每 10 秒偵測並自動重連（`_ws_connect()` 重新 `connect` + `subscribe`）
- 🐛 **修復 `--session day` 啟動後立刻退出**：main loop 以 `get_session() == CLOSED` 偵測結束，但 08:45 前啟動時（如 08:31）回傳 CLOSED，導致剛連上 WebSocket 就退出
  - 更新 `src/application/services/mtx_auto_trader.py`：改以 `_session_should_end()` 邏輯取代——日盤以 `>= 13:31`、夜盤以 `05:01–08:44` 為結束條件，開盤前啟動不再提早退出
  - 新增 10 個迴歸單元測試（`tests/test_mtx_auto_trader.py`）：`TestSessionEndCondition` + `TestWebSocketReconnect`

### v5.8.3 - 2026-05-20
- 🐛 **修復 run_mtx_trader.py 輸出空白（腳本看似當掉）**：未呼叫 `setup_logging`，Python 預設只輸出 WARNING+，INFO 訊息全被吃掉，導致 WebSocket 訂閱成功後畫面靜止
  - 更新 `scripts/run_mtx_trader.py`：加入 `logging.basicConfig(INFO)` 初始化，輸出格式 `HH:MM:SS LEVEL name — msg`
  - 更新 `src/application/services/mtx_auto_trader.py`：WebSocket 訂閱成功改用 `logger.warning` 輸出 `✅ WebSocket 已訂閱...`，讓使用者確認腳本存活
  - 更新 `src/infrastructure/market_data/fubon_client.py`：Candles seed 失敗（404/403 換約日預期錯誤）降為 `logger.debug`，不再汙染輸出

### v5.8.2 - 2026-05-20
- 🐛 **修復 MTX WebSocket 啟動失敗**：`fubon_neo` SDK 預設以 Speed 模式初始化，但 Speed 模式不支援 `aggregates` 頻道，導致 `run_mtx_trader.py` 啟動即崩潰
  - 更新 `src/infrastructure/market_data/fubon_client.py`：`_initialize_sdk` 改為 `sdk.init_realtime(Mode.Normal)`，允許訂閱 `aggregates` / `candles` 頻道
- 🐛 **修復每日 K 線請求錯誤**：`historical/candles` 需付費方案（403）；改用 `historical.daily()` 端點
  - 更新 `src/infrastructure/market_data/fubon_client.py`：`timeframe='D'` 改呼叫 `restfutopt.historical.daily(symbol=...)`；Seed 失敗降為 `warning` 層級
- 🐛 **修復換約日夜盤 Seed 404**：新近月合約換約當日無 `afterhours` 歷史 K 線（404），Seed 結果為空
  - 更新 `src/application/services/mtx_auto_trader.py`：`_seed_bars` 夜盤 afterhours 回傳空時，自動 fallback 至一般盤資料

### v5.8.1 - 2026-05-20
- 🔀 **MTX Feature Toggle（`MTX_LIVE_ORDER`）**：透過環境變數切換模擬 vs 實單模式，預設模擬
  - 新增 `src/infrastructure/persistence/mtx_sheets_recorder.py`：`MTXSheetsRecorder` 將模擬進出場記錄寫入 Google Sheets「微台交易紀錄」頁籤，13 欄位（timestamp / session / symbol / direction / action / price / lots / pnl_pts / pnl_twd / reason / mode），lazy 初始化 worksheet
  - 更新 `src/application/services/mtx_auto_trader.py`：`_open_position` / `_close_position` 三路分派——`dry_run=True` → 略過全部；`live_order=False`（模擬）→ 寫 Sheets；`live_order=True` → 呼叫 Fubon API
  - 更新 `config/settings.py`：新增 `MTXTraderSettings`，對應環境變數 `MTX_LIVE_ORDER`（bool，預設 false）、`MTX_SIM_WORKSHEET`（預設「微台交易紀錄」）、`MTX_STOP_LOSS_PTS`（預設 30）、`MTX_TAKE_PROFIT_PTS`（預設 50）、`MTX_MAX_LOTS`（預設 3）
  - 更新 `docker/Dockerfile.cloudrun`：加入 `run_mtx_trader.py` 與 `entrypoint-mtx-trader.sh`
  - 新增 24 個單元測試（`tests/test_mtx_sheets_recorder.py`）覆蓋三種模式路由；74/74 通過

### v5.8.0 - 2026-05-19
- 🤖 **MTX 微台指自動交易系統**：依 SKILL.md 多重時間框架策略（日K + 5分K + 1分K KD + MA）全自動進出場，支援日盤（08:45–13:30）與夜盤（15:00–05:00）
  - 新增 `src/application/services/mtx_signal_engine.py`：`BarManager`（逐 tick 建立 OHLCV）、`compute_stoch`（KD 9/3/3）、`compute_ma`、`golden_cross` / `death_cross` 偵測、`MTXSignalEngine` 三層訊號評估（日K偏多 + 5分K黃金交叉 + 1分K收復MA5 → 做多；反之做空）
  - 新增 `src/application/services/mtx_auto_trader.py`：`MTXAutoTrader` 服務，訂閱 Fubon WebSocket `aggregates` 頻道（日盤 `afterHours=False` / 夜盤 `afterHours=True`）；最多 3 口倉位；IOC 市價單進出場；Telegram 推播所有委託通知
  - 更新 `src/infrastructure/market_data/fubon_client.py`：`place_futures_order` 新增 `is_night_session` 參數，夜盤自動使用 `FutOptMarketType.FutureNight`
  - 新增 `scripts/run_mtx_trader.py`：CLI 入口（`--session day|night|auto` / `--dry-run`）
  - 新增 `docker/entrypoint-mtx-trader.sh`：Cloud Run Job Docker entrypoint
  - 新增 50 個單元測試（`tests/test_mtx_auto_trader.py`）
  - Terraform：新增 Cloud Run Job `bag-holder-mtx-trader-day`（日盤）與 `bag-holder-mtx-trader-night`（夜盤）及對應 Cloud Scheduler 觸發（`44 8 * * 1-5` / `59 14 * * 1-5` 台北時間）

### v5.6.0 - 2026-05-08
- 📊 **Telegram `/pnl` 指令**：在 Telegram 輸入 `/pnl` 即可查看未實現損益與已實現損益摘要，格式針對手機閱讀最佳化
  - 更新 `src/infrastructure/persistence/google_sheets_reader.py`：`get_pnl_summary()` 直接讀取「未實現損益」（Apps Script 即時股價）與「已實現損益」兩個專屬工作表，不再呼叫 yfinance；新增 `unrealized_pnl_worksheet_name`（預設「未實現損益」）與 `realized_pnl_worksheet_name`（預設「已實現損益」）設定
  - 更新 `src/infrastructure/notification/telegram_trade_bot.py`：新增 `handle_pnl_command()`，`process_telegram_command()` 加入 `/pnl` 分派，`/help` 加入 `/pnl` 說明
  - 更新 `src/interfaces/api/webhook_app.py`：`/pnl` 以 background task 執行（同 `/scan`）；新增 `_send_sync()` 使用 sync httpx，並在 Telegram Markdown 解析失敗（400）時自動 fallback 純文字重試，避免訊息靜默消失
  - 新增 `tests/test_google_sheets_reader_pnl.py`：14 個 P&L 計算單元測試
  - 更新 `tests/test_trade_bot_commands.py`：新增 11 個 `/pnl` 指令測試
  - 更新 `tests/test_webhook_handler.py`：新增 `/pnl` background task 與 `_send_sync` fallback 測試

### v5.7.0 - 2026-05-13
- 🕑 **調整每日主排程時間 08:05 → 14:40**：配合台股收盤後（13:30）取得完整當日資料，Cloud Scheduler `bag-holder-run-jobs-trigger` cron 由 `5 8 * * 1-5` 改為 `40 14 * * 1-5`
- 🏦 **新增 Fubon 今日成交記錄同步至 Google Sheets（`sync-trades`）**：每日 14:35（收盤約一小時後）自動呼叫 Fubon Neo API `sdk.stock.get_order_results()` 查詢當日所有已成交委託，逐筆寫入 Google Sheets「交易記錄」頁籤
  - 新增 `src/application/services/fubon_trades_syncer.py`：`FubonTradesSyncer` 服務；登入 Fubon SDK → 取今日委託 → 過濾 `filled_qty > 0` → 透過 `GoogleSheetsRecorder` 寫入
  - 新增 `src/interfaces/cli/sync_trades_main.py`：CLI 入口（`python main.py sync-trades`）
  - 新增 `docker/entrypoint-sync-trades.sh`：Cloud Run Job entrypoint
  - 新增 `terraform/deployable/run-sync-trades.workflow.yaml`：GCP Workflow 定義
  - Terraform：新增 Cloud Run Job `bag-holder-sync-trades`、GCP Workflow `bag-holder-sync-trades`、Cloud Scheduler `bag-holder-sync-trades-trigger`（14:35 週一至五）
  - 新增 14 個單元測試（`tests/test_fubon_trades_syncer.py`）

### v5.5.0 - 2026-05-08
- 📲 **Telegram `/scan` 指令**：在 Telegram 輸入 `/scan` 即可手動觸發 GCP download + signals 工作流程，結果自動推送至 Telegram
  - 新增 `src/infrastructure/gcp/workflow_trigger.py`：`GcpWorkflowTrigger`，使用 `google-auth` ADC 呼叫 GCP Workflows REST API
  - 更新 `src/infrastructure/notification/telegram_trade_bot.py`：新增 `handle_scan_command()`，`process_telegram_command()` 加入 `/scan` 分派
  - 更新 `src/interfaces/api/webhook_app.py`：`/scan` 以 FastAPI `BackgroundTasks` 執行，Telegram 立即收到確認回覆
  - 新增 `config/settings.py`：`GCP_WORKFLOW_NAME`（預設 `bag-holder-run-jobs`）、`GCP_WORKFLOW_LOCATION`（預設 `asia-east1`）兩個可選設定
  - 新增 9 個單元測試（`tests/test_gcp_workflow_trigger.py`）

### v5.4.0 - 2026-04-30
- 🏦 **新增富邦 API 資料來源**：`download` 指令新增 `--source fubon` 參數，可切換至富邦 Neo API 下載歷史股價，預設仍為 yfinance
  - 新增 `FubonDownloadClient`：同步客戶端，支援 `apikey_login` / `login` 兩種登入方式
  - 與 `YFinanceClient` 相同介面（`download_all_stocks`, `download_recent_data`, `get_last_trading_date`），可無縫切換
  - 內建速率限制（預設 30 req/min），適合夜間批次下載
  - CSV 存檔格式與 yfinance 相同，兩者資料可共用同一目錄
  - 新增 `DOWNLOAD_DATA_SOURCE` 環境變數，可設定全域預設資料來源
  - 新增 18 個單元測試覆蓋登入、資料取得、批次下載等情境

### v5.3.1 - 2026-04-28
- 🐛 **修正 GCP Workflows YAML 解析錯誤**：`raise` 值中含冒號（`status: `）導致 YAML parser 截斷 `${...}` 表達式，以單引號包覆修正

### v5.3.0 - 2026-04-27
- ☁️ **新增 Terraform IaC GCP 部署**：以 Terraform 管理所有 GCP 資源，CI/CD 自動 `terraform apply`
  - `terraform/bootstrap/`：一次性基礎建設（GCS backend bucket、Runner Service Account、IAM 權限）
  - `terraform/deployable/`：Cloud Run Jobs（download / signals）、Cloud Run Service（webhook）、GCP Workflows、Cloud Scheduler
  - `terraform/modules/cloud_run_job/` & `cloud_run_service/`：可複用模組，統一 secret / env var 注入
  - GCP Workflows `run-jobs.workflow.yaml`：依序執行 download → signals，失敗即 raise 中斷
  - Cloud Scheduler 設定 UTC 00:05 週一至五（台北時間 08:05）自動觸發
  - GitHub Actions `deploy.yml` 新增 `terraform init / plan / apply` 步驟

### v5.2.0 - 2026-04-25
- 🚀 **Telegram Webhook + Cloud Run Service（方案 A）**
  - 新增 `src/application/use_cases/handle_telegram_webhook.py`：Application 層 Use Case，協調 webhook 事件處理
  - 新增 `src/interfaces/api/webhook_app.py`：FastAPI HTTP adapter，接收 Telegram webhook POST
  - 新增 `docker/entrypoint-webhook.sh`：自動向 Telegram 註冊 webhook URL 後啟動 uvicorn
  - 更新 `docker/Dockerfile.cloudrun`：加入 webhook entrypoint
  - 更新 `.github/workflows/deploy.yml`：自動部署 `bag-holder-webhook` Cloud Run Service（min-instances=0，幾乎免費）
  - 支援 `X-Telegram-Bot-Api-Secret-Token` header 驗證，防止偽造請求
  - 新增 11 個單元測試（`tests/test_webhook_handler.py`）

### v4.3.0 - 2026-04-14
- 🔍 **賣出警示新增月營收過濾**：`signals` 指令的賣出清單現在也會套用 `min_monthly_revenue_million` 門檻，只顯示通過營收門檻股票的賣出訊號（與買入過濾邏輯一致）

### v4.2.0 - 2026-04-11
- ⚡ **下載批次大小從 100 → 200**：`download_all_stocks` 預設 `batch_size` 由 100 提升至 200，減少批次數量加速下載
- 🗂️ **設定集中管理**：`.env` 僅保留機敏憑證（Fubon API Key/Secret、Telegram Token/Chat ID、Secret Key），所有非機敏參數（策略參數、回測設定、應用程式設定等）改由 `config/settings.py` 管理
- 🆕 **新增 `DownloadSettings`**：`DOWNLOAD_BATCH_SIZE`（預設 200）可透過環境變數覆蓋

### v5.1.1 - 2026-04-24
- 🆕 **AI 二次過濾新增 OpenRouter provider**：`AI_PROVIDER=openrouter`
  - 使用 OpenAI 相容 API 串接 OpenRouter，預設模型 `google/gemini-2.5-flash-preview`
  - 設定 `OPENROUTER_API_KEY` 即可使用，支援所有 OpenRouter 上的模型
  - 新增 2 個單元測試覆蓋 openrouter factory 建立

### v5.1.0 - 2026-04-23
- 🆕 **AI 二次過濾**：`python main.py signals --ai-filter`
  - 在 P1 技術訊號篩選後，透過 AI API 對 buy + watch 清單進行綜合分析
  - 重新分級為：🔥 強烈建議買入 / ✅ 建議買入 / 👀 觀察 / ⛔ 不建議，每支附一行中文理由
  - Telegram 訊息採用手機友善格式（`--ai-filter --send-telegram`）
  - 支援 Claude / OpenAI / Gemini / OpenRouter，透過 `AI_PROVIDER` 設定切換
  - 抽象架構：`BaseAIAnalyzer`（base.py）+ 各 provider 只需實作 `_analyze_batch()`
  - `factory.create_analyzer(provider, api_key, model)` 統一建立實例
  - 新增 `AIAnalyzerSettings`（`AI_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `AI_MODEL`）
  - 20 個單元測試全數通過

### v5.0.0 - 2026-04-21
- 🚀 **富邦 e01 期貨 API 完整串接**
  - 安裝 `fubon_neo` SDK v2.2.8 (macOS ARM64)
  - 登入方式改為正確的 `apikey_login(user_id, api_key, cert_path, cert_password)`
  - `FubonClient` 新增期貨行情方法：`get_futures_quote()`, `get_futures_tickers()`, `get_futures_candles()`
  - `FubonClient` 新增期貨下單方法：`place_futures_order()`, `cancel_futures_order()`, `get_futures_orders()`
  - `FubonClient` 新增期貨帳務方法：`get_futures_positions()`, `get_futures_margin_equity()`
  - `TaiwanFuturesMonitor._get_futures_quote()` 改為呼叫真實 API（自動計算近月合約代號 e.g. TXFE6）
  - 新增 `get_near_month_symbol(product)` 工具函式自動計算近月合約代號
  - 新增 `scripts/test_fubon_futures.py` 完整測試腳本（連線、報價、部位、下單）
  - 更新 `.env` 模板並填入 API Key、憑證路徑
  - 更新 `config/settings.py` 中 `has_api_key_auth()` 邏輯
  - 新增 30 個期貨 API 單元測試（含 `get_near_month_symbol` 和 `FubonClient` mock 測試）

#### 期貨 API 使用方式

```python
from src.api.fubon_client import FubonClient, get_near_month_symbol

async with FubonClient(
    user_id="身分證字號",
    api_key="API_KEY",
    cert_path="/path/to/cert.p12",
    cert_password="憑證密碼",  # 預設與身分證字號相同
) as client:
    # 查詢近月合約代號
    symbol = get_near_month_symbol('TXF')  # e.g. 'TXFE6'

    # 查詢期貨報價
    quote = await client.get_futures_quote(symbol)

    # 查詢期貨部位
    positions = await client.get_futures_positions()

    # 查詢帳戶權益
    equity = await client.get_futures_margin_equity()

    # 期貨下單（限價委託）
    result = await client.place_futures_order(
        symbol=symbol, buy_sell='Buy', price='20000', lot=1
    )
```

#### 測試腳本

```bash
source venv/bin/activate
python scripts/test_fubon_futures.py --user-id A123456789 --no-trade
```

### v4.1.0 - 2026-04-09
- ⚡ **`backtest` 新增 `--skip-download` 參數**：略過自動下載資料，直接使用本地 `data/stocks/` 資料，加速重跑回測

### v4.0.0 - 2026-04-09
- 🏭 **新增族群趨勢過濾器**：`signals` 指令新增第 6 道進場過濾，只保留強勢族群的買入訊號
  - 依股票代碼前兩碼自動分組（20+ 族群：水泥、食品、塑膠、紡織、電機、航運、金融、半導體等）
  - 族群強度 = 族群內收盤 > MA20 的股票比例，≥ 50% 視為強勢
  - 弱勢族群的買入訊號移入觀察清單，標示「族群偏弱（XXX）」
  - 買入清單新增族群欄位；Telegram 及終端輸出新增族群強弱摘要（強勢 N / 弱勢 N 族群）
  - 族群過濾數不足（< 3 支）時自動豁免過濾，避免小族群誤判
- ⚙️ 新增設定：`BACKTEST_ENABLE_SECTOR_TREND_FILTER=true`、`BACKTEST_SECTOR_TREND_THRESHOLD=0.5`
- ✅ 新增 `tests/test_sector_trend.py` 共 24 個單元測試覆蓋代碼分組、強度計算、強弱判斷、摘要排序

### v3.9.0 - 2026-04-09
- 🔒 **回測新增成交量門檻過濾（Filter 6）**：進場訊號需當日成交張數 ≥ 1000 張（1,000,000 股），排除流動性不足個股
- 📈 **回測績效大幅提升**：加入此過濾後 P1 策略報酬率從 -1.84% → **+34.10%**，勝率 47.5% → **51.64%**，最大回撤 31.93% → **8.82%**，夏普比率達 **1.20**
- ⚙️ 可透過 `.env` 設定 `BACKTEST_MIN_VOLUME_LOTS=1000`（0 = 停用）
- ✅ 新增 3 個 `TestTechnicalStrategy` 單元測試覆蓋門檻過濾、邊界值、停用情境

### v3.10.0 - 2026-04-30
- 📥 **新增 Fubon API 資料來源**：`python main.py download --source fubon` 可透過富邦 Neo API 下載今日台股快照資料
  - 預設仍使用 yfinance；`--source fubon` 可切換至 Fubon API
  - 快照模式：單次 2 API 請求取得全市場資料，速度比 yfinance 快 ~160 倍（0.27s vs 42.9s）
  - 支援 TSE / OTC / TIB（臺灣創新板）三市場，與 yfinance 股票覆蓋率一致（~1967 檔）
  - 多日歷史資料採 `ThreadPoolExecutor` 並發下載，速率限制 30 req/min 防觸發 API 限流
  - 成交量單位修正：Fubon 快照 `tradeVolume` 為「張」（1 張 = 1000 股），自動 ×1000 轉換為「股」與 yfinance 一致
  - TIB 市場修正：TWSE 含 TIB 於 TSE 下，Fubon 需額外 `market='TIB'` 查詢，修正後不遺漏創新板個股
- ⚙️ 新增設定：`FUBON_API_KEY`, `FUBON_USER_ID`, `FUBON_CERT_PATH`, `FUBON_CERT_BASE64`（GCP/CI 用，base64 編碼的 .p12，與 FUBON_CERT_PATH 二擇一）, `FUBON_CERT_PASSWORD`, `FUBON_RATE_LIMIT_PER_MINUTE`（預設 30）, `DOWNLOAD_FUBON_MAX_WORKERS`（預設 200）
- ✅ 新增 `tests/test_fubon_download_client.py` 共 29 個單元測試

### v3.9.0 - 2026-04-23
- 🔕 **新增 `SIGNALS_SHOW_SELL` 開關**：可在 `settings.py` / 環境變數關閉 signals 賣出警示區塊（終端機與 Telegram）
  - 預設值：`False`（關閉）；設定 `SIGNALS_SHOW_SELL=true` 可重新開啟
  - 關閉時說明欄位會提示如何重新開啟

### v3.8.0 - 2026-04-09
- 🔒 **signals 新增成交量過濾（≥1000張）**：排除流動性不足的個股，買入／賣出／觀察三個清單均套用此門檻
- ✅ 新增 5 個 TestVolumeFilter 單元測試

### v3.7.0 - 2026-04-09
- 🆕 **新增 `python main.py signals` 指令**：今日 P1 完整策略買賣訊號，直接給出「建議買入」與「賣出警示」
- 📊 **建議買入**：通過 MA60 上方、均線排列(MA5>MA10>MA20)、RSI≥50、動能前30、成交量≥1000張 五道過濾的股票（可執行訊號）
- 📉 **賣出警示**：今日觸發 MACD Death Cross / Death Cross / RSI Momentum Loss 的股票，每股僅保留最嚴重訊號，預設顯示前30支
- 🔍 **與 `scan` 的差異**：`scan` = 寬鬆條件觀察清單，`signals` = P1 策略可執行進出場建議
- ✅ 新增 14 個單元測試覆蓋代號格式轉換、名稱查詢、訊號過濾

### v3.6.0 - 2026-04-09
- 🔬 **新增 P1 交易歸因分析** (`scripts/analyze_scan_attribution.py`)：對 P1 實際交易按進場日的掃描類型分類，量化各類型的勝率與每筆平均報酬
- 📊 **歸因回測結論**（1645 筆交易）：
  - **動能股**（70% 交易）：勝率 54.1%，平均每筆 **+1.22%**，累計貢獻 +1408%
  - **超賣股**（0% 交易）：P1 的 `rsi_min_entry=50` 完全過濾掉 RSI < 30 的超賣股
  - **突破股**（80% 交易）：勝率 52.0%，平均每筆 **+0.95%**，累計貢獻 +1249%
  - **無分類**（14% 交易）：勝率 54.8%，平均每筆 **+1.95%**（最高，Donchian/MACD 貢獻大）
  - 注意：動能股 + 突破股大量重疊（一筆可同時屬於多類型）
- ✅ 新增 11 個單元測試覆蓋歸因分類與統計計算邏輯

### v3.5.0 - 2026-04-09
- 🔬 **新增掃描類型回測比較工具** (`scripts/backtest_scan_types.py`)：量化比較動能股、超賣股、突破股三種掃描類型，使用 P1 生產策略作為白名單過濾器
- 📊 **回測結論**（585 天 2024-09-01～2026-04-09）：
  - Baseline (P1 動能 top30)：+51.73%，勝率 52.5%，Sharpe 1.68
  - 動能股掃描白名單：**-9.53%**（勝率 45.6%，最大回撤 32.75%）— 每日平均 84 支，比 top30 寬鬆品質較差
  - 突破股掃描白名單：**-33.18%**（勝率 41.9%，最大回撤 38.47%）— 每日平均 287 支，條件過寬
  - 超賣股掃描白名單：幾乎無交易（RSI < 30 被 P1 rsi_min_entry=50 過濾），掃描類型與趨勢跟蹤策略根本不相容
- ✅ **結論**：P1 動能 top30 精選是三者中績效最佳的篩選機制；掃描類型可作為參考但不適合直接接入 P1 策略
- ✅ 新增 17 個單元測試覆蓋 RSI 計算、MA 計算與白名單建立邏輯

### v3.5.0 - 2026-04-22
- 🚫 **處置股/注意股過濾**：新增 `DisposalStockFilter`，優先使用富邦 SDK `intraday.tickers(isDisposition=True)`，fallback 至 TWSE 公告 API；處置股被硬排除，不進任何清單
- 📊 **三大法人籌碼過濾**：新增 `InstitutionalFlowLoader`，從 TWSE T86 API 取得每日外資、投信、自營商買賣超；法人買超比散戶早 3-10 天，預設 `enable_institutional_filter=False` 觀察模式（啟用後降級至 watch）
- 📈 **月營收年增率**：`revenue_filter.py` 新增 `yoy_pct`（年增率）、`mom_pct`（月增率）欄位，buy 清單顯示 YoY；新設定 `min_revenue_yoy_pct`（預設 0 = 停用）
- ⚙️ **新增 6 個 settings.py 可調參數**：`enable_disposal_filter`、`filter_attention_stocks`、`enable_institutional_filter`、`institutional_min_foreign_net_shares`、`institutional_min_trust_net_shares`、`institutional_require_any`、`min_revenue_yoy_pct`
- ✅ 新增 65 個單元測試覆蓋三個新模組

**使用方式**：
```bash
# 處置股過濾預設啟用，無需額外設定
python main.py signals

# 啟用三大法人過濾（先觀察數週，設門檻前保持 False）
BACKTEST_ENABLE_INSTITUTIONAL_FILTER=true python main.py signals

# 加入月營收年增率門檻（需年增率 >= 20%）
BACKTEST_MIN_REVENUE_YOY_PCT=20 python main.py signals
```

### v3.4.0 - 2026-04-09
- 🎯 **Donchian 週期從 20 天調整至 50 天**：更長週期過濾假突破，勝率維持 53%，夏普顯著提升
- 📊 **動能排名 top_n 從 50 縮至 30**：更精選動能最強的 30 支，報酬 +7%、回撤大幅下降
- 🔧 **大盤 RSI 門檻從 45 放寬至 40**：容許更多交易日進場，微幅改善報酬
- 📈 **回測結果**（585 天）：總報酬 **51.73%**（超越 TAIEX 49.45%）、年化 28%+、夏普 **1.68**、最大回撤 **7.73%**
- 🔬 以下方向實測無效（恢復原設定）：停用 Golden Cross、NEUTRAL 開放 Donchian、縮 BB 倉位增趨勢倍率、移除停利限制
- ✅ 更新單元測試與 diagnose_filters.py 的生產配置（87 tests pass）

### v3.5.0 - 2026-04-22
- 🚫 **新增處置股/注意股過濾器**（`src/scanner/disposal_filter.py`）：硬過濾，處置/注意股不進 buy/watch 清單
  - 主要來源：富邦 SDK `intraday.tickers(isDisposition=True / isAttention=True)`
  - 備用來源：TWSE OpenAPI `/announcement/punish` + `/announcement/notetrans`（免登入，自動 fallback）
  - 每日磁碟快取 `data/cache/disposal_cache.json`；失敗時 fail-open 不阻斷掃描
- 📊 **新增三大法人籌碼過濾器**（`src/scanner/institutional_filter.py`）：外資/投信法人買超是領先 3-10 天的早期信號
  - 資料來源：TWSE T86 API（`/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALLBUT0999`）
  - `InstitutionalFlow` dataclass：外資/投信/自營商/合計買賣超（張數）
  - 支援 OR/AND 邏輯過濾；法人不足時降級至 WATCH（非硬過濾）
  - 每日磁碟快取；非交易日 fail-open
- 📈 **月營收升級**（`src/scanner/revenue_filter.py`）：新增 YoY 年增率、MoM 月增率
  - `get_revenue_yoy()` / `get_revenue_mom()` helper functions
  - 快取 schema_version=2；舊版 float 格式自動視為過期重抓
  - 新設定 `BACKTEST_MIN_REVENUE_YOY_PCT`（預設 0=停用）
- ⚙️ **新增 settings.py 參數**（共 7 個）：`enable_disposal_filter`、`filter_attention_stocks`、`enable_institutional_filter`、`institutional_min_foreign_net_shares`、`institutional_min_trust_net_shares`、`institutional_require_any`、`min_revenue_yoy_pct`
- ✅ **新增 65 個單元測試**：`test_disposal_filter.py`（18）、`test_institutional_filter.py`（18）、`test_revenue_filter.py` 擴增（29 → 29）

### v3.4.1 - 2026-05-04
- 📋 **Google Sheets 交易記錄新增「股票名稱」欄位**：`stock_code` 欄位後新增 `stock_name`，自動從 TWSE/TPEX API 查詢中文名稱（如「台積電」），查無時留空
- ✅ 更新 `test_google_sheets_recorder.py` 以反映新欄位順序，修正測試正確使用 mock 隔離環境設定

### v3.4.0 - 2026-04-10
- 📁 **signals 歷史記錄自動儲存**：每次執行 `python main.py signals` 自動將結果（買入、賣出、族群摘要）存為 `data/signals_log/signals_YYYYMMDD_HHMMSS.json`，可供後續查閱與比對
- 🐛 **修正 TEST_TW.csv 汙染 latest date 偵測的 bug**：測試遺留的 `data/stocks/TEST_TW.csv` 含有未來日期 timestamp，導致 scanner 誤判最新交易日，造成無訊號輸出；已刪除該檔案
- ✅ 新增 `TestSaveSignalsHistory` 單元測試（25 tests pass）

### v3.3.0 - 2026-04-09
- 🎯 **趨勢部位停損從 10% 擴至 15%**：給 Donchian Breakout / MACD Golden Cross 更大的空間讓 8% trailing stop 發揮，避免過早被打出
- 🔄 **P3-B 從信號式出場恢復為 trailing stop**：信號式出場（RSI Momentum Loss / MACD Death Cross）在現有配置下觸發 0 次（部位被停損/profit-protection 先退出），改回 trailing stop 效果更好
- 📈 **回測結果**（584 天）：總報酬 **42.26%**、年化 24.60%、夏普比率 **1.13**、勝率 **51.58%**、Donchian Breakout 勝率 **53.8%**
- ✅ 更新單元測試預設值以反映最新設定（87 tests pass）

### v3.2.0 - 2026-04-08
- 🎯 **P3-C：市場環境分層訊號路由**：依 TAIEX RSI(14) 將市場分三區，各區允許不同訊號
  - **STRONG**（RSI >= 60）：全部訊號允許（趨勢 + 均值回歸）
  - **NEUTRAL**（RSI 45-60）：僅 BB Squeeze Break + RSI Oversold
  - **WEAK**（市場環境過濾觸發）：暫停所有買進
- 📊 `BacktestEngine` 新增 `get_market_regime()`、`benchmark_rsi` 儲存、`strong/neutral_regime_signals` 路由設定
- ✅ **新增 `TestMarketRegime` 單元測試**（5 tests）：覆蓋 WEAK/STRONG/NEUTRAL 判斷與訊號封鎖邏輯

### v3.2.0 - 2026-04-25
- 📝 **新增 Telegram 交易記錄 Bot**：使用者輸入「買入/賣出 股票代號 價格 股數」，自動記錄至 CSV 及 Google Sheets
- 🗂️ **新增 `GoogleSheetsRecorder`**（`src/infrastructure/persistence/google_sheets_recorder.py`）：透過 Service Account 將交易記錄同步寫入 Google Sheets，支援 JSON 字串或金鑰檔案兩種憑證方式
- 🤖 **新增 `trade_bot_main.py`**（`src/interfaces/trade_bot_main.py`）：獨立 Bot 執行入口，polling 模式，支援 /stats、/trades、/help 指令
- ⚙️ **新增 `GoogleSheetsSettings`**：新增 `GOOGLE_SHEETS_ENABLED`、`GOOGLE_SHEETS_SPREADSHEET_ID`、`GOOGLE_SHEETS_WORKSHEET_NAME`、`GOOGLE_CREDENTIALS_JSON`、`GOOGLE_CREDENTIALS_FILE` 參數
- 🐳 **新增 `trade-recorder` Docker 服務**：docker-compose.yml 增加獨立 trade-recorder container
- ✅ **新增 26 個單元測試**：覆蓋 Google Sheets 可用性判斷、寫入成功/失敗、交易指令解析（中英文/買賣/舊格式）、Google Sheets 同步狀態回報

### v3.1.0 - 2026-04-10
- 🆕 **新增買入冷卻期（Signal Cooldown）**：同一支股票在 `BACKTEST_SIGNAL_COOLDOWN_DAYS` 個交易日內重複出現買入訊號時，自動降級為 WATCH，避免同一波上漲中反覆進場（預設 10 日）
- 📋 **新增 `docs/reduce_trade_frequency.md`**：記錄 10 種降低交易頻率的方法及建議回測驗證順序
- ✅ **新增 5 個單元測試**：覆蓋冷卻期啟用/停用、窗口內/外訊號、跨 start_date 歷史追蹤

### v3.0.0 - 2026-04-08
- 🔄 **P1：恢復 Golden Cross + MACD Golden Cross**：過濾器診斷顯示停用這兩個訊號讓報酬率 -5.90%，儘管勝率低（22-32%），其進場時機對組合有正向錨定效果
- 🗑️ **P1：移除 Volume Confirmation（F3）**：診斷顯示此 filter 讓報酬率 -4.55%，在趨勢市中篩出的高成交量突破反而容易追高後被追蹤停損打出
- ✅ **更新單元測試**：修正因 P1 設定改變而失效的測試（3 個），新增 `test_macd_golden_cross_not_disabled_by_default`、`test_golden_cross_not_disabled_by_default`

### v2.13.0 - 2026-05-29
- 📈 **RSI 進場門檻從 50 提升至 76**：全期回測（2024-09 ~ 2026-05）顯示 RSI≥76 在各項指標均優於 RSI≥50
  | 指標 | RSI≥50（舊） | RSI≥76（新） |
  |------|------------|------------|
  | 勝率 | 51.89% | **52.10% ↑** |
  | 總報酬 | 45.24% | **49.14% ↑** |
  | 最大回撤 | 8.17% | **4.87% ↓** |
  | Sharpe | 1.53 | **1.98 ↑** |
  | 交易筆數 | 1297 | 1094 |
- 🐛 **修正 backtest_main.py 資料路徑 bug**：`../../data/stocks` → `../../../data/stocks`，修正本機執行 `--skip-download` 時找不到資料的問題

### v2.12.1 - 2026-05-11
- 🛡️ **Fubon 資料源週末防護**：`download_snapshot()` 在週末（Saturday/Sunday）直接跳過，不呼叫 API，避免 Fubon 回傳非交易日前填資料
- 🛡️ **Fubon `download_all_stocks()` / `download_recent_data()`**：週末時 `end_date` 自動對齊最後交易日，不傳入週末日期給 API
- ✅ **新增單元測試** `test_snapshot_skipped_on_weekend`：驗證週末 snapshot 回傳 0 且不呼叫 save/API

### v2.12.0 - 2026-05-11
- 🐛 **修正 signals 盤前/週末資料污染導致 0 訊號問題**：yfinance 在盤前或週末下載時，會回傳當日/週末的前填假資料，造成 `latest` 交易日被拉到非真實交易日，訊號全數被過濾為 0
- 🛡️ **`signals_scanner.py`**：計算 `latest` 交易日時，自動跳過週六/週日（`weekday >= 5`），以及盤前（14:00 台灣時間前）的今日資料
- 🛡️ **`yfinance_client.py` `save_stock_data`**：儲存前過濾週末日期；盤前執行時不寫入今日前填資料
- 🧹 **一次性清理現有 CSV**：移除 `data/stocks/` 下 1970 支股票的週六/週日及盤前今日假資料列
- ✅ **更新單元測試**：修正 `test_data_downloader.py` 中使用週六日期（2026-03-28）的測試資料，改為平日（2026-03-27）

### v2.11.0 - 2026-04-14
- 💰 **新增月營收過濾（第 7 道進場過濾）**：`signals` 指令自動排除每月營收低於門檻的股票，預設 1 億元（`BACKTEST_MIN_MONTHLY_REVENUE_MILLION=100`）
- 🌐 **新增 `src/scanner/revenue_filter.py`**：從 TWSE / TPEX OpenAPI 取得最新月營收，帶當日磁碟快取（`data/revenue_cache.json`），API 失敗時自動降級略過
- ⚙️ **新增 config 參數 `min_monthly_revenue_million`**：單位百萬元，0 = 停用；透過 env `BACKTEST_MIN_MONTHLY_REVENUE_MILLION` 覆蓋
- ✅ **新增 `tests/test_revenue_filter.py`**（8 tests）：覆蓋 TSE/OTC 解析、HTML 降級、快取讀寫、過期快取更新、API 失敗容錯

### v2.10.0 - 2026-04-09
- 🏷️ **`python main.py scan` 顯示股票名稱**：選股結果除股票代號外，同時顯示中文公司名稱（如「2330.TW 台積電」）
- 🆕 **新增 `src/utils/stock_name_mapper.py`**：從 TWSE / TPEX OpenAPI 取得股票名稱並快取至 `data/stock_names.json`（24 小時 TTL），支援 `lookup_name(symbol_stem)` 查詢
- ✅ **新增 `tests/test_stock_name_mapper.py`**（7 tests）：覆蓋 TSE/OTC 名稱抓取、underscore/dot 格式查詢、快取讀取與過期更新

### v2.9.0 - 2026-04-08
- 🔍 **新增過濾器診斷腳本 `scripts/diagnose_filters.py`**：逐步累加 9 個場景（baseline → +disabled_signals → +market_regime → ... → full），對每個場景輸出整體績效比較表、各 filter 對交易次數的削減量、以及各訊號勝率明細。協助定位哪個 filter 是績效劣於大盤的主因
- ✅ **新增 `TestDiagnoseFilters` 單元測試**（6 tests）：驗證場景定義的累加邏輯、最終場景與生產設定一致性、訊號勝率統計正確性、報告輸出不崩潰

### v2.8.0 - 2026-04-08
- ⚙️ **所有 BacktestSettings 參數補齊至 `.env` / `.env.example`**：新增 `BACKTEST_*` 完整區塊，包含時間範圍、停損停利、進場過濾、大盤環境、動能排名、產業排除共 15 個參數
- 🔗 **strategy.py 與 BacktestSettings 完全一致**：`BacktestRunner` 現在把 `disabled_signals`、`require_ma60_uptrend`、`require_volume_confirmation`、`volume_confirmation_multiplier`、`rsi_overbought_threshold` 全部從 config 讀取並傳入 `TechnicalStrategy`，消除寫死預設值的不一致風險

### v2.7.0 - 2026-04-08
- 🌐 **強化大盤市場環境過濾器（Direction 1）**：原本只檢查 TAIEX 收盤 >= MA20，新增三層篩選：
  - TAIEX close >= MA20（原有）
  - TAIEX MA5 >= MA20（短期趨勢對齊，新增）
  - TAIEX RSI(14) >= 45（大盤動能確認，新增）
  - 任一條件不通過即暫停當日新進場，直接應對 Q4 2025 虧損 -15% 的根本問題
- 📊 **動能排名過濾器（Direction 4）**：每個交易日計算所有股票近 20 日動能，只允許排名前 50 的股票發出 BUY 訊號，避免進場動能不足的股票
- ⚙️ **新增 4 個設定參數**：`BACKTEST_MARKET_REGIME_RSI_THRESHOLD`（預設 45）、`BACKTEST_MARKET_REGIME_CHECK_MA5`（預設 True）、`BACKTEST_MOMENTUM_TOP_N`（預設 50）、`BACKTEST_MOMENTUM_LOOKBACK_DAYS`（預設 20）
- 🧪 新增 10 個單元測試覆蓋新功能，全部 55 個測試通過

### v2.4.0 - 2026-04-07
- 🎯 **策略勝率突破 50%**：自動回測優化，勝率從 45.68% 提升至 **53.36%**
- 📊 **新增 MA 均線對齊過濾**：進場時需 MA5 > MA10 > MA20，確保短中期趨勢一致，避免買在動量消退的假突破
- 💡 **優化分析**：識別出 BB Squeeze Break 為主力訊號（佔 83%），MA 對齊過濾有效篩選優質進場點
- 📈 **回測結果改善**：總回報 0.61% → 11.15%，最大回撤 7.73% → 6.12%，夏普比率 0.23 → 2.42
- 🧪 新增 2 個單元測試：MA 對齊失敗攔截、MA 對齊通過允許進場

### v2.6.0 - 2026-04-08
- 🚫 **停用 Golden Cross 訊號**：兩期回測勝率均 < 50%（Q4 2025: 0%、Q1 2026: 45.5%），加入 DEFAULT_DISABLED_SIGNALS
- 🔍 **新增 Filter 5 — RSI 動能確認**：進場需 RSI ≥ 50（可透過 `BACKTEST_RSI_MIN_ENTRY` 調整）。BB Squeeze Break 在 Q4 2025 勝率僅 44.8%，RSI 過濾排除低動能假突破
- 🎯 **停利從 20% 降至 10%**：Q4 2025 最高獲利僅 9.96%，20% 目標從未觸發；調整後更符合實際（`BACKTEST_TAKE_PROFIT_PCT`）
- 🔒 **追蹤停損從 5% 縮至 3%**：更早鎖住已實現利潤（`BACKTEST_TRAILING_STOP_PCT`）
- ⏱️ **最長持倉從 30 天縮至 15 天**：減少持有不動死掌（`BACKTEST_MAX_HOLDING_DAYS`）
- 📊 **優化前後對比**：

  | 指標 | Q4 2025 優化前 | Q4 2025 優化後 | Q1 2026 優化前 | Q1 2026 優化後 |
  |------|--------------|--------------|--------------|--------------|
  | 勝率 | 42.93% | **45.19% ↑** | 53.36% | 52.36% |
  | 總報酬 | -15.05% | **-9.69% ↑** | 11.15% | 9.99% |
  | 夏普比率 | -3.61 | **-1.65 ↑** | 2.42 | 1.76 |
  | 超額報酬 vs TAIEX | -26.40% | **-21.07% ↑** | +2.13% | +3.12% |

- 🧪 新增 5 個單元測試：Golden Cross 停用、RSI < 50 攔截、RSI = 50 通過、RSI = None 不攔截、有效進場含 RSI

### v2.5.0 - 2026-04-08
- 🚫 **生技醫療業排除過濾**：以 TWSE 官方產業類別代碼 31（生技醫療業）作為過濾條件，預設排除 57 支生技醫療股
- 🗂️ 新增 `config/industry_codes.json`：TWSE 產業代碼對應表，可依官方公告更新，目前涵蓋 4102-4207 及 6541-6550 等主要生技類股
- ⚙️ 新增 `BacktestSettings`（`config/settings.py`）：`exclude_industry_codes`（預設 `[31]`）與 `industry_code_map_path` 可透過環境變數 `BACKTEST_EXCLUDE_INDUSTRY_CODES` 調整
- 🔄 回測期間更新為 **2025-10-01 ~ 2026-01-01**（季度回測）
- 📊 **回測結果**（排除生技股，Q4 2025）：勝率 42.93%，總報酬 -15.05%，大盤同期 +11.47%（市場弱勢期間策略承壓）
- 🧪 新增 7 個單元測試：產業過濾器 JSON 載入、多產業代碼、缺檔保護、空清單、Comment 鍵忽略、預設代碼驗證、過濾邏輯整合

### v2.3.0 - 2026-04-07
- 🚫 停用 **MACD Golden Cross** 買進訊號（兩次回測勝率 13-17%，改降為 WATCH 保留報告可視性）
- 📈 新增股票 **MA60 趨勢過濾**：股價在 60 日均線以下不做多，避免逆勢進場
- 📊 新增**成交量確認過濾**：進場當天量需 > 20 日均量 × 1.5 倍，過濾低量假突破
- 🔧 三項過濾可透過 `TechnicalStrategy` 建構參數調整（`disabled_signals`、`require_ma60_uptrend`、`require_volume_confirmation`）
- ✅ 新增 4 個單元測試覆蓋各過濾條件

### v2.2.1 - 2026-04-12
- 🐛 修正 `load_from_stocks_dir` 讀取 `TEST*.csv` 髒資料，導致 `signals` 最新交易日被拉到非交易日（如周六），產生 0 個買入訊號的問題
- 🛡️ `_analyze_futures_signals` 修正 `high_price`/`low_price` 為 `None` 時的 `TypeError`
- 🧪 修正 `test_futures.py` 中對不存在的 `FuturesSignalType` 及已改名欄位的引用

### v2.2.0 - 2026-04-02
- 🐛 修正年化報酬率公式運算子優先順序錯誤（`- 1 * 100` → `(- 1) * 100`）
- 🐛 修正訊號成功率從硬寫 50% 改為依實際交易結果計算，報告中顯示每種訊號的真實勝率與觸發交易次數
- ⚖️ 倉位計算改用初始資金固定金額（`initial_capital × position_sizing`），高價股不再強制分配最少 1 張造成倉位失衡
- 🛡️ 停損從 10% 縮至 5%，新增追蹤停損機制：股價創高後停損點隨之上移，保留上漲獲利
- 📊 新增大盤 MA20 過濾器：TAIEX 收盤在 20 日均線以下時自動暫停做多，避免弱勢市場持續開倉
- 🧪 新增 4 個測試：追蹤停損、大盤過濾、訊號記錄、倉位計算邏輯

### v2.1.2 - 2026-04-02
- ⚡ `download_all_stocks` 改用批次模式（`batch_size=100`），透過 `yf.download()` 一次抓 100 支，速度大幅提升
- 🆕 新增 `_download_batch()` 方法，處理 yfinance MultiIndex 回傳格式

### v2.1.1 - 2026-04-01
- 🐛 修正 `load_from_stocks_dir` 空值欄位造成整檔載入失敗的問題（改為逐行跳過）
- 🤖 `BacktestRunner` 新增資料覆蓋率檢查：當本地 CSV 只有少數幾天時，自動觸發歷史資料下載
- 🗑️ 清除測試遺留的 `data/stocks/TEST_TW.csv`

### v2.1.0 - 2026-04-01
- 🔧 回測系統優先載入 `data/stocks/` 本地 CSV，不再重複從 yfinance 抓取
- 🆕 `YFinanceDataSource.load_from_stocks_dir()` — 批次讀取每檔獨立 CSV
- 🐛 修正 `calculate_position_size` 最小張數判斷未含手續費的問題
- ✅ 新增 `load_from_stocks_dir` 相關單元測試（3 個測試案例）

### v3.0.3 - 2026-04-28
- 💰 **Artifact Registry cleanup policy**：自動保留最新 5 個 image，舊版自動刪除（原本 43 個 image 累積 14 GB → 降至 5 個）

### v3.0.4 - 2026-04-30
- 🤖 **AI 分析 Telegram 訊息包含模型名稱**：Telegram 推送的 AI 二次過濾分析標題現在會顯示所使用的 AI 模型（例如 `🤖 AI 二次過濾分析 (claude-sonnet-4-6) 2026-04-30`）
- 🚨 **Telegram 發送失敗時 Cloud Run Job 標示為失敗**：`--send-telegram` 模式下，若 Telegram 推送失敗，程式以 `exit(1)` 退出，讓 GCP Cloud Run Job 正確標記為失敗並觸發警報

### v3.0.3 - 2026-04-30
- 🐛 修正 Cloud Run signals job AI 分析 Telegram 發送失敗的問題
  - AI 產生的 `reason` 文字含 `_`、`[`、`*` 等字元時，Telegram 以 Markdown 解析會回傳 400 錯誤
  - `TelegramNotifier.send_message`：`parse_mode=None` 時不傳 `parse_mode` 欄位給 API
  - `run_ai_analysis`：AI 格式化輸出改用 `parse_mode=None`（純文字，無需 Markdown 解析）

### v3.15.1 - 2026-05-30
- 🐛 **修正週線收盤進場（`BACKTEST_WEEKLY_CLOSE_ONLY`）產生 0 筆交易的 Bug**：
  - 根本原因：BUY 訊號在週五（週最後交易日）發出後，回測引擎將其排入「次日開盤執行」佇列；但次日（週六）無市場資料，舊邏輯直接丟棄訊號，導致所有交易均被捨棄
  - 修復方式：`execute_pending_signals` 改為「攜帶前進」（carry-forward）—— 若當日無開盤價，訊號繼續保留至下一個交易日；超過 5 個日曆天（`MAX_CARRY_DAYS`）後才丟棄，避免過時訊號偏差
  - 新增單元測試：`TestPendingSignalCarryForward`（2 個測試），驗證週末攜帶及過期丟棄行為

### v3.15.0 - 2026-05-30
- 📅 **方向2：週線收盤進場（`BACKTEST_WEEKLY_CLOSE_ONLY`）**：只在每週最後交易日產生進場訊號，過濾日線雜訊，配合寬停損（15%）+ 長持倉（45天）讓趨勢有發展空間
  - 範例：`BACKTEST_WEEKLY_CLOSE_ONLY=true BACKTEST_STOP_LOSS_PCT=0.15 BACKTEST_MAX_HOLDING_DAYS=45`
- 📊 **方向3：Minervini Stage 2 過濾（`BACKTEST_REQUIRE_MINERVINI_TREND`）**：要求 price > MA60 > MA120，確保股票處於長期上升趨勢（Stage 2），參考 Mark Minervini SEPA 方法
  - 範例：`BACKTEST_REQUIRE_MINERVINI_TREND=true`
- 🔢 **新增 MA120**：TechnicalIndicators 加入 120日均線，`ma_periods` 預設改為 `[5, 10, 20, 60, 120]`

### v3.14.0 - 2026-05-30
- 📈 **週線 RSI 過濾（Filter 10）**：新增 `BACKTEST_REQUIRE_WEEKLY_RSI` / `BACKTEST_WEEKLY_RSI_MIN` 參數，要求週 RSI(14) ≥ 門檻（預設 50）才允許進場，使用 Wilder's smoothing 算法與 talib 一致
  - 範例：`BACKTEST_REQUIRE_WEEKLY_RSI=true BACKTEST_WEEKLY_RSI_MIN=50`
- 💰 **月營收 YoY 過濾（Filter 11）**：新增 `BACKTEST_REQUIRE_REVENUE_GROWTH` / `BACKTEST_REVENUE_YOY_MIN_PCT` 參數，進場前確認最近月營收年增率 ≥ 門檻
  - 資料來源：FinMind TaiwanStockMonthRevenue（需 `FINMIND_API_TOKEN`，免費帳號每小時 600 次）
  - 範例：`BACKTEST_REQUIRE_REVENUE_GROWTH=true BACKTEST_REVENUE_YOY_MIN_PCT=0` （正成長即可）
  - 範例：`BACKTEST_REQUIRE_REVENUE_GROWTH=true BACKTEST_REVENUE_YOY_MIN_PCT=10` （年增率 ≥ 10%）

### v3.13.0 - 2026-05-13
- 🔒 **VPC + 固定 IP (Static NAT)**：所有 Cloud Run Jobs/Service 改走 Direct VPC Egress，透過 Cloud NAT 以固定靜態 IP 對外連線，可設定為 Fubon API Key 的 IP 白名單，防止 API Key 外流被濫用下單
  - 新增 `google_compute_address.nat_ip`（靜態外部 IP）、VPC Network/Subnetwork、Cloud Router、Cloud NAT
  - `terraform apply` 後由 `outputs.nat_ip` 取得固定 IP，填入 Fubon API Key 白名單

### v3.12.3 - 2026-05-09
- 🐛 **修正 Fubon SDK SIGSEGV on exit**：`download_main.py` 完成下載後改用 `os._exit(0)` 退出，繞過 Python 正常清理流程（GC/執行緒清理會觸發 fubon_neo native code 崩潰）
- 🔧 **download_snapshot 後呼叫 logout()**：確保 Fubon SDK 背景連線在 exit 前被正確關閉

### v3.12.2 - 2026-05-09
- 🐛 **修正 Workflow YAML KeyError**：`wait_for_execution` 中 `determine_result` 改用 `"succeededCount" in status` 防護，避免 job 失敗時 Cloud Run 不回傳 succeededCount 而拋出 KeyError
- 🔑 **APP_SECRETS 補充 Fubon 憑證**：新增 `FUBON_USER_ID`、`FUBON_API_KEY`、`FUBON_CERT_PASSWORD`、`FUBON_IS_SIMULATION`

### v3.12.1 - 2026-05-09
- 🐛 **修正 Cloud Run 缺少 fubon_neo Linux SDK**：`Dockerfile.cloudrun` builder stage 新增從富邦官方伺服器下載並安裝 Linux x86_64 版 `fubon_neo-2.2.8` whl，修復 GCP Workflow 因 `ImportError` 導致 download job 失敗的問題
- 📝 **更新 requirements.txt 說明**：補充各平台 fubon_neo 下載連結

### v3.12.0 - 2026-05-09
- 🔄 **Download 改用 Fubon 資料來源**：Cloud Run 下載任務改為預設使用 Fubon API（`DOWNLOAD_DATA_SOURCE=fubon`），透過 Terraform env_vars 設定，無需修改程式碼
- ⏰ **排程頻率提升**：原本 10:00 單次執行改為 9:30～12:30 每 30 分鐘執行一次（共 7 次：9:30、10:00、10:30、11:00、11:30、12:00、12:30）
  - 新增 `bag-holder-run-jobs-mid-hour-trigger`（整點：10:00 / 11:00 / 12:00）
  - 新增 `bag-holder-run-jobs-half-hour-trigger`（半點：9:30 / 10:30 / 11:30 / 12:30）
  - 原 `bag-holder-run-jobs-10-trigger` 由上述兩個排程取代

### v3.11.0 - 2026-05-09
- 🆕 **買入訊號進場價格區間**：訊號掃描後自動計算建議進場區間與停損位
  - 依訊號類型（Golden Cross / MACD Golden Cross / RSI Oversold / BB Squeeze Break / Donchian Breakout）搭配技術指標（MA20、布林通道）推算
  - 終端輸出新增「進場區間」與「停損」欄位
  - Telegram 訊號每支股票加一行 `📌 進場 X–Y  🛑 停損 Z`
  - AI 二次過濾後的 strong_buy / buy 同樣顯示進場區間與停損
  - AI 分析時將進場區間作為附加背景資訊（`entry_range`、`stop_loss`）
  - 多訊號合併時取最寬進場範圍、最保守（較高）停損
  - 新增 `tests/test_price_range.py` 15 個單元測試

### v3.1.0 - 2026-05-04
- 🆕 **10:00 Signals 排程**：新增台北時間 10:00 (M-F) 的第二次 signals 掃描（download → signals → Telegram + AI 過濾）
- 🆕 **持倉賣出檢查（`python main.py check-holdings`）**：
  - 讀取 Google Sheets 交易記錄，自動判斷未平倉持倉（最後 action = 買入）
  - 比對當日 P1 賣出訊號（RSI Momentum Loss / MACD Death Cross / Death Cross）
  - Enrich 每筆警示：現金損益%、持有天數、族群強弱、月營收年增率
  - AI（Claude/OpenAI/Gemini）三分類判斷：確認賣出 / 設停損觀察 / 繼續持有
  - 結果推送 Telegram
  - 已有「賣出」記錄的股票自動略過
- 🆕 **新增 Cloud Run Job `bag-holder-check-holdings`**
- 🆕 **新增 GCP Workflow `bag-holder-run-jobs-10`**（10:00 workflow）
- 🆕 **AI 持倉分析擴充**：`BaseAIAnalyzer` 新增 `analyze_holdings()` / `format_holdings_for_telegram()` 方法

### v3.0.2 - 2026-04-28
- 🐛 修正 Cloud Scheduler cron 時間錯誤：`5 0 * * 1-5` → `5 8 * * 1-5`（台北時間 08:05，原本實際執行於 00:05）
- 🆕 **GCP Monitoring 失敗告警**：新增三條 alert policy，任一步驟失敗即寄 email 通知
  - Cloud Scheduler 觸發失敗
  - GCP Workflow 執行失敗
  - Cloud Run Job（download / signals）task 失敗
  - 新增 Terraform 變數 `notification_email`，由 GitHub Secret `NOTIFICATION_EMAIL` 注入
  - **需手動設定 GitHub Secret**：`NOTIFICATION_EMAIL` = 你的 email 地址

### v3.0.1 - 2026-04-28
- 🐛 修正 `signals_scanner.py` 中股票資料路徑硬編碼錯誤，導致 Cloud Run `bag-holder-signals` 執行失敗（exit code 1）
  - 原路徑 `../../data/stocks`（相對 `__file__`）在容器內解析為 `/app/src/data/stocks`，但實際資料在 `/app/data/stocks`
  - 改用 `settings.data.stocks_path`（`DATA_STOCKS_PATH` 環境變數），與 `yfinance_client.py` / `csv_scanner.py` 一致

### v3.0.0 - 2026-04-25
- 🆕 **DDD / Hexagonal Architecture 全面重構**
  - 新增 `src/domain/` 領域層（models, services, ports）
  - 新增 `src/application/use_cases/` 應用層 Use Cases
  - 新增 `src/infrastructure/` 基礎設施層（persistence, market_data, notification, ai）
  - 新增 `src/interfaces/cli/` 介面層 CLI 入口
- 🔧 `src/database/`, `src/indicators/` 轉為 re-export shim，保持向下相容
- ✅ 所有 411 個單元測試通過

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