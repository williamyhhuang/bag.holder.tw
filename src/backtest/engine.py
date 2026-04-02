"""
Backtesting engine with portfolio management and performance calculation
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple
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
        stop_loss_pct: Decimal = Decimal('0.05'),  # 5% stop loss (tightened from 10%)
        take_profit_pct: Decimal = Decimal('0.2'),  # 20% take profit
        max_holding_days: int = 30,
        trailing_stop_pct: Optional[Decimal] = Decimal('0.05'),  # 5% trailing stop from peak
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.tax_rate = tax_rate
        self.position_sizing = position_sizing
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_holding_days = max_holding_days
        self.trailing_stop_pct = trailing_stop_pct
        self.benchmark_bullish: Dict[date, bool] = {}  # date -> True if TAIEX >= MA20

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

    def execute_buy_order(self, signal: TradingSignal) -> bool:
        """
        Execute a buy order based on trading signal

        Args:
            signal: Trading signal

        Returns:
            True if order executed successfully
        """
        try:
            # Check if we already have a position in this stock
            if signal.symbol in self.positions:
                self.logger.debug(f"Already holding position in {signal.symbol}")
                return False

            # Calculate position size
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

            # Create position
            position = Position(
                symbol=signal.symbol,
                quantity=quantity,
                entry_price=signal.price,
                entry_date=signal.date,
                current_price=signal.price,
                current_date=signal.date,
                status=PositionStatus.OPEN,
                stop_loss=signal.price * (Decimal('1') - self.stop_loss_pct),
                take_profit=signal.price * (Decimal('1') + self.take_profit_pct),
                entry_signal_name=signal.signal_name,
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
            if self.trailing_stop_pct and current_price > position.entry_price:
                new_trailing_stop = (
                    current_price * (Decimal('1') - self.trailing_stop_pct)
                ).quantize(Decimal('0.01'))
                if new_trailing_stop > (position.stop_loss or Decimal('0')):
                    position.stop_loss = new_trailing_stop

            # Check stop loss
            if current_price <= position.stop_loss:
                positions_to_close.append((symbol, current_price, "Stop Loss"))

            # Check take profit
            elif current_price >= position.take_profit:
                positions_to_close.append((symbol, current_price, "Take Profit"))

            # Check max holding period
            elif (self.current_date - position.entry_date).days >= self.max_holding_days:
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

    def build_benchmark_filter(self, benchmark_data: List[StockData], ma_period: int = 20):
        """Pre-compute whether each benchmark date is bullish (close >= MA).

        Result stored in self.benchmark_bullish so run_backtest can do O(1) lookups.
        """
        if not benchmark_data:
            return
        prices = sorted(benchmark_data, key=lambda x: x.date)
        for i in range(len(prices)):
            if i < ma_period - 1:
                continue
            window = [prices[j].close_price for j in range(i - ma_period + 1, i + 1)]
            ma = sum(window) / Decimal(str(ma_period))
            self.benchmark_bullish[prices[i].date] = prices[i].close_price >= ma

    def is_market_bullish(self, target_date: date) -> bool:
        """Return True if TAIEX is above its 20-day MA on or before target_date.

        Falls back to True (no filter) when benchmark data is unavailable.
        """
        if not self.benchmark_bullish:
            return True
        available = [d for d in self.benchmark_bullish if d <= target_date]
        if not available:
            return True
        return self.benchmark_bullish[max(available)]

    def process_signals(self, signals: List[TradingSignal], market_bullish: bool = True):
        """Process a list of trading signals for the current date.

        BUY signals are suppressed when market_bullish is False (TAIEX below MA20).
        """
        for signal in signals:
            if signal.date != self.current_date:
                continue

            if signal.signal_type == SignalType.BUY:
                if not market_bullish:
                    self.logger.debug(
                        f"Skipping BUY {signal.symbol}: market below MA20"
                    )
                    continue
                self.execute_buy_order(signal)
            elif signal.signal_type == SignalType.SELL and signal.symbol in self.positions:
                current_price = self.get_current_price(signal.symbol, self.current_date)
                if current_price:
                    self.execute_sell_order(signal.symbol, current_price, "Sell Signal")

    def run_backtest(
        self,
        signals: List[TradingSignal],
        start_date: date,
        end_date: date,
        benchmark_data: Optional[List[StockData]] = None,
    ) -> BacktestResult:
        """
        Run complete backtest

        Args:
            signals: List of trading signals
            start_date: Backtest start date
            end_date: Backtest end date
            benchmark_data: Optional TAIEX data for market MA20 filter

        Returns:
            BacktestResult object with performance metrics
        """
        self.logger.info(f"Starting backtest from {start_date} to {end_date}")

        # Build benchmark MA20 filter if data provided
        if benchmark_data:
            self.build_benchmark_filter(benchmark_data)
            self.logger.info("Benchmark MA20 filter enabled")

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