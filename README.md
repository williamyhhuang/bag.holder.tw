# 台股分析系統 (Taiwan Stock Analysis System)

全新的台股分析系統，整合資料下載、股票掃描、策略回測與期貨分析功能。採用 CSV 檔案儲存，簡化部署並提供統一 CLI 介面。

🆕 **全面重構**: CLI 統一介面、CSV 資料儲存、完整回測系統、定時任務支援！

## 🎯 專案特色

- **📥 股票資料下載**: YFinance 整合下載台股歷史資料（上市 + 上櫃）
- **🚦 今日買賣訊號**: P1 完整策略過濾，直接輸出「建議買入」與「賣出警示」
- **🔍 股票觀察清單**: 寬鬆條件快速篩選動能、超賣、突破股
- **📈 策略回測系統**: 完整回測引擎 (P1 策略，585天 +51.73%，Sharpe 1.68)
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
使用 YFinance 下載台股歷史資料，支援 TSE 與 OTC 市場。

```bash
# 下載最近的股票資料
python main.py download

# 指定日期區間
python main.py download --start-date 2024-01-01 --end-date 2024-01-31

# 指定市場
python main.py download --markets TSE OTC
```

### 今日買賣訊號 (signals) ⭐
使用 P1 完整策略過濾，直接輸出「今日建議買入」與「賣出警示」，是每日操盤的主要參考指令。

```bash
# 今日買賣訊號（最常用）
python main.py signals

# 同時顯示觀察清單（訊號觸發但未完全達標）
python main.py signals --watch

# 發送到 Telegram
python main.py signals --send-telegram
```

**買入訊號條件（必須同時通過）：**
1. 技術訊號觸發：BB Squeeze Break / Donchian Breakout / Golden Cross / MACD Golden Cross
2. 個股在 MA60 上方（長期上升趨勢）
3. 均線多頭排列：MA5 > MA10 > MA20
4. RSI ≥ 50（具備上漲動能）
5. 近 20 日動能排名前 30（避免動能衰退的假突破）

**賣出警示訊號（持有中請注意）：**
- MACD Death Cross（最嚴重）
- Death Cross（MA5 跌破 MA20）
- RSI Momentum Loss（RSI 跌破 50）

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

> **signals vs scan 的差異**: `signals` 使用 P1 完整策略（含 5 道進場過濾），輸出可直接參考的進出場建議；`scan` 使用簡單閾值，僅作為觀察清單。

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

### v3.4.0 - 2026-04-09
- 🎯 **Donchian 週期從 20 天調整至 50 天**：更長週期過濾假突破，勝率維持 53%，夏普顯著提升
- 📊 **動能排名 top_n 從 50 縮至 30**：更精選動能最強的 30 支，報酬 +7%、回撤大幅下降
- 🔧 **大盤 RSI 門檻從 45 放寬至 40**：容許更多交易日進場，微幅改善報酬
- 📈 **回測結果**（585 天）：總報酬 **51.73%**（超越 TAIEX 49.45%）、年化 28%+、夏普 **1.68**、最大回撤 **7.73%**
- 🔬 以下方向實測無效（恢復原設定）：停用 Golden Cross、NEUTRAL 開放 Donchian、縮 BB 倉位增趨勢倍率、移除停利限制
- ✅ 更新單元測試與 diagnose_filters.py 的生產配置（87 tests pass）

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

### v3.0.0 - 2026-04-08
- 🔄 **P1：恢復 Golden Cross + MACD Golden Cross**：過濾器診斷顯示停用這兩個訊號讓報酬率 -5.90%，儘管勝率低（22-32%），其進場時機對組合有正向錨定效果
- 🗑️ **P1：移除 Volume Confirmation（F3）**：診斷顯示此 filter 讓報酬率 -4.55%，在趨勢市中篩出的高成交量突破反而容易追高後被追蹤停損打出
- ✅ **更新單元測試**：修正因 P1 設定改變而失效的測試（3 個），新增 `test_macd_golden_cross_not_disabled_by_default`、`test_golden_cross_not_disabled_by_default`

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