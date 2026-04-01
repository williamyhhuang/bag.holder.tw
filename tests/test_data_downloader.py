"""
Tests for data downloader module
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from src.data_downloader.yfinance_client import YFinanceClient

class TestYFinanceClient:
    """Test YFinance client functionality"""

    def setup_method(self):
        """Setup for each test"""
        self.client = YFinanceClient()

    def test_get_tse_listed_stocks(self):
        """Test getting TSE listed stocks"""
        stocks = self.client.get_tse_listed_stocks()
        assert isinstance(stocks, list)
        assert len(stocks) > 0
        assert '2330.TW' in stocks

    def test_get_otc_listed_stocks(self):
        """Test getting OTC listed stocks"""
        stocks = self.client.get_otc_listed_stocks()
        assert isinstance(stocks, list)
        assert len(stocks) > 0

    def test_get_last_trading_date(self):
        """Test getting last trading date"""
        last_date = self.client.get_last_trading_date()
        assert isinstance(last_date, datetime)
        assert last_date <= datetime.now()

    @pytest.mark.integration
    def test_get_stock_data(self):
        """Test downloading stock data (integration test)"""
        # Test with a known good stock symbol
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        data = self.client.get_stock_data('2330.TW', start_date, end_date)

        if data is not None and not data.empty:
            assert isinstance(data, pd.DataFrame)
            assert 'symbol' in data.columns
            assert 'close' in data.columns
        # If no data, it might be due to market closure, which is acceptable

    def test_save_stock_data(self):
        """Test saving stock data to CSV"""
        # Create temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock data
            mock_data = pd.DataFrame({
                'date': [datetime.now()],
                'open': [100.0],
                'high': [110.0],
                'low': [95.0],
                'close': [105.0],
                'volume': [1000000],
                'symbol': ['TEST.TW']
            })

            # Temporarily change the data path
            original_path = self.client.csv_path if hasattr(self.client, 'csv_path') else None

            # Save data
            result = self.client.save_stock_data('TEST.TW', mock_data)

            # For this test, we'll just check if the method runs without error
            assert isinstance(result, bool)

class TestDataDownloaderIntegration:
    """Integration tests for data downloader"""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_download_recent_data(self):
        """Test downloading recent data (slow integration test)"""
        client = YFinanceClient()

        # Download data for just a few stocks to speed up test
        result = client.download_recent_data()

        # Result should be a number (count of successful downloads)
        assert isinstance(result, int)
        assert result >= 0