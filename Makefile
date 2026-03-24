# Taiwan Stock Monitor Makefile
# Convenient commands for development and deployment

.PHONY: help install test clean dev prod stop logs backup

# Default target
help:
	@echo "🎯 Taiwan Stock Monitor Commands"
	@echo "================================"
	@echo "Development:"
	@echo "  make install    - Install dependencies and setup environment"
	@echo "  make dev        - Start development environment"
	@echo "  make test       - Run all tests"
	@echo "  make lint       - Run code linting"
	@echo "  make format     - Format code"
	@echo ""
	@echo "Production:"
	@echo "  make prod       - Start production environment"
	@echo "  make stop       - Stop all services"
	@echo "  make restart    - Restart all services"
	@echo "  make logs       - View service logs"
	@echo "  make backup     - Create system backup"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate - Run database migrations"
	@echo "  make db-reset   - Reset database (DANGER: deletes all data)"
	@echo "  make db-seed    - Seed database with sample data"
	@echo ""
	@echo "Monitoring:"
	@echo "  make health     - Check system health"
	@echo "  make metrics    - View system metrics"
	@echo "  make status     - Show service status"
	@echo ""
	@echo "Git Operations:"
	@echo "  make commit MSG='message' - Create commit with message"
	@echo "  make smart-commit - Auto-detect changes and commit"
	@echo "  make git-status  - Show git status with file changes"
	@echo "  make git-log     - Show recent commit history"

# Installation and setup
install:
	@echo "📦 Installing Taiwan Stock Monitor..."
	chmod +x deploy/install.sh
	./deploy/install.sh

# Development environment
dev:
	@echo "🔧 Starting development environment..."
	docker-compose up --build

dev-daemon:
	@echo "🔧 Starting development environment in background..."
	docker-compose up -d --build

# Production environment
prod:
	@echo "🚀 Starting production environment..."
	docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

# Stop all services
stop:
	@echo "🛑 Stopping all services..."
	docker-compose down
	docker-compose -f deploy/docker-compose.prod.yml down 2>/dev/null || true

# Restart services
restart: stop prod

# View logs
logs:
	@echo "📋 Viewing service logs..."
	docker-compose logs -f --tail=100

logs-scanner:
	@echo "📋 Viewing scanner logs..."
	docker-compose logs -f scanner

logs-telegram:
	@echo "📋 Viewing telegram logs..."
	docker-compose logs -f telegram-bot

logs-app:
	@echo "📋 Viewing app logs..."
	docker-compose logs -f app

# Testing
test:
	@echo "🧪 Running all tests..."
	python -m pytest tests/ -v

test-unit:
	@echo "🧪 Running unit tests..."
	python -m pytest tests/ -v -m "not integration"

test-integration:
	@echo "🧪 Running integration tests..."
	python -m pytest tests/ -v -m "integration"

test-coverage:
	@echo "🧪 Running tests with coverage..."
	python -m pytest tests/ --cov=src --cov-report=html --cov-report=term

# Code quality
lint:
	@echo "🔍 Running code linting..."
	python -m flake8 src/
	python -m mypy src/ --ignore-missing-imports

format:
	@echo "🎨 Formatting code..."
	python -m black src/ tests/
	python -m isort src/ tests/

# Database operations
db-migrate:
	@echo "🗄️ Running database migrations..."
	python -c "from src.database.connection import db_manager; db_manager.create_tables()"

db-reset:
	@echo "⚠️  WARNING: This will delete ALL data!"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@echo "🗄️ Resetting database..."
	docker-compose exec postgres psql -U postgres -d tw_stock -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	python -c "from src.database.connection import db_manager; db_manager.create_tables()"

db-seed:
	@echo "🌱 Seeding database with sample data..."
	python scripts/seed_database.py

db-backup:
	@echo "💾 Creating database backup..."
	mkdir -p data/backups
	docker-compose exec postgres pg_dump -U postgres tw_stock > data/backups/backup_$(shell date +%Y%m%d_%H%M%S).sql

