"""
Unit tests for bias rate (乖離率) feature
"""
import sys
import os
from datetime import date
from decimal import Decimal

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest.models import StockData, TechnicalIndicators, SignalType
from src.backtest.strategy import TechnicalStrategy


def _make_indicators(
    ma5=None, ma10=None, ma20=None, ma60=None,
    rsi14=50.0, macd=None, macd_signal=None, macd_histogram=None,
    bb_upper=None, bb_middle=None, bb_lower=None, volume_ma20=None,
) -> TechnicalIndicators:
    return TechnicalIndicators(
        date=date(2026, 4, 14),
        ma5=Decimal(str(ma5)) if ma5 else None,
        ma10=Decimal(str(ma10)) if ma10 else None,
        ma20=Decimal(str(ma20)) if ma20 else None,
        ma60=Decimal(str(ma60)) if ma60 else None,
        rsi14=Decimal(str(rsi14)) if rsi14 else None,
        macd=Decimal(str(macd)) if macd else None,
        macd_signal=Decimal(str(macd_signal)) if macd_signal else None,
        macd_histogram=Decimal(str(macd_histogram)) if macd_histogram else None,
        bb_upper=Decimal(str(bb_upper)) if bb_upper else None,
        bb_middle=Decimal(str(bb_middle)) if bb_middle else None,
        bb_lower=Decimal(str(bb_lower)) if bb_lower else None,
        volume_ma20=Decimal(str(volume_ma20)) if volume_ma20 else None,
    )


