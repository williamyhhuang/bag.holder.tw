"""
Unit tests for T86 historical data backtest integration:
- InstitutionalHistoryLoader.load_cached_range / build_consecutive_series
- TechnicalStrategy.build_factor_whitelist with inst_consecutive_by_date
- scripts/backfill_t86.backfill
- scripts/backtest_t86_factor.build_inst_filter_whitelist
"""
import json
import sys
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.market_data.institutional_history import (
    InstitutionalHistoryLoader,
)
from src.application.services.backtest_strategy import TechnicalStrategy
from src.domain.models import StockData
from scripts.backtest_t86_factor import build_inst_filter_whitelist


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _write_cache(history_dir: Path, d: date, data: dict):
    path = history_dir / f"{d.strftime('%Y%m%d')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": d.isoformat(), "data": data}, f)


def _day(sym_nets: dict) -> dict:
    """{symbol: (foreign_net, trust_net)} → cache data format"""
    return {
        sym: {"foreign_net": f, "trust_net": t, "dealer_net": 0}
        for sym, (f, t) in sym_nets.items()
    }


# ─────────────────────────────────────────────
# load_cached_range
# ─────────────────────────────────────────────

class TestLoadCachedRange:
    def test_loads_only_cached_days_in_range(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        d1, d2, d3 = date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)
        _write_cache(tmp_path, d1, _day({"2330": (100, 50)}))
        _write_cache(tmp_path, d3, _day({"2330": (200, -10)}))

        results = loader.load_cached_range(d1, d3)
        assert [r["date"] for r in results] == [d1, d3]
        assert results[0]["data"]["2330"]["foreign_net"] == 100

    def test_no_network_call_for_missing_days(self, tmp_path, monkeypatch):
        import src.infrastructure.market_data.institutional_history as mod
        called = []
        monkeypatch.setattr(
            mod, "_fetch_t86_for_date", lambda d: called.append(d) or {}
        )
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        loader.load_cached_range(date(2025, 3, 3), date(2025, 3, 7))
        assert called == []

    def test_empty_range(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        assert loader.load_cached_range(date(2025, 3, 3), date(2025, 3, 5)) == []


# ─────────────────────────────────────────────
# build_consecutive_series
# ─────────────────────────────────────────────

class TestBuildConsecutiveSeries:
    def test_streak_accumulates(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        days = [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)]
        for d in days:
            _write_cache(tmp_path, d, _day({"2330": (100, 50)}))

        series = loader.build_consecutive_series(days[0], days[-1], warmup_days=0)
        assert series[days[0]]["2330"]["foreign_consecutive"] == 1
        assert series[days[1]]["2330"]["foreign_consecutive"] == 2
        assert series[days[2]]["2330"]["foreign_consecutive"] == 3
        assert series[days[2]]["2330"]["trust_consecutive"] == 3

    def test_streak_resets_on_sell(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        d1, d2, d3 = date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)
        _write_cache(tmp_path, d1, _day({"2330": (100, 50)}))
        _write_cache(tmp_path, d2, _day({"2330": (-100, 50)}))  # 外資轉賣
        _write_cache(tmp_path, d3, _day({"2330": (100, 50)}))

        series = loader.build_consecutive_series(d1, d3, warmup_days=0)
        assert series[d2]["2330"]["foreign_consecutive"] == 0
        assert series[d3]["2330"]["foreign_consecutive"] == 1
        assert series[d3]["2330"]["trust_consecutive"] == 3

    def test_warmup_makes_first_day_streak_correct(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        warm = date(2025, 3, 3)
        first = date(2025, 3, 4)
        _write_cache(tmp_path, warm, _day({"2330": (100, 0)}))
        _write_cache(tmp_path, first, _day({"2330": (100, 0)}))

        series = loader.build_consecutive_series(first, first, warmup_days=5)
        # 暖機日不在輸出，但 streak 已累積
        assert warm not in series
        assert series[first]["2330"]["foreign_consecutive"] == 2

    def test_missing_symbol_resets_streak(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        d1, d2, d3 = date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)
        _write_cache(tmp_path, d1, _day({"2330": (100, 0)}))
        _write_cache(tmp_path, d2, _day({"2317": (100, 0)}))  # 2330 缺席
        _write_cache(tmp_path, d3, _day({"2330": (100, 0)}))

        series = loader.build_consecutive_series(d1, d3, warmup_days=0)
        assert series[d3]["2330"]["foreign_consecutive"] == 1

    def test_empty_cache_returns_empty(self, tmp_path):
        loader = InstitutionalHistoryLoader(history_dir=tmp_path)
        assert loader.build_consecutive_series(
            date(2025, 3, 3), date(2025, 3, 5)
        ) == {}


# ─────────────────────────────────────────────
# build_factor_whitelist with real T86
# ─────────────────────────────────────────────

def _make_stock_data(symbol: str, base_price: float, n_days: int = 25,
                     end: date = date(2025, 3, 5), daily_gain: float = 0.0,
                     last_day_vol_mult: float = 1.0):
    """產生連續 n_days 的 StockData。

    預設 n_days=25：量能比率可計算（需 21 日），但 RPS 3m/6m 因資料不足
    跳過 → 兩支股票的 RPS 均取預設 0.5，避免百分位排名平手時順序不確定。
    """
    records = []
    price = base_price
    for i in range(n_days):
        d = end - timedelta(days=n_days - 1 - i)
        price = price * (1 + daily_gain)
        p = Decimal(str(round(price, 2)))
        vol = 1_000_000
        if i == n_days - 1:
            vol = int(vol * last_day_vol_mult)
        records.append(StockData(
            symbol=symbol, date=d, open_price=p, high_price=p,
            low_price=p, close_price=p, volume=vol,
        ))
    return records


class TestFactorWhitelistWithT86:
    """
    測試設計（確定性，避免百分位平手的不確定排序）：
      - 25 日資料 → RPS 跳過（雙方 0.5），只剩量能(20%) vs 法人(30%)
      - 2317 帶量能優勢（+0.2）；2330 帶法人連買優勢（+0.3）
      → 有真實 T86 時 2330 勝；無 T86（法人均 0.5）時 2317 勝
    """

    @staticmethod
    def _two_stocks(end: date):
        return {
            "2317": _make_stock_data("2317", 100, end=end, last_day_vol_mult=2.0),
            "2330": _make_stock_data("2330", 100, end=end),
        }

    def test_inst_data_changes_ranking(self):
        """法人連買優勢（權重30%）應蓋過量能優勢（權重20%）"""
        strategy = TechnicalStrategy()
        end = date(2025, 3, 5)
        inst = {
            end: {
                "2330": {"foreign_consecutive": 5, "trust_consecutive": 3},
                "2317": {"foreign_consecutive": 0, "trust_consecutive": 0},
            }
        }
        wl = strategy.build_factor_whitelist(
            stock_data_dict=self._two_stocks(end), top_n=1,
            start_date=end, end_date=end,
            inst_consecutive_by_date=inst,
        )
        assert wl[end] == {"2330"}

    def test_without_inst_data_legacy_behaviour(self):
        """無 T86 資料時法人均 0.5 → 量能優勢者勝出（舊行為）"""
        strategy = TechnicalStrategy()
        end = date(2025, 3, 5)
        wl = strategy.build_factor_whitelist(
            stock_data_dict=self._two_stocks(end), top_n=1,
            start_date=end, end_date=end,
        )
        assert wl[end] == {"2317"}

    def test_inst_uses_latest_available_date_no_lookahead(self):
        """目標日無 T86 資料時，沿用最近一個『較早』的日期（不可用未來資料）"""
        strategy = TechnicalStrategy()
        target = date(2025, 3, 5)
        earlier = date(2025, 3, 4)
        future = date(2025, 3, 6)
        inst = {
            earlier: {
                "2330": {"foreign_consecutive": 5, "trust_consecutive": 5},
                "2317": {"foreign_consecutive": 0, "trust_consecutive": 0},
            },
            future: {  # 未來資料：2317 大買 — 不得影響 target 日排名
                "2317": {"foreign_consecutive": 99, "trust_consecutive": 99},
                "2330": {"foreign_consecutive": 0, "trust_consecutive": 0},
            },
        }
        wl = strategy.build_factor_whitelist(
            stock_data_dict=self._two_stocks(target), top_n=1,
            start_date=target, end_date=target,
            inst_consecutive_by_date=inst,
        )
        assert wl[target] == {"2330"}


# ─────────────────────────────────────────────
# build_inst_filter_whitelist (場景 D)
# ─────────────────────────────────────────────

class TestInstFilterWhitelist:
    def test_streak_threshold(self):
        d = date(2025, 3, 5)
        series = {
            d: {
                "2330": {"foreign_consecutive": 3, "trust_consecutive": 0},
                "2317": {"foreign_consecutive": 1, "trust_consecutive": 1},
                "2454": {"foreign_consecutive": 0, "trust_consecutive": 2},
            }
        }
        wl = build_inst_filter_whitelist(series, {"2330", "2317", "2454"}, 2)
        assert wl[d] == {"2330", "2454"}

    def test_fail_open_for_symbols_without_t86(self):
        d = date(2025, 3, 5)
        series = {d: {"2330": {"foreign_consecutive": 0, "trust_consecutive": 0}}}
        # 8069 為上櫃，無 T86 資料 → fail-open 保留
        wl = build_inst_filter_whitelist(series, {"2330", "8069"}, 2)
        assert "8069" in wl[d]
        assert "2330" not in wl[d]


# ─────────────────────────────────────────────
# backfill_t86
# ─────────────────────────────────────────────

class TestBackfill:
    def test_skips_weekend_and_cached(self, tmp_path, monkeypatch):
        import src.infrastructure.market_data.institutional_history as mod
        import scripts.backfill_t86 as bf

        fetched = []

        def fake_fetch(d):
            fetched.append(d)
            return {"2330": {"foreign_net": 1, "trust_net": 1, "dealer_net": 0}}

        monkeypatch.setattr(mod, "_fetch_t86_for_date", fake_fetch)
        monkeypatch.setattr(
            bf, "InstitutionalHistoryLoader",
            lambda: InstitutionalHistoryLoader(history_dir=tmp_path),
        )
        monkeypatch.setattr("time.sleep", lambda s: None)

        # 2025-03-07(五) 已有快取；03-08/09 是週末；03-10(一) 需抓取
        _write_cache(tmp_path, date(2025, 3, 7), _day({"2330": (1, 1)}))
        stats = bf.backfill(date(2025, 3, 7), date(2025, 3, 10), delay=0)

        assert stats["cached"] == 1
        assert stats["skipped_weekend"] == 2
        assert stats["fetched"] == 1
        assert fetched == [date(2025, 3, 10)]
