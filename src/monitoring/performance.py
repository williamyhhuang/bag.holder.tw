"""
Performance monitoring and optimization system
"""
import asyncio
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import threading
from collections import deque

from prometheus_client import Counter, Histogram, Gauge, start_http_server

from ..utils.logger import get_logger
from ..utils.error_handler import handle_errors
from ..database.connection import db_manager

logger = get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active database connections')
MEMORY_USAGE = Gauge('memory_usage_bytes', 'Memory usage in bytes')
CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage')
STOCK_SCAN_DURATION = Histogram('stock_scan_duration_seconds', 'Stock scan duration')
ALERT_GENERATION_COUNT = Counter('alerts_generated_total', 'Total alerts generated')

@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_usage_percent: float
    active_threads: int
    database_connections: int
    cache_hit_ratio: float
    request_rate: float
    error_rate: float

@dataclass
class SystemLimits:
    """System resource limits for Mac Mini 2015"""
    max_cpu_percent: float = 80.0
    max_memory_mb: float = 3200.0  # Leave 800MB for system
    max_disk_percent: float = 90.0
    max_threads: int = 100
    max_db_connections: int = 20

class PerformanceMonitor:
    """System performance monitoring and optimization"""

    def __init__(self, limits: SystemLimits = None):
        self.limits = limits or SystemLimits()
        self.logger = get_logger(self.__class__.__name__)

        self.metrics_history = deque(maxlen=1440)  # 24 hours of minute data
        self.is_monitoring = False
        self.monitor_thread = None

        # Performance tracking
        self.request_times = deque(maxlen=1000)
        self.error_count = 0
        self.request_count = 0

        # Adaptive thresholds
        self.adaptive_batch_size = 50
        self.adaptive_delay = 1.0

    def start_monitoring(self, port: int = 9090):
        """Start performance monitoring"""
        try:
            # Start Prometheus HTTP server
            start_http_server(port)
            self.logger.info(f"Prometheus metrics server started on port {port}")

            # Start monitoring thread
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitoring_loop)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()

            self.logger.info("Performance monitoring started")

        except Exception as e:
            self.logger.error(f"Failed to start performance monitoring: {e}")

    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        self.logger.info("Performance monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                metrics = self._collect_metrics()
                self._update_prometheus_metrics(metrics)
                self._check_thresholds(metrics)
                self.metrics_history.append(metrics)

                time.sleep(60)  # Collect metrics every minute

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)

    def _collect_metrics(self) -> PerformanceMetrics:
        """Collect current system metrics"""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Thread count
            active_threads = threading.active_count()

            # Database connections (simplified)
            db_connections = self._get_db_connection_count()

            # Request metrics
            request_rate = self._calculate_request_rate()
            error_rate = self._calculate_error_rate()

            # Cache metrics (placeholder)
            cache_hit_ratio = 0.85  # Would be calculated from actual cache stats

            return PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                disk_usage_percent=disk.percent,
                active_threads=active_threads,
                database_connections=db_connections,
                cache_hit_ratio=cache_hit_ratio,
                request_rate=request_rate,
                error_rate=error_rate
            )

        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
            return PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=0, memory_percent=0, memory_used_mb=0,
                disk_usage_percent=0, active_threads=0, database_connections=0,
                cache_hit_ratio=0, request_rate=0, error_rate=0
            )

    def _update_prometheus_metrics(self, metrics: PerformanceMetrics):
        """Update Prometheus metrics"""
        try:
            CPU_USAGE.set(metrics.cpu_percent)
            MEMORY_USAGE.set(metrics.memory_used_mb * 1024 * 1024)  # Convert to bytes
            ACTIVE_CONNECTIONS.set(metrics.database_connections)

        except Exception as e:
            self.logger.error(f"Error updating Prometheus metrics: {e}")

    def _check_thresholds(self, metrics: PerformanceMetrics):
        """Check if metrics exceed thresholds and take action"""
        try:
            alerts = []

            if metrics.cpu_percent > self.limits.max_cpu_percent:
                alerts.append(f"High CPU usage: {metrics.cpu_percent:.1f}%")
                self._optimize_cpu_usage()

            if metrics.memory_used_mb > self.limits.max_memory_mb:
                alerts.append(f"High memory usage: {metrics.memory_used_mb:.1f}MB")
                self._optimize_memory_usage()

            if metrics.disk_usage_percent > self.limits.max_disk_percent:
                alerts.append(f"High disk usage: {metrics.disk_usage_percent:.1f}%")
                self._cleanup_disk_space()

            if metrics.active_threads > self.limits.max_threads:
                alerts.append(f"High thread count: {metrics.active_threads}")

            if alerts:
                self.logger.warning(f"Performance alerts: {'; '.join(alerts)}")

        except Exception as e:
            self.logger.error(f"Error checking thresholds: {e}")

    def _optimize_cpu_usage(self):
        """Optimize CPU usage when threshold exceeded"""
        try:
            # Increase delays between operations
            self.adaptive_delay = min(self.adaptive_delay * 1.2, 5.0)

            # Reduce batch sizes
            self.adaptive_batch_size = max(int(self.adaptive_batch_size * 0.8), 10)

            self.logger.info(
                f"CPU optimization: delay={self.adaptive_delay:.1f}s, "
                f"batch_size={self.adaptive_batch_size}"
            )

        except Exception as e:
            self.logger.error(f"Error optimizing CPU usage: {e}")

    def _optimize_memory_usage(self):
        """Optimize memory usage when threshold exceeded"""
        try:
            import gc

            # Force garbage collection
            gc.collect()

            # Clear metric history if too large
            if len(self.metrics_history) > 720:  # Keep only 12 hours
                for _ in range(360):
                    self.metrics_history.popleft()

            self.logger.info("Memory optimization: garbage collection performed")

        except Exception as e:
            self.logger.error(f"Error optimizing memory usage: {e}")

    def _cleanup_disk_space(self):
        """Cleanup disk space when threshold exceeded"""
        try:
            # This would implement log rotation and old data cleanup
            self.logger.info("Disk cleanup: log rotation and data cleanup triggered")

            # Execute database cleanup
            try:
                with db_manager.get_session() as session:
                    session.execute("SELECT cleanup_old_data();")
                    session.commit()
            except Exception as e:
                self.logger.error(f"Database cleanup failed: {e}")

        except Exception as e:
            self.logger.error(f"Error cleaning up disk space: {e}")

    def _get_db_connection_count(self) -> int:
        """Get current database connection count"""
        try:
            # This is a simplified implementation
            # In practice, you'd query the connection pool
            return 5  # Placeholder

        except Exception as e:
            self.logger.error(f"Error getting DB connection count: {e}")
            return 0

    def _calculate_request_rate(self) -> float:
        """Calculate requests per minute"""
        if not self.request_times:
            return 0.0

        now = time.time()
        minute_ago = now - 60

        recent_requests = [t for t in self.request_times if t > minute_ago]
        return len(recent_requests)

    def _calculate_error_rate(self) -> float:
        """Calculate error rate percentage"""
        if self.request_count == 0:
            return 0.0

        return (self.error_count / self.request_count) * 100

    @handle_errors()
    def track_request(self, method: str, endpoint: str, duration: float, success: bool):
        """Track request metrics"""
        self.request_count += 1
        self.request_times.append(time.time())

        if not success:
            self.error_count += 1

        # Update Prometheus metrics
        REQUEST_COUNT.labels(method=method, endpoint=endpoint).inc()
        REQUEST_DURATION.observe(duration)

    def get_adaptive_settings(self) -> Dict[str, any]:
        """Get current adaptive performance settings"""
        return {
            'batch_size': self.adaptive_batch_size,
            'delay': self.adaptive_delay,
            'cpu_usage': self.metrics_history[-1].cpu_percent if self.metrics_history else 0,
            'memory_usage_mb': self.metrics_history[-1].memory_used_mb if self.metrics_history else 0
        }

