"""
Claude AI 二次過濾：對 P1 技術策略篩出的股票清單做進一步分析與分級
"""
import json
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

ANALYSIS_TOOL = {
    "name": "classify_stocks",
    "description": "將股票清單依據分析結果分類為四個等級",
    "input_schema": {
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
    },
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


class ClaudeAnalyzer:
    """使用 Claude API 對訊號清單進行二次過濾分析"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "需要安裝 anthropic 套件：pip install anthropic>=0.40.0"
            )
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def analyze_signals(
        self, signals_result: dict, max_stocks_per_batch: int = 50
    ) -> dict:
        """分析訊號結果並回傳 Claude 的分級結果

        Args:
            signals_result: SignalsScanner.scan_today() 的回傳值
            max_stocks_per_batch: 每批最多傳給 Claude 的股票數

        Returns:
            {
                "strong_buy": [...],
                "buy": [...],
                "watch": [...],
                "avoid": [...],
                "target_date": ...,
            }
        """
        buy_list = signals_result.get("buy", [])
        watch_list = signals_result.get("watch", [])

        # 合併 buy + watch 讓 Claude 重新分級
        all_stocks = buy_list + watch_list

        if not all_stocks:
            return {
                "strong_buy": [],
                "buy": [],
                "watch": [],
                "avoid": [],
                "target_date": signals_result.get("target_date"),
            }

        # 分批處理
        batches = [
            all_stocks[i : i + max_stocks_per_batch]
            for i in range(0, len(all_stocks), max_stocks_per_batch)
        ]

        combined: dict[str, list] = {
            "strong_buy": [],
            "buy": [],
            "watch": [],
            "avoid": [],
        }

        for batch in batches:
            batch_result = self._analyze_batch(batch)
            for key in combined:
                combined[key].extend(batch_result.get(key, []))

        combined["target_date"] = signals_result.get("target_date")
        return combined

    def _analyze_batch(self, stocks: list[dict]) -> dict:
        """對一批股票呼叫 Claude API"""
        # 只傳必要欄位，減少 token 用量
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

        user_message = (
            f"以下是今日透過 P1 技術策略篩選出的 {len(simplified)} 支股票，"
            "請依據分析結果，使用 classify_stocks 工具將每支股票分配到對應分類。\n\n"
            f"股票清單（JSON）：\n{json.dumps(simplified, ensure_ascii=False, indent=2)}"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[ANALYSIS_TOOL],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": user_message}],
            )

            # 取出 tool_use block
            for block in response.content:
                if block.type == "tool_use" and block.name == "classify_stocks":
                    return block.input

            logger.warning("Claude 未回傳 tool_use block，回傳空結果")
            return {"strong_buy": [], "buy": [], "watch": [], "avoid": []}

        except Exception as e:
            logger.error(f"Claude API 呼叫失敗: {e}")
            raise

    def format_for_telegram(self, claude_result: dict) -> list[str]:
        """將 Claude 分析結果格式化為手機友善的 Telegram 訊息

        格式範例：
        🤖 Claude AI 二次過濾分析

        🔥 強烈建議買入 (3 支)
        2330 台積電
        └ 三訊號共振，RSI 62 健康，半導體景氣回升

        ✅ 建議買入 (5 支)
        ...
        """
        target_date = claude_result.get("target_date", "")
        strong_buy = claude_result.get("strong_buy", [])
        buy = claude_result.get("buy", [])
        watch = claude_result.get("watch", [])
        avoid = claude_result.get("avoid", [])

        lines = [f"🤖 Claude AI 二次過濾分析 {target_date}\n"]

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
        lines.append(f"共分析 {total} 支（強買{len(strong_buy)} 買{len(buy)} 觀察{len(watch)} 不建議{len(avoid)}）")

        return _split_into_chunks("\n".join(lines))


def _short_symbol(symbol: str) -> str:
    """將 '2330.TW' 轉為 '2330'"""
    return symbol.split(".")[0] if "." in symbol else symbol


def _split_into_chunks(text: str, max_length: int = 4096) -> list[str]:
    """將長文字按行切割為不超過 max_length 的多則訊息"""
    if len(text) <= max_length:
        return [text]

    chunks = []
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
