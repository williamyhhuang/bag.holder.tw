from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.application.services.mtx_60m_ma_alert import (
    completed_candles,
    evaluate_ma_alert,
    format_alert,
    load_candle_state,
    mark_alert_sent,
    save_candle_state,
    was_alert_sent,
)


TW = ZoneInfo("Asia/Taipei")


def _rows(closes):
    start = datetime(2026, 8, 1, 9, tzinfo=TW)
    return [(start + timedelta(hours=i), close) for i, close in enumerate(closes)]


def test_matches_when_all_slopes_positive_and_mas_bullishly_aligned():
    result = evaluate_ma_alert(_rows(range(100, 121)))

    assert result is not None
    assert result.matched is True
    assert result.ma5 >= result.ma10 >= result.ma20
    assert result.ma5_slope > 0
    assert result.ma10_slope > 0
    assert result.ma20_slope > 0


def test_does_not_match_when_short_ma_slope_is_not_positive():
    result = evaluate_ma_alert(_rows([100 + i for i in range(20)] + [100]))

    assert result is not None
    assert result.ma5_slope < 0
    assert result.matched is False


def test_requires_21_completed_bars_for_ma20_slope():
    assert evaluate_ma_alert(_rows(range(20))) is None


def test_excludes_current_unfinished_bar():
    now = datetime(2026, 8, 10, 10, 30, tzinfo=TW)
    candles = [
        {"time": "2026-08-10T09:00:00+08:00", "close": 20000},
        {"time": "2026-08-10T10:00:00+08:00", "close": 20100},
    ]

    assert completed_candles(candles, now=now, session="day") == [
        (datetime(2026, 8, 10, 9, tzinfo=TW), 20000.0)
    ]


def test_accepts_shortened_final_day_bar_after_market_close():
    now = datetime(2026, 8, 10, 13, 31, tzinfo=TW)
    candles = [{"time": "2026-08-10T13:00:00+08:00", "close": 20100}]

    assert len(completed_candles(candles, now=now, session="day")) == 1


def test_formats_telegram_message():
    result = evaluate_ma_alert(_rows(range(100, 121)))

    message = format_alert("MTXQ6", "day", result)

    assert "微台 60K" in message
    assert "MA5 ≥ MA10 ≥ MA20" in message
    assert "日盤" in message


def test_candle_state_round_trip_and_retention(tmp_path):
    path = tmp_path / "state.json"
    rows = _rows(range(250))

    save_candle_state(path, rows, keep=200)
    loaded = completed_candles(
        load_candle_state(path),
        now=datetime(2026, 9, 1, tzinfo=TW),
        session="night",
    )

    assert len(loaded) == 200
    assert loaded[0][1] == 50
    assert loaded[-1][1] == 249


def test_alert_marker_prevents_duplicate_notification(tmp_path):
    path = tmp_path / "state.last-alert"
    bar_time = datetime(2026, 8, 10, 10, 45, tzinfo=TW)

    assert was_alert_sent(path, bar_time) is False
    mark_alert_sent(path, bar_time)
    assert was_alert_sent(path, bar_time) is True
    assert was_alert_sent(path, bar_time + timedelta(hours=1)) is False
