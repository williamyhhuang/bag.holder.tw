"""
Unit tests for 均線多頭／空頭排列策略（5MA>=10MA>=20MA / 5MA<=10MA<=20MA）：
  - src/domain/services/ma_cross_screener.detect_ma_alignment
  - src/application/services/ma_cross_scanner.MACrossScanner（align_* 結果、CSV）
  - src/interfaces/cli/ma_cross_main（Telegram 訊息、main 發送）
"""
import os
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.application.services.ma_cross_scanner import (
    ALIGN_COLUMNS,
    RESULT_COLUMNS,
    MACrossScanner,
    MACrossScanResult,
)
from src.domain.services.ma_cross_screener import _alignment_flags, detect_ma_alignment
from src.interfaces.cli import ma_cross_main as cli


def make_df(closes, volume=1000, start="2026-01-01"):
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"date": dates, "close": closes, "volume": volume})


def down_then_up():
    """先跌（空頭排列）再漲，最後某天轉為多頭排列"""
    return list(np.linspace(120, 90, 40)) + list(np.linspace(91, 115, 25))


def up_then_down():
    return list(np.linspace(90, 120, 40)) + list(np.linspace(119, 95, 25))


def formation_len(closes, direction):
    """截到排列剛形成那天（含當天）的長度"""
    s = pd.Series(closes, dtype=float)
    bull, bear, _ = _alignment_flags(s, (5, 10, 20))
    flags = bull if direction == "bull" else bear
    for i in range(21, len(s)):
        if flags.iloc[i] and not flags.iloc[i - 1] and not pd.isna(s.rolling(20).mean().iloc[i - 1]):
            return i + 1
    raise AssertionError("測試資料沒有形成排列")


# ── detect_ma_alignment ─────────────────────────────────────────────────────

class TestDetectMaAlignment:
    def test_bull_formed_today(self):
        closes = down_then_up()
        n = formation_len(closes, "bull")
        df = make_df(closes[:n])
        hit = detect_ma_alignment(df)
        assert hit is not None
        assert hit["direction"] == "bull"
        assert hit["streak_days"] == 1
        assert hit["formed_date"] == df["date"].iloc[-1].date()
        assert hit["ma5"] >= hit["ma10"] >= hit["ma20"]

    def test_bear_formed_today(self):
        closes = up_then_down()
        n = formation_len(closes, "bear")
        hit = detect_ma_alignment(make_df(closes[:n]))
        assert hit is not None
        assert hit["direction"] == "bear"
        assert hit["ma5"] <= hit["ma10"] <= hit["ma20"]

    def test_continuing_alignment_excluded_by_default(self):
        closes = down_then_up()
        n = formation_len(closes, "bull")
        df = make_df(closes[:n + 2])  # 已連續 3 天
        assert detect_ma_alignment(df) is None
        hit = detect_ma_alignment(df, lookback_days=3)
        assert hit is not None and hit["streak_days"] == 3
        assert hit["formed_date"] == df["date"].iloc[n - 1].date()

    def test_lookback_zero_allows_continuing(self):
        closes = down_then_up()
        hit = detect_ma_alignment(make_df(closes), lookback_days=0)
        assert hit is not None and hit["direction"] == "bull"
        assert hit["streak_days"] > 1

    def test_not_aligned_returns_none(self):
        # 5MA=100 < 20MA=102.5 < 10MA=105：既非多頭也非空頭
        df = make_df([100.0] * 20 + [110.0] * 5 + [100.0] * 5)
        assert detect_ma_alignment(df, lookback_days=0) is None

    def test_all_equal_is_no_direction(self):
        assert detect_ma_alignment(make_df([100.0] * 40), lookback_days=0) is None

    def test_equal_counts_as_aligned(self):
        # 5MA == 10MA > 20MA：>= 允許相等
        s = pd.Series([90.0] * 10 + [100.0] * 10, dtype=float)
        bull, bear, ma = _alignment_flags(s, (5, 10, 20))
        assert ma[5].iloc[-1] == ma[10].iloc[-1] > ma[20].iloc[-1]
        assert bull.iloc[-1] and not bear.iloc[-1]

    def test_insufficient_data(self):
        assert detect_ma_alignment(make_df(list(range(1, 21)))) is None

    def test_aligned_since_first_valid_day_is_not_new(self):
        # 從第一天就持續上漲：沒有「未成立的前一天」，不算新形成
        df = make_df(list(np.linspace(50, 80, 21)))
        assert detect_ma_alignment(df, lookback_days=5) is None
        assert detect_ma_alignment(df, lookback_days=0) is not None

    def test_custom_periods(self):
        closes = down_then_up()
        hit = detect_ma_alignment(make_df(closes), periods=(3, 6), lookback_days=0)
        assert hit is not None and "ma3" in hit and "ma6" in hit


