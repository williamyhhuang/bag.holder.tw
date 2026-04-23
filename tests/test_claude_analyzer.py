"""
Unit tests for ClaudeAnalyzer
"""
import pytest
from unittest.mock import MagicMock, patch


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

MOCK_TOOL_RESULT = {
    "strong_buy": [
        {"symbol": "2330.TW", "name": "台積電", "reason": "三訊號共振，RSI 62 健康"}
    ],
    "buy": [],
    "watch": [
        {"symbol": "3008.TW", "name": "大立光", "reason": "RSI 偏低，等待確認"}
    ],
    "avoid": [
        {"symbol": "2454.TW", "name": "聯發科", "reason": "處置股風險高，避免操作"}
    ],
}


def _make_mock_response(tool_input: dict):
    """建立 Mock Claude API 回應"""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "classify_stocks"
    block.input = tool_input

    response = MagicMock()
    response.content = [block]
    return response


class TestClaudeAnalyzer:
    def _get_analyzer(self):
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            from src.claude.analyzer import ClaudeAnalyzer
            analyzer = ClaudeAnalyzer.__new__(ClaudeAnalyzer)
            analyzer._anthropic = MagicMock()
            analyzer._model = "claude-sonnet-4-6"
            analyzer._client = MagicMock()
            return analyzer

    def test_analyze_signals_returns_all_keys(self):
        analyzer = self._get_analyzer()
        analyzer._client.messages.create.return_value = _make_mock_response(MOCK_TOOL_RESULT)

        result = analyzer.analyze_signals(SAMPLE_SIGNALS_RESULT)

        assert "strong_buy" in result
        assert "buy" in result
        assert "watch" in result
        assert "avoid" in result
        assert "target_date" in result

    def test_analyze_signals_target_date_preserved(self):
        analyzer = self._get_analyzer()
        analyzer._client.messages.create.return_value = _make_mock_response(MOCK_TOOL_RESULT)

        result = analyzer.analyze_signals(SAMPLE_SIGNALS_RESULT)

        assert result["target_date"] == "2026-04-23"

    def test_analyze_signals_merges_buy_and_watch(self):
        """analyze_signals 應把 buy + watch 合併後傳給 Claude"""
        analyzer = self._get_analyzer()
        analyzer._client.messages.create.return_value = _make_mock_response(MOCK_TOOL_RESULT)

        analyzer.analyze_signals(SAMPLE_SIGNALS_RESULT)

        call_args = analyzer._client.messages.create.call_args
        messages = call_args[1]["messages"] if call_args[1] else call_args[0][4]
        user_content = messages[0]["content"]
        # 應包含 buy + watch 的 symbol
        assert "2330.TW" in user_content
        assert "3008.TW" in user_content

    def test_analyze_signals_empty_lists(self):
        analyzer = self._get_analyzer()

        empty_result = {
            "target_date": "2026-04-23",
            "buy": [],
            "watch": [],
            "sell": [],
            "sector_summary": [],
        }
        result = analyzer.analyze_signals(empty_result)

        assert result["strong_buy"] == []
        assert result["buy"] == []
        assert result["watch"] == []
        assert result["avoid"] == []
        # API 不應被呼叫
        analyzer._client.messages.create.assert_not_called()

    def test_analyze_signals_batching(self):
        """超過 max_stocks_per_batch 時應分批呼叫"""
        analyzer = self._get_analyzer()
        analyzer._client.messages.create.return_value = _make_mock_response(
            {"strong_buy": [], "buy": [], "watch": [], "avoid": []}
        )

        many_stocks = [
            {"symbol": f"{i:04d}.TW", "name": f"股票{i}", "signal": "BB Squeeze Break",
             "price": 100.0, "rsi": 55.0, "sector": "電子業", "revenue_yoy_pct": None, "note": ""}
            for i in range(60)
        ]
        result_input = {
            "target_date": "2026-04-23",
            "buy": many_stocks,
            "watch": [],
            "sell": [],
        }

        analyzer.analyze_signals(result_input, max_stocks_per_batch=50)

        # 60 支股票 / 50 = 2 批
        assert analyzer._client.messages.create.call_count == 2

    def test_no_tool_use_block_returns_empty(self):
        """Claude 未回傳 tool_use 時應回傳空結果"""
        analyzer = self._get_analyzer()
        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        response.content = [text_block]
        analyzer._client.messages.create.return_value = response

        result = analyzer._analyze_batch([
            {"symbol": "2330.TW", "name": "台積電", "signal": "BB Squeeze Break",
             "price": 980.0, "rsi": 62.0, "sector": "半導體業",
             "revenue_yoy_pct": None, "note": ""}
        ])

        assert result == {"strong_buy": [], "buy": [], "watch": [], "avoid": []}