class ResourceOptimizer:
    """Resource optimization for Mac Mini 2015"""

    def __init__(self, performance_monitor: PerformanceMonitor):
        self.performance_monitor = performance_monitor
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def optimize_database_queries(self):
        """Optimize database query performance"""
        try:
            with db_manager.get_session() as session:
                # Analyze slow queries and create indexes if needed
                slow_queries = session.execute("""
                    SELECT query, mean_time, calls
                    FROM pg_stat_statements
                    WHERE mean_time > 100
                    ORDER BY mean_time DESC
                    LIMIT 10
                """).fetchall()

                if slow_queries:
                    self.logger.info(f"Found {len(slow_queries)} slow queries")

                    # Log slow queries for analysis
                    for query, mean_time, calls in slow_queries:
                        self.logger.warning(
                            f"Slow query: {mean_time:.2f}ms avg, "
                            f"{calls} calls - {query[:100]}..."
                        )

        except Exception as e:
            self.logger.error(f"Error optimizing database queries: {e}")

    @handle_errors()
    def optimize_memory_usage(self):
        """Optimize application memory usage"""
        try:
            import gc

            # Configure garbage collection for Mac Mini
            gc.set_threshold(700, 10, 10)  # More aggressive collection

            # Force collection
            collected = gc.collect()

            self.logger.info(f"Garbage collection freed {collected} objects")

        except Exception as e:
            self.logger.error(f"Error optimizing memory: {e}")

    @handle_errors()
    def optimize_concurrency(self) -> Dict[str, int]:
        """Optimize concurrency settings based on system performance"""
        try:
            current_metrics = self.performance_monitor.metrics_history[-1] if self.performance_monitor.metrics_history else None

            if not current_metrics:
                return {'max_workers': 2, 'batch_size': 50}

            # Adaptive concurrency based on CPU and memory usage
            if current_metrics.cpu_percent > 70:
                max_workers = 1
                batch_size = 25
            elif current_metrics.cpu_percent > 50:
                max_workers = 2
                batch_size = 35
            else:
                max_workers = 3
                batch_size = 50

            # Adjust for memory usage
            if current_metrics.memory_percent > 80:
                max_workers = max(1, max_workers - 1)
                batch_size = max(10, batch_size - 10)

            settings = {
                'max_workers': max_workers,
                'batch_size': batch_size
            }

            self.logger.info(f"Optimized concurrency settings: {settings}")
            return settings

        except Exception as e:
            self.logger.error(f"Error optimizing concurrency: {e}")
            return {'max_workers': 2, 'batch_size': 50}

