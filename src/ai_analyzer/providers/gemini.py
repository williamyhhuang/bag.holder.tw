"""
Google Gemini AI 分析器實作
"""
import json

from src.ai_analyzer.base import RESULT_SCHEMA, SYSTEM_PROMPT, BaseAIAnalyzer
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiAnalyzer(BaseAIAnalyzer):
    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str, model: str = ""):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "需要安裝 google-generativeai 套件：pip install google-generativeai>=0.8.0"
            )
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model or self.DEFAULT_MODEL

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        try:
            tool = self._genai.protos.Tool(
                function_declarations=[
                    self._genai.protos.FunctionDeclaration(
                        name="classify_stocks",
                        description="將股票清單依據分析結果分類為四個等級",
                        parameters=self._genai.protos.Schema(
                            type=self._genai.protos.Type.OBJECT,
                            properties=self._build_gemini_properties(),
                            required=["strong_buy", "buy", "watch", "avoid"],
                        ),
                    )
                ]
            )

            model = self._genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=SYSTEM_PROMPT,
                tools=[tool],
            )

            response = model.generate_content(self._build_user_message(stocks))

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

    def _build_gemini_properties(self) -> dict:
        """將共用 RESULT_SCHEMA 轉換為 Gemini protos.Schema 格式"""
        item_schema = self._genai.protos.Schema(
            type=self._genai.protos.Type.OBJECT,
            properties={
                "symbol": self._genai.protos.Schema(type=self._genai.protos.Type.STRING),
                "name": self._genai.protos.Schema(type=self._genai.protos.Type.STRING),
                "reason": self._genai.protos.Schema(type=self._genai.protos.Type.STRING),
            },
            required=["symbol", "name", "reason"],
        )
        array_schema = self._genai.protos.Schema(
            type=self._genai.protos.Type.ARRAY,
            items=item_schema,
        )
        return {
            "strong_buy": array_schema,
            "buy": array_schema,
            "watch": array_schema,
            "avoid": array_schema,
        }
