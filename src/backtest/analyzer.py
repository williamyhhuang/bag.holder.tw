"""
Performance analyzer for backtesting results
"""
import pandas as pd
from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import csv
import os

from .models import BacktestResult, Position, Portfolio, StockData
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceAnalyzer:
    """Analyze and compare backtesting performance"""

    def __init__(self, output_dir: str = "data"):
        self.output_dir = output_dir
        self.logger = get_logger(self.__class__.__name__)

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

    def analyze_trades(self, trades: List[Position]) -> Dict:
        """
        Analyze individual trade performance

        Args:
            trades: List of closed positions

        Returns:
            Dictionary with trade analysis
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'break_even_trades': 0,
                'win_rate': Decimal('0'),
                'avg_win_amount': Decimal('0'),
                'avg_loss_amount': Decimal('0'),
                'avg_win_percent': Decimal('0'),
                'avg_loss_percent': Decimal('0'),
                'best_trade': None,
                'worst_trade': None,
                'avg_holding_period': Decimal('0'),
                'profit_factor': Decimal('0'),
                'trades_by_month': {},
                'trades_by_symbol': {}
            }

        total_trades = len(trades)
        winning_trades = [t for t in trades if (t.pnl or Decimal('0')) > 0]
        losing_trades = [t for t in trades if (t.pnl or Decimal('0')) < 0]
        break_even_trades = [t for t in trades if (t.pnl or Decimal('0')) == 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        break_even_count = len(break_even_trades)

        # Basic statistics
        win_rate = (Decimal(win_count) / Decimal(total_trades) * Decimal('100')).quantize(Decimal('0.01'))

        # Average amounts
        avg_win_amount = (sum(t.pnl or Decimal('0') for t in winning_trades) / Decimal(win_count)).quantize(Decimal('0.01')) if win_count > 0 else Decimal('0')
        avg_loss_amount = (sum(t.pnl or Decimal('0') for t in losing_trades) / Decimal(loss_count)).quantize(Decimal('0.01')) if loss_count > 0 else Decimal('0')

        # Average percentages
        avg_win_percent = (sum(t.pnl_percent or Decimal('0') for t in winning_trades) / Decimal(win_count)).quantize(Decimal('0.01')) if win_count > 0 else Decimal('0')
        avg_loss_percent = (sum(t.pnl_percent or Decimal('0') for t in losing_trades) / Decimal(loss_count)).quantize(Decimal('0.01')) if loss_count > 0 else Decimal('0')

        # Best and worst trades
        best_trade = max(trades, key=lambda t: t.pnl or Decimal('0'))
        worst_trade = min(trades, key=lambda t: t.pnl or Decimal('0'))

        # Average holding period
        holding_periods = [t.holding_days or 0 for t in trades]
        avg_holding_period = Decimal(sum(holding_periods) / len(holding_periods)).quantize(Decimal('0.1'))

        # Profit factor
        total_wins = sum(t.pnl or Decimal('0') for t in winning_trades)
        total_losses = abs(sum(t.pnl or Decimal('0') for t in losing_trades))
        profit_factor = (total_wins / total_losses).quantize(Decimal('0.01')) if total_losses > 0 else Decimal('0')

        # Trades by month
        trades_by_month = {}
        for trade in trades:
            if trade.entry_date:
                month_key = trade.entry_date.strftime('%Y-%m')
                if month_key not in trades_by_month:
                    trades_by_month[month_key] = {'count': 0, 'pnl': Decimal('0')}
                trades_by_month[month_key]['count'] += 1
                trades_by_month[month_key]['pnl'] += trade.pnl or Decimal('0')

        # Trades by symbol
        trades_by_symbol = {}
        for trade in trades:
            symbol = trade.symbol
            if symbol not in trades_by_symbol:
                trades_by_symbol[symbol] = {'count': 0, 'pnl': Decimal('0'), 'win_rate': Decimal('0')}
            trades_by_symbol[symbol]['count'] += 1
            trades_by_symbol[symbol]['pnl'] += trade.pnl or Decimal('0')

        # Calculate win rate by symbol
        for symbol in trades_by_symbol:
            symbol_trades = [t for t in trades if t.symbol == symbol]
            symbol_wins = len([t for t in symbol_trades if (t.pnl or Decimal('0')) > 0])
            trades_by_symbol[symbol]['win_rate'] = (Decimal(symbol_wins) / Decimal(len(symbol_trades)) * Decimal('100')).quantize(Decimal('0.01'))

        return {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'break_even_trades': break_even_count,
            'win_rate': win_rate,
            'avg_win_amount': avg_win_amount,
            'avg_loss_amount': avg_loss_amount,
            'avg_win_percent': avg_win_percent,
            'avg_loss_percent': avg_loss_percent,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_holding_period': avg_holding_period,
            'profit_factor': profit_factor,
            'trades_by_month': trades_by_month,
            'trades_by_symbol': trades_by_symbol
        }

    def calculate_benchmark_comparison(
        self,
        portfolio_history: List[Portfolio],
        benchmark_data: List[StockData]
    ) -> Dict:
        """
        Compare strategy performance against benchmark

        Args:
            portfolio_history: Strategy portfolio history
            benchmark_data: Benchmark price data

        Returns:
            Dictionary with comparison metrics
        """
        if not portfolio_history or not benchmark_data:
            return {}

        try:
            # Create benchmark lookup
            benchmark_lookup = {data.date: data.close_price for data in benchmark_data}

            # Calculate returns
            strategy_returns = []
            benchmark_returns = []

            for i in range(1, len(portfolio_history)):
                prev_portfolio = portfolio_history[i-1]
                curr_portfolio = portfolio_history[i]

                # Strategy return
                strategy_return = (curr_portfolio.total_value - prev_portfolio.total_value) / prev_portfolio.total_value
                strategy_returns.append(float(strategy_return))

                # Benchmark return
                if curr_portfolio.date in benchmark_lookup and prev_portfolio.date in benchmark_lookup:
                    prev_bench = benchmark_lookup[prev_portfolio.date]
                    curr_bench = benchmark_lookup[curr_portfolio.date]
                    benchmark_return = (curr_bench - prev_bench) / prev_bench
                    benchmark_returns.append(float(benchmark_return))
                else:
                    benchmark_returns.append(0.0)

            if not strategy_returns or not benchmark_returns:
                return {}

            # Calculate performance metrics
            import numpy as np

            strategy_total = portfolio_history[-1].total_value / portfolio_history[0].total_value - 1
            benchmark_total = benchmark_data[-1].close_price / benchmark_data[0].close_price - 1

            strategy_volatility = np.std(strategy_returns) * np.sqrt(252) if len(strategy_returns) > 1 else 0
            benchmark_volatility = np.std(benchmark_returns) * np.sqrt(252) if len(benchmark_returns) > 1 else 0

            # Alpha and Beta calculation (simplified)
            if benchmark_volatility > 0:
                correlation = np.corrcoef(strategy_returns, benchmark_returns)[0, 1] if len(strategy_returns) > 1 else 0
                beta = correlation * (strategy_volatility / benchmark_volatility) if benchmark_volatility > 0 else 0
                alpha = float(strategy_total) - beta * float(benchmark_total)
            else:
                beta = 0
                alpha = float(strategy_total)

            return {
                'strategy_total_return': Decimal(str(strategy_total * 100)).quantize(Decimal('0.01')),
                'benchmark_total_return': Decimal(str(benchmark_total * 100)).quantize(Decimal('0.01')),
                'excess_return': Decimal(str((strategy_total - benchmark_total) * 100)).quantize(Decimal('0.01')),
                'strategy_volatility': Decimal(str(strategy_volatility * 100)).quantize(Decimal('0.01')),
                'benchmark_volatility': Decimal(str(benchmark_volatility * 100)).quantize(Decimal('0.01')),
                'alpha': Decimal(str(alpha * 100)).quantize(Decimal('0.01')),
                'beta': Decimal(str(beta)).quantize(Decimal('0.01')),
                'correlation': Decimal(str(correlation)).quantize(Decimal('0.01')) if 'correlation' in locals() else Decimal('0')
            }

        except Exception as e:
            self.logger.error(f"Error calculating benchmark comparison: {e}")
            return {}

    def calculate_risk_metrics(self, portfolio_history: List[Portfolio]) -> Dict:
        """
        Calculate risk metrics

        Args:
            portfolio_history: Strategy portfolio history

        Returns:
            Dictionary with risk metrics
        """
        if len(portfolio_history) < 2:
            return {}

        try:
            # Calculate returns
            returns = []
            for i in range(1, len(portfolio_history)):
                prev_value = portfolio_history[i-1].total_value
                curr_value = portfolio_history[i].total_value
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(float(daily_return))

            if not returns:
                return {}

            import numpy as np

            returns_array = np.array(returns)

            # Basic statistics
            avg_return = np.mean(returns_array)
            std_return = np.std(returns_array)
            min_return = np.min(returns_array)
            max_return = np.max(returns_array)

            # Value at Risk (95%)
            var_95 = np.percentile(returns_array, 5)

            # Conditional Value at Risk (Expected Shortfall)
            cvar_95 = np.mean(returns_array[returns_array <= var_95]) if np.any(returns_array <= var_95) else var_95

            # Sortino Ratio (downside deviation)
            negative_returns = returns_array[returns_array < 0]
            downside_deviation = np.std(negative_returns) if len(negative_returns) > 0 else 0
            sortino_ratio = (avg_return / downside_deviation * np.sqrt(252)) if downside_deviation > 0 else 0

            # Calmar Ratio (return / max drawdown)
            max_drawdown = self.calculate_max_drawdown_detailed(portfolio_history)['max_drawdown']
            calmar_ratio = (avg_return * 252 / (float(max_drawdown) / 100)) if max_drawdown > 0 else 0

            return {
                'avg_daily_return': Decimal(str(avg_return * 100)).quantize(Decimal('0.01')),
                'daily_volatility': Decimal(str(std_return * 100)).quantize(Decimal('0.01')),
                'annualized_volatility': Decimal(str(std_return * np.sqrt(252) * 100)).quantize(Decimal('0.01')),
                'best_day': Decimal(str(max_return * 100)).quantize(Decimal('0.01')),
                'worst_day': Decimal(str(min_return * 100)).quantize(Decimal('0.01')),
                'var_95': Decimal(str(var_95 * 100)).quantize(Decimal('0.01')),
                'cvar_95': Decimal(str(cvar_95 * 100)).quantize(Decimal('0.01')),
                'sortino_ratio': Decimal(str(sortino_ratio)).quantize(Decimal('0.01')),
                'calmar_ratio': Decimal(str(calmar_ratio)).quantize(Decimal('0.01'))
            }

        except Exception as e:
            self.logger.error(f"Error calculating risk metrics: {e}")
            return {}

    def calculate_max_drawdown_detailed(self, portfolio_history: List[Portfolio]) -> Dict:
        """
        Calculate detailed max drawdown analysis

        Args:
            portfolio_history: Strategy portfolio history

        Returns:
            Dictionary with drawdown details
        """
        if len(portfolio_history) < 2:
            return {'max_drawdown': Decimal('0'), 'drawdown_duration': 0, 'recovery_date': None}

        peak = portfolio_history[0].total_value
        max_dd = Decimal('0')
        max_dd_start = None
        max_dd_end = None
        current_dd_start = None

        for portfolio in portfolio_history[1:]:
            if portfolio.total_value > peak:
                peak = portfolio.total_value
                current_dd_start = None
            else:
                if current_dd_start is None:
                    current_dd_start = portfolio.date

                drawdown = (peak - portfolio.total_value) / peak * Decimal('100')
                if drawdown > max_dd:
                    max_dd = drawdown
                    max_dd_start = current_dd_start
                    max_dd_end = portfolio.date

        # Calculate drawdown duration
        drawdown_duration = 0
        if max_dd_start and max_dd_end:
            drawdown_duration = (max_dd_end - max_dd_start).days

        return {
            'max_drawdown': max_dd.quantize(Decimal('0.01')),
            'drawdown_start': max_dd_start,
            'drawdown_end': max_dd_end,
            'drawdown_duration': drawdown_duration
        }

    def export_trades_to_csv(self, trades: List[Position], filename: str = None) -> str:
        """
        Export trade details to CSV

        Args:
            trades: List of closed positions
            filename: Output filename

        Returns:
            Path to exported file
        """
        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backtest_trades_{timestamp}.csv"

        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow([
                    'Symbol', 'Entry Date', 'Exit Date', 'Entry Price', 'Exit Price',
                    'Quantity', 'PnL', 'PnL %', 'Holding Days', 'Stop Loss', 'Take Profit'
                ])

                # Write trade data
                for trade in trades:
                    writer.writerow([
                        trade.symbol,
                        trade.entry_date.strftime('%Y-%m-%d') if trade.entry_date else '',
                        trade.exit_date.strftime('%Y-%m-%d') if trade.exit_date else '',
                        str(trade.entry_price),
                        str(trade.exit_price) if trade.exit_price else '',
                        trade.quantity,
                        str(trade.pnl) if trade.pnl else '',
                        str(trade.pnl_percent) if trade.pnl_percent else '',
                        trade.holding_days or '',
                        str(trade.stop_loss) if trade.stop_loss else '',
                        str(trade.take_profit) if trade.take_profit else ''
                    ])

            self.logger.info(f"Exported {len(trades)} trades to {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error exporting trades to CSV: {e}")
            raise

    def export_portfolio_to_csv(self, portfolio_history: List[Portfolio], filename: str = None) -> str:
        """
        Export portfolio history to CSV

        Args:
            portfolio_history: Portfolio history
            filename: Output filename

        Returns:
            Path to exported file
        """
        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"portfolio_history_{timestamp}.csv"

        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow([
                    'Date', 'Cash', 'Total Value', 'Realized PnL', 'Unrealized PnL',
                    'Total PnL', 'Positions Count'
                ])

                # Write portfolio data
                for portfolio in portfolio_history:
                    writer.writerow([
                        portfolio.date.strftime('%Y-%m-%d'),
                        str(portfolio.cash),
                        str(portfolio.total_value),
                        str(portfolio.realized_pnl),
                        str(portfolio.unrealized_pnl),
                        str(portfolio.total_pnl),
                        len(portfolio.positions)
                    ])

            self.logger.info(f"Exported {len(portfolio_history)} portfolio records to {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error exporting portfolio to CSV: {e}")
            raise

    def generate_performance_summary(self, result: BacktestResult) -> Dict:
        """
        Generate comprehensive performance summary

        Args:
            result: Backtest result

        Returns:
            Dictionary with performance summary
        """
        summary = {
            'backtest_period': {
                'start_date': result.start_date,
                'end_date': result.end_date,
                'duration_days': (result.end_date - result.start_date).days
            },
            'capital': {
                'initial': result.initial_capital,
                'final': result.final_capital,
                'total_return': result.total_return,
                'total_return_pct': result.total_return_pct,
                'annualized_return': result.annualized_return
            },
            'risk_metrics': {
                'max_drawdown': result.max_drawdown,
                'sharpe_ratio': result.sharpe_ratio
            },
            'trade_statistics': {
                'total_trades': result.total_trades,
                'winning_trades': result.winning_trades,
                'losing_trades': result.losing_trades,
                'win_rate': result.win_rate,
                'profit_factor': result.profit_factor,
                'avg_win': result.avg_win,
                'avg_loss': result.avg_loss,
                'largest_win': result.largest_win,
                'largest_loss': result.largest_loss,
                'avg_holding_period': result.avg_holding_period
            }
        }

        # Add detailed trade analysis
        trade_analysis = self.analyze_trades(result.trades)
        summary['detailed_trade_analysis'] = trade_analysis

        # Add risk analysis
        risk_analysis = self.calculate_risk_metrics(result.portfolio_history)
        summary['detailed_risk_analysis'] = risk_analysis

        return summary