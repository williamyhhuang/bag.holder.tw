"""
Main backtesting execution script
"""
import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.backtest import (
    YFinanceDataSource,
    BacktestEngine,
    TechnicalStrategy,
    PerformanceAnalyzer,
    BacktestReporter
)
from src.data_downloader.yfinance_client import YFinanceClient
from src.utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class BacktestRunner:
    """Main backtest runner"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.data_source = YFinanceDataSource()
        self.yf_client = YFinanceClient()
        # 從 BacktestSettings 讀取策略參數，與 strategy.py TechnicalStrategy 完全對齊
        cfg = settings.backtest
        disabled = [s.strip() for s in cfg.disabled_signals.split(",") if s.strip()]
        self.strategy = TechnicalStrategy(
            rsi_min_entry=cfg.rsi_min_entry,
            disabled_signals=disabled,
            require_ma60_uptrend=cfg.require_ma60_uptrend,
            require_volume_confirmation=cfg.require_volume_confirmation,
            volume_confirmation_multiplier=cfg.volume_confirmation_multiplier,
            rsi_overbought_threshold=cfg.rsi_overbought_threshold,
        )
        self.engine = BacktestEngine(
            stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
            take_profit_pct=Decimal(str(cfg.take_profit_pct)),
            trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
            max_holding_days=cfg.max_holding_days,
            position_sizing=Decimal(str(cfg.position_sizing)),
        )
        self.analyzer = PerformanceAnalyzer()
        self.reporter = BacktestReporter()

    def _coverage_ratio(self, stock_data: dict, required_start: date, required_end: date) -> float:
        """
        Return the fraction of loaded symbols that have enough records to cover
        [required_start, required_end].  A symbol is considered covered when its
        earliest record is on or before required_start.
        """
        if not stock_data:
            return 0.0
        covered = sum(
            1 for records in stock_data.values()
            if records and records[0].date <= required_start
        )
        return covered / len(stock_data)

    def _download_history(self, stocks_dir: str, needed_start: date, needed_end: date):
        """Download historical data for all stocks and save to stocks_dir."""
        self.logger.info(
            f"Local data does not cover {needed_start} – {needed_end}. "
            "Downloading historical data via yfinance…"
        )
        self.yf_client.download_all_stocks(
            start_date=datetime.combine(needed_start, datetime.min.time()),
            end_date=datetime.combine(needed_end, datetime.min.time()),
        )

    async def run_full_backtest(
        self,
        start_date: date = None,
        end_date: date = None,
        initial_capital: Decimal = Decimal('1000000')
    ):
        """
        Run complete backtesting process

        Args:
            start_date: Backtest start date (overrides config; defaults to BACKTEST_START_DATE)
            end_date: Backtest end date (overrides config; defaults to BACKTEST_END_DATE or today)
            initial_capital: Initial capital
        """
        cfg = settings.backtest
        if start_date is None:
            start_date = cfg.start_date or date(2024, 9, 1)
        if end_date is None:
            end_date = cfg.end_date or date.today()

        self.logger.info(f"Starting full backtest from {start_date} to {end_date}")

        try:
            # Step 1: Load historical data (prefer local files, fall back to yfinance)
            self.logger.info("Step 1: Loading historical data...")
            stocks_dir = os.path.join(os.path.dirname(__file__), '../../data/stocks')
            stocks_dir = os.path.normpath(stocks_dir)

            if os.path.isdir(stocks_dir) and os.listdir(stocks_dir):
                self.logger.info(f"Loading local data from {stocks_dir} ...")
                needed_start = start_date - timedelta(days=100)
                # Load extra history for indicator warm-up
                stock_data = self.data_source.load_from_stocks_dir(
                    stocks_dir=stocks_dir,
                    start_date=needed_start,
                    end_date=end_date
                )
                if not stock_data:
                    raise Exception(f"No stock data found in {stocks_dir}")

                # If local data doesn't cover the required period, download history
                coverage = self._coverage_ratio(stock_data, needed_start, end_date)
                if coverage < 0.1:  # < 10 % of symbols have enough history
                    self._download_history(stocks_dir, needed_start, end_date)
                    # Reload after download
                    stock_data = self.data_source.load_from_stocks_dir(
                        stocks_dir=stocks_dir,
                        start_date=needed_start,
                        end_date=end_date
                    )
                    if not stock_data:
                        raise Exception("No stock data after historical download")
            else:
                self.logger.info("Local data not found – fetching from yfinance...")
                stock_symbols = self.data_source.get_taiwan_stock_list()
                stock_data = self.data_source.fetch_multiple_stocks(
                    symbols=stock_symbols,
                    start_date=start_date - timedelta(days=100),
                    end_date=end_date,
                    delay=1.0
                )
                if not stock_data:
                    raise Exception("No stock data fetched")
                data_file = self.data_source.save_to_csv(stock_data)
                self.logger.info(f"Historical data saved to: {data_file}")

            # Step 2: Apply industry exclusion filter (依 config/settings.py backtest 設定)
            excluded_symbols = settings.backtest.load_excluded_symbols(
                project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), '../..')))
            )
            if excluded_symbols:
                before = len(stock_data)
                stock_data = {
                    sym: data for sym, data in stock_data.items()
                    if sym not in excluded_symbols
                }
                removed = before - len(stock_data)
                self.logger.info(
                    f"Industry filter: removed {removed} stocks "
                    f"(excluded industry codes: {settings.backtest.exclude_industry_codes}). "
                    f"Remaining: {len(stock_data)} stocks."
                )
            else:
                self.logger.info("No industry exclusion configured.")

            # Step 3: Generate trading signals
            self.logger.info("Step 3: Generating trading signals...")
            signals = self.strategy.generate_signals_for_multiple_stocks(
                stock_data_dict=stock_data,
                start_date=start_date,
                end_date=end_date
            )

            self.logger.info(f"Generated {len(signals)} trading signals")

            # Get signal summary
            signal_summary = self.strategy.get_signal_summary(signals)
            self.logger.info(f"Signal summary: {signal_summary}")

            # Step 4: Prepare backtest engine
            self.logger.info("Step 4: Setting up backtest engine...")
            cfg = settings.backtest
            # P3-C: parse regime signal lists (empty string → None = all allowed)
            def _parse_signals(s: str):
                items = [x.strip() for x in s.split(",") if x.strip()]
                return items if items else None

            self.engine = BacktestEngine(
                initial_capital=initial_capital,
                stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
                take_profit_pct=Decimal(str(cfg.take_profit_pct)),
                trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
                max_holding_days=cfg.max_holding_days,
                position_sizing=Decimal(str(cfg.position_sizing)),
                market_regime_strong_rsi=cfg.market_regime_strong_rsi,
                strong_regime_signals=_parse_signals(cfg.strong_regime_signals),
                neutral_regime_signals=_parse_signals(cfg.neutral_regime_signals),
                strong_trend_signals=_parse_signals(cfg.strong_trend_signals),
                strong_trend_multiplier=cfg.strong_trend_multiplier,
            )

            # Add price data to engine
            for symbol, data in stock_data.items():
                self.engine.add_price_data(symbol, data)

            # Step 5: Fetch benchmark data (needed before backtest for MA20 market filter)
            self.logger.info("Step 5: Fetching benchmark data for market filter...")
            benchmark_data = self.data_source.get_market_index_data(start_date, end_date)

            # Step 5b: Build momentum rankings (Direction 4)
            if cfg.momentum_top_n > 0:
                self.logger.info(
                    f"Step 5b: Building momentum rankings "
                    f"(top_n={cfg.momentum_top_n}, lookback={cfg.momentum_lookback_days}d)..."
                )
                momentum_whitelist = self.strategy.build_momentum_rankings(
                    stock_data_dict=stock_data,
                    lookback_days=cfg.momentum_lookback_days,
                    top_n=cfg.momentum_top_n,
                    start_date=start_date,
                    end_date=end_date,
                )
                self.engine.set_momentum_whitelist(momentum_whitelist)
                self.logger.info(
                    f"Momentum whitelist set for {len(momentum_whitelist)} trading dates"
                )
            else:
                self.logger.info("Step 5b: Momentum ranking disabled (momentum_top_n=0)")

            # Step 6: Run backtest (pass benchmark for enhanced market regime filter)
            self.logger.info("Step 6: Running backtest...")
            result = self.engine.run_backtest(
                signals,
                start_date,
                end_date,
                benchmark_data=benchmark_data,
                market_regime_rsi_threshold=cfg.market_regime_rsi_threshold,
                market_regime_check_ma5=cfg.market_regime_check_ma5,
            )

            # Step 7: Generate reports
            self.logger.info("Step 7: Generating reports...")
            # benchmark_data already fetched in Step 4
            exported_files = self.reporter.export_all_results(
                result=result,
                signals=signals,
                benchmark_data=benchmark_data
            )

            # Log results
            self.logger.info("Backtest completed successfully!")
            self.logger.info(f"Performance Summary:")
            self.logger.info(f"  Initial Capital: {result.initial_capital:,}")
            self.logger.info(f"  Final Capital: {result.final_capital:,}")
            self.logger.info(f"  Total Return: {result.total_return_pct}%")
            self.logger.info(f"  Win Rate: {result.win_rate}%")
            self.logger.info(f"  Total Trades: {result.total_trades}")
            self.logger.info(f"  Max Drawdown: {result.max_drawdown}%")
            self.logger.info(f"  Sharpe Ratio: {result.sharpe_ratio}")

            self.logger.info("Generated files:")
            for file_type, filepath in exported_files.items():
                self.logger.info(f"  {file_type}: {filepath}")

            return result, exported_files

        except Exception as e:
            self.logger.error(f"Backtest failed: {e}")
            raise

    def run_quick_test(self, symbols: list = None, days: int = 30):
        """
        Run a quick backtest for testing purposes

        Args:
            symbols: List of symbols to test (defaults to top 5)
            days: Number of days to backtest
        """
        self.logger.info(f"Running quick test for {days} days")

        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            stocks_dir = os.path.join(os.path.dirname(__file__), '../../data/stocks')
            stocks_dir = os.path.normpath(stocks_dir)

            if os.path.isdir(stocks_dir) and os.listdir(stocks_dir):
                self.logger.info(f"Loading local data from {stocks_dir} ...")
                needed_start = start_date - timedelta(days=50)
                all_stock_data = self.data_source.load_from_stocks_dir(
                    stocks_dir=stocks_dir,
                    start_date=needed_start,
                    end_date=end_date
                )
                if self._coverage_ratio(all_stock_data, needed_start, end_date) < 0.1:
                    self._download_history(stocks_dir, needed_start, end_date)
                    all_stock_data = self.data_source.load_from_stocks_dir(
                        stocks_dir=stocks_dir,
                        start_date=needed_start,
                        end_date=end_date
                    )
                # Optionally filter to requested symbols
                if symbols:
                    symbol_set = {s[0] if isinstance(s, tuple) else s for s in symbols}
                    stock_data = {k: v for k, v in all_stock_data.items() if k in symbol_set}
                else:
                    # Quick test: use first 5 available symbols
                    keys = list(all_stock_data.keys())[:5]
                    stock_data = {k: all_stock_data[k] for k in keys}
            else:
                if symbols is None:
                    all_symbols = self.data_source.get_taiwan_stock_list()
                    symbols = all_symbols[:5]  # Top 5 stocks only
                stock_data = self.data_source.fetch_multiple_stocks(
                    symbols=symbols,
                    start_date=start_date - timedelta(days=50),
                    end_date=end_date,
                    delay=0.5
                )

            # Generate signals
            signals = self.strategy.generate_signals_for_multiple_stocks(
                stock_data_dict=stock_data,
                start_date=start_date,
                end_date=end_date
            )

            # Run backtest
            self.engine = BacktestEngine(initial_capital=Decimal('100000'))
            for symbol, data in stock_data.items():
                self.engine.add_price_data(symbol, data)

            result = self.engine.run_backtest(signals, start_date, end_date)

            # Quick summary
            self.logger.info("Quick Test Results:")
            self.logger.info(f"  Return: {result.total_return_pct}%")
            self.logger.info(f"  Trades: {result.total_trades}")
            self.logger.info(f"  Win Rate: {result.win_rate}%")

            return result

        except Exception as e:
            self.logger.error(f"Quick test failed: {e}")
            raise


async def main():
    """Main execution function"""
    runner = BacktestRunner()

    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--quick':
        # Quick test mode
        print("Running quick test...")
        result = runner.run_quick_test()
        print(f"Quick test completed. Return: {result.total_return_pct}%")
    else:
        # Full backtest mode
        print("Running full backtest...")
        result, files = await runner.run_full_backtest()
        print(f"Full backtest completed. Check reports in: {files}")


if __name__ == "__main__":
    asyncio.run(main())