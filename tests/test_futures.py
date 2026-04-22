"""
台指期貨監控模組及富邦 API 客戶端單元測試
"""
import sys
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, date
from decimal import Decimal

from src.futures.monitor import (
    TaiwanFuturesMonitor,
    FuturesContract,
    FuturesQuote,
    FuturesSignal
)
from src.api.fubon_client import FubonClient, get_near_month_symbol


# ─────────────────────────────────────────────────────────────────────────────
# get_near_month_symbol 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestGetNearMonthSymbol:
    """近月合約代號計算測試"""

    def test_symbol_format(self):
        """驗證代號格式正確（4-5字元）"""
        for product in ['TXF', 'MXF', 'MTX']:
            sym = get_near_month_symbol(product)
            assert sym.startswith(product), f"{sym} should start with {product}"
            assert len(sym) == len(product) + 2, f"{sym} should have 2 char suffix"

    def test_month_code_in_valid_range(self):
        """月份代碼應在 A~L 範圍"""
        sym = get_near_month_symbol('TXF')
        month_code = sym[3]
        assert month_code in 'ABCDEFGHIJKL'

    def test_year_digit_is_numeric(self):
        """年份尾碼應為數字"""
        sym = get_near_month_symbol('TXF')
        assert sym[4].isdigit()

    def test_products(self):
        """三大合約代號皆正確產生"""
        txf = get_near_month_symbol('TXF')
        mxf = get_near_month_symbol('MXF')
        mtx = get_near_month_symbol('MTX')
        assert txf.startswith('TXF')
        assert mxf.startswith('MXF')
        assert mtx.startswith('MTX')


# ─────────────────────────────────────────────────────────────────────────────
# FuturesContract 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestFuturesContract:
    """期貨合約單元測試"""

    def test_futures_contract_creation(self):
        """測試期貨合約創建"""
        contract = FuturesContract(
            symbol='TXF',
            name='台指期貨(大台)',
            underlying='台灣加權指數',
            expiry_date=date(2026, 5, 20),
            contract_size=200,
            tick_size=Decimal('1'),
            is_active=True
        )

        assert contract.symbol == 'TXF'
        assert contract.name == '台指期貨(大台)'
        assert contract.contract_size == 200
        assert contract.tick_size == Decimal('1')
        assert contract.is_active is True

    def test_contract_value_calculation(self):
        """測試合約價值計算"""
        contract = FuturesContract(
            symbol='TXF',
            name='台指期貨(大台)',
            underlying='台灣加權指數',
            expiry_date=date(2026, 5, 20),
            contract_size=200,
            tick_size=Decimal('1'),
            is_active=True
        )
        price = Decimal('18000')
        expected_value = price * contract.contract_size
        assert expected_value == Decimal('3600000')


# ─────────────────────────────────────────────────────────────────────────────
# FuturesQuote 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestFuturesQuote:
    """期貨報價單元測試"""

    def test_futures_quote_creation(self):
        """測試期貨報價創建"""
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18000.0'),
            volume=1000,
            timestamp=datetime(2026, 5, 1, 9, 0, 0),
            bid_price=Decimal('17999.0'),
            ask_price=Decimal('18001.0'),
            bid_volume=500,
            ask_volume=300
        )

        assert quote.symbol == 'TXF'
        assert quote.price == Decimal('18000.0')
        assert quote.volume == 1000
        assert quote.bid_price == Decimal('17999.0')
        assert quote.ask_price == Decimal('18001.0')

    def test_spread_calculation(self):
        """測試買賣價差計算"""
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18000.0'),
            volume=1000,
            timestamp=datetime(2026, 5, 1, 9, 0, 0),
            bid_price=Decimal('17999.0'),
            ask_price=Decimal('18001.0'),
        )
        spread = quote.ask_price - quote.bid_price
        assert spread == Decimal('2.0')


