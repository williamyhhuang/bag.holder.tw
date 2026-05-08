"""
Google Sheets trade reader.

Reads three worksheets managed by the 台股套牢指南 spreadsheet:
  - 交易記錄     : raw trade log  → open positions (for holdings checker)
  - 未實現損益   : Apps-Script computed unrealized P&L with live prices
  - 已實現損益   : Apps-Script computed realized P&L from trade history
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass
class HoldingRecord:
    stock_code: str   # e.g. '2330' (no .TW/.TWO suffix)
    entry_price: float
    entry_date: str   # YYYY-MM-DD
    quantity: int


@dataclass
class UnrealizedPosition:
    stock_code: str
    stock_name: str
    entry_price: float      # 平均成本
    entry_date: str         # not available from this sheet; kept for compat
    quantity: int
    current_price: float    # 即時股價 (from Apps Script)
    unrealized_pnl: float   # 未實現損益(元)
    pnl_pct: float          # 報酬率 (%)


@dataclass
class RealizedTrade:
    stock_code: str
    stock_name: str
    entry_price: float      # 買入均價
    exit_price: float       # 賣出均價
    exit_date: str          # 出場日期
    quantity: int           # 賣出股數
    realized_pnl: float     # 已實現損益(元)
    pnl_pct: float          # 報酬率 (%)


@dataclass
class PnlSummary:
    unrealized: List[UnrealizedPosition] = field(default_factory=list)
    realized: List[RealizedTrade] = field(default_factory=list)
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    fetch_time: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pct(val) -> float:
    """
    Parse a percentage value from Google Sheets.
    Handles both formatted strings ('32.74%') and raw decimals (0.3274).
    Returns the value as a plain percentage float (e.g. 32.74).
    """
    if isinstance(val, str):
        cleaned = val.strip().rstrip('%')
        return float(cleaned) if cleaned else 0.0
    # Sheets stores percentages internally as decimals (0.3274 → 32.74%)
    return round(float(val) * 100, 2)


def _parse_num(val, default: float = 0.0) -> float:
    """Parse a number that may be formatted with thousands commas or be empty."""
    if val is None or val == '':
        return default
    if isinstance(val, (int, float)):
        return float(val)
    return float(str(val).replace(',', ''))


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class GoogleSheetsReader:
    """讀取 Google Sheets 三個工作表的損益資料"""

    def __init__(self):
        self._client = None
        self._spreadsheet = None
        # Cached worksheet handles
        self._trade_ws = None
        self._unrealized_ws = None
        self._realized_ws = None

    # ------------------------------------------------------------------
    # Internal: credential + connection setup
    # ------------------------------------------------------------------

    def _connect(self):
        """Lazy-init: authenticate and open the spreadsheet."""
        if self._spreadsheet is not None:
            return

        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError:
            raise ImportError(
                "gspread / google-auth 未安裝，請執行: pip install gspread google-auth"
            )

        from config.settings import settings
        gs_cfg = settings.google_sheets

        if not gs_cfg.enabled:
            raise RuntimeError("Google Sheets 未啟用，請設定 GOOGLE_SHEETS_ENABLED=true")
        if not gs_cfg.spreadsheet_id:
            raise RuntimeError("請設定 GOOGLE_SHEETS_SPREADSHEET_ID")

        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]

        if gs_cfg.credentials_json:
            cred_info = json.loads(gs_cfg.credentials_json)
            creds = Credentials.from_service_account_info(cred_info, scopes=scopes)
        elif gs_cfg.credentials_file:
            creds = Credentials.from_service_account_file(gs_cfg.credentials_file, scopes=scopes)
        else:
            raise RuntimeError(
                "請設定 GOOGLE_CREDENTIALS_JSON（JSON 字串）或 GOOGLE_CREDENTIALS_FILE（檔案路徑）"
            )

        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(gs_cfg.spreadsheet_id)

    def _get_worksheet(self, name: str):
        """Open a worksheet by name (from the cached spreadsheet connection)."""
        self._connect()
        try:
            return self._spreadsheet.worksheet(name)
        except Exception:
            raise RuntimeError(f"找不到工作表 '{name}'，請確認試算表內有此 tab")

    def _trade_worksheet(self):
        if self._trade_ws is None:
            from config.settings import settings
            self._trade_ws = self._get_worksheet(settings.google_sheets.worksheet_name)
        return self._trade_ws

    def _unrealized_worksheet(self):
        if self._unrealized_ws is None:
            from config.settings import settings
            self._unrealized_ws = self._get_worksheet(
                settings.google_sheets.unrealized_pnl_worksheet_name
            )
        return self._unrealized_ws

    def _realized_worksheet(self):
        if self._realized_ws is None:
            from config.settings import settings
            self._realized_ws = self._get_worksheet(
                settings.google_sheets.realized_pnl_worksheet_name
            )
        return self._realized_ws

    # ------------------------------------------------------------------
    # Public: open positions (for holdings checker, unchanged)
    # ------------------------------------------------------------------

    def get_open_positions(self) -> List[HoldingRecord]:
        """
        讀取交易記錄，依 timestamp 升序排序後，取每支股票的最後一筆 action：
          - 最後一筆為 '買入' → 未平倉，回傳 HoldingRecord
          - 最後一筆為 '賣出' → 已平倉，略過
        """
        try:
            ws = self._trade_worksheet()
            records = ws.get_all_records()
        except Exception as e:
            logger.error(f"無法讀取交易記錄工作表: {e}")
            return []

        if not records:
            logger.info("Google Sheets 無交易記錄")
            return []

        records_sorted = sorted(records, key=lambda r: str(r.get("timestamp", "")))

        last_record: Dict[str, dict] = {}
        for r in records_sorted:
            code = str(r.get("stock_code", "")).strip()
            action = str(r.get("action", "")).strip()
            if code and action in ("買入", "賣出"):
                last_record[code] = r

        open_positions: List[HoldingRecord] = []
        for code, r in last_record.items():
            if str(r.get("action", "")).strip() == "買入":
                try:
                    open_positions.append(HoldingRecord(
                        stock_code=code,
                        entry_price=float(r.get("price", 0)),
                        entry_date=str(r.get("date", "")).strip(),
                        quantity=int(r.get("quantity", 0)),
                    ))
                except (ValueError, TypeError) as e:
                    logger.warning(f"無法解析 {code} 的持倉資料: {e}")

        logger.info(f"找到 {len(open_positions)} 支未平倉持倉")
        return open_positions

    # ------------------------------------------------------------------
    # Public: P&L summary (reads dedicated P&L sheets directly)
    # ------------------------------------------------------------------

    def get_pnl_summary(self) -> Optional[PnlSummary]:
        """
        讀取「未實現損益」與「已實現損益」工作表（由 Apps Script 即時計算），
        組合成 PnlSummary。不呼叫任何外部 API。

        Returns:
            PnlSummary，或 None（無法讀取 Sheets）
        """
        unrealized = self._read_unrealized_sheet()
        realized = self._read_realized_sheet()

        if unrealized is None and realized is None:
            return None

        unrealized = unrealized or []
        realized = realized or []

        return PnlSummary(
            unrealized=unrealized,
            realized=realized,
            total_unrealized_pnl=round(sum(p.unrealized_pnl for p in unrealized), 2),
            total_realized_pnl=round(sum(t.realized_pnl for t in realized), 2),
            fetch_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def _read_unrealized_sheet(self) -> Optional[List[UnrealizedPosition]]:
        """
        讀取「未實現損益」工作表。
        欄位：股票代號, 股票名稱, 持倉股數, 平均成本(元), 即時股價, 未實現損益(元), 報酬率
        """
        try:
            ws = self._unrealized_worksheet()
            records = ws.get_all_records()
        except Exception as e:
            logger.error(f"無法讀取未實現損益工作表: {e}")
            return None

        positions: List[UnrealizedPosition] = []
        for r in records:
            code = str(r.get("股票代號", "")).strip()
            if not code:
                continue
            try:
                positions.append(UnrealizedPosition(
                    stock_code=code,
                    stock_name=str(r.get("股票名稱", "")).strip(),
                    entry_price=_parse_num(r.get("平均成本(元)", 0)),
                    entry_date="",
                    quantity=int(_parse_num(r.get("持倉股數", 0))),
                    current_price=_parse_num(r.get("即時股價", 0)),
                    unrealized_pnl=_parse_num(r.get("未實現損益(元)", 0)),
                    pnl_pct=_parse_pct(r.get("報酬率", 0)),
                ))
            except Exception as e:
                logger.warning(f"無法解析未實現損益列 {code}: {e}")

        logger.info(f"未實現損益：讀取 {len(positions)} 筆")
        return positions

    def _read_realized_sheet(self) -> Optional[List[RealizedTrade]]:
        """
        讀取「已實現損益」工作表。
        欄位：股票代號, 股票名稱, 賣出股數, 買入均價(元), 賣出均價(元),
              出場日期, 已實現損益(元), 報酬率
        """
        try:
            ws = self._realized_worksheet()
            records = ws.get_all_records()
        except Exception as e:
            logger.error(f"無法讀取已實現損益工作表: {e}")
            return None

        trades: List[RealizedTrade] = []
        for r in records:
            code = str(r.get("股票代號", "")).strip()
            if not code:
                continue
            try:
                trades.append(RealizedTrade(
                    stock_code=code,
                    stock_name=str(r.get("股票名稱", "")).strip(),
                    quantity=int(_parse_num(r.get("賣出股數", 0))),
                    entry_price=_parse_num(r.get("買入均價(元)", 0)),
                    exit_price=_parse_num(r.get("賣出均價(元)", 0)),
                    exit_date=str(r.get("出場日期", "")).strip(),
                    realized_pnl=_parse_num(r.get("已實現損益(元)", 0)),
                    pnl_pct=_parse_pct(r.get("報酬率", 0)),
                ))
            except Exception as e:
                logger.warning(f"無法解析已實現損益列 {code}: {e}")

        # 最新賣出排最前面
        trades.sort(key=lambda t: t.exit_date, reverse=True)
        logger.info(f"已實現損益：讀取 {len(trades)} 筆")
        return trades
