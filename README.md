# 台股監控機器人 (Taiwan Stock Monitoring Robot)

基於富邦證券官方 SDK 的台股監控機器人，能夠全市場掃描 1,800+ 檔股票，進行即時技術指標分析，並支援台指期貨監控，透過 Telegram 發送買賣信號通知。

🆕 **新增回測系統**: 完整的策略回測功能，使用 YFinance 資料源驗證交易策略績效！

## 🎯 專案特色

- **全市場掃描**: 監控 TSE/OTC 市場 1,800+ 檔股票
- **期貨監控**: 專注台指期貨三大合約 (TXF大台/MXF小台/MTX微台)
- **即時技術分析**: 支援多種技術指標 (MA, RSI, MACD, 布林通道)
- **智能通知系統**: Telegram Bot 推送買賣信號
- **投資組合追蹤**: 個人投資組合管理與績效追蹤
- **🆕 策略回測**: 完整的回測系統，驗證策略勝率與績效
- **容器化部署**: Docker + Docker Compose 一鍵部署
- **跨平台支援**: macOS、Windows 11、Linux 全平台最佳化
- **官方 SDK 整合**: 使用富邦證券 fubon_neo 官方 SDK

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────────┐
│                   Taiwan Stock Monitor                         │
├─────────────────────────────────────────────────────────────────┤
│  📱 Telegram Bot  │  🔍 Scanner  │  🎯 Futures  │  📊 API Server │
├─────────────────────────────────────────────────────────────────┤
│                        🧠 Core Services                        │
│  • Rate Limiter   • Logger      • Error Handler              │
│  • Config Mgr     • DB Models   • Tech Indicators            │
├─────────────────────────────────────────────────────────────────┤
│  💾 PostgreSQL  │  🚀 Redis Cache  │  📊 Fubon Neo SDK        │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 快速開始

### 支援平台

- 🍎 **macOS** (Mac Mini 2015+)
- 🪟 **Windows 11** (筆電/桌機)
- 🐧 **Linux** (Ubuntu 20.04+)

### 1. 環境需求

#### macOS / Linux
- Docker & Docker Compose
- Python 3.11+ (開發用)
- PostgreSQL 15+ (可用 Docker)
- Redis 7+ (可用 Docker)

#### Windows 11
- Docker Desktop for Windows
- Python 3.11+
- Windows Terminal (建議)
- WSL 2 (建議)

### 2. 設定配置

```bash
# 複製配置檔案
cp .env.example .env

# 編輯配置檔案，填入真實的 API 金鑰
nano .env
```

必要配置項目：
```env
# 富邦證券 API 認證 (二選一)
# 方式 1: API Key (推薦)
FUBON_API_KEY=your_fubon_api_key_here
FUBON_API_SECRET=your_fubon_api_secret_here

# 方式 2: 憑證檔案
FUBON_USER_ID=your_fubon_user_id_here
FUBON_PASSWORD=your_fubon_password_here
FUBON_CERT_PATH=/path/to/your/certificate.pfx
FUBON_CERT_PASSWORD=your_certificate_password_here

# 環境設定
FUBON_IS_SIMULATION=true

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# 資料庫
POSTGRES_PASSWORD=your_secure_password

# 期貨監控設定
FUTURES_ENABLED_CONTRACTS=TXF,MXF,MTX
FUTURES_MONITOR_INTERVAL=30
```

### 3. 啟動服務

#### macOS / Linux
```bash
# 開發環境 (僅股票監控)
make dev

# 生產環境 (僅股票監控)
make prod

# 啟動全部服務 (股票 + 期貨)
docker-compose --profile full up -d

# 僅啟動期貨監控
docker-compose --profile futures up -d

# 查看服務狀態
make status
```

