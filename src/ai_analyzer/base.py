"""
AI 分析器抽象基底類別

所有共用邏輯（批次處理、Telegram 格式化、Prompt 建構）集中在此。
各 provider 只需實作 _analyze_batch()。
"""
import json
from abc import ABC, abstractmethod

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── 共用 JSON Schema（供各 provider 建構 tool/function calling 使用）──────
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "strong_buy": {
            "type": "array",
            "description": "強烈建議買入：技術面強、基本面支撐、建議積極布局",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string", "description": "中文理由，30字以內"},
                },
                "required": ["symbol", "name", "reason"],
            },
        },
        "buy": {
            "type": "array",
            "description": "建議買入：技術訊號有效，可考慮小量布局",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["symbol", "name", "reason"],
            },
        },
        "watch": {
            "type": "array",
            "description": "觀察：訊號偏弱或有風險因素，宜觀察後再決定",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["symbol", "name", "reason"],
            },
        },
        "avoid": {
            "type": "array",
            "description": "不建議：有明顯風險（處置股/注意股/RSI過高/訊號可疑），不建議操作",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["symbol", "name", "reason"],
            },
        },
    },
    "required": ["strong_buy", "buy", "watch", "avoid"],
}

SYSTEM_PROMPT = """你是一位資深台灣股市技術分析師，專長在判讀技術指標訊號品質。
你收到的是已通過 P1 量化策略初步篩選的股票清單，清單中每支股票都具備有效的技術訊號。
你的任務是針對每支股票的訊號強度與風險因素，進行第二層分析與分級。

分級標準：
- strong_buy：多個訊號共振、RSI 在 50-65 健康區間、無異常標記、產業族群強勢
- buy：單一訊號有效、RSI 合理、無明顯風險
- watch：訊號強度偏弱、RSI 偏高（>70）偏低（<50）、或產業趨勢不明
- avoid：標記為「處置股」或「注意股」、RSI 極端值、訊號名稱含有可疑字眼

請務必將所有輸入的股票都分配到四個類別之一，不得遺漏。
每支股票的理由限 30 字以內，使用繁體中文。"""

EMPTY_RESULT: dict = {"strong_buy": [], "buy": [], "watch": [], "avoid": []}


class BaseAIAnalyzer(ABC):
    """AI 分析器基底類別，子類別只需實作 _analyze_batch()"""

    # 子類別可覆寫預設模型名稱
    DEFAULT_MODEL: str = ""

    def analyze_signals(
        self, signals_result: dict, max_stocks_per_batch: int = 50
    ) -> dict:
        """分析訊號結果並回傳重新分級後的結果

        將 buy + watch 合併後分批傳給 AI，結果合併回傳。

        Returns:
            {"strong_buy": [...], "buy": [...], "watch": [...], "avoid": [...], "target_date": ...}
        """
        all_stocks = signals_result.get("buy", [])

        if not all_stocks:
            return {**EMPTY_RESULT, "target_date": signals_result.get("target_date")}

        batches = [
            all_stocks[i : i + max_stocks_per_batch]
            for i in range(0, len(all_stocks), max_stocks_per_batch)
        ]

        combined: dict[str, list] = {k: [] for k in EMPTY_RESULT}
        for batch in batches:
            batch_result = self._analyze_batch(batch)
            for key in combined:
                combined[key].extend(batch_result.get(key, []))

        combined["target_date"] = signals_result.get("target_date")
        return combined

    @abstractmethod
    def _analyze_batch(self, stocks: list[dict]) -> dict:
        """對一批股票呼叫 AI API，回傳分類結果。子類別實作。"""

    def format_for_telegram(self, result: dict) -> list[str]:
        """將分析結果格式化為手機友善的 Telegram 訊息（自動切分）"""
        target_date = result.get("target_date", "")
        strong_buy = result.get("strong_buy", [])
        buy = result.get("buy", [])
        watch = result.get("watch", [])
        avoid = result.get("avoid", [])

        lines = [f"🤖 AI 二次過濾分析 {target_date}\n"]

        sections = [
            ("🔥 強烈建議買入", strong_buy),
            ("✅ 建議買入", buy),
            ("👀 觀察", watch),
            ("⛔ 不建議", avoid),
        ]
        for title, stocks in sections:
            if not stocks:
                continue
            lines.append(f"{title} ({len(stocks)} 支)")
            for s in stocks:
                symbol = _short_symbol(s.get("symbol", ""))
                name = s.get("name", "")
                note = s.get("note", "")
                note_tag = f" ⚠️{note}" if note else ""
                reason = s.get("reason", "")
                lines.append(f"{symbol} {name}{note_tag}")
                if reason:
                    lines.append(f"└ {reason}")
            lines.append("")

        total = len(strong_buy) + len(buy) + len(watch) + len(avoid)
        lines.append(
            f"共分析 {total} 支"
            f"（強買{len(strong_buy)} 買{len(buy)} 觀察{len(watch)} 不建議{len(avoid)}）"
        )

        return _split_into_chunks("\n".join(lines))

    def _build_user_message(self, stocks: list[dict]) -> str:
        """建構傳給 AI 的 user message"""
        simplified = [
            {
                "symbol": s.get("symbol", ""),
                "name": s.get("name", ""),
                "signal": s.get("signal", ""),
                "price": s.get("price"),
                "rsi": s.get("rsi"),
                "sector": s.get("sector", ""),
                "revenue_yoy_pct": s.get("revenue_yoy_pct"),
                "note": s.get("note", ""),
            }
            for s in stocks
        ]
        return (
            f"以下是今日透過 P1 技術策略篩選出的 {len(simplified)} 支股票，"
            "請將每支股票分配到對應分類。\n\n"
            f"股票清單（JSON）：\n{json.dumps(simplified, ensure_ascii=False, indent=2)}"
        )


# ── 共用工具函式 ──────────────────────────────────────────────────────────────

def _short_symbol(symbol: str) -> str:
    """將 '2330.TW' 轉為 '2330'"""
    return symbol.split(".")[0] if "." in symbol else symbol


def _split_into_chunks(text: str, max_length: int = 4096) -> list[str]:
    """將長文字按行切割為不超過 max_length 的多則訊息"""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in text.split("\n"):
        needed = len(line) + 1
        if current_lines and current_len + needed > max_length:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_len = 0
        current_lines.append(line)
        current_len += needed

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks
