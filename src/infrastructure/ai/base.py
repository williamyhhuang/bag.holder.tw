"""
AI 分析器抽象基底類別

所有共用邏輯（批次處理、Telegram 格式化、Prompt 建構）集中在此。
各 provider 只需實作 _analyze_batch() 與 _analyze_holdings_batch()。
"""
import json
from abc import ABC, abstractmethod

from ...utils.logger import get_logger

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

SYSTEM_PROMPT = """你是一位資深台灣股市分析師，兼具技術面與基本面判讀能力。
你收到的是已通過 P1 量化策略初步篩選的股票清單，清單中每支股票都具備有效的技術訊號。
你的任務是針對每支股票的訊號強度、財務健全度與產業競爭地位，進行第二層分析與分級。

分級標準：
- strong_buy：多個訊號共振、RSI 在 50-65 健康區間、無異常標記、財務穩健（獲利成長或低負債）、在產業族群中具明顯競爭優勢
- buy：單一訊號有效、RSI 合理、財務無重大疑慮、無明顯風險
- watch：訊號強度偏弱、RSI 偏高（>70）或偏低（<50）、財務表現平淡、或產業趨勢不明
- avoid：標記為「處置股」或「注意股」、RSI 極端值、財務疑慮（虧損/高負債）、訊號名稱含有可疑字眼

分析時請額外考量：
1. 財務健全度：結合月營收年增率（revenue_yoy_pct）評估公司獲利動能與財務狀況
2. 產業族群優勢：比較同 sector 個股，點出該公司在族群中的相對強弱勢
3. 由虧轉盈跡象：根據你的訓練知識，判斷該公司近期是否有由虧轉盈的跡象（如財報轉正、營收連續成長、業外收益改善、或媒體/法說會釋出正面展望），若有則應提升分級或在理由中特別標注

請務必將所有輸入的股票都分配到四個類別之一，不得遺漏。
每支股票的理由限 100 字以內，使用繁體中文。"""

EMPTY_RESULT: dict = {"strong_buy": [], "buy": [], "watch": [], "avoid": []}

# ── 持倉賣出決策（Sell Analysis）─────────────────────────────────────────────

_SELL_ITEM = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "name": {"type": "string"},
        "reason": {"type": "string", "description": "中文理由，50字以內"},
    },
    "required": ["symbol", "name", "reason"],
}

SELL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "sell": {
            "type": "array",
            "description": "確認賣出：技術訊號明確（MACD Death Cross/Death Cross）且財務/族群惡化，建議立即出場",
            "items": _SELL_ITEM,
        },
        "watch": {
            "type": "array",
            "description": "設停損觀察：軟性訊號（如 RSI Momentum Loss）或財務/族群尚可，設好停損繼續觀察",
            "items": _SELL_ITEM,
        },
        "hold": {
            "type": "array",
            "description": "繼續持有：族群仍強、財報良好，訊號可能是假突破，不急出場",
            "items": _SELL_ITEM,
        },
    },
    "required": ["sell", "watch", "hold"],
}

SELL_SYSTEM_PROMPT = """你是資深台灣股市風控分析師，擅長判斷持倉出場時機。
你收到的是持倉中已觸發 P1 賣出訊號的股票，請結合以下維度做出出場判斷：
- 技術面：訊號類型（MACD Death Cross 最嚴重 > Death Cross > RSI Momentum Loss）、RSI 水準
- 基本面：月營收年增率（revenue_yoy_pct），正值代表成長、負值代表衰退
- 族群趨勢：sector_is_strong，true 代表族群仍強
- 持倉狀況：pnl_pct（獲利/虧損百分比）、holding_days（持有天數）

分類標準：
- sell：訊號強烈（MACD Death Cross 或 Death Cross）且族群轉弱或財報衰退，建議立即出場
- watch：RSI Momentum Loss 等軟性訊號，或財務/族群仍可，建議設停損繼續觀察
- hold：訊號偏弱且族群仍強、財報成長，可能是假突破，不急出場

全部輸入股票必須分配到三類之一，不得遺漏。理由限 50 字以內，使用繁體中文。"""

EMPTY_SELL_RESULT: dict = {"sell": [], "watch": [], "hold": []}


