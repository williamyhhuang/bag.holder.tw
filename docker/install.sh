#!/bin/bash

# Taiwan Stock Monitor Installation Script for Mac Mini 2015
# This script sets up the complete environment for the stock monitoring robot

set -e  # Exit on any error

echo "🚀 Starting Taiwan Stock Monitor installation..."

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This script is designed for macOS (Mac Mini 2015)"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install with Homebrew
install_with_brew() {
    if ! command_exists brew; then
        echo "📦 Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    echo "📦 Updating Homebrew..."
    brew update

    echo "📦 Installing system dependencies..."
    brew install python@3.11 postgresql@15 redis docker docker-compose git
}

# Function to setup Python environment
setup_python_env() {
    echo "🐍 Setting up Python environment..."

    # Create virtual environment
    python3.11 -m venv venv
    source venv/bin/activate

    # Upgrade pip
    pip install --upgrade pip

    # Install TA-Lib (required for technical indicators)
    if ! command_exists ta-lib-config; then
        echo "📊 Installing TA-Lib..."
        brew install ta-lib
    fi

    # Install Python dependencies
    pip install -r requirements.txt

    echo "✅ Python environment setup complete"
}

# Function to setup database
setup_database() {
    echo "🗄️ Setting up PostgreSQL database..."

    # Start PostgreSQL service
    brew services start postgresql@15

    # Wait for PostgreSQL to start
    sleep 5

    # Create database and user
    createdb tw_stock 2>/dev/null || echo "Database tw_stock already exists"

    # Initialize database
    psql tw_stock -c "
        CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
        CREATE EXTENSION IF NOT EXISTS \"btree_gin\";
    " 2>/dev/null || true

    echo "✅ Database setup complete"
}

# Function to setup Redis
setup_redis() {
    echo "📦 Setting up Redis..."

    # Start Redis service
    brew services start redis

    echo "✅ Redis setup complete"
}

# Function to setup configuration
setup_config() {
    echo "⚙️ Setting up configuration..."

    # Copy environment file
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "📝 Created .env file from template"
        echo "⚠️  Please edit .env file and add your API keys:"
        echo "   - FUBON_API_KEY"
        echo "   - FUBON_SECRET"
        echo "   - TELEGRAM_BOT_TOKEN"
    else
        echo "📝 .env file already exists"
    fi

    # Create log directories
    mkdir -p logs data/backups

    echo "✅ Configuration setup complete"
}

# Function to setup Docker environment
setup_docker() {
    echo "🐳 Setting up Docker environment..."

    # Start Docker Desktop (if available)
    if [ -d "/Applications/Docker.app" ]; then
        open -a Docker
        echo "🐳 Starting Docker Desktop..."

        # Wait for Docker to start
        echo "⏳ Waiting for Docker to start..."
        for i in {1..30}; do
            if docker info >/dev/null 2>&1; then
                break
            fi
            sleep 2
        done

        if ! docker info >/dev/null 2>&1; then
            echo "❌ Docker failed to start. Please start Docker Desktop manually."
            exit 1
        fi
    else
        echo "⚠️  Docker Desktop not found. Please install Docker Desktop for Mac."
        echo "   Download from: https://www.docker.com/products/docker-desktop"
        exit 1
    fi

    echo "✅ Docker setup complete"
}

# Function to initialize database with sample data
init_database() {
    echo "📊 Initializing database with sample data..."

    # Run database initialization
    python -c "
from src.database.connection import db_manager
try:
    db_manager.create_tables()
    print('✅ Database tables created successfully')
except Exception as e:
    print(f'❌ Database initialization failed: {e}')
    exit(1)
" || echo "⚠️ Database initialization had issues"

    echo "✅ Database initialization complete"
}

# Function to run tests
run_tests() {
    echo "🧪 Running tests to verify installation..."

    # Run unit tests
    python -m pytest tests/ -v --tb=short

    if [ $? -eq 0 ]; then
        echo "✅ All tests passed!"
    else
        echo "⚠️ Some tests failed. Check the output above."
    fi
}

