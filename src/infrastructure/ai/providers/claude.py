"""
Claude (Anthropic) AI 分析器實作
"""
from ..base import RESULT_SCHEMA, SELL_RESULT_SCHEMA, SELL_SYSTEM_PROMPT, SYSTEM_PROMPT, BaseAIAnalyzer
from ....utils.logger import get_logger

logger = get_logger(__name__)

_TOOL = {
    "name": "classify_stocks",
    "description": "將股票清單依據分析結果分類為四個等級",
    "input_schema": RESULT_SCHEMA,
}

_SELL_TOOL = {
    "name": "classify_holdings_sell_decision",
    "description": "判斷持倉股票是否應出場，分類為確認賣出、設停損觀察、繼續持有",
    "input_schema": SELL_RESULT_SCHEMA,
}


class ClaudeAnalyzer(BaseAIAnalyzer):
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: str, model: str = ""):
        try:
            import anthropic
        except ImportError:
            raise ImportError("需要安裝 anthropic 套件：pip install anthropic>=0.40.0")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[_TOOL],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": self._build_user_message(stocks)}],
            )
            for block in response.content:
                if block.type == "tool_use" and block.name == "classify_stocks":
                    return block.input
            logger.warning("Claude 未回傳 tool_use block")
            return {"strong_buy": [], "buy": [], "watch": [], "avoid": []}
        except Exception as e:
            logger.error(f"Claude API 呼叫失敗: {e}")
            raise

    def _analyze_holdings_batch(self, stocks: list[dict]) -> dict:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SELL_SYSTEM_PROMPT,
                tools=[_SELL_TOOL],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": self._build_holdings_message(stocks)}],
            )
            for block in response.content:
                if block.type == "tool_use" and block.name == "classify_holdings_sell_decision":
                    return block.input
            logger.warning("Claude 未回傳持倉分析 tool_use block")
            return {"sell": [], "watch": [], "hold": []}
        except Exception as e:
            logger.error(f"Claude API 持倉分析呼叫失敗: {e}")
            raise
