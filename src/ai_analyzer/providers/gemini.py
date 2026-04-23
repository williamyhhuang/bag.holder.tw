"""
Google Gemini AI 分析器實作（使用 google-genai 新版 SDK）
"""
from src.ai_analyzer.base import SYSTEM_PROMPT, BaseAIAnalyzer
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiAnalyzer(BaseAIAnalyzer):
    DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"

    def __init__(self, api_key: str, model: str = ""):
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError(
                "需要安裝 google-genai 套件：pip install google-genai"
            )
        self._client = genai.Client(api_key=api_key)
        self._types = genai_types
        self._model_name = model or self.DEFAULT_MODEL

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        types = self._types
        try:
            item_schema = types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "symbol": types.Schema(type=types.Type.STRING),
                    "name": types.Schema(type=types.Type.STRING),
                    "reason": types.Schema(type=types.Type.STRING),
                },
                required=["symbol", "name", "reason"],
            )
            array_schema = types.Schema(
                type=types.Type.ARRAY,
                items=item_schema,
            )
            tool = types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="classify_stocks",
                        description="將股票清單依據分析結果分類為四個等級",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "strong_buy": array_schema,
                                "buy": array_schema,
                                "watch": array_schema,
                                "avoid": array_schema,
                            },
                            required=["strong_buy", "buy", "watch", "avoid"],
                        ),
                    )
                ]
            )

            response = self._client.models.generate_content(
                model=self._model_name,
                contents=self._build_user_message(stocks),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[tool],
                ),
            )

            for part in response.candidates[0].content.parts:
                if part.function_call and part.function_call.name == "classify_stocks":
                    args = dict(part.function_call.args)
                    return {
                        "strong_buy": list(args.get("strong_buy", [])),
                        "buy": list(args.get("buy", [])),
                        "watch": list(args.get("watch", [])),
                        "avoid": list(args.get("avoid", [])),
                    }

            logger.warning("Gemini 未回傳 function_call")
            return {"strong_buy": [], "buy": [], "watch": [], "avoid": []}
        except Exception as e:
            logger.error(f"Gemini API 呼叫失敗: {e}")
            raise