#### Windows 11
```batch
# 開發環境 (僅股票監控)
scripts\start-windows-dev.bat

# 生產環境 (僅股票監控)
scripts\start-windows-prod.bat

# 啟動全部服務 (股票 + 期貨)
docker-compose --profile full up -d

# 僅啟動期貨監控
docker-compose --profile futures up -d

# 檢查服務健康
scripts\windows-health-check.bat
```

#### 期貨監控獨立啟動
```bash
# 僅啟動期貨監控所需服務 (資料庫 + Redis + 期貨監控)
docker-compose up postgres redis futures-monitor -d

# 開發模式直接執行期貨監控
source venv/bin/activate
python -m src.futures.main

# 注意：期貨監控需要 postgres 和 redis 服務支援
# 如果資料庫未啟動，請先執行：
# docker-compose up postgres redis -d
```

### 4. 平台最佳化部署

#### Mac Mini 2015 優化

```bash
# 使用資源限制版本
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

#### Windows 11 筆電優化

```batch
# 使用 Windows 最佳化配置
docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d

# 或使用便捷腳本
scripts\start-windows-prod.bat
```

**效能配置差異：**
- **Mac Mini 2015**: 2GB RAM, 2 CPU cores
- **Windows 11 筆電**: 4GB RAM, 4 CPU cores
- **掃描間隔**: Windows 版本較短 (5分鐘 vs 10分鐘)

## 📁 專案結構

```
bag.holder.tw/
├── src/                          # 主要程式碼
│   ├── api/                      # API 客戶端
│   │   └── fubon_client.py      # 富邦證券 SDK 客戶端
│   ├── database/                 # 資料庫相關
│   │   ├── models.py            # 資料模型
│   │   └── connection.py        # 資料庫連線
│   ├── scanner/                  # 市場掃描引擎
│   ├── indicators/               # 技術指標計算
│   ├── backtest/                 # 🆕 回測系統
│   │   ├── main.py              # 回測主程式
│   │   ├── data_source.py       # YFinance 資料源
│   │   ├── engine.py            # 回測引擎
│   │   ├── strategy.py          # 策略執行器
│   │   ├── analyzer.py          # 績效分析器
│   │   ├── reporter.py          # 報告生成器
│   │   └── models.py            # 回測資料模型
│   ├── futures/                  # 期貨監控模組
│   │   ├── main.py              # 期貨監控主程式
│   │   └── monitor.py           # 台指期貨監控邏輯
│   ├── telegram/                 # Telegram Bot
│   └── utils/                    # 工具模組
│       ├── logger.py            # 日誌系統
│       ├── rate_limiter.py      # 限流管理
│       └── error_handler.py     # 錯誤處理
├── config/                       # 配置管理
│   └── settings.py              # 設定檔
├── data/                         # 資料目錄
│   └── init.sql                 # 資料庫初始化
├── reports/                      # 🆕 回測報告目錄
├── docker/                       # 容器化
│   └── Dockerfile               # Docker 映像檔
├── logs/                         # 日誌檔案
├── tests/                        # 測試程式
├── docker-compose.yml            # 服務編排
├── docker-compose.override.yml   # Mac Mini 優化
├── requirements.txt              # Python 依賴
├── .env.example                  # 配置範例
└── README.md                     # 專案說明
```

## 🔬 策略回測系統

### 系統概述

完整的策略回測框架，整合 YFinance 資料源，驗證技術分析策略在台股市場的實際績效。

### 核心功能

#### 📊 資料獲取 (YFinance)
- **台股資料**: 自動獲取台股上市櫃股票歷史資料
- **基準比較**: 大盤指數 (TAIEX) 資料用於績效比較
- **資料快取**: 本地 CSV 檔案快取，提升回測效率
- **市場篩選**: 自動篩選市值大於 10 億、日均量 > 1000 張的股票

#### ⚙️ 技術指標引擎
- **移動平均**: MA5, MA10, MA20, MA60
- **動量指標**: RSI (14日)
- **趨勢追蹤**: MACD (12,26,9)
- **波動分析**: 布林通道 (20日，2標準差)
- **成交量確認**: 成交量移動平均 (20日)

#### 🎯 交易訊號系統
**買進訊號**:
- Golden Cross: MA5 突破 MA20 向上
- RSI Oversold: RSI < 30
- MACD Golden Cross: MACD 線突破訊號線向上
- BB Squeeze Break: 突破布林通道上軌

**賣出訊號**:
- Death Cross: MA5 跌破 MA20 向下
- RSI Overbought: RSI > 70
- MACD Death Cross: MACD 線跌破訊號線向下

#### 💼 投資組合管理
- **風險控制**: 停損 -10%、停利 +20%
- **資金管理**: 每筆交易最多使用 10% 資金
- **交易成本**: 手續費 0.1425%、交易稅 0.3%
- **最長持倉**: 30 個交易日自動出場

#### 📈 績效分析
- **基本指標**: 總報酬率、年化報酬率、夏普比率
- **風險指標**: 最大回撤、波動度、VaR、CVaR
- **交易統計**: 勝率、獲利因子、平均持倉期間
- **基準比較**: vs 大盤表現，計算 Alpha、Beta 值

### 快速開始

#### 安裝依賴
```bash
# 啟動虛擬環境
source venv/bin/activate

