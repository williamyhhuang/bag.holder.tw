"""
Stock filtering system for screening and selection
"""
from typing import List, Dict, Optional, Callable, Any
from decimal import Decimal
from datetime import date, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from ..database.connection import db_manager
from ..database.models import Stock, StockPrice, StockRealtime, TechnicalIndicator
from ..utils.logger import get_logger

logger = get_logger(__name__)

class FilterOperator(Enum):
    """Filter operators for comparisons"""
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_EQUAL = "gte"
    LESS_EQUAL = "lte"
    EQUAL = "eq"
    NOT_EQUAL = "ne"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"

@dataclass
class FilterCriteria:
    """Filter criteria definition"""
    field: str
    operator: FilterOperator
    value: Any
    value2: Optional[Any] = None  # For BETWEEN operator

@dataclass
class FilterResult:
    """Filter result with stock and matching values"""
    stock: Stock
    matched_values: Dict[str, Any]
    score: float = 0.0

class StockFilter:
    """Base stock filtering system"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def filter_stocks(
        self,
        criteria_list: List[FilterCriteria],
        markets: List[str] = None,
        limit: int = None,
        sort_by: str = None,
        sort_desc: bool = True
    ) -> List[FilterResult]:
        """
        Filter stocks based on multiple criteria

        Args:
            criteria_list: List of filter criteria
            markets: Markets to filter (TSE, OTC)
            limit: Maximum number of results
            sort_by: Field to sort by
            sort_desc: Sort in descending order

        Returns:
            List of FilterResult objects
        """
        try:
            with db_manager.get_session() as session:
                results = []

                # Get base query for active stocks
                base_query = session.query(Stock).filter(Stock.is_active == True)

                if markets:
                    base_query = base_query.filter(Stock.market.in_(markets))

                stocks = base_query.all()

                for stock in stocks:
                    # Check if stock meets all criteria
                    matched_values = {}
                    meets_criteria = True

                    for criteria in criteria_list:
                        value = self._get_stock_value(session, stock, criteria.field)

                        if value is None:
                            meets_criteria = False
                            break

                        if not self._evaluate_criteria(value, criteria):
                            meets_criteria = False
                            break

                        matched_values[criteria.field] = value

                    if meets_criteria:
                        score = self._calculate_score(matched_values, criteria_list)
                        results.append(FilterResult(
                            stock=stock,
                            matched_values=matched_values,
                            score=score
                        ))

                # Sort results
                if sort_by and sort_by in results[0].matched_values if results else False:
                    results.sort(
                        key=lambda x: x.matched_values.get(sort_by, 0),
                        reverse=sort_desc
                    )
                elif sort_by == 'score':
                    results.sort(key=lambda x: x.score, reverse=sort_desc)

                # Apply limit
                if limit:
                    results = results[:limit]

                self.logger.info(f"Filter found {len(results)} stocks matching criteria")
                return results

        except Exception as e:
            self.logger.error(f"Error filtering stocks: {e}")
            return []

    def _get_stock_value(self, session: Session, stock: Stock, field: str) -> Any:
        """Get value for a specific field from stock data"""
        try:
            # Handle different data sources
            if field in ['symbol', 'name', 'market', 'industry']:
                return getattr(stock, field)

            elif field.startswith('price_'):
                # Real-time price fields
                realtime = session.query(StockRealtime).filter(
                    StockRealtime.stock_id == stock.id
                ).first()

                if realtime:
                    field_map = {
                        'price_current': realtime.current_price,
                        'price_change': realtime.change_amount,
                        'price_change_pct': realtime.change_percent,
                        'volume': realtime.volume
                    }
                    return field_map.get(field)

            elif field.startswith('ma') or field.startswith('rsi') or field.startswith('macd') or field.startswith('bb'):
                # Technical indicator fields
                indicator = session.query(TechnicalIndicator).filter(
                    TechnicalIndicator.stock_id == stock.id
                ).order_by(desc(TechnicalIndicator.date)).first()

                if indicator:
                    return getattr(indicator, field, None)

            elif field.startswith('hist_'):
                # Historical data fields
                return self._get_historical_value(session, stock, field)

            return None

        except Exception as e:
            self.logger.error(f"Error getting value for field {field}: {e}")
            return None

    def _get_historical_value(self, session: Session, stock: Stock, field: str) -> Any:
        """Get historical data values"""
        try:
            if field == 'hist_avg_volume_20':
                # 20-day average volume
                cutoff_date = date.today() - timedelta(days=30)
                prices = session.query(StockPrice).filter(
                    and_(
                        StockPrice.stock_id == stock.id,
                        StockPrice.date >= cutoff_date
                    )
                ).order_by(desc(StockPrice.date)).limit(20).all()

                if len(prices) >= 20:
                    total_volume = sum(price.volume for price in prices)
                    return total_volume / len(prices)

            elif field == 'hist_price_change_5d':
                # 5-day price change percentage
                today_price = session.query(StockPrice).filter(
                    StockPrice.stock_id == stock.id
                ).order_by(desc(StockPrice.date)).first()

                old_price = session.query(StockPrice).filter(
                    StockPrice.stock_id == stock.id
                ).order_by(desc(StockPrice.date)).offset(5).first()

                if today_price and old_price:
                    change = (today_price.close_price - old_price.close_price) / old_price.close_price * 100
                    return change

            return None

        except Exception as e:
            self.logger.error(f"Error getting historical value: {e}")
            return None

    def _evaluate_criteria(self, value: Any, criteria: FilterCriteria) -> bool:
        """Evaluate if value meets criteria"""
        try:
            if value is None:
                return False

            op = criteria.operator
            target = criteria.value

            if op == FilterOperator.GREATER_THAN:
                return value > target
            elif op == FilterOperator.LESS_THAN:
                return value < target
            elif op == FilterOperator.GREATER_EQUAL:
                return value >= target
            elif op == FilterOperator.LESS_EQUAL:
                return value <= target
            elif op == FilterOperator.EQUAL:
                return value == target
            elif op == FilterOperator.NOT_EQUAL:
                return value != target
            elif op == FilterOperator.BETWEEN:
                return target <= value <= criteria.value2
            elif op == FilterOperator.IN:
                return value in target
            elif op == FilterOperator.NOT_IN:
                return value not in target

            return False

        except Exception as e:
            self.logger.error(f"Error evaluating criteria: {e}")
            return False

    def _calculate_score(self, matched_values: Dict[str, Any], criteria_list: List[FilterCriteria]) -> float:
        """Calculate relevance score for matched stock"""
        score = 0.0

        try:
            # Score based on various factors
            for criteria in criteria_list:
                field = criteria.field
                value = matched_values.get(field)

                if value is None:
                    continue

                # Add scoring logic based on field type
                if field == 'rsi14':
                    # Prefer extreme RSI values
                    rsi_val = float(value)
                    if rsi_val < 30:
                        score += 10  # Oversold
                    elif rsi_val > 70:
                        score += 10  # Overbought
                elif field == 'volume':
                    # Higher volume gets more points
                    volume_val = int(value)
                    if volume_val > 1000000:
                        score += 5
                elif field.startswith('price_change_pct'):
                    # Significant price changes
                    change = abs(float(value))
                    if change > 5:
                        score += 8
                    elif change > 3:
                        score += 5

            return score

        except Exception as e:
            self.logger.error(f"Error calculating score: {e}")
            return 0.0

class PresetFilters:
    """Predefined filter presets for common screening scenarios"""

    @staticmethod
    def momentum_stocks() -> List[FilterCriteria]:
        """Momentum stocks filter"""
        return [
            FilterCriteria('price_change_pct', FilterOperator.GREATER_THAN, Decimal('3.0')),
            FilterCriteria('volume', FilterOperator.GREATER_THAN, 500000),
            FilterCriteria('rsi14', FilterOperator.GREATER_THAN, Decimal('50.0')),
            FilterCriteria('ma5', FilterOperator.GREATER_THAN, Decimal('0')),  # MA5 > 0 (valid data)
        ]

    @staticmethod
    def oversold_stocks() -> List[FilterCriteria]:
        """Oversold stocks filter"""
        return [
            FilterCriteria('rsi14', FilterOperator.LESS_THAN, Decimal('30.0')),
            FilterCriteria('price_change_pct', FilterOperator.LESS_THAN, Decimal('-2.0')),
            FilterCriteria('volume', FilterOperator.GREATER_THAN, 300000),
        ]

    @staticmethod
    def breakout_stocks() -> List[FilterCriteria]:
        """Breakout stocks filter"""
        return [
            FilterCriteria('price_current', FilterOperator.GREATER_THAN, Decimal('0')),  # Valid price
            FilterCriteria('volume', FilterOperator.GREATER_THAN, 1000000),  # High volume
            FilterCriteria('ma5', FilterOperator.GREATER_THAN, Decimal('0')),  # Valid MA5
        ]

    @staticmethod
    def value_stocks() -> List[FilterCriteria]:
        """Value stocks filter (simplified)"""
        return [
            FilterCriteria('price_change_pct', FilterOperator.BETWEEN, Decimal('-5.0'), Decimal('5.0')),
            FilterCriteria('volume', FilterOperator.GREATER_THAN, 200000),
            FilterCriteria('rsi14', FilterOperator.BETWEEN, Decimal('40.0'), Decimal('60.0')),
        ]

    @staticmethod
    def high_volume_stocks() -> List[FilterCriteria]:
        """High volume stocks filter"""
        return [
            FilterCriteria('volume', FilterOperator.GREATER_THAN, 2000000),
            FilterCriteria('price_current', FilterOperator.GREATER_THAN, Decimal('10.0')),
        ]

    @staticmethod
    def tech_stocks() -> List[FilterCriteria]:
        """Technology sector stocks"""
        return [
            FilterCriteria('industry', FilterOperator.IN, ['半導體', '電子', '通信']),
            FilterCriteria('market', FilterOperator.EQUAL, 'TSE'),
        ]

class MarketScreener:
    """Advanced market screening with multiple filters"""

    def __init__(self):
        self.stock_filter = StockFilter()
        self.logger = get_logger(self.__class__.__name__)

    def screen_market(
        self,
        preset_name: str = None,
        custom_criteria: List[FilterCriteria] = None,
        markets: List[str] = ['TSE', 'OTC'],
        limit: int = 50
    ) -> List[FilterResult]:
        """
        Screen market with preset or custom criteria

        Args:
            preset_name: Name of preset filter
            custom_criteria: Custom filter criteria
            markets: Markets to screen
            limit: Maximum results

        Returns:
            List of FilterResult objects
        """
        try:
            # Get criteria
            if preset_name:
                criteria = self._get_preset_criteria(preset_name)
            elif custom_criteria:
                criteria = custom_criteria
            else:
                criteria = PresetFilters.momentum_stocks()  # Default

            if not criteria:
                self.logger.error(f"Unknown preset: {preset_name}")
                return []

            # Apply filter
            results = self.stock_filter.filter_stocks(
                criteria_list=criteria,
                markets=markets,
                limit=limit,
                sort_by='score',
                sort_desc=True
            )

            self.logger.info(f"Market screen '{preset_name or 'custom'}' found {len(results)} stocks")
            return results

        except Exception as e:
            self.logger.error(f"Error in market screening: {e}")
            return []

    def _get_preset_criteria(self, preset_name: str) -> List[FilterCriteria]:
        """Get criteria for preset name"""
        preset_map = {
            'momentum': PresetFilters.momentum_stocks,
            'oversold': PresetFilters.oversold_stocks,
            'breakout': PresetFilters.breakout_stocks,
            'value': PresetFilters.value_stocks,
            'high_volume': PresetFilters.high_volume_stocks,
            'tech': PresetFilters.tech_stocks,
        }

        if preset_name in preset_map:
            return preset_map[preset_name]()

        return []

    def get_available_presets(self) -> List[str]:
        """Get list of available preset names"""
        return ['momentum', 'oversold', 'breakout', 'value', 'high_volume', 'tech']

    def screen_for_signals(self) -> Dict[str, List[FilterResult]]:
        """Screen market for different signal types"""
        results = {}

        signal_presets = [
            ('momentum', '動能股'),
            ('oversold', '超賣股'),
            ('breakout', '突破股'),
            ('high_volume', '高量股')
        ]

        for preset, description in signal_presets:
            try:
                stocks = self.screen_market(preset_name=preset, limit=20)
                results[description] = stocks
                self.logger.info(f"{description}: {len(stocks)} stocks found")
            except Exception as e:
                self.logger.error(f"Error screening {description}: {e}")
                results[description] = []

        return results