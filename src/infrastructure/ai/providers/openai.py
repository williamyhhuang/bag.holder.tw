"""
OpenAI AI 分析器實作
"""
import json

from ..base import RESULT_SCHEMA, SYSTEM_PROMPT, BaseAIAnalyzer
from ....utils.logger import get_logger

logger = get_logger(__name__)

_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_stocks",
        "description": "將股票清單依據分析結果分類為四個等級",
        "parameters": RESULT_SCHEMA,
    },
}


class OpenAIAnalyzer(BaseAIAnalyzer):
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str, model: str = ""):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("需要安裝 openai 套件：pip install openai>=1.0.0")
        self._client = OpenAI(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_message(stocks)},
                ],
                tools=[_TOOL],
                tool_choice={"type": "function", "function": {"name": "classify_stocks"}},
            )
            tool_call = response.choices[0].message.tool_calls
            if tool_call:
                return json.loads(tool_call[0].function.arguments)
            logger.warning("OpenAI 未回傳 tool_call")
            return {"strong_buy": [], "buy": [], "watch": [], "avoid": []}
        except Exception as e:
            logger.error(f"OpenAI API 呼叫失敗: {e}")
            raise
