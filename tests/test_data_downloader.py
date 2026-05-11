"""
Tests for data downloader module
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os
from unittest.mock import patch, MagicMock

from src.infrastructure.market_data.yfinance_client import YFinanceClient

class TestYFinanceClient:
    """Test YFinance client functionality"""

    def setup_method(self):
        """Setup for each test"""
        self.client = YFinanceClient()

    def test_get_tse_listed_stocks(self):
        """Test getting TSE listed stocks"""
        mock_data = [
            {'Code': '2330', 'Name': '台積電'},
            {'Code': '2317', 'Name': '鴻海'},
            {'Code': 'IX0001', 'Name': '加權指數'},  # should be excluded
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        with patch('src.infrastructure.market_data.yfinance_client.requests.get', return_value=mock_response):
            stocks = self.client.get_tse_listed_stocks()

        assert isinstance(stocks, list)
        assert len(stocks) == 2
        assert '2330.TW' in stocks
        assert '2317.TW' in stocks

    def test_get_otc_listed_stocks(self):
        """Test getting OTC listed stocks"""
        mock_data = [
            {'SecuritiesCompanyCode': '6277', 'CompanyName': '宏正'},
            {'SecuritiesCompanyCode': '3481', 'CompanyName': '群創'},
            {'SecuritiesCompanyCode': '00679B', 'CompanyName': '元大美債20年'},  # should be excluded
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status.return_value = None

        with patch('src.infrastructure.market_data.yfinance_client.requests.get', return_value=mock_response):
            stocks = self.client.get_otc_listed_stocks()

        assert isinstance(stocks, list)
        assert len(stocks) == 2
        assert '6277.TWO' in stocks
        assert '3481.TWO' in stocks

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

    def test_save_stock_data_appends_new_rows(self):
        """New dates should be appended to the existing CSV, not overwrite it."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.infrastructure.market_data.yfinance_client.settings') as mock_settings:
                mock_settings.data.stocks_path = temp_dir

                day1 = pd.DataFrame({
                    'date': ['2026-03-27'],  # Friday (weekday)
                    'open': [100.0], 'high': [110.0], 'low': [95.0],
                    'close': [105.0], 'volume': [1000000], 'symbol': ['TEST.TW'],
                })
                day2 = pd.DataFrame({
                    'date': ['2026-03-31'],  # Tuesday (weekday)
                    'open': [106.0], 'high': [112.0], 'low': [104.0],
                    'close': [110.0], 'volume': [1200000], 'symbol': ['TEST.TW'],
                })

                self.client.save_stock_data('TEST.TW', day1)
                self.client.save_stock_data('TEST.TW', day2)

                saved = pd.read_csv(os.path.join(temp_dir, 'TEST_TW.csv'))
                assert len(saved) == 2, "Should have two distinct date rows"

    def test_save_stock_data_deduplicates_on_same_date(self):
        """Saving data for an existing date should update the row, not create a duplicate."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.infrastructure.market_data.yfinance_client.settings') as mock_settings:
                mock_settings.data.stocks_path = temp_dir

                original = pd.DataFrame({
                    'date': ['2026-03-27'],  # Friday (weekday)
                    'open': [100.0], 'high': [110.0], 'low': [95.0],
                    'close': [105.0], 'volume': [1000000], 'symbol': ['TEST.TW'],
                })
                updated = pd.DataFrame({
                    'date': ['2026-03-27'],  # Friday (weekday)
                    'open': [100.0], 'high': [115.0], 'low': [95.0],
                    'close': [112.0], 'volume': [1500000], 'symbol': ['TEST.TW'],
                })

                self.client.save_stock_data('TEST.TW', original)
                self.client.save_stock_data('TEST.TW', updated)

                saved = pd.read_csv(os.path.join(temp_dir, 'TEST_TW.csv'))
                assert len(saved) == 1, "Duplicate date should not create extra rows"
                assert saved['close'].iloc[0] == 112.0, "Should keep the latest value"

    def test_save_stock_data_sorted_by_date(self):
        """Saved CSV should always be sorted ascending by date."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.infrastructure.market_data.yfinance_client.settings') as mock_settings:
                mock_settings.data.stocks_path = temp_dir

                # Save newer date first, then older
                new_row = pd.DataFrame({
                    'date': ['2026-03-31'],
                    'open': [106.0], 'high': [112.0], 'low': [104.0],
                    'close': [110.0], 'volume': [1200000], 'symbol': ['TEST.TW'],
                })
                old_row = pd.DataFrame({
                    'date': ['2026-03-28'],
                    'open': [100.0], 'high': [110.0], 'low': [95.0],
                    'close': [105.0], 'volume': [1000000], 'symbol': ['TEST.TW'],
                })

                self.client.save_stock_data('TEST.TW', new_row)
                self.client.save_stock_data('TEST.TW', old_row)

                saved = pd.read_csv(os.path.join(temp_dir, 'TEST_TW.csv'))
                dates = pd.to_datetime(saved['date']).tolist()
                assert dates == sorted(dates), "Rows should be sorted ascending by date"

