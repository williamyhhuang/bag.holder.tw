"""
Grid search: weekly_donchian_period (5 groups) + Direction B (dual Donchian)
Metric: total_return_pct * win_rate (maximise)
"""
import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.market_data.backtest_data_source import YFinanceDataSource
from src.application.services.backtest_engine import BacktestEngine
from src.application.services.backtest_strategy import TechnicalStrategy
from src.application.services.performance_analyzer import PerformanceAnalyzer
from src.interfaces.reporters.backtest_reporter import BacktestReporter
from src.domain.services.sector_trend_analyzer import SectorTrendAnalyzer
from src.infrastructure.market_data.yfinance_client import YFinanceClient
from config.settings import settings
from datetime import date, timedelta
from pathlib import Path


def build_strategy(cfg, weekly_donchian_period: int, donchian_period_2: int = 0):
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
        require_weekly_trend=cfg.require_weekly_trend,
        require_52w_filter=cfg.require_52w_filter,
        above_52w_low_pct=cfg.above_52w_low_pct,
        near_52w_high_pct=cfg.near_52w_high_pct,
        enable_vcp=cfg.enable_vcp,
        vcp_lookback=cfg.vcp_lookback,
        pre_breakout_mode=cfg.pre_breakout_mode,
        enable_momentum_signal=cfg.enable_momentum_signal,
        momentum_signal_days=cfg.momentum_signal_days,
        momentum_signal_min_return=cfg.momentum_signal_min_return,
        require_weekly_rsi=cfg.require_weekly_rsi,
        weekly_rsi_min=cfg.weekly_rsi_min,
        require_revenue_growth=cfg.require_revenue_growth,
        revenue_yoy_min_pct=cfg.revenue_yoy_min_pct,
        finmind_api_token=settings.finmind.api_token or "",
        weekly_close_only=cfg.weekly_close_only,
        require_minervini_trend=cfg.require_minervini_trend,
        min_confirming_signals=cfg.min_confirming_signals,
        enable_weekly_signals=True,           # always on
        weekly_bb_period=cfg.weekly_bb_period,
        weekly_donchian_period=weekly_donchian_period,
        donchian_period_2=donchian_period_2,
    )


async def run_one(cfg, stock_data, benchmark_data, sector_whitelist, label: str,
                  weekly_donchian_period: int, donchian_period_2: int = 0):
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()

    strategy = build_strategy(cfg, weekly_donchian_period, donchian_period_2)
    signals = strategy.generate_signals_for_multiple_stocks(
        stock_data_dict=stock_data,
        start_date=start_date,
        end_date=end_date,
    )

    def _parse_signals(s: str):
        items = [x.strip() for x in s.split(",") if x.strip()]
        return items if items else None

    engine = BacktestEngine(
        initial_capital=Decimal("1000000"),
        stop_loss_pct=Decimal(str(cfg.stop_loss_pct)),
        take_profit_pct=Decimal(str(cfg.take_profit_pct)),
        trailing_stop_pct=Decimal(str(cfg.trailing_stop_pct)),
        max_holding_days=cfg.max_holding_days,
        position_sizing=Decimal(str(cfg.position_sizing)),
        atr_stop_multiplier=cfg.atr_stop_multiplier,
        min_holding_days=cfg.min_holding_days,
        market_regime_strong_rsi=cfg.market_regime_strong_rsi,
        strong_regime_signals=_parse_signals(cfg.strong_regime_signals),
        neutral_regime_signals=_parse_signals(cfg.neutral_regime_signals),
        strong_trend_signals=_parse_signals(cfg.strong_trend_signals),
        strong_trend_multiplier=cfg.strong_trend_multiplier,
    )

    # trend exit config
    trend_names = [s.strip() for s in cfg.trend_signal_names.split(",") if s.strip()]
    if trend_names:
        if cfg.trend_use_trailing_stop:
            eff_trailing = Decimal(str(cfg.trend_trailing_stop_pct))
            eff_exit_signals = None
        else:
            eff_trailing = Decimal("0")
            eff_exit_signals = [
                s.strip() for s in cfg.trend_exit_on_signals.split(",") if s.strip()
            ] or None
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

    for symbol, data in stock_data.items():
        engine.add_price_data(symbol, data)

    if sector_whitelist:
        engine.set_sector_whitelist(sector_whitelist)

    result = engine.run_backtest(
        signals,
        start_date,
        end_date,
        benchmark_data=benchmark_data,
        market_regime_rsi_threshold=cfg.market_regime_rsi_threshold,
        market_regime_check_ma5=cfg.market_regime_check_ma5,
    )

    score = float(result.total_return_pct) * float(result.win_rate)
    print(
        f"[{label:35s}]  "
        f"return={result.total_return_pct:6.2f}%  "
        f"win={result.win_rate:5.1f}%  "
        f"trades={result.total_trades:3d}  "
        f"sharpe={result.sharpe_ratio:5.2f}  "
        f"score={score:8.2f}",
        flush=True,
    )
    return label, result, score


