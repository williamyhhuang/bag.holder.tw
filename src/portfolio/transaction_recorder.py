"""
Advanced transaction recording and analysis system
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from ..database.connection import db_manager
from ..database.models import Portfolio, Transaction, Stock
from ..utils.logger import get_logger
from ..utils.error_handler import handle_errors, ApplicationError

logger = get_logger(__name__)

class TransactionMethod(Enum):
    """Transaction recording methods"""
    FIFO = "FIFO"  # First In, First Out
    LIFO = "LIFO"  # Last In, First Out
    HIFO = "HIFO"  # Highest In, First Out
    LOFO = "LOFO"  # Lowest In, First Out
    AVERAGE = "AVERAGE"  # Average Cost

@dataclass
class TransactionRecord:
    """Detailed transaction record"""
    transaction_id: str
    stock_symbol: str
    stock_name: str
    transaction_type: str
    quantity: int
    price: Decimal
    total_amount: Decimal
    fee: Decimal
    tax: Decimal
    transaction_date: date
    notes: Optional[str]
    created_at: datetime

@dataclass
class RealizedGain:
    """Realized gain/loss calculation"""
    stock_symbol: str
    quantity_sold: int
    avg_buy_price: Decimal
    sell_price: Decimal
    gross_proceeds: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    holding_period_days: int
    is_long_term: bool  # > 1 year

class TransactionRecorder:
    """Advanced transaction recording with tax optimization"""

    def __init__(self, method: TransactionMethod = TransactionMethod.FIFO):
        self.method = method
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def record_buy_transaction(
        self,
        portfolio_id: str,
        stock_symbol: str,
        quantity: int,
        price: Decimal,
        transaction_date: date = None,
        fee: Decimal = None,
        tax: Decimal = None,
        notes: str = None,
        source: str = "manual"
    ) -> Optional[str]:
        """
        Record a buy transaction with detailed tracking

        Args:
            portfolio_id: Portfolio ID
            stock_symbol: Stock symbol
            quantity: Number of shares
            price: Purchase price per share
            transaction_date: Transaction date
            fee: Brokerage fees
            tax: Transaction taxes
            notes: Optional notes
            source: Transaction source (manual, import, auto)

        Returns:
            Transaction ID if successful
        """
        try:
            if transaction_date is None:
                transaction_date = date.today()

            fee = fee or Decimal('0')
            tax = tax or Decimal('0')

            with db_manager.get_session() as session:
                # Validate portfolio
                portfolio = session.query(Portfolio).filter(
                    Portfolio.id == portfolio_id
                ).first()
                if not portfolio:
                    raise ApplicationError(f"Portfolio not found: {portfolio_id}")

                # Validate stock
                stock = session.query(Stock).filter(
                    Stock.symbol == stock_symbol
                ).first()
                if not stock:
                    raise ApplicationError(f"Stock not found: {stock_symbol}")

                # Calculate total amount (cost basis + fees)
                total_amount = (price * quantity) + fee + tax

                # Create transaction
                transaction = Transaction(
                    portfolio_id=portfolio_id,
                    stock_id=stock.id,
                    transaction_type='BUY',
                    quantity=quantity,
                    price=price,
                    fee=fee,
                    tax=tax,
                    total_amount=total_amount,
                    transaction_date=transaction_date,
                    notes=f"[{source}] {notes}" if notes else f"[{source}]"
                )

                session.add(transaction)
                session.commit()

                self.logger.info(
                    f"Recorded BUY: {stock_symbol} {quantity}@{price} = ${total_amount}"
                )
                return str(transaction.id)

        except Exception as e:
            self.logger.error(f"Error recording buy transaction: {e}")
            raise

    @handle_errors()
    def record_sell_transaction(
        self,
        portfolio_id: str,
        stock_symbol: str,
        quantity: int,
        price: Decimal,
        transaction_date: date = None,
        fee: Decimal = None,
        tax: Decimal = None,
        notes: str = None,
        source: str = "manual"
    ) -> Tuple[Optional[str], List[RealizedGain]]:
        """
        Record a sell transaction and calculate realized gains

        Args:
            portfolio_id: Portfolio ID
            stock_symbol: Stock symbol
            quantity: Number of shares to sell
            price: Sale price per share
            transaction_date: Transaction date
            fee: Brokerage fees
            tax: Transaction taxes
            notes: Optional notes
            source: Transaction source

        Returns:
            Tuple of (Transaction ID, List of realized gains)
        """
        try:
            if transaction_date is None:
                transaction_date = date.today()

            fee = fee or Decimal('0')
            tax = tax or Decimal('0')

            with db_manager.get_session() as session:
                # Validate portfolio and stock
                portfolio = session.query(Portfolio).filter(
                    Portfolio.id == portfolio_id
                ).first()
                if not portfolio:
                    raise ApplicationError(f"Portfolio not found: {portfolio_id}")

                stock = session.query(Stock).filter(
                    Stock.symbol == stock_symbol
                ).first()
                if not stock:
                    raise ApplicationError(f"Stock not found: {stock_symbol}")

                # Check available shares
                available_shares = self._get_available_shares(session, portfolio_id, stock.id)
                if available_shares < quantity:
                    raise ApplicationError(
                        f"Insufficient shares: have {available_shares}, selling {quantity}"
                    )

                # Calculate net proceeds
                gross_proceeds = price * quantity
                net_proceeds = gross_proceeds - fee - tax

                # Create transaction
                transaction = Transaction(
                    portfolio_id=portfolio_id,
                    stock_id=stock.id,
                    transaction_type='SELL',
                    quantity=quantity,
                    price=price,
                    fee=fee,
                    tax=tax,
                    total_amount=net_proceeds,
                    transaction_date=transaction_date,
                    notes=f"[{source}] {notes}" if notes else f"[{source}]"
                )

                session.add(transaction)

                # Calculate realized gains based on method
                realized_gains = self._calculate_realized_gains(
                    session, portfolio_id, stock, quantity, price, transaction_date
                )

                session.commit()

                self.logger.info(
                    f"Recorded SELL: {stock_symbol} {quantity}@{price} = ${net_proceeds}"
                )

                return str(transaction.id), realized_gains

        except Exception as e:
            self.logger.error(f"Error recording sell transaction: {e}")
            raise

    def _get_available_shares(self, session: Session, portfolio_id: str, stock_id: str) -> int:
        """Get total available shares for a stock in portfolio"""
        transactions = session.query(Transaction).filter(
            and_(
                Transaction.portfolio_id == portfolio_id,
                Transaction.stock_id == stock_id
            )
        ).all()

        total_shares = 0
        for tx in transactions:
            if tx.transaction_type == 'BUY':
                total_shares += tx.quantity
            elif tx.transaction_type == 'SELL':
                total_shares -= tx.quantity

        return total_shares

    def _calculate_realized_gains(
        self,
        session: Session,
        portfolio_id: str,
        stock: Stock,
        quantity_sold: int,
        sell_price: Decimal,
        sell_date: date
    ) -> List[RealizedGain]:
        """Calculate realized gains using specified method"""
        try:
            # Get all buy transactions for this stock
            buy_transactions = session.query(Transaction).filter(
                and_(
                    Transaction.portfolio_id == portfolio_id,
                    Transaction.stock_id == stock.id,
                    Transaction.transaction_type == 'BUY',
                    Transaction.transaction_date <= sell_date
                )
            ).order_by(Transaction.transaction_date).all()

            if not buy_transactions:
                return []

            # Apply lot selection method
            if self.method == TransactionMethod.FIFO:
                buy_transactions.sort(key=lambda x: x.transaction_date)
            elif self.method == TransactionMethod.LIFO:
                buy_transactions.sort(key=lambda x: x.transaction_date, reverse=True)
            elif self.method == TransactionMethod.HIFO:
                buy_transactions.sort(key=lambda x: x.price, reverse=True)
            elif self.method == TransactionMethod.LOFO:
                buy_transactions.sort(key=lambda x: x.price)

            realized_gains = []
            remaining_to_sell = quantity_sold

            for buy_tx in buy_transactions:
                if remaining_to_sell <= 0:
                    break

                # Get available quantity from this buy transaction
                available_qty = self._get_available_from_transaction(
                    session, portfolio_id, stock.id, buy_tx.id, sell_date
                )

                if available_qty <= 0:
                    continue

                # Determine quantity to sell from this lot
                qty_from_lot = min(remaining_to_sell, available_qty)

                # Calculate holding period
                holding_period = (sell_date - buy_tx.transaction_date).days

                # Calculate realized gain/loss
                cost_basis_per_share = buy_tx.total_amount / buy_tx.quantity
                cost_basis_lot = cost_basis_per_share * qty_from_lot
                gross_proceeds_lot = sell_price * qty_from_lot
                realized_pnl = gross_proceeds_lot - cost_basis_lot

                gain = RealizedGain(
                    stock_symbol=stock.symbol,
                    quantity_sold=qty_from_lot,
                    avg_buy_price=cost_basis_per_share,
                    sell_price=sell_price,
                    gross_proceeds=gross_proceeds_lot,
                    cost_basis=cost_basis_lot,
                    realized_pnl=realized_pnl,
                    holding_period_days=holding_period,
                    is_long_term=holding_period > 365
                )

                realized_gains.append(gain)
                remaining_to_sell -= qty_from_lot

            return realized_gains

        except Exception as e:
            self.logger.error(f"Error calculating realized gains: {e}")
            return []

    def _get_available_from_transaction(
        self,
        session: Session,
        portfolio_id: str,
        stock_id: str,
        buy_transaction_id: str,
        before_date: date
    ) -> int:
        """Get available shares from a specific buy transaction"""
        # This is a simplified version - in practice, you'd track
        # lot assignments more precisely
        buy_tx = session.query(Transaction).filter(
            Transaction.id == buy_transaction_id
        ).first()

        if not buy_tx:
            return 0

        # For simplicity, assume shares are consumed in order
        # In practice, you'd maintain a lot tracking table
        return buy_tx.quantity  # Simplified

    @handle_errors()
    def import_transactions_from_csv(
        self,
        portfolio_id: str,
        csv_data: List[Dict[str, str]]
    ) -> Tuple[int, int, List[str]]:
        """
        Import transactions from CSV data

        Args:
            portfolio_id: Portfolio ID
            csv_data: List of transaction dictionaries

        Returns:
            Tuple of (success_count, error_count, error_messages)
        """
        success_count = 0
        error_count = 0
        errors = []

        for i, row in enumerate(csv_data, 1):
            try:
                # Parse CSV row
                stock_symbol = row.get('symbol', '').upper()
                transaction_type = row.get('type', '').upper()
                quantity = int(row.get('quantity', 0))
                price = Decimal(str(row.get('price', 0)))
                transaction_date = datetime.strptime(
                    row.get('date', ''), '%Y-%m-%d'
                ).date()
                fee = Decimal(str(row.get('fee', 0)))
                tax = Decimal(str(row.get('tax', 0)))
                notes = row.get('notes', f'CSV import row {i}')

                # Validate required fields
                if not stock_symbol or transaction_type not in ['BUY', 'SELL']:
                    raise ValueError(f"Invalid data in row {i}")

                # Record transaction
                if transaction_type == 'BUY':
                    self.record_buy_transaction(
                        portfolio_id=portfolio_id,
                        stock_symbol=stock_symbol,
                        quantity=quantity,
                        price=price,
                        transaction_date=transaction_date,
                        fee=fee,
                        tax=tax,
                        notes=notes,
                        source="csv_import"
                    )
                else:  # SELL
                    self.record_sell_transaction(
                        portfolio_id=portfolio_id,
                        stock_symbol=stock_symbol,
                        quantity=quantity,
                        price=price,
                        transaction_date=transaction_date,
                        fee=fee,
                        tax=tax,
                        notes=notes,
                        source="csv_import"
                    )

                success_count += 1

            except Exception as e:
                error_count += 1
                error_msg = f"Row {i}: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)

        self.logger.info(
            f"CSV import completed: {success_count} success, {error_count} errors"
        )

        return success_count, error_count, errors

    @handle_errors()
    def get_transaction_history(
        self,
        portfolio_id: str,
        stock_symbol: str = None,
        start_date: date = None,
        end_date: date = None,
        limit: int = None
    ) -> List[TransactionRecord]:
        """
        Get transaction history with filters

        Args:
            portfolio_id: Portfolio ID
            stock_symbol: Optional stock filter
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum number of records

        Returns:
            List of transaction records
        """
        try:
            with db_manager.get_session() as session:
                query = session.query(Transaction, Stock).join(
                    Stock, Transaction.stock_id == Stock.id
                ).filter(Transaction.portfolio_id == portfolio_id)

                # Apply filters
                if stock_symbol:
                    query = query.filter(Stock.symbol == stock_symbol.upper())

                if start_date:
                    query = query.filter(Transaction.transaction_date >= start_date)

                if end_date:
                    query = query.filter(Transaction.transaction_date <= end_date)

                # Order by date (newest first)
                query = query.order_by(desc(Transaction.transaction_date))

                # Apply limit
                if limit:
                    query = query.limit(limit)

                transactions = query.all()

                # Convert to TransactionRecord objects
                records = []
                for tx, stock in transactions:
                    record = TransactionRecord(
                        transaction_id=str(tx.id),
                        stock_symbol=stock.symbol,
                        stock_name=stock.name,
                        transaction_type=tx.transaction_type,
                        quantity=tx.quantity,
                        price=tx.price,
                        total_amount=tx.total_amount,
                        fee=tx.fee,
                        tax=tx.tax,
                        transaction_date=tx.transaction_date,
                        notes=tx.notes,
                        created_at=tx.created_at
                    )
                    records.append(record)

                return records

        except Exception as e:
            self.logger.error(f"Error getting transaction history: {e}")
            return []

    @handle_errors()
    def calculate_tax_report(
        self,
        portfolio_id: str,
        tax_year: int
    ) -> Dict[str, Decimal]:
        """
        Generate tax report for a given year

        Args:
            portfolio_id: Portfolio ID
            tax_year: Tax year (e.g., 2023)

        Returns:
            Tax report summary
        """
        try:
            start_date = date(tax_year, 1, 1)
            end_date = date(tax_year, 12, 31)

            # Get all sell transactions for the year
            sell_records = self.get_transaction_history(
                portfolio_id=portfolio_id,
                start_date=start_date,
                end_date=end_date
            )

            sell_transactions = [r for r in sell_records if r.transaction_type == 'SELL']

            if not sell_transactions:
                return {
                    'total_proceeds': Decimal('0'),
                    'total_cost_basis': Decimal('0'),
                    'total_realized_gain': Decimal('0'),
                    'short_term_gain': Decimal('0'),
                    'long_term_gain': Decimal('0')
                }

            # For each sell transaction, calculate gains
            # (This is simplified - in practice you'd need to track
            # the actual cost basis for each lot sold)
            total_proceeds = Decimal('0')
            total_cost_basis = Decimal('0')
            short_term_gain = Decimal('0')
            long_term_gain = Decimal('0')

            with db_manager.get_session() as session:
                for sell_record in sell_transactions:
                    stock = session.query(Stock).filter(
                        Stock.symbol == sell_record.stock_symbol
                    ).first()

                    if stock:
                        gains = self._calculate_realized_gains(
                            session, portfolio_id, stock,
                            sell_record.quantity, sell_record.price,
                            sell_record.transaction_date
                        )

                        for gain in gains:
                            total_proceeds += gain.gross_proceeds
                            total_cost_basis += gain.cost_basis

                            if gain.is_long_term:
                                long_term_gain += gain.realized_pnl
                            else:
                                short_term_gain += gain.realized_pnl

            return {
                'total_proceeds': total_proceeds,
                'total_cost_basis': total_cost_basis,
                'total_realized_gain': total_proceeds - total_cost_basis,
                'short_term_gain': short_term_gain,
                'long_term_gain': long_term_gain
            }

        except Exception as e:
            self.logger.error(f"Error calculating tax report: {e}")
            return {}

class TransactionAnalyzer:
    """Analyze transaction patterns and performance"""

    def __init__(self, transaction_recorder: TransactionRecorder):
        self.transaction_recorder = transaction_recorder
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def analyze_trading_patterns(self, portfolio_id: str) -> Dict[str, any]:
        """Analyze trading patterns and behavior"""
        try:
            # Get all transactions
            transactions = self.transaction_recorder.get_transaction_history(
                portfolio_id=portfolio_id
            )

            if not transactions:
                return {}

            # Calculate various metrics
            total_transactions = len(transactions)
            buy_transactions = [t for t in transactions if t.transaction_type == 'BUY']
            sell_transactions = [t for t in transactions if t.transaction_type == 'SELL']

            total_invested = sum(t.total_amount for t in buy_transactions)
            total_proceeds = sum(t.total_amount for t in sell_transactions)

            # Average holding period (simplified)
            avg_holding_period = self._calculate_avg_holding_period(transactions)

            # Most traded stocks
            stock_counts = {}
            for tx in transactions:
                stock_counts[tx.stock_symbol] = stock_counts.get(tx.stock_symbol, 0) + 1

            most_traded = sorted(stock_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            analysis = {
                'total_transactions': total_transactions,
                'buy_count': len(buy_transactions),
                'sell_count': len(sell_transactions),
                'total_invested': total_invested,
                'total_proceeds': total_proceeds,
                'avg_holding_period_days': avg_holding_period,
                'most_traded_stocks': most_traded,
                'trading_frequency': self._calculate_trading_frequency(transactions),
                'avg_transaction_size': total_invested / len(buy_transactions) if buy_transactions else 0
            }

            return analysis

        except Exception as e:
            self.logger.error(f"Error analyzing trading patterns: {e}")
            return {}

    def _calculate_avg_holding_period(self, transactions: List[TransactionRecord]) -> int:
        """Calculate average holding period (simplified)"""
        # This is a simplified calculation
        # In practice, you'd match specific buy/sell pairs
        if not transactions:
            return 0

        date_range = max(t.transaction_date for t in transactions) - min(t.transaction_date for t in transactions)
        return date_range.days

    def _calculate_trading_frequency(self, transactions: List[TransactionRecord]) -> str:
        """Calculate trading frequency category"""
        if not transactions:
            return "No trades"

        date_range = max(t.transaction_date for t in transactions) - min(t.transaction_date for t in transactions)
        if date_range.days == 0:
            return "Single day"

        trades_per_month = len(transactions) / (date_range.days / 30)

        if trades_per_month > 10:
            return "Very Active"
        elif trades_per_month > 5:
            return "Active"
        elif trades_per_month > 1:
            return "Moderate"
        else:
            return "Infrequent"