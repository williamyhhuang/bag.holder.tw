"""
monitoring package - backward compatibility shim
"""
from src.infrastructure.monitoring.performance import performance_monitor, resource_optimizer, health_checker
from src.infrastructure.monitoring.health_endpoint import health_app, start_health_server

__all__ = [
    'performance_monitor',
    'resource_optimizer',
    'health_checker',
    'health_app',
    'start_health_server',
]
