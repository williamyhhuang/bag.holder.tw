"""
Application configuration settings
"""
import os
from typing import List, Optional
from pathlib import Path

from pydantic import Field, validator
from pydantic_settings import BaseSettings

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent

class DatabaseSettings(BaseSettings):
    """Database configuration"""
    url: str = Field(default="postgresql://postgres:password@localhost:5432/tw_stock", env="DATABASE_URL")
    echo: bool = Field(default=False, env="DATABASE_ECHO")

    class Config:
        env_prefix = "DATABASE_"

class RedisSettings(BaseSettings):
    """Redis configuration"""
    url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    db: int = Field(default=0, env="REDIS_DB")

    class Config:
        env_prefix = "REDIS_"

class FubonAPISettings(BaseSettings):
    """Fubon API configuration for official SDK"""
    # Authentication Method 1: API Key (Recommended)
    api_key: Optional[str] = Field(default=None, env="FUBON_API_KEY")
    api_secret: Optional[str] = Field(default=None, env="FUBON_API_SECRET")

    # Authentication Method 2: Certificate File
    user_id: Optional[str] = Field(default=None, env="FUBON_USER_ID")
    password: Optional[str] = Field(default=None, env="FUBON_PASSWORD")
    cert_path: Optional[str] = Field(default=None, env="FUBON_CERT_PATH")
    cert_password: Optional[str] = Field(default=None, env="FUBON_CERT_PASSWORD")

    # Environment settings
    is_simulation: bool = Field(default=True, env="FUBON_IS_SIMULATION")
    rate_limit_per_minute: int = Field(default=30, env="FUBON_RATE_LIMIT_PER_MINUTE")

    @validator('api_key', 'api_secret', 'user_id', 'password')
    def check_authentication_method(cls, v, values):
        """Ensure at least one authentication method is provided"""
        # This validation will be performed when the settings are initialized
        return v

    def has_api_key_auth(self) -> bool:
        """Check if API key authentication is configured"""
        return bool(self.api_key and self.api_secret)

    def has_cert_auth(self) -> bool:
        """Check if certificate authentication is configured"""
        return bool(self.user_id and self.cert_path)

    class Config:
        env_prefix = "FUBON_"

class TelegramSettings(BaseSettings):
    """Telegram bot configuration"""
    bot_token: str = Field(default="dummy_token", env="TELEGRAM_BOT_TOKEN")
    chat_id: str = Field(default="dummy_chat_id", env="TELEGRAM_CHAT_ID")
    webhook_url: Optional[str] = Field(default=None, env="TELEGRAM_WEBHOOK_URL")
    webhook_secret: Optional[str] = Field(default=None, env="TELEGRAM_WEBHOOK_SECRET")

    class Config:
        env_prefix = "TELEGRAM_"

class AppSettings(BaseSettings):
    """Application configuration"""
    name: str = Field(default="tw-stock-monitor", env="APP_NAME")
    version: str = Field(default="1.0.0", env="APP_VERSION")
    environment: str = Field(default="development", env="APP_ENV")
    debug: bool = Field(default=False, env="APP_DEBUG")
    host: str = Field(default="0.0.0.0", env="APP_HOST")
    port: int = Field(default=8000, env="APP_PORT")

    class Config:
        env_prefix = "APP_"

class LoggingSettings(BaseSettings):
    """Logging configuration"""
    level: str = Field(default="INFO", env="LOG_LEVEL")
    file_path: str = Field(default="logs/app.log", env="LOG_FILE_PATH")
    max_file_size: str = Field(default="10MB", env="LOG_MAX_FILE_SIZE")
    backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")

    class Config:
        env_prefix = "LOG_"

class ScannerSettings(BaseSettings):
    """Scanner configuration"""
    interval_seconds: int = Field(default=300, env="SCAN_INTERVAL_SECONDS")
    batch_size: int = Field(default=50, env="SCAN_BATCH_SIZE")
    max_concurrent: int = Field(default=10, env="SCAN_MAX_CONCURRENT")
    enabled_markets: List[str] = Field(default=["TSE", "OTC"], env="SCAN_ENABLED_MARKETS")

    @validator('enabled_markets', pre=True)
    def split_markets(cls, v):
        if isinstance(v, str):
            return [market.strip() for market in v.split(',')]
        return v

    class Config:
        env_prefix = "SCAN_"

