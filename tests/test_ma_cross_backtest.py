"""
Unit tests for src/application/services/ma_cross_backtest.py

重點：向量化回測的選股結果必須與生產端（MACrossScanner / detect_ma_cross_flat60 /
compute_sub_industry_metrics / select_hot_sub_industries）逐日結果一致。
"""
import os
import sys
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.application.services.ma_cross_backtest import (
    Panel,
    build_panel,
    first_entries,
    forward_returns,
    hot_sub_industry_mask,
    ma_cross_signals,
    run_topn_backtest,
    stock_hot_mask,
    sub_industry_daily_metrics,
    summarize,
)
from src.application.services.ma_cross_scanner import MACrossScanner
from src.domain.services.ma_cross_screener import detect_ma_cross_flat60
from src.domain.services.sub_industry_index import (
    build_daily_snapshot,
    compute_sub_industry_metrics,
    select_hot_sub_industries,
)


def random_frames(n_stocks=12, n_days=160, seed=7):
    """隨機漫步價格；部分股票有停牌日，製造缺值情境"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    frames = {}
    for i in range(n_stocks):
        # 前段下跌、後段上漲的趨勢 + 雜訊，讓穿越訊號有機會出現
        drift = np.concatenate([np.full(n_days // 2, -0.003), np.full(n_days - n_days // 2, 0.004)])
        rets = drift + rng.normal(0, 0.02, n_days) * (1 + i / n_stocks)
        close = 100 * np.exp(np.cumsum(rets))
        df = pd.DataFrame({
            "date": dates,
            "open": close * (1 + rng.normal(0, 0.005, n_days)),
            "close": close,
            "volume": rng.integers(1_000, 100_000, n_days).astype(float),
        })
        if i % 4 == 0:  # 停牌幾天
            df = df.drop(index=[30, 31, 90]).reset_index(drop=True)
        frames[f"{1000 + i}"] = {"market": "TW", "df": df}
    return frames


SUBS = {
    "S1": {"name": "一", "chain": "鏈", "codes": ["1000", "1001", "1002", "1003"]},
    "S2": {"name": "二", "chain": "鏈", "codes": ["1004", "1005", "1006"]},
    "S3": {"name": "三", "chain": "鏈", "codes": ["1007", "1008"]},
    "S4": {"name": "四", "chain": "鏈", "codes": ["1009", "1010", "1011", "1000"]},
}


@pytest.fixture(scope="module")
def frames():
    return random_frames()


@pytest.fixture(scope="module")
def panel(frames):
    return build_panel(frames)


class TestConsistencyWithProduction:
    def test_ma_signals_match_detect(self, frames, panel):
        sig = ma_cross_signals(panel.close, lookback_days=5, slope_days=5, flat_tolerance=0.01)
        assert sig.values.any(), "測試資料應至少產生一個訊號"
        for code, item in frames.items():
            df = item["df"]
            for i in range(len(df)):
                d = df["date"].iloc[i]
                hit = detect_ma_cross_flat60(df.iloc[: i + 1], 5, 5, 0.01)
                assert bool(sig.at[d, code]) == (hit is not None), (code, d)

    @pytest.mark.parametrize("weighting", ["equal", "value"])
    def test_sub_industry_metrics_match(self, frames, panel, weighting):
        met = sub_industry_daily_metrics(panel, SUBS, weighting)
        dfs = {c: it["df"] for c, it in frames.items()}
        for d in panel.close.index[1::17]:
            snap = build_daily_snapshot(dfs, d.date())
            prod = compute_sub_industry_metrics(snap, SUBS, weighting).set_index("sub_id")
            for sub_id in prod.index:
                assert met["change_pct"].at[d, sub_id] == pytest.approx(prod.at[sub_id, "change_pct"])
                assert met["trade_value"].at[d, sub_id] == pytest.approx(prod.at[sub_id, "trade_value"])

    @pytest.mark.parametrize("top_n", [0, 1, 2])
    def test_hot_mask_matches_select(self, frames, panel, top_n):
        met = sub_industry_daily_metrics(panel, SUBS)
        min_value = float(met["trade_value"].stack().median())
        hot = hot_sub_industry_mask(met, min_value, top_n)
        dfs = {c: it["df"] for c, it in frames.items()}
        for d in panel.close.index[1::13]:
            snap = build_daily_snapshot(dfs, d.date())
            prod = select_hot_sub_industries(compute_sub_industry_metrics(snap, SUBS), min_value, top_n)
            assert set(hot.columns[hot.loc[d].to_numpy()]) == set(prod["sub_id"]), d

    def test_final_picks_match_scanner(self, frames, panel):
        """最後一天：回測選股 == MACrossScanner 選股"""
        cfg = SimpleNamespace(
            lookback_days=5, ma60_slope_days=5, ma60_flat_tolerance=0.01,
            enable_sub_industry_filter=True, sub_industry_min_trade_value=0.0,
            sub_industry_top_n=2, sub_industry_weighting="equal",
            sub_industry_cache_ttl_hours=1, output_dir="unused",
        )
        scan = MACrossScanner(cfg=cfg).scan(price_frames=frames, sub_industries=SUBS, names={}, industries={})

        base = ma_cross_signals(panel.close, 5, 5, 0.01)
        hot = hot_sub_industry_mask(sub_industry_daily_metrics(panel, SUBS), 0.0, 2)
        picks = base & stock_hot_mask(hot, SUBS, base.columns)
        last = picks.iloc[-1]
        assert set(last[last].index) == set(scan.stocks["code"])
        assert set(base.iloc[-1][base.iloc[-1]].index) == set(scan.candidates["code"])


class TestHelpers:
    def test_build_panel_drops_sparse_days(self):
        d = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-10"])
        frames = {
            "A": {"market": "TW", "df": pd.DataFrame({"date": d[:2], "open": 1.0, "close": [1.0, 2.0], "volume": 1.0})},
            "B": {"market": "TW", "df": pd.DataFrame({"date": d[:2], "open": 1.0, "close": [1.0, 2.0], "volume": 1.0})},
            # 只有 1 檔在 01-10 有資料（髒資料）→ 該日剔除
            "C": {"market": "TW", "df": pd.DataFrame({"date": d, "open": 1.0, "close": [1.0, 2.0, 3.0], "volume": 1.0})},
        }
        panel = build_panel(frames)
        assert list(panel.close.index) == list(d[:2])

    def test_forward_returns_entry_next_open(self):
        idx = pd.bdate_range("2026-01-01", periods=4)
        panel = Panel(
            open=pd.DataFrame({"A": [10.0, 20.0, 30.0, 40.0]}, index=idx),
            close=pd.DataFrame({"A": [11.0, 22.0, 33.0, 44.0]}, index=idx),
            volume=pd.DataFrame({"A": [1.0] * 4}, index=idx),
        )
        fwd = forward_returns(panel, [1, 2])
        assert fwd[1].iloc[0, 0] == pytest.approx((22 / 20 - 1) * 100)   # t+1 開盤 → t+1 收盤
        assert fwd[2].iloc[0, 0] == pytest.approx((33 / 20 - 1) * 100)   # t+1 開盤 → t+2 收盤
        assert np.isnan(fwd[2].iloc[-1, 0])

    def test_first_entries(self):
        sig = pd.DataFrame({"A": [True, True, False, True]})
        assert list(first_entries(sig)["A"]) == [True, False, False, True]

    def test_summarize(self):
        idx = pd.bdate_range("2026-01-01", periods=2)
        sig = pd.DataFrame({"A": [True, False], "B": [True, True]}, index=idx)
        ret = pd.DataFrame({"A": [2.0, 9.0], "B": [-1.0, 4.0]}, index=idx)
        mkt = pd.Series([0.5, 1.0], index=idx)
        row = summarize(sig, {5: ret}, {5: mkt}, "x")
        assert row["signals"] == 3
        assert row["ret5d"] == pytest.approx((2 - 1 + 4) / 3)
        assert row["win5d"] == pytest.approx(200 / 3)
        assert row["excess5d"] == pytest.approx(((2 - .5) + (-1 - .5) + (4 - 1)) / 3)

    def test_run_topn_backtest_shape(self, panel):
        res = run_topn_backtest(panel, SUBS, top_ns=(1, 2), horizons=(1, 5),
                                flat_tolerance=0.01, min_trade_value=0.0, new_entries_only=False)
        assert list(res["variant"]) == ["no_filter", "top1", "top2"]
        # 計入每日訊號時，過濾越嚴格訊號數不會變多
        # （只算新進榜時不一定成立：過濾會讓同一檔股票反覆進出榜）
        assert res["signals"].iloc[1] <= res["signals"].iloc[2] <= res["signals"].iloc[0]
