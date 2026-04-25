"""
Health check HTTP endpoint for monitoring
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from datetime import datetime
from typing import Dict, Any

from .performance import health_checker, performance_monitor
from ...utils.logger import get_logger

logger = get_logger(__name__)

# Create FastAPI app for health checks
health_app = FastAPI(
    title="Taiwan Stock Monitor Health API",
    description="Health monitoring endpoints",
    version="1.0.0"
)

@health_app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Taiwan Stock Monitor Health API", "timestamp": datetime.now()}

@health_app.get("/health")
async def health_check():
    """Main health check endpoint"""
    try:
        health_status = health_checker.get_overall_health()

        if health_status['healthy']:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "timestamp": health_status['timestamp'].isoformat(),
                    "components": health_status['components']
                }
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "timestamp": health_status['timestamp'].isoformat(),
                    "components": health_status['components']
                }
            )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@health_app.get("/health/database")
async def database_health():
    """Database specific health check"""
    try:
        is_healthy = health_checker.check_database_health()

        return JSONResponse(
            status_code=200 if is_healthy else 503,
            content={
                "component": "database",
                "healthy": is_healthy,
                "details": health_checker.health_status.get('database', {}),
                "timestamp": datetime.now().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"Database health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@health_app.get("/health/system")
async def system_health():
    """System resource health check"""
    try:
        is_healthy = health_checker.check_system_health()

        return JSONResponse(
            status_code=200 if is_healthy else 503,
            content={
                "component": "system",
                "healthy": is_healthy,
                "details": health_checker.health_status.get('system', {}),
                "timestamp": datetime.now().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"System health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@health_app.get("/metrics/performance")
async def performance_metrics():
    """Get current performance metrics"""
    try:
        settings = performance_monitor.get_adaptive_settings()

        current_metrics = None
        if performance_monitor.metrics_history:
            current_metrics = performance_monitor.metrics_history[-1]

        return JSONResponse(
            status_code=200,
            content={
                "adaptive_settings": settings,
                "current_metrics": {
                    "cpu_percent": current_metrics.cpu_percent if current_metrics else 0,
                    "memory_percent": current_metrics.memory_percent if current_metrics else 0,
                    "memory_used_mb": current_metrics.memory_used_mb if current_metrics else 0,
                    "active_threads": current_metrics.active_threads if current_metrics else 0,
                    "request_rate": current_metrics.request_rate if current_metrics else 0,
                    "error_rate": current_metrics.error_rate if current_metrics else 0
                } if current_metrics else {},
                "timestamp": datetime.now().isoformat()
            }
        )

    except Exception as e:
        logger.error(f"Performance metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@health_app.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    try:
        db_healthy = health_checker.check_database_health()

        if db_healthy:
            return JSONResponse(
                status_code=200,
                content={"status": "ready", "timestamp": datetime.now().isoformat()}
            )
        else:
            return JSONResponse(
                status_code=503,
                content={"status": "not ready", "timestamp": datetime.now().isoformat()}
            )

    except Exception as e:
        logger.error(f"Readiness check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@health_app.get("/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    try:
        return JSONResponse(
            status_code=200,
            content={"status": "alive", "timestamp": datetime.now().isoformat()}
        )

    except Exception as e:
        logger.error(f"Liveness check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def start_health_server(host: str = "0.0.0.0", port: int = 8000):
    """Start health check server"""
    try:
        config = uvicorn.Config(
            health_app,
            host=host,
            port=port,
            log_level="info",
            access_log=False
        )

        server = uvicorn.Server(config)
        await server.serve()

    except Exception as e:
        logger.error(f"Error starting health server: {e}")
        raise
