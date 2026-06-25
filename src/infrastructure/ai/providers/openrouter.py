"""
OpenRouter AI 分析器實作（OpenAI 相容 API）
"""
import json

from ..base import RESULT_SCHEMA, SELL_RESULT_SCHEMA, SELL_SYSTEM_PROMPT, SYSTEM_PROMPT, BaseAIAnalyzer
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

_SELL_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_holdings_sell_decision",
        "description": "判斷持倉股票是否應出場，分類為確認賣出、設停損觀察、繼續持有",
        "parameters": SELL_RESULT_SCHEMA,
    },
}

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterAnalyzer(BaseAIAnalyzer):
    DEFAULT_MODEL = "google/gemini-2.5-flash-preview"

    def __init__(
        self,
        api_key: str,
        model: str = "",
        seed: int | None = None,
        provider_order: str | None = None,
        provider_allow_fallbacks: bool = False,
        max_tokens: int | None = None,
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("需要安裝 openai 套件：pip install openai>=1.0.0")
        self._client = OpenAI(
            api_key=api_key,
            base_url=_OPENROUTER_BASE_URL,
        )
        self._model = model or self.DEFAULT_MODEL
        self._seed = seed
        self._provider_order = (
            [p.strip() for p in provider_order.split(",") if p.strip()]
            if provider_order
            else None
        )
        self._provider_allow_fallbacks = provider_allow_fallbacks
        self._max_tokens = max_tokens

    def _request_kwargs(self) -> dict:
        """非決定性的共用請求參數（目前為 max_tokens）。

        明確設定 max_tokens 可避免 OpenRouter 依模型輸出上限（如 65536）
        預扣額度，導致餘額足夠實際用量卻仍回傳 402（額度不足）的問題。
        """
        kwargs: dict = {}
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        return kwargs

    def _determinism_kwargs(self) -> dict:
        """組裝降低變異用的請求參數：固定 seed + 鎖定後端供應商。

        seed 讓支援的後端盡力產生一致輸出；provider 路由鎖定可消除
        OpenRouter 將同一請求送到不同後端造成的變異（最大變異來源）。
        """
        kwargs: dict = {}
        if self._seed is not None:
            kwargs["seed"] = self._seed
        if self._provider_order:
            kwargs["extra_body"] = {
                "provider": {
                    "order": self._provider_order,
                    "allow_fallbacks": self._provider_allow_fallbacks,
                }
            }
        return kwargs

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_message(stocks)},
                ],
                tools=[_TOOL],
                tool_choice={"type": "function", "function": {"name": "classify_stocks"}},
                **self._request_kwargs(),
                **self._determinism_kwargs(),
            )
            tool_call = response.choices[0].message.tool_calls
            if tool_call:
                return json.loads(tool_call[0].function.arguments)
            logger.warning("OpenRouter 未回傳 tool_call")
            return {"strong_buy": [], "buy": [], "watch": [], "avoid": []}
        except Exception as e:
            logger.error(f"OpenRouter API 呼叫失敗: {e}")
            raise

    def _analyze_holdings_batch(self, stocks: list[dict]) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SELL_SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_holdings_message(stocks)},
                ],
                tools=[_SELL_TOOL],
                tool_choice={"type": "function", "function": {"name": "classify_holdings_sell_decision"}},
                **self._request_kwargs(),
                **self._determinism_kwargs(),
            )
            tool_call = response.choices[0].message.tool_calls
            if tool_call:
                return json.loads(tool_call[0].function.arguments)
            logger.warning("OpenRouter 未回傳持倉分析 tool_call")
            return {"sell": [], "watch": [], "hold": []}
        except Exception as e:
            logger.error(f"OpenRouter API 持倉分析呼叫失敗: {e}")
            raise