# 安裝回測系統依賴
pip install yfinance numpy
```

#### 運行回測
```bash
# 完整回測 (2024-09-01 至今)
python run_backtest.py

# 快速測試 (最近 30 天)
python -c "
import asyncio
from src.backtest.main import BacktestRunner
runner = BacktestRunner()
asyncio.run(runner.run_quick_test())
"
```

#### 輸出檔案
回測完成後會在以下目錄生成檔案：

**data/ 目錄**:
- `historical_data_*.csv`: 歷史價格資料
- `trades_*.csv`: 交易明細記錄
- `portfolio_*.csv`: 投資組合歷史
- `signals_*.csv`: 交易訊號記錄

**reports/ 目錄**:
- `report_*.md`: 詳細回測報告，包含:
  - 📊 投資績效摘要
  - 🎯 交易統計分析
  - 🔍 訊號效果分析
  - ⚠️ 風險指標詳情
  - 📋 策略優化建議

### 回測報告範例

```
📊 BACKTEST RESULTS
==================================================
📈 Total Return: 15.2%
🎯 Win Rate: 62.5%
📉 Max Drawdown: -8.3%
⚡ Sharpe Ratio: 1.45
🔢 Total Trades: 48
✅ Winning Trades: 30
❌ Losing Trades: 18
```

### 自定義回測參數

```python
from src.backtest.main import BacktestRunner
from decimal import Decimal
from datetime import date

runner = BacktestRunner()
result = await runner.run_full_backtest(
    start_date=date(2024, 1, 1),
    end_date=date.today(),
    initial_capital=Decimal('500000')  # 50萬初始資金
)
```

### 單元測試

```bash
# 運行回測系統測試
python -m pytest tests/test_backtest.py -v

# 測試特定模組
python -m pytest tests/test_backtest.py::TestBacktestEngine -v
```

## 🎯 台指期貨監控

### 監控範圍
本系統專注於台灣指數期貨最重要的三大合約：

- **TXF (大台)**: 台指期貨，合約大小 200 點，適合大額交易
- **MXF (小台)**: 小台指期貨，合約大小 50 點，適合中額交易
- **MTX (微台)**: 微型台指期貨，合約大小 10 點，適合小額交易

### 自動化功能
- **近月合約追蹤**: 自動計算並追蹤近月到期合約
- **價格突破警示**: 1.5% 以上價格變動即時通知
- **成交量異常檢測**: 各合約專用成交量監控
- **高波動檢測**: 3% 以上振幅變化警報
- **技術指標分析**: 專為期貨設計的技術指標

### 啟動期貨監控

```bash
# 啟動全部服務 (股票 + 期貨，推薦)
docker-compose --profile full up -d

