"""
AI 分析器工廠：根據設定建立對應的 provider 實例
"""
from .base import BaseAIAnalyzer


def create_analyzer(
    provider: str,
    api_key: str,
    model: str = "",
    *,
    seed: int | None = None,
    provider_order: str | None = None,
    provider_allow_fallbacks: bool = False,
    max_tokens: int | None = None,
) -> BaseAIAnalyzer:
    """建立 AI 分析器實例

    Args:
        provider: "claude" | "openai" | "gemini" | "openrouter"
        api_key:  對應 provider 的 API key
        model:    指定模型名稱；空字串則使用各 provider 的預設值
        seed:     固定 seed（僅 OpenRouter 使用，降低取樣變異）
        provider_order: 鎖定 OpenRouter 後端供應商順序（逗號分隔）
        provider_allow_fallbacks: 指定供應商不可用時是否允許改用其他家
        max_tokens: 回應最大輸出 tokens（僅 OpenRouter 使用，None = 套用 provider 預設）

    Returns:
        BaseAIAnalyzer 的子類別實例

    Raises:
        ValueError: provider 不在支援清單中
        ImportError: 對應的套件未安裝
    """
    provider = provider.lower().strip()

    if provider == "claude":
        from .providers.claude import ClaudeAnalyzer
        return ClaudeAnalyzer(api_key=api_key, model=model)

    if provider == "openai":
        from .providers.openai import OpenAIAnalyzer
        return OpenAIAnalyzer(api_key=api_key, model=model)

    if provider == "gemini":
        from .providers.gemini import GeminiAnalyzer
        return GeminiAnalyzer(api_key=api_key, model=model)

    if provider == "openrouter":
        from .providers.openrouter import OpenRouterAnalyzer
        return OpenRouterAnalyzer(
            api_key=api_key,
            model=model,
            seed=seed,
            provider_order=provider_order,
            provider_allow_fallbacks=provider_allow_fallbacks,
            max_tokens=max_tokens,
        )

    raise ValueError(
        f"不支援的 AI provider：'{provider}'，"
        "請使用 'claude'、'openai'、'gemini' 或 'openrouter'"
    )
