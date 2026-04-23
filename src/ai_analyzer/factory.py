"""
AI 分析器工廠：根據設定建立對應的 provider 實例
"""
from src.ai_analyzer.base import BaseAIAnalyzer


def create_analyzer(
    provider: str,
    api_key: str,
    model: str = "",
) -> BaseAIAnalyzer:
    """建立 AI 分析器實例

    Args:
        provider: "claude" | "openai" | "gemini"
        api_key:  對應 provider 的 API key
        model:    指定模型名稱；空字串則使用各 provider 的預設值

    Returns:
        BaseAIAnalyzer 的子類別實例

    Raises:
        ValueError: provider 不在支援清單中
        ImportError: 對應的套件未安裝
    """
    provider = provider.lower().strip()

    if provider == "claude":
        from src.ai_analyzer.providers.claude import ClaudeAnalyzer
        return ClaudeAnalyzer(api_key=api_key, model=model)

    if provider == "openai":
        from src.ai_analyzer.providers.openai import OpenAIAnalyzer
        return OpenAIAnalyzer(api_key=api_key, model=model)

    if provider == "gemini":
        from src.ai_analyzer.providers.gemini import GeminiAnalyzer
        return GeminiAnalyzer(api_key=api_key, model=model)

    raise ValueError(
        f"不支援的 AI provider：'{provider}'，"
        "請使用 'claude'、'openai' 或 'gemini'"
    )