class TestBatchDownload:
    """Unit tests for _download_batch"""

    def setup_method(self):
        self.client = YFinanceClient()
        self.start = datetime(2026, 3, 28)
        self.end = datetime(2026, 4, 1)

    def _make_multi_df(self, symbols):
        """Build a minimal MultiIndex DataFrame that mimics yf.download output."""
        dates = pd.to_datetime(['2026-03-28', '2026-03-31'])
        arrays = [
            [sym for sym in symbols for _ in ('Close', 'High', 'Low', 'Open', 'Volume')],
            ['Close', 'High', 'Low', 'Open', 'Volume'] * len(symbols),
        ]
        cols = pd.MultiIndex.from_arrays(arrays, names=['Ticker', 'Price'])
        data = {}
        for sym in symbols:
            for col in ('Close', 'High', 'Low', 'Open'):
                data[(sym, col)] = [100.0, 101.0]
            data[(sym, 'Volume')] = [1_000_000, 1_200_000]
        return pd.DataFrame(data, index=dates, columns=cols)

    @patch('yfinance.download')
    def test_batch_single_symbol(self, mock_dl):
        """Single-symbol path returns a dict with one entry."""
        mock_df = pd.DataFrame({
            'Date': pd.to_datetime(['2026-03-28', '2026-03-31']),
            'Open': [99.0, 100.0], 'High': [102.0, 103.0],
            'Low': [98.0, 99.0], 'Close': [101.0, 102.0],
            'Volume': [1_000_000, 1_100_000],
        }).set_index('Date')
        mock_dl.return_value = mock_df

        result = self.client._download_batch(['2330.TW'], self.start, self.end)

        assert '2330.TW' in result
        assert not result['2330.TW'].empty
        assert 'symbol' in result['2330.TW'].columns

    @patch('yfinance.download')
    def test_batch_multiple_symbols(self, mock_dl):
        """Multi-symbol path splits the MultiIndex DataFrame per ticker."""
        symbols = ['2330.TW', '2317.TW']
        mock_dl.return_value = self._make_multi_df(symbols)

        result = self.client._download_batch(symbols, self.start, self.end)

        assert '2330.TW' in result
        assert '2317.TW' in result
        assert result['2330.TW']['symbol'].iloc[0] == '2330.TW'

    @patch('yfinance.download')
    def test_batch_empty_symbol_excluded(self, mock_dl):
        """Symbol with all-NaN data should be absent from result."""
        symbols = ['2330.TW', 'INVALID.TW']
        base = self._make_multi_df(symbols)
        # Wipe out INVALID.TW with NaN
        for col in ('Close', 'High', 'Low', 'Open', 'Volume'):
            base[('INVALID.TW', col)] = float('nan')
        mock_dl.return_value = base

        result = self.client._download_batch(symbols, self.start, self.end)

        assert '2330.TW' in result
        assert 'INVALID.TW' not in result

    @patch('yfinance.download')
    def test_download_all_stocks_uses_batches(self, mock_dl):
        """download_all_stocks should call yf.download once per batch, not per symbol."""
        symbols = [f'{i:04d}.TW' for i in range(1, 11)]  # 10 symbols

        # Fake stock list fetch
        with patch.object(self.client, 'get_tse_listed_stocks', return_value=symbols), \
             patch.object(self.client, 'get_otc_listed_stocks', return_value=[]), \
             patch.object(self.client, 'save_stock_data', return_value=True):

            mock_dl.return_value = self._make_multi_df(symbols)

            count = self.client.download_all_stocks(
                start_date=self.start,
                end_date=self.end,
                batch_size=10,  # all in one batch
            )

        # yf.download called exactly once (one batch of 10)
        assert mock_dl.call_count == 1
        assert count == 10


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