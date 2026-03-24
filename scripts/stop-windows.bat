@echo off
REM Taiwan Stock Monitor - Windows Stop Script

echo 🛑 Stopping Taiwan Stock Monitor Services
echo ==========================================

REM Stop all related services
echo 📦 Stopping Docker containers...
docker-compose -f docker-compose.yml -f docker-compose.windows.yml down 2>nul
docker-compose -f docker-compose.yml -f docker-compose.windows.yml -f deploy\docker-compose.prod.yml down 2>nul

if %errorLevel% eq 0 (
    echo ✅ Services stopped successfully
) else (
    echo ⚠️ Some services may not have been running
)

echo.
echo 🧹 Cleaning up (optional)...
echo Press any key to clean unused Docker resources, or close to skip
pause >nul

docker system prune -f
docker volume prune -f

echo ✅ Cleanup completed
echo.
echo 🎯 Taiwan Stock Monitor has been stopped
pause