# Docker 部署說明

## 服務架構

本系統使用 Docker Compose 運行多個獨立服務：

### 🔧 核心服務

1. **redis** - 快取和速率限制
2. **app** - 主應用程式（CLI 介面）
3. **downloader** - 定時下載股票資料
4. **scanner** - 定時股票掃描分析
5. **telegram-bot** - Telegram 整合服務
6. **futures-monitor** - 期貨分析服務
7. **backtest** - 回測服務

### 📋 服務執行時程

- **downloader**: 每日執行一次 (86400 秒)
- **scanner**: 每小時執行一次 (3600 秒)
- **futures-monitor**: 每 30 分鐘執行一次 (1800 秒)
- **telegram-bot**: 持續運行
- **backtest**: 手動執行

## 快速開始

### 1. 環境準備

```bash
# 複製環境變數範例檔案
cp .env.example .env

# 編輯環境變數
vi .env
```

必須設定的環境變數：
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
REDIS_URL=redis://redis:6379
```

### 2. 基本部署

```bash
# 啟動核心服務 (redis + app + downloader + scanner)
docker compose up -d redis app downloader scanner

# 查看服務狀態
docker compose ps

# 查看日誌
docker compose logs -f scanner
```

### 3. 完整部署

```bash
# 啟動所有服務（包含期貨監控）
docker compose --profile full up -d

# 或僅啟動期貨相關服務
docker compose --profile futures up -d
```

### 4. 手動執行回測

```bash
# 執行回測
docker compose --profile backtest run --rm backtest

# 或直接透過 app 服務執行
docker compose exec app python main.py backtest
```

## 服務管理

### 查看服務狀態

```bash
# 查看所有服務
docker compose ps

# 查看特定服務日誌
docker compose logs -f downloader
docker compose logs -f scanner
docker compose logs -f futures-monitor
```

### 手動執行任務

```bash
# 手動下載資料
docker compose exec app python main.py download

# 手動執行掃描
docker compose exec app python main.py scan --send-telegram

# 手動期貨分析
docker compose exec app python main.py futures --send-telegram

# 查看幫助
docker compose exec app python main.py --help
```

### 服務重啟

```bash
# 重啟特定服務
docker compose restart scanner

# 重啟所有服務
docker compose restart

# 停止並移除所有服務
docker compose down
```

## 資料持久化

### Volume 掛載

- `./data:/app/data` - 股票資料 CSV 檔案
- `./logs:/app/logs` - 應用程式日誌
- `./reports:/app/reports` - 回測報告
- `redis_data` - Redis 資料

### 備份重要資料

```bash
# 備份股票資料
tar -czf backup_$(date +%Y%m%d).tar.gz data/

# 備份日誌
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/
```

## 監控和除錯

### 健康檢查

```bash
# 檢查 Redis 連線
docker compose exec redis redis-cli ping

# 檢查應用程式狀態
docker compose exec app python -c "print('✅ App is running')"
```

### 除錯指令

```bash
# 進入容器檢查
docker compose exec app bash

# 查看 Python 套件
docker compose exec app pip list

# 檢查資料目錄
docker compose exec app ls -la data/stocks/
```

### 效能監控

```bash
# 查看容器資源使用
docker stats

# 查看服務資源使用
docker compose exec app top
```

## 客製化設定

### 修改執行頻率

編輯 `docker-compose.yml` 中的 `sleep` 時間：

```yaml
# 例如：每 2 小時執行掃描
command: >
  sh -c "
  while true; do
    echo 'Starting stock scan...'
    python main.py scan --send-telegram
    echo 'Scan completed. Waiting for next run...'
    sleep 7200
  done
  "
```

### 新增環境變數

在 `docker-compose.yml` 的 `environment` 區段新增：

```yaml
environment:
  - REDIS_URL=redis://redis:6379
  - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
  - YOUR_CUSTOM_VAR=${YOUR_CUSTOM_VAR}
```

## 故障排除

### 常見問題

1. **Redis 連線失敗**
   ```bash
   docker compose logs redis
   docker compose exec redis redis-cli ping
   ```

2. **Telegram 無法發送訊息**
   - 檢查 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
   - 確認 bot 有發送訊息權限

3. **股票資料下載失敗**
   - 檢查網路連線
   - yfinance API 可能暫時無法使用

4. **記憶體不足**
   ```bash
   # 限制容器記憶體使用
   docker compose exec app python main.py scan --strategy momentum
   ```

### 重置環境

```bash
# 完全重置（會刪除所有資料）
docker compose down -v
docker compose up -d
```

## 生產環境建議

1. **資源限制**: 在 compose 檔案中加入 resource limits
2. **日誌輪轉**: 設定日誌檔案大小限制
3. **備份策略**: 定期備份重要資料
4. **監控**: 加入 Prometheus/Grafana 監控
5. **安全性**: 使用 secrets 管理敏感資料
