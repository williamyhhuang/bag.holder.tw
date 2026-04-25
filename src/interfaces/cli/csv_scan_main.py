"""
CSV-based scanner main entry point
"""
import argparse
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.application.services.csv_scanner import CSVStockScanner
from src.infrastructure.notification.telegram_notifier import TelegramNotifier
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CSVScannerCLI:
    """Command line interface for CSV-based scanner"""

    def __init__(self):
        self.scanner = CSVStockScanner()
        self.telegram = TelegramNotifier()
        self.logger = get_logger(self.__class__.__name__)

    def run_scan(self, args):
        """Run the scan command"""
        try:
            strategy = args.strategy if args.strategy else None

            if strategy:
                # Run specific strategy
                if strategy == 'momentum':
                    results = {'momentum': self.scanner.analyze_momentum_stocks()}
                elif strategy == 'oversold':
                    results = {'oversold': self.scanner.analyze_oversold_stocks()}
                elif strategy == 'breakout':
                    results = {'breakout': self.scanner.analyze_breakout_stocks()}
                else:
                    self.logger.error(f"Unknown strategy: {strategy}")
                    return
            else:
                # Run all strategies
                results = self.scanner.run_all_strategies()

            # Display results
            self.display_results(results)

            # Send to Telegram if requested
            if args.send_telegram:
                message = self.scanner.format_results_for_telegram(results)
                success = self.telegram.send_message(message)
                if success:
                    self.logger.info("Results sent to Telegram successfully")
                else:
                    self.logger.error("Failed to send results to Telegram")

        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            sys.exit(1)

    def display_results(self, results):
        """Display scan results"""
        total_stocks = sum(len(stocks) for stocks in results.values())
        print(f"\n📈 選股分析結果 (共找到 {total_stocks} 支股票)\n")

        for strategy, stocks in results.items():
            if not stocks:
                continue

            strategy_name = {
                'momentum': '動能股',
                'oversold': '超賣股',
                'breakout': '突破股'
            }.get(strategy, strategy)

            print(f"🎯 {strategy_name} ({len(stocks)}支):")
            print("-" * 50)

            for stock in stocks[:10]:  # Show top 10
                symbol = stock['symbol'].replace('_', '.')
                name = stock.get('name', '')
                symbol_display = f"{symbol} {name}" if name else symbol
                action = "做多" if stock['action'] == 'long' else "做空"
                price = stock['price']
                change_pct = stock['price_change_pct']
                volume = stock['volume']
                rsi = stock['rsi14']

                print(f"  {symbol_display:<20} | {action:<4} | 價格: {price:>8.2f} | "
                      f"漲跌: {change_pct:>+6.2f}% | 成交量: {volume:>10,.0f} | "
                      f"RSI: {rsi:>5.1f}")

            print()

def create_parser():
    """Create argument parser for scan command"""
    parser = argparse.ArgumentParser(
        description="Scan Taiwan stocks using CSV data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.scanner.csv_main scan
  python -m src.scanner.csv_main scan --strategy momentum
  python -m src.scanner.csv_main scan --send-telegram
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan stocks for opportunities')
    scan_parser.add_argument(
        '--strategy',
        choices=['momentum', 'oversold', 'breakout'],
        help='Specific strategy to run (default: all strategies)'
    )
    scan_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='Send results to Telegram'
    )

    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = CSVScannerCLI()

    if args.command == 'scan':
        cli.run_scan(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()