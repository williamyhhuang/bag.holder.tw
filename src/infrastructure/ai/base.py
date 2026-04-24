"""
Infrastructure AI base - re-exports from ai_analyzer for backward compatibility
"""
from ...ai_analyzer.base import BaseAIAnalyzer, RESULT_SCHEMA, SYSTEM_PROMPT, EMPTY_RESULT

__all__ = ["BaseAIAnalyzer", "RESULT_SCHEMA", "SYSTEM_PROMPT", "EMPTY_RESULT"]
