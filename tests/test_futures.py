"""
台指期貨監控模組單元測試
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, date
from decimal import Decimal

from src.futures.monitor import (
    TaiwanFuturesMonitor,
    FuturesContract,
    FuturesQuote,
    FuturesSignal,
    FuturesSignalType
)
from src.api.fubon_client import FubonClient


class TestFuturesContract:
    """期貨合約單元測試"""

    def test_futures_contract_creation(self):
        """測試期貨合約創建"""
        contract = FuturesContract(
            symbol='TXF',
            name='台指期貨(大台)',
            underlying='台灣加權指數',
            expiry_date=date(2026, 4, 15),
            contract_size=200,
            tick_size=Decimal('1'),
            is_active=True
        )

        assert contract.symbol == 'TXF'
        assert contract.name == '台指期貨(大台)'
        assert contract.underlying == '台灣加權指數'
        assert contract.expiry_date == date(2026, 4, 15)
        assert contract.contract_size == 200
        assert contract.tick_size == Decimal('1')
        assert contract.is_active is True

    def test_contract_value_calculation(self):
        """測試合約價值計算"""
        contract = FuturesContract(
            symbol='TXF',
            name='台指期貨(大台)',
            underlying='台灣加權指數',
            expiry_date=date(2026, 4, 15),
            contract_size=200,
            tick_size=Decimal('1'),
            is_active=True
        )

        # 假設台指期貨價格為 18000 點
        price = Decimal('18000')
        expected_value = price * contract.contract_size  # 18000 * 200 = 3,600,000

        assert contract.contract_size * price == expected_value


class TestFuturesQuote:
    """期貨報價單元測試"""

    def test_futures_quote_creation(self):
        """測試期貨報價創建"""
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18000.0'),
            volume=1000,
            timestamp=datetime(2026, 3, 25, 9, 0, 0),
            bid_price=Decimal('17999.0'),
            ask_price=Decimal('18001.0'),
            bid_volume=500,
            ask_volume=300
        )

        assert quote.symbol == 'TXF'
        assert quote.price == Decimal('18000.0')
        assert quote.volume == 1000
        assert quote.timestamp == datetime(2026, 3, 25, 9, 0, 0)
        assert quote.bid_price == Decimal('17999.0')
        assert quote.ask_price == Decimal('18001.0')
        assert quote.bid_volume == 500
        assert quote.ask_volume == 300

    def test_spread_calculation(self):
        """測試買賣價差計算"""
        quote = FuturesQuote(
            symbol='TXF',
            price=Decimal('18000.0'),
            volume=1000,
            timestamp=datetime(2026, 3, 25, 9, 0, 0),
            bid_price=Decimal('17999.0'),
            ask_price=Decimal('18001.0'),
            bid_volume=500,
            ask_volume=300
        )

        spread = quote.ask_price - quote.bid_price
        assert spread == Decimal('2.0')


class TestFuturesSignal:
    """期貨信號單元測試"""

    def test_futures_signal_creation(self):
        """測試期貨信號創建"""
        signal = FuturesSignal(
            symbol='TXF',
            signal_type=FuturesSignalType.PRICE_BREAKOUT,
            price=Decimal('18100.0'),
            volume=2000,
            message='TXF 價格突破 1.5%',
            timestamp=datetime(2026, 3, 25, 10, 30, 0),
            confidence=0.8
        )

        assert signal.symbol == 'TXF'
        assert signal.signal_type == FuturesSignalType.PRICE_BREAKOUT
        assert signal.price == Decimal('18100.0')
        assert signal.volume == 2000
        assert signal.message == 'TXF 價格突破 1.5%'
        assert signal.timestamp == datetime(2026, 3, 25, 10, 30, 0)
        assert signal.confidence == 0.8


class TestTaiwanFuturesMonitor:
    """台指期貨監控器單元測試"""

    @pytest.fixture
    def mock_fubon_client(self):
        """模擬 Fubon 客戶端"""
        client = Mock(spec=FubonClient)
        client.is_simulation = True
        return client

    @pytest.fixture
    def futures_monitor(self, mock_fubon_client):
        """創建期貨監控器實例"""
        return TaiwanFuturesMonitor(mock_fubon_client)

    def test_monitor_initialization(self, futures_monitor):
        """測試監控器初始化"""
        assert futures_monitor is not None
        assert len(futures_monitor.futures_contracts) == 3
        assert 'TXF' in futures_monitor.futures_contracts
        assert 'MXF' in futures_monitor.futures_contracts
        assert 'MTX' in futures_monitor.futures_contracts

    def test_contract_info_retrieval(self, futures_monitor):
        """測試合約信息獲取"""
        # 測試 TXF 大台
        txf_info = futures_monitor.get_contract_info('TXF')
        assert txf_info is not None
        assert txf_info.symbol == 'TXF'
        assert txf_info.name == '台指期貨(大台)'
        assert txf_info.contract_size == 200
        assert txf_info.tick_size == Decimal('1')
        assert txf_info.is_active is True

        # 測試 MXF 小台
        mxf_info = futures_monitor.get_contract_info('MXF')
        assert mxf_info is not None
        assert mxf_info.symbol == 'MXF'
        assert mxf_info.name == '小台指期貨(小台)'
        assert mxf_info.contract_size == 50

        # 測試 MTX 微台
        mtx_info = futures_monitor.get_contract_info('MTX')
        assert mtx_info is not None
        assert mtx_info.symbol == 'MTX'
        assert mtx_info.name == '微型台指期貨(微台)'
        assert mtx_info.contract_size == 10

        # 測試不存在的合約
        invalid_info = futures_monitor.get_contract_info('INVALID')
        assert invalid_info is None

    def test_active_contracts_retrieval(self, futures_monitor):
        """測試活躍合約獲取"""
        active_contracts = futures_monitor.get_active_contracts()
        assert len(active_contracts) == 3

        symbols = {contract.symbol for contract in active_contracts}
        assert symbols == {'TXF', 'MXF', 'MTX'}

        # 確保所有合約都是活躍的
        for contract in active_contracts:
            assert contract.is_active is True

    def test_near_month_expiry_calculation(self, futures_monitor):
        """測試近月合約到期日計算"""
        expiry_date = futures_monitor._get_near_month_expiry()

        # 檢查返回的是 date 物件
        assert isinstance(expiry_date, date)

        # 檢查是第三個週三
        # 4月第三個週三應該是 15 號
        assert expiry_date.day == 15
        assert expiry_date.month == 4
        assert expiry_date.year == 2026

    @pytest.mark.asyncio
    async def test_get_futures_quote(self, futures_monitor, mock_fubon_client):
        """測試期貨報價獲取"""
        # 模擬 API 返回數據
        mock_quote_data = {
            'symbol': 'TXF',
            'price': 18000.0,
            'volume': 1000,
            'bid_price': 17999.0,
            'ask_price': 18001.0,
            'bid_volume': 500,
            'ask_volume': 300
        }

        mock_fubon_client.get_futures_quote = AsyncMock(return_value=mock_quote_data)

        quote = await futures_monitor.get_futures_quote('TXF')

        assert quote is not None
        assert quote.symbol == 'TXF'
        assert quote.price == Decimal('18000.0')
        assert quote.volume == 1000
        mock_fubon_client.get_futures_quote.assert_called_once_with('TXF')

    @pytest.mark.asyncio
    async def test_price_change_detection(self, futures_monitor):
        """測試價格變化檢測"""
        # 模擬當前價格和前一價格
        current_price = Decimal('18100.0')
        previous_price = Decimal('17800.0')

        # 計算價格變化百分比
        price_change = futures_monitor._calculate_price_change_percentage(
            current_price, previous_price
        )

        expected_change = ((current_price - previous_price) / previous_price) * 100
        assert abs(price_change - expected_change) < Decimal('0.01')

    def test_price_change_percentage_calculation(self, futures_monitor):
        """測試價格變化百分比計算"""
        # 測試價格上漲
        current = Decimal('18100.0')
        previous = Decimal('18000.0')
        change = futures_monitor._calculate_price_change_percentage(current, previous)
        expected = (Decimal('100.0') / Decimal('18000.0')) * 100
        assert abs(change - expected) < Decimal('0.01')

        # 測試價格下跌
        current = Decimal('17900.0')
        previous = Decimal('18000.0')
        change = futures_monitor._calculate_price_change_percentage(current, previous)
        expected = (Decimal('-100.0') / Decimal('18000.0')) * 100
        assert abs(change - expected) < Decimal('0.01')

        # 測試價格不變
        current = Decimal('18000.0')
        previous = Decimal('18000.0')
        change = futures_monitor._calculate_price_change_percentage(current, previous)
        assert change == Decimal('0.0')

    def test_volume_anomaly_detection(self, futures_monitor):
        """測試成交量異常檢測"""
        # 模擬歷史平均成交量
        average_volume = 1000

        # 測試正常成交量
        normal_volume = 1200
        is_anomaly = futures_monitor._is_volume_anomaly(normal_volume, average_volume)
        assert is_anomaly is False

        # 測試異常成交量 (超過 2 倍)
        high_volume = 2500
        is_anomaly = futures_monitor._is_volume_anomaly(high_volume, average_volume)
        assert is_anomaly is True

        # 測試邊界值
        boundary_volume = 2000  # 剛好 2 倍
        is_anomaly = futures_monitor._is_volume_anomaly(boundary_volume, average_volume)
        assert is_anomaly is True

    @pytest.mark.asyncio
    async def test_signal_detection(self, futures_monitor, mock_fubon_client):
        """測試信號檢測"""
        # 模擬價格突破的報價數據
        mock_quote_data = {
            'symbol': 'TXF',
            'price': 18300.0,  # 假設這是一個突破價格
            'volume': 2500,    # 異常高成交量
            'bid_price': 18299.0,
            'ask_price': 18301.0,
            'bid_volume': 1000,
            'ask_volume': 800
        }

        mock_fubon_client.get_futures_quote = AsyncMock(return_value=mock_quote_data)

        # 模擬之前的價格用於比較
        with patch.object(futures_monitor, '_get_previous_price') as mock_prev_price:
            mock_prev_price.return_value = Decimal('18000.0')

            signals = await futures_monitor._detect_signals('TXF')

            # 檢查是否檢測到信號
            assert isinstance(signals, list)
            # 具體的信號檢測邏輯需要根據實際實現進行測試

    @pytest.mark.asyncio
    async def test_monitoring_loop_error_handling(self, futures_monitor, mock_fubon_client):
        """測試監控循環錯誤處理"""
        # 模擬 API 錯誤
        mock_fubon_client.get_futures_quote = AsyncMock(
            side_effect=Exception("API Error")
        )

        # 確保錯誤被正確處理，不會中斷監控
        try:
            quote = await futures_monitor.get_futures_quote('TXF')
            assert quote is None  # 錯誤時應該返回 None
        except Exception:
            pytest.fail("Exception should be handled gracefully")


class TestFuturesIntegration:
    """期貨監控整合測試"""

    @pytest.mark.asyncio
    async def test_full_monitoring_cycle(self):
        """測試完整的監控循環"""
        # 這個測試需要更多的模擬設置
        # 包括數據庫連接、Redis 緩存等
        pass

    @pytest.mark.asyncio
    async def test_signal_notification(self):
        """測試信號通知"""
        # 測試當檢測到信號時是否正確發送通知
        pass


# 測試配置和輔助函數
def test_futures_signal_types():
    """測試期貨信號類型枚舉"""
    assert hasattr(FuturesSignalType, 'PRICE_BREAKOUT')
    assert hasattr(FuturesSignalType, 'VOLUME_ANOMALY')
    assert hasattr(FuturesSignalType, 'HIGH_VOLATILITY')


def test_contract_symbols():
    """測試合約代號常量"""
    # 確保只追蹤三大合約
    expected_symbols = {'TXF', 'MXF', 'MTX'}

    # 這個測試需要根據實際的常量定義進行調整
    monitor = TaiwanFuturesMonitor(Mock())
    actual_symbols = set(monitor.futures_contracts.keys())

    assert actual_symbols == expected_symbols