class BaseAIAnalyzer(ABC):
    """AI 分析器基底類別，子類別只需實作 _analyze_batch()"""

    # 子類別可覆寫預設模型名稱
    DEFAULT_MODEL: str = ""

    @property
    def model(self) -> str:
        """回傳實際使用的模型名稱（子類別以 self._model 儲存）"""
        return getattr(self, "_model", self.DEFAULT_MODEL)

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

    # ── 持倉賣出決策 ──────────────────────────────────────────────────────────

    def analyze_holdings(self, holdings: list[dict], max_per_batch: int = 30) -> dict:
        """
        批次分析持倉賣出決策。

        Args:
            holdings: 含賣出訊號的持倉清單，每筆包含
                      symbol, name, signal, price, rsi, entry_price,
                      pnl_pct, holding_days, sector_is_strong, revenue_yoy_pct
        Returns:
            {"sell": [...], "watch": [...], "hold": [...]}
        """
        if not holdings:
            return dict(EMPTY_SELL_RESULT)

        batches = [
            holdings[i : i + max_per_batch]
            for i in range(0, len(holdings), max_per_batch)
        ]
        combined: dict[str, list] = {k: [] for k in EMPTY_SELL_RESULT}
        for batch in batches:
            batch_result = self._analyze_holdings_batch(batch)
            for key in combined:
                combined[key].extend(batch_result.get(key, []))
        return combined

    def _analyze_holdings_batch(self, stocks: list[dict]) -> dict:
        """對一批持倉股票呼叫 AI API 做出場決策，子類別覆寫。
        使用 SELL_SYSTEM_PROMPT + SELL_RESULT_SCHEMA。
        預設實作拋出 NotImplementedError。
        """
        raise NotImplementedError("子類別需實作 _analyze_holdings_batch()")

    def _build_holdings_message(self, stocks: list[dict]) -> str:
        """建構傳給 AI 的持倉分析 user message"""
        simplified = [
            {
                "symbol": s.get("symbol", ""),
                "name": s.get("name", ""),
                "signal": s.get("signal", ""),
                "price": s.get("price"),
                "rsi": s.get("rsi"),
                "entry_price": s.get("entry_price"),
                "pnl_pct": round(s["pnl_pct"], 2) if s.get("pnl_pct") is not None else None,
                "holding_days": s.get("holding_days"),
                "sector": s.get("sector", ""),
                "sector_is_strong": s.get("sector_is_strong"),
                "revenue_yoy_pct": s.get("revenue_yoy_pct"),
            }
            for s in stocks
        ]
        return (
            f"以下是持倉中已觸發 P1 賣出訊號的 {len(simplified)} 支股票，"
            "請結合技術面、基本面與族群趨勢，判斷是否應出場。\n\n"
            f"股票清單（JSON）：\n{json.dumps(simplified, ensure_ascii=False, indent=2)}"
        )

    def format_holdings_for_telegram(self, result: dict, target_date=None) -> list[str]:
        """格式化持倉 AI 分析結果為 Telegram 訊息"""
        sell = result.get("sell", [])
        watch = result.get("watch", [])
        hold = result.get("hold", [])
        model_tag = f" ({self.model})" if self.model else ""
        date_str = f" {target_date}" if target_date else ""
        lines = [f"🤖 AI 持倉分析{model_tag}{date_str}\n"]

        sections = [
            ("🔴 建議出場", sell),
            ("👀 設停損觀察", watch),
            ("✅ 繼續持有", hold),
        ]
        for title, stocks in sections:
            if not stocks:
                continue
            lines.append(f"{title} ({len(stocks)} 支)")
            for s in stocks:
                symbol = _short_symbol(s.get("symbol", ""))
                name = s.get("name", "")
                reason = s.get("reason", "")
                lines.append(f"【{symbol} {name}】")
                if reason:
                    lines.append(f"└ {reason}")
                lines.append("")

        total = len(sell) + len(watch) + len(hold)
        lines.append(
            f"共分析 {total} 支"
            f"（出場{len(sell)} 觀察{len(watch)} 持有{len(hold)}）"
        )
        return _split_into_chunks("\n".join(lines))

    def format_for_telegram(self, result: dict) -> list[str]:
        """將分析結果格式化為手機友善的 Telegram 訊息（自動切分）"""
        target_date = result.get("target_date", "")
        strong_buy = result.get("strong_buy", [])
        buy = result.get("buy", [])
        watch = result.get("watch", [])
        avoid = result.get("avoid", [])

        model_tag = f" ({self.model})" if self.model else ""
        lines = [f"🤖 AI 二次過濾分析{model_tag} {target_date}\n"]

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
                lines.append(f"【{symbol} {name}】{note_tag}")
                if reason:
                    lines.append(f"└ {reason}")
                if s.get("entry_low") and s.get("entry_high") and s.get("stop_loss"):
                    lines.append(f"📌 {s['entry_low']:.1f}–{s['entry_high']:.1f}  🛑 {s['stop_loss']:.1f}")
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
                "entry_range": f"{s['entry_low']:.1f}–{s['entry_high']:.1f}" if s.get("entry_low") else None,
                "stop_loss": s.get("stop_loss"),
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
