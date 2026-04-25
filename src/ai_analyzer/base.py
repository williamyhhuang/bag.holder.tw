"""
ai_analyzer.base - backward compatibility shim
"""
from src.infrastructure.ai.base import (
    BaseAIAnalyzer, RESULT_SCHEMA, SYSTEM_PROMPT, EMPTY_RESULT,
    _short_symbol, _split_into_chunks,
)

__all__ = [
    "BaseAIAnalyzer", "RESULT_SCHEMA", "SYSTEM_PROMPT", "EMPTY_RESULT",
    "_short_symbol", "_split_into_chunks",
]
