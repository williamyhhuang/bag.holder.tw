#!/usr/bin/env python3
"""
Simple script to run backtest demo
"""
import sys
import os
import asyncio
import argparse
from decimal import Decimal

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.backtest.main import BacktestRunner
    from src.utils.logger import get_logger
    from config.settings import settings
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure all dependencies are installed and paths are correct.")
    sys.exit(1)

logger = get_logger(__name__)


async def run_demo_backtest(skip_download: bool = False):
    """Run a demonstration backtest"""
    print("🚀 Starting Taiwan Stock Backtesting Demo")
    print("=" * 50)

    try:
        runner = BacktestRunner()

        # Dates come from config (BACKTEST_START_DATE / BACKTEST_END_DATE in .env)
        # run_full_backtest() resolves None → config value → fallback
        result, files = await runner.run_full_backtest(
            initial_capital=Decimal('1000000'),
            skip_download=skip_download,
        )

        # Resolve the actual dates used (for display)
        cfg = settings.backtest
        from datetime import date
        start_date = cfg.start_date or date(2024, 9, 1)
        end_date = cfg.end_date or date.today()

        print(f"📅 Backtest Period: {start_date} to {end_date}")
        print(f"💰 Initial Capital: NT$1,000,000")
        print()

        # Display results
        print("📊 BACKTEST RESULTS")
        print("=" * 50)
        print(f"📈 Total Return: {result.total_return_pct}%")
        print(f"🎯 Win Rate: {result.win_rate}%")
        print(f"📉 Max Drawdown: {result.max_drawdown}%")
        print(f"⚡ Sharpe Ratio: {result.sharpe_ratio}")
        print(f"🔢 Total Trades: {result.total_trades}")
        print(f"✅ Winning Trades: {result.winning_trades}")
        print(f"❌ Losing Trades: {result.losing_trades}")
        print()

        print("📁 Generated Files:")
        print("=" * 30)
        for file_type, filepath in files.items():
            print(f"  📄 {file_type}: {filepath}")
        print()

        print("✅ Backtest completed successfully!")
        print("📋 Check the reports/ directory for detailed analysis.")

        return True

    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        logger.error(f"Backtest error: {e}")
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Taiwan Stock Backtest')
    parser.add_argument('--skip-download', action='store_true', help='略過下載資料')
    args = parser.parse_args()

    print("Taiwan Stock Trading Strategy Backtest System")
    print("Powered by YFinance + Technical Analysis")
    print()

    # Run the backtest
    success = asyncio.run(run_demo_backtest(skip_download=args.skip_download))

    if success:
        print("\n🎉 Demo completed! Check the generated reports for detailed analysis.")
    else:
        print("\n💥 Demo failed. Please check the logs for error details.")
        sys.exit(1)


if __name__ == "__main__":
    main()