async def main():
    cfg = settings.backtest
    start_date = cfg.start_date or date(2024, 9, 1)
    end_date = cfg.end_date or date.today()
    needed_start = start_date - timedelta(days=100)

    # ── Load data once ──────────────────────────────────────────────────
    data_source = YFinanceDataSource()
    stocks_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "../data/stocks")
    )
    print(f"Loading data from {stocks_dir} …", flush=True)
    stock_data = data_source.load_from_stocks_dir(
        stocks_dir=stocks_dir,
        start_date=needed_start,
        end_date=end_date,
    )
    print(f"Loaded {len(stock_data)} symbols", flush=True)

    # Apply industry exclusion
    excluded = cfg.load_excluded_symbols(
        project_root=Path(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    )
    if excluded:
        stock_data = {s: d for s, d in stock_data.items() if s not in excluded}
        print(f"After exclusion: {len(stock_data)} symbols", flush=True)

    # Benchmark
    yf_client = YFinanceClient()
    benchmark_data = data_source.get_market_index_data(start_date, end_date)

    # Sector whitelist (shared)
    sector_whitelist = None
    if cfg.enable_sector_trend_filter:
        base_strategy = build_strategy(cfg, cfg.weekly_donchian_period)
        sector_analyzer = SectorTrendAnalyzer()
        sector_whitelist = base_strategy.build_sector_whitelist(
            stock_data_dict=stock_data,
            sector_analyzer=sector_analyzer,
            threshold=cfg.sector_trend_threshold,
            start_date=start_date,
            end_date=end_date,
            use_momentum=cfg.sector_use_momentum,
            momentum_lookback_days=cfg.sector_momentum_lookback_days,
            top_pct=cfg.sector_top_pct,
        )

    # ── Grid configs ────────────────────────────────────────────────────
    configs = [
        # (label, weekly_donchian_period, donchian_period_2)
        ("weekly_d5  (weekly_only)",  5,  0),
        ("weekly_d8  (weekly_only)",  8,  0),
        ("weekly_d10 (weekly_only)", 10,  0),   # current default
        ("weekly_d13 (weekly_only)", 13,  0),
        ("weekly_d15 (weekly_only)", 15,  0),
        ("weekly_d10 + dual_d20",    10, 20),   # Direction B
    ]

    print(f"\n{'='*80}")
    print(f"Grid search: weekly_donchian_period × donchian_period_2")
    print(f"Metric: total_return% × win_rate% (higher = better)")
    print(f"{'='*80}\n")

    results = []
    for label, wdp, dp2 in configs:
        print(f"→ Running {label} …", flush=True)
        entry = await run_one(cfg, stock_data, benchmark_data, sector_whitelist,
                              label, wdp, dp2)
        results.append(entry)

    # ── Summary ─────────────────────────────────────────────────────────
    results.sort(key=lambda x: x[2], reverse=True)
    print(f"\n{'='*80}")
    print("SUMMARY (sorted by score = return% × win_rate%)")
    print(f"{'='*80}")
    for rank, (label, res, score) in enumerate(results, 1):
        print(
            f"#{rank}  [{label:35s}]  "
            f"return={res.total_return_pct:6.2f}%  "
            f"win={res.win_rate:5.1f}%  "
            f"score={score:8.2f}"
        )

    best_label, best_res, best_score = results[0]
    print(f"\n✓ BEST: {best_label}  (score={best_score:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
