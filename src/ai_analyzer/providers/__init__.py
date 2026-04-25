"""
ai_analyzer.providers - backward compatibility shim
"""
from src.infrastructure.ai.providers.claude import ClaudeAnalyzer
from src.infrastructure.ai.providers.openai import OpenAIAnalyzer
from src.infrastructure.ai.providers.gemini import GeminiAnalyzer
from src.infrastructure.ai.providers.openrouter import OpenRouterAnalyzer

__all__ = ["ClaudeAnalyzer", "OpenAIAnalyzer", "GeminiAnalyzer", "OpenRouterAnalyzer"]
