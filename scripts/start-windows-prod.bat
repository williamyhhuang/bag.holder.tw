@echo off
REM Taiwan Stock Monitor - Windows Production Startup Script

echo 🚀 Starting Taiwan Stock Monitor (Production Mode)
echo ==================================================

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ⚠️  Running without administrator privileges
    echo Some features may be limited
)

REM Check if Docker is running
docker info >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Docker is not running
    echo Please start Docker Desktop and try again
    pause
    exit /b 1
)

REM Check if .env exists
if not exist .env (
    echo ❌ .env file not found
    echo Please copy .env.example to .env and configure your API keys
    pause
    exit /b 1
)

echo ✅ Pre-flight checks passed
echo.

REM Start production services with Windows configuration
echo 🐳 Starting Docker services in production mode...
docker-compose -f docker-compose.yml -f docker-compose.windows.yml -f deploy\docker-compose.prod.yml up -d --build

if %errorLevel% eq 0 (
    echo ✅ Services started successfully in background
    echo.
    echo 📊 Available services:
    echo   - API Server: http://localhost:8000
    echo   - Health Check: http://localhost:8000/health
    echo   - Prometheus: http://localhost:9090 (if monitoring enabled)
    echo   - Grafana: http://localhost:3000 (if monitoring enabled)
    echo.
    echo 📋 To view logs: docker-compose logs -f
    echo 📋 To stop services: scripts\stop-windows.bat
    echo.

    REM Show container status
    echo 🐳 Container Status:
    docker-compose ps

) else (
    echo ❌ Failed to start services
    echo Check the error messages above
    pause
)

pause