# 僅啟動期貨監控相關服務
docker-compose --profile futures up -d

# 最小化啟動 (手動指定服務)
docker-compose up postgres redis futures-monitor -d

# 開發模式
source venv/bin/activate
python -m src.futures.main
```

### 期貨監控設定

在 `.env` 檔案中配置：

```env
# 期貨監控設定
FUTURES_ENABLED_CONTRACTS=TXF,MXF,MTX  # 啟用的合約
FUTURES_MONITOR_INTERVAL=30            # 監控間隔 (秒)
FUTURES_MAX_POSITION_SIZE=10           # 最大部位大小
FUBON_IS_SIMULATION=true               # 模擬交易模式
```

## 🔧 主要功能模組

### 📊 資料庫架構

#### 股票相關
- **stocks**: 股票主檔 (代號、名稱、市場)
- **stock_prices**: 歷史價格資料 (OHLCV)
- **stock_realtime**: 即時報價
- **technical_indicators**: 技術指標
- **alerts**: 警報信號
- **portfolios**: 投資組合
- **transactions**: 交易記錄

#### 期貨相關
- **futures_contracts**: 期貨合約主檔 (TXF, MXF, MTX)
- **futures_quotes**: 期貨即時報價
- **futures_signals**: 期貨交易信號
- **futures_positions**: 期貨部位記錄

### 🚦 Rate Limiting 系統

支援三種限流方式：
- **記憶體限流**: 單機簡單限流
- **Redis 限流**: 分散式限流
- **資料庫限流**: 持久化限流記錄

### 📝 日誌系統

- **結構化日誌**: JSON 格式便於分析
- **多層級輸出**: Console + File + Database
- **錯誤追蹤**: 自動錯誤統計與分類
- **Telegram 警報**: 重大錯誤即時通知

### 🔄 錯誤處理

- **重試機制**: 自動重試失敗的 API 調用
- **熔斷器模式**: 防止服務雪崩
- **優雅降級**: 確保服務穩定性

## 🛠️ 開發指南

### 本地開發環境

```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安裝依賴
pip install -r requirements.txt

# 重要: 安裝富邦證券 SDK
# 1. 下載官方 fubon_neo SDK (.whl 檔案)
# 2. 安裝 SDK
pip install fubon_neo-<version>.whl

# 設定資料庫
export DATABASE_URL="postgresql://postgres:password@localhost:5432/tw_stock"

# 執行股票監控應用
python src/main.py

# 或執行期貨監控
python -m src.futures.main
```

### 測試

```bash
# 執行所有測試
pytest

# 執行特定測試
pytest tests/test_api/

# 產生覆蓋率報告
pytest --cov=src --cov-report=html
```

### 程式碼品質

```bash
# 格式化程式碼
black src/

# 檢查程式碼風格
flake8 src/

# 型別檢查
mypy src/
```

## 🔍 監控與維運

### 健康檢查

```bash
# 檢查服務狀態
curl http://localhost:8000/health

# 查看系統指標
curl http://localhost:9090/metrics
```

### 日誌查看

```bash
# 應用日誌
docker-compose logs app

# 掃描器日誌
docker-compose logs scanner

# 期貨監控日誌
docker-compose logs futures-monitor

# Telegram Bot 日誌
docker-compose logs telegram-bot

