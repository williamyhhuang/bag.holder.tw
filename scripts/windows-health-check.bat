@echo off
REM Taiwan Stock Monitor - Windows Health Check Script

echo 🩺 Taiwan Stock Monitor Health Check
echo ====================================

REM Check Docker
echo 🐳 Checking Docker...
docker info >nul 2>&1
if %errorLevel% eq 0 (
    echo ✅ Docker is running
) else (
    echo ❌ Docker is not running
    goto :end
)

REM Check containers
echo.
echo 📦 Container Status:
docker-compose ps

REM Check API health
echo.
echo 🔍 API Health Check...
powershell -Command "try { $response = Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 5; Write-Host '✅ API is healthy:' $response.status } catch { Write-Host '❌ API health check failed:' $_.Exception.Message }"

REM Check database
echo.
echo 🗄️ Database Check...
docker-compose exec -T postgres pg_isready -U postgres 2>nul
if %errorLevel% eq 0 (
    echo ✅ Database is ready
) else (
    echo ❌ Database is not ready
)

REM Check Redis
echo.
echo 📦 Redis Check...
docker-compose exec -T redis redis-cli ping 2>nul | findstr PONG >nul
if %errorLevel% eq 0 (
    echo ✅ Redis is responding
) else (
    echo ❌ Redis is not responding
)

REM System resources
echo.
echo 💻 System Resources:
echo Memory Usage:
wmic OS get TotalVisibleMemorySize,FreePhysicalMemory /format:list | findstr "="

echo.
echo Disk Space:
for /f "tokens=3" %%a in ('dir /-c ^| find "bytes free"') do echo Free: %%a bytes

REM Docker stats
echo.
echo 🐳 Docker Resource Usage:
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

:end
echo.
echo 🏁 Health check completed
pause