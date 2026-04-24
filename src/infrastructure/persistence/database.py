"""
Database connection management
"""
import os
from typing import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from .orm_models import Base

class DatabaseManager:
    """Database connection and session management"""

    def __init__(self, database_url: str = None):
        if database_url is None:
            database_url = os.getenv(
                'DATABASE_URL',
                'postgresql://postgres:password@localhost:5432/tw_stock'
            )

        # Create engine with connection pooling
        self.engine: Engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Validate connections before use
            echo=os.getenv('DATABASE_ECHO', 'false').lower() == 'true'
        )

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self):
        """Drop all tables (use with caution!)"""
        Base.metadata.drop_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session_direct(self) -> Session:
        """Get a database session (manual management required)"""
        return self.SessionLocal()

    def health_check(self) -> bool:
        """Check if database connection is healthy"""
        try:
            with self.get_session() as session:
                session.execute("SELECT 1")
                return True
        except Exception:
            return False

# Global database manager instance
db_manager = DatabaseManager()