class HealthChecker:
    """Application health monitoring"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.health_status = {}

    @handle_errors()
    def check_database_health(self) -> bool:
        """Check database connectivity and performance"""
        try:
            start_time = time.time()

            with db_manager.get_session() as session:
                result = session.execute("SELECT 1").scalar()

            duration = time.time() - start_time

            is_healthy = result == 1 and duration < 1.0

            self.health_status['database'] = {
                'healthy': is_healthy,
                'response_time': duration,
                'last_check': datetime.now()
            }

            return is_healthy

        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            self.health_status['database'] = {
                'healthy': False,
                'error': str(e),
                'last_check': datetime.now()
            }
            return False

    @handle_errors()
    def check_api_health(self) -> bool:
        """Check external API connectivity"""
        try:
            # This would check Fubon API connectivity
            # Placeholder implementation

            is_healthy = True  # Replace with actual API check

            self.health_status['api'] = {
                'healthy': is_healthy,
                'last_check': datetime.now()
            }

            return is_healthy

        except Exception as e:
            self.logger.error(f"API health check failed: {e}")
            self.health_status['api'] = {
                'healthy': False,
                'error': str(e),
                'last_check': datetime.now()
            }
            return False

    @handle_errors()
    def check_system_health(self) -> bool:
        """Check overall system health"""
        try:
            # Check system resources
            cpu_ok = psutil.cpu_percent(interval=1) < 90
            memory_ok = psutil.virtual_memory().percent < 90
            disk_ok = psutil.disk_usage('/').percent < 95

            is_healthy = cpu_ok and memory_ok and disk_ok

            self.health_status['system'] = {
                'healthy': is_healthy,
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'last_check': datetime.now()
            }

            return is_healthy

        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            return False

    def get_overall_health(self) -> Dict[str, any]:
        """Get overall application health status"""
        db_healthy = self.check_database_health()
        api_healthy = self.check_api_health()
        system_healthy = self.check_system_health()

        overall_healthy = db_healthy and api_healthy and system_healthy

        return {
            'healthy': overall_healthy,
            'components': self.health_status,
            'timestamp': datetime.now()
        }

# Global instances
performance_monitor = PerformanceMonitor()
resource_optimizer = ResourceOptimizer(performance_monitor)
health_checker = HealthChecker()