@echo off
REM Taiwan Stock Monitor Installation Script for Windows 11
REM This script sets up the complete environment for the stock monitoring robot

echo 🚀 Starting Taiwan Stock Monitor installation for Windows 11...

REM Check if running on Windows
if not "%OS%"=="Windows_NT" (
    echo ❌ This script is designed for Windows
    pause
    exit /b 1
)

REM Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo ✅ Administrator privileges confirmed
) else (
    echo ❌ This script requires Administrator privileges
    echo Please run as Administrator
    pause
    exit /b 1
)

REM Function to check if command exists
where python >nul 2>&1
if %errorLevel% == 0 (
    echo ✅ Python found
) else (
    echo 📦 Installing Python...
    echo Please download and install Python 3.11 from https://python.org
    echo Make sure to check "Add to PATH" during installation
    pause
    goto :install_python
)

:install_python
echo Please install Python 3.11 and restart this script
pause
exit /b 1

:check_docker
where docker >nul 2>&1
if %errorLevel% == 0 (
    echo ✅ Docker found
) else (
    echo 📦 Installing Docker Desktop...
    echo Please download and install Docker Desktop from https://docker.com
    pause
    goto :install_docker
)

:install_docker
echo Please install Docker Desktop and restart this script
pause
exit /b 1

:setup_python_env
echo 🐍 Setting up Python environment...

REM Create virtual environment
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install dependencies
pip install -r requirements.txt

echo ✅ Python environment setup complete

:setup_config
echo ⚙️ Setting up configuration...

REM Copy environment file
if not exist .env (
    copy .env.example .env
    echo 📝 Created .env file from template
    echo ⚠️  Please edit .env file and add your API keys:
    echo    - FUBON_API_KEY
    echo    - FUBON_API_SECRET
    echo    - TELEGRAM_BOT_TOKEN
) else (
    echo 📝 .env file already exists
)

REM Create directories
if not exist logs mkdir logs
if not exist data mkdir data
if not exist data\backups mkdir data\backups

echo ✅ Configuration setup complete

:setup_docker_env
echo 🐳 Setting up Docker environment...

REM Check if Docker Desktop is running
docker info >nul 2>&1
if %errorLevel% == 0 (
    echo ✅ Docker Desktop is running
) else (
    echo ⚠️ Docker Desktop is not running
    echo Please start Docker Desktop and press any key to continue
    pause
)

echo ✅ Docker setup complete

:init_database
echo 📊 Initializing database...

REM Run database initialization
python -c "from src.database.connection import db_manager; db_manager.create_tables(); print('✅ Database tables created successfully')" || echo ⚠️ Database initialization had issues

echo ✅ Database initialization complete

:create_shortcuts
echo 🛠️ Creating desktop shortcuts...

REM Create batch files for easy startup
echo @echo off > start_development.bat
echo cd /d "%CD%" >> start_development.bat
echo call venv\Scripts\activate.bat >> start_development.bat
echo docker-compose up --build >> start_development.bat

echo @echo off > start_production.bat
echo cd /d "%CD%" >> start_production.bat
echo docker-compose -f docker-compose.yml -f deploy\docker-compose.prod.yml up -d --build >> start_production.bat

echo @echo off > stop_services.bat
echo cd /d "%CD%" >> stop_services.bat
echo docker-compose down >> stop_services.bat

echo ✅ Created startup scripts:
echo   - start_development.bat
echo   - start_production.bat
echo   - stop_services.bat

:final_setup
echo 🎉 Installation completed successfully!
echo.
echo 📋 Next steps:
echo 1. Edit .env file with your API credentials
echo 2. Download fubon_neo SDK (.whl file) from Fubon Securities
echo 3. Install SDK: pip install fubon_neo-^<version^>.whl
echo 4. Run start_development.bat to begin
echo.
echo 📚 For more information, see docs\WINDOWS_DEPLOYMENT.md
echo.
pause