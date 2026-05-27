"""
周線趨勢過濾回測比較
=====================
比較啟用/停用 require_weekly_trend 的回測績效差異。
"""
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

os.environ.setdefault("BACKTEST_ENABLE_SECTOR_TREND_FILTER", "false")

from src.infrastructure.market_data.backtest_data_source import YFinanceDataSource
from src.application.services.backtest_strategy import TechnicalStrategy
from src.application.services.backtest_engine import BacktestEngine
from src.domain.models import SignalType
from config.settings import settings

cfg = settings.backtest
START_DATE = date(2024, 9, 1)
END_DATE = date(2025, 12, 31)
INITIAL_CAPITAL = Decimal("1000000")


def _build_strategy(require_weekly_trend: bool) -> TechnicalStrategy:
    disabled = [s.strip() for s in cfg.disabled_signals.split(",") if s.strip()]
    return TechnicalStrategy(
        rsi_min_entry=cfg.rsi_min_entry,
        disabled_signals=disabled,
        require_ma60_uptrend=cfg.require_ma60_uptrend,
        require_volume_confirmation=cfg.require_volume_confirmation,
        volume_confirmation_multiplier=cfg.volume_confirmation_multiplier,
        rsi_overbought_threshold=cfg.rsi_overbought_threshold,
        donchian_period=cfg.donchian_period,
        min_volume_lots=cfg.min_volume_lots,
        signal_cooldown_days=cfg.signal_cooldown_days,
        require_weekly_trend=require_weekly_trend,
    )


def _build_engine() -> BacktestEngine:
    """Build a properly configured BacktestEngine (mirrors backtest_main.py)."""
    def _parse_signals(s: str):
        items = [x.strip() for x in s.split(",") if x.strip()]
        return items if items else None

    engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
        take_profit_pct=Decimal(str(cfg.take_profit_pct)),
        trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
        max_holding_days=cfg.max_holding_days,
        position_sizing=Decimal(str(cfg.position_sizing)),
        market_regime_strong_rsi=cfg.market_regime_strong_rsi,
        strong_regime_signals=_parse_signals(cfg.strong_regime_signals),
        neutral_regime_signals=_parse_signals(cfg.neutral_regime_signals),
        strong_trend_signals=_parse_signals(cfg.strong_trend_signals),
        strong_trend_multiplier=cfg.strong_trend_multiplier,
    )

    # Configure trend signal exit parameters
    trend_names = [s.strip() for s in cfg.trend_signal_names.split(",") if s.strip()]
    if trend_names:
        eff_trailing = Decimal(str(cfg.trend_trailing_stop_pct)) if cfg.trend_use_trailing_stop else Decimal('0')
        eff_exit_signals = None if cfg.trend_use_trailing_stop else (
            [s.strip() for s in cfg.trend_exit_on_signals.split(",") if s.strip()] or None
        )
        trend_exit = {
            name: {
                "stop_loss_pct": Decimal(str(cfg.trend_stop_loss_pct)),
                "trailing_stop_pct": eff_trailing,
                "take_profit_pct": Decimal(str(cfg.trend_take_profit_pct)),
                "max_holding_days": cfg.trend_max_holding_days,
                "exit_on_signals": eff_exit_signals,
                "profit_threshold_pct": Decimal(str(cfg.trend_profit_threshold_pct)),
                "profit_trailing_pct": Decimal(str(cfg.trend_profit_trailing_pct)),
            }
            for name in trend_names
        }
        engine.set_signal_exit_config(trend_exit)
    return engine


def run_backtest(stock_data: dict, require_weekly_trend: bool, benchmark_data=None) -> dict:
    """Run backtest and return summary."""
    strategy = _build_strategy(require_weekly_trend)
    engine = _build_engine()

    # Add price data to engine (required for position management)
    for symbol, data in stock_data.items():
        engine.add_price_data(symbol, data)

    # Momentum whitelist
    if cfg.momentum_top_n > 0:
        print(f"  Building momentum rankings (top {cfg.momentum_top_n})...")
        momentum_whitelist = strategy.build_momentum_rankings(
            stock_data_dict=stock_data,
            lookback_days=cfg.momentum_lookback_days,
            top_n=cfg.momentum_top_n,
            start_date=START_DATE,
            end_date=END_DATE,
        )
        engine.set_momentum_whitelist(momentum_whitelist)

    print(f"  Generating signals (weekly_trend={require_weekly_trend})...")
    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=stock_data,
        start_date=START_DATE,
        end_date=END_DATE,
    )

    buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
    print(f"  BUY signals: {len(buy_signals)}")

    print(f"  Running backtest engine...")
    results = engine.run_backtest(
        signals=signals,
        start_date=START_DATE,
        end_date=END_DATE,
        benchmark_data=benchmark_data,
        market_regime_rsi_threshold=cfg.market_regime_rsi_threshold,
        market_regime_check_ma5=cfg.market_regime_check_ma5,
    )

    return {
        "require_weekly_trend": require_weekly_trend,
        "buy_signals": len(buy_signals),
        "total_trades": int(results.total_trades),
        "win_rate": float(results.win_rate),
        "total_return": float(results.total_return_pct),
        "sharpe": float(results.sharpe_ratio) if results.sharpe_ratio else 0.0,
        "max_drawdown": float(results.max_drawdown) if results.max_drawdown else 0.0,
    }


def main():
    print("Loading stock data...")
    data_source = YFinanceDataSource()
    stocks_dir = str(PROJECT_ROOT / "data" / "stocks")
    stock_data = data_source.load_from_stocks_dir(
        stocks_dir=stocks_dir,
        start_date=START_DATE - timedelta(days=200),
        end_date=END_DATE,
    )
    print(f"Loaded {len(stock_data)} stocks")

    print("Fetching benchmark data (TAIEX)...")
    benchmark_data = data_source.get_market_index_data(START_DATE, END_DATE)
    print()

    results = []
    for use_weekly in [False, True]:
        label = "weekly_trend=ON " if use_weekly else "weekly_trend=OFF"
        print(f"=== {label} ===")
        r = run_backtest(stock_data, require_weekly_trend=use_weekly, benchmark_data=benchmark_data)
        results.append(r)
        print()

    print("=" * 66)
    print(f"{'Metric':<30} {'weekly_trend=OFF':>18} {'weekly_trend=ON':>18}")
    print("-" * 66)
    for metric in ["buy_signals", "total_trades", "win_rate", "total_return", "sharpe", "max_drawdown"]:
        a = results[0][metric]
        b = results[1][metric]
        if isinstance(a, float):
            if metric in ("win_rate", "total_return", "max_drawdown"):
                print(f"{metric:<30} {a:>17.2f}% {b:>17.2f}%")
            else:
                print(f"{metric:<30} {a:>18.3f} {b:>18.3f}")
        else:
            print(f"{metric:<30} {a:>18} {b:>18}")
    print("=" * 66)


if __name__ == "__main__":
    main()
