# 降低觸發交易次數的方法

> 記錄日期：2026-04-09
> 狀態：方法 8 已實作

---

## 現有過濾器強化

### 方法 1：縮小動能 Top-N 範圍
- **現況**：momentum_top_n = 30（20 日報酬排名前 30 名）
- **方向**：降至 top 15 或 top 20，只選最強動能股
- **設定**：`BACKTEST_MOMENTUM_TOP_N`

### 方法 2：提高 RSI 最低進場門檻
- **現況**：`rsi_min_entry = 50`（RSI ≥ 50 才進場）
- **方向**：調高至 55 或 60，確保動能更充足
- **設定**：`BACKTEST_RSI_MIN_ENTRY`

### 方法 3：提高成交量倍數要求
- **現況**：`volume_confirmation_multiplier = 1.5`（當日量 > 1.5× MA20）
- **方向**：調高至 2.0× 或 2.5×，只接受明顯量增突破
- **設定**：`BACKTEST_VOLUME_CONFIRMATION_MULTIPLIER`
- **注意**：`require_volume_confirmation` 目前預設為 False，需先開啟

### 方法 4：提高族群強度門檻
- **現況**：`sector_trend_threshold = 0.5`（50% 族群股票在 MA20 上方）
- **方向**：調高至 60–65%
- **設定**：`BACKTEST_SECTOR_TREND_THRESHOLD`

---

## 新增過濾條件

### 方法 5：MA60 斜率要求（MA60 本身也要上升）
- **現況**：只檢查 price > MA60（靜態位置）
- **方向**：加入 MA60[今日] > MA60[N 日前]，確保長趨勢本身也在走升
- **實作位置**：`strategy.py` → `_apply_buy_filters`

### 方法 6：訊號組合確認（Multi-signal confirmation）
- **現況**：任一訊號觸發即進場
- **方向**：要求同日同股票觸發 2 個以上買入訊號才算有效進場
- **例子**：Donchian Breakout + MACD Golden Cross 同日觸發

### 方法 7：ADX 趨勢強度過濾
- **現況**：未使用 ADX
- **方向**：加入 ADX ≥ 25 條件，確保股票在真實趨勢中而非橫盤震盪
- **實作位置**：`calculator.py` 新增 ADX 計算；`strategy.py` 加入過濾

### 方法 8：同股票買入冷卻期（Cooldown）✅ 已實作
- **現況**：同一股票可在連續多日觸發買入訊號
- **方向**：同股票在最近 N 個交易日內已觸發過買入訊號，自動跳過
- **設定**：`BACKTEST_SIGNAL_COOLDOWN_DAYS`（0 = 停用，預設 10）
- **實作位置**：`strategy.py` → `generate_signals`（逐歷史日追蹤，對 scanner 也有效）
- **效果**：避免同一支股票在一波上漲中反覆進場

### 方法 9：進場前回檔要求（Pullback filter）
- **現況**：訊號觸發即可進場，不管當下是否在高點
- **方向**：要求訊號觸發前 K 日內有一定幅度回檔（例如從近期高點回落 > 3–5%），避免追高
- **實作位置**：`strategy.py` → `_apply_buy_filters`

### 方法 10：停用低勝率訊號
- **現況**：Golden Cross / MACD Golden Cross 單獨出現時勝率約 22–32%
- **方向**：只有在與其他訊號同日同股票出現時才有效，或移回 `disabled_signals`
- **設定**：`BACKTEST_DISABLED_SIGNALS`

---

## 建議回測驗證順序

1. **方法 8**（冷卻期，已實作）→ 直接驗證成效
2. **方法 2**（RSI 門檻 50 → 55）→ 只調數值，低風險
3. **方法 1**（top 30 → top 20）→ 只調數值，低風險
4. **方法 6**（多訊號組合確認）→ 需新增邏輯
5. **方法 5**（MA60 斜率）→ 需新增邏輯
6. **方法 7**（ADX）→ 需新增指標計算
