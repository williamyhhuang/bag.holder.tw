"""
Holdings Checker — 持倉賣出檢查服務

流程：
1. 讀 Google Sheets 取得未平倉持倉
2. 執行 SignalsScanner.scan_today() 取全市場賣出訊號
3. 篩選持倉股的賣出訊號並 enrich（pnl%, holding_days, sector, revenue_yoy）
4. 呼叫 AI 做出場決策（sell / watch / hold）
"""

from datetime import date
from typing import Dict, List

from ...infrastructure.persistence.google_sheets_reader import GoogleSheetsReader
from ...infrastructure.market_data.revenue_filter import MonthlyRevenueLoader, get_revenue_yoy
from ...utils.logger import get_logger
from .signals_scanner import SignalsScanner
from config.settings import settings

logger = get_logger(__name__)


def _normalize(symbol: str) -> str:
    """'2330.TW' → '2330', '4741.TWO' → '4741'"""
    if symbol.endswith('.TWO'):
        return symbol[:-4]
    if symbol.endswith('.TW'):
        return symbol[:-3]
    return symbol


def _to_internal_symbol(display: str) -> str:
    """'2330.TW' → '2330', '4741.TWO' → '4741O'（內部格式）"""
    if display.endswith('.TWO'):
        return display[:-4] + 'O'
    if display.endswith('.TW'):
        return display[:-3]
    return display


class HoldingsChecker:
    """今日持倉賣出檢查器"""

    def __init__(self, fubon_sdk=None):
        self.logger = get_logger(self.__class__.__name__)
        self._fubon_sdk = fubon_sdk

    def check(self) -> Dict:
        """
        執行持倉賣出檢查。

        Returns:
            {
              'target_date': date,
              'open_positions': ['2330', '2454', ...],
              'sell_alerts': [...],           # 有賣出訊號的持倉（enriched）
              'ai_result': {'sell': [...], 'watch': [...], 'hold': [...]},
            }
        """
        # 1. 讀取未平倉持倉
        reader = GoogleSheetsReader()
        holdings = reader.get_open_positions()

        if not holdings:
            self.logger.info("無持倉記錄，略過檢查")
            return {
                'target_date': date.today(),
                'open_positions': [],
                'sell_alerts': [],
                'ai_result': {'sell': [], 'watch': [], 'hold': []},
            }

        holdings_by_code = {h.stock_code: h for h in holdings}
        holding_codes = set(holdings_by_code.keys())
        self.logger.info(f"未平倉持倉 {len(holding_codes)} 支：{', '.join(sorted(holding_codes))}")

        # 2. 全市場訊號掃描
        scanner = SignalsScanner(fubon_sdk=self._fubon_sdk)
        scan_result = scanner.scan_today()
        today = scan_result['target_date']

        # 3. 篩選持倉有賣出訊號的股票
        sell_alerts = [
            dict(s) for s in scan_result['sell']
            if _normalize(s['symbol']) in holding_codes
        ]
        self.logger.info(
            f"掃描完成，持倉 {len(holding_codes)} 支中有 {len(sell_alerts)} 支出現賣出訊號"
        )

        if not sell_alerts:
            return {
                'target_date': today,
                'open_positions': list(holding_codes),
                'sell_alerts': [],
                'ai_result': {'sell': [], 'watch': [], 'hold': []},
            }

        # 4. Enrich sell_alerts
        sector_map = {
            r['sector']: r['is_strong']
            for r in scan_result.get('sector_summary', [])
        }
        revenue_map: Dict = {}
        try:
            revenue_map = MonthlyRevenueLoader().load()
        except Exception as e:
            self.logger.warning(f"無法載入月營收資料: {e}")

        for alert in sell_alerts:
            code = _normalize(alert['symbol'])
            h = holdings_by_code.get(code)
            if h:
                alert['entry_price'] = h.entry_price
                alert['holding_days'] = (today - date.fromisoformat(h.entry_date)).days
                if h.entry_price and h.entry_price > 0:
                    alert['pnl_pct'] = round(
                        (alert['price'] - h.entry_price) / h.entry_price * 100, 2
                    )
                else:
                    alert['pnl_pct'] = None

            # Sector
            internal = _to_internal_symbol(alert['symbol'])
            stock_sector = scanner.sector_analyzer.get_stock_sector(internal)
            alert['sector'] = stock_sector
            alert['sector_is_strong'] = sector_map.get(stock_sector, False)

            # Revenue YoY（OTC: '4741O' → revenue_key '4741'；TSE: '2330' → '2330'）
            revenue_key = internal[:-1] if internal.endswith('O') else internal
            alert['revenue_yoy_pct'] = (
                get_revenue_yoy(revenue_map, revenue_key) if revenue_map else None
            )

        # 5. AI 分析
        ai_result = {'sell': [], 'watch': [], 'hold': []}
        try:
            cfg = settings.ai_analyzer
            api_key = cfg.get_api_key()
            if api_key:
                from ...infrastructure.ai.factory import create_analyzer
                analyzer = create_analyzer(
                    provider=cfg.provider, api_key=api_key, model=cfg.model
                )
                ai_result = analyzer.analyze_holdings(sell_alerts)
                self.logger.info(
                    f"AI 持倉分析完成：出場 {len(ai_result['sell'])} 支，"
                    f"觀察 {len(ai_result['watch'])} 支，"
                    f"持有 {len(ai_result['hold'])} 支"
                )
            else:
                self.logger.warning("未設定 AI API Key，略過 AI 持倉分析")
        except Exception as e:
            self.logger.error(f"AI 持倉分析失敗: {e}")

        return {
            'target_date': today,
            'open_positions': list(holding_codes),
            'sell_alerts': sell_alerts,
            'ai_result': ai_result,
        }