class IndicatorSettings(BaseSettings):
    """Technical indicators configuration"""
    ma_periods: List[int] = Field(default=[5, 10, 20, 60], env="INDICATORS_MA_PERIODS")
    rsi_period: int = Field(default=14, env="INDICATORS_RSI_PERIOD")
    macd_fast: int = Field(default=12, env="INDICATORS_MACD_FAST")
    macd_slow: int = Field(default=26, env="INDICATORS_MACD_SLOW")
    macd_signal: int = Field(default=9, env="INDICATORS_MACD_SIGNAL")
    bb_period: int = Field(default=20, env="INDICATORS_BB_PERIOD")
    bb_std_dev: float = Field(default=2.0, env="INDICATORS_BB_STD_DEV")

    @validator('ma_periods', pre=True)
    def split_ma_periods(cls, v):
        if isinstance(v, str):
            return [int(period.strip()) for period in v.split(',')]
        return v

    class Config:
        env_prefix = "INDICATORS_"

class AlertSettings(BaseSettings):
    """Alert configuration"""
    enabled: bool = Field(default=True, env="ALERT_ENABLED")
    cooldown_minutes: int = Field(default=60, env="ALERT_COOLDOWN_MINUTES")
    max_per_stock_per_day: int = Field(default=5, env="ALERT_MAX_PER_STOCK_PER_DAY")
    batch_size: int = Field(default=20, env="ALERT_BATCH_SIZE")

    class Config:
        env_prefix = "ALERT_"

class DataRetentionSettings(BaseSettings):
    """Data retention configuration"""
    retention_days: int = Field(default=365, env="DATA_RETENTION_DAYS")
    cleanup_interval_hours: int = Field(default=24, env="CLEANUP_INTERVAL_HOURS")
    auto_cleanup_enabled: bool = Field(default=True, env="AUTO_CLEANUP_ENABLED")

    class Config:
        env_prefix = "DATA_"

class SecuritySettings(BaseSettings):
    """Security configuration"""
    secret_key: str = Field(default="dummy_secret_key", env="SECRET_KEY")
    allowed_hosts: List[str] = Field(default=["localhost", "127.0.0.1"], env="ALLOWED_HOSTS")
    cors_origins: List[str] = Field(default=[], env="CORS_ORIGINS")

    @validator('allowed_hosts', 'cors_origins', pre=True)
    def split_hosts(cls, v):
        if isinstance(v, str):
            return [host.strip() for host in v.split(',') if host.strip()]
        return v

    class Config:
        env_prefix = "SECURITY_"

class FuturesSettings(BaseSettings):
    """Futures monitoring configuration"""
    enabled_contracts: List[str] = Field(default=["TXF", "MXF", "MTX"], env="FUTURES_ENABLED_CONTRACTS")
    monitor_interval: int = Field(default=30, env="FUTURES_MONITOR_INTERVAL")
    max_position_size: int = Field(default=10, env="FUTURES_MAX_POSITION_SIZE")

    @validator('enabled_contracts', pre=True)
    def split_contracts(cls, v):
        if isinstance(v, str):
            return [contract.strip() for contract in v.split(',')]
        return v

    class Config:
        env_prefix = "FUTURES_"

class PerformanceSettings(BaseSettings):
    """Performance optimization settings (for Mac Mini 2015)"""
    max_workers: int = Field(default=2, env="MAX_WORKERS")
    memory_limit_mb: int = Field(default=2048, env="MEMORY_LIMIT_MB")
    cpu_limit: float = Field(default=2.0, env="CPU_LIMIT")
    batch_processing_delay: float = Field(default=1.0, env="BATCH_PROCESSING_DELAY")

