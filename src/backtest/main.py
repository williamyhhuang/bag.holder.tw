"""
Main backtesting execution script
"""
import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
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
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BacktestRunner:
    """Main backtest runner"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.data_source = YFinanceDataSource()
        self.strategy = TechnicalStrategy()
        self.engine = BacktestEngine()
        self.analyzer = PerformanceAnalyzer()
        self.reporter = BacktestReporter()

    async def run_full_backtest(
        self,
        start_date: date = date(2024, 9, 1),
        end_date: date = None,
        initial_capital: Decimal = Decimal('1000000')
    ):
        """
        Run complete backtesting process

        Args:
            start_date: Backtest start date
            end_date: Backtest end date (defaults to today)
            initial_capital: Initial capital
        """
        if end_date is None:
            end_date = date.today()

        self.logger.info(f"Starting full backtest from {start_date} to {end_date}")

        try:
            # Step 1: Fetch historical data
            self.logger.info("Step 1: Fetching historical data...")
            stock_symbols = self.data_source.get_taiwan_stock_list()

            stock_data = self.data_source.fetch_multiple_stocks(
                symbols=stock_symbols,
                start_date=start_date - timedelta(days=100),  # Extra data for indicators
                end_date=end_date,
                delay=1.0
            )

            if not stock_data:
                raise Exception("No stock data fetched")

            # Save historical data
            data_file = self.data_source.save_to_csv(stock_data)
            self.logger.info(f"Historical data saved to: {data_file}")

            # Step 2: Generate trading signals
            self.logger.info("Step 2: Generating trading signals...")
            signals = self.strategy.generate_signals_for_multiple_stocks(
                stock_data_dict=stock_data,
                start_date=start_date,
                end_date=end_date
            )

            self.logger.info(f"Generated {len(signals)} trading signals")

            # Get signal summary
            signal_summary = self.strategy.get_signal_summary(signals)
            self.logger.info(f"Signal summary: {signal_summary}")

            # Step 3: Prepare backtest engine
            self.logger.info("Step 3: Setting up backtest engine...")
            self.engine = BacktestEngine(initial_capital=initial_capital)

            # Add price data to engine
            for symbol, data in stock_data.items():
                self.engine.add_price_data(symbol, data)

            # Step 4: Run backtest
            self.logger.info("Step 4: Running backtest...")
            result = self.engine.run_backtest(signals, start_date, end_date)

            # Step 5: Fetch benchmark data
            self.logger.info("Step 5: Fetching benchmark data...")
            benchmark_data = self.data_source.get_market_index_data(start_date, end_date)

            # Step 6: Generate reports
            self.logger.info("Step 6: Generating reports...")
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
            # Use subset of symbols for quick testing
            if symbols is None:
                all_symbols = self.data_source.get_taiwan_stock_list()
                symbols = all_symbols[:5]  # Top 5 stocks only

            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            # Fetch data
            stock_data = self.data_source.fetch_multiple_stocks(
                symbols=symbols,
                start_date=start_date - timedelta(days=50),  # Extra for indicators
                end_date=end_date,
                delay=0.5  # Faster for testing
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