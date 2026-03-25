# 需求
我現在還沒有富邦 API key，請建立回測系統，並從 yfinance 取得資料驗證現在的策略勝率是多少

# 條件
1. 資料源從 yfinance SDK 取得
2. 用2024-09 ~ now 的分析資料進行回測
3. 將分析資料存成 csv，以便後續回測使用
4. 將回測報告以 markdown 形式呈現，需包含可優化策略建議

# 實作計畫

## 現有策略分析
基於 `src/indicators/calculator.py` 和 `src/scanner/engine.py` 的分析，現有交易策略包含：

1. **技術指標計算**：
   - 移動平均線（MA5, MA10, MA20, MA60）
   - RSI（14日）
   - MACD（12,26,9）
   - 布林通道（20日，2標準差）
   - 成交量移動平均（20日）

2. **交易訊號**：
   - **買進訊號**：
     - Golden Cross：MA5 突破 MA20 向上
     - RSI Oversold：RSI < 30
     - MACD Golden Cross：MACD 線突破訊號線向上
     - BB Squeeze Break：突破布林通道上軌
   - **賣出訊號**：
     - Death Cross：MA5 跌破 MA20 向下
     - RSI Overbought：RSI > 70
     - MACD Death Cross：MACD 線跌破訊號線向下
   - **關注訊號**：
     - Volume Surge：成交量異常放大（2倍於20日均量）

## 系統架構設計

### 1. 資料獲取模組 (`src/backtest/data_source.py`)
- 使用 yfinance 獲取台股歷史資料
- 資料格式轉換與清理
- 支援批次下載多檔股票
- 資料快取機制

### 2. 回測引擎 (`src/backtest/engine.py`)
- 時間序列回測框架
- 持倉管理（買進、賣出、持有）
- 交易成本計算（手續費、交易稅）
- 資金管理（現金流、槓桿控制）

### 3. 策略執行器 (`src/backtest/strategy.py`)
- 整合現有技術指標計算邏輯
- 套用現有交易訊號判斷規則
- 支援多種進出場策略
- 風險控制機制（停損、停利）

### 4. 績效分析器 (`src/backtest/analyzer.py`)
- 計算關鍵績效指標：
  - 總報酬率、年化報酬率
  - 夏普比率、最大回撤
  - 勝率、平均獲利/虧損
  - 交易次數、持倉時間分析
- 基準比較（大盤指數）

### 5. 報告生成器 (`src/backtest/reporter.py`)
- 生成詳細的 Markdown 回測報告
- 輸出交易明細 CSV
- 績效圖表生成
- 策略優化建議

## 實作步驟

### Phase 1: 基礎建設
1. [pending] 分析現有策略邏輯，了解交易訊號的判斷條件
2. [pending] 設計回測系統架構，包含 yfinance 資料源整合
3. [pending] 實作 yfinance 資料獲取模組，取得台股 2024-09 到現在的歷史資料

### Phase 2: 核心功能
4. [pending] 實作回測引擎，包含持倉管理和績效計算
5. [pending] 實作策略回測執行器，套用現有交易策略邏輯
6. [pending] 實作回測結果分析和報告生成，輸出 CSV 檔案

### Phase 3: 報告與測試
7. [pending] 建立回測報告 Markdown 模板，包含勝率分析和策略優化建議
8. [pending] 撰寫單元測試覆蓋回測系統各模組
9. [pending] 執行完整回測並生成最終報告

## 預期產出

### 1. 程式碼模組
- `src/backtest/` 目錄下的完整回測系統
- 單元測試檔案 `tests/test_backtest.py`

### 2. 資料檔案
- `data/historical_data.csv` - 歷史價格資料
- `data/trading_signals.csv` - 交易訊號記錄
- `data/backtest_results.csv` - 回測交易明細

### 3. 分析報告
- `reports/backtest_report.md` - 詳細回測報告
- 包含策略績效分析、勝率統計、優化建議

## 技術規格

### 回測參數
- **回測期間**：2024-09-01 至今
- **初始資金**：1,000,000 TWD
- **交易成本**：
  - 手續費：0.1425%（買進/賣出各收一次）
  - 交易稅：0.3%（僅賣出時收取）
- **資金配置**：每筆交易最多使用 10% 資金

### 股票池選擇
- 台股上市櫃股票
- 市值 > 10億、日均量 > 1000張
- 排除全額交割股、注意股票

### 進出場規則
- **進場條件**：任一買進訊號觸發
- **出場條件**：
  - 賣出訊號觸發
  - 停損：-10%
  - 停利：+20%
  - 最長持倉：30個交易日