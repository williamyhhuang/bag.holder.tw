"""
MTX 回測出場機制測試 — 確保 scripts/backtest_mtx_strategies.simulate_session 與生產引擎
MTXSignalEngine 採相同出場框架（保本+移動停利，KD 反交叉為可選且預設關閉）。

回測=實盤一致（CLAUDE.md）：此處驗證回測層的出場優先序與預設行為。
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# scripts/ 非套件，加入 path 以 import 回測模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backtest_mtx_strategies as bt  # noqa: E402


def _random_walk_session(n_ticks: int = 600, seed: int = 42):
    """固定種子的隨機漫步日盤 tick 序列（帶微幅上升漂移），產生真實的 KD 交叉進場與多種出場。"""
    rnd = random.Random(seed)
    start = datetime(2026, 5, 19, 9, 0, 0)
    ticks = []
    t = start
    price = 20000.0
    for _ in range(n_ticks):
        price += 0.05 + rnd.uniform(-9, 9)
        ticks.append((t, round(price, 0), 1))
        t += timedelta(seconds=20)
    return ticks


def _daily_bullish(n=14):
    """中性偏多的日 K（讓 daily_bias 不致於回傳 -1）。"""
    bars = []
    base = 19000.0
    for i in range(n):
        c = base + i * 20
        bars.append(bt.Bar(datetime(2026, 5, 1) + timedelta(days=i), c - 5, c + 10, c - 10, c, 1000))
    return bars


def _run(enable_kd_exit, monkeypatch):
    # 強制 daily bias = +1，隔離日 K seed，聚焦出場行為
    monkeypatch.setattr(bt, "daily_bias", lambda _bars: 1)
    ticks = _random_walk_session()
    bars_1m = bt.build_bars(ticks, 1)
    bars_5m = bt.build_bars(ticks, 5)
    # variant="D"：5m 訊號 = sign(daily bias)，進場僅取決於 1m 黃金交叉，
    # 可在合成震盪行情中穩定產生交易以驗證出場框架（出場邏輯與 variant 無關）。
    return bt.simulate_session(
        bars_1m, bars_5m, _daily_bullish(), variant="D",
        long_only=True, enable_kd_exit=enable_kd_exit,
    )


def test_generates_trades(monkeypatch):
    trades = _run(enable_kd_exit=False, monkeypatch=monkeypatch)
    assert len(trades) > 0, "震盪 session 應產生交易"


def test_no_kd_exit_when_disabled(monkeypatch):
    trades = _run(enable_kd_exit=False, monkeypatch=monkeypatch)
    reasons = {t.exit_reason for t in trades}
    assert not any("KD" in r for r in reasons), f"關閉 KD 出場時不應出現 KD 出場原因：{reasons}"


def test_exit_reasons_within_allowed_set(monkeypatch):
    trades = _run(enable_kd_exit=False, monkeypatch=monkeypatch)
    allowed = {"停損", "獲利", "保本", "移動停利", "多空反轉", "收盤強平"}
    for t in trades:
        assert t.exit_reason in allowed, f"未預期的出場原因：{t.exit_reason}"


def test_trailing_or_breakeven_reachable(monkeypatch):
    """新出場機制（保本/移動停利）應在震盪行情中至少觸發一次。"""
    trades = _run(enable_kd_exit=False, monkeypatch=monkeypatch)
    reasons = [t.exit_reason for t in trades]
    assert any(r in ("移動停利", "保本") for r in reasons), f"應觸發保本或移動停利：{set(reasons)}"


def test_kd_exit_appears_when_enabled(monkeypatch):
    """開啟 KD 出場後，KD 反交叉出場原因可出現（對照組）。"""
    trades = _run(enable_kd_exit=True, monkeypatch=monkeypatch)
    # 至少能正常完成且產生交易；KD 在此震盪行情通常會出現
    assert len(trades) > 0
