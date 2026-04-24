"""
Database connection management - thin re-export shim for backward compatibility
"""
# Re-export from new infrastructure location
from src.infrastructure.persistence.database import DatabaseManager, db_manager

__all__ = ["DatabaseManager", "db_manager"]