class TestBiasRateBuyFilter:
    """個股乖離率買入過濾 (Filter 8)"""

    def _make_strategy(self, buy_max=10.0, bias_period=20) -> TechnicalStrategy:
        return TechnicalStrategy(
            stock_bias_buy_max_pct=buy_max,
            bias_ma_period=bias_period,
            # Disable other filters to isolate bias filter
            require_ma60_uptrend=False,
            require_volume_confirmation=False,
            rsi_min_entry=0.0,
            min_volume_lots=0,
        )

    def test_buy_passes_when_bias_within_limit(self):
        """乖離率未超過門檻時，BUY 訊號應通過"""
        strategy = self._make_strategy(buy_max=10.0)
        # MA20=100, price=108 → bias=8% < 10%
        indicators = _make_indicators(ma5=105, ma10=103, ma20=100, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="Golden Cross",
            price=Decimal('108'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.BUY

    def test_buy_blocked_when_bias_exceeds_limit(self):
        """乖離率超過門檻時，非趨勢 BUY 訊號應降為 WATCH"""
        strategy = self._make_strategy(buy_max=10.0)
        # MA20=100, price=115 → bias=15% > 10%；BB Squeeze Break 非趨勢訊號，應被阻擋
        indicators = _make_indicators(ma5=112, ma10=108, ma20=100, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="BB Squeeze Break",
            price=Decimal('115'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.WATCH

    def test_buy_trend_signal_exempt_from_bias_filter(self):
        """趨勢訊號（Donchian Breakout / Golden Cross / MACD Golden Cross）應豁免乖離率過濾"""
        strategy = self._make_strategy(buy_max=10.0)
        # MA20=100, price=130 → bias=30% > 10%；但趨勢訊號突破本身代表新高，不應被阻擋
        indicators = _make_indicators(ma5=125, ma10=118, ma20=100, ma60=90)
        for trend_signal in ("Donchian Breakout", "Golden Cross", "MACD Golden Cross"):
            result = strategy._apply_buy_filters(
                signal_name=trend_signal,
                price=Decimal('130'),
                volume=2_000_000,
                indicators=indicators,
            )
            assert result == SignalType.BUY, f"{trend_signal} 應豁免乖離率過濾但被降為 WATCH"

    def test_buy_at_exact_limit_passes(self):
        """乖離率剛好等於門檻時應通過（> 才阻擋）"""
        strategy = self._make_strategy(buy_max=10.0)
        # MA20=100, price=110 → bias=10.0% (not > 10)
        indicators = _make_indicators(ma5=107, ma10=105, ma20=100, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="Golden Cross",
            price=Decimal('110'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.BUY

    def test_bias_filter_disabled_when_zero(self):
        """buy_max=0 時停用乖離率過濾，即使乖離率很高也應通過"""
        strategy = self._make_strategy(buy_max=0.0)
        # MA20=100, price=150 → bias=50%, but filter disabled
        indicators = _make_indicators(ma5=145, ma10=140, ma20=100, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="Golden Cross",
            price=Decimal('150'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.BUY

    def test_bias_filter_skipped_when_ma_unavailable(self):
        """MA 資料不足時應略過偏差率過濾，不阻擋訊號"""
        strategy = self._make_strategy(buy_max=10.0, bias_period=20)
        # ma20 = None
        indicators = _make_indicators(ma5=115, ma10=112, ma20=None, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="Golden Cross",
            price=Decimal('120'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.BUY

    def test_bias_filter_uses_ma5_when_period_is_5(self):
        """bias_ma_period=5 時應使用 MA5 計算乖離率"""
        strategy = self._make_strategy(buy_max=10.0, bias_period=5)
        # MA5=100, price=115 → bias=15% > 10%
        indicators = _make_indicators(ma5=100, ma10=102, ma20=104, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="BB Squeeze Break",
            price=Decimal('115'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.WATCH

    def test_bias_filter_negative_bias_passes(self):
        """負乖離（price < MA）時應通過（只過濾過熱，不過濾超賣）。
        使用 Donchian Breakout（趨勢訊號）略過 MA 排列 Filter 4，
        以專注驗證乖離率過濾本身的行為。
        """
        strategy = self._make_strategy(buy_max=10.0)
        # MA20=100, price=90 → bias=-10%, not > 10%；bias filter should pass
        indicators = _make_indicators(ma5=92, ma10=93, ma20=100, ma60=90)
        result = strategy._apply_buy_filters(
            signal_name="Donchian Breakout",   # trend signal → skips MA alignment filter
            price=Decimal('90'),
            volume=2_000_000,
            indicators=indicators,
        )
        assert result == SignalType.BUY


class TestBiasRateSellSignal:
    """個股乖離率賣出訊號生成"""

    def _make_price_data(self, close: float, ma20: float, date_val=date(2026, 4, 14)) -> list:
        """建立足夠的歷史資料讓 generate_signals 能運作。"""
        records = []
        # 建立 70 天假資料（需足夠讓 MA/RSI 計算）
        for i in range(70):
            d = date(2026, 4, 14) - __import__('datetime').timedelta(days=70 - i)
            # 前 69 天收盤價等於 ma20（基準線）
            records.append(StockData(
                symbol="TEST",
                date=d,
                open_price=Decimal(str(ma20)),
                high_price=Decimal(str(ma20 * 1.01)),
                low_price=Decimal(str(ma20 * 0.99)),
                close_price=Decimal(str(ma20)),
                volume=2_000_000,
            ))
        # 最後一天（target day）設定為目標收盤價
        records.append(StockData(
            symbol="TEST",
            date=date_val,
            open_price=Decimal(str(close)),
            high_price=Decimal(str(close * 1.01)),
            low_price=Decimal(str(close * 0.99)),
            close_price=Decimal(str(close)),
            volume=2_000_000,
        ))
        return records

    def test_sell_signal_generated_when_bias_exceeds_threshold(self):
        """乖離率超過賣出門檻時應生成『高乖離率』賣出訊號"""
        strategy = TechnicalStrategy(
            stock_bias_sell_pct=20.0,
            bias_ma_period=20,
            require_ma60_uptrend=False,
            require_volume_confirmation=False,
            rsi_min_entry=0.0,
            min_volume_lots=0,
        )
        # MA20 ≈ 100（前 69 天都是 100），最後一天漲到 125 → bias ≈ 25% > 20%
        price_data = self._make_price_data(close=125.0, ma20=100.0)
        signals = strategy.generate_signals(
            "TEST", price_data,
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 14),
        )
        sell_signals = [s for s in signals if s.signal_type == SignalType.SELL and s.signal_name == "高乖離率"]
        assert len(sell_signals) == 1
        assert "高乖離率" in sell_signals[0].signal_name

    def test_sell_signal_not_generated_when_bias_below_threshold(self):
        """乖離率未超過門檻時，不應生成『高乖離率』賣出訊號"""
        strategy = TechnicalStrategy(
            stock_bias_sell_pct=20.0,
            bias_ma_period=20,
            require_ma60_uptrend=False,
            require_volume_confirmation=False,
            rsi_min_entry=0.0,
            min_volume_lots=0,
        )
        # bias ≈ 10% < 20%
        price_data = self._make_price_data(close=110.0, ma20=100.0)
        signals = strategy.generate_signals(
            "TEST", price_data,
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 14),
        )
        sell_signals = [s for s in signals if s.signal_name == "高乖離率"]
        assert len(sell_signals) == 0

    def test_sell_signal_disabled_when_zero(self):
        """stock_bias_sell_pct=0 時不應生成任何高乖離率訊號"""
        strategy = TechnicalStrategy(
            stock_bias_sell_pct=0.0,
            bias_ma_period=20,
            require_ma60_uptrend=False,
            require_volume_confirmation=False,
            rsi_min_entry=0.0,
            min_volume_lots=0,
        )
        price_data = self._make_price_data(close=150.0, ma20=100.0)
        signals = strategy.generate_signals(
            "TEST", price_data,
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 14),
        )
        sell_signals = [s for s in signals if s.signal_name == "高乖離率"]
        assert len(sell_signals) == 0


class TestBiasRateInP1SellSignals:
    """高乖離率應在 P1_SELL_SIGNALS 集合中"""

    def test_high_bias_in_p1_sell_signals(self):
        from src.scanner.signals_scanner import P1_SELL_SIGNALS
        assert "高乖離率" in P1_SELL_SIGNALS


class TestBiasRateSettings:
    """乖離率設定值正確性驗證"""

    def test_default_settings_exist(self):
        from config.settings import settings
        cfg = settings.backtest
        assert hasattr(cfg, 'bias_ma_period')
        assert hasattr(cfg, 'stock_bias_buy_max_pct')
        assert hasattr(cfg, 'stock_bias_sell_pct')
        assert hasattr(cfg, 'market_bias_buy_max_pct')
        assert hasattr(cfg, 'market_bias_sell_pct')

    def test_default_bias_ma_period(self):
        from config.settings import settings
        assert settings.backtest.bias_ma_period == 20

    def test_default_stock_bias_buy_max_pct(self):
        from config.settings import settings
        assert settings.backtest.stock_bias_buy_max_pct == 10.0

    def test_default_stock_bias_sell_pct(self):
        from config.settings import settings
        assert settings.backtest.stock_bias_sell_pct == 20.0

    def test_default_market_bias_buy_max_pct(self):
        from config.settings import settings
        assert settings.backtest.market_bias_buy_max_pct == 8.0

    def test_default_market_bias_sell_pct(self):
        from config.settings import settings
        assert settings.backtest.market_bias_sell_pct == 12.0