# Function to create systemd-like services for macOS
setup_services() {
    echo "🛠️ Setting up background services..."

    # Create LaunchAgents directory
    mkdir -p ~/Library/LaunchAgents

    # Create service files for the different components
    cat > ~/Library/LaunchAgents/com.twstock.scanner.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.twstock.scanner</string>
    <key>ProgramArguments</key>
    <array>
        <string>REPLACE_WITH_PROJECT_PATH/venv/bin/python</string>
        <string>-m</string>
        <string>src.scanner.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>REPLACE_WITH_PROJECT_PATH</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/logs/scanner.log</string>
    <key>StandardOutPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/logs/scanner.log</string>
</dict>
</plist>
EOF

    cat > ~/Library/LaunchAgents/com.twstock.telegram.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.twstock.telegram</string>
    <key>ProgramArguments</key>
    <array>
        <string>REPLACE_WITH_PROJECT_PATH/venv/bin/python</string>
        <string>-m</string>
        <string>src.telegram.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>REPLACE_WITH_PROJECT_PATH</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/logs/telegram.log</string>
    <key>StandardOutPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/logs/telegram.log</string>
</dict>
</plist>
EOF

    # Replace placeholder with actual path
    PROJECT_PATH=$(pwd)
    sed -i '' "s|REPLACE_WITH_PROJECT_PATH|$PROJECT_PATH|g" ~/Library/LaunchAgents/com.twstock.*.plist

    echo "✅ Service files created (use 'launchctl load/unload' to manage)"
}

# Function to create management scripts
create_management_scripts() {
    echo "📜 Creating management scripts..."

    # Create start script
    cat > start.sh << 'EOF'
#!/bin/bash
echo "🚀 Starting Taiwan Stock Monitor services..."

# Start database services
brew services start postgresql@15
brew services start redis

# Start Docker Compose
docker-compose up -d

echo "✅ All services started!"
echo "📊 Access health check: http://localhost:8000/health"
echo "📈 Access metrics: http://localhost:9090/metrics"
EOF

    # Create stop script
    cat > stop.sh << 'EOF'
#!/bin/bash
echo "🛑 Stopping Taiwan Stock Monitor services..."

# Stop Docker Compose
docker-compose down

echo "✅ Services stopped!"
EOF

    # Create status script
    cat > status.sh << 'EOF'
#!/bin/bash
echo "📊 Taiwan Stock Monitor Status"
echo "================================"

# Check Docker services
echo "🐳 Docker Services:"
docker-compose ps

echo ""
echo "🗄️ Database Status:"
brew services list | grep postgres

echo ""
echo "📦 Redis Status:"
brew services list | grep redis

echo ""
echo "🌐 Health Check:"
curl -s http://localhost:8000/health | jq . || echo "❌ Health endpoint not available"
EOF

    # Create backup script
    cat > backup.sh << 'EOF'
#!/bin/bash
echo "💾 Creating backup..."

BACKUP_DIR="./data/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database
pg_dump tw_stock > "$BACKUP_DIR/database.sql"

# Backup configuration
cp .env "$BACKUP_DIR/env_backup"

echo "✅ Backup created at: $BACKUP_DIR"
EOF

    # Make scripts executable
    chmod +x start.sh stop.sh status.sh backup.sh

    echo "✅ Management scripts created"
}

# Main installation function
main() {
    echo "🎯 Taiwan Stock Monitor Installation for Mac Mini 2015"
    echo "======================================================"

    # Check system requirements
    echo "📋 Checking system requirements..."

    # Check macOS version
    MACOS_VERSION=$(sw_vers -productVersion)
    echo "💻 macOS Version: $MACOS_VERSION"

    # Check available memory
    MEMORY_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    echo "🧠 Available Memory: ${MEMORY_GB}GB"

    if [ $MEMORY_GB -lt 4 ]; then
        echo "⚠️  Warning: Less than 4GB RAM detected. Performance may be limited."
    fi

    # Check available disk space
    DISK_AVAILABLE=$(df -h . | awk 'NR==2{print $4}')
    echo "💽 Available Disk Space: $DISK_AVAILABLE"

    echo ""
    echo "🔧 Starting installation process..."
    echo ""

    # Run installation steps
    install_with_brew
    setup_python_env
    setup_database
    setup_redis
    setup_config
    setup_docker
    init_database
    setup_services
    create_management_scripts

    # Optional: Run tests
    read -p "🧪 Run tests to verify installation? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        run_tests
    fi

    echo ""
    echo "🎉 Installation completed successfully!"
    echo ""
    echo "📝 Next steps:"
    echo "1. Edit .env file with your API credentials"
    echo "2. Run './start.sh' to start all services"
    echo "3. Check status with './status.sh'"
    echo "4. Access health check: http://localhost:8000/health"
    echo ""
    echo "📚 Useful commands:"
    echo "  ./start.sh    - Start all services"
    echo "  ./stop.sh     - Stop all services"
    echo "  ./status.sh   - Check service status"
    echo "  ./backup.sh   - Create system backup"
    echo ""
    echo "📖 For more information, see README.md"
}

# Run main function
main "$@"