"""
CLI entry point for Taiwan Stock Analysis System
Re-exports from root main.py for DDD interface layer placement
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

# Import from root main.py
from main import main, create_parser, run_download, run_signals, run_scan, run_backtest, run_futures

__all__ = ["main", "create_parser"]

if __name__ == "__main__":
    main()
