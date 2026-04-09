"""
Sector Trend Analyzer — 族群趨勢分析器
=========================================
依 TWSE/TPEX 官方產業別代碼將個股分組到對應族群，
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

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Set

from src.backtest.models import StockData
from src.utils.logger import get_logger
from src.utils.stock_industry_mapper import (
    get_stock_industries,
    get_sector_name,
    INDUSTRY_CODE_TO_SECTOR,
)

logger = get_logger(__name__)

# 這些族群不做趨勢過濾（意義不大或數量太少）
_EXEMPT_SECTORS: Set[str] = {"其他", "綜合", "存託憑證", "ETF"}

# 族群至少需要幾支有效股票才計算強度（否則視為強勢，不過濾）
MIN_SECTOR_STOCKS = 3

# ── 代碼前綴降級映射（API 不可用時的備援）────────────────────────────────────
# 只保留 TSE 傳統股（11-28xx）的可靠前綴，其他一律歸 '其他'
_FALLBACK_PREFIX_TO_CODE: Dict[str, str] = {
    "11": "01",  # 水泥
    "12": "02",  # 食品
    "13": "03",  # 塑膠
    "14": "04",  # 紡織
    "15": "05",  # 電機機械
    "16": "06",  # 電器電纜
    "17": "07",  # 化學
    "18": "08",  # 玻璃陶瓷
    "19": "09",  # 造紙
    "20": "10",  # 鋼鐵
    "21": "11",  # 橡膠
    "22": "12",  # 汽車
    "23": "13",  # 電子
    "24": "22",  # 半導體
    "25": "14",  # 建材
    "26": "15",  # 航運
    "27": "16",  # 觀光
    "28": "17",  # 金融
    "29": "18",  # 貿易百貨
}


def _extract_code(symbol: str) -> str:
    """從內部 symbol 取出純數字代碼（去除 OTC 的 'O' 後綴）。
    例: '2330' → '2330', '4741O' → '4741'
    """
    return symbol.rstrip("O")


class SectorTrendAnalyzer:
    """台股族群趨勢分析器。

    優先使用 TWSE/TPEX 官方產業別資料；
    API 不可用時降級為代碼前綴推斷（僅適用於傳統上市股）。
    """

    def __init__(self):
        # 載入官方產業別對照表（含快取機制）
        self._industries: Dict[str, str] = {}
        self._load_industries()

    def _load_industries(self) -> None:
        """載入股票代號 → 產業別代碼對照表"""
        try:
            self._industries = get_stock_industries(use_cache=True)
            logger.debug(f"載入 {len(self._industries)} 支股票產業別代碼")
        except Exception as e:
            logger.warning(f"載入產業別代碼失敗，將使用代碼前綴降級: {e}")
            self._industries = {}

    def get_stock_sector(self, symbol: str) -> str:
        """回傳股票所屬族群名稱。

        Args:
            symbol: 內部 symbol，如 '2330'、'4741O'

        Returns:
            族群名稱字串（如 '半導體業'、'金融保險'）
        """
        code = _extract_code(symbol)

        # 優先使用官方產業別代碼
        industry_code = self._industries.get(code)
        if industry_code:
            return get_sector_name(industry_code)

        # 降級：代碼前綴推斷（僅對傳統 TSE 股有效）
        prefix = code[:2]
        fallback_industry = _FALLBACK_PREFIX_TO_CODE.get(prefix)
        if fallback_industry:
            return get_sector_name(fallback_industry)

        return "其他"

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
        # 族群 → 統計 (above_ma, total)
        sector_counts: Dict[str, List[int]] = {}

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
        strong = set(_EXEMPT_SECTORS)  # 免過濾族群永遠視為強勢
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
