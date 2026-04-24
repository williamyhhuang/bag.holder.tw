"""
Technical indicators calculation engine (domain service - no external dependencies)
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import date, datetime

import talib

from ...utils.logger import get_logger
from ...utils.error_handler import handle_errors, ApplicationError
from ..models.stock import StockData

logger = get_logger(__name__)

class IndicatorCalculator:
    """Technical indicators calculation engine"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors(default_return_value={})
    def calculate_all_indicators(
        self,
        price_data: List[StockData],
        ma_periods: List[int] = [5, 10, 20, 60],
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std_dev: float = 2.0
    ) -> Dict[date, Dict[str, Decimal]]:
        """
        Calculate all technical indicators for given price data

        Args:
            price_data: List of StockData objects
            ma_periods: Moving average periods
            rsi_period: RSI calculation period
            macd_fast: MACD fast period
            macd_slow: MACD slow period
            macd_signal: MACD signal line period
            bb_period: Bollinger Bands period
            bb_std_dev: Bollinger Bands standard deviation

        Returns:
            Dictionary mapping dates to indicator values
        """
        if not price_data or len(price_data) < max(ma_periods + [rsi_period, macd_slow, bb_period]):
            self.logger.warning(f"Insufficient data for indicator calculation: {len(price_data)} records")
            return {}

        # Convert to pandas DataFrame
        df = self._to_dataframe(price_data)

        if df.empty:
            return {}

        results = {}

        try:
            # Calculate indicators
            ma_data = self._calculate_moving_averages(df, ma_periods)
            rsi_data = self._calculate_rsi(df, rsi_period)
            macd_data = self._calculate_macd(df, macd_fast, macd_slow, macd_signal)
            bb_data = self._calculate_bollinger_bands(df, bb_period, bb_std_dev)
            volume_ma = self._calculate_volume_ma(df, 20)

            # Combine all indicators by date
            for idx, (i, row) in enumerate(df.iterrows()):
                trade_date = i.date() if hasattr(i, 'date') else i  # convert Timestamp to date

                indicators = {
                    'ma5': ma_data.get('ma5', {}).get(idx),
                    'ma10': ma_data.get('ma10', {}).get(idx),
                    'ma20': ma_data.get('ma20', {}).get(idx),
                    'ma60': ma_data.get('ma60', {}).get(idx),
                    'rsi14': rsi_data.get(idx),
                    'macd': macd_data.get('macd', {}).get(idx),
                    'macd_signal': macd_data.get('signal', {}).get(idx),
                    'macd_histogram': macd_data.get('histogram', {}).get(idx),
                    'bb_upper': bb_data.get('upper', {}).get(idx),
                    'bb_middle': bb_data.get('middle', {}).get(idx),
                    'bb_lower': bb_data.get('lower', {}).get(idx),
                    'volume_ma20': volume_ma.get(idx)
                }

                # Convert to Decimal and filter None values
                filtered_indicators = {}
                for key, value in indicators.items():
                    if value is not None and not (isinstance(value, float) and np.isnan(value)):
                        if key == 'volume_ma20':
                            filtered_indicators[key] = int(value) if value > 0 else None
                        else:
                            filtered_indicators[key] = Decimal(str(round(float(value), 4)))

                if filtered_indicators:
                    results[trade_date] = filtered_indicators

            self.logger.info(f"Calculated indicators for {len(results)} dates")
            return results

        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            raise ApplicationError(f"Indicator calculation failed: {e}")

    def _to_dataframe(self, price_data: List[StockData]) -> pd.DataFrame:
        """Convert StockData list to pandas DataFrame"""
        data = []
        for price in sorted(price_data, key=lambda x: x.date):
            data.append({
                'date': price.date,
                'open': float(price.open_price),
                'high': float(price.high_price),
                'low': float(price.low_price),
                'close': float(price.close_price),
                'volume': int(price.volume)
            })

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date') if not df.empty else df

    def _calculate_moving_averages(self, df: pd.DataFrame, periods: List[int]) -> Dict[str, Dict[int, float]]:
        """Calculate moving averages"""
        results = {}

        for period in periods:
            if len(df) >= period:
                ma_values = talib.SMA(df['close'].values, timeperiod=period)
                results[f'ma{period}'] = {i: val for i, val in enumerate(ma_values) if not np.isnan(val)}

        return results

    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> Dict[int, float]:
        """Calculate RSI"""
        if len(df) >= period:
            rsi_values = talib.RSI(df['close'].values, timeperiod=period)
            return {i: val for i, val in enumerate(rsi_values) if not np.isnan(val)}
        return {}

    def _calculate_macd(self, df: pd.DataFrame, fast: int, slow: int, signal: int) -> Dict[str, Dict[int, float]]:
        """Calculate MACD"""
        if len(df) >= slow:
            macd_line, signal_line, histogram = talib.MACD(
                df['close'].values,
                fastperiod=fast,
                slowperiod=slow,
                signalperiod=signal
            )

            return {
                'macd': {i: val for i, val in enumerate(macd_line) if not np.isnan(val)},
                'signal': {i: val for i, val in enumerate(signal_line) if not np.isnan(val)},
                'histogram': {i: val for i, val in enumerate(histogram) if not np.isnan(val)}
            }
        return {'macd': {}, 'signal': {}, 'histogram': {}}

    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int, std_dev: float) -> Dict[str, Dict[int, float]]:
        """Calculate Bollinger Bands"""
        if len(df) >= period:
            upper, middle, lower = talib.BBANDS(
                df['close'].values,
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev
            )

            return {
                'upper': {i: val for i, val in enumerate(upper) if not np.isnan(val)},
                'middle': {i: val for i, val in enumerate(middle) if not np.isnan(val)},
                'lower': {i: val for i, val in enumerate(lower) if not np.isnan(val)}
            }
        return {'upper': {}, 'middle': {}, 'lower': {}}

    def _calculate_volume_ma(self, df: pd.DataFrame, period: int) -> Dict[int, float]:
        """Calculate volume moving average"""
        if len(df) >= period:
            volume_ma = talib.SMA(df['volume'].values.astype(float), timeperiod=period)
            return {i: val for i, val in enumerate(volume_ma) if not np.isnan(val)}
        return {}
