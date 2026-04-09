"""
Backtesting engine with portfolio management and performance calculation
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Set, Tuple
import uuid

from .models import (
    StockData, TradingSignal, Order, Position, Portfolio,
    SignalType, OrderType, PositionStatus, BacktestResult
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BacktestEngine:
    """Backtesting engine for strategy evaluation"""

    def __init__(
        self,
        initial_capital: Decimal = Decimal('1000000'),
        commission_rate: Decimal = Decimal('0.001425'),  # 0.1425%
        tax_rate: Decimal = Decimal('0.003'),  # 0.3% for selling only
        position_sizing: Decimal = Decimal('0.1'),  # 10% of initial capital per position
        stop_loss_pct: Decimal = Decimal('0.05'),  # 5% stop loss
        take_profit_pct: Decimal = Decimal('0.20'),  # 20% take profit
        max_holding_days: int = 30,
        trailing_stop_pct: Optional[Decimal] = Decimal('0.05'),  # 5% trailing stop from peak
        # P3-C: market regime-based signal routing
        market_regime_strong_rsi: float = 60.0,
        strong_regime_signals: Optional[List[str]] = None,
        neutral_regime_signals: Optional[List[str]] = None,
        # P5: trend signal position multiplier in STRONG regime
        strong_trend_signals: Optional[List[str]] = None,
        strong_trend_multiplier: float = 1.0,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.position_sizing = position_sizing
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_holding_days = max_holding_days
        self.trailing_stop_pct = trailing_stop_pct
        self.benchmark_bullish: Dict[date, bool] = {}  # date -> True if all market regime checks pass
        self.benchmark_rsi: Dict[date, Decimal] = {}   # date -> TAIEX RSI(14) value
        self.momentum_whitelist: Dict[date, Set[str]] = {}  # date -> set of allowed symbols
        self.sector_whitelist: Dict[date, Set[str]] = {}    # date -> set of symbols in strong sectors
        # P3-C: regime-based signal routing
        # None = no restriction (all signals allowed in that regime)
        self.market_regime_strong_rsi = market_regime_strong_rsi
        self.strong_regime_signals: Optional[List[str]] = strong_regime_signals
        self.neutral_regime_signals: Optional[List[str]] = neutral_regime_signals
        # P5: trend signal multiplier (STRONG regime only)
        self.strong_trend_signals: Optional[List[str]] = strong_trend_signals
        self.strong_trend_multiplier: float = strong_trend_multiplier
        # P6: per-signal exit config (trend signals use wider stop / longer holding)
        # Keys are signal names; each value is a dict with optional keys:
        #   stop_loss_pct, take_profit_pct, trailing_stop_pct, max_holding_days
        self.signal_exit_config: Dict[str, dict] = {}

        self.logger = get_logger(self.__class__.__name__)

        # Portfolio state
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.orders: List[Order] = []
        self.portfolio_history: List[Portfolio] = []

        # Tracking
        self.current_date: Optional[date] = None
        self.price_data: Dict[str, Dict[date, StockData]] = {}

    def add_price_data(self, symbol: str, data: List[StockData]):
        """Add price data for a symbol"""
        if symbol not in self.price_data:
            self.price_data[symbol] = {}

        for stock_data in data:
            self.price_data[symbol][stock_data.date] = stock_data

        self.logger.debug(f"Added {len(data)} price records for {symbol}")

    def get_current_price(self, symbol: str, target_date: date) -> Optional[Decimal]:
        """Get current price for a symbol on a specific date"""
        if symbol in self.price_data and target_date in self.price_data[symbol]:
            return self.price_data[symbol][target_date].close_price
        return None

    def calculate_position_size(self, price: Decimal) -> int:
        """Calculate position size based on fixed % of initial capital (not current cash).

        Using initial_capital as the basis ensures every position targets the same
        dollar exposure regardless of running P&L.  If 1 lot (1,000 shares) exceeds
        the target amount the stock is too expensive to fit the sizing rule → skip it.
        """
        target_amount = self.initial_capital * self.position_sizing
        shares = int(target_amount / price / 1000) * 1000  # Round down to whole lots (1張)
        if shares < 1000:
            return 0  # 1 lot alone exceeds position limit; skip this stock
        total_cost = price * shares * (Decimal('1') + self.commission_rate)
        return shares if self.cash >= total_cost else 0

    def calculate_trading_costs(self, price: Decimal, quantity: int, is_buy: bool) -> Tuple[Decimal, Decimal]:
        """
        Calculate trading costs (commission and tax)

        Args:
            price: Trade price
            quantity: Number of shares
            is_buy: True for buy order, False for sell order

        Returns:
            Tuple of (commission, tax)
        """
        trade_value = price * quantity
        commission = (trade_value * self.commission_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Tax only applies to selling
        tax = Decimal('0')
        if not is_buy:
            tax = (trade_value * self.tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        return commission, tax

    def execute_buy_order(self, signal: TradingSignal, sizing_override: Optional[Decimal] = None) -> bool:
        """
        Execute a buy order based on trading signal

        Args:
            signal: Trading signal
            sizing_override: Override position_sizing for this order (P5: trend signals in STRONG)

        Returns:
            True if order executed successfully
        """
        try:
            # Check if we already have a position in this stock
            if signal.symbol in self.positions:
                self.logger.debug(f"Already holding position in {signal.symbol}")
                return False

            # Calculate position size (use override if provided)
            if sizing_override is not None:
                original = self.position_sizing
                self.position_sizing = sizing_override
                quantity = self.calculate_position_size(signal.price)
                self.position_sizing = original
            else:
                quantity = self.calculate_position_size(signal.price)
            if quantity <= 0:
                self.logger.debug(f"Insufficient cash for {signal.symbol}")
                return False

            # Calculate costs
            commission, tax = self.calculate_trading_costs(signal.price, quantity, is_buy=True)
            total_cost = signal.price * quantity + commission + tax

            if total_cost > self.cash:
                self.logger.debug(f"Insufficient cash for {signal.symbol} (need: {total_cost}, have: {self.cash})")
                return False

            # Execute order
            order_id = str(uuid.uuid4())
            order = Order(
                order_id=order_id,
                symbol=signal.symbol,
                order_type=OrderType.MARKET,
                signal_type=SignalType.BUY,
                quantity=quantity,
                price=signal.price,
                timestamp=datetime.combine(signal.date, datetime.min.time()),
                executed_price=signal.price,
                executed_quantity=quantity,
                executed_time=datetime.combine(signal.date, datetime.min.time()),
                commission=commission,
                tax=tax
            )

            # Update cash
            self.cash -= total_cost

            # Apply per-signal exit config (P6: trend signals use wider stop / longer holding)
            exit_cfg = self.signal_exit_config.get(signal.signal_name, {})
            eff_stop_loss_pct = exit_cfg.get("stop_loss_pct", self.stop_loss_pct)
            eff_take_profit_pct = exit_cfg.get("take_profit_pct", self.take_profit_pct)
            eff_trailing_pct = exit_cfg.get("trailing_stop_pct", None)
            eff_max_holding = exit_cfg.get("max_holding_days", None)
            eff_exit_on_signals = exit_cfg.get("exit_on_signals", None)
            eff_profit_threshold = exit_cfg.get("profit_threshold_pct", None)
            eff_profit_trailing = exit_cfg.get("profit_trailing_pct", None)

            # Create position
            position = Position(
                symbol=signal.symbol,
                quantity=quantity,
                entry_price=signal.price,
                entry_date=signal.date,
                current_price=signal.price,
                current_date=signal.date,
                status=PositionStatus.OPEN,
                stop_loss=signal.price * (Decimal('1') - eff_stop_loss_pct),
                take_profit=signal.price * (Decimal('1') + eff_take_profit_pct),
                entry_signal_name=signal.signal_name,
                max_holding_days_override=eff_max_holding,
                trailing_stop_pct_override=eff_trailing_pct,
                exit_on_signals=eff_exit_on_signals,
                profit_threshold_pct=eff_profit_threshold,
                profit_trailing_pct=eff_profit_trailing,
            )

            self.positions[signal.symbol] = position
            self.orders.append(order)

            self.logger.info(f"BUY {signal.symbol}: {quantity} shares @ {signal.price} (Total: {total_cost})")
            return True

        except Exception as e:
            self.logger.error(f"Error executing buy order for {signal.symbol}: {e}")
            return False

    def execute_sell_order(self, symbol: str, price: Decimal, reason: str = "Signal") -> bool:
        """
        Execute a sell order for a position

        Args:
            symbol: Stock symbol
            price: Sell price
            reason: Reason for selling

        Returns:
            True if order executed successfully
        """
        try:
            if symbol not in self.positions:
                return False

            position = self.positions[symbol]
            quantity = position.quantity

            # Calculate costs
            commission, tax = self.calculate_trading_costs(price, quantity, is_buy=False)
            proceeds = price * quantity - commission - tax

            # Execute order
            order_id = str(uuid.uuid4())
            order = Order(
                order_id=order_id,
                symbol=symbol,
                order_type=OrderType.MARKET,
                signal_type=SignalType.SELL,
                quantity=quantity,
                price=price,
                timestamp=datetime.combine(self.current_date, datetime.min.time()),
                executed_price=price,
                executed_quantity=quantity,
                executed_time=datetime.combine(self.current_date, datetime.min.time()),
                commission=commission,
                tax=tax
            )

            # Update cash
            self.cash += proceeds

            # Close position
            position.exit_price = price
            position.exit_date = self.current_date
            position.status = PositionStatus.CLOSED
            position.holding_days = (self.current_date - position.entry_date).days
            position.pnl = proceeds - (position.entry_price * quantity)
            position.pnl_percent = ((price - position.entry_price) / position.entry_price * Decimal('100')).quantize(Decimal('0.01'))

            self.closed_positions.append(position)
            del self.positions[symbol]
            self.orders.append(order)

            self.logger.info(f"SELL {symbol}: {quantity} shares @ {price} ({reason}) PnL: {position.pnl} ({position.pnl_percent}%)")
            return True

        except Exception as e:
            self.logger.error(f"Error executing sell order for {symbol}: {e}")
            return False

    def check_position_exits(self):
        """Check and execute position exits based on stop loss, take profit, or max holding period"""
        positions_to_close = []

        for symbol, position in self.positions.items():
            current_price = self.get_current_price(symbol, self.current_date)
            if current_price is None:
                continue

            # Update current price
            position.current_price = current_price
            position.current_date = self.current_date

            # Update trailing stop: ratchet up as price rises above entry
            # P6: use per-position trailing_stop_pct_override if explicitly set, else engine default
            # P3-B: Decimal('0') means trailing stop disabled (signal-based exit instead)
            if position.trailing_stop_pct_override is not None:
                eff_trailing = position.trailing_stop_pct_override  # may be 0 = disabled
            else:
                eff_trailing = self.trailing_stop_pct
            if eff_trailing and current_price > position.entry_price:
                new_trailing_stop = (
                    current_price * (Decimal('1') - eff_trailing)
                ).quantize(Decimal('0.01'))
                if new_trailing_stop > (position.stop_loss or Decimal('0')):
                    position.stop_loss = new_trailing_stop

            # C: profit-protection trailing stop — only activates once position is in profit
            # > profit_threshold_pct (e.g. 5%). Ratchets at profit_trailing_pct (e.g. 6%) from peak.
            if (position.profit_threshold_pct is not None
                    and position.profit_trailing_pct is not None):
                profit_pct = (current_price - position.entry_price) / position.entry_price
                if profit_pct > position.profit_threshold_pct:
                    protection_stop = (
                        current_price * (Decimal('1') - position.profit_trailing_pct)
                    ).quantize(Decimal('0.01'))
                    if protection_stop > (position.stop_loss or Decimal('0')):
                        position.stop_loss = protection_stop

            # Check stop loss
            if position.stop_loss is not None and current_price <= position.stop_loss:
                positions_to_close.append((symbol, current_price, "Stop Loss"))

            # Check take profit
            elif position.take_profit is not None and current_price >= position.take_profit:
                positions_to_close.append((symbol, current_price, "Take Profit"))

            # Check max holding period (P6: use per-position override if set)
            else:
                eff_max_days = position.max_holding_days_override or self.max_holding_days
                if (self.current_date - position.entry_date).days >= eff_max_days:
                    positions_to_close.append((symbol, current_price, "Max Holding Period"))

        # Execute exits
        for symbol, price, reason in positions_to_close:
            self.execute_sell_order(symbol, price, reason)

    def update_portfolio(self):
        """Update portfolio values and save to history"""
        total_value = self.cash

        # Calculate unrealized PnL
        unrealized_pnl = Decimal('0')
        for position in self.positions.values():
            if position.current_price:
                position_value = position.current_price * position.quantity
                total_value += position_value
                entry_value = position.entry_price * position.quantity
                unrealized_pnl += position_value - entry_value

        # Calculate realized PnL
        realized_pnl = sum(pos.pnl or Decimal('0') for pos in self.closed_positions)
        total_pnl = realized_pnl + unrealized_pnl

        # Create portfolio snapshot
        portfolio = Portfolio(
            cash=self.cash,
            total_value=total_value,
            positions=list(self.positions.values()),
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            date=self.current_date
        )

        self.portfolio_history.append(portfolio)

    @staticmethod
    def _calc_rsi(closes: List[Decimal], period: int = 14) -> Optional[Decimal]:
        """Calculate RSI for the last element given a price list.

        Returns None when there is insufficient data (< period + 1 bars).
        """
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for j in range(len(closes) - period, len(closes)):
            delta = closes[j] - closes[j - 1]
            if delta > 0:
                gains.append(delta)
                losses.append(Decimal('0'))
            else:
                gains.append(Decimal('0'))
                losses.append(abs(delta))
        avg_gain = sum(gains) / Decimal(str(period))
        avg_loss = sum(losses) / Decimal(str(period))
        if avg_loss == 0:
            return Decimal('100')
        rs = avg_gain / avg_loss
        return Decimal('100') - (Decimal('100') / (Decimal('1') + rs))

    def build_benchmark_filter(
        self,
        benchmark_data: List[StockData],
        ma_period: int = 20,
        ma_short: int = 5,
        rsi_period: int = 14,
        rsi_threshold: float = 45.0,
        check_ma5: bool = True,
    ):
        """Pre-compute whether each benchmark date passes all market regime checks.

        Bullish = ALL enabled conditions are met:
          1. TAIEX close >= MA20   — price above long-term trend
          2. TAIEX MA5 >= MA20    — short-term trend above long-term (if check_ma5=True)
          3. TAIEX RSI(14) >= rsi_threshold — market has upward momentum

        Result stored in self.benchmark_bullish for O(1) lookups in run_backtest.
        """
        if not benchmark_data:
            return
        prices = sorted(benchmark_data, key=lambda x: x.date)
        closes = [p.close_price for p in prices]
        rsi_dec = Decimal(str(rsi_threshold))

        for i in range(len(prices)):
            # Need at least ma_period bars for MA20
            if i < ma_period - 1:
                continue

            # Condition 1: close >= MA20
            window_long = closes[i - ma_period + 1: i + 1]
            ma20 = sum(window_long) / Decimal(str(ma_period))
            above_ma20 = prices[i].close_price >= ma20

            # Condition 2: MA5 >= MA20 (optional)
            if check_ma5 and i >= ma_short - 1:
                window_short = closes[i - ma_short + 1: i + 1]
                ma5 = sum(window_short) / Decimal(str(ma_short))
                ma5_above_ma20 = ma5 >= ma20
            else:
                ma5_above_ma20 = True  # skip when disabled or insufficient data

            # Condition 3: RSI(14) >= threshold
            rsi_window = closes[max(0, i - rsi_period): i + 1]
            rsi = self._calc_rsi(rsi_window, period=rsi_period)
            rsi_ok = (rsi is not None and rsi >= rsi_dec)

            self.benchmark_bullish[prices[i].date] = above_ma20 and ma5_above_ma20 and rsi_ok
            if rsi is not None:
                self.benchmark_rsi[prices[i].date] = rsi

    def is_market_bullish(self, target_date: date) -> bool:
        """Return True if TAIEX passes all market regime checks on or before target_date.

        Falls back to True (no filter) when benchmark data is unavailable.
        """
        if not self.benchmark_bullish:
            return True
        available = [d for d in self.benchmark_bullish if d <= target_date]
        if not available:
            return True
        return self.benchmark_bullish[max(available)]

    def get_market_regime(self, target_date: date) -> str:
        """Return the market regime for a given date: 'STRONG', 'NEUTRAL', or 'WEAK'.

        P3-C (2026-04-08): Three-zone regime routing.

        WEAK   — market regime filter fails (is_market_bullish=False)
                 → all BUY signals suppressed

        NEUTRAL — market is bullish but TAIEX RSI < market_regime_strong_rsi (default 60)
                  → only neutral_regime_signals allowed (e.g. BB Squeeze Break)

        STRONG  — market is bullish AND TAIEX RSI >= market_regime_strong_rsi
                  → all signals allowed (trend + mean-reversion)

        Falls back to 'NEUTRAL' when benchmark RSI data is unavailable.
        """
        if not self.is_market_bullish(target_date):
            return "WEAK"
        if not self.benchmark_rsi:
            return "NEUTRAL"
        available = [d for d in self.benchmark_rsi if d <= target_date]
        if not available:
            return "NEUTRAL"
        rsi = self.benchmark_rsi[max(available)]
        if rsi >= Decimal(str(self.market_regime_strong_rsi)):
            return "STRONG"
        return "NEUTRAL"

    def set_signal_exit_config(self, config: Dict[str, dict]):
        """Set per-signal exit parameters for trend-following signals.

        P6: Trend signals (Donchian Breakout, Golden Cross, MACD Golden Cross) need
        wider stops and longer holding to capture multi-week price moves.

        config format:
          {
            "Donchian Breakout": {
                "stop_loss_pct": Decimal("0.10"),
                "trailing_stop_pct": Decimal("0.08"),
                "take_profit_pct": Decimal("0.40"),
                "max_holding_days": 60,
            },
            ...
          }
        """
        self.signal_exit_config = config

    def set_momentum_whitelist(self, whitelist: Dict[date, Set[str]]):
        """Set the daily momentum whitelist for BUY signal filtering.

        Only symbols present in the whitelist for a given date will be allowed
        to generate BUY orders. Pass an empty dict to disable filtering.
        """
        self.momentum_whitelist = whitelist

    def set_sector_whitelist(self, whitelist: Dict[date, Set[str]]):
        """Set the daily sector-trend whitelist for BUY signal filtering.

        Only symbols that belong to a strong sector on a given date will be
        allowed to generate BUY orders.  Pass an empty dict to disable.
        """
        self.sector_whitelist = whitelist

    def _get_momentum_allowed(self, target_date: date) -> Optional[Set[str]]:
        """Return the allowed symbol set for the most recent whitelist date."""
        if not self.momentum_whitelist:
            return None
        available = [d for d in self.momentum_whitelist if d <= target_date]
        if not available:
            return None
        return self.momentum_whitelist[max(available)]

    def _get_sector_allowed(self, target_date: date) -> Optional[Set[str]]:
        """Return the sector-allowed symbol set for the most recent whitelist date."""
        if not self.sector_whitelist:
            return None
        available = [d for d in self.sector_whitelist if d <= target_date]
        if not available:
            return None
        return self.sector_whitelist[max(available)]

    def process_signals(self, signals: List[TradingSignal], market_bullish: bool = True):
        """Process a list of trading signals for the current date.

        BUY signals are suppressed when:
        - market_bullish is False (TAIEX fails regime checks, i.e. WEAK regime), OR
        - P3-C: signal name is not in the allowed list for the current regime, OR
        - momentum_whitelist is set and the symbol is not in top-N momentum stocks.

        P3-C regime routing (when benchmark RSI data available):
          STRONG (RSI >= market_regime_strong_rsi): strong_regime_signals allowed (None = all)
          NEUTRAL (RSI < market_regime_strong_rsi): neutral_regime_signals allowed (None = all)
          WEAK (market_bullish=False): no buys
        """
        momentum_allowed = self._get_momentum_allowed(self.current_date)
        sector_allowed = self._get_sector_allowed(self.current_date)
        regime = self.get_market_regime(self.current_date) if market_bullish else "WEAK"

        for signal in signals:
            if signal.date != self.current_date:
                continue

            if signal.signal_type == SignalType.BUY:
                if regime == "WEAK":
                    self.logger.debug(
                        f"Skipping BUY {signal.symbol}: WEAK market regime"
                    )
                    continue
                # P3-C: regime-based signal routing
                if regime == "STRONG" and self.strong_regime_signals is not None:
                    if signal.signal_name not in self.strong_regime_signals:
                        self.logger.debug(
                            f"Skipping BUY {signal.symbol}/{signal.signal_name}: "
                            f"not in STRONG regime signals"
                        )
                        continue
                elif regime == "NEUTRAL" and self.neutral_regime_signals is not None:
                    if signal.signal_name not in self.neutral_regime_signals:
                        self.logger.debug(
                            f"Skipping BUY {signal.symbol}/{signal.signal_name}: "
                            f"not in NEUTRAL regime signals"
                        )
                        continue
                if momentum_allowed is not None and signal.symbol not in momentum_allowed:
                    self.logger.debug(
                        f"Skipping BUY {signal.symbol}: not in top-N momentum"
                    )
                    continue
                if sector_allowed is not None and signal.symbol not in sector_allowed:
                    self.logger.debug(
                        f"Skipping BUY {signal.symbol}: sector not strong enough"
                    )
                    continue
                # P5: apply trend signal multiplier in STRONG regime
                sizing_override = None
                if (
                    regime == "STRONG"
                    and self.strong_trend_signals is not None
                    and signal.signal_name in self.strong_trend_signals
                    and self.strong_trend_multiplier != 1.0
                ):
                    sizing_override = self.position_sizing * Decimal(str(self.strong_trend_multiplier))
                self.execute_buy_order(signal, sizing_override=sizing_override)
            elif signal.signal_type == SignalType.SELL and signal.symbol in self.positions:
                position = self.positions[signal.symbol]
                # P3-B: signal-based exit for trend positions
                # If position specifies exit_on_signals, only exit on matching signals.
                # Otherwise (mean-reversion positions), exit on any sell signal.
                if position.exit_on_signals is not None:
                    should_exit = signal.signal_name in position.exit_on_signals
                else:
                    should_exit = True
                if should_exit:
                    current_price = self.get_current_price(signal.symbol, self.current_date)
                    if current_price:
                        self.execute_sell_order(
                            signal.symbol, current_price,
                            f"Signal Exit: {signal.signal_name}"
                        )

    def run_backtest(
        self,
        signals: List[TradingSignal],
        start_date: date,
        end_date: date,
        benchmark_data: Optional[List[StockData]] = None,
        market_regime_rsi_threshold: float = 45.0,
        market_regime_check_ma5: bool = True,
    ) -> BacktestResult:
        """
        Run complete backtest

        Args:
            signals: List of trading signals
            start_date: Backtest start date
            end_date: Backtest end date
            benchmark_data: Optional TAIEX data for market regime filter
            market_regime_rsi_threshold: TAIEX RSI(14) must be >= this value
            market_regime_check_ma5: Also require TAIEX MA5 >= MA20

        Returns:
            BacktestResult object with performance metrics
        """
        self.logger.info(f"Starting backtest from {start_date} to {end_date}")

        # Build enhanced market regime filter if benchmark data provided
        if benchmark_data:
            self.build_benchmark_filter(
                benchmark_data,
                rsi_threshold=market_regime_rsi_threshold,
                check_ma5=market_regime_check_ma5,
            )
            self.logger.info(
                f"Market regime filter enabled "
                f"(MA5>MA20: {market_regime_check_ma5}, RSI>={market_regime_rsi_threshold})"
            )

        # Group signals by date
        signals_by_date: Dict[date, List[TradingSignal]] = {}
        for signal in signals:
            if signal.date not in signals_by_date:
                signals_by_date[signal.date] = []
            signals_by_date[signal.date].append(signal)

        # Run day by day
        current = start_date
        while current <= end_date:
            self.current_date = current

            # Check position exits first
            self.check_position_exits()

            # Process new signals (suppress BUY when TAIEX below MA20)
            if current in signals_by_date:
                market_bullish = self.is_market_bullish(current)
                self.process_signals(signals_by_date[current], market_bullish)

            # Update portfolio
            self.update_portfolio()

            current += timedelta(days=1)

        # Close all remaining positions at end date
        for symbol in list(self.positions.keys()):
            current_price = self.get_current_price(symbol, end_date)
            if current_price:
                self.execute_sell_order(symbol, current_price, "Backtest End")

        # Calculate final results
        result = self.calculate_results(start_date, end_date)
        self.logger.info(f"Backtest completed. Final capital: {result.final_capital} ({result.total_return_pct}%)")

        return result

    def calculate_results(self, start_date: date, end_date: date) -> BacktestResult:
        """Calculate comprehensive backtest results"""
        final_capital = self.portfolio_history[-1].total_value if self.portfolio_history else self.cash

        # Basic returns
        total_return = final_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital * Decimal('100')).quantize(Decimal('0.01'))

        # Annualized return
        days = (end_date - start_date).days
        years = Decimal(days) / Decimal('365')
        annualized_return = (((final_capital / self.initial_capital) ** (Decimal('1') / years) - Decimal('1')) * Decimal('100')).quantize(Decimal('0.01')) if years > 0 else Decimal('0')

        # Trade statistics
        total_trades = len(self.closed_positions)
        winning_trades = len([p for p in self.closed_positions if (p.pnl or Decimal('0')) > 0])
        losing_trades = total_trades - winning_trades

        win_rate = (Decimal(winning_trades) / Decimal(total_trades) * Decimal('100')).quantize(Decimal('0.01')) if total_trades > 0 else Decimal('0')

        # Profit/Loss statistics
        wins = [p.pnl for p in self.closed_positions if (p.pnl or Decimal('0')) > 0]
        losses = [p.pnl for p in self.closed_positions if (p.pnl or Decimal('0')) < 0]

        avg_win = (sum(wins) / len(wins)).quantize(Decimal('0.01')) if wins else Decimal('0')
        avg_loss = (sum(losses) / len(losses)).quantize(Decimal('0.01')) if losses else Decimal('0')
        largest_win = max(wins) if wins else Decimal('0')
        largest_loss = min(losses) if losses else Decimal('0')

        profit_factor = (sum(wins) / abs(sum(losses))).quantize(Decimal('0.01')) if losses and sum(losses) != 0 else Decimal('0')

        # Drawdown calculation
        max_drawdown = self.calculate_max_drawdown()

        # Sharpe ratio (simplified - using daily returns)
        sharpe_ratio = self.calculate_sharpe_ratio()

        # Average holding period
        holding_periods = [p.holding_days or 0 for p in self.closed_positions]
        avg_holding_period = Decimal(sum(holding_periods) / len(holding_periods)).quantize(Decimal('0.1')) if holding_periods else Decimal('0')

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            annualized_return=annualized_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period=avg_holding_period,
            trades=self.closed_positions,
            portfolio_history=self.portfolio_history
        )

    def calculate_max_drawdown(self) -> Decimal:
        """Calculate maximum drawdown from portfolio history"""
        if len(self.portfolio_history) < 2:
            return Decimal('0')

        peak = self.portfolio_history[0].total_value
        max_dd = Decimal('0')

        for portfolio in self.portfolio_history[1:]:
            if portfolio.total_value > peak:
                peak = portfolio.total_value
            else:
                drawdown = (peak - portfolio.total_value) / peak * Decimal('100')
                max_dd = max(max_dd, drawdown)

        return max_dd.quantize(Decimal('0.01'))

    def calculate_sharpe_ratio(self) -> Decimal:
        """Calculate simplified Sharpe ratio"""
        if len(self.portfolio_history) < 2:
            return Decimal('0')

        returns = []
        for i in range(1, len(self.portfolio_history)):
            prev_value = self.portfolio_history[i-1].total_value
            curr_value = self.portfolio_history[i].total_value
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(float(daily_return))

        if not returns or len(returns) < 2:
            return Decimal('0')

        import numpy as np
        returns_array = np.array(returns)
        avg_return = np.mean(returns_array)
        std_return = np.std(returns_array)

        if std_return == 0:
            return Decimal('0')

        # Annualized Sharpe (assuming 252 trading days)
        sharpe = (avg_return / std_return) * np.sqrt(252)
        return Decimal(str(sharpe)).quantize(Decimal('0.01'))