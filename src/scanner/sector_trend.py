"""
Sector Trend Analyzer — 族群趨勢分析器
=========================================
依台灣股票代碼前兩碼將個股分組到對應族群，
計算各族群強度（收盤價 > MA20 的股票比例），
只保留強勢族群的買入訊號。

族群強度定義：
  strength = 族群內「收盤 > MA20」股票數 / 族群股票總數（有資料者）
  strength >= threshold（預設 0.5）→ 強勢族群
  strength <  threshold            → 弱勢族群（買入訊號降為 WATCH）

使用方式：
  analyzer = SectorTrendAnalyzer()
  sector_strength = analyzer.compute_sector_strength(stock_data, target_date)
  strong = analyzer.get_strong_sectors(sector_strength, threshold=0.5)
  sector = analyzer.get_stock_sector("2330")  # → "半導體業"
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set

from src.backtest.models import StockData
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─── 股票代碼前兩碼 → 族群名稱 ─────────────────────────────────────────────
# 依 TWSE 官方產業別分類，同性質細分類合併為一個較粗的族群，
# 確保每個族群有足夠的股票數量（≥ MIN_SECTOR_STOCKS）才有統計意義。
_PREFIX_TO_SECTOR: Dict[str, str] = {
    # ── ETF ──────────────────────────────────────────────────────────────
    "00": "ETF",
    # ── 傳統產業 ─────────────────────────────────────────────────────────
    "11": "水泥工業",
    "12": "食品工業",
    "13": "塑膠工業",
    "17": "塑膠工業",       # 化學工業 → 與塑膠合併
    "14": "紡織纖維",
    "15": "電機機械",
    "16": "電器電纜",
    "18": "傳統工業",       # 玻璃陶瓷
    "19": "傳統工業",       # 造紙工業
    "20": "鋼鐵工業",
    "21": "橡膠汽車",       # 橡膠工業
    "22": "橡膠汽車",       # 汽車工業
    "25": "建材營造",
    "26": "航運業",
    "27": "觀光餐旅",
    "29": "貿易百貨",
    # ── 金融 ─────────────────────────────────────────────────────────────
    "28": "金融保險",
    "51": "金融保險", "52": "金融保險", "53": "金融保險",
    "54": "金融保險", "55": "金融保險", "56": "金融保險",
    "57": "金融保險", "58": "金融保險",
    # ── 電子/半導體（上市）────────────────────────────────────────────────
    "23": "電子工業",
    "24": "半導體業",
    "32": "光電業",
    "33": "通信網路",
    "34": "電子通路",
    "35": "半導體業",       # 半導體(上櫃)，與上市合併
    "31": "電子零組件",
    "36": "電子零組件",
    "37": "電子零組件",
    "38": "電子零組件",
    "39": "電子零組件",
    # ── 科技（上櫃）──────────────────────────────────────────────────────
    "30": "科技上櫃",
    "60": "科技上櫃", "61": "科技上櫃", "62": "科技上櫃",
    "63": "科技上櫃", "64": "科技上櫃", "65": "科技上櫃",
    "80": "科技上櫃", "81": "科技上櫃", "82": "科技上櫃",
    "83": "科技上櫃", "84": "科技上櫃", "85": "科技上櫃",
    "86": "科技上櫃", "87": "科技上櫃", "88": "科技上櫃", "89": "科技上櫃",
    # ── 生技醫療 ─────────────────────────────────────────────────────────
    "41": "生技醫療", "42": "生技醫療", "43": "生技醫療",
    "66": "生技醫療", "67": "生技醫療", "68": "生技醫療", "69": "生技醫療",
    # ── 其他 ─────────────────────────────────────────────────────────────
    "91": "其他", "92": "其他", "93": "其他", "94": "其他",
    "95": "其他", "96": "其他", "97": "其他", "98": "其他", "99": "其他",
}

# 這些族群不做趨勢過濾（ETF、其他分類意義不大）
_EXEMPT_SECTORS: Set[str] = {"ETF", "其他"}

# 族群至少需要幾支有效股票才計算強度（否則視為強勢，不過濾）
MIN_SECTOR_STOCKS = 3


def _extract_code(symbol: str) -> str:
    """從內部 symbol 取出純數字代碼（去除 OTC 的 'O' 後綴）。
    例: '2330' → '2330', '4741O' → '4741'
    """
    return symbol.rstrip("O")


def _get_sector_from_code(code: str) -> str:
    """依股票代碼前兩碼查詢族群名稱，找不到時回傳 '其他'。"""
    prefix = code[:2]
    return _PREFIX_TO_SECTOR.get(prefix, "其他")


class SectorTrendAnalyzer:
    """台股族群趨勢分析器。

    使用已載入的本地股票資料（OHLCV CSV），
    計算各族群的趨勢強度並回傳強勢族群集合。
    """

    def get_stock_sector(self, symbol: str) -> str:
        """回傳股票所屬族群名稱。

        Args:
            symbol: 內部 symbol，如 '2330'、'4741O'

        Returns:
            族群名稱字串
        """
        code = _extract_code(symbol)
        return _get_sector_from_code(code)

    def compute_sector_strength(
        self,
        stock_data: Dict[str, List[StockData]],
        target_date: date,
        ma_period: int = 20,
    ) -> Dict[str, float]:
        """計算各族群在 target_date 的趨勢強度。

        強度 = 族群內「最近收盤 > MA{ma_period}」的股票比例（0.0 ~ 1.0）。
        - 若族群股票數 < MIN_SECTOR_STOCKS，強度設為 1.0（免過濾）。
        - 若某支股票在 target_date 無資料或指標不足，略過。

        Args:
            stock_data: 股票歷史資料字典 {symbol: [StockData, ...]}
            target_date: 計算基準日（通常為最新交易日）
            ma_period: 移動平均天數（預設 20）

        Returns:
            {族群名稱: 強度分數} — 只包含有資料的族群
        """
        # 族群 → 統計 (above, total)
        sector_counts: Dict[str, List[int]] = {}  # [above_ma, total]

        for symbol, records in stock_data.items():
            sector = self.get_stock_sector(symbol)
            if sector in _EXEMPT_SECTORS:
                continue

            # 找出 target_date 的收盤價
            price_by_date = {r.date: r.close_price for r in records}
            close = price_by_date.get(target_date)
            if close is None:
                continue

            # 計算 MA（取 target_date 前 ma_period 個交易日的平均）
            sorted_dates = sorted(price_by_date.keys())
            dates_up_to_target = [d for d in sorted_dates if d <= target_date]
            if len(dates_up_to_target) < ma_period:
                continue  # 資料不足，略過此股

            ma_dates = dates_up_to_target[-ma_period:]
            ma_value = sum(price_by_date[d] for d in ma_dates) / ma_period

            if sector not in sector_counts:
                sector_counts[sector] = [0, 0]
            sector_counts[sector][1] += 1
            if close > Decimal(str(ma_value)):
                sector_counts[sector][0] += 1

        # 轉換為強度分數
        strength: Dict[str, float] = {}
        for sector, (above, total) in sector_counts.items():
            if total < MIN_SECTOR_STOCKS:
                # 股票數不足時設為 1.0，視為強勢（不過濾）
                strength[sector] = 1.0
            else:
                strength[sector] = above / total

        return strength

    def get_strong_sectors(
        self,
        sector_strength: Dict[str, float],
        threshold: float = 0.5,
    ) -> Set[str]:
        """回傳強勢族群名稱集合。

        Args:
            sector_strength: compute_sector_strength() 的回傳值
            threshold: 強勢族群最低強度門檻（預設 0.5 = 50% 股票在 MA20 上方）

        Returns:
            強勢族群名稱集合；同時含 _EXEMPT_SECTORS（免過濾族群）
        """
        strong = set(_EXEMPT_SECTORS)  # ETF / 其他 永遠視為強勢
        for sector, score in sector_strength.items():
            if score >= threshold:
                strong.add(sector)
        return strong

    def build_sector_summary(
        self,
        sector_strength: Dict[str, float],
        threshold: float = 0.5,
    ) -> List[Dict]:
        """產生族群強度摘要，供日誌與 Telegram 輸出使用。

        Returns:
            按強度降序排列的族群資料清單：
            [{'sector', 'strength_pct', 'is_strong'}, ...]
        """
        rows = []
        for sector, score in sorted(sector_strength.items(), key=lambda x: -x[1]):
            rows.append({
                "sector": sector,
                "strength_pct": round(score * 100, 1),
                "is_strong": score >= threshold,
            })
        return rows
