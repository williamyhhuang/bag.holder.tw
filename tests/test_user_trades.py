"""
Tests for user trades module
"""
import pytest
import pandas as pd
import tempfile
from pathlib import Path
from datetime import datetime

from src.infrastructure.persistence.user_trades_recorder import UserTradesRecorder

class TestUserTradesRecorder:
    """Test user trades recorder functionality"""

    @pytest.fixture
    def temp_recorder(self):
        """Create recorder with temporary CSV file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = UserTradesRecorder()
            # Override the CSV path to use temporary directory
            original_path = recorder.csv_path
            recorder.csv_path = Path(temp_dir) / "test_trades.csv"

            yield recorder

            # Restore original path (though not necessary for temp directory)
            recorder.csv_path = original_path

    def test_init_csv_file(self, temp_recorder):
        """Test CSV file initialization"""
        assert not temp_recorder.csv_path.exists()

        temp_recorder.init_csv_file()

        assert temp_recorder.csv_path.exists()

        # Check that CSV has correct headers
        df = pd.read_csv(temp_recorder.csv_path)
        expected_columns = [
            'timestamp', 'date', 'symbol', 'action', 'cost',
            'quantity', 'notes', 'strategy', 'status'
        ]
        assert list(df.columns) == expected_columns

    def test_record_trade(self, temp_recorder):
        """Test recording a trade"""
        result = temp_recorder.record_trade(
            symbol='2330.TW',
            action='long',
            cost=580.0,
            quantity=1000,
            notes='Test trade',
            strategy='momentum'
        )

        assert result is True
        assert temp_recorder.csv_path.exists()

        # Verify trade was recorded
        df = pd.read_csv(temp_recorder.csv_path)
        assert len(df) == 1
        assert df.iloc[0]['symbol'] == '2330.TW'
        assert df.iloc[0]['action'] == 'long'
        assert df.iloc[0]['cost'] == 580.0
        assert df.iloc[0]['quantity'] == 1000

    def test_get_user_trades(self, temp_recorder):
        """Test getting user trades"""
        # Record some trades
        temp_recorder.record_trade('2330.TW', 'long', 580.0)
        temp_recorder.record_trade('2454.TW', 'short', 95.5)

        # Get all trades
        trades = temp_recorder.get_user_trades()
        assert len(trades) == 2

        # Filter by symbol
        tsmc_trades = temp_recorder.get_user_trades(symbol='2330.TW')
        assert len(tsmc_trades) == 1
        assert tsmc_trades.iloc[0]['symbol'] == '2330.TW'

        # Filter by action
        long_trades = temp_recorder.get_user_trades(action='long')
        assert len(long_trades) == 1
        assert long_trades.iloc[0]['action'] == 'long'

    def test_get_trade_statistics(self, temp_recorder):
        """Test getting trade statistics"""
        # Record some trades
        temp_recorder.record_trade('2330.TW', 'long', 580.0)
        temp_recorder.record_trade('2454.TW', 'short', 95.5)
        temp_recorder.record_trade('1101.TW', 'long', 45.0)

        stats = temp_recorder.get_trade_statistics()

        assert isinstance(stats, dict)
        assert stats['total_trades'] == 3
        assert stats['long_trades'] == 2
        assert stats['short_trades'] == 1
        assert stats['open_trades'] == 3  # All trades start as open

    def test_update_trade_status(self, temp_recorder):
        """Test updating trade status"""
        # Record a trade
        temp_recorder.record_trade('2330.TW', 'long', 580.0, quantity=1000)

        # Update trade status
        result = temp_recorder.update_trade_status(
            trade_id=0,
            status='closed',
            exit_price=620.0
        )

        assert result is True

        # Verify update
        df = pd.read_csv(temp_recorder.csv_path)
        assert df.iloc[0]['status'] == 'closed'
        assert df.iloc[0]['exit_price'] == 620.0
        # Check P&L calculation
        expected_pnl = (620.0 - 580.0) * 1000  # Long position profit
        assert df.iloc[0]['pnl'] == expected_pnl

    def test_export_trades_report(self, temp_recorder):
        """Test exporting trades report"""
        # Record some trades
        temp_recorder.record_trade('2330.TW', 'long', 580.0)
        temp_recorder.record_trade('2454.TW', 'short', 95.5)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_report.csv"
            result = temp_recorder.export_trades_report(str(output_path))

            assert result == str(output_path)
            assert output_path.exists()

            # Verify report contains data
            with open(output_path, 'r') as f:
                content = f.read()
                assert '2330.TW' in content
                assert '2454.TW' in content

class TestUserTradesEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_csv_operations(self):
        """Test operations on empty CSV"""
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = UserTradesRecorder()
            recorder.csv_path = Path(temp_dir) / "empty_trades.csv"

            # Test getting trades from non-existent file
            trades = recorder.get_user_trades()
            assert len(trades) == 0

            # Test statistics from empty data
            stats = recorder.get_trade_statistics()
            assert stats == {}

    def test_invalid_trade_id(self):
        """Test updating with invalid trade ID"""
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = UserTradesRecorder()
            recorder.csv_path = Path(temp_dir) / "test_trades.csv"

            # Try to update non-existent trade
            result = recorder.update_trade_status(999, 'closed')
            assert result is False