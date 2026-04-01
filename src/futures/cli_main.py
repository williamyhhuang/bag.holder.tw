"""
Futures analysis CLI main entry point
"""
import argparse
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.futures.analyzer import FuturesAnalyzer
from src.utils.logger import get_logger

logger = get_logger(__name__)

class FuturesCLI:
    """Command line interface for futures analysis"""

    def __init__(self):
        self.analyzer = FuturesAnalyzer()
        self.logger = get_logger(self.__class__.__name__)

    def run_analysis(self, args):
        """Run futures analysis"""
        try:
            self.logger.info("Starting futures analysis...")

            # Run analysis
            analysis = self.analyzer.run_analysis()

            if not analysis.get('success'):
                self.logger.error(f"Analysis failed: {analysis.get('error')}")
                print(f"❌ 分析失敗: {analysis.get('error')}")
                return

            # Display results
            self.display_analysis(analysis)

            # Send to Telegram if requested
            if args.send_telegram:
                message = self.analyzer.format_analysis_for_telegram(analysis)
                success = self.analyzer.telegram.send_message(message)
                if success:
                    self.logger.info("Analysis sent to Telegram successfully")
                    print("✅ 分析結果已發送至 Telegram")
                else:
                    self.logger.error("Failed to send analysis to Telegram")
                    print("❌ Telegram 發送失敗")

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            print(f"❌ 分析失敗: {e}")
            sys.exit(1)

    def display_analysis(self, analysis):
        """Display analysis results"""
        try:
            print("\n🔮 微台期貨分析結果")
            print("=" * 50)

            futures_data = analysis.get('futures_data', {})
            recommendation = analysis.get('recommendation', '觀察')
            confidence = analysis.get('confidence', 0.5)
            reasoning = analysis.get('reasoning', [])

            # Basic info
            print(f"建議操作: {recommendation}")
            print(f"信心度: {confidence:.1%}")
            print()

            # Market data
            price = futures_data.get('current_price', 0)
            change = futures_data.get('change', 0)
            change_pct = futures_data.get('change_percent', 0)
            volume = futures_data.get('volume', 0)

            print("市場數據:")
            print(f"  目前價位: {price:,.0f}")
            print(f"  漲跌: {change:+.0f} ({change_pct:+.2f}%)")
            print(f"  成交量: {volume:,.0f}")
            print()

            # Analysis reasoning
            if reasoning:
                print("分析依據:")
                for i, reason in enumerate(reasoning, 1):
                    print(f"  {i}. {reason}")
                print()

            print(f"分析時間: {analysis.get('analysis_time', '').strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            self.logger.error(f"Error displaying analysis: {e}")
            print("顯示結果時發生錯誤")

def create_parser():
    """Create argument parser for futures command"""
    parser = argparse.ArgumentParser(
        description="Analyze Taiwan futures market",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.futures.cli_main analyze
  python -m src.futures.cli_main analyze --send-telegram
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Run futures analysis')
    analyze_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='Send analysis to Telegram'
    )

    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = FuturesCLI()

    if args.command == 'analyze':
        cli.run_analysis(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()