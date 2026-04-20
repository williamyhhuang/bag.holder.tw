"""
Application configuration settings
"""
import json
import os
from datetime import date
from typing import List, Optional, Set
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
    debug: bool = Field(default=True, env="APP_DEBUG")
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
    cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:8080"], env="CORS_ORIGINS")

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

class DownloadSettings(BaseSettings):
    """Data download configuration"""
    batch_size: int = Field(default=200, env="DOWNLOAD_BATCH_SIZE")

    class Config:
        env_prefix = "DOWNLOAD_"

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

class BacktestSettings(BaseSettings):
    """Backtest execution configuration"""

    # 排除特定 TWSE 產業類別代碼的股票
    # 31 = 生技醫療業（證交所官方產業別代碼）
    exclude_industry_codes: List[int] = Field(
        default=[31],
        env="BACKTEST_EXCLUDE_INDUSTRY_CODES",
        description="TWSE 產業類別代碼排除清單，預設排除生技醫療業 (31)",
    )

    # 產業代碼對應表路徑（相對於專案根目錄）
    industry_code_map_path: str = Field(
        default="config/industry_codes.json",
        env="BACKTEST_INDUSTRY_CODE_MAP_PATH",
    )

    # ── 停損 / 停利設定 ─────────────────────────────────────────────
    # 停利從 20% 降至 10%：Q4 2025 最高獲利僅 9.96%，20% 目標從未觸發
    take_profit_pct: float = Field(
        default=0.10,
        env="BACKTEST_TAKE_PROFIT_PCT",
        description="停利百分比（0.10 = 10%）",
    )
    # 停損維持 5%
    stop_loss_pct: float = Field(
        default=0.10,
        env="BACKTEST_STOP_LOSS_PCT",
        description="停損百分比（0.10 = 10%）",
    )
    # 追蹤停損從 5% 縮至 3%：更早鎖住已實現的利潤
    trailing_stop_pct: float = Field(
        default=0.03,
        env="BACKTEST_TRAILING_STOP_PCT",
        description="追蹤停損百分比（0.03 = 3%）",
    )
    # 最長持倉從 30 天縮至 15 天：減少持有不動的死掌
    max_holding_days: int = Field(
        default=15,
        env="BACKTEST_MAX_HOLDING_DAYS",
        description="最長持倉天數",
    )

    # ── 進場品質過濾 ────────────────────────────────────────────────
    # RSI 最低進場門檻：確認股票具備上漲動能，避免 BB 假突破
    # BB Squeeze Break 在 Q4 2025 勝率僅 44.8%，加入 RSI ≥ 50 過濾
    rsi_min_entry: float = Field(
        default=50.0,
        env="BACKTEST_RSI_MIN_ENTRY",
        description="RSI 進場最低門檻（50 = 股票需具備上漲動能）",
    )

    # ── TechnicalStrategy 對應參數（與 strategy.py 一致）───────────
    # Filter 1: 停用的訊號名稱（逗號分隔）
    # P1 (2026-04-08): 恢復 Golden Cross + MACD Golden Cross
    # 診斷顯示停用它們讓報酬率 -5.90%
    disabled_signals: str = Field(
        default="",
        env="BACKTEST_DISABLED_SIGNALS",
        description="停用的訊號名稱，逗號分隔（空白 = 全部啟用）",
    )
    # Filter 2: 個股價格需在 MA60 上方（長期上升趨勢）
    require_ma60_uptrend: bool = Field(
        default=True,
        env="BACKTEST_REQUIRE_MA60_UPTREND",
        description="進場時個股需在 MA60 上方",
    )
    # Filter 3: 進場量能確認
    # P1 (2026-04-08): 停用 Volume Confirmation（診斷顯示讓報酬率 -4.55%）
    require_volume_confirmation: bool = Field(
        default=False,
        env="BACKTEST_REQUIRE_VOLUME_CONFIRMATION",
        description="進場時需量能確認（False = 停用）",
    )
    volume_confirmation_multiplier: float = Field(
        default=1.5,
        env="BACKTEST_VOLUME_CONFIRMATION_MULTIPLIER",
        description="量能確認倍數（預設 1.5 = 當日量 > 1.5× MA20 量）",
    )
    # RSI 超買門檻（賣出訊號參考）
    rsi_overbought_threshold: float = Field(
        default=70.0,
        env="BACKTEST_RSI_OVERBOUGHT_THRESHOLD",
        description="RSI 超買門檻（70 = 出現超買訊號）",
    )
    # Filter 6: 最低成交張數門檻（流動性過濾）
    # 1 張 = 1,000 股；設 1000 = 成交量需 >= 1,000,000 股；0 = 停用
    min_volume_lots: int = Field(
        default=1000,
        env="BACKTEST_MIN_VOLUME_LOTS",
        description="最低成交張數門檻（1 張=1,000 股；0=停用）",
    )

    # ── 大盤市場環境過濾 ─────────────────────────────────────────────
    # 三層大盤篩選（任一為 False 即暫停新進場）：
    #   1. TAIEX 收盤 >= MA20（價格在長期均線上方）
    #   2. TAIEX MA5 >= MA20（短期趨勢優於長期趨勢）
    #   3. TAIEX RSI(14) >= market_regime_rsi_threshold（大盤具備上漲動能）
    # Q4 2025 策略虧損 15%，大盤卻漲 11%，根本原因是沒有偵測市場環境
    market_regime_rsi_threshold: float = Field(
        default=40.0,
        env="BACKTEST_MARKET_REGIME_RSI_THRESHOLD",
        description="大盤 RSI 進場門檻（45 = 大盤需具備基本動能）",
    )
    market_regime_check_ma5: bool = Field(
        default=True,
        env="BACKTEST_MARKET_REGIME_CHECK_MA5",
        description="是否啟用 TAIEX MA5 > MA20 趨勢對齊檢查",
    )

    # ── P3-C 市場環境分層訊號路由 ────────────────────────────────────
    # STRONG (RSI >= market_regime_strong_rsi): 允許趨勢跟蹤 + 均值回歸訊號
    # NEUTRAL (RSI < strong_rsi): 僅允許均值回歸訊號（BB Squeeze Break）
    # WEAK (市場環境過濾觸發): 暫停所有買進
    market_regime_strong_rsi: float = Field(
        default=60.0,
        env="BACKTEST_MARKET_REGIME_STRONG_RSI",
        description="TAIEX RSI 超過此值視為強勢市場（啟用趨勢訊號）",
    )
    # None / 空字串 = 該 regime 允許所有訊號
    strong_regime_signals: str = Field(
        default="",
        env="BACKTEST_STRONG_REGIME_SIGNALS",
        description="強勢市場允許的訊號（空白 = 全部）",
    )
    neutral_regime_signals: str = Field(
        default="BB Squeeze Break,RSI Oversold,Golden Cross,MACD Golden Cross",
        env="BACKTEST_NEUTRAL_REGIME_SIGNALS",
        description="中性市場允許的訊號（空白 = 全部）",
    )

    # ── P5 趨勢訊號加倍倉位 ───────────────────────────────────────────
    # STRONG 市場環境下，趨勢訊號使用 position_sizing * multiplier 的倉位
    # P6b: 移除 Golden Cross（勝率 26.1%），只保留 Donchian Breakout + MACD Golden Cross
    strong_trend_signals: str = Field(
        default="Donchian Breakout,MACD Golden Cross",
        env="BACKTEST_STRONG_TREND_SIGNALS",
        description="STRONG 市場下使用加倍倉位的趨勢訊號（逗號分隔）",
    )
    strong_trend_multiplier: float = Field(
        default=2.0,
        env="BACKTEST_STRONG_TREND_MULTIPLIER",
        description="STRONG 市場下趨勢訊號倉位乘數（2.0 = 10%，其餘信號維持 5%）",
    )

    # ── P6 趨勢訊號出場參數 ──────────────────────────────────────────
    # 趨勢訊號（Donchian Breakout / Golden Cross / MACD GC）使用較寬的停損與較長持倉
    # 讓趨勢有空間發展，而不被 3% 追蹤停損提早出場
    trend_signal_names: str = Field(
        default="Donchian Breakout,MACD Golden Cross",
        env="BACKTEST_TREND_SIGNAL_NAMES",
        description="套用趨勢出場參數的訊號名稱（逗號分隔）",
    )
    trend_stop_loss_pct: float = Field(
        default=0.15,
        env="BACKTEST_TREND_STOP_LOSS_PCT",
        description="趨勢訊號停損百分比（0.15 = 15%；寬停損讓 trailing stop 有空間發揮）",
    )
    trend_trailing_stop_pct: float = Field(
        default=0.08,
        env="BACKTEST_TREND_TRAILING_STOP_PCT",
        description="趨勢訊號追蹤停損百分比（0.08 = 8%；trend_use_trailing_stop=False 時忽略）",
    )
    # P3-B: 訊號式出場 — 趨勢倉位不使用追蹤停損，改用 MACD 死叉等訊號出場
    trend_use_trailing_stop: bool = Field(
        default=True,
        env="BACKTEST_TREND_USE_TRAILING_STOP",
        description="趨勢倉位是否啟用追蹤停損（True = 用 8% trailing；False = 改用 trend_exit_on_signals 訊號出場）",
    )
    trend_exit_on_signals: str = Field(
        default="RSI Momentum Loss,MACD Death Cross,Death Cross",
        env="BACKTEST_TREND_EXIT_ON_SIGNALS",
        description="趨勢倉位的訊號式出場觸發訊號（逗號分隔；trend_use_trailing_stop=False 時啟用）",
    )
    # P3-B/C: 獲利保護停損 — 倉位獲利超過門檻後才啟動追蹤停損，保護已獲利的部位
    trend_profit_threshold_pct: float = Field(
        default=0.05,
        env="BACKTEST_TREND_PROFIT_THRESHOLD_PCT",
        description="啟動獲利保護停損的獲利門檻（0.05 = 5%）",
    )
    trend_profit_trailing_pct: float = Field(
        default=0.06,
        env="BACKTEST_TREND_PROFIT_TRAILING_PCT",
        description="獲利保護停損從最高點回撤百分比（0.06 = 6%）",
    )
    trend_take_profit_pct: float = Field(
        default=0.40,
        env="BACKTEST_TREND_TAKE_PROFIT_PCT",
        description="趨勢訊號停利百分比（0.40 = 40%，高門檻讓趨勢跑）",
    )
    trend_max_holding_days: int = Field(
        default=60,
        env="BACKTEST_TREND_MAX_HOLDING_DAYS",
        description="趨勢訊號最長持倉天數（60 天，讓趨勢充分發展）",
    )
    donchian_period: int = Field(
        default=50,
        env="BACKTEST_DONCHIAN_PERIOD",
        description="Donchian Channel 突破回看天數（50 = 過去 50 個交易日最高，回測最佳值）",
    )

    # ── P4 持倉規模設定 ──────────────────────────────────────────────
    # 每筆交易佔初始資金比例（0.05 = 5%）
    # P4 (2026-04-08): 從 10% 降至 5%，允許最多 ~20 倉位同時運行，提升大盤曝險
    position_sizing: float = Field(
        default=0.05,
        env="BACKTEST_POSITION_SIZING",
        description="每筆交易佔初始資金比例（0.05 = 5%，允許最多 20 倉位同時運行）",
    )

    # ── 族群趨勢過濾 ─────────────────────────────────────────────────
    # 只保留強勢族群的買入訊號，過濾掉弱勢族群
    # 強勢族群定義：族群內超過 threshold 比例的股票收盤 > MA20
    enable_sector_trend_filter: bool = Field(
        default=True,
        env="BACKTEST_ENABLE_SECTOR_TREND_FILTER",
        description="啟用族群趨勢過濾（True = 只保留強勢族群的買入訊號）",
    )
    sector_trend_threshold: float = Field(
        default=0.5,
        env="BACKTEST_SECTOR_TREND_THRESHOLD",
        description="族群強勢門檻（0.5 = 族群內 50% 以上股票在 MA20 上方視為強勢）",
    )

    # ── 月營收門檻 ───────────────────────────────────────────────────
    # 過濾每月營收過低的股票（資料來自 TWSE / TPEX OpenAPI，當日快取）
    # 單位：百萬元（NTD million）；0 = 停用；直接在此修改數值即可
    # 1 億元 = 100 百萬元
    min_monthly_revenue_million: float = 100.0

    # ── 同股票買入冷卻期 ──────────────────────────────────────────────
    # 同一支股票在最近 signal_cooldown_days 個交易日內已觸發過買入訊號，
    # 就自動跳過（降級為 WATCH），避免同一波上漲中反覆進場。
    # 0 = 停用；建議值 10（約 2 個交易週）
    signal_cooldown_days: int = Field(
        default=0,
        env="BACKTEST_SIGNAL_COOLDOWN_DAYS",
        description="同股票買入冷卻期（交易日數；0 = 停用）",
    )

    # ── 動能排名過濾 ─────────────────────────────────────────────────
    # 每個交易日，只允許近 N 日動能排名前 top_n 的股票發出買進訊號
    # 避免進場動能不足的股票，即使它們觸發了 BB Squeeze Break
    momentum_top_n: int = Field(
        default=30,
        env="BACKTEST_MOMENTUM_TOP_N",
        description="每日動能排名篩選，只交易前 N 名（0 = 停用；30 = 回測最佳值）",
    )
    momentum_lookback_days: int = Field(
        default=20,
        env="BACKTEST_MOMENTUM_LOOKBACK_DAYS",
        description="計算動能的回看天數（預設 20 個交易日）",
    )

    # ── 回測時間範圍 ─────────────────────────────────────────────────
    # 格式：YYYY-MM-DD；留空則預設為今天（end_date）或程式預設值（start_date）
    # 欄位名不加 backtest_ 前綴，避免與 env_prefix="BACKTEST_" 疊加成 BACKTEST_BACKTEST_*
    start_date: Optional[date] = Field(
        default=date(2024, 9, 1),
        description="回測起始日期（YYYY-MM-DD），留空使用程式預設值",
    )
    end_date: Optional[date] = Field(
        default=None,
        description="回測結束日期（YYYY-MM-DD），留空使用今天",
    )

    @validator("exclude_industry_codes", pre=True)
    def split_codes(cls, v):
        if isinstance(v, str):
            return [int(c.strip()) for c in v.split(",") if c.strip()]
        if isinstance(v, int):
            return [v]
        return v

    @validator("start_date", "end_date", pre=True)
    def parse_date(cls, v):
        """Accept YYYY-MM-DD strings; treat empty string as None."""
        if not v:
            return None
        if isinstance(v, date):
            return v
        from datetime import datetime
        return datetime.strptime(str(v).strip(), "%Y-%m-%d").date()

    def load_excluded_symbols(self, project_root: Path) -> Set[str]:
        """回傳應排除的股票代碼集合（依 exclude_industry_codes 設定）。

        讀取 industry_code_map_path 指定的 JSON，收集所有
        exclude_industry_codes 內產業別的股票代碼。
        """
        map_path = project_root / self.industry_code_map_path
        if not map_path.exists():
            return set()

        with open(map_path, encoding="utf-8") as f:
            data = json.load(f)

        excluded: Set[str] = set()
        for key, entry in data.items():
            if key.startswith("_"):
                continue
            if isinstance(entry, dict):
                code = entry.get("code")
                if code in self.exclude_industry_codes:
                    excluded.update(entry.get("stocks", []))
        return excluded

    class Config:
        env_prefix = "BACKTEST_"
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"


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
    download: DownloadSettings = DownloadSettings()
    strategy: StrategySettings = StrategySettings()
    backtest: BacktestSettings = BacktestSettings()

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