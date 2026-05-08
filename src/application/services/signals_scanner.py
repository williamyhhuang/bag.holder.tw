"""
Today's Trading Signals Scanner
=================================
使用 P1 完整策略（TechnicalStrategy + 所有過濾器）掃描今日訊號，
直接輸出「建議買入」「賣出警示」清單。

與 csv_scanner.py 的差異：
  csv_scanner: 簡單閾值條件（觀察清單）
  signals_scanner: P1 完整技術訊號 + MA60/RSI/均線排列/動能前30 過濾（可執行訊號）
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ...infrastructure.market_data.backtest_data_source import YFinanceDataSource
from .backtest_strategy import TechnicalStrategy
from ...domain.models import StockData, TradingSignal, SignalType, TechnicalIndicators
from ...domain.services.sector_trend_analyzer import SectorTrendAnalyzer
from ...infrastructure.market_data.revenue_filter import MonthlyRevenueLoader, get_revenue_million, get_revenue_yoy
from ...infrastructure.market_data.disposal_filter import DisposalStockFilter
from ...infrastructure.market_data.institutional_filter import InstitutionalFlowLoader, InstitutionalFlow
from ...utils.logger import get_logger
from ...utils.stock_name_mapper import get_stock_names
from config.settings import settings

logger = get_logger(__name__)

# P1 策略的賣出訊號名稱（只有這些才是真正的出場訊號）
P1_SELL_SIGNALS = {"RSI Momentum Loss", "MACD Death Cross", "Death Cross"}

# 流動性過濾門檻：1000 張 × 1000 股/張 = 1,000,000 股
MIN_VOLUME_SHARES = 1_000_000


def _display_symbol(symbol: str) -> str:
    """將內部 symbol 轉成顯示格式（4741O → 4741.TWO，2330 → 2330.TW）"""
    if symbol.endswith('O'):
        return symbol[:-1] + '.TWO'
    return symbol + '.TW'


def _lookup_name(symbol: str, names: dict) -> str:
    """依內部 symbol 查公司名稱"""
    return names.get(_display_symbol(symbol), "")


def _watch_reason(
    signal_name: str,
    indicators: TechnicalIndicators,
    strategy: TechnicalStrategy,
) -> str:
    """回傳 WATCH 訊號被降級的主要原因（用於顯示）"""
    if signal_name in strategy.disabled_signals:
        return "訊號停用"
    if strategy.require_ma60_uptrend:
        ma60 = indicators.ma60
        if ma60 is not None:
            # 需要從 signal 外層傳入 price；這裡用 ma5 作近似判斷
            pass  # price 從呼叫方傳入
    rsi = indicators.rsi14
    if rsi is not None and strategy.rsi_min_entry > 0:
        if rsi < Decimal(str(strategy.rsi_min_entry)):
            return f"RSI {float(rsi):.1f} < {strategy.rsi_min_entry}"
    ma5, ma10, ma20 = indicators.ma5, indicators.ma10, indicators.ma20
    if ma5 and ma10 and ma20:
        if not (ma5 > ma10 > ma20):
            return f"均線排列不佳 (MA5={float(ma5):.1f} MA10={float(ma10):.1f} MA20={float(ma20):.1f})"
    return "未達進場條件"


def _watch_reason_with_price(
    signal_name: str,
    price: Decimal,
    indicators: TechnicalIndicators,
    strategy: TechnicalStrategy,
) -> str:
    """完整判斷 WATCH 被降級的原因"""
    if signal_name in strategy.disabled_signals:
        return "訊號停用"
    if strategy.require_ma60_uptrend:
        ma60 = indicators.ma60
        if ma60 is not None and price < ma60:
            return f"低於MA60 (價格={float(price):.1f} MA60={float(ma60):.1f})"
    if strategy.require_volume_confirmation:
        pass  # volume 在此省略
    if signal_name not in strategy.TREND_SIGNAL_NAMES:
        ma5, ma10, ma20 = indicators.ma5, indicators.ma10, indicators.ma20
        if ma5 and ma10 and ma20:
            if not (ma5 > ma10 > ma20):
                return f"均線排列不佳 (MA5={float(ma5):.0f} MA10={float(ma10):.0f} MA20={float(ma20):.0f})"
    rsi = indicators.rsi14
    if rsi is not None and strategy.rsi_min_entry > 0:
        if rsi < Decimal(str(strategy.rsi_min_entry)):
            return f"RSI {float(rsi):.1f} < {strategy.rsi_min_entry:.0f}"
    return "未達進場條件"


def _calculate_price_range(
    signal_name: str,
    price: Decimal,
    indicators: TechnicalIndicators,
) -> Optional[dict]:
    """依訊號類型計算建議進場區間與停損位，回傳 dict 或 None（指標不足時）"""
    ma20 = indicators.ma20
    bb_upper = indicators.bb_upper
    bb_middle = indicators.bb_middle
    bb_lower = indicators.bb_lower
    try:
        if signal_name in ("Golden Cross", "MACD Golden Cross"):
            if ma20 is None:
                return None
            entry_low = float(min(ma20, price))
            entry_high = float(max(ma20, price))
            stop = float(ma20 * Decimal("0.97"))
        elif signal_name == "RSI Oversold":
            entry_low = float(price)
            entry_high = float(price * Decimal("1.02"))
            stop = float(bb_lower) if bb_lower else float(price * Decimal("0.95"))
        elif signal_name == "BB Squeeze Break":
            if bb_middle is None or bb_upper is None:
                return None
            entry_low = float(bb_middle)
            entry_high = float(bb_upper)
            stop = float(bb_middle * Decimal("0.97"))
        elif signal_name == "Donchian Breakout":
            entry_low = float(price)
            entry_high = float(price * Decimal("1.03"))
            stop = float(ma20 * Decimal("0.97")) if ma20 else float(price * Decimal("0.95"))
        else:
            entry_low = float(price * Decimal("0.99"))
            entry_high = float(price * Decimal("1.01"))
            stop = float(price * Decimal("0.95"))
        return {
            "entry_low": round(entry_low, 2),
            "entry_high": round(entry_high, 2),
            "stop_loss": round(stop, 2),
        }
    except Exception:
        return None


class SignalsScanner:
    """今日 P1 策略訊號掃描器"""

    def __init__(self, fubon_sdk=None):
        self.logger = get_logger(self.__class__.__name__)
        self.data_source = YFinanceDataSource()
        self._stock_names = get_stock_names()
        self.sector_analyzer = SectorTrendAnalyzer()
        self._fubon_sdk = fubon_sdk

        cfg = settings.backtest
        disabled = [s.strip() for s in cfg.disabled_signals.split(",") if s.strip()]
        self.strategy = TechnicalStrategy(
            disabled_signals=disabled,
            require_ma60_uptrend=cfg.require_ma60_uptrend,
            require_volume_confirmation=cfg.require_volume_confirmation,
            volume_confirmation_multiplier=cfg.volume_confirmation_multiplier,
            rsi_min_entry=cfg.rsi_min_entry,
            donchian_period=cfg.donchian_period,
            signal_cooldown_days=cfg.signal_cooldown_days,
        )
        self.cfg = cfg

    def _load_stock_data(self) -> Tuple[Dict[str, List[StockData]], date]:
        """載入本地 CSV 資料，回傳 stock_data_dict 與最新交易日"""
        stocks_dir = str(Path(settings.data.stocks_path).resolve())
        # 需要足夠的歷史資料讓指標暖機（MA60 + Donchian50 = 至少 120 天）
        load_start = date.today() - timedelta(days=365)
        stock_data = self.data_source.load_from_stocks_dir(
            stocks_dir=stocks_dir,
            start_date=load_start,
            end_date=date.today(),
        )
        if not stock_data:
            raise RuntimeError(f"找不到股票資料：{stocks_dir}，請先執行 python main.py download")

        # 找最新交易日
        latest = max(
            r.date
            for records in stock_data.values()
            for r in records
        )

        # 產業排除
        excluded = self.cfg.load_excluded_symbols(
            project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), '../..')))
        )
        stock_data = {s: d for s, d in stock_data.items() if s not in excluded}

        # 建立各股票在 target_date 的成交量（股），供流動性過濾使用
        volume_on_date: Dict[str, int] = {}
        for symbol, records in stock_data.items():
            for r in records:
                if r.date == latest:
                    volume_on_date[symbol] = r.volume
                    break

        return stock_data, latest, volume_on_date

    def _build_momentum_top_n(
        self,
        stock_data: Dict[str, List[StockData]],
        target_date: date,
    ) -> Optional[Set[str]]:
        """計算今日動能前 N 名（P1 設定：lookback=20d, top=30）"""
        top_n = self.cfg.momentum_top_n
        lookback = self.cfg.momentum_lookback_days
        if top_n <= 0:
            return None

        lookback_target = target_date - timedelta(days=lookback)
        scores: Dict[str, float] = {}

        for symbol, records in stock_data.items():
            price_by_date = {r.date: r.close_price for r in records}
            current = price_by_date.get(target_date)
            if current is None:
                continue
            past_dates = [d for d in price_by_date if d <= lookback_target]
            if not past_dates:
                continue
            past = price_by_date[max(past_dates)]
            if past == 0:
                continue
            scores[symbol] = float(current / past) - 1.0

        ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
        return set(ranked[:top_n])

    def scan_today(self) -> Dict:
        """
        掃描今日訊號，回傳：
        {
          'target_date': date,
          'buy':   [{'symbol', 'name', 'signal', 'price', 'rsi', 'in_top30'}, ...],
          'sell':  [{'symbol', 'name', 'signal', 'price', 'rsi'}, ...],
          'watch': [{'symbol', 'name', 'signal', 'price', 'rsi', 'reason'}, ...],
        }
        """
        self.logger.info("載入股票資料...")
        stock_data, target_date, volume_on_date = self._load_stock_data()
        self.logger.info(f"載入 {len(stock_data)} 支股票，最新交易日 {target_date}")

        # 載入月營收資料（若 min_monthly_revenue_million > 0 才啟用）
        revenue_map: Dict[str, dict] = {}
        min_revenue = self.cfg.min_monthly_revenue_million
        min_yoy = self.cfg.min_revenue_yoy_pct
        if min_revenue > 0:
            revenue_map = MonthlyRevenueLoader().load()
            self.logger.info(
                f"月營收過濾啟用：門檻 {min_revenue:.0f} 百萬元（{min_revenue/100:.1f}億），"
                f"已載入 {len(revenue_map)} 支"
                + (f"，年增率門檻 {min_yoy:.0f}%" if min_yoy > 0 else "")
            )

        # 處置股/注意股標記（不排除，僅於訊號備註中顯示）
        disposal_labeled: Dict[str, str] = {}
        if self.cfg.enable_disposal_filter:
            disposal_labeled = DisposalStockFilter(
                sdk=self._fubon_sdk,
                filter_attention=self.cfg.filter_attention_stocks,
            ).load_labeled()
            self.logger.info(
                f"處置股/注意股標記啟用：{len(disposal_labeled)} 支"
            )

        # 三大法人資料（若啟用）
        institutional_map: Dict[str, InstitutionalFlow] = {}
        if self.cfg.enable_institutional_filter:
            institutional_map = InstitutionalFlowLoader().load(target_date)
            self.logger.info(
                f"三大法人過濾啟用：已載入 {len(institutional_map)} 支"
                f"（外資門檻 {self.cfg.institutional_min_foreign_net_shares//1000}張，"
                f"投信門檻 {self.cfg.institutional_min_trust_net_shares//1000}張）"
            )

        # 建立動能前 30 名白名單
        top30 = self._build_momentum_top_n(stock_data, target_date)
        self.logger.info(f"動能前30名: {len(top30) if top30 else '停用'}")

        # 計算族群趨勢（若啟用）
        strong_sectors = None
        sector_summary = []
        if self.cfg.enable_sector_trend_filter:
            self.logger.info("計算族群趨勢強度...")
            sector_strength = self.sector_analyzer.compute_sector_strength(
                stock_data, target_date
            )
            strong_sectors = self.sector_analyzer.get_strong_sectors(
                sector_strength, threshold=self.cfg.sector_trend_threshold
            )
            sector_summary = self.sector_analyzer.build_sector_summary(
                sector_strength, threshold=self.cfg.sector_trend_threshold
            )
            strong_count = sum(1 for r in sector_summary if r["is_strong"])
            total_count = len(sector_summary)
            self.logger.info(
                f"族群分析完成：{strong_count}/{total_count} 個族群為強勢"
                f"（門檻 {self.cfg.sector_trend_threshold:.0%}）"
            )

        # 只針對最新交易日產生訊號（傳入全量歷史資料供指標計算，僅輸出 target_date 的訊號）
        self.logger.info("產生技術訊號...")
        all_signals = self.strategy.generate_signals_for_multiple_stocks(
            stock_data_dict=stock_data,
            start_date=target_date,
            end_date=target_date,
        )
        self.logger.info(f"共產生 {len(all_signals)} 個訊號")

        buy_list = []
        sell_list = []
        watch_list = []

        for sig in all_signals:
            if sig.date != target_date:
                continue

            # 流動性過濾：成交量低於 1000 張略過
            if volume_on_date.get(sig.symbol, 0) < MIN_VOLUME_SHARES:
                continue

            # OTC 內部 symbol 帶 'O' 後綴（4741O），API key 只有數字（4741）
            revenue_key = sig.symbol[:-1] if sig.symbol.endswith('O') else sig.symbol

            # 取得處置/注意標籤（空字串代表正常股票）
            disposal_note = disposal_labeled.get(revenue_key, "") if disposal_labeled else ""

            symbol_display = _display_symbol(sig.symbol)
            name = _lookup_name(sig.symbol, self._stock_names)
            rsi = float(sig.indicators.rsi14) if sig.indicators.rsi14 else None
            price = float(sig.price)

            entry = {
                "symbol": symbol_display,
                "name": name,
                "signal": sig.signal_name,
                "price": price,
                "rsi": rsi,
            }

            if sig.signal_type == SignalType.BUY:
                if disposal_note:
                    entry["note"] = disposal_note  # "處置股" 或 "注意股"

                in_top30 = top30 is None or sig.symbol in top30
                entry["in_top30"] = in_top30

                # 計算建議進場區間與停損
                price_range = _calculate_price_range(sig.signal_name, sig.price, sig.indicators)
                if price_range:
                    entry.update(price_range)

                # 族群趨勢過濾
                stock_sector = self.sector_analyzer.get_stock_sector(sig.symbol)
                entry["sector"] = stock_sector
                in_strong_sector = (
                    strong_sectors is None or stock_sector in strong_sectors
                )

                # 月營收過濾（含年增率）
                revenue_ok = True
                if min_revenue > 0 and revenue_map:
                    rev = get_revenue_million(revenue_map, revenue_key)
                    if rev is None or rev < min_revenue:
                        revenue_ok = False
                        entry["reason"] = (
                            f"月營收 {rev:.0f}M < {min_revenue:.0f}M"
                            if rev is not None
                            else "月營收資料不足"
                        )
                        if rev is not None:
                            entry["revenue_million"] = rev
                    elif min_yoy > 0:
                        yoy = get_revenue_yoy(revenue_map, revenue_key)
                        if yoy < min_yoy:
                            revenue_ok = False
                            entry["reason"] = f"年增率 {yoy:.1f}% < {min_yoy:.0f}%"
                            entry["revenue_yoy_pct"] = yoy
                        else:
                            entry["revenue_yoy_pct"] = yoy

                # 三大法人過濾（次要過濾，失敗降至 watch）
                inst_ok = True
                if self.cfg.enable_institutional_filter and institutional_map:
                    flow = institutional_map.get(revenue_key)
                    # 上櫃股票 T86 無資料 → fail-open，不過濾
                    if flow is not None:
                        foreign_ok = (
                            self.cfg.institutional_min_foreign_net_shares <= 0
                            or flow.foreign_net >= self.cfg.institutional_min_foreign_net_shares
                        )
                        trust_ok = (
                            self.cfg.institutional_min_trust_net_shares <= 0
                            or flow.trust_net >= self.cfg.institutional_min_trust_net_shares
                        )
                        inst_ok = foreign_ok or trust_ok if self.cfg.institutional_require_any else foreign_ok and trust_ok
                        if not inst_ok:
                            entry["reason"] = (
                                f"法人籌碼不足（外資 {flow.foreign_net//1000:+.0f}張"
                                f" 投信 {flow.trust_net//1000:+.0f}張）"
                            )
                        entry["institutional"] = {
                            "foreign_lots": flow.foreign_net // 1000,
                            "trust_lots": flow.trust_net // 1000,
                            "total_lots": flow.total_net // 1000,
                        }
                    else:
                        # 有啟用但無資料（如上櫃股票）→ 顯示法人數據欄位留空
                        entry["institutional"] = None

                if not in_top30:
                    entry["reason"] = "動能排名不在前30"
                    watch_list.append(entry)
                elif not in_strong_sector:
                    entry["reason"] = f"族群偏弱（{stock_sector}）"
                    watch_list.append(entry)
                elif not revenue_ok:
                    watch_list.append(entry)
                elif not inst_ok:
                    watch_list.append(entry)
                else:
                    # 通過所有過濾：加入月營收 YoY 顯示（若有）
                    if min_revenue > 0 and revenue_map:
                        yoy = get_revenue_yoy(revenue_map, revenue_key)
                        if yoy != 0.0:
                            entry["revenue_yoy_pct"] = yoy
                    buy_list.append(entry)

            elif sig.signal_type == SignalType.SELL:
                # 只保留 P1 策略定義的出場訊號，過濾掉 RSI Overbought 等雜訊
                # 注意：賣出不套用月營收/法人過濾——持倉出場訊號必須顯示
                if sig.signal_name in P1_SELL_SIGNALS:
                    if disposal_note:
                        entry["disposal"] = True
                        entry["note"] = disposal_note
                    sell_list.append(entry)

            elif sig.signal_type == SignalType.WATCH:
                if disposal_note:
                    entry["note"] = disposal_note
                entry["sector"] = self.sector_analyzer.get_stock_sector(sig.symbol)
                entry["reason"] = _watch_reason_with_price(
                    sig.signal_name, sig.price, sig.indicators, self.strategy
                )
                watch_list.append(entry)

        # 買入：每支股票合併多個訊號為一筆，訊號名稱用「+」連接
        buy_by_symbol: Dict[str, dict] = {}
        for entry in buy_list:
            sym = entry["symbol"]
            if sym not in buy_by_symbol:
                buy_by_symbol[sym] = dict(entry, signals=[entry["signal"]])
            else:
                existing = buy_by_symbol[sym]
                existing["signals"].append(entry["signal"])
                # 合併進場區間：取更寬的範圍，停損取較高（更保守）
                if "entry_low" in entry and "entry_low" in existing:
                    existing["entry_low"] = min(existing["entry_low"], entry["entry_low"])
                    existing["entry_high"] = max(existing["entry_high"], entry["entry_high"])
                    existing["stop_loss"] = max(existing["stop_loss"], entry["stop_loss"])
        for entry in buy_by_symbol.values():
            entry["signal"] = " + ".join(sorted(set(entry["signals"])))
            del entry["signals"]
        buy_list = list(buy_by_symbol.values())

        # 賣出：每支股票只保留最嚴重的訊號（MACD Death Cross > Death Cross > RSI Momentum Loss）
        SELL_PRIORITY = {"MACD Death Cross": 0, "Death Cross": 1, "RSI Momentum Loss": 2}
        sell_by_symbol: Dict[str, dict] = {}
        for entry in sell_list:
            sym = entry["symbol"]
            if sym not in sell_by_symbol:
                sell_by_symbol[sym] = entry
            else:
                existing_priority = SELL_PRIORITY.get(sell_by_symbol[sym]["signal"], 99)
                new_priority = SELL_PRIORITY.get(entry["signal"], 99)
                if new_priority < existing_priority:
                    sell_by_symbol[sym] = entry
        sell_list = list(sell_by_symbol.values())

        # 排序：買入 by RSI 降序（動能最強優先），賣出 by RSI 升序（最緊急優先）
        buy_list.sort(key=lambda x: -(x["rsi"] or 0))
        sell_list.sort(key=lambda x: x["rsi"] or 99)
        watch_list.sort(key=lambda x: x["signal"])

        return {
            "target_date": target_date,
            "total_scanned": len(stock_data),
            "buy": buy_list,
            "sell": sell_list,
            "watch": watch_list,
            "sector_summary": sector_summary,
        }