# ─────────────────────────────────────────────────────────────────────────────
# FuturesSignal 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestFuturesSignal:

    def test_futures_signal_creation(self):
        signal = FuturesSignal(
            contract_symbol='TXF',
            signal_type='LONG',
            signal_name='PRICE_BREAKOUT',
            current_price=Decimal('18100.0'),
            target_price=Decimal('18500.0'),
            stop_loss=Decimal('17800.0'),
            confidence=0.8,
            description='TXF 價格突破 1.5%',
            triggered_at=datetime(2026, 5, 1, 10, 30, 0),
        )

        assert signal.contract_symbol == 'TXF'
        assert signal.signal_type == 'LONG'
        assert signal.confidence == 0.8

    def test_valid_signal_types(self):
        valid_types = {'LONG', 'SHORT', 'CLOSE_LONG', 'CLOSE_SHORT', 'NEUTRAL'}
        signal = FuturesSignal(
            contract_symbol='TXF',
            signal_type='LONG',
            signal_name='TEST',
            current_price=Decimal('18000'),
            target_price=None,
            stop_loss=None,
            confidence=0.8,
            description='test',
            triggered_at=datetime.now(),
        )
        assert signal.signal_type in valid_types


# ─────────────────────────────────────────────────────────────────────────────
# TaiwanFuturesMonitor 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestTaiwanFuturesMonitor:

    @pytest.fixture
    def mock_fubon_client(self):
        client = Mock(spec=FubonClient)
        client.is_simulation = True
        client.get_futures_quote = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def futures_monitor(self, mock_fubon_client):
        return TaiwanFuturesMonitor(mock_fubon_client)

    def test_monitor_initialization(self, futures_monitor):
        assert futures_monitor is not None
        assert len(futures_monitor.futures_contracts) == 3
        assert 'TXF' in futures_monitor.futures_contracts
        assert 'MXF' in futures_monitor.futures_contracts
        assert 'MTX' in futures_monitor.futures_contracts

    def test_contract_info_retrieval(self, futures_monitor):
        txf = futures_monitor.get_contract_info('TXF')
        assert txf is not None
        assert txf.symbol == 'TXF'
        assert txf.contract_size == 200

        mxf = futures_monitor.get_contract_info('MXF')
        assert mxf.contract_size == 50

        mtx = futures_monitor.get_contract_info('MTX')
        assert mtx.contract_size == 10

        assert futures_monitor.get_contract_info('INVALID') is None

    def test_active_contracts_retrieval(self, futures_monitor):
        active = futures_monitor.get_active_contracts()
        assert len(active) == 3
        symbols = {c.symbol for c in active}
        assert symbols == {'TXF', 'MXF', 'MTX'}

    def test_near_month_expiry_calculation(self, futures_monitor):
        expiry = futures_monitor._get_near_month_expiry()
        assert isinstance(expiry, date)
        # Must be a Wednesday
        assert expiry.weekday() == 2

    @pytest.mark.asyncio
    async def test_get_futures_quote_returns_none_when_api_returns_none(
        self, futures_monitor, mock_fubon_client
    ):
        """API 回傳 None 時，_get_futures_quote 也應回傳 None"""
        mock_fubon_client.get_futures_quote = AsyncMock(return_value=None)
        quote = await futures_monitor._get_futures_quote('TXF')
        assert quote is None

    @pytest.mark.asyncio
    async def test_get_futures_quote_returns_quote_when_api_succeeds(
        self, futures_monitor, mock_fubon_client
    ):
        """API 成功回傳資料時，_get_futures_quote 應回傳 FuturesQuote"""
        mock_fubon_client.get_futures_quote = AsyncMock(return_value={
            'symbol': 'TXFE6',
            'last_price': Decimal('20000'),
            'close_price': Decimal('20000'),
            'high_price': Decimal('20100'),
            'low_price': Decimal('19900'),
            'change': Decimal('100'),
            'change_percent': Decimal('0.5'),
            'volume': 1500,
            'timestamp': datetime.now(),
        })
        quote = await futures_monitor._get_futures_quote('TXF')
        assert quote is not None
        assert quote.symbol == 'TXF'
        assert quote.price == Decimal('20000')
        assert quote.volume == 1500

    @pytest.mark.asyncio
    async def test_get_futures_quote_handles_exception_gracefully(
        self, futures_monitor, mock_fubon_client
    ):
        """API 拋出例外時，_get_futures_quote 應回傳 None 而不是拋出"""
        mock_fubon_client.get_futures_quote = AsyncMock(side_effect=Exception("API error"))
        quote = await futures_monitor._get_futures_quote('TXF')
        assert quote is None

    @pytest.mark.asyncio
    async def test_analyze_signals_returns_list(self, futures_monitor):
        contract = futures_monitor.futures_contracts['TXF']
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18100.0'),
            change_amount=Decimal('100.0'),
            change_percent=Decimal('0.56'),
            volume=1000,
            timestamp=datetime.now(),
        )
        signals = await futures_monitor._analyze_futures_signals(contract, quote)
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_high_volume_triggers_signal(self, futures_monitor):
        """TXF 成交量 > 5000 時應觸發量暴增訊號"""
        contract = futures_monitor.futures_contracts['TXF']
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18300.0'),
            change_amount=Decimal('300.0'),
            change_percent=Decimal('1.67'),
            volume=6000,
            timestamp=datetime.now(),
        )
        signals = await futures_monitor._analyze_futures_signals(contract, quote)
        assert len(signals) > 0

    @pytest.mark.asyncio
    async def test_large_price_change_triggers_signal(self, futures_monitor):
        """漲跌幅超過 1.5% 應觸發突破訊號"""
        contract = futures_monitor.futures_contracts['TXF']
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18400.0'),
            change_amount=Decimal('400.0'),
            change_percent=Decimal('2.0'),
            volume=500,
            timestamp=datetime.now(),
        )
        signals = await futures_monitor._analyze_futures_signals(contract, quote)
        assert any(s.signal_name == '台指期貨價格突破' for s in signals)


