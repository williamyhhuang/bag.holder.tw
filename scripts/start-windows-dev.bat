@echo off
REM Taiwan Stock Monitor - Windows Development Startup Script

echo 🚀 Starting Taiwan Stock Monitor (Development Mode)
echo ==================================================

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

REM Start services with Windows configuration
echo 🐳 Starting Docker services...
docker-compose -f docker-compose.yml -f docker-compose.windows.yml up --build

echo.
echo 🎉 Taiwan Stock Monitor started successfully!
echo.
echo 📊 Available services:
echo   - API Server: http://localhost:8000
echo   - Health Check: http://localhost:8000/health
echo   - Database: localhost:5432
echo   - Redis: localhost:6379
echo.
echo Press Ctrl+C to stop all services
pause