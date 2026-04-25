"""
CSV-based user trades recorder
"""
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
import os

from ...utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

class UserTradesRecorder:
    """Records user trading activities to CSV file"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.csv_path = Path(settings.data.user_trades_path)

    def init_csv_file(self):
        """Initialize CSV file with headers if it doesn't exist"""
        try:
            if not self.csv_path.exists():
                # Create parent directory if it doesn't exist
                self.csv_path.parent.mkdir(parents=True, exist_ok=True)

                # Create CSV with headers
                headers = [
                    'timestamp', 'date', 'symbol', 'action', 'cost',
                    'quantity', 'notes', 'strategy', 'status'
                ]

                df = pd.DataFrame(columns=headers)
                df.to_csv(self.csv_path, index=False)
                self.logger.info(f"Initialized user trades CSV at {self.csv_path}")

        except Exception as e:
            self.logger.error(f"Error initializing CSV file: {e}")

    def record_trade(
        self,
        symbol: str,
        action: str,  # 'long' or 'short'
        cost: float,
        quantity: Optional[int] = 1,
        notes: Optional[str] = None,
        strategy: Optional[str] = None
    ) -> bool:
        """
        Record a user trade to CSV

        Args:
            symbol: Stock symbol
            action: Trading action ('long' or 'short')
            cost: Cost per share
            quantity: Number of shares
            notes: Additional notes
            strategy: Strategy used

        Returns:
            True if recorded successfully
        """
        try:
            # Initialize CSV if it doesn't exist
            self.init_csv_file()

            # Create trade record
            trade_record = {
                'timestamp': datetime.now().isoformat(),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'symbol': symbol,
                'action': action,
                'cost': cost,
                'quantity': quantity or 1,
                'notes': notes or '',
                'strategy': strategy or '',
                'status': 'open'
            }

            # Read existing data
            if self.csv_path.exists() and os.path.getsize(self.csv_path) > 0:
                df = pd.read_csv(self.csv_path)
            else:
                df = pd.DataFrame()

            # Append new record
            new_row = pd.DataFrame([trade_record])
            df = pd.concat([df, new_row], ignore_index=True)

            # Save to CSV
            df.to_csv(self.csv_path, index=False)

            self.logger.info(f"Recorded trade: {symbol} {action} at {cost}")
            return True

        except Exception as e:
            self.logger.error(f"Error recording trade: {e}")
            return False

    def get_user_trades(
        self,
        symbol: Optional[str] = None,
        action: Optional[str] = None,
        days_back: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get user trades from CSV

        Args:
            symbol: Filter by symbol
            action: Filter by action
            days_back: Number of days back to fetch

        Returns:
            DataFrame with trades
        """
        try:
            if not self.csv_path.exists():
                return pd.DataFrame()

            df = pd.read_csv(self.csv_path)

            if df.empty:
                return df

            # Convert date column to datetime
            df['date'] = pd.to_datetime(df['date'])

            # Apply filters
            if symbol:
                df = df[df['symbol'] == symbol]

            if action:
                df = df[df['action'] == action]

            if days_back:
                cutoff_date = datetime.now() - pd.Timedelta(days=days_back)
                df = df[df['date'] >= cutoff_date]

            return df.sort_values('date', ascending=False)

        except Exception as e:
            self.logger.error(f"Error getting user trades: {e}")
            return pd.DataFrame()

    def update_trade_status(
        self,
        trade_id: int,
        status: str,
        exit_price: Optional[float] = None,
        exit_date: Optional[str] = None
    ) -> bool:
        """
        Update trade status (e.g., close a position)

        Args:
            trade_id: Row index of the trade
            status: New status ('closed', 'partial', etc.)
            exit_price: Exit price if closing
            exit_date: Exit date if closing

        Returns:
            True if updated successfully
        """
        try:
            if not self.csv_path.exists():
                return False

            df = pd.read_csv(self.csv_path)

            if trade_id >= len(df) or trade_id < 0:
                self.logger.error(f"Invalid trade ID: {trade_id}")
                return False

            # Update status
            df.loc[trade_id, 'status'] = status

            if exit_price is not None:
                df.loc[trade_id, 'exit_price'] = exit_price

            if exit_date is not None:
                df.loc[trade_id, 'exit_date'] = exit_date

            # Add profit/loss calculation if both prices available
            if exit_price is not None and 'cost' in df.columns:
                entry_price = df.loc[trade_id, 'cost']
                action = df.loc[trade_id, 'action']
                quantity = df.loc[trade_id, 'quantity']

                if action == 'long':
                    pnl = (exit_price - entry_price) * quantity
                else:  # short
                    pnl = (entry_price - exit_price) * quantity

                df.loc[trade_id, 'pnl'] = pnl
                df.loc[trade_id, 'pnl_pct'] = (pnl / (entry_price * quantity)) * 100

            # Save updated data
            df.to_csv(self.csv_path, index=False)

            self.logger.info(f"Updated trade {trade_id} status to {status}")
            return True

        except Exception as e:
            self.logger.error(f"Error updating trade status: {e}")
            return False

    def get_trade_statistics(self, days_back: Optional[int] = 30) -> Dict:
        """
        Get trading statistics

        Args:
            days_back: Number of days to analyze

        Returns:
            Dictionary with statistics
        """
        try:
            df = self.get_user_trades(days_back=days_back)

            if df.empty:
                return {}

            stats = {
                'total_trades': len(df),
                'long_trades': len(df[df['action'] == 'long']),
                'short_trades': len(df[df['action'] == 'short']),
                'open_trades': len(df[df['status'] == 'open']),
                'closed_trades': len(df[df['status'] == 'closed']),
                'total_invested': df['cost'].sum() if 'cost' in df.columns else 0
            }

            # Calculate P&L if available
            if 'pnl' in df.columns:
                closed_trades = df[df['status'] == 'closed']
                if not closed_trades.empty:
                    stats['total_pnl'] = closed_trades['pnl'].sum()
                    stats['avg_pnl'] = closed_trades['pnl'].mean()
                    stats['win_rate'] = len(closed_trades[closed_trades['pnl'] > 0]) / len(closed_trades) * 100

            return stats

        except Exception as e:
            self.logger.error(f"Error calculating trade statistics: {e}")
            return {}

    def export_trades_report(self, output_path: Optional[str] = None) -> str:
        """
        Export trades to a formatted report

        Args:
            output_path: Output file path

        Returns:
            Path to the generated report
        """
        try:
            df = self.get_user_trades()

            if df.empty:
                return "No trades to export"

            if output_path is None:
                output_path = f"trades_report_{datetime.now().strftime('%Y%m%d')}.csv"

            # Add summary statistics at the top
            stats = self.get_trade_statistics()

            # Create a formatted export
            with open(output_path, 'w') as f:
                f.write("# User Trading Report\\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
                f.write("# Statistics:\\n")

                for key, value in stats.items():
                    f.write(f"# {key}: {value}\\n")

                f.write("\\n")

            # Append the actual data
            df.to_csv(output_path, mode='a', index=False)

            self.logger.info(f"Exported trades report to {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Error exporting trades report: {e}")
            return f"Error: {e}"