db-restore:
	@echo "🔄 Restoring database from backup..."
	@read -p "Enter backup file name: " backup && \
	docker-compose exec postgres psql -U postgres tw_stock < data/backups/$$backup

# System monitoring and health
health:
	@echo "🩺 Checking system health..."
	@curl -s http://localhost:8000/health | jq . || echo "❌ Health endpoint not available"

metrics:
	@echo "📊 Showing system metrics..."
	@curl -s http://localhost:8000/metrics/performance | jq . || echo "❌ Metrics endpoint not available"

status:
	@echo "📈 System status:"
	@echo "=================="
	@echo "🐳 Docker Services:"
	@docker-compose ps
	@echo ""
	@echo "🗄️ Database Status:"
	@docker-compose exec postgres pg_isready -U postgres || echo "❌ Database not ready"
	@echo ""
	@echo "📦 Redis Status:"
	@docker-compose exec redis redis-cli ping || echo "❌ Redis not ready"

# Backup and maintenance
backup:
	@echo "💾 Creating full system backup..."
	./backup.sh

clean:
	@echo "🧹 Cleaning up..."
	docker-compose down -v
	docker system prune -f
	docker volume prune -f

# Performance monitoring
monitor:
	@echo "📊 Starting monitoring dashboard..."
	docker-compose --profile monitoring up -d prometheus grafana
	@echo "📊 Grafana available at: http://localhost:3000"
	@echo "📈 Prometheus available at: http://localhost:9090"

# Quick start for development
quick-start: install dev

# Production deployment
deploy: install prod

# Update system
update:
	@echo "🔄 Updating Taiwan Stock Monitor..."
	git pull
	docker-compose pull
	docker-compose build --no-cache
	make restart

# Performance test
perf-test:
	@echo "⚡ Running performance tests..."
	python -m pytest tests/ -v -m "slow" --durations=10

# Security scan
security-scan:
	@echo "🔒 Running security scan..."
	python -m safety check
	python -m bandit -r src/

# Documentation
docs:
	@echo "📚 Building documentation..."
	mkdocs build

docs-serve:
	@echo "📚 Serving documentation..."
	mkdocs serve

# Environment validation
validate-env:
	@echo "✅ Validating environment..."
	@python -c " \
import os; \
required_vars = ['FUBON_API_KEY', 'FUBON_SECRET', 'TELEGRAM_BOT_TOKEN', 'POSTGRES_PASSWORD']; \
missing = [var for var in required_vars if not os.getenv(var)]; \
print('❌ Missing environment variables: ' + str(missing)) if missing else print('✅ All required environment variables are set'); \
exit(1) if missing else None \
"

# System info
info:
	@echo "ℹ️  System Information"
	@echo "====================="
	@echo "🐳 Docker Version:" && docker --version
	@echo "🐍 Python Version:" && python --version
	@echo "💻 System:" && uname -a
	@echo "🧠 Memory:" && free -h 2>/dev/null || vm_stat | head -5
	@echo "💽 Disk:" && df -h . | head -2

# Git operations
commit:
	@if [ -z "$(MSG)" ]; then \
		echo "❌ Please provide a commit message: make commit MSG='your message'"; \
		exit 1; \
	fi
	@echo "📝 Creating commit with message: $(MSG)"
	./scripts/auto-commit.sh "$(MSG)"

smart-commit:
	@echo "🤖 Running smart commit..."
	./scripts/smart-commit.sh -y

git-status:
	@echo "📊 Git Status"
	@echo "============="
	@git status --short --branch
	@echo ""
	@echo "📋 Recent Changes:"
	@git diff --stat

git-log:
	@echo "📜 Recent Commit History"
	@echo "======================="
	@git log --oneline --graph --decorate -10

git-setup:
	@echo "⚙️  Setting up Git configuration..."
	@git config user.name "Taiwan Stock Monitor"
	@git config user.email "dev@twstock.local"
	@echo "✅ Git configuration completed"