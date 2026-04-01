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
    cmd = ['python', '-m', 'src.data_downloader.main', 'download']

    if args.start_date:
        cmd.extend(['--start-date', args.start_date])
    if args.end_date:
        cmd.extend(['--end-date', args.end_date])
    if args.markets:
        cmd.extend(['--markets'] + args.markets)
    if hasattr(args, 'limit') and args.limit:
        cmd.extend(['--limit', str(args.limit)])

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Download command failed: {e}")
        return False

def run_scan(args):
    """Run scan command"""
    cmd = ['python', '-m', 'src.scanner.csv_main', 'scan']

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

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Backtest command failed: {e}")
        return False

def run_futures(args):
    """Run futures command"""
    cmd = ['python', '-m', 'src.futures.cli_main', 'analyze']

    if args.send_telegram:
        cmd.append('--send-telegram')

    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"Futures command failed: {e}")
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

  # 執行選股分析
  python main.py scan
  python main.py scan --strategy momentum --send-telegram

  # 執行回測
  python main.py backtest

  # 期貨分析
  python main.py futures --send-telegram
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

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='執行選股分析')
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

    # Futures command
    futures_parser = subparsers.add_parser('futures', help='期貨分析')
    futures_parser.add_argument(
        '--send-telegram',
        action='store_true',
        help='發送結果到 Telegram'
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
        elif args.command == 'scan':
            success = run_scan(args)
        elif args.command == 'backtest':
            success = run_backtest(args)
        elif args.command == 'futures':
            success = run_futures(args)
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