class TestFormatForTelegram:
    def _get_analyzer(self):
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            from src.claude.analyzer import ClaudeAnalyzer
            analyzer = ClaudeAnalyzer.__new__(ClaudeAnalyzer)
            analyzer._anthropic = MagicMock()
            analyzer._model = "claude-sonnet-4-6"
            analyzer._client = MagicMock()
            return analyzer

    def test_format_contains_emojis(self):
        analyzer = self._get_analyzer()
        claude_result = {
            "target_date": "2026-04-23",
            **MOCK_TOOL_RESULT,
        }
        chunks = analyzer.format_for_telegram(claude_result)
        full_text = "\n".join(chunks)

        assert "🤖" in full_text
        assert "🔥" in full_text
        assert "⛔" in full_text

    def test_format_symbol_shortened(self):
        """symbol 應縮短為不含 .TW 的格式"""
        analyzer = self._get_analyzer()
        claude_result = {
            "target_date": "2026-04-23",
            "strong_buy": [{"symbol": "2330.TW", "name": "台積電", "reason": "測試"}],
            "buy": [],
            "watch": [],
            "avoid": [],
        }
        chunks = analyzer.format_for_telegram(claude_result)
        full_text = "\n".join(chunks)

        assert "2330" in full_text
        assert "2330.TW" not in full_text

    def test_format_empty_sections_omitted(self):
        """空的分類不應出現在訊息中"""
        analyzer = self._get_analyzer()
        claude_result = {
            "target_date": "2026-04-23",
            "strong_buy": [{"symbol": "2330.TW", "name": "台積電", "reason": "測試"}],
            "buy": [],
            "watch": [],
            "avoid": [],
        }
        chunks = analyzer.format_for_telegram(claude_result)
        full_text = "\n".join(chunks)

        assert "建議買入 (0" not in full_text
        assert "觀察 (0" not in full_text

    def test_format_note_tag_shown(self):
        """處置股標記應出現在訊息中"""
        analyzer = self._get_analyzer()
        claude_result = {
            "target_date": "2026-04-23",
            "strong_buy": [],
            "buy": [],
            "watch": [],
            "avoid": [
                {"symbol": "2454.TW", "name": "聯發科", "reason": "處置股", "note": "處置股"}
            ],
        }
        chunks = analyzer.format_for_telegram(claude_result)
        full_text = "\n".join(chunks)

        assert "⚠️" in full_text

    def test_format_long_message_split(self):
        """超過 4096 字元時應拆分為多則"""
        analyzer = self._get_analyzer()
        # 建立大量股票填滿訊息
        many_stocks = [
            {"symbol": f"{i:04d}.TW", "name": f"超長名稱股票{i:04d}", "reason": "訊號強勢，RSI 健康，族群強勢，基本面良好"}
            for i in range(100)
        ]
        claude_result = {
            "target_date": "2026-04-23",
            "strong_buy": many_stocks,
            "buy": [],
            "watch": [],
            "avoid": [],
        }
        chunks = analyzer.format_for_telegram(claude_result)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 4096