# ── MACrossScanner ──────────────────────────────────────────────────────────

def cfg(**over):
    base = dict(
        short_ma_periods=[5, 10], lookback_days=5, ma60_slope_days=5, ma60_flat_tolerance=0.002,
        min_volume_lots=0, enable_sub_industry_filter=True, sub_industry_min_trade_value=1e4,
        sub_industry_top_n=10, sub_industry_weighting="equal",
        sub_industry_cache_ttl_hours=168, output_dir="unused",
        align_enabled=True, align_periods=[5, 10, 20], align_lookback_days=1,
        align_apply_sub_industry_filter=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestScannerAlignment:
    def _frames(self):
        bull = down_then_up()
        bear = up_then_down()
        nb, nr = formation_len(bull, "bull"), formation_len(bear, "bear")
        n = max(nb, nr)
        # 對齊最後一天日期：較短的序列前面補平盤不影響最後 20 天均線
        bull_df = make_df([bull[0]] * (n - nb) + bull[:nb])
        bear_df = make_df([bear[0]] * (n - nr) + bear[:nr])
        flat = make_df([100.0] * n)
        return {
            "1111": {"market": "TW", "df": bull_df},
            "2222": {"market": "TWO", "df": bear_df},
            "3333": {"market": "TW", "df": flat},
        }

    def _scan(self, subs=None, **over):
        scanner = MACrossScanner(cfg=cfg(**over))
        return scanner.scan(
            price_frames=self._frames(),
            sub_industries=subs or {},
            names={"1111.TW": "甲", "2222.TWO": "乙"},
            industries={},
        )

    def test_bull_and_bear_detected(self):
        result = self._scan(enable_sub_industry_filter=False)
        a = result.align_candidates
        assert list(a.columns) == ALIGN_COLUMNS
        assert dict(zip(a["code"], a["direction"])) == {"1111": "bull", "2222": "bear"}
        assert len(result.align_stocks) == 2
        row = a[a["code"] == "1111"].iloc[0]
        assert row["name"] == "甲" and row["market"] == "上市"
        assert row["streak_days"] == 1

    def test_disabled(self):
        result = self._scan(align_enabled=False, enable_sub_industry_filter=False)
        assert result.align_candidates.empty and result.align_stocks.empty

    def test_volume_threshold_applies(self):
        assert self._scan(enable_sub_industry_filter=False, min_volume_lots=2).align_candidates.empty

    def test_sub_industry_filter(self):
        subs = {"HOT": {"name": "熱", "chain": "鏈", "codes": ["1111"]}}
        result = self._scan(subs, sub_industry_top_n=1)
        assert len(result.align_candidates) == 2
        assert list(result.align_stocks["code"]) == ["1111"]
        # 可單獨關閉排列的細產業過濾
        result = self._scan(subs, sub_industry_top_n=1, align_apply_sub_industry_filter=False)
        assert len(result.align_stocks) == 2

    def test_save_writes_align_csv(self, tmp_path):
        scanner = MACrossScanner(cfg=cfg(enable_sub_industry_filter=False))
        result = scanner.scan(price_frames=self._frames(), sub_industries={}, names={}, industries={})
        scanner.save(result, str(tmp_path))
        files = [p.name for p in tmp_path.iterdir()]
        assert any(f.startswith("ma_align_") for f in files)
        saved = pd.read_csv(next(tmp_path.glob("ma_align_*.csv")), dtype={"code": str})
        assert set(saved["code"]) == {"1111", "2222"}


# ── CLI ─────────────────────────────────────────────────────────────────────

def _align_result(bull=2, bear=1):
    rows = []
    for i in range(bull + bear):
        rows.append({
            "formed_date": date(2026, 11, 16), "direction": "bull" if i < bull else "bear", "streak_days": 1,
            "code": f"{9000 + i}", "name": f"股{i}", "market": "上市", "sector": "半導體",
            "sub_industries": "鏈/甲", "hot_sub_industries": "鏈/甲", "main_sub_industry": "鏈/甲",
            "close": 50.0, "change_pct": 1.5, "ma5": 1.0, "ma10": 1.0, "ma20": 1.0, "volume": 1000,
        })
    align = pd.DataFrame(rows, columns=ALIGN_COLUMNS)
    empty = pd.DataFrame(columns=RESULT_COLUMNS)
    hot = pd.DataFrame([{"sub_id": "A", "chain": "鏈", "name": "甲", "members": 1,
                         "trade_value": 1e11, "change_pct": 3.0}])
    return MACrossScanResult(date(2026, 11, 16), empty, empty, pd.DataFrame(), hot, align, align)


class TestAlignmentTelegram:
    def test_sections(self):
        chunks = cli.format_alignment_for_telegram(_align_result(), show_filter=True)
        assert chunks == [
            "<b>📊 均線排列（5/10/20MA）</b>\n2026-11-16（一）・細產業過濾後 <b>3</b> 檔\n\n"
            "<b>🔴 多頭排列</b>（5MA≥10MA≥20MA）2 檔\n\n"
            "🏷 <b>鏈/甲</b>\n<b>9000</b>  股0  50.00  +1.50%\n<b>9001</b>  股1  50.00  +1.50%\n\n"
            "<b>🟢 空頭排列</b>（5MA≤10MA≤20MA）1 檔\n\n"
            "🏷 <b>鏈/甲</b>\n<b>9002</b>  股2  50.00  +1.50%"
        ]

    def test_empty_direction(self):
        text = cli.format_alignment_for_telegram(_align_result(bull=1, bear=0), True)[0]
        assert "🟢 空頭排列</b>（5MA≤10MA≤20MA）0 檔\n無" in text

    def test_empty(self):
        text = cli.format_alignment_for_telegram(_align_result(0, 0), True)[0]
        assert "今日無新形成多頭／空頭排列的股票" in text

    def test_max_stocks_per_direction(self):
        text = cli.format_alignment_for_telegram(_align_result(5, 5), True, max_stocks=2)[0]
        assert text.count("另有 3 檔") == 2

    def test_chunking(self):
        chunks = cli.format_alignment_for_telegram(_align_result(300, 300), True, max_stocks=0)
        assert len(chunks) > 1
        assert all(len(c) <= cli.TELEGRAM_CHUNK_LIMIT for c in chunks)
        assert sum(c.count(" 股") for c in chunks) == 600


class TestAlignmentCliMain:
    def _run(self, align_enabled):
        with patch.object(cli, "MACrossScanner") as scanner_cls, \
                patch.object(cli, "send_telegram", return_value=True) as send, \
                patch.object(cli.settings.ma_cross, "align_enabled", align_enabled):
            scanner_cls.return_value.scan.return_value = _align_result()
            scanner_cls.return_value.save.return_value = "out.csv"
            assert cli.main(["--send-telegram"]) == 0
            return send.call_args.args[0]

    def test_sends_both_strategies(self):
        chunks = self._run(True)
        assert chunks[0].startswith("<b>📈 均線穿越 60MA")
        assert chunks[-1].startswith("<b>📊 均線排列")

    def test_align_disabled(self):
        chunks = self._run(False)
        assert not any("均線排列" in c for c in chunks)