# ─────────────────────────────────────────────────────────────────────────────
# FubonClient 期貨方法測試（使用 mock SDK）
# ─────────────────────────────────────────────────────────────────────────────

class TestFubonClientFuturesAPI:
    """FubonClient 期貨 API 方法測試"""

    @pytest.fixture
    def mock_sdk(self):
        sdk = MagicMock()

        # Mock futopt marketdata
        mock_quote_data = MagicMock()
        mock_quote_data.data = {
            'name': '臺股期貨014',
            'closePrice': 20000,
            'lastPrice': 20050,
            'openPrice': 19900,
            'highPrice': 20100,
            'lowPrice': 19850,
            'previousClose': 19950,
            'change': 100,
            'changePercent': 0.5,
            'lastSize': 5,
            'total': {'tradeVolume': 2500},
        }
        sdk.marketdata.rest_client.futopt.intraday.quote.return_value = mock_quote_data

        mock_tickers_data = MagicMock()
        mock_tickers_data.data = [
            {'symbol': 'TXFE6', 'name': '臺股期貨E6', 'referencePrice': 20000,
             'settlementDate': '20260520', 'startDate': '20260421', 'endDate': '20260520'},
        ]
        sdk.marketdata.rest_client.futopt.intraday.tickers.return_value = mock_tickers_data

        # Mock futopt_accounting
        mock_position_data = MagicMock()
        mock_position_data.is_success = True
        mock_position_data.data = []
        sdk.futopt_accounting.query_hybrid_position.return_value = mock_position_data

        mock_equity_data = MagicMock()
        mock_equity_data.is_success = True
        mock_equity_data.data = {
            'date': '2026/04/21',
            'account': '1234567',
            'currency': 'TWD',
            'today_balance': 500000.0,
            'today_equity': 520000.0,
            'initial_margin': 80000.0,
            'maintenance_margin': 60000.0,
            'available_margin': 420000.0,
            'risk_index': 0.0,
            'fut_unrealized_pnl': 0.0,
            'fut_realized_pnl': 0.0,
            'buy_lot': 0,
            'sell_lot': 0,
        }
        sdk.futopt_accounting.query_margin_equity.return_value = mock_equity_data

        return sdk

    @pytest.fixture
    def client_with_mock_sdk(self, mock_sdk):
        client = FubonClient(
            user_id='A123456789',
            api_key='test_key',
            cert_path='/tmp/test.p12',
            cert_password='A123456789',
        )
        client.sdk = mock_sdk
        client.is_logged_in = True

        # Mock accounts
        mock_acc = MagicMock()
        mock_acc.account_type = 'futopt'
        mock_acc.account = '1234567'
        mock_acc.name = 'Test User'
        mock_accounts = MagicMock()
        mock_accounts.data = [mock_acc]
        client.accounts = mock_accounts

        return client

    @pytest.mark.asyncio
    async def test_get_futures_quote(self, client_with_mock_sdk):
        quote = await client_with_mock_sdk.get_futures_quote('TXFE6')
        assert quote is not None
        assert quote['last_price'] == Decimal('20050')
        assert quote['high_price'] == Decimal('20100')
        assert quote['volume'] == 2500

    @pytest.mark.asyncio
    async def test_get_futures_tickers(self, client_with_mock_sdk):
        tickers = await client_with_mock_sdk.get_futures_tickers(product='TXF')
        assert len(tickers) == 1
        assert tickers[0]['symbol'] == 'TXFE6'

    @pytest.mark.asyncio
    async def test_get_futures_positions_empty(self, client_with_mock_sdk):
        positions = await client_with_mock_sdk.get_futures_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_futures_margin_equity(self, client_with_mock_sdk):
        equity = await client_with_mock_sdk.get_futures_margin_equity()
        assert equity is not None
        assert equity['today_balance'] == 500000.0
        assert equity['available_margin'] == 420000.0
        assert equity['currency'] == 'TWD'

    def test_get_futopt_account(self, client_with_mock_sdk):
        acc = client_with_mock_sdk.get_futopt_account()
        assert acc is not None
        assert acc.account_type == 'futopt'

    def test_has_api_key_auth(self):
        from config.settings import FubonAPISettings
        settings = FubonAPISettings(
            user_id='A123456789',
            api_key='testkey',
            cert_path='/tmp/test.p12',
        )
        assert settings.has_api_key_auth() is True

    def test_has_api_key_auth_false_without_cert(self):
        from config.settings import FubonAPISettings
        settings = FubonAPISettings(
            user_id='A123456789',
            api_key='testkey',
        )
        assert settings.has_api_key_auth() is False

    def test_has_cert_auth(self):
        from config.settings import FubonAPISettings
        settings = FubonAPISettings(
            user_id='A123456789',
            password='pw',
            cert_path='/tmp/test.p12',
        )
        assert settings.has_cert_auth() is True


