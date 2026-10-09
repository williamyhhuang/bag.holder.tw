"""
Unit tests for download 缺口偵測與補抓（src/interfaces/cli/download_main.py）
"""
import os
import sys
from collections import Counter
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces.cli import download_main as dm


def _write(path, dates):
    lines = ["date,open,high,low,close,volume,symbol"]
    lines += [f"{d},1,1,1,1,100,X.TW" for d in dates]
    path.write_text("\n".join(lines) + "\n")


class TestTailDates:
    def test_reads_tail_and_skips_truncated_line(self, tmp_path):
        p = tmp_path / "1101_TW.csv"
        _write(p, [f"2026-07-{d:02d}" for d in range(1, 31)])
        dates = dm._tail_dates(str(p), tail_bytes=120)
        assert dates and dates[-1] == date(2026, 7, 30)
        assert len(dates) < 30

    def test_timezone_suffix_and_missing_file(self, tmp_path):
        p = tmp_path / "1101_TW.csv"
        _write(p, ["2026-10-08 00:00:00+08:00"])
        assert dm._tail_dates(str(p), 4096) == [date(2026, 10, 8)]
        assert dm._tail_dates(str(tmp_path / "nope.csv"), 4096) == []


class TestCoverageAndMissing:
    def test_coverage_ignores_test_files(self, tmp_path):
        _write(tmp_path / "1101_TW.csv", ["2026-07-01", "2026-07-02"])
        _write(tmp_path / "1102_TW.csv", ["2026-07-02"])
        _write(tmp_path / "TEST_TW.csv", ["2026-07-03"])
        cov, n = dm.local_date_coverage(str(tmp_path), 4096)
        assert n == 2
        assert cov == Counter({date(2026, 7, 1): 1, date(2026, 7, 2): 2})

    def test_middle_gap_detected(self):
        # 7/02 之後直接接上 10/08：資料最後日期是今天，但中間缺了交易日
        cov = Counter({date(2026, 7, 2): 100, date(2026, 10, 8): 100})
        cal = [date(2026, 7, 2), date(2026, 7, 3), date(2026, 10, 7), date(2026, 10, 8)]
        assert dm.find_missing_trading_days(cov, 100, cal, date(2026, 10, 8)) == [
            date(2026, 7, 3), date(2026, 10, 7)]

    def test_holidays_not_in_calendar_are_not_gaps(self):
        cov = Counter({date(2026, 10, 5): 100, date(2026, 10, 7): 100})
        cal = [date(2026, 10, 5), date(2026, 10, 7)]   # 10/06 為假日，不在交易日曆中
        assert dm.find_missing_trading_days(cov, 100, cal, date(2026, 10, 8)) == []

    def test_partial_coverage_threshold(self):
        cov = Counter({date(2026, 10, 7): 40})
        cal = [date(2026, 10, 7)]
        assert dm.find_missing_trading_days(cov, 100, cal, date(2026, 10, 8)) == [date(2026, 10, 7)]
        assert dm.find_missing_trading_days(cov, 100, cal, date(2026, 10, 8), min_ratio=0.3) == []

    def test_today_and_empty_dir_ignored(self):
        assert dm.find_missing_trading_days(Counter(), 100, [date(2026, 10, 8)], date(2026, 10, 8)) == []
        assert dm.find_missing_trading_days(Counter(), 0, [date(2026, 10, 7)], date(2026, 10, 8)) == []


class TestNonTradingCache:
    def test_roundtrip_and_bad_file(self, tmp_path):
        p = tmp_path / "nt.json"
        assert dm.load_non_trading_days(p) == set()
        dm.save_non_trading_days({date(2026, 10, 6)}, p)
        assert dm.load_non_trading_days(p) == {date(2026, 10, 6)}
        p.write_text("not json")
        assert dm.load_non_trading_days(p) == set()


class TestLocalSymbols:
    def test_groups_by_market(self, tmp_path):
        for name in ["2330_TW.csv", "8042_TWO.csv", "TEST_TW.csv", "weird.csv"]:
            (tmp_path / name).write_text("date\n")
        assert dm.local_symbols(str(tmp_path)) == {"TW": ["2330"], "TWO": ["8042"]}


