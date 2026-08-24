from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.application.services.mtx_60m_ma_alert import (
    completed_candles,
    evaluate_ma_alert,
    format_alert,
    load_candle_state,
    mark_alert_sent,
    save_candle_state,
    select_near_month_symbol,
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
    assert result.signal == "long"
    assert result.ma5 >= result.ma10 >= result.ma20
    assert result.ma5_slope > 0
    assert result.ma10_slope > 0
    assert result.ma20_slope > 0


def test_matches_when_ma5_is_above_ma10_but_below_ma20():
    closes = [
        112, 100, 117, 95, 86, 84, 120, 107, 89, 119, 102,
        100, 106, 80, 87, 84, 93, 98, 82, 86, 118,
    ]

    result = evaluate_ma_alert(_rows(closes))

    assert result is not None
    assert result.ma5 >= result.ma10
    assert result.ma5 < result.ma20
    assert result.matched is True


def test_matches_when_ma5_is_above_ma20_but_below_ma10():
    closes = [
        84, 112, 108, 94, 102, 94, 112, 94, 85, 96, 84,
        103, 105, 105, 119, 88, 113, 113, 83, 90, 120,
    ]

    result = evaluate_ma_alert(_rows(closes))

    assert result is not None
    assert result.ma5 < result.ma10
    assert result.ma5 >= result.ma20
    assert result.matched is True


def test_does_not_match_when_short_ma_slope_is_not_positive():
    result = evaluate_ma_alert(_rows([100 + i for i in range(20)] + [100]))

    assert result is not None
    assert result.ma5_slope < 0
    assert result.matched is False
    assert result.signal is None


def test_matches_short_when_all_slopes_negative_and_mas_bearishly_aligned():
    result = evaluate_ma_alert(_rows(range(120, 99, -1)))

    assert result is not None
    assert result.matched is True
    assert result.signal == "short"
    assert result.ma5 <= result.ma10 <= result.ma20
    assert result.ma5_slope < 0
    assert result.ma10_slope < 0
    assert result.ma20_slope < 0


def test_matches_short_when_ma5_is_below_ma10_but_above_ma20():
    long_closes = [
        112, 100, 117, 95, 86, 84, 120, 107, 89, 119, 102,
        100, 106, 80, 87, 84, 93, 98, 82, 86, 118,
    ]
    result = evaluate_ma_alert(_rows([200 - close for close in long_closes]))

    assert result is not None
    assert result.ma5 <= result.ma10
    assert result.ma5 > result.ma20
    assert result.signal == "short"


def test_matches_short_when_ma5_is_below_ma20_but_above_ma10():
    long_closes = [
        84, 112, 108, 94, 102, 94, 112, 94, 85, 96, 84,
        103, 105, 105, 119, 88, 113, 113, 83, 90, 120,
    ]
    result = evaluate_ma_alert(_rows([200 - close for close in long_closes]))

    assert result is not None
    assert result.ma5 > result.ma10
    assert result.ma5 <= result.ma20
    assert result.signal == "short"


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
    assert "MA5 ≥ MA10 或 MA5 ≥ MA20" in message
    assert "日盤" in message


def test_formats_short_telegram_message():
    result = evaluate_ma_alert(_rows(range(120, 99, -1)))

    message = format_alert("TMFI6", "night", result)

    assert "📉 微台 60K 空排通知" in message
    assert "MA5 ≤ MA10 或 MA5 ≤ MA20" in message
    assert "三條均線斜率皆為負" in message
    assert "夜盤" in message


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


def test_selects_nearest_active_tmf_contract():
    tickers = [
        {"symbol": "TMFI6", "end_date": "2026-09-16"},
        {"symbol": "TMFH6", "end_date": "2026-08-19"},
        {"symbol": "TXFH6", "end_date": "2026-08-19"},
    ]

    assert select_near_month_symbol(
        tickers, as_of=date(2026, 8, 11)
    ) == "TMFH6"


def test_ignores_expired_contract_and_accepts_compact_settlement_date():
    tickers = [
        {"symbol": "TMFG6", "end_date": "2026-07-15"},
        {"symbol": "TMFH6", "settlement_date": "20260819"},
    ]

    assert select_near_month_symbol(
        tickers, as_of=date(2026, 8, 11)
    ) == "TMFH6"


def test_returns_none_when_api_has_no_dated_active_tmf_contract():
    tickers = [
        {"symbol": "TXFH6", "end_date": "2026-08-19"},
        {"symbol": "TMFH6", "end_date": ""},
    ]

    assert select_near_month_symbol(
        tickers, as_of=date(2026, 8, 11)
    ) is None
