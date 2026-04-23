"""
Unit tests for ai_analyzer (base class + providers + factory)
"""
import json
import pytest
from typing import Optional
from unittest.mock import MagicMock, patch

from src.ai_analyzer.base import BaseAIAnalyzer, _short_symbol, _split_into_chunks

SAMPLE_SIGNALS_RESULT = {
    "target_date": "2026-04-23",
    "total_scanned": 3,
    "buy": [
        {
            "symbol": "2330.TW",
            "name": "台積電",
            "signal": "BB Squeeze Break + Donchian Breakout",
            "price": 980.0,
            "rsi": 62.5,
            "sector": "半導體業",
            "revenue_yoy_pct": 20.0,
            "note": "",
        },
        {
            "symbol": "2454.TW",
            "name": "聯發科",
            "signal": "Golden Cross",
            "price": 1200.0,
            "rsi": 55.0,
            "sector": "半導體業",
            "revenue_yoy_pct": 10.0,
            "note": "處置股",
        },
    ],
    "sell": [],
    "watch": [
        {
            "symbol": "3008.TW",
            "name": "大立光",
            "signal": "BB Squeeze Break",
            "price": 2500.0,
            "rsi": 48.0,
            "sector": "光學鏡頭",
            "revenue_yoy_pct": None,
            "note": "",
        }
    ],
    "sector_summary": [],
}

MOCK_BATCH_RESULT = {
    "strong_buy": [{"symbol": "2330.TW", "name": "台積電", "reason": "三訊號共振，RSI 62 健康"}],
    "buy": [],
    "watch": [{"symbol": "3008.TW", "name": "大立光", "reason": "RSI 偏低，等待確認"}],
    "avoid": [{"symbol": "2454.TW", "name": "聯發科", "reason": "處置股風險高，避免操作"}],
}


# ── 具體的測試用 Analyzer（繼承 BaseAIAnalyzer）────────────────────────────────
class FakeAnalyzer(BaseAIAnalyzer):
    """測試用：_analyze_batch 固定回傳 MOCK_BATCH_RESULT"""

    def __init__(self, batch_result: Optional[dict] = None):
        self._batch_result = batch_result or MOCK_BATCH_RESULT
        self._call_count = 0

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        self._call_count += 1
        return self._batch_result


# ── BaseAIAnalyzer.analyze_signals ────────────────────────────────────────────

class TestAnalyzeSignals:
    def test_returns_all_keys(self):
        analyzer = FakeAnalyzer()
        result = analyzer.analyze_signals(SAMPLE_SIGNALS_RESULT)
        assert all(k in result for k in ("strong_buy", "buy", "watch", "avoid", "target_date"))

    def test_target_date_preserved(self):
        analyzer = FakeAnalyzer()
        result = analyzer.analyze_signals(SAMPLE_SIGNALS_RESULT)
        assert result["target_date"] == "2026-04-23"

    def test_merges_buy_and_watch(self):
        """analyze_signals 應把 buy + watch 合併後傳給 _analyze_batch"""
        call_args: list[list[dict]] = []

        class CaptureAnalyzer(BaseAIAnalyzer):
            def _analyze_batch(self, stocks):
                call_args.append(stocks)
                return {"strong_buy": [], "buy": [], "watch": [], "avoid": []}

        CaptureAnalyzer().analyze_signals(SAMPLE_SIGNALS_RESULT)
        symbols = [s["symbol"] for s in call_args[0]]
        assert "2330.TW" in symbols  # buy
        assert "3008.TW" in symbols  # watch

    def test_empty_input_returns_empty(self):
        analyzer = FakeAnalyzer()
        result = analyzer.analyze_signals({"target_date": "2026-04-23", "buy": [], "watch": []})
        assert result["strong_buy"] == []
        assert result["buy"] == []
        assert result["avoid"] == []
        assert analyzer._call_count == 0

    def test_batching(self):
        """60 支股票 / 50 = 2 批"""
        many = [
            {"symbol": f"{i:04d}.TW", "name": f"股票{i}", "signal": "BB Squeeze Break",
             "price": 100.0, "rsi": 55.0, "sector": "電子業", "revenue_yoy_pct": None, "note": ""}
            for i in range(60)
        ]
        analyzer = FakeAnalyzer({"strong_buy": [], "buy": [], "watch": [], "avoid": []})
        analyzer.analyze_signals({"target_date": "2026-04-23", "buy": many, "watch": []},
                                  max_stocks_per_batch=50)
        assert analyzer._call_count == 2

    def test_batch_results_merged(self):
        """多批結果應合併到同一個分類"""
        batch_result = {
            "strong_buy": [{"symbol": "X.TW", "name": "X", "reason": "r"}],
            "buy": [], "watch": [], "avoid": [],
        }
        analyzer = FakeAnalyzer(batch_result)
        many = [
            {"symbol": f"{i}.TW", "name": f"S{i}", "signal": "s",
             "price": 1.0, "rsi": 50.0, "sector": "", "revenue_yoy_pct": None, "note": ""}
            for i in range(60)
        ]
        result = analyzer.analyze_signals({"target_date": "x", "buy": many, "watch": []},
                                           max_stocks_per_batch=50)
        # 2 批各貢獻 1 筆 strong_buy → 共 2 筆
        assert len(result["strong_buy"]) == 2


