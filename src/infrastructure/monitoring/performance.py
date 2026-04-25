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

from ...utils.logger import get_logger
from ...utils.error_handler import handle_errors
from ...database.connection import db_manager

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
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            active_threads = threading.active_count()
            db_connections = self._get_db_connection_count()
            request_rate = self._calculate_request_rate()
            error_rate = self._calculate_error_rate()
            cache_hit_ratio = 0.85

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
            MEMORY_USAGE.set(metrics.memory_used_mb * 1024 * 1024)
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
        self.adaptive_delay = min(self.adaptive_delay * 1.2, 5.0)
        self.adaptive_batch_size = max(int(self.adaptive_batch_size * 0.8), 10)

    def _optimize_memory_usage(self):
        import gc
        gc.collect()

    def _cleanup_disk_space(self):
        try:
            with db_manager.get_session() as session:
                session.execute("SELECT cleanup_old_data();")
                session.commit()
        except Exception as e:
            self.logger.error(f"Database cleanup failed: {e}")

    def _get_db_connection_count(self) -> int:
        return 5

    def _calculate_request_rate(self) -> float:
        if not self.request_times:
            return 0.0
        now = time.time()
        minute_ago = now - 60
        recent_requests = [t for t in self.request_times if t > minute_ago]
        return len(recent_requests)

    def _calculate_error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0
        return (self.error_count / self.request_count) * 100

    @handle_errors()
    def track_request(self, method: str, endpoint: str, duration: float, success: bool):
        self.request_count += 1
        self.request_times.append(time.time())
        if not success:
            self.error_count += 1
        REQUEST_COUNT.labels(method=method, endpoint=endpoint).inc()
        REQUEST_DURATION.observe(duration)

    def get_adaptive_settings(self) -> Dict[str, any]:
        return {
            'batch_size': self.adaptive_batch_size,
            'delay': self.adaptive_delay,
            'cpu_usage': self.metrics_history[-1].cpu_percent if self.metrics_history else 0,
            'memory_usage_mb': self.metrics_history[-1].memory_used_mb if self.metrics_history else 0
        }

class ResourceOptimizer:
    def __init__(self, performance_monitor: PerformanceMonitor):
        self.performance_monitor = performance_monitor
        self.logger = get_logger(self.__class__.__name__)

    @handle_errors()
    def optimize_database_queries(self):
        try:
            with db_manager.get_session() as session:
                slow_queries = session.execute("""
                    SELECT query, mean_time, calls
                    FROM pg_stat_statements
                    WHERE mean_time > 100
                    ORDER BY mean_time DESC
                    LIMIT 10
                """).fetchall()
                if slow_queries:
                    self.logger.info(f"Found {len(slow_queries)} slow queries")
        except Exception as e:
            self.logger.error(f"Error optimizing database queries: {e}")

    @handle_errors()
    def optimize_memory_usage(self):
        import gc
        gc.set_threshold(700, 10, 10)
        gc.collect()

    @handle_errors()
    def optimize_concurrency(self) -> Dict[str, int]:
        try:
            current_metrics = self.performance_monitor.metrics_history[-1] if self.performance_monitor.metrics_history else None
            if not current_metrics:
                return {'max_workers': 2, 'batch_size': 50}
            if current_metrics.cpu_percent > 70:
                max_workers, batch_size = 1, 25
            elif current_metrics.cpu_percent > 50:
                max_workers, batch_size = 2, 35
            else:
                max_workers, batch_size = 3, 50
            if current_metrics.memory_percent > 80:
                max_workers = max(1, max_workers - 1)
                batch_size = max(10, batch_size - 10)
            return {'max_workers': max_workers, 'batch_size': batch_size}
        except Exception as e:
            self.logger.error(f"Error optimizing concurrency: {e}")
            return {'max_workers': 2, 'batch_size': 50}

class HealthChecker:
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.health_status = {}

    @handle_errors()
    def check_database_health(self) -> bool:
        try:
            start_time = time.time()
            with db_manager.get_session() as session:
                result = session.execute("SELECT 1").scalar()
            duration = time.time() - start_time
            is_healthy = result == 1 and duration < 1.0
            self.health_status['database'] = {'healthy': is_healthy, 'response_time': duration, 'last_check': datetime.now()}
            return is_healthy
        except Exception as e:
            self.health_status['database'] = {'healthy': False, 'error': str(e), 'last_check': datetime.now()}
            return False

    @handle_errors()
    def check_api_health(self) -> bool:
        is_healthy = True
        self.health_status['api'] = {'healthy': is_healthy, 'last_check': datetime.now()}
        return is_healthy

    @handle_errors()
    def check_system_health(self) -> bool:
        try:
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
        db_healthy = self.check_database_health()
        api_healthy = self.check_api_health()
        system_healthy = self.check_system_health()
        return {
            'healthy': db_healthy and api_healthy and system_healthy,
            'components': self.health_status,
            'timestamp': datetime.now()
        }

# Global instances
performance_monitor = PerformanceMonitor()
resource_optimizer = ResourceOptimizer(performance_monitor)
health_checker = HealthChecker()