# 資料庫日誌
docker-compose logs postgres
```

### 資料清理

系統會自動執行資料清理：
- 歷史價格資料保留 1 年
- 技術指標保留 1 年
- 警報記錄保留 3 個月
- 系統日誌保留 3 個月

## ⚙️ 配置說明

### 效能調優

針對 Mac Mini 2015 的資源限制：
- 記憶體限制: 2GB
- CPU 限制: 2 核心
- 批次處理延遲: 1 秒
- 併發連線數: 10

### API 限制

- 富邦 API: 30 次/分鐘
- Telegram API: 30 次/秒
- 掃描間隔: 5 分鐘

## 🚨 故障排除

### 常見問題

1. **資料庫連線失敗**
   ```bash
   # 檢查資料庫狀態
   docker-compose ps postgres
   docker-compose logs postgres
   ```

2. **API 限流錯誤**
   ```bash
   # 檢查 Redis 狀態
   docker-compose ps redis
   # 清除限流記錄
   docker-compose exec redis redis-cli FLUSHDB
   ```

3. **記憶體不足**
   ```bash
   # 調整資源限制
   nano docker-compose.override.yml
   ```

## 📈 效能指標

### 股票監控
- 掃描速度: ~1,800 股票/5分鐘
- 記憶體使用: <4GB (含所有服務)
- CPU 使用: <50% (雙核心)
- 資料庫大小: ~500MB/年

### 期貨監控
- 監控合約: 3 個 (TXF, MXF, MTX)
- 監控頻率: 每 30 秒更新
- 額外記憶體: ~200MB
- 期貨資料: ~100MB/年

## 🤝 貢獻指南

1. Fork 專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交變更 (`git commit -m 'Add some amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 建立 Pull Request

## 📄 授權條款

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

## 🙏 致謝

- [富邦證券 fubon_neo SDK](https://www.fbs.com.tw/) - 官方 API 與期貨資料來源
- [Telegram Bot API](https://core.telegram.org/bots/api) - 通知系統
- [TA-Lib](https://ta-lib.org/) - 技術指標計算
- [FastAPI](https://fastapi.tiangolo.com/) - 高效能 Web 框架
- [PostgreSQL](https://www.postgresql.org/) - 穩定的資料庫系統

---

## 📝 變更日誌 (Change Log)

### v1.1.0 - 2026-03-25
#### 🎯 新增功能
- **台指期貨監控**: 新增專門監控台指期貨三大合約 (TXF大台/MXF小台/MTX微台)
- **近月合約追蹤**: 自動計算並追蹤近月到期合約 (第三個週三)
- **期貨信號檢測**:
  - 價格突破警示 (1.5% 以上變動)
  - 成交量異常檢測 (2倍平均值)
  - 高波動檢測 (3% 以上振幅)
- **雙重認證支援**: API Key 或憑證檔案兩種認證方式
- **Docker Profile**: 期貨監控獨立 profile，可選擇性啟動

#### 🔧 技術改進
- **官方 SDK 整合**: 更新為使用富邦證券 fubon_neo 官方 SDK
- **系統架構優化**: 新增 futures/ 模組，模組化期貨監控邏輯
- **單元測試覆蓋**: 新增完整的期貨監控單元測試套件
- **設定檔強化**: 支援期貨監控相關環境變數配置

#### 📊 資料庫更新
- **期貨相關表格**: 新增 futures_contracts, futures_quotes, futures_signals, futures_positions

#### 📋 文檔更新
- **README.md**: 更新專案架構圖、啟動指令、配置說明
- **期貨監控章節**: 詳細說明三大合約監控功能與配置
- **效能指標**: 分離股票與期貨監控的效能數據

#### 🧪 測試改進
- **test_futures.py**: 新增 25+ 個期貨監控單元測試
- **涵蓋範圍**: 合約管理、報價處理、信號檢測、錯誤處理

### v1.0.0 - 2026-03-24
#### 🎉 初始版本
- **股票監控**: 全市場 1,800+ 檔股票掃描
- **技術指標**: MA, RSI, MACD, 布林通道
- **Telegram Bot**: 即時通知系統
- **投資組合管理**: 個人投資組合追蹤
- **容器化部署**: Docker + Docker Compose
- **跨平台支援**: macOS, Windows 11, Linux

---

**免責聲明**: 本系統僅供參考，不構成投資建議。投資有風險，請謹慎評估。