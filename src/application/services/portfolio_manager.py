"""
Portfolio management system for tracking investment performance
"""
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from ...database.connection import db_manager
from ...database.models import (
    Portfolio, PortfolioHolding, Transaction, Stock, StockRealtime
)
from ...utils.logger import get_logger
from ...utils.error_handler import handle_errors, ApplicationError

logger = get_logger(__name__)

@dataclass
class HoldingInfo:
    """Portfolio holding information"""
    stock_symbol: str
    stock_name: str
    quantity: int
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    cost_basis: Decimal

@dataclass
class PortfolioSummary:
    """Portfolio summary information"""
    total_cost_basis: Decimal
    total_market_value: Decimal
    total_unrealized_pnl: Decimal
    total_unrealized_pnl_pct: Decimal
    total_realized_pnl: Decimal
    cash_balance: Decimal
    holdings_count: int
    last_updated: datetime

class PortfolioManager:
    """Portfolio management and tracking system"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def create_portfolio(self, user_id: str, name: str = "Default Portfolio") -> Optional[str]:
        """
        Create a new portfolio for user

        Args:
            user_id: Telegram user ID
            name: Portfolio name

        Returns:
            Portfolio ID if successful, None otherwise
        """
        try:
            with db_manager.get_session() as session:
                # Check if portfolio with same name exists
                existing = session.query(Portfolio).filter(
                    and_(
                        Portfolio.user_id == user_id,
                        Portfolio.name == name
                    )
                ).first()

                if existing:
                    raise ApplicationError(f"Portfolio '{name}' already exists")

                # Create new portfolio
                portfolio = Portfolio(
                    user_id=user_id,
                    name=name
                )
                session.add(portfolio)
                session.commit()

                self.logger.info(f"Created portfolio '{name}' for user {user_id}")
                return str(portfolio.id)

        except Exception as e:
            self.logger.error(f"Error creating portfolio: {e}")
            raise

    @handle_errors()
    def get_user_portfolios(self, user_id: str) -> List[Portfolio]:
        """
        Get all portfolios for a user

        Args:
            user_id: Telegram user ID

        Returns:
            List of user portfolios
        """
        try:
            with db_manager.get_session() as session:
                portfolios = session.query(Portfolio).filter(
                    and_(
                        Portfolio.user_id == user_id,
                        Portfolio.is_active == True
                    )
                ).order_by(Portfolio.created_at).all()

                return portfolios

        except Exception as e:
            self.logger.error(f"Error getting user portfolios: {e}")
            return []

    @handle_errors()
    def get_portfolio_holdings(self, portfolio_id: str) -> List[HoldingInfo]:
        """
        Get all holdings in a portfolio with current market values

        Args:
            portfolio_id: Portfolio ID

        Returns:
            List of holding information
        """
        try:
            with db_manager.get_session() as session:
                holdings = session.query(PortfolioHolding, Stock).join(
                    Stock, PortfolioHolding.stock_id == Stock.id
                ).filter(
                    PortfolioHolding.portfolio_id == portfolio_id
                ).all()

                holding_infos = []

                for holding, stock in holdings:
                    # Get current price
                    current_price = self._get_current_price(session, stock.id)

                    if current_price is None:
                        self.logger.warning(f"No current price for {stock.symbol}")
                        current_price = holding.avg_cost  # Fallback to cost basis

                    # Calculate values
                    cost_basis = holding.avg_cost * holding.quantity
                    market_value = current_price * holding.quantity
                    unrealized_pnl = market_value - cost_basis
                    unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else Decimal('0')

                    holding_info = HoldingInfo(
                        stock_symbol=stock.symbol,
                        stock_name=stock.name,
                        quantity=holding.quantity,
                        avg_cost=holding.avg_cost,
                        current_price=current_price,
                        market_value=market_value,
                        unrealized_pnl=unrealized_pnl,
                        unrealized_pnl_pct=unrealized_pnl_pct,
                        cost_basis=cost_basis
                    )

                    holding_infos.append(holding_info)

                return holding_infos

        except Exception as e:
            self.logger.error(f"Error getting portfolio holdings: {e}")
            return []

    @handle_errors()
    def get_portfolio_summary(self, portfolio_id: str) -> Optional[PortfolioSummary]:
        """
        Get portfolio summary with total values

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Portfolio summary information
        """
        try:
            holdings = self.get_portfolio_holdings(portfolio_id)

            if not holdings:
                return PortfolioSummary(
                    total_cost_basis=Decimal('0'),
                    total_market_value=Decimal('0'),
                    total_unrealized_pnl=Decimal('0'),
                    total_unrealized_pnl_pct=Decimal('0'),
                    total_realized_pnl=Decimal('0'),
                    cash_balance=Decimal('0'),
                    holdings_count=0,
                    last_updated=datetime.now()
                )

            # Calculate totals
            total_cost_basis = sum(holding.cost_basis for holding in holdings)
            total_market_value = sum(holding.market_value for holding in holdings)
            total_unrealized_pnl = total_market_value - total_cost_basis
            total_unrealized_pnl_pct = (total_unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else Decimal('0')

            # Get realized P&L from transactions
            total_realized_pnl = self._calculate_realized_pnl(portfolio_id)

            summary = PortfolioSummary(
                total_cost_basis=total_cost_basis,
                total_market_value=total_market_value,
                total_unrealized_pnl=total_unrealized_pnl,
                total_unrealized_pnl_pct=total_unrealized_pnl_pct,
                total_realized_pnl=total_realized_pnl,
                cash_balance=Decimal('0'),  # TODO: Implement cash tracking
                holdings_count=len(holdings),
                last_updated=datetime.now()
            )

            return summary

        except Exception as e:
            self.logger.error(f"Error getting portfolio summary: {e}")
            return None

    @handle_errors()
    def add_transaction(
        self,
        portfolio_id: str,
        stock_symbol: str,
        transaction_type: str,
        quantity: int,
        price: Decimal,
        transaction_date: date = None,
        fee: Decimal = None,
        tax: Decimal = None,
        notes: str = None
    ) -> bool:
        """
        Add a transaction and update portfolio holdings

        Args:
            portfolio_id: Portfolio ID
            stock_symbol: Stock symbol
            transaction_type: BUY or SELL
            quantity: Number of shares (positive integer)
            price: Transaction price per share
            transaction_date: Transaction date (default: today)
            fee: Transaction fee
            tax: Transaction tax
            notes: Optional notes

        Returns:
            True if successful, False otherwise
        """
        try:
            if transaction_type not in ['BUY', 'SELL']:
                raise ApplicationError(f"Invalid transaction type: {transaction_type}")

            if quantity <= 0:
                raise ApplicationError("Quantity must be positive")

            if price <= 0:
                raise ApplicationError("Price must be positive")

            if transaction_date is None:
                transaction_date = date.today()

            fee = fee or Decimal('0')
            tax = tax or Decimal('0')

            with db_manager.get_session() as session:
                # Get stock
                stock = session.query(Stock).filter(Stock.symbol == stock_symbol).first()
                if not stock:
                    raise ApplicationError(f"Stock not found: {stock_symbol}")

                # Calculate total amount
                if transaction_type == 'BUY':
                    total_amount = (price * quantity) + fee + tax
                else:  # SELL
                    total_amount = (price * quantity) - fee - tax

                # Create transaction record
                transaction = Transaction(
                    portfolio_id=portfolio_id,
                    stock_id=stock.id,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    price=price,
                    fee=fee,
                    tax=tax,
                    total_amount=total_amount,
                    transaction_date=transaction_date,
                    notes=notes
                )
                session.add(transaction)

                # Update portfolio holding
                self._update_portfolio_holding(
                    session, portfolio_id, stock.id, transaction_type, quantity, price
                )

                session.commit()

                self.logger.info(
                    f"Added {transaction_type} transaction: "
                    f"{stock_symbol} {quantity} @ {price}"
                )
                return True

        except Exception as e:
            self.logger.error(f"Error adding transaction: {e}")
            return False

    def _update_portfolio_holding(
        self,
        session: Session,
        portfolio_id: str,
        stock_id: str,
        transaction_type: str,
        quantity: int,
        price: Decimal
    ):
        """Update portfolio holding based on transaction"""
        holding = session.query(PortfolioHolding).filter(
            and_(
                PortfolioHolding.portfolio_id == portfolio_id,
                PortfolioHolding.stock_id == stock_id
            )
        ).first()

        if transaction_type == 'BUY':
            if holding:
                # Update existing holding (weighted average cost)
                total_cost = (holding.avg_cost * holding.quantity) + (price * quantity)
                total_quantity = holding.quantity + quantity
                new_avg_cost = total_cost / total_quantity

                holding.quantity = total_quantity
                holding.avg_cost = new_avg_cost
            else:
                # Create new holding
                holding = PortfolioHolding(
                    portfolio_id=portfolio_id,
                    stock_id=stock_id,
                    quantity=quantity,
                    avg_cost=price
                )
                session.add(holding)

        elif transaction_type == 'SELL':
            if not holding:
                raise ApplicationError("Cannot sell stock not in portfolio")

            if holding.quantity < quantity:
                raise ApplicationError(f"Insufficient shares: have {holding.quantity}, selling {quantity}")

            # Reduce quantity
            holding.quantity -= quantity

            # Remove holding if quantity becomes zero
            if holding.quantity == 0:
                session.delete(holding)

    def _get_current_price(self, session: Session, stock_id: str) -> Optional[Decimal]:
        """Get current price for a stock"""
        realtime = session.query(StockRealtime).filter(
            StockRealtime.stock_id == stock_id
        ).first()

        return realtime.current_price if realtime else None

    def _calculate_realized_pnl(self, portfolio_id: str) -> Decimal:
        """Calculate total realized P&L from sell transactions"""
        try:
            with db_manager.get_session() as session:
                # Get all sell transactions with their corresponding buy average cost
                # This is a simplified calculation - in practice, you'd want to use
                # specific lot tracking (FIFO, LIFO, etc.)

                sell_transactions = session.query(Transaction).filter(
                    and_(
                        Transaction.portfolio_id == portfolio_id,
                        Transaction.transaction_type == 'SELL'
                    )
                ).all()

                total_realized = Decimal('0')

                for sell_tx in sell_transactions:
                    # Get average cost from current holding (simplified)
                    holding = session.query(PortfolioHolding).filter(
                        and_(
                            PortfolioHolding.portfolio_id == portfolio_id,
                            PortfolioHolding.stock_id == sell_tx.stock_id
                        )
                    ).first()

                    if holding:
                        avg_cost = holding.avg_cost
                    else:
                        # If no holding exists, estimate from buy transactions
                        avg_cost = self._estimate_avg_cost(session, portfolio_id, sell_tx.stock_id, sell_tx.transaction_date)

                    # Calculate realized P&L
                    cost_basis = avg_cost * sell_tx.quantity
                    sale_proceeds = sell_tx.total_amount  # Already includes fees/taxes
                    realized_pnl = sale_proceeds - cost_basis

                    total_realized += realized_pnl

                return total_realized

        except Exception as e:
            self.logger.error(f"Error calculating realized P&L: {e}")
            return Decimal('0')

    def _estimate_avg_cost(self, session: Session, portfolio_id: str, stock_id: str, before_date: date) -> Decimal:
        """Estimate average cost for sold positions"""
        try:
            buy_transactions = session.query(Transaction).filter(
                and_(
                    Transaction.portfolio_id == portfolio_id,
                    Transaction.stock_id == stock_id,
                    Transaction.transaction_type == 'BUY',
                    Transaction.transaction_date <= before_date
                )
            ).all()

            if not buy_transactions:
                return Decimal('0')

            total_cost = sum(tx.price * tx.quantity for tx in buy_transactions)
            total_quantity = sum(tx.quantity for tx in buy_transactions)

            return total_cost / total_quantity if total_quantity > 0 else Decimal('0')

        except Exception as e:
            self.logger.error(f"Error estimating average cost: {e}")
            return Decimal('0')

class PerformanceAnalyzer:
    """Portfolio performance analysis and metrics"""

    def __init__(self, portfolio_manager: PortfolioManager):
        self.portfolio_manager = portfolio_manager
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def calculate_portfolio_metrics(self, portfolio_id: str) -> Dict[str, Decimal]:
        """
        Calculate various portfolio performance metrics

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Dictionary of performance metrics
        """
        try:
            summary = self.portfolio_manager.get_portfolio_summary(portfolio_id)
            holdings = self.portfolio_manager.get_portfolio_holdings(portfolio_id)

            if not summary or not holdings:
                return {}

            metrics = {
                'total_return_pct': summary.total_unrealized_pnl_pct,
                'total_return_amount': summary.total_unrealized_pnl,
                'best_performer_pct': max((h.unrealized_pnl_pct for h in holdings), default=Decimal('0')),
                'worst_performer_pct': min((h.unrealized_pnl_pct for h in holdings), default=Decimal('0')),
                'avg_return_pct': sum(h.unrealized_pnl_pct for h in holdings) / len(holdings) if holdings else Decimal('0'),
                'winners_count': len([h for h in holdings if h.unrealized_pnl > 0]),
                'losers_count': len([h for h in holdings if h.unrealized_pnl < 0]),
                'win_rate': len([h for h in holdings if h.unrealized_pnl > 0]) / len(holdings) * 100 if holdings else Decimal('0')
            }

            return metrics

        except Exception as e:
            self.logger.error(f"Error calculating portfolio metrics: {e}")
            return {}

    @handle_errors()
    def get_top_performers(self, portfolio_id: str, limit: int = 5) -> List[HoldingInfo]:
        """Get top performing stocks in portfolio"""
        holdings = self.portfolio_manager.get_portfolio_holdings(portfolio_id)
        return sorted(holdings, key=lambda x: x.unrealized_pnl_pct, reverse=True)[:limit]

    @handle_errors()
    def get_worst_performers(self, portfolio_id: str, limit: int = 5) -> List[HoldingInfo]:
        """Get worst performing stocks in portfolio"""
        holdings = self.portfolio_manager.get_portfolio_holdings(portfolio_id)
        return sorted(holdings, key=lambda x: x.unrealized_pnl_pct)[:limit]