# ─────────────────────────────────────────────────────────────────────────────
# 輔助測試
# ─────────────────────────────────────────────────────────────────────────────

def test_contract_symbols():
    """確保只追蹤三大合約"""
    monitor = TaiwanFuturesMonitor(Mock())
    assert set(monitor.futures_contracts.keys()) == {'TXF', 'MXF', 'MTX'}


def test_txf_mxf_mtx_contract_sizes():
    """驗證三大合約乘數"""
    monitor = TaiwanFuturesMonitor(Mock())
    assert monitor.futures_contracts['TXF'].contract_size == 200
    assert monitor.futures_contracts['MXF'].contract_size == 50
    assert monitor.futures_contracts['MTX'].contract_size == 10


# ─────────────────────────────────────────────────────────────────────────────
# FuturesAnalyzer._get_taiex_from_fubon 測試
# ─────────────────────────────────────────────────────────────────────────────

class TestGetTaiexFromFubon:
    """測試 FuturesAnalyzer._get_taiex_from_fubon Fubon SDK fallback"""

    @pytest.fixture
    def analyzer(self):
        from src.futures.analyzer import FuturesAnalyzer
        return FuturesAnalyzer()

    def _make_mock_sdk(self, price=37000.0, change=150.0, change_pct=0.41):
        """建立模擬 FubonSDK，回傳 IR0001 行情"""
        mock_sdk = MagicMock()
        mock_accounts = MagicMock()
        mock_accounts.is_success = True
        mock_sdk.apikey_login.return_value = mock_accounts
        mock_sdk.login.return_value = mock_accounts

        mock_result = MagicMock()
        mock_result.data = {
            'lastPrice': price,
            'closePrice': price,
            'change': change,
            'changePercent': change_pct,
            'highPrice': price + 200,
            'lowPrice': price - 300,
        }
        mock_sdk.marketdata.rest_client.stock.intraday.quote.return_value = mock_result
        return mock_sdk

    def test_returns_taiex_data_when_fubon_succeeds(self, analyzer):
        """Fubon SDK 成功時應回傳 TAIEX 資料"""
        mock_sdk = self._make_mock_sdk(price=37000.0, change=150.0, change_pct=0.41)

        mock_fubon_neo_sdk = MagicMock()
        mock_fubon_neo_sdk.FubonSDK = MagicMock(return_value=mock_sdk)
        with patch.dict(sys.modules, {'fubon_neo': MagicMock(), 'fubon_neo.sdk': mock_fubon_neo_sdk}), \
             patch('src.futures.analyzer.settings') as mock_settings:
            mock_settings.fubon.has_api_key_auth.return_value = True
            mock_settings.fubon.user_id = 'A123456789'
            mock_settings.fubon.api_key = 'testkey'
            mock_settings.fubon.cert_path = '/tmp/test.p12'
            mock_settings.fubon.cert_password = 'A123456789'

            result = analyzer._get_taiex_from_fubon()

        assert result is not None
        assert result['symbol'] == 'TAIEX'
        assert result['current_price'] == 37000.0
        assert result['change'] == 150.0
        assert result['change_percent'] == 0.41

    def test_returns_none_when_no_credentials(self, analyzer):
        """未設定 Fubon 憑證時應回傳 None"""
        with patch('src.futures.analyzer.settings') as mock_settings:
            mock_settings.fubon.has_api_key_auth.return_value = False
            mock_settings.fubon.has_cert_auth.return_value = False

            result = analyzer._get_taiex_from_fubon()

        assert result is None

    def test_returns_none_when_login_fails(self, analyzer):
        """Fubon 登入失敗時應回傳 None"""
        mock_sdk = MagicMock()
        mock_accounts = MagicMock()
        mock_accounts.is_success = False
        mock_accounts.message = 'Login failed'
        mock_sdk.apikey_login.return_value = mock_accounts

        mock_fubon_neo_sdk = MagicMock()
        mock_fubon_neo_sdk.FubonSDK = MagicMock(return_value=mock_sdk)
        with patch.dict(sys.modules, {'fubon_neo': MagicMock(), 'fubon_neo.sdk': mock_fubon_neo_sdk}), \
             patch('src.futures.analyzer.settings') as mock_settings:
            mock_settings.fubon.has_api_key_auth.return_value = True
            mock_settings.fubon.user_id = 'A123456789'
            mock_settings.fubon.api_key = 'testkey'
            mock_settings.fubon.cert_path = '/tmp/test.p12'
            mock_settings.fubon.cert_password = 'A123456789'

            result = analyzer._get_taiex_from_fubon()

        assert result is None

    def test_returns_none_when_api_raises(self, analyzer):
        """SDK 拋出例外時應回傳 None 而不是拋出"""
        mock_fubon_neo_sdk = MagicMock()
        mock_fubon_neo_sdk.FubonSDK = MagicMock(side_effect=Exception("SDK error"))
        with patch.dict(sys.modules, {'fubon_neo': MagicMock(), 'fubon_neo.sdk': mock_fubon_neo_sdk}), \
             patch('src.futures.analyzer.settings') as mock_settings:
            mock_settings.fubon.has_api_key_auth.return_value = True
            mock_settings.fubon.user_id = 'A123456789'
            mock_settings.fubon.api_key = 'testkey'
            mock_settings.fubon.cert_path = '/tmp/test.p12'
            mock_settings.fubon.cert_password = 'A123456789'

            result = analyzer._get_taiex_from_fubon()

        assert result is None

    def test_get_taiex_index_data_falls_back_to_fubon(self, analyzer):
        """TWSE 和 yfinance 都失敗時，應 fallback 到 Fubon SDK"""
        with patch.object(analyzer, '_get_taiex_from_twse', return_value=None), \
             patch.object(analyzer, '_get_taiex_from_yfinance', return_value=None), \
             patch.object(analyzer, '_get_taiex_from_fubon', return_value={
                 'symbol': 'TAIEX',
                 'current_price': 37000.0,
                 'change': 150.0,
                 'change_percent': 0.41,
                 'volume': 0,
                 'high': 37200.0,
                 'low': 36700.0,
                 'timestamp': datetime.now(),
             }) as mock_fubon:
            result = analyzer.get_taiex_index_data()

        assert result is not None
        assert result['symbol'] == 'TAIEX'
        mock_fubon.assert_called_once()
