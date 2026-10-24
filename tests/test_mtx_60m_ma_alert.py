from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.application.services.mtx_60m_ma_alert import (
    completed_candles,
    detect_ma5_cross,
    evaluate_ma_alert,
    format_alert,
    format_ma5_cross_alert,
    held_positions,
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


def test_rejects_when_ma5_is_above_ma10_but_below_ma20():
    closes = [
        112, 100, 117, 95, 86, 84, 120, 107, 89, 119, 102,
        100, 106, 80, 87, 84, 93, 98, 82, 86, 118,
    ]

    result = evaluate_ma_alert(_rows(closes))

    assert result is not None
    assert result.ma5 >= result.ma10
    assert result.ma5 < result.ma20
    assert result.matched is False


def test_rejects_when_ma5_is_above_ma20_but_below_ma10():
    closes = [
        84, 112, 108, 94, 102, 94, 112, 94, 85, 96, 84,
        103, 105, 105, 119, 88, 113, 113, 83, 90, 120,
    ]

    result = evaluate_ma_alert(_rows(closes))

    assert result is not None
    assert result.ma5 < result.ma10
    assert result.ma5 >= result.ma20
    assert result.matched is False


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


def test_rejects_short_when_ma5_is_below_ma10_but_above_ma20():
    long_closes = [
        112, 100, 117, 95, 86, 84, 120, 107, 89, 119, 102,
        100, 106, 80, 87, 84, 93, 98, 82, 86, 118,
    ]
    result = evaluate_ma_alert(_rows([200 - close for close in long_closes]))

    assert result is not None
    assert result.ma5 <= result.ma10
    assert result.ma5 > result.ma20
    assert result.matched is False


def test_rejects_short_when_ma5_is_below_ma20_but_above_ma10():
    long_closes = [
        84, 112, 108, 94, 102, 94, 112, 94, 85, 96, 84,
        103, 105, 105, 119, 88, 113, 113, 83, 90, 120,
    ]
    result = evaluate_ma_alert(_rows([200 - close for close in long_closes]))

    assert result is not None
    assert result.ma5 > result.ma10
    assert result.ma5 <= result.ma20
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


def test_formats_short_telegram_message():
    result = evaluate_ma_alert(_rows(range(120, 99, -1)))

    message = format_alert("TMFI6", "night", result)

    assert "📉 微台 60K 空排通知" in message
    assert "MA5 ≤ MA10 ≤ MA20" in message
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


def _run_5m(runner, tmp_path, closes, now, sent, positions=None):
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

        async def ensure_futopt_account(self, retries=3):
            return True

        async def get_futures_positions(self):
            if positions is None:
                raise RuntimeError("positions unavailable")
            return positions

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
    assert "MA5 ≥ MA10 ≥ MA20" in sent[0]

    # 下一根仍是多排 → 不重複通知
    assert _run_5m(runner, tmp_path, up + [125], base + timedelta(minutes=5), sent) == 0
    assert len(sent) == 1

    # 轉為空排 → 通知
    down = list(range(125, 95, -1))
    assert _run_5m(runner, tmp_path, down, base + timedelta(minutes=200), sent) == 0
    assert len(sent) == 2 and "微台 5K 空排通知" in sent[1]



# ── 排列含等號：多排 MA5 >= MA10 >= MA20、空排 MA5 <= MA10 <= MA20 ─────────────

# MA5 == MA10 == 60、MA20 == 55，三條均線斜率皆正
EQUAL_MA5_MA10_LONG = [40] + [50] * 10 + [62, 60, 60, 60, 58, 60, 60, 60, 59, 61]


def test_long_matches_when_ma5_equals_ma10():
    result = evaluate_ma_alert(_rows(EQUAL_MA5_MA10_LONG))

    assert result.ma5 == result.ma10 == 60
    assert result.ma20 == 55
    assert min(result.ma5_slope, result.ma10_slope, result.ma20_slope) > 0
    assert result.signal == "long"


def test_short_matches_when_ma5_equals_ma10():
    result = evaluate_ma_alert(_rows([200 - c for c in EQUAL_MA5_MA10_LONG]))

    assert result.ma5 == result.ma10 == 140
    assert result.ma20 == 145
    assert result.signal == "short"


def test_still_requires_slopes_when_aligned():
    # 均線多排但 MA5 斜率轉負（最新一根大跌）→ 不成立
    closes = list(range(100, 141)) + [128]
    result = evaluate_ma_alert(_rows(closes))

    assert result.ma5 >= result.ma10 >= result.ma20
    assert result.ma5_slope < 0
    assert result.matched is False


def test_formats_5k_condition_with_equal_signs():
    result = evaluate_ma_alert(_rows(range(100, 121)))
    message = format_alert("TMFV6", "day", result, interval_minutes=5)
    assert "MA5 ≥ MA10 ≥ MA20，且三條均線斜率皆為正" in message

    result = evaluate_ma_alert(_rows(range(120, 99, -1)))
    message = format_alert("TMFV6", "night", result, interval_minutes=5)
    assert "MA5 ≤ MA10 ≤ MA20，且三條均線斜率皆為負" in message



# ── 持倉時 5K 站上／跌破 MA5 ─────────────────────────────────────────────────

TMF_LONG = {"symbol": "FITMF", "expiry_date": "202611", "buy_sell": "BSAction.Buy",
            "price": 22000.0, "orig_lots": 2, "tradable_lot": 2}


def _rows5(closes):
    start = datetime(2026, 10, 21, 9, tzinfo=TW)
    return [(start + timedelta(minutes=5 * i), c) for i, c in enumerate(closes)]


def test_detects_close_crossing_above_ma5():
    result = detect_ma5_cross(_rows5([100, 100, 100, 100, 100, 99, 105]))
    assert result is not None
    assert result.direction == "up"
    assert result.close > result.ma5


def test_detects_close_crossing_below_ma5():
    result = detect_ma5_cross(_rows5([100, 100, 100, 100, 100, 101, 95]))
    assert result is not None
    assert result.direction == "down"
    assert result.close < result.ma5


def test_no_cross_when_already_above_or_below_ma5():
    assert detect_ma5_cross(_rows5([100, 101, 102, 103, 104, 105, 106])) is None
    assert detect_ma5_cross(_rows5([106, 105, 104, 103, 102, 101, 100])) is None


def test_ma5_cross_requires_six_bars():
    assert detect_ma5_cross(_rows5([100, 100, 100, 100, 105])) is None


def test_held_positions_filters_tmf_with_lots():
    positions = [
        TMF_LONG,
        {"symbol": "FITX", "orig_lots": 1, "tradable_lot": 1},
        {"symbol": "TMFK6", "orig_lots": 0, "tradable_lot": 0},
        {"symbol": "TMFK6", "orig_lots": 1, "tradable_lot": 0},
    ]
    held = held_positions(positions, ["TMF"])
    assert [p["symbol"] for p in held] == ["FITMF", "TMFK6"]


def test_formats_ma5_cross_alert_with_position():
    cross = detect_ma5_cross(_rows5([100, 100, 100, 100, 100, 101, 95]))
    message = format_ma5_cross_alert("TMFK6", "day", cross, [TMF_LONG])
    assert "🔽 微台 5K 跌破 MA5（持倉通知）" in message
    assert "FITMF 202611 多單 2 口 @ 22000" in message


def _position_msgs(sent):
    return [m for m in sent if "持倉通知" in m]


def test_5m_runner_sends_ma5_cross_only_when_holding(tmp_path):
    runner = _load_runner()
    now = datetime(2026, 10, 21, 10, 0, tzinfo=TW)
    closes = [100] * 25 + [101, 95]  # 最後一根跌破 MA5

    sent = []
    _run_5m(runner, tmp_path / "flat", closes, now, sent, positions=[])
    assert _position_msgs(sent) == []

    sent = []
    _run_5m(runner, tmp_path / "held", closes, now, sent, positions=[TMF_LONG])
    assert len(_position_msgs(sent)) == 1 and "跌破 MA5" in _position_msgs(sent)[0]

    # 同一根 K 重跑不重複通知
    _run_5m(runner, tmp_path / "held", closes, now, sent, positions=[TMF_LONG])
    assert len(_position_msgs(sent)) == 1


def test_5m_runner_ignores_position_query_failure(tmp_path):
    runner = _load_runner()
    sent = []
    closes = [100] * 25 + [101, 95]
    assert _run_5m(runner, tmp_path, closes, datetime(2026, 10, 21, 10, 0, tzinfo=TW), sent, positions=None) == 0
    assert _position_msgs(sent) == []


def test_5m_runner_logs_raw_positions(tmp_path, caplog):
    import logging

    runner = _load_runner()
    sent = []
    closes = [100] * 25 + [101, 102]
    with caplog.at_level(logging.INFO):
        _run_5m(runner, tmp_path, closes, datetime(2026, 10, 21, 10, 0, tzinfo=TW), sent, positions=[TMF_LONG])
    assert any("期貨部位 1 筆" in r.message and "FITMF" in r.message for r in caplog.records)