class FakeExchange:
    """2026-10-06 為假日（兩市場皆無資料），10-07 有資料"""

    def __init__(self, fail_days=()):
        self.calls = []
        self.fail_days = set(fail_days)

    def fetch_day(self, day):
        import pandas as pd
        self.calls.append(day)
        if day in self.fail_days:
            raise RuntimeError("blocked")
        if day == date(2026, 10, 6):
            empty = pd.DataFrame(columns=["code", "open", "high", "low", "close", "volume"])
            return {"TW": empty, "TWO": empty}
        tw = pd.DataFrame([{"code": "2330", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
                           {"code": "9999", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}])
        two = pd.DataFrame([{"code": "8042", "open": 3.0, "high": 4.0, "low": 2.5, "close": 3.5, "volume": 20.0}])
        return {"TW": tw, "TWO": two}


class TestBackfillGap:
    def _setup(self, tmp_path):
        stocks = tmp_path / "stocks"
        stocks.mkdir(exist_ok=True)
        _write(stocks / "2330_TW.csv", ["2026-10-02", "2026-10-05", "2026-10-08"])
        _write(stocks / "8042_TWO.csv", ["2026-10-02", "2026-10-05", "2026-10-08"])
        return stocks

    def _run(self, tmp_path, fake):
        stocks = self._setup(tmp_path)
        cache = tmp_path / "cache" / "nt.json"
        settings_stub = SimpleNamespace(
            download=SimpleNamespace(gap_check_days=7, gap_check_tail_bytes=4096),
            data=SimpleNamespace(stocks_path=str(stocks)),
        )
        saved = []
        with patch.object(dm, "settings", settings_stub), \
                patch.object(dm, "NON_TRADING_CACHE", cache), \
                patch.object(dm, "datetime", wraps=datetime) as dt, \
                patch.object(dm, "YFinanceClient") as yf:
            dt.now.return_value = datetime(2026, 10, 8, 14, 30)
            yf.return_value.save_stock_data.side_effect = lambda sym, df: saved.append((sym, df)) or True
            count = dm.DataDownloaderCLI().backfill_gap(client=fake)
        return count, saved, cache

    def test_fills_missing_days_and_caches_holidays(self, tmp_path):
        fake = FakeExchange()
        count, saved, cache = self._run(tmp_path, fake)
        # 10/01（窗口起點）、10/06、10/07 為疑似缺口；10/06 確認為非交易日
        assert date(2026, 10, 6) in fake.calls and date(2026, 10, 7) in fake.calls
        assert count == 2
        by_sym = dict(saved)
        assert set(by_sym) == {"2330.TW", "8042.TWO"}       # 9999 本地沒有檔案 → 不新增
        df = by_sym["2330.TW"]
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "symbol"]
        assert date(2026, 10, 7) in set(df["date"].dt.date)
        assert dm.load_non_trading_days(cache) == {date(2026, 10, 6)}

    def test_cached_holiday_not_requested_again(self, tmp_path):
        first = FakeExchange()
        self._run(tmp_path, first)
        second = FakeExchange()
        cache = tmp_path / "cache" / "nt.json"
        assert dm.load_non_trading_days(cache)
        # 第二次執行：本地資料未變（save 被 mock），但 10/06 已在快取中，不再查詢
        self._run(tmp_path, second)
        assert date(2026, 10, 6) not in second.calls

    def test_no_gap_no_requests(self, tmp_path):
        stocks = tmp_path / "stocks"
        stocks.mkdir()
        _write(stocks / "2330_TW.csv", ["2026-10-07", "2026-10-08"])
        fake = FakeExchange()
        settings_stub = SimpleNamespace(
            download=SimpleNamespace(gap_check_days=1, gap_check_tail_bytes=4096),
            data=SimpleNamespace(stocks_path=str(stocks)),
        )
        with patch.object(dm, "settings", settings_stub), \
                patch.object(dm, "NON_TRADING_CACHE", tmp_path / "nt.json"), \
                patch.object(dm, "datetime", wraps=datetime) as dt:
            dt.now.return_value = datetime(2026, 10, 8, 14, 30)
            assert dm.DataDownloaderCLI().backfill_gap(client=fake) == 0
        assert fake.calls == []

    def test_fetch_error_skips_day(self, tmp_path):
        fake = FakeExchange(fail_days={date(2026, 10, 7)})
        count, saved, cache = self._run(tmp_path, fake)
        assert date(2026, 10, 7) not in dm.load_non_trading_days(cache)  # 失敗不可誤記為假日

    def test_run_download_skips_snapshot_on_holiday(self):
        cli = dm.DataDownloaderCLI()
        client = MagicMock()
        with patch.object(cli, "_make_client", return_value=client), \
                patch.object(cli, "backfill_gap", return_value=0) as backfill, \
                patch.object(cli, "is_market_open_today", return_value=False):
            args = SimpleNamespace(start_date=None, end_date=None, source="fubon", markets=None, limit=None)
            assert cli.run_download(args) == 0
        backfill.assert_called_once()          # 缺口補抓照常執行
        client.download_recent_data.assert_not_called()

    def test_is_market_open_today(self):
        cli = dm.DataDownloaderCLI()
        with patch("src.utils.trading_calendar.is_trading_day", return_value=False):
            assert cli.is_market_open_today() is False
        with patch("src.utils.trading_calendar.is_trading_day", return_value=True):
            assert cli.is_market_open_today() is True

    def test_run_download_backfills_before_recent(self):
        cli = dm.DataDownloaderCLI()
        order = []
        client = MagicMock()
        client.download_recent_data.side_effect = lambda: order.append("recent") or 10
        with patch.object(cli, "_make_client", return_value=client), \
                patch.object(cli, "is_market_open_today", return_value=True), \
                patch.object(cli, "backfill_gap", side_effect=lambda: order.append("backfill") or 0):
            args = SimpleNamespace(start_date=None, end_date=None, source="fubon", markets=None, limit=None)
            assert cli.run_download(args) == 10
        assert order == ["backfill", "recent"]
