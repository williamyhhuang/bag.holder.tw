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
Cloud Scheduler (台北時間 08:05 週一至五)
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
| Cloud Run Service | `bag-holder-webhook` | Telegram Webhook Bot |
| GCP Workflows | `bag-holder-run-jobs` | 08:05 依序執行 download → signals |
| GCP Workflows | `bag-holder-run-jobs-10` | 10:00 依序執行 download → signals → check-holdings |
| Cloud Scheduler | `bag-holder-run-jobs-trigger` | UTC 00:05（台北 08:05）觸發 |

#### Terraform 結構

```
terraform/
├── bootstrap/      # 一次性基礎建設（GCS backend、IAM SA）
└── deployable/     # 每次部署更新的資源
    ├── main.tf
    ├── variables.tf
    ├── backend.tf
    ├── run-jobs.workflow.yaml   # GCP Workflows 定義
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

### v5.6.0 - 2026-05-08
- 📊 **Telegram `/pnl` 指令**：在 Telegram 輸入 `/pnl` 即可查看未實現損益與已實現損益摘要，格式針對手機閱讀最佳化
  - 更新 `src/infrastructure/persistence/google_sheets_reader.py`：`get_pnl_summary()` 直接讀取「未實現損益」（Apps Script 即時股價）與「已實現損益」兩個專屬工作表，不再呼叫 yfinance；新增 `unrealized_pnl_worksheet_name`（預設「未實現損益」）與 `realized_pnl_worksheet_name`（預設「已實現損益」）設定
  - 更新 `src/infrastructure/notification/telegram_trade_bot.py`：新增 `handle_pnl_command()`，`process_telegram_command()` 加入 `/pnl` 分派，`/help` 加入 `/pnl` 說明
  - 更新 `src/interfaces/api/webhook_app.py`：`/pnl` 以 background task 執行（同 `/scan`）；新增 `_send_sync()` 使用 sync httpx，並在 Telegram Markdown 解析失敗（400）時自動 fallback 純文字重試，避免訊息靜默消失
  - 新增 `tests/test_google_sheets_reader_pnl.py`：14 個 P&L 計算單元測試
  - 更新 `tests/test_trade_bot_commands.py`：新增 11 個 `/pnl` 指令測試
  - 更新 `tests/test_webhook_handler.py`：新增 `/pnl` background task 與 `_send_sync` fallback 測試

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