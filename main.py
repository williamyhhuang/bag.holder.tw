"""
Main CLI entry point for Taiwan Stock Analysis System
"""
import argparse
import sys
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger

logger = get_logger(__name__)

def run_download(args):
    """Run download command"""
    cmd = ['python', '-m', 'src.interfaces.cli.download_main', 'download']

    if args.start_date:
        cmd.extend(['--start-date', args.start_date])
    if args.end_date:
        cmd.extend(['--end-date', args.end_date])
    if args.markets:
        cmd.extend(['--markets'] + args.markets)
    if hasattr(args, 'limit') and args.limit:
        cmd.extend(['--limit', str(args.limit)])
    if hasattr(args, 'source') and args.source:
        cmd.extend(['--source', args.source])

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Download command failed: {e}")
        return False

def run_signals(args):
    """Run today's trading signals command"""
    cmd = ['python', '-m', 'src.interfaces.cli.signals_main', 'signals']

    if getattr(args, 'watch', False):
        cmd.append('--watch')
    if getattr(args, 'send_telegram', False):
        cmd.append('--send-telegram')
    if getattr(args, 'ai_filter', False):
        cmd.append('--ai-filter')

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Signals command failed: {e}")
        return False

def run_scan(args):
    """Run scan command"""
    cmd = ['python', '-m', 'src.interfaces.cli.csv_scan_main', 'scan']

    if args.strategy:
        cmd.extend(['--strategy', args.strategy])
    if args.send_telegram:
        cmd.append('--send-telegram')

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Scan command failed: {e}")
        return False

def run_backtest(args):
    """Run backtest command"""
    cmd = ['python', 'run_backtest.py']

    if hasattr(args, 'period') and args.period:
        cmd.extend(['--period', args.period])
    if hasattr(args, 'strategy') and args.strategy:
        cmd.extend(['--strategy', args.strategy])
    if getattr(args, 'skip_download', False):
        cmd.append('--skip-download')

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Backtest command failed: {e}")
        return False

def run_futures(args):
    """Run futures command"""
    cmd = ['python', '-m', 'src.interfaces.cli.futures_cli_main', 'analyze']

    if args.send_telegram:
        cmd.append('--send-telegram')

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Futures command failed: {e}")
        return False

def run_check_holdings(args):
    """Run check-holdings command"""
    cmd = ['python', '-m', 'src.interfaces.cli.check_holdings_main', 'check-holdings']

    if getattr(args, 'send_telegram', False):
        cmd.append('--send-telegram')

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Check-holdings command failed: {e}")
        return False

def run_sync_trades(args):
    """Run sync-trades command"""
    cmd = ['python', '-m', 'src.interfaces.cli.sync_trades_main', 'sync-trades']

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Sync-trades command failed: {e}")
        return False

def create_parser():
    """Create main argument parser"""
    parser = argparse.ArgumentParser(
        prog='台股分析系統',
        description='Taiwan Stock Analysis System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例用法:
  # 下載股票資料
  python main.py download
  python main.py download --start-date 2024-01-01 --end-date 2024-01-31

  # 今日買賣訊號（P1 策略完整過濾，建議進出場）
  python main.py signals
  python main.py signals --watch         # 含觀察清單
  python main.py signals --send-telegram

  # 執行選股分析（觀察清單，寬鬆條件）
  python main.py scan
  python main.py scan --strategy momentum --send-telegram

  # 執行回測
  python main.py backtest
  python main.py backtest --skip-download  # 略過下載，直接用本地資料

  # 期貨分析
  python main.py futures --send-telegram

  # 持倉賣出檢查（讀 Google Sheets，判斷是否應賣出，含 AI 分析）
  python main.py check-holdings
  python main.py check-holdings --send-telegram

  # 同步 Fubon 今日成交記錄至 Google Sheets（每日 14:35 自動執行）
  python main.py sync-trades
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用指令')

    # Download command
    download_parser = subparsers.add_parser('download', help='下載股票資料')
    download_parser.add_argument(
        '--start-date',
        type=str,
        help='開始日期 (YYYY-MM-DD 格式)'
    )
    download_parser.add_argument(
        '--end-date',
        type=str,
        help='結束日期 (YYYY-MM-DD 格式)'
    )
    download_parser.add_argument(
        '--markets',
        nargs='+',
        choices=['TSE', 'OTC'],
        help='市場選擇 (預設: TSE OTC)'
    )
    download_parser.add_argument(
        '--limit',
        type=int,
        help='限制下載股票數量 (測試用)'
    )
    download_parser.add_argument(
        '--source',
        choices=['yfinance', 'fubon'],
        default=None,
        help='資料來源: yfinance (預設) 或 fubon'
    )

    # Signals command (P1 actionable buy/sell signals)
    signals_parser = subparsers.add_parser('signals', help='今日 P1 策略買賣訊號（建議進出場）')
    signals_parser.add_argument(
        '--watch',
        action='store_true',
        help='同時顯示觀察清單（訊號觸發但未達條件）'
    )
    signals_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='發送結果到 Telegram'
    )
    signals_parser.add_argument(
        '--ai-filter',
        action='store_true',
        dest='ai_filter',
        help='使用 AI 對訊號清單進行二次過濾分析'
    )

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='執行選股分析（觀察清單）')
    scan_parser.add_argument(
        '--strategy',
        choices=['momentum', 'oversold', 'breakout'],
        help='特定策略 (預設: 所有策略)'
    )
    scan_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='發送結果到 Telegram'
    )

    # Backtest command
    backtest_parser = subparsers.add_parser('backtest', help='執行回測分析')
    backtest_parser.add_argument(
        '--skip-download',
        action='store_true',
        help='略過下載資料，直接使用本地資料'
    )

    # Futures command
    futures_parser = subparsers.add_parser('futures', help='期貨分析')
    futures_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='發送結果到 Telegram'
    )

    # Check-holdings command
    check_holdings_parser = subparsers.add_parser(
        'check-holdings',
        help='持倉賣出檢查：讀 Google Sheets 持倉，判斷是否應賣出（含 AI 判斷）'
    )
    check_holdings_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='發送結果到 Telegram'
    )

    # Sync-trades command
    subparsers.add_parser(
        'sync-trades',
        help='同步 Fubon 今日成交記錄至 Google Sheets 交易記錄頁籤'
    )

    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    print(f"🚀 執行指令: {args.command}")

    success = False

    try:
        if args.command == 'download':
            success = run_download(args)
        elif args.command == 'signals':
            success = run_signals(args)
        elif args.command == 'scan':
            success = run_scan(args)
        elif args.command == 'backtest':
            success = run_backtest(args)
        elif args.command == 'futures':
            success = run_futures(args)
        elif args.command == 'check-holdings':
            success = run_check_holdings(args)
        elif args.command == 'sync-trades':
            success = run_sync_trades(args)
        else:
            parser.print_help()
            sys.exit(1)

        if success:
            print(f"✅ 指令 '{args.command}' 執行完成")
        else:
            print(f"❌ 指令 '{args.command}' 執行失敗")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⚠️ 使用者中斷執行")
        sys.exit(1)
    except Exception as e:
        logger.error(f"執行錯誤: {e}")
        print(f"❌ 執行錯誤: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()