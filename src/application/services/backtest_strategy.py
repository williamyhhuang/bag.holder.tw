"""
Trading strategy implementation for backtesting
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Set, Tuple

from ...domain.models import StockData, TradingSignal, TechnicalIndicators, SignalType
from ...domain.services.indicator_calculator import IndicatorCalculator
from ...domain.services.signal_detector import SignalDetector
from ...utils.logger import get_logger

logger = get_logger(__name__)


def _find_swing_points(prices: List[float], kind: str = "high", half_window: int = 5) -> List[Tuple[int, float]]:
    """Find swing highs or lows in a price series.

    Args:
        prices: Sequence of close (or high/low) prices.
        kind: 'high' for swing highs, 'low' for swing lows.
        half_window: Number of bars on each side to confirm a swing point.

    Returns:
        List of (index, price) tuples for confirmed swing points.
    """
    points: List[Tuple[int, float]] = []
    n = len(prices)
    for i in range(half_window, n - half_window):
        window = prices[i - half_window: i + half_window + 1]
        if kind == "high":
            if prices[i] == max(window):
                points.append((i, prices[i]))
        else:
            if prices[i] == min(window):
                points.append((i, prices[i]))
    return points


def _detect_vcp(
    closes: List[float],
    volumes: List[int],
    half_window: int = 5,
    min_contractions: int = 2,
    vol_short: int = 10,
    vol_long: int = 30,
) -> bool:
    """Detect a Volatility Contraction Pattern (VCP).

    Criteria:
    1. At least min_contractions successive drawdowns, each smaller than the prior.
    2. Volume contracting: recent vol_short-day average < vol_long-day average.

    Args:
        closes: Recent close prices (oldest first).
        volumes: Corresponding volume data.
        half_window: Side bars required to confirm swing highs/lows.
        min_contractions: Minimum number of contracting drawdown cycles required.
        vol_short: Short MA window for volume contraction check.
        vol_long: Long MA window for volume contraction check.

    Returns:
        True if a VCP pattern is detected.
    """
    if len(closes) < vol_long + half_window * 2:
        return False

    # Find swing highs and lows
    swing_highs = _find_swing_points(closes, kind="high", half_window=half_window)
    swing_lows = _find_swing_points(closes, kind="low", half_window=half_window)

    if len(swing_highs) < min_contractions or len(swing_lows) < min_contractions:
        return False

    # Calculate drawdowns: from each swing high to the next swing low
    drawdowns: List[float] = []
    for hi_idx, hi_val in swing_highs:
        subsequent_lows = [(lo_idx, lo_val) for lo_idx, lo_val in swing_lows if lo_idx > hi_idx]
        if not subsequent_lows:
            continue
        lo_idx, lo_val = subsequent_lows[0]
        if hi_val <= 0:
            continue
        drawdown = (hi_val - lo_val) / hi_val
        drawdowns.append(drawdown)

    if len(drawdowns) < min_contractions:
        return False

    # Check that consecutive drawdowns are contracting
    is_contracting = all(drawdowns[i] < drawdowns[i - 1] for i in range(1, len(drawdowns)))
    if not is_contracting:
        return False

    # Volume contraction: short-term average below long-term average
    if len(volumes) >= vol_long:
        vol_ma_short = sum(volumes[-vol_short:]) / vol_short
        vol_ma_long = sum(volumes[-vol_long:]) / vol_long
        vol_contracting = vol_ma_short < vol_ma_long
    else:
        vol_contracting = True  # Not enough data, skip volume check

    return vol_contracting


def _build_weekly_closes(price_data: List[StockData]) -> List[Tuple[date, Decimal]]:
    """
    Aggregate daily OHLCV to weekly frequency (ISO week, last trading day = week end).
    Returns list of (week_last_date, close_price) sorted chronologically.
    """
    weekly: Dict[Tuple[int, int], Tuple[date, Decimal]] = {}
    for data in sorted(price_data, key=lambda x: x.date):
        iso = data.date.isocalendar()
        key = (iso[0], iso[1])
        weekly[key] = (data.date, data.close_price)
    return sorted(weekly.values(), key=lambda x: x[0])


def _build_weekly_ohlcv(
    price_data: List[StockData],
) -> List[Tuple[date, Decimal, Decimal, Decimal, Decimal]]:
    """
    Aggregate daily OHLCV to weekly (ISO week).
    Returns list of (week_last_date, open, high, low, close) sorted chronologically.
    Open = first day's open, High = week high, Low = week low, Close = last day's close.
    """
    weekly: Dict[Tuple[int, int], list] = {}
    for data in sorted(price_data, key=lambda x: x.date):
        iso = data.date.isocalendar()
        key = (iso[0], iso[1])
        if key not in weekly:
            weekly[key] = [data.date, data.open_price, data.high_price, data.low_price, data.close_price]
        else:
            # update: last date, expand high/low, update close
            weekly[key][0] = data.date
            if data.high_price > weekly[key][2]:
                weekly[key][2] = data.high_price
            if data.low_price < weekly[key][3]:
                weekly[key][3] = data.low_price
            weekly[key][4] = data.close_price
    return sorted(
        [(row[0], row[1], row[2], row[3], row[4]) for row in weekly.values()],
        key=lambda x: x[0],
    )


def _compute_weekly_bollinger(
    weekly_ohlcv: List[Tuple[date, Decimal, Decimal, Decimal, Decimal]],
    period: int = 20,
    std_dev: float = 2.0,
) -> Dict[date, Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]]:
    """
    Compute Bollinger Bands on weekly closes.
    Returns {week_last_date: (bb_upper, bb_middle, bb_lower)}.
    """
    result: Dict[date, Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]] = {}
    closes = [row[4] for row in weekly_ohlcv]
    dates = [row[0] for row in weekly_ohlcv]
    for i in range(period - 1, len(closes)):
        window = [float(c) for c in closes[i - period + 1: i + 1]]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        mult = std_dev * std
        result[dates[i]] = (
            Decimal(str(round(mean + mult, 4))),
            Decimal(str(round(mean, 4))),
            Decimal(str(round(mean - mult, 4))),
        )
    return result


def _compute_weekly_donchian_high(
    weekly_ohlcv: List[Tuple[date, Decimal, Decimal, Decimal, Decimal]],
    period: int = 10,
) -> Dict[date, Optional[Decimal]]:
    """
    Compute rolling N-week high (using weekly high) for Donchian channel.
    Returns {week_last_date: N-week high of prior N weeks (excludes current week)}.
    """
    result: Dict[date, Optional[Decimal]] = {}
    highs = [row[2] for row in weekly_ohlcv]
    dates = [row[0] for row in weekly_ohlcv]
    for i in range(period, len(highs)):
        # Use prior `period` weeks (not including current) to avoid look-ahead
        prior_highs = highs[i - period: i]
        result[dates[i]] = max(prior_highs)
    return result


def _calculate_weekly_rsi(weekly_closes: List[Tuple[date, Decimal]], period: int = 14) -> Dict[Tuple[int, int], Decimal]:
    """Calculate RSI for weekly closes using Wilder's smoothing (same as talib).

    Returns:
        {(iso_year, iso_week): rsi_value}
    """
    result: Dict[Tuple[int, int], Decimal] = {}
    if len(weekly_closes) < period + 1:
        return result

    closes = [float(c) for _, c in weekly_closes]
    dates = [d for d, _ in weekly_closes]

    # Price changes (deltas[i] = closes[i+1] - closes[i])
    deltas = [closes[i + 1] - closes[i] for i in range(len(closes) - 1)]

    # Seed: simple average of first `period` deltas
    avg_gain = sum(max(d, 0.0) for d in deltas[:period]) / period
    avg_loss = sum(abs(min(d, 0.0)) for d in deltas[:period]) / period

    def _rsi(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    # First RSI corresponds to closes[period] → dates[period]
    iso = dates[period].isocalendar()
    result[(iso[0], iso[1])] = Decimal(str(round(_rsi(avg_gain, avg_loss), 2)))

    # Wilder's smoothing for subsequent weeks
    for i in range(period, len(deltas)):
        delta = deltas[i]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + abs(min(delta, 0.0))) / period
        iso = dates[i + 1].isocalendar()
        result[(iso[0], iso[1])] = Decimal(str(round(_rsi(avg_gain, avg_loss), 2)))

    return result


def _calculate_weekly_ma(weekly_closes: List[Tuple[date, Decimal]], period: int) -> Dict[Tuple[int, int], Decimal]:
    """
    Calculate simple MA for weekly closes.
    Returns {(iso_year, iso_week): ma_value}.
    """
    result: Dict[Tuple[int, int], Decimal] = {}
    if period <= 0 or len(weekly_closes) < period:
        return result

    closes = [c for _, c in weekly_closes]
    dates = [d for d, _ in weekly_closes]

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1: i + 1]
        avg = sum(window) / Decimal(period)
        iso = dates[i].isocalendar()
        result[(iso[0], iso[1])] = avg

    return result


class TechnicalStrategy:
    """Technical analysis strategy using existing indicator logic"""

    # P1 (2026-04-08): Restored Golden Cross + MACD Golden Cross.
    # Filter diagnosis showed disabling them degraded return by -5.90%.
    # Despite low win rates (22-32%), their position timing had positive portfolio effect.
    DEFAULT_DISABLED_SIGNALS: list = []

    # Signals that use trend-following logic (skip MA alignment filter)
    TREND_SIGNAL_NAMES: List[str] = [
        "Donchian Breakout",
        "Golden Cross",
        "MACD Golden Cross",
        "Volume Surge",
        "BB Squeeze Break",
        "Weekly BB Squeeze Break",
        "Weekly Donchian Breakout",
        "Donchian Breakout 2",
    ]

    # Mean-reversion signals that should skip the RSI min entry filter
    # (they fire when RSI is LOW by definition, so requiring RSI >= 50 paradoxically blocks all of them)
    MEAN_REVERSION_SIGNALS: List[str] = [
        "RSI Oversold",
        "BB Lower Touch",
        "Volume Climax",
        "RSI Bullish Divergence",
        "Support Bounce",
    ]

    def __init__(
        self,
        ma_periods: List[int] = [5, 10, 20, 60, 120],
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
        disabled_signals: Optional[List[str]] = None,
        require_ma60_uptrend: bool = True,
        require_volume_confirmation: bool = True,
        volume_confirmation_multiplier: float = 1.5,
        rsi_overbought_threshold: float = 70.0,
        rsi_min_entry: float = 50.0,
        donchian_period: int = 20,
        min_volume_lots: int = 0,
        signal_cooldown_days: int = 0,
        require_weekly_trend: bool = False,
        require_52w_filter: bool = False,
        above_52w_low_pct: float = 0.30,
        near_52w_high_pct: float = 0.25,
        enable_vcp: bool = False,
        vcp_lookback: int = 60,
        pre_breakout_mode: bool = True,
        enable_momentum_signal: bool = False,
        momentum_signal_days: int = 5,
        momentum_signal_min_return: float = 0.03,
        require_weekly_rsi: bool = False,
        weekly_rsi_min: float = 50.0,
        require_revenue_growth: bool = False,
        revenue_yoy_min_pct: float = 0.0,
        finmind_api_token: str = "",
        weekly_close_only: bool = False,
        require_minervini_trend: bool = False,
        min_confirming_signals: int = 1,
        enable_weekly_signals: bool = False,
        weekly_bb_period: int = 20,
        weekly_donchian_period: int = 10,
        donchian_period_2: int = 0,
        rsi_oversold_require_uptrend: bool = True,
        enable_left_side_signals: bool = False,
        left_side_min_price: float = 20.0,
        left_side_max_drawdown_10d_pct: float = 0.20,
        left_side_min_confirming_signals: int = 1,
        left_side_disabled_signals: Optional[List[str]] = None,
    ):
        self.ma_periods = ma_periods
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev

        # Buy-signal quality filters (evidence-based from backtests)
        self.disabled_signals: List[str] = (
            disabled_signals if disabled_signals is not None
            else self.DEFAULT_DISABLED_SIGNALS
        )
        self.require_ma60_uptrend = require_ma60_uptrend
        self.require_volume_confirmation = require_volume_confirmation
        self.volume_confirmation_multiplier = Decimal(str(volume_confirmation_multiplier))
        self.rsi_overbought_threshold = Decimal(str(rsi_overbought_threshold))
        self.rsi_min_entry = Decimal(str(rsi_min_entry))
        self.donchian_period = donchian_period
        # Filter 6: minimum daily volume in lots (1 lot = 1,000 shares); 0 = disabled
        self.min_volume_lots = min_volume_lots
        # Filter 7: cooldown — skip BUY if same symbol triggered BUY within N trading days; 0 = disabled
        self.signal_cooldown_days = signal_cooldown_days
        # Filter 8: weekly trend confirmation — weekly MA5 > MA20 required for BUY
        self.require_weekly_trend = require_weekly_trend
        # Filter 9: 52-week high/low Minervini filter
        self.require_52w_filter = require_52w_filter
        self.above_52w_low_pct = Decimal(str(above_52w_low_pct))
        self.near_52w_high_pct = Decimal(str(near_52w_high_pct))
        # VCP signal
        self.enable_vcp = enable_vcp
        self.vcp_lookback = vcp_lookback
        # Breakout mode
        self.pre_breakout_mode = pre_breakout_mode
        # Multi-day momentum signal
        self.enable_momentum_signal = enable_momentum_signal
        self.momentum_signal_days = momentum_signal_days
        self.momentum_signal_min_return = Decimal(str(momentum_signal_min_return))
        self.require_weekly_rsi = require_weekly_rsi
        self.weekly_rsi_min = Decimal(str(weekly_rsi_min))
        self.require_revenue_growth = require_revenue_growth
        self.revenue_yoy_min_pct = revenue_yoy_min_pct
        self.finmind_api_token = finmind_api_token
        self.weekly_close_only = weekly_close_only
        self.require_minervini_trend = require_minervini_trend
        # Filter 15: multi-signal confirmation — BUY only when >= N signals agree on the same day
        self.min_confirming_signals = min_confirming_signals
        # Weekly signals: BB Squeeze Break and Donchian on weekly timeframe
        self.enable_weekly_signals = enable_weekly_signals
        self.weekly_bb_period = weekly_bb_period
        self.weekly_donchian_period = weekly_donchian_period
        self.donchian_period_2 = donchian_period_2
        # B1 (win-rate): mean-reversion signals (RSI Oversold) are exempt from the RSI min-entry
        # filter by design, which risks "catching a falling knife" in a downtrend. When enabled,
        # require RSI Oversold to additionally sit in an uptrend context (price > MA60 AND
        # weekly MA5 > MA20) regardless of the global require_ma60_uptrend / require_weekly_trend
        # toggles — only buy oversold dips inside an established uptrend.
        self.rsi_oversold_require_uptrend = rsi_oversold_require_uptrend
        # Left-side (mean-reversion) strategy parameters
        self.enable_left_side_signals = enable_left_side_signals
        self.left_side_min_price = Decimal(str(left_side_min_price))
        self.left_side_max_drawdown_10d_pct = Decimal(str(left_side_max_drawdown_10d_pct))
        self.left_side_min_confirming_signals = left_side_min_confirming_signals
        self.left_side_disabled_signals: List[str] = (
            left_side_disabled_signals if left_side_disabled_signals is not None else []
        )

        self.indicator_calculator = IndicatorCalculator()
        self.signal_detector = SignalDetector()
        self.logger = get_logger(self.__class__.__name__)

        # Strategy state
        self.indicators_cache: Dict[str, Dict[date, TechnicalIndicators]] = {}
        # Weekly MA cache: symbol -> {(iso_year, iso_week): (ma5, ma20)}
        self.weekly_ma_cache: Dict[str, Dict[Tuple[int, int], Tuple[Optional[Decimal], Optional[Decimal]]]] = {}
        # Weekly RSI cache: symbol -> {(iso_year, iso_week): rsi}
        self.weekly_rsi_cache: Dict[str, Dict[Tuple[int, int], Decimal]] = {}
        # Weekly signal caches: symbol -> {date: ...}
        self.weekly_bb_cache: Dict[str, Dict[date, Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]]] = {}
        self.weekly_donchian_cache: Dict[str, Dict[date, Optional[Decimal]]] = {}
        # Revenue cache: symbol -> {date_str -> {revenue, yoy_pct}}
        self.revenue_cache: Dict[str, Dict[str, dict]] = {}

    def prepare_price_data(self, stock_data: List[StockData]) -> List:
        """Convert StockData to format compatible with IndicatorCalculator"""
        # Create mock StockPrice objects for indicator calculation
        from ...database.models import StockPrice

        price_objects = []
        for data in stock_data:
            # Create a mock object with required attributes
            class MockStockPrice:
                def __init__(self, stock_data: StockData):
                    self.date = stock_data.date
                    self.open_price = stock_data.open_price
                    self.high_price = stock_data.high_price
                    self.low_price = stock_data.low_price
                    self.close_price = stock_data.close_price
                    self.volume = stock_data.volume

            price_objects.append(MockStockPrice(data))

        return price_objects

    def calculate_indicators(self, symbol: str, price_data: List[StockData]) -> Dict[date, TechnicalIndicators]:
        """
        Calculate technical indicators for a stock

        Args:
            symbol: Stock symbol
            price_data: List of stock price data

        Returns:
            Dictionary mapping dates to TechnicalIndicators
        """
        if symbol in self.indicators_cache:
            return self.indicators_cache[symbol]

        try:
            # Prepare data for indicator calculation
            prepared_data = self.prepare_price_data(price_data)

            if len(prepared_data) < max(self.ma_periods + [self.rsi_period, self.macd_slow, self.bb_period]):
                self.logger.warning(f"Insufficient data for {symbol}: {len(prepared_data)} records")
                return {}

            # Calculate indicators using existing logic
            indicators_data = self.indicator_calculator.calculate_all_indicators(
                price_data=prepared_data,
                ma_periods=self.ma_periods,
                rsi_period=self.rsi_period,
                macd_fast=self.macd_fast,
                macd_slow=self.macd_slow,
                macd_signal=self.macd_signal,
                bb_period=self.bb_period,
                bb_std_dev=self.bb_std_dev
            )

            # Convert to TechnicalIndicators objects
            result = {}
            for trade_date, indicators in indicators_data.items():
                result[trade_date] = TechnicalIndicators(
                    date=trade_date,
                    ma5=indicators.get('ma5'),
                    ma10=indicators.get('ma10'),
                    ma20=indicators.get('ma20'),
                    ma60=indicators.get('ma60'),
                    ma120=indicators.get('ma120'),
                    rsi14=indicators.get('rsi14'),
                    macd=indicators.get('macd'),
                    macd_signal=indicators.get('macd_signal'),
                    macd_histogram=indicators.get('macd_histogram'),
                    bb_upper=indicators.get('bb_upper'),
                    bb_middle=indicators.get('bb_middle'),
                    bb_lower=indicators.get('bb_lower'),
                    volume_ma20=indicators.get('volume_ma20'),
                    atr14=indicators.get('atr14'),
                )

            self.indicators_cache[symbol] = result
            self.logger.info(f"Calculated indicators for {symbol}: {len(result)} dates")
            return result

        except Exception as e:
            self.logger.error(f"Error calculating indicators for {symbol}: {e}")
            return {}

    def convert_indicators_to_dict(self, indicators: TechnicalIndicators) -> Dict[str, Decimal]:
        """Convert TechnicalIndicators object to dictionary format for SignalDetector"""
        result = {}

        if indicators.ma5 is not None:
            result['ma5'] = indicators.ma5
        if indicators.ma10 is not None:
            result['ma10'] = indicators.ma10
        if indicators.ma20 is not None:
            result['ma20'] = indicators.ma20
        if indicators.ma60 is not None:
            result['ma60'] = indicators.ma60
        if indicators.rsi14 is not None:
            result['rsi14'] = indicators.rsi14
        if indicators.macd is not None:
            result['macd'] = indicators.macd
        if indicators.macd_signal is not None:
            result['macd_signal'] = indicators.macd_signal
        if indicators.macd_histogram is not None:
            result['macd_histogram'] = indicators.macd_histogram
        if indicators.bb_upper is not None:
            result['bb_upper'] = indicators.bb_upper
        if indicators.bb_middle is not None:
            result['bb_middle'] = indicators.bb_middle
        if indicators.bb_lower is not None:
            result['bb_lower'] = indicators.bb_lower
        if indicators.volume_ma20 is not None:
            result['volume_ma20'] = indicators.volume_ma20

        return result

    def generate_signals(
        self,
        symbol: str,
        price_data: List[StockData],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TradingSignal]:
        """
        Generate trading signals for a stock

        Args:
            symbol: Stock symbol
            price_data: List of stock price data
            start_date: Start date for signal generation
            end_date: End date for signal generation

        Returns:
            List of trading signals
        """
        signals = []

        try:
            # Calculate indicators
            indicators_data = self.calculate_indicators(symbol, price_data)
            if not indicators_data:
                return signals

            # Create price lookup
            price_lookup = {data.date: data for data in price_data}

            # Sort dates for chronological processing
            sorted_dates = sorted(indicators_data.keys())

            # Direction 2: pre-compute the last trading day of each ISO week
            # so we only enter positions on weekly close (reduces noise from intra-week signals)
            # Pre-compute last trading day of each ISO week (used by weekly_close_only
            # and by enable_weekly_signals — weekly signals only fire on week end)
            weekly_last_trading_days: Set[date] = set()
            if self.weekly_close_only or self.enable_weekly_signals:
                for j in range(len(sorted_dates) - 1):
                    if sorted_dates[j].isocalendar()[1] != sorted_dates[j + 1].isocalendar()[1]:
                        weekly_last_trading_days.add(sorted_dates[j])
                if sorted_dates:
                    weekly_last_trading_days.add(sorted_dates[-1])

            # Filter 8: pre-compute weekly MA5/MA20 for this symbol
            weekly_closes_built: Optional[List[Tuple[date, Decimal]]] = None
            if self.require_weekly_trend or self.require_weekly_rsi:
                weekly_closes_built = _build_weekly_closes(price_data)

            if self.require_weekly_trend:
                if symbol not in self.weekly_ma_cache:
                    wma5 = _calculate_weekly_ma(weekly_closes_built, 5)
                    wma20 = _calculate_weekly_ma(weekly_closes_built, 20)
                    combined: Dict[Tuple[int, int], Tuple[Optional[Decimal], Optional[Decimal]]] = {}
                    all_weeks = set(wma5.keys()) | set(wma20.keys())
                    for wk in all_weeks:
                        combined[wk] = (wma5.get(wk), wma20.get(wk))
                    self.weekly_ma_cache[symbol] = combined
                weekly_data = self.weekly_ma_cache[symbol]
            else:
                weekly_data = {}

            # Filter 10: pre-compute weekly RSI(14)
            if self.require_weekly_rsi:
                if symbol not in self.weekly_rsi_cache:
                    if weekly_closes_built is None:
                        weekly_closes_built = _build_weekly_closes(price_data)
                    self.weekly_rsi_cache[symbol] = _calculate_weekly_rsi(weekly_closes_built, 14)
                weekly_rsi_data = self.weekly_rsi_cache[symbol]
            else:
                weekly_rsi_data = {}

            # Weekly signal indicators: BB and Donchian on weekly OHLCV
            weekly_bb_data: Dict[date, Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]] = {}
            weekly_donchian_data: Dict[date, Optional[Decimal]] = {}
            if self.enable_weekly_signals:
                if symbol not in self.weekly_bb_cache:
                    wohlcv = _build_weekly_ohlcv(price_data)
                    self.weekly_bb_cache[symbol] = _compute_weekly_bollinger(wohlcv, self.weekly_bb_period)
                    self.weekly_donchian_cache[symbol] = _compute_weekly_donchian_high(wohlcv, self.weekly_donchian_period)
                weekly_bb_data = self.weekly_bb_cache[symbol]
                weekly_donchian_data = self.weekly_donchian_cache[symbol]

            # Filter 11: pre-load monthly revenue history from FinMind
            if self.require_revenue_growth and self.finmind_api_token:
                if symbol not in self.revenue_cache:
                    try:
                        from ...infrastructure.market_data.finmind_client import FinMindRevenueLoader
                        loader = FinMindRevenueLoader(api_token=self.finmind_api_token)
                        start_str = sorted_dates[0].isoformat() if sorted_dates else "2020-01-01"
                        end_str = sorted_dates[-1].isoformat() if sorted_dates else "2026-12-31"
                        self.revenue_cache[symbol] = loader.load_stock_revenue_history(
                            symbol, start_date=start_str, end_date=end_str
                        )
                    except Exception as exc:
                        self.logger.warning(f"[Revenue] 無法載入 {symbol} 月營收: {exc}")
                        self.revenue_cache[symbol] = {}
                revenue_history = self.revenue_cache[symbol]
            else:
                revenue_history = {}

            # Filter 9: pre-compute rolling 252-day (52-week) high/low per date
            # Uses high_price for 52w high and low_price for 52w low
            w52_high_by_date: Dict[date, Optional[Decimal]] = {}
            w52_low_by_date: Dict[date, Optional[Decimal]] = {}
            if self.require_52w_filter:
                _W52 = 252
                for idx, d in enumerate(sorted_dates):
                    start_idx = max(0, idx - _W52 + 1)
                    window = sorted_dates[start_idx: idx + 1]
                    highs = [price_lookup[wd].high_price for wd in window if wd in price_lookup]
                    lows = [price_lookup[wd].low_price for wd in window if wd in price_lookup]
                    w52_high_by_date[d] = max(highs) if highs else None
                    w52_low_by_date[d] = min(lows) if lows else None

            # Filter 7: cooldown tracking — last BUY signal date per symbol
            # Processed across full history so cooldown works even when start_date restricts output
            last_buy_date: Dict[str, date] = {}

            for i, current_date in enumerate(sorted_dates):
                if end_date and current_date > end_date:
                    break

                # Need at least one previous date for signal detection
                if i == 0:
                    continue

                # Direction 2: only enter on the last trading day of each week
                if self.weekly_close_only and current_date not in weekly_last_trading_days:
                    continue

                # Skip if outside date range (still track cooldown state below)
                in_output_range = (not start_date or current_date >= start_date)

                current_indicators = indicators_data[current_date]
                previous_indicators = indicators_data[sorted_dates[i-1]]

                # Get current price data
                if current_date not in price_lookup:
                    continue

                current_price_data = price_lookup[current_date]

                # Convert to format for SignalDetector
                current_dict = self.convert_indicators_to_dict(current_indicators)
                previous_dict = self.convert_indicators_to_dict(previous_indicators)

                # Detect signals using existing logic
                detected_signals = self.signal_detector.detect_signals(
                    current_indicators=current_dict,
                    previous_indicators=previous_dict,
                    current_price=current_price_data.close_price,
                    volume=current_price_data.volume,
                    pre_breakout_mode=self.pre_breakout_mode,
                )

                # P3-B/A: RSI Momentum Loss — RSI crosses below 50 (trend losing momentum)
                # Faster than MACD Death Cross; signals early trend reversal for exit
                curr_rsi = current_indicators.rsi14
                prev_rsi = previous_indicators.rsi14
                if (curr_rsi is not None and prev_rsi is not None
                        and curr_rsi < Decimal('50') and prev_rsi >= Decimal('50')):
                    detected_signals.append({
                        'type': 'SELL',
                        'name': 'RSI Momentum Loss',
                        'description': f'RSI 跌破 50（{float(curr_rsi):.1f}），趨勢動能衰退',
                        'strength': 'MEDIUM',
                        'price': current_price_data.close_price,
                    })

                # P6: Donchian Channel signal (pre-breakout or confirmed breakout)
                if self.donchian_period > 0 and i >= self.donchian_period:
                    lookback_dates = sorted_dates[i - self.donchian_period: i]
                    donchian_high = max(
                        (price_lookup[d].high_price for d in lookback_dates if d in price_lookup),
                        default=None,
                    )
                    if donchian_high is not None:
                        close = current_price_data.close_price
                        if self.pre_breakout_mode:
                            # Pre-breakout: within 3% below the channel high
                            if donchian_high * Decimal('0.97') < close <= donchian_high:
                                detected_signals.append({
                                    'type': 'BUY',
                                    'name': 'Donchian Breakout',
                                    'description': f'接近近 {self.donchian_period} 日最高（{donchian_high}），前置佈局',
                                    'strength': 'STRONG',
                                    'price': close,
                                })
                        else:
                            # Confirmed breakout: close above channel high
                            if close > donchian_high:
                                detected_signals.append({
                                    'type': 'BUY',
                                    'name': 'Donchian Breakout',
                                    'description': f'收盤突破近 {self.donchian_period} 日最高（{donchian_high}）',
                                    'strength': 'STRONG',
                                    'price': close,
                                })

                # 方向 B: 第二 Donchian 週期（捕捉不同時間框架的突破）
                if self.donchian_period_2 > 0 and i >= self.donchian_period_2:
                    lookback_dates_2 = sorted_dates[i - self.donchian_period_2: i]
                    donchian_high_2 = max(
                        (price_lookup[d].high_price for d in lookback_dates_2 if d in price_lookup),
                        default=None,
                    )
                    if donchian_high_2 is not None:
                        close = current_price_data.close_price
                        if self.pre_breakout_mode:
                            if donchian_high_2 * Decimal('0.97') < close <= donchian_high_2:
                                detected_signals.append({
                                    'type': 'BUY',
                                    'name': 'Donchian Breakout 2',
                                    'description': f'接近近 {self.donchian_period_2} 日最高（{donchian_high_2}），前置佈局',
                                    'strength': 'STRONG',
                                    'price': close,
                                })
                        else:
                            if close > donchian_high_2:
                                detected_signals.append({
                                    'type': 'BUY',
                                    'name': 'Donchian Breakout 2',
                                    'description': f'收盤突破近 {self.donchian_period_2} 日最高（{donchian_high_2}）',
                                    'strength': 'STRONG',
                                    'price': close,
                                })

                # Multi-day momentum signal: N-day sustained price rise
                if self.enable_momentum_signal and i >= self.momentum_signal_days:
                    lookback = sorted_dates[i - self.momentum_signal_days: i]
                    past_date = lookback[0]
                    if past_date in price_lookup:
                        past_close = price_lookup[past_date].close_price
                        if past_close > 0:
                            n_day_return = (current_price_data.close_price - past_close) / past_close
                            if n_day_return >= self.momentum_signal_min_return:
                                detected_signals.append({
                                    'type': 'BUY',
                                    'name': 'Momentum Surge',
                                    'description': (
                                        f'{self.momentum_signal_days} 日累積漲幅 '
                                        f'{float(n_day_return):.1%}，持續動能'
                                    ),
                                    'strength': 'STRONG',
                                    'price': current_price_data.close_price,
                                })

                # Weekly signals — only fire on the last trading day of each ISO week
                if self.enable_weekly_signals and current_date in weekly_last_trading_days:
                    close = current_price_data.close_price

                    # Weekly BB Squeeze Break: price in top 30% of weekly BB (pre-breakout)
                    bb_tuple = weekly_bb_data.get(current_date)
                    if bb_tuple is not None:
                        w_upper, w_middle, _ = bb_tuple
                        if w_upper is not None and w_middle is not None and w_upper > w_middle:
                            threshold = w_middle + Decimal('0.7') * (w_upper - w_middle)
                            if threshold < close < w_upper:
                                detected_signals.append({
                                    'type': 'BUY',
                                    'name': 'Weekly BB Squeeze Break',
                                    'description': (
                                        f'週線 BB 擠壓突破前置：價格位於週 BB 上軌 70% 位置以上'
                                        f'（收盤 {float(close):.2f}，週 BB 中軌 {float(w_middle):.2f}，上軌 {float(w_upper):.2f}）'
                                    ),
                                    'strength': 'STRONG',
                                    'price': close,
                                })

                    # Weekly Donchian Breakout: close above prior N-week high
                    w_donchian_high = weekly_donchian_data.get(current_date)
                    if w_donchian_high is not None and close > w_donchian_high:
                        detected_signals.append({
                            'type': 'BUY',
                            'name': 'Weekly Donchian Breakout',
                            'description': (
                                f'週線突破近 {self.weekly_donchian_period} 週最高'
                                f'（收盤 {float(close):.2f} > {self.weekly_donchian_period} 週高 {float(w_donchian_high):.2f}）'
                            ),
                            'strength': 'STRONG',
                            'price': close,
                        })

                # VCP (Volatility Contraction Pattern) signal
                # Requires a series of contracting pullbacks + volume contraction
                if self.enable_vcp and i >= self.vcp_lookback:
                    vcp_dates = sorted_dates[i - self.vcp_lookback: i + 1]
                    vcp_closes = [
                        float(price_lookup[d].close_price)
                        for d in vcp_dates if d in price_lookup
                    ]
                    vcp_volumes = [
                        price_lookup[d].volume
                        for d in vcp_dates if d in price_lookup
                    ]
                    if _detect_vcp(vcp_closes, vcp_volumes):
                        detected_signals.append({
                            'type': 'BUY',
                            'name': 'VCP',
                            'description': f'波動收縮型態（{self.vcp_lookback} 日回調逐次縮小 + 量縮）',
                            'strength': 'STRONG',
                            'price': current_price_data.close_price,
                        })

                # ── Left-side (mean-reversion) signals ──────────────────────
                if self.enable_left_side_signals:
                    close = current_price_data.close_price

                    # Pre-check: not in free-fall (10-day drawdown < threshold)
                    _in_free_fall = False
                    if i >= 10:
                        lookback_10d = sorted_dates[i - 10: i]
                        close_10d_ago = price_lookup.get(lookback_10d[0])
                        if close_10d_ago is not None and close_10d_ago.close_price > 0:
                            drawdown_10d = (close_10d_ago.close_price - close) / close_10d_ago.close_price
                            if drawdown_10d >= self.left_side_max_drawdown_10d_pct:
                                _in_free_fall = True

                    if not _in_free_fall:
                        # Volume Climax: volume > 3x MA20 AND daily drop > 3%
                        if i >= 1:
                            prev_close_data = price_lookup.get(sorted_dates[i - 1])
                            if prev_close_data is not None and prev_close_data.close_price > 0:
                                daily_return = (close - prev_close_data.close_price) / prev_close_data.close_price
                                vol_ma20 = current_indicators.volume_ma20
                                if (daily_return < Decimal('-0.03')
                                        and vol_ma20 is not None and vol_ma20 > 0
                                        and current_price_data.volume > int(vol_ma20) * 3):
                                    detected_signals.append({
                                        'type': 'BUY',
                                        'name': 'Volume Climax',
                                        'description': (
                                            f'爆量急跌（量 {current_price_data.volume:,} > 3× MA20 {int(vol_ma20):,}，'
                                            f'跌幅 {float(daily_return):.1%}），投降性賣壓'
                                        ),
                                        'strength': 'STRONG',
                                        'price': close,
                                    })

                        # RSI Bullish Divergence: price makes new 20-day low but RSI is higher
                        # than at the previous swing low (bullish divergence)
                        _DIVERGENCE_LOOKBACK = 20
                        if i >= _DIVERGENCE_LOOKBACK:
                            lookback_dates = sorted_dates[i - _DIVERGENCE_LOOKBACK: i]
                            lookback_lows = [
                                (d, price_lookup[d].low_price)
                                for d in lookback_dates if d in price_lookup
                            ]
                            if lookback_lows:
                                min_low_date, min_low_price = min(lookback_lows, key=lambda x: x[1])
                                curr_low = current_price_data.low_price
                                curr_rsi = current_indicators.rsi14
                                # Current price at or below the lookback minimum
                                if (curr_low <= min_low_price
                                        and curr_rsi is not None
                                        and min_low_date in indicators_data):
                                    prev_low_rsi = indicators_data[min_low_date].rsi14
                                    # RSI higher (bullish divergence) — price lower but RSI higher
                                    if prev_low_rsi is not None and curr_rsi > prev_low_rsi:
                                        detected_signals.append({
                                            'type': 'BUY',
                                            'name': 'RSI Bullish Divergence',
                                            'description': (
                                                f'RSI 多頭背離（價格新低 {float(curr_low):.1f} ≤ {float(min_low_price):.1f}，'
                                                f'RSI {float(curr_rsi):.1f} > {float(prev_low_rsi):.1f}）'
                                            ),
                                            'strength': 'STRONG',
                                            'price': close,
                                        })

                        # Support Bounce: price touches within 2% of a 40-day swing low,
                        # then closes above it
                        _SUPPORT_LOOKBACK = 40
                        if i >= _SUPPORT_LOOKBACK:
                            support_dates = sorted_dates[i - _SUPPORT_LOOKBACK: i]
                            support_lows = [
                                price_lookup[d].low_price
                                for d in support_dates if d in price_lookup
                            ]
                            if support_lows:
                                swing_low = min(support_lows)
                                curr_low = current_price_data.low_price
                                # Touched within 2% of swing low, then closed above it
                                if (swing_low > 0
                                        and curr_low <= swing_low * Decimal('1.02')
                                        and close > swing_low):
                                    detected_signals.append({
                                        'type': 'BUY',
                                        'name': 'Support Bounce',
                                        'description': (
                                            f'支撐反彈（日低 {float(curr_low):.1f} 觸及 {_SUPPORT_LOOKBACK} 日'
                                            f'支撐 {float(swing_low):.1f}，收盤站回 {float(close):.1f}）'
                                        ),
                                        'strength': 'MEDIUM',
                                        'price': close,
                                    })

                # Convert to TradingSignal objects, applying buy-quality filters
                for signal_data in detected_signals:
                    signal_type = self.map_signal_type(signal_data['type'])

                    # Apply filters only to BUY signals
                    if signal_type == SignalType.BUY:
                        iso = current_date.isocalendar()
                        wk_key = (iso[0], iso[1])
                        w_ma5, w_ma20 = weekly_data.get(wk_key, (None, None))
                        w_rsi = weekly_rsi_data.get(wk_key)
                        # Look up most recent revenue on or before current_date
                        rev_yoy: Optional[float] = None
                        if revenue_history:
                            try:
                                from ...infrastructure.market_data.finmind_client import FinMindRevenueLoader
                                _loader = FinMindRevenueLoader(api_token=self.finmind_api_token)
                                rev_data = _loader.get_revenue_on_date(symbol, current_date, revenue_history)
                                if rev_data:
                                    rev_yoy = rev_data.get("yoy_pct")
                            except Exception:
                                pass
                        signal_type = self._apply_buy_filters(
                            signal_name=signal_data['name'],
                            price=current_price_data.close_price,
                            volume=current_price_data.volume,
                            indicators=current_indicators,
                            weekly_ma5=w_ma5,
                            weekly_ma20=w_ma20,
                            w52_high=w52_high_by_date.get(current_date) if self.require_52w_filter else None,
                            w52_low=w52_low_by_date.get(current_date) if self.require_52w_filter else None,
                            weekly_rsi=w_rsi,
                            revenue_yoy=rev_yoy,
                        )

                    # Filter 7: cooldown — downgrade BUY to WATCH if same symbol triggered
                    # a BUY within the last signal_cooldown_days trading dates
                    if signal_type == SignalType.BUY and self.signal_cooldown_days > 0:
                        prev_buy = last_buy_date.get(symbol)
                        if prev_buy is not None:
                            days_since = sum(
                                1 for d in sorted_dates
                                if prev_buy < d <= current_date
                            )
                            if days_since <= self.signal_cooldown_days:
                                self.logger.debug(
                                    f"Signal '{signal_data['name']}' blocked: cooldown "
                                    f"({days_since} trading days since last BUY on {prev_buy}) → WATCH"
                                )
                                signal_type = SignalType.WATCH

                    # Record last BUY date for cooldown tracking (regardless of output range)
                    if signal_type == SignalType.BUY:
                        last_buy_date[symbol] = current_date

                    # Only append to output within the requested date range
                    if not in_output_range:
                        continue

                    trading_signal = TradingSignal(
                        symbol=symbol,
                        date=current_date,
                        signal_type=signal_type,
                        signal_name=signal_data['name'],
                        price=current_price_data.close_price,
                        description=signal_data['description'],
                        strength=signal_data['strength'],
                        indicators=current_indicators
                    )

                    signals.append(trading_signal)

            # Filter 15: multi-signal confirmation
            # Downgrade BUY to WATCH if fewer than min_confirming_signals BUY signals
            # agree on the same (symbol, date).  Requires 2+ independent indicators
            # to fire simultaneously, reducing false positives.
            # Left-side signals use their own threshold (left_side_min_confirming_signals).
            if self.min_confirming_signals > 1 or self.left_side_min_confirming_signals > 1:
                from collections import Counter
                # Count right-side and left-side BUY signals separately
                right_buy_count: dict = Counter(
                    s.date for s in signals
                    if s.signal_type == SignalType.BUY and s.signal_name not in self.MEAN_REVERSION_SIGNALS
                )
                left_buy_count: dict = Counter(
                    s.date for s in signals
                    if s.signal_type == SignalType.BUY and s.signal_name in self.MEAN_REVERSION_SIGNALS
                )
                for s in signals:
                    if s.signal_type != SignalType.BUY:
                        continue
                    is_left = s.signal_name in self.MEAN_REVERSION_SIGNALS
                    if is_left:
                        threshold = self.left_side_min_confirming_signals
                        count = left_buy_count[s.date]
                    else:
                        threshold = self.min_confirming_signals
                        count = right_buy_count[s.date]
                    if count < threshold:
                        s.signal_type = SignalType.WATCH
                        self.logger.debug(
                            f"Signal '{s.signal_name}' on {s.date} downgraded: "
                            f"only {count}/{threshold} confirming signals → WATCH"
                        )

            self.logger.info(f"Generated {len(signals)} signals for {symbol}")
            return signals

        except Exception as e:
            self.logger.error(f"Error generating signals for {symbol}: {e}")
            return []

    def _apply_buy_filters(
        self,
        signal_name: str,
        price: Decimal,
        volume: int,
        indicators: TechnicalIndicators,
        weekly_ma5: Optional[Decimal] = None,
        weekly_ma20: Optional[Decimal] = None,
        w52_high: Optional[Decimal] = None,
        w52_low: Optional[Decimal] = None,
        weekly_rsi: Optional[Decimal] = None,
        revenue_yoy: Optional[float] = None,
    ) -> SignalType:
        """Apply quality filters to a BUY signal.

        Returns SignalType.BUY if all checks pass, SignalType.WATCH otherwise.
        Degrading to WATCH keeps the signal in reports for analysis without
        triggering actual trades.

        Filters (all evidence-based from backtests):
        1. Disabled signals list  — MACD Golden Cross / Golden Cross: win rate < 50%
        2. MA60 uptrend check     — price must be above MA60 (long-term trend)
        3. Volume confirmation     — today's volume > 1.5× MA20 volume
        4. MA alignment check     — MA5 > MA10 > MA20 (short/mid trend must be bullish)
        5. RSI momentum check     — RSI >= rsi_min_entry (avoid entering on false breakouts
                                    when momentum is weak; BB Squeeze Break had 44.8% win
                                    rate in Q4-2025 without this filter)
        6. Minimum volume lots    — liquidity filter
        7. Signal cooldown        — handled in generate_signals
        8. Weekly trend           — weekly MA5 > MA20 (medium-term uptrend confirmation)
        """
        # Route left-side (mean-reversion) signals to their own filter pipeline.
        # RSI Oversold uses the original right-side filter with uptrend guard.
        # New left-side signals (BB Lower Touch, Volume Climax, etc.) are blocked
        # entirely when enable_left_side_signals is False.
        if signal_name in self.MEAN_REVERSION_SIGNALS and signal_name != "RSI Oversold":
            if not self.enable_left_side_signals:
                return SignalType.WATCH
            return self._apply_mean_reversion_filters(
                signal_name=signal_name,
                price=price,
                volume=volume,
                indicators=indicators,
            )

        # Filter 1: disabled signals (poor historical win rate)
        if signal_name in self.disabled_signals:
            self.logger.debug(f"Signal '{signal_name}' is disabled → WATCH")
            return SignalType.WATCH

        # Filter 2: price above MA60 (stock in long-term uptrend)
        if self.require_ma60_uptrend:
            ma60 = indicators.ma60
            if ma60 is not None and price < ma60:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: price {price} < MA60 {ma60} → WATCH"
                )
                return SignalType.WATCH

        # Filter 3: volume confirmation (avoid low-liquidity breakouts)
        if self.require_volume_confirmation:
            volume_ma20 = indicators.volume_ma20
            if volume_ma20 is not None and volume_ma20 > 0:
                if Decimal(str(volume)) < Decimal(str(volume_ma20)) * self.volume_confirmation_multiplier:
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: volume {volume} < "
                        f"{self.volume_confirmation_multiplier}× MA20 {volume_ma20} → WATCH"
                    )
                    return SignalType.WATCH

        # Filter 4: MA alignment — MA5 > MA10 > MA20 ensures short AND mid-term trend is bullish.
        # Skipped for trend signals (Donchian Breakout / Golden Cross / MACD GC): the breakout
        # itself is the trend confirmation; requiring prior MA alignment would block early entries.
        if signal_name not in self.TREND_SIGNAL_NAMES:
            ma5 = indicators.ma5
            ma10 = indicators.ma10
            ma20 = indicators.ma20
            if ma5 is not None and ma10 is not None and ma20 is not None:
                if not (ma5 > ma10 > ma20):
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: MA alignment failed "
                        f"(MA5={ma5}, MA10={ma10}, MA20={ma20}) → WATCH"
                    )
                    return SignalType.WATCH

        # Filter 5: RSI momentum confirmation.
        # Require RSI >= rsi_min_entry (default 50) to ensure the stock has upward momentum.
        # A BB breakout with weak RSI (< 50) is typically a false breakout or dead-cat bounce.
        # Evidence: BB Squeeze Break win rate dropped from 54.1% (Q1-2026) to 44.8% (Q4-2025);
        # adding this filter aims to reject low-momentum breakouts that quickly reverse.
        # Mean-reversion signals (RSI Oversold) are exempt: they fire when RSI is low by design;
        # requiring RSI >= min_entry would paradoxically block all of them.
        if self.rsi_min_entry > 0 and signal_name not in self.MEAN_REVERSION_SIGNALS:
            rsi = indicators.rsi14
            if rsi is not None and rsi < self.rsi_min_entry:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: RSI {rsi} < min entry "
                    f"{self.rsi_min_entry} → WATCH"
                )
                return SignalType.WATCH

        # Filter 5b (B1): mean-reversion uptrend guard.
        # RSI Oversold is exempt from the RSI min-entry filter (it fires when RSI is low by
        # design). Without a trend context this catches falling knives. When enabled, require
        # the oversold dip to occur inside an established uptrend: price > MA60 AND weekly
        # MA5 > MA20 (when the data is available). Applies independently of the global
        # require_ma60_uptrend / require_weekly_trend toggles.
        if self.rsi_oversold_require_uptrend and signal_name in self.MEAN_REVERSION_SIGNALS:
            ma60 = indicators.ma60
            if ma60 is not None and price < ma60:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: oversold but price {price} < MA60 {ma60} "
                    f"(falling knife) → WATCH"
                )
                return SignalType.WATCH
            if weekly_ma5 is not None and weekly_ma20 is not None and weekly_ma5 <= weekly_ma20:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: oversold but weekly MA5 {weekly_ma5:.2f} "
                    f"<= weekly MA20 {weekly_ma20:.2f} (weekly downtrend) → WATCH"
                )
                return SignalType.WATCH

        # Filter 6: minimum daily volume (liquidity filter).
        # 1 lot (張) = 1,000 shares; min_volume_lots=1000 means volume >= 1,000,000 shares.
        # Avoids low-liquidity stocks where slippage invalidates backtest assumptions.
        if self.min_volume_lots > 0:
            min_shares = self.min_volume_lots * 1000
            if volume < min_shares:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: volume {volume} < "
                    f"min {min_shares} ({self.min_volume_lots} lots) → WATCH"
                )
                return SignalType.WATCH

        # Filter 8: weekly trend confirmation — weekly MA5 > MA20 ensures the medium-term
        # trend is upward (5-week avg > 20-week avg ≈ 1-month vs 5-month). Filters out
        # individual-day false breakouts that occur during a broader weekly downtrend.
        if self.require_weekly_trend:
            if weekly_ma5 is not None and weekly_ma20 is not None:
                if weekly_ma5 <= weekly_ma20:
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: weekly MA5 {weekly_ma5:.2f} "
                        f"<= weekly MA20 {weekly_ma20:.2f} → WATCH"
                    )
                    return SignalType.WATCH

        # Filter 9: 52-week high/low Minervini SEPA filter
        # - Price must be >= above_52w_low_pct above 52-week low (in an established uptrend)
        # - Price must be <= near_52w_high_pct from 52-week high (showing continued strength)
        if self.require_52w_filter:
            if w52_high is not None and w52_low is not None and w52_high > 0 and w52_low > 0:
                above_low_ratio = (price - w52_low) / w52_low
                below_high_ratio = (w52_high - price) / w52_high
                if above_low_ratio < self.above_52w_low_pct:
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: price {float(price):.1f} "
                        f"only {float(above_low_ratio):.1%} above 52w low {float(w52_low):.1f} "
                        f"(< {float(self.above_52w_low_pct):.0%}) → WATCH"
                    )
                    return SignalType.WATCH
                if below_high_ratio > self.near_52w_high_pct:
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: price {float(price):.1f} "
                        f"is {float(below_high_ratio):.1%} below 52w high {float(w52_high):.1f} "
                        f"(> {float(self.near_52w_high_pct):.0%}) → WATCH"
                    )
                    return SignalType.WATCH

        # Filter 12 (Direction 3): Minervini Stage 2 — price > MA60 > MA120, MA120 is valid
        # Ensures stock is in a confirmed long-term uptrend before entry
        if self.require_minervini_trend:
            ma60 = indicators.ma60
            ma120 = indicators.ma120
            if ma60 is not None and ma120 is not None:
                if not (price > ma60 > ma120):
                    self.logger.debug(
                        f"Signal '{signal_name}' blocked: Minervini Stage 2 failed "
                        f"price={float(price):.1f} MA60={float(ma60):.1f} MA120={float(ma120):.1f} → WATCH"
                    )
                    return SignalType.WATCH

        # Filter 13: weekly RSI bullish momentum
        if self.require_weekly_rsi and weekly_rsi is not None:
            if weekly_rsi < self.weekly_rsi_min:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: weekly RSI {float(weekly_rsi):.1f} "
                    f"< {float(self.weekly_rsi_min):.1f} → WATCH"
                )
                return SignalType.WATCH

        # Filter 14: monthly revenue YoY growth (fundamental filter)
        if self.require_revenue_growth and revenue_yoy is not None:
            if revenue_yoy < self.revenue_yoy_min_pct:
                self.logger.debug(
                    f"Signal '{signal_name}' blocked: revenue YoY {revenue_yoy:.1f}% "
                    f"< {self.revenue_yoy_min_pct:.1f}% → WATCH"
                )
                return SignalType.WATCH

        return SignalType.BUY

    def _apply_mean_reversion_filters(
        self,
        signal_name: str,
        price: Decimal,
        volume: int,
        indicators: TechnicalIndicators,
    ) -> SignalType:
        """Apply quality filters specific to left-side (mean-reversion) BUY signals.

        Left-side signals (BB Lower Touch, Volume Climax, RSI Bullish Divergence,
        Support Bounce) buy when stocks are oversold, so they intentionally skip
        right-side filters like MA alignment, RSI momentum, 52-week, weekly trend,
        and revenue growth.

        Filters applied:
        1. Disabled signals check
        2. Not in free-fall (10-day drawdown < threshold)
        3. Minimum volume lots (liquidity)
        4. Not a penny stock (price >= left_side_min_price)
        """
        # Filter 1: disabled signals
        if signal_name in self.left_side_disabled_signals:
            self.logger.debug(f"Left-side signal '{signal_name}' is disabled → WATCH")
            return SignalType.WATCH

        # Filter 2: not a penny stock
        if price < self.left_side_min_price:
            self.logger.debug(
                f"Left-side signal '{signal_name}' blocked: price {price} "
                f"< min {self.left_side_min_price} → WATCH"
            )
            return SignalType.WATCH

        # Filter 3: minimum daily volume (liquidity, same as right-side)
        if self.min_volume_lots > 0:
            min_shares = self.min_volume_lots * 1000
            if volume < min_shares:
                self.logger.debug(
                    f"Left-side signal '{signal_name}' blocked: volume {volume} < "
                    f"min {min_shares} ({self.min_volume_lots} lots) → WATCH"
                )
                return SignalType.WATCH

        # Filter 4: not in free-fall is checked in generate_signals() where
        # we have access to historical price data (10-day lookback)

        return SignalType.BUY

    def map_signal_type(self, signal_type_str: str) -> SignalType:
        """Map string signal type to SignalType enum"""
        mapping = {
            'BUY': SignalType.BUY,
            'SELL': SignalType.SELL,
            'WATCH': SignalType.WATCH
        }
        return mapping.get(signal_type_str, SignalType.WATCH)

    def generate_signals_for_multiple_stocks(
        self,
        stock_data_dict: Dict[str, List[StockData]],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TradingSignal]:
        """
        Generate trading signals for multiple stocks

        Args:
            stock_data_dict: Dictionary mapping symbols to price data
            start_date: Start date for signal generation
            end_date: End date for signal generation

        Returns:
            List of trading signals for all stocks
        """
        all_signals = []
        total_stocks = len(stock_data_dict)

        self.logger.info(f"Generating signals for {total_stocks} stocks")

        for i, (symbol, price_data) in enumerate(stock_data_dict.items(), 1):
            self.logger.info(f"Processing {symbol} ({i}/{total_stocks})")

            signals = self.generate_signals(symbol, price_data, start_date, end_date)
            all_signals.extend(signals)

        self.logger.info(f"Generated {len(all_signals)} total signals")
        return all_signals

    def get_signal_summary(self, signals: List[TradingSignal]) -> Dict:
        """
        Get summary statistics of generated signals

        Args:
            signals: List of trading signals

        Returns:
            Dictionary with signal summary
        """
        summary = {
            'total_signals': len(signals),
            'buy_signals': len([s for s in signals if s.signal_type == SignalType.BUY]),
            'sell_signals': len([s for s in signals if s.signal_type == SignalType.SELL]),
            'watch_signals': len([s for s in signals if s.signal_type == SignalType.WATCH]),
            'signals_by_name': {},
            'signals_by_symbol': {},
            'date_range': None
        }

        if signals:
            # Count by signal name
            for signal in signals:
                name = signal.signal_name
                if name not in summary['signals_by_name']:
                    summary['signals_by_name'][name] = 0
                summary['signals_by_name'][name] += 1

            # Count by symbol
            for signal in signals:
                symbol = signal.symbol
                if symbol not in summary['signals_by_symbol']:
                    summary['signals_by_symbol'][symbol] = 0
                summary['signals_by_symbol'][symbol] += 1

            # Date range
            dates = [s.date for s in signals]
            summary['date_range'] = {
                'start': min(dates),
                'end': max(dates)
            }

        return summary

    def filter_signals(
        self,
        signals: List[TradingSignal],
        signal_types: Optional[List[SignalType]] = None,
        signal_names: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TradingSignal]:
        """
        Filter signals based on various criteria

        Args:
            signals: List of trading signals
            signal_types: Filter by signal types
            signal_names: Filter by signal names
            symbols: Filter by symbols
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Filtered list of trading signals
        """
        filtered = signals

        if signal_types:
            filtered = [s for s in filtered if s.signal_type in signal_types]

        if signal_names:
            filtered = [s for s in filtered if s.signal_name in signal_names]

        if symbols:
            filtered = [s for s in filtered if s.symbol in symbols]

        if start_date:
            filtered = [s for s in filtered if s.date >= start_date]

        if end_date:
            filtered = [s for s in filtered if s.date <= end_date]

        return filtered

    def build_momentum_rankings(
        self,
        stock_data_dict: Dict[str, List[StockData]],
        lookback_days: int = 20,
        top_n: int = 50,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[date, Set[str]]:
        """Build a daily top-N momentum whitelist from historical price data.

        For each trading date in [start_date, end_date], rank all stocks by their
        lookback_days price return (close[t] / close[t-lookback_days] - 1) and
        return the set of symbols that rank in the top_n.

        Stocks without enough history to compute the lookback return are excluded
        from consideration (not promoted to top-N by default).

        Args:
            stock_data_dict: Symbol → list of StockData (sorted by date ascending).
            lookback_days:   Number of calendar days to look back when computing
                             momentum (default 20 ≈ 1 trading month).
            top_n:           Maximum number of symbols allowed per day (0 = no limit).
            start_date:      First date to include in the output dict.
            end_date:        Last date to include in the output dict.

        Returns:
            Dict mapping each trading date to a set of the top_n symbol strings.
        """
        if top_n <= 0:
            return {}

        # Build per-symbol price lookups: {symbol: {date: close_price}}
        price_lookup: Dict[str, Dict[date, Decimal]] = {}
        for symbol, records in stock_data_dict.items():
            price_lookup[symbol] = {r.date: r.close_price for r in records}

        # Collect all unique trading dates across the universe
        all_dates: Set[date] = set()
        for records in stock_data_dict.values():
            for r in records:
                all_dates.add(r.date)

        # Filter to the requested range
        if start_date:
            all_dates = {d for d in all_dates if d >= start_date}
        if end_date:
            all_dates = {d for d in all_dates if d <= end_date}

        whitelist: Dict[date, Set[str]] = {}

        for target_date in sorted(all_dates):
            lookback_target = target_date - timedelta(days=lookback_days)

            momentum_scores: Dict[str, float] = {}
            for symbol, prices in price_lookup.items():
                current_close = prices.get(target_date)
                if current_close is None:
                    continue  # symbol not traded on this date

                # Find the closest available date on or before the lookback target
                past_dates = [d for d in prices if d <= lookback_target]
                if not past_dates:
                    continue  # not enough history

                past_close = prices[max(past_dates)]
                if past_close == 0:
                    continue

                momentum = float(current_close / past_close) - 1.0
                momentum_scores[symbol] = momentum

            # Rank by momentum descending, keep top_n
            ranked = sorted(momentum_scores, key=lambda s: momentum_scores[s], reverse=True)
            whitelist[target_date] = set(ranked[:top_n])

        self.logger.info(
            f"Built momentum rankings for {len(whitelist)} dates "
            f"(lookback={lookback_days}d, top_n={top_n})"
        )
        return whitelist

    def build_sector_whitelist(
        self,
        stock_data_dict: Dict[str, List[StockData]],
        sector_analyzer,  # SectorTrendAnalyzer（避免循環 import 用 duck-typing）
        threshold: float = 0.5,
        ma_period: int = 20,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_momentum: bool = False,
        momentum_lookback_days: int = 60,
        top_pct: float = 0.20,
    ) -> Dict[date, Set[str]]:
        """Build a daily sector-trend whitelist from historical price data.

        For each trading date, computes the sector strength (fraction of stocks
        in the sector whose close > MA{ma_period}).  Symbols that belong to a
        strong sector (strength >= threshold) are included in the whitelist for
        that date.

        Args:
            stock_data_dict: Symbol → list of StockData (sorted by date ascending).
            sector_analyzer:  SectorTrendAnalyzer instance (duck-typed to avoid
                              circular import).
            threshold:        Minimum fraction of stocks above MA{ma_period} for a
                              sector to be considered strong (default 0.5 = 50%).
            ma_period:        Period for the moving average used in sector strength
                              calculation (default 20).
            start_date:       First date to include in the output dict.
            end_date:         Last date to include in the output dict.

        Returns:
            Dict mapping each trading date to a set of symbol strings that are in
            strong sectors.  An empty dict means the filter is disabled.
        """
        # Pre-build per-symbol price lookup and sector assignment
        price_lookup: Dict[str, Dict[date, Decimal]] = {}
        symbol_sector: Dict[str, str] = {}
        for symbol, records in stock_data_dict.items():
            price_lookup[symbol] = {r.date: r.close_price for r in records}
            symbol_sector[symbol] = sector_analyzer.get_stock_sector(symbol)

        # Collect all trading dates in range
        all_dates: Set[date] = set()
        for records in stock_data_dict.values():
            for r in records:
                all_dates.add(r.date)
        if start_date:
            all_dates = {d for d in all_dates if d >= start_date}
        if end_date:
            all_dates = {d for d in all_dates if d <= end_date}

        whitelist: Dict[date, Set[str]] = {}

        for target_date in sorted(all_dates):
            if use_momentum:
                # Momentum-based: rank sectors by average recent return, keep top pct
                sector_momentum = sector_analyzer.compute_sector_momentum(
                    stock_data_dict, target_date, lookback_days=momentum_lookback_days
                )
                strong_sectors = sector_analyzer.get_strong_sectors_by_momentum(
                    sector_momentum, top_pct=top_pct
                )
            else:
                # Binary MA20-based: fraction of stocks above MA20 >= threshold
                sector_strength = sector_analyzer.compute_sector_strength(
                    stock_data_dict, target_date, ma_period=ma_period
                )
                strong_sectors = sector_analyzer.get_strong_sectors(sector_strength, threshold)

            # Collect all symbols in strong sectors
            allowed: Set[str] = set()
            for symbol in stock_data_dict:
                sector = symbol_sector[symbol]
                if sector in strong_sectors:
                    allowed.add(symbol)

            whitelist[target_date] = allowed

        strong_sector_dates = sum(
            1 for d, allowed in whitelist.items()
            if len(allowed) < len(stock_data_dict)
        )
        self.logger.info(
            f"Built sector whitelist for {len(whitelist)} dates "
            f"(threshold={threshold:.0%}, ma_period={ma_period}); "
            f"filter active on {strong_sector_dates} dates"
        )
        return whitelist
    def build_factor_whitelist(
        self,
        stock_data_dict: Dict[str, List[StockData]],
        top_n: int = 15,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        inst_consecutive_by_date: Optional[Dict[date, Dict[str, dict]]] = None,
    ) -> Dict[date, Set[str]]:
        """Build a daily top-N factor whitelist from historical OHLCV data.

        For each trading date, ranks all stocks by a composite factor score:
          - RPS 3m (63 交易日報酬百分位): 25%
          - RPS 6m (126 交易日報酬百分位): 25%
          - 量能比率 (今日量/20日均量百分位): 20%
          - 法人連續買超: 30%

        Institutional data: when `inst_consecutive_by_date` is provided (built
        from the T86 historical cache via
        InstitutionalHistoryLoader.build_consecutive_series), the 30%
        institutional weight uses real consecutive-buy streaks
        (foreign*0.6 + trust*0.4, percentile-ranked cross-sectionally).
        Otherwise all stocks receive a uniform 0.5 (legacy behaviour), so
        ranking is effectively determined by RPS + volume ratio only.

        Args:
            stock_data_dict: Symbol → list of StockData (sorted by date ascending).
            top_n:           Number of top-ranked symbols to allow per day.
            start_date:      First date to include.
            end_date:        Last date to include.
            inst_consecutive_by_date: {date: {symbol: {"foreign_consecutive": int,
                             "trust_consecutive": int}}} from T86 history cache.

        Returns:
            Dict mapping each trading date to a set of top-N symbol strings.
        """
        from .factor_engine import FactorEngine, _percentile_rank

        if top_n <= 0:
            return {}

        engine = FactorEngine()

        # Build per-symbol OHLCV lookup for fast access
        # {symbol: sorted list of StockData}
        sorted_data: Dict[str, List[StockData]] = {
            sym: sorted(records, key=lambda r: r.date)
            for sym, records in stock_data_dict.items()
        }

        # Collect all unique trading dates
        all_dates: Set[date] = set()
        for records in stock_data_dict.values():
            for r in records:
                all_dates.add(r.date)

        if start_date:
            all_dates = {d for d in all_dates if d >= start_date}
        if end_date:
            all_dates = {d for d in all_dates if d <= end_date}

        whitelist: Dict[date, Set[str]] = {}
        inst_by_date = inst_consecutive_by_date or {}
        # T86 是「逐日快照」資料；非交易日/缺漏日沿用最近一個可用日
        inst_dates_sorted = sorted(inst_by_date.keys())

        def _inst_for_date(target: date) -> Dict[str, dict]:
            if not inst_dates_sorted:
                return {}
            # 找 <= target 的最近一日（無 lookahead）
            candidates = [d for d in inst_dates_sorted if d <= target]
            return inst_by_date[candidates[-1]] if candidates else {}

        for target_date in sorted(all_dates):
            # Compute raw scores for all symbols
            rps_3m_raw = engine._compute_rps(sorted_data, target_date, 63)
            rps_6m_raw = engine._compute_rps(sorted_data, target_date, 126)
            vol_ratio_raw = engine._compute_vol_ratio(sorted_data, target_date)

            # Percentile rank across full universe
            rps_3m_pct = _percentile_rank(rps_3m_raw)
            rps_6m_pct = _percentile_rank(rps_6m_raw)
            vol_ratio_pct = _percentile_rank(vol_ratio_raw)

            # Institutional score: real T86 streaks when available, else 0.5
            inst_day = _inst_for_date(target_date)
            inst_raw: Dict[str, float] = {
                sym: vals.get("foreign_consecutive", 0) * 0.6
                + vals.get("trust_consecutive", 0) * 0.4
                for sym, vals in inst_day.items()
            }
            inst_pct = _percentile_rank(inst_raw) if inst_raw else {}

            composite: Dict[str, float] = {}
            all_syms = set(rps_3m_pct) | set(rps_6m_pct) | set(vol_ratio_pct)
            for sym in all_syms:
                r3 = rps_3m_pct.get(sym, 0.5)
                r6 = rps_6m_pct.get(sym, 0.5)
                v = vol_ratio_pct.get(sym, 0.5)
                # 上櫃股無 T86 資料 → 中位數 0.5（與生產 FactorEngine 一致）
                i = inst_pct.get(sym, 0.5)
                composite[sym] = r3 * 0.25 + r6 * 0.25 + v * 0.20 + i * 0.30

            # Top-N
            ranked = sorted(composite, key=lambda s: composite[s], reverse=True)
            whitelist[target_date] = set(ranked[:top_n])

        self.logger.info(
            f"Built factor whitelist for {len(whitelist)} dates "
            f"(top_n={top_n}, inst_data={'real T86' if inst_by_date else 'uniform 0.5'})"
        )
        return whitelist
