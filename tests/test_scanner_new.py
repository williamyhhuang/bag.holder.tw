"""
Tests for scanner module
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import tempfile
from pathlib import Path

from src.scanner.csv_scanner import CSVStockScanner

class TestCSVStockScanner:
    """Test CSV stock scanner functionality"""

    def setup_method(self):
        """Setup for each test"""
        self.scanner = CSVStockScanner()

    def test_calculate_rsi(self):
        """Test RSI calculation"""
        # Create sample price data
        prices = pd.Series([100, 102, 101, 105, 104, 107, 106, 108, 110, 109, 112, 115, 113, 116, 118])

        rsi = self.scanner.calculate_rsi(prices, period=14)

        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(prices)
        # RSI should be between 0 and 100
        valid_rsi = rsi.dropna()
        assert all((0 <= val <= 100) for val in valid_rsi)

    def test_calculate_technical_indicators(self):
        """Test technical indicators calculation"""
        # Create sample data
        data = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=30),
            'close': np.random.uniform(100, 110, 30),
            'volume': np.random.uniform(100000, 200000, 30)
        })

        result = self.scanner.calculate_technical_indicators(data)

        assert isinstance(result, pd.DataFrame)
        assert 'ma5' in result.columns
        assert 'ma20' in result.columns
        assert 'rsi14' in result.columns
        assert 'price_change_pct' in result.columns

    def test_analyze_momentum_stocks_empty_data(self):
        """Test momentum analysis with empty data"""
        # Temporarily change data path to non-existent directory
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = self.scanner.data_path
            self.scanner.data_path = Path(temp_dir)

            results = self.scanner.analyze_momentum_stocks()

            assert isinstance(results, list)
            assert len(results) == 0

            # Restore original path
            self.scanner.data_path = original_path

    def test_format_results_for_telegram(self):
        """Test formatting results for Telegram"""
        # Create mock results
        mock_results = {
            'momentum': [
                {
                    'symbol': '2330_TW',
                    'action': 'long',
                    'price': 580.0,
                    'price_change_pct': 2.5,
                    'volume': 50000000,
                    'rsi14': 65.0,
                    'date': datetime.now()
                }
            ],
            'oversold': [],
            'breakout': [
                {
                    'symbol': '2454_TW',
                    'action': 'long',
                    'price': 95.5,
                    'price_change_pct': 3.2,
                    'volume': 20000000,
                    'rsi14': 45.0,
                    'date': datetime.now()
                }
            ]
        }

        message = self.scanner.format_results_for_telegram(mock_results)

        assert isinstance(message, str)
        assert '動能股' in message
        assert '突破股' in message
        assert '2330' in message
        assert '2454' in message

    def test_run_all_strategies(self):
        """Test running all strategies"""
        # This will return empty results if no CSV files exist, which is expected
        results = self.scanner.run_all_strategies()

        assert isinstance(results, dict)
        assert 'momentum' in results
        assert 'oversold' in results
        assert 'breakout' in results
        assert all(isinstance(stocks, list) for stocks in results.values())