class DataSettings(BaseSettings):
    """Data storage configuration"""
    stocks_path: str = Field(default="data/stocks", env="DATA_STOCKS_PATH")
    user_trades_path: str = Field(default="data/user_trades.csv", env="DATA_USER_TRADES_PATH")

    class Config:
        env_prefix = "DATA_"

class StrategySettings(BaseSettings):
    """Strategy configuration for stock filtering"""
    # RSI Settings
    rsi_oversold_threshold: float = Field(default=30.0, env="STRATEGY_RSI_OVERSOLD_THRESHOLD")
    rsi_overbought_threshold: float = Field(default=70.0, env="STRATEGY_RSI_OVERBOUGHT_THRESHOLD")
    rsi_period: int = Field(default=14, env="STRATEGY_RSI_PERIOD")

    # Volume Settings
    min_volume_momentum: int = Field(default=500000, env="STRATEGY_MIN_VOLUME_MOMENTUM")
    min_volume_oversold: int = Field(default=300000, env="STRATEGY_MIN_VOLUME_OVERSOLD")
    min_volume_breakout: int = Field(default=1000000, env="STRATEGY_MIN_VOLUME_BREAKOUT")
    min_volume_value: int = Field(default=200000, env="STRATEGY_MIN_VOLUME_VALUE")
    min_volume_high: int = Field(default=2000000, env="STRATEGY_MIN_VOLUME_HIGH")

    # Price Settings
    min_price: float = Field(default=10.0, env="STRATEGY_MIN_PRICE")
    momentum_price_change: float = Field(default=3.0, env="STRATEGY_MOMENTUM_PRICE_CHANGE")
    oversold_price_change: float = Field(default=-2.0, env="STRATEGY_OVERSOLD_PRICE_CHANGE")
    value_price_change_min: float = Field(default=-5.0, env="STRATEGY_VALUE_PRICE_CHANGE_MIN")
    value_price_change_max: float = Field(default=5.0, env="STRATEGY_VALUE_PRICE_CHANGE_MAX")

    # MA Settings
    ma_periods: List[int] = Field(default=[5, 10, 20, 60], env="STRATEGY_MA_PERIODS")

    # Score Settings
    rsi_extreme_score: float = Field(default=10.0, env="STRATEGY_RSI_EXTREME_SCORE")
    high_volume_score: float = Field(default=5.0, env="STRATEGY_HIGH_VOLUME_SCORE")
    price_change_high_score: float = Field(default=8.0, env="STRATEGY_PRICE_CHANGE_HIGH_SCORE")
    price_change_mid_score: float = Field(default=5.0, env="STRATEGY_PRICE_CHANGE_MID_SCORE")

    @validator('ma_periods', pre=True)
    def split_ma_periods(cls, v):
        if isinstance(v, str):
            return [int(period.strip()) for period in v.split(',')]
        return v

    class Config:
        env_prefix = "STRATEGY_"

class Settings(BaseSettings):
    """Main application settings"""
    # Sub-settings
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    fubon: FubonAPISettings = FubonAPISettings()
    telegram: TelegramSettings = TelegramSettings()
    app: AppSettings = AppSettings()
    logging: LoggingSettings = LoggingSettings()
    scanner: ScannerSettings = ScannerSettings()
    indicators: IndicatorSettings = IndicatorSettings()
    alerts: AlertSettings = AlertSettings()
    data_retention: DataRetentionSettings = DataRetentionSettings()
    security: SecuritySettings = SecuritySettings()
    futures: FuturesSettings = FuturesSettings()
    performance: PerformanceSettings = PerformanceSettings()
    data: DataSettings = DataSettings()
    strategy: StrategySettings = StrategySettings()

    class Config:
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = 'utf-8'
        case_sensitive = False
        extra = 'ignore'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Create required directories
        self._create_directories()

    def _create_directories(self):
        """Create required directories if they don't exist"""
        # Create logs directory
        log_dir = Path(self.logging.file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create data directory
        data_dir = PROJECT_ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Create config directory
        config_dir = PROJECT_ROOT / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.app.environment.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.app.environment.lower() == "production"

# Global settings instance
settings = Settings()