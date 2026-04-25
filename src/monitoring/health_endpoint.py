"""
monitoring.health_endpoint - backward compatibility shim
"""
from src.infrastructure.monitoring.health_endpoint import (
    health_app, start_health_server,
)

__all__ = ['health_app', 'start_health_server']
