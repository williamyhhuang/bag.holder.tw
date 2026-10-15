from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.application.services.mtx_60m_ma_alert import (
    completed_candles,
    evaluate_ma_alert,
    format_alert,
    load_candle_state,
    load_last_signal,
    mark_alert_sent,
    save_candle_state,
    save_last_signal,
    select_near_month_symbol,
    signal_changed,
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


# ── 5K ──────────────────────────────────────────────────────────────────────

def test_5m_excludes_unfinished_bar():
    now = datetime(2026, 8, 10, 9, 7, tzinfo=TW)
    candles = [
        {"time": "2026-08-10T09:00:00+08:00", "close": 20000},
        {"time": "2026-08-10T09:05:00+08:00", "close": 20010},
    ]

    assert completed_candles(candles, now=now, session="day", interval_minutes=5) == [
        (datetime(2026, 8, 10, 9, tzinfo=TW), 20000.0)
    ]


def test_5m_does_not_apply_60k_shortened_final_bar_rule():
    now = datetime(2026, 8, 10, 13, 32, tzinfo=TW)
    candles = [
        {"time": "2026-08-10T13:25:00+08:00", "close": 20000},
        {"time": "2026-08-10T13:30:00+08:00", "close": 20010},
    ]

    rows = completed_candles(candles, now=now, session="day", interval_minutes=5)

    assert rows == [(datetime(2026, 8, 10, 13, 25, tzinfo=TW), 20000.0)]


def test_formats_5m_telegram_message():
    result = evaluate_ma_alert(_rows(range(100, 121)))

    message = format_alert("TMFV6", "day", result, interval_minutes=5)

    assert "📈 微台 5K 多排通知" in message
    assert "60K" not in message


def test_signal_changed_only_on_new_or_reversed_alignment():
    assert signal_changed(None, "long") is True
    assert signal_changed("none", "long") is True
    assert signal_changed("short", "long") is True
    assert signal_changed("long", "short") is True
    assert signal_changed("long", "long") is False
    assert signal_changed("short", "short") is False
    assert signal_changed("long", None) is False


def test_last_signal_round_trip(tmp_path):
    path = tmp_path / "5m.json.last-signal"

    assert load_last_signal(path) is None
    save_last_signal(path, "long")
    assert load_last_signal(path) == "long"
    save_last_signal(path, None)
    assert load_last_signal(path) == "none"
    assert signal_changed(load_last_signal(path), "long") is True


def _load_runner():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "run_mtx_60m_alert.py"
    spec = importlib.util.spec_from_file_location("run_mtx_60m_alert", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_5m(runner, tmp_path, closes, now, sent):
    import asyncio
    from unittest.mock import patch

    start = now - timedelta(minutes=5 * len(closes))
    candles = [
        {"time": (start + timedelta(minutes=5 * i)).isoformat(), "close": c}
        for i, c in enumerate(closes)
    ]

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_futures_tickers(self, **kwargs):
            return [{"symbol": "TMFV6", "end_date": "2026-12-31"}]

        async def get_futures_candles(self, symbol, timeframe, session):
            assert timeframe == "5"
            return candles

    class FakeNotifier:
        def send_message(self, message, parse_mode=None):
            sent.append(message)
            return True

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch.object(runner, "_build_client", return_value=FakeClient()), \
            patch.object(runner, "TelegramNotifier", FakeNotifier), \
            patch.object(runner, "datetime", FakeDatetime):
        return asyncio.run(runner.run("day", tmp_path / "5m.json", interval=5))


def test_5m_runner_notifies_only_when_alignment_changes(tmp_path):
    runner = _load_runner()
    sent = []
    base = datetime(2026, 8, 10, 11, 0, tzinfo=TW)
    up = list(range(100, 125))

    # 第一次成立多排 → 通知
    assert _run_5m(runner, tmp_path, up, base, sent) == 0
    assert len(sent) == 1 and "微台 5K 多排通知" in sent[0]
    assert "MA5 > MA10 > MA20" in sent[0]

    # 下一根仍是多排 → 不重複通知
    assert _run_5m(runner, tmp_path, up + [125], base + timedelta(minutes=5), sent) == 0
    assert len(sent) == 1

    # 轉為空排 → 通知
    down = list(range(125, 95, -1))
    assert _run_5m(runner, tmp_path, down, base + timedelta(minutes=200), sent) == 0
    assert len(sent) == 2 and "微台 5K 空排通知" in sent[1]


# ── 5K 嚴格排列 ─────────────────────────────────────────────────────────────

LOOSE_LONG_ABOVE_MA10_BELOW_MA20 = [
    112, 100, 117, 95, 86, 84, 120, 107, 89, 119, 102,
    100, 106, 80, 87, 84, 93, 98, 82, 86, 118,
]
LOOSE_LONG_ABOVE_MA20_BELOW_MA10 = [
    84, 112, 108, 94, 102, 94, 112, 94, 85, 96, 84,
    103, 105, 105, 119, 88, 113, 113, 83, 90, 120,
]


def test_strict_order_matches_fully_aligned_long_and_short():
    long_result = evaluate_ma_alert(_rows(range(100, 121)), strict_order=True)
    short_result = evaluate_ma_alert(_rows(range(120, 99, -1)), strict_order=True)

    assert long_result.signal == "long"
    assert long_result.ma5 > long_result.ma10 > long_result.ma20
    assert short_result.signal == "short"
    assert short_result.ma5 < short_result.ma10 < short_result.ma20


def test_strict_order_rejects_partial_long_alignment():
    for closes in (LOOSE_LONG_ABOVE_MA10_BELOW_MA20, LOOSE_LONG_ABOVE_MA20_BELOW_MA10):
        assert evaluate_ma_alert(_rows(closes)).signal == "long"
        assert evaluate_ma_alert(_rows(closes), strict_order=True).matched is False


def test_strict_order_rejects_partial_short_alignment():
    for closes in (LOOSE_LONG_ABOVE_MA10_BELOW_MA20, LOOSE_LONG_ABOVE_MA20_BELOW_MA10):
        mirrored = [200 - c for c in closes]
        assert evaluate_ma_alert(_rows(mirrored)).signal == "short"
        assert evaluate_ma_alert(_rows(mirrored), strict_order=True).matched is False


def test_strict_order_still_requires_slopes():
    # 均線嚴格多排但 MA5 斜率轉負（最新一根大跌）→ 不成立
    closes = list(range(100, 141)) + [128]
    result = evaluate_ma_alert(_rows(closes), strict_order=True)

    assert result.ma5 > result.ma10 > result.ma20
    assert result.ma5_slope < 0
    assert result.matched is False


def test_formats_strict_order_condition():
    result = evaluate_ma_alert(_rows(range(100, 121)), strict_order=True)
    message = format_alert("TMFV6", "day", result, interval_minutes=5, strict_order=True)
    assert "MA5 > MA10 > MA20，且三條均線斜率皆為正" in message

    result = evaluate_ma_alert(_rows(range(120, 99, -1)), strict_order=True)
    message = format_alert("TMFV6", "night", result, interval_minutes=5, strict_order=True)
    assert "MA5 < MA10 < MA20，且三條均線斜率皆為負" in message


def test_strict_order_defaults_to_5k_only():
    from config.settings import settings

    assert settings.mtx_ma_alert.strict_order_intervals == [5]
