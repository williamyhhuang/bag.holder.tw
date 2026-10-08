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


class TestBackfillGap:
    def _run(self, missing, yf_side_effect=None):
        with patch.object(dm, "reference_trading_calendar", return_value=[]), \
                patch.object(dm, "local_date_coverage", return_value=(Counter(), 1)), \
                patch.object(dm, "find_missing_trading_days", return_value=missing), \
                patch.object(dm, "datetime", wraps=datetime) as dt, \
                patch.object(dm, "YFinanceClient") as yf:
            dt.now.return_value = datetime(2026, 10, 8, 14, 30)
            yf.return_value.download_all_stocks.return_value = 1999
            if yf_side_effect:
                yf.return_value.download_all_stocks.side_effect = yf_side_effect
            return dm.DataDownloaderCLI().backfill_gap(), yf

    def test_backfills_from_earliest_missing_day(self):
        count, yf = self._run([date(2026, 7, 3), date(2026, 10, 7)])
        assert count == 1999
        start, end = yf.return_value.download_all_stocks.call_args.args
        assert start == datetime(2026, 7, 3)
        assert end == datetime(2026, 10, 8)   # yfinance end 不含當日

    def test_skip_when_no_gap(self):
        count, yf = self._run([])
        assert count == 0
        yf.assert_not_called()

    def test_download_failure_does_not_raise(self):
        count, _ = self._run([date(2026, 10, 7)], yf_side_effect=RuntimeError("boom"))
        assert count == 0

    def test_calendar_failure_does_not_raise(self):
        with patch.object(dm, "reference_trading_calendar", side_effect=RuntimeError("net")):
            assert dm.DataDownloaderCLI().backfill_gap() == 0

    def test_run_download_backfills_before_recent(self):
        cli = dm.DataDownloaderCLI()
        order = []
        client = MagicMock()
        client.download_recent_data.side_effect = lambda: order.append("recent") or 10
        with patch.object(cli, "_make_client", return_value=client), \
                patch.object(cli, "backfill_gap", side_effect=lambda: order.append("backfill") or 0):
            args = SimpleNamespace(start_date=None, end_date=None, source="fubon", markets=None, limit=None)
            assert cli.run_download(args) == 10
        assert order == ["backfill", "recent"]