# ── BaseAIAnalyzer.format_for_telegram ───────────────────────────────────────

class TestFormatForTelegram:
    def _result(self, **overrides):
        base = {"target_date": "2026-04-23", **MOCK_BATCH_RESULT}
        base.update(overrides)
        return base

    def test_contains_emojis(self):
        chunks = FakeAnalyzer().format_for_telegram(self._result())
        text = "\n".join(chunks)
        assert "🤖" in text and "🔥" in text and "⛔" in text

    def test_symbol_shortened(self):
        result = self._result(
            strong_buy=[{"symbol": "2330.TW", "name": "台積電", "reason": "測試"}],
            buy=[], watch=[], avoid=[],
        )
        text = "\n".join(FakeAnalyzer().format_for_telegram(result))
        assert "2330" in text
        assert "2330.TW" not in text

    def test_empty_sections_omitted(self):
        result = self._result(
            strong_buy=[{"symbol": "2330.TW", "name": "台積電", "reason": "測試"}],
            buy=[], watch=[], avoid=[],
        )
        text = "\n".join(FakeAnalyzer().format_for_telegram(result))
        assert "建議買入 (0" not in text

    def test_note_tag_shown(self):
        result = self._result(
            strong_buy=[], buy=[], watch=[],
            avoid=[{"symbol": "2454.TW", "name": "聯發科", "reason": "處置股", "note": "處置股"}],
        )
        text = "\n".join(FakeAnalyzer().format_for_telegram(result))
        assert "⚠️" in text

    def test_long_message_split(self):
        many = [
            {"symbol": f"{i:04d}.TW", "name": f"超長名稱股票{i:04d}", "reason": "訊號強勢，RSI 健康，族群強勢，基本面良好"}
            for i in range(100)
        ]
        result = self._result(strong_buy=many, buy=[], watch=[], avoid=[])
        chunks = FakeAnalyzer().format_for_telegram(result)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 4096


# ── Factory ───────────────────────────────────────────────────────────────────

class TestFactory:
    def test_unknown_provider_raises(self):
        from src.ai_analyzer.factory import create_analyzer
        with pytest.raises(ValueError, match="不支援的 AI provider"):
            create_analyzer(provider="unknown", api_key="key")

    def test_openrouter_provider_returns_openrouter_analyzer(self):
        from src.ai_analyzer.factory import create_analyzer
        import sys
        sys.modules["openai"] = MagicMock()
        from src.ai_analyzer.providers.openrouter import OpenRouterAnalyzer
        analyzer = create_analyzer(provider="openrouter", api_key="test-key")
        assert isinstance(analyzer, OpenRouterAnalyzer)

    def test_openrouter_provider_case_insensitive(self):
        from src.ai_analyzer.factory import create_analyzer
        import sys
        sys.modules["openai"] = MagicMock()
        from src.ai_analyzer.providers.openrouter import OpenRouterAnalyzer
        analyzer = create_analyzer(provider="OpenRouter", api_key="k")
        assert isinstance(analyzer, OpenRouterAnalyzer)

    def test_claude_provider_returns_claude_analyzer(self):
        from src.ai_analyzer.factory import create_analyzer
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            mock_anthropic = MagicMock()
            with patch("src.ai_analyzer.providers.claude.anthropic", mock_anthropic, create=True):
                import importlib
                import sys
                # 讓 import anthropic 在 ClaudeAnalyzer.__init__ 裡不失敗
                sys.modules["anthropic"] = MagicMock()
                from src.ai_analyzer.providers.claude import ClaudeAnalyzer
                analyzer = create_analyzer(provider="claude", api_key="test-key")
                assert isinstance(analyzer, ClaudeAnalyzer)

    def test_provider_case_insensitive(self):
        from src.ai_analyzer.factory import create_analyzer
        import sys
        sys.modules["anthropic"] = MagicMock()
        from src.ai_analyzer.providers.claude import ClaudeAnalyzer
        analyzer = create_analyzer(provider="CLAUDE", api_key="k")
        assert isinstance(analyzer, ClaudeAnalyzer)


# ── Helper functions ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_short_symbol_with_suffix(self):
        assert _short_symbol("2330.TW") == "2330"
        assert _short_symbol("4741.TWO") == "4741"

    def test_short_symbol_without_suffix(self):
        assert _short_symbol("2330") == "2330"

    def test_split_short_text_no_split(self):
        chunks = _split_into_chunks("short text", max_length=100)
        assert chunks == ["short text"]

    def test_split_long_text(self):
        text = "\n".join([f"line {i}" for i in range(1000)])
        chunks = _split_into_chunks(text, max_length=100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100
