# 台股監控機器人 (Taiwan Stock Monitoring Robot)

基於富邦 API 的台股監控機器人，能夠全市場掃描 1,800+ 檔股票，進行即時技術指標分析，並透過 Telegram 發送買賣信號通知。

## 🎯 專案特色

- **全市場掃描**: 監控 TSE/OTC 市場 1,800+ 檔股票
- **即時技術分析**: 支援多種技術指標 (MA, RSI, MACD, 布林通道)
- **智能通知系統**: Telegram Bot 推送買賣信號
- **投資組合追蹤**: 個人投資組合管理與績效追蹤
- **容器化部署**: Docker + Docker Compose 一鍵部署
- **Mac Mini 最佳化**: 針對 Mac Mini 2015 資源優化

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                   Taiwan Stock Monitor                      │
├─────────────────────────────────────────────────────────────┤
│  📱 Telegram Bot  │  🔍 Scanner  │  📊 API Server  │  📈 Web │
├─────────────────────────────────────────────────────────────┤
│                    🧠 Core Services                         │
│  • Rate Limiter   • Logger      • Error Handler            │
│  • Config Mgr     • DB Models   • Tech Indicators          │
├─────────────────────────────────────────────────────────────┤
│  💾 PostgreSQL    │  🚀 Redis Cache  │  📊 Fubon API      │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速開始

### 1. 環境需求

- Docker & Docker Compose
- Python 3.11+ (開發用)
- PostgreSQL 15+ (可用 Docker)
- Redis 7+ (可用 Docker)

### 2. 設定配置

```bash
# 複製配置檔案
cp .env.example .env

# 編輯配置檔案，填入真實的 API 金鑰
nano .env
```

必要配置項目：
```env
# 富邦 API
FUBON_API_KEY=your_fubon_api_key_here
FUBON_SECRET=your_fubon_secret_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# 資料庫
POSTGRES_PASSWORD=your_secure_password
```

### 3. 啟動服務

```bash
# 啟動所有服務
docker-compose up -d

# 查看服務狀態
docker-compose ps

# 查看日誌
docker-compose logs -f
```

### 4. Mac Mini 2015 優化部署

```bash
# 使用資源限制版本
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

## 📁 專案結構

```
bag.holder.tw/
├── src/                          # 主要程式碼
│   ├── api/                      # API 客戶端
│   │   └── fubon_client.py      # 富邦 API 客戶端
│   ├── database/                 # 資料庫相關
│   │   ├── models.py            # 資料模型
│   │   └── connection.py        # 資料庫連線
│   ├── scanner/                  # 市場掃描引擎
│   ├── indicators/               # 技術指標計算
│   ├── telegram/                 # Telegram Bot
│   └── utils/                    # 工具模組
│       ├── logger.py            # 日誌系統
│       ├── rate_limiter.py      # 限流管理
│       └── error_handler.py     # 錯誤處理
├── config/                       # 配置管理
│   └── settings.py              # 設定檔
├── data/                         # 資料目錄
│   └── init.sql                 # 資料庫初始化
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

## 🔧 主要功能模組

### 📊 資料庫架構

- **stocks**: 股票主檔 (代號、名稱、市場)
- **stock_prices**: 歷史價格資料 (OHLCV)
- **stock_realtime**: 即時報價
- **technical_indicators**: 技術指標
- **alerts**: 警報信號
- **portfolios**: 投資組合
- **transactions**: 交易記錄

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

# 設定資料庫
export DATABASE_URL="postgresql://postgres:password@localhost:5432/tw_stock"

# 執行應用
python src/main.py
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

- 掃描速度: ~1,800 股票/5分鐘
- 記憶體使用: <4GB (含所有服務)
- CPU 使用: <50% (雙核心)
- 資料庫大小: ~500MB/年

## 🤝 貢獻指南

1. Fork 專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交變更 (`git commit -m 'Add some amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 建立 Pull Request

## 📄 授權條款

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

## 🙏 致謝

- [富邦證券 API](https://www.fubon.com/) - 股價資料來源
- [Telegram Bot API](https://core.telegram.org/bots/api) - 通知系統
- [TA-Lib](https://ta-lib.org/) - 技術指標計算

---

**免責聲明**: 本系統僅供參考，不構成投資建議。投資有風險，請謹慎評估。