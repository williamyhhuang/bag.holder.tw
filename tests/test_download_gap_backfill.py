"""
Unit tests for download 缺口偵測與補抓（src/interfaces/cli/download_main.py）
"""
import os
import sys
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces.cli import download_main as dm


def _write(path, dates):
    lines = ["date,open,high,low,close,volume,symbol"]
    lines += [f"{d},1,1,1,1,100,X.TW" for d in dates]
    path.write_text("\n".join(lines) + "\n")


class TestLatestLocalDate:
    def test_mode_of_last_dates_ignores_test_files(self, tmp_path):
        _write(tmp_path / "1101_TW.csv", ["2026-07-01", "2026-07-02"])
        _write(tmp_path / "1102_TW.csv", ["2026-07-02"])
        _write(tmp_path / "1103_TW.csv", ["2026-06-30"])            # 停牌股
        _write(tmp_path / "TEST_TW.csv", ["2026-10-11 00:00:00+08:00"] * 5)
        assert dm.latest_local_date(str(tmp_path)) == date(2026, 7, 2)

    def test_timezone_suffix_and_empty_dir(self, tmp_path):
        assert dm.latest_local_date(str(tmp_path)) is None
        _write(tmp_path / "1101_TW.csv", ["2026-10-08 00:00:00+08:00"])
        assert dm.latest_local_date(str(tmp_path)) == date(2026, 10, 8)

    def test_unreadable_file_is_skipped(self, tmp_path):
        (tmp_path / "bad_TW.csv").write_text("date\nnot-a-date\n")
        _write(tmp_path / "1101_TW.csv", ["2026-10-07"])
        assert dm.latest_local_date(str(tmp_path)) == date(2026, 10, 7)


class TestFindBackfillStart:
    def test_no_gap_when_latest_is_previous_weekday(self):
        assert dm.find_backfill_start(date(2026, 10, 7), date(2026, 10, 8)) is None

    def test_no_gap_over_weekend(self):
        # 週五 → 週一：中間只有週末
        assert dm.find_backfill_start(date(2026, 10, 9), date(2026, 10, 12)) is None

    def test_no_gap_when_already_today(self):
        assert dm.find_backfill_start(date(2026, 10, 8), date(2026, 10, 8)) is None

    def test_gap_detected(self):
        assert dm.find_backfill_start(date(2026, 7, 2), date(2026, 10, 8)) == date(2026, 7, 3)

    def test_none_when_no_local_data(self):
        assert dm.find_backfill_start(None, date(2026, 10, 8)) is None


class TestBackfillGap:
    def _cli(self):
        return dm.DataDownloaderCLI()

    def test_backfills_with_yfinance(self):
        with patch.object(dm, "latest_local_date", return_value=date(2026, 7, 2)), \
                patch.object(dm, "datetime", wraps=datetime) as dt, \
                patch.object(dm, "YFinanceClient") as yf:
            dt.now.return_value = datetime(2026, 10, 8, 14, 30)
            yf.return_value.download_all_stocks.return_value = 1999
            assert self._cli().backfill_gap() == 1999
            start, end = yf.return_value.download_all_stocks.call_args.args
            assert start == datetime(2026, 7, 3)
            assert end == datetime(2026, 10, 8)   # yfinance end 不含當日

    def test_skip_when_no_gap(self):
        with patch.object(dm, "latest_local_date", return_value=date(2026, 10, 7)), \
                patch.object(dm, "datetime", wraps=datetime) as dt, \
                patch.object(dm, "YFinanceClient") as yf:
            dt.now.return_value = datetime(2026, 10, 8, 14, 30)
            assert self._cli().backfill_gap() == 0
            yf.assert_not_called()

    def test_failure_does_not_raise(self):
        with patch.object(dm, "latest_local_date", return_value=date(2026, 7, 2)), \
                patch.object(dm, "YFinanceClient") as yf:
            yf.return_value.download_all_stocks.side_effect = RuntimeError("boom")
            assert self._cli().backfill_gap() == 0

    def test_run_download_backfills_before_recent(self):
        cli = self._cli()
        order = []
        client = MagicMock()
        client.download_recent_data.side_effect = lambda: order.append("recent") or 10
        with patch.object(cli, "_make_client", return_value=client), \
                patch.object(cli, "backfill_gap", side_effect=lambda: order.append("backfill") or 0):
            args = SimpleNamespace(start_date=None, end_date=None, source="fubon", markets=None, limit=None)
            assert cli.run_download(args) == 10
        assert order == ["backfill", "recent"]
