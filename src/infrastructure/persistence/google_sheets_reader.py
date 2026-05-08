"""
Google Sheets trade reader — reads existing records to determine open positions
and compute unrealized / realized P&L.
"""
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ...utils.logger import get_logger

logger = get_logger(__name__)


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
    entry_price: float
    entry_date: str
    quantity: int
    current_price: float        # fetched from yfinance
    unrealized_pnl: float       # (current_price - entry_price) * quantity
    pnl_pct: float              # percentage change


@dataclass
class RealizedTrade:
    stock_code: str
    stock_name: str
    entry_price: float
    exit_price: float
    exit_date: str
    quantity: int
    realized_pnl: float
    pnl_pct: float


@dataclass
class PnlSummary:
    unrealized: List[UnrealizedPosition] = field(default_factory=list)
    realized: List[RealizedTrade] = field(default_factory=list)
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    fetch_time: str = ""


class GoogleSheetsReader:
    """讀取 Google Sheets 交易紀錄，判斷未平倉持倉"""

    def __init__(self):
        self._worksheet = None

    def _get_worksheet(self):
        if self._worksheet is not None:
            return self._worksheet

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

        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(gs_cfg.spreadsheet_id)

        try:
            self._worksheet = spreadsheet.worksheet(gs_cfg.worksheet_name)
        except Exception:
            raise RuntimeError(
                f"找不到工作表 '{gs_cfg.worksheet_name}'，請先有交易記錄"
            )

        return self._worksheet

    def get_open_positions(self) -> List[HoldingRecord]:
        """
        讀取所有交易記錄，依 timestamp 升序排序後，取每支股票的最後一筆 action：
          - 最後一筆為 '買入' → 未平倉，回傳 HoldingRecord
          - 最後一筆為 '賣出' → 已平倉，略過

        Returns:
            List of HoldingRecord for open positions
        """
        try:
            ws = self._get_worksheet()
            records = ws.get_all_records()  # list of dicts, header row is excluded
        except Exception as e:
            logger.error(f"無法讀取 Google Sheets: {e}")
            return []

        if not records:
            logger.info("Google Sheets 無交易記錄")
            return []

        # Sort by timestamp ascending (ISO format sorts correctly as string)
        records_sorted = sorted(records, key=lambda r: str(r.get("timestamp", "")))

        # Track last action per stock_code
        last_record: dict[str, dict] = {}
        for r in records_sorted:
            code = str(r.get("stock_code", "")).strip()
            action = str(r.get("action", "")).strip()
            if code and action in ("買入", "賣出"):
                last_record[code] = r

        open_positions: List[HoldingRecord] = []
        for code, r in last_record.items():
            if str(r.get("action", "")).strip() == "買入":
                try:
                    entry_price = float(r.get("price", 0))
                    entry_date = str(r.get("date", "")).strip()
                    quantity = int(r.get("quantity", 0))
                    open_positions.append(
                        HoldingRecord(
                            stock_code=code,
                            entry_price=entry_price,
                            entry_date=entry_date,
                            quantity=quantity,
                        )
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"無法解析 {code} 的持倉資料: {e}")

        logger.info(f"找到 {len(open_positions)} 支未平倉持倉")
        return open_positions

    # ------------------------------------------------------------------
    # P&L helpers
    # ------------------------------------------------------------------

    def _fetch_current_prices(self, codes: List[str]) -> Dict[str, float]:
        """
        從 yfinance 批次取得最新股價。
        嘗試 .TW 後綴，若無資料再試 .TWO。

        Returns:
            dict of {stock_code: price}  (price=0.0 if unavailable)
        """
        if not codes:
            return {}

        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance 未安裝，無法取得即時股價")
            return {c: 0.0 for c in codes}

        prices: Dict[str, float] = {}
        tw_symbols = [f"{c}.TW" for c in codes]

        try:
            data = yf.download(
                tw_symbols,
                period="5d",
                progress=False,
                auto_adjust=True,
            )
            close = data.get("Close", data) if isinstance(data.columns, object) and "Close" in data.columns else data

            for code in codes:
                sym = f"{code}.TW"
                try:
                    if hasattr(close, 'columns') and sym in close.columns:
                        series = close[sym].dropna()
                    elif len(codes) == 1:
                        series = close.dropna()
                    else:
                        series = None

                    if series is not None and len(series) > 0:
                        prices[code] = float(series.iloc[-1])
                    else:
                        prices[code] = 0.0
                except Exception:
                    prices[code] = 0.0
        except Exception as e:
            logger.warning(f"yfinance 批次下載失敗: {e}")
            for code in codes:
                prices[code] = 0.0

        # Retry missing with .TWO suffix
        missing = [c for c, p in prices.items() if p == 0.0]
        if missing:
            two_symbols = [f"{c}.TWO" for c in missing]
            try:
                data2 = yf.download(
                    two_symbols,
                    period="5d",
                    progress=False,
                    auto_adjust=True,
                )
                close2 = data2.get("Close", data2) if "Close" in data2.columns else data2
                for code in missing:
                    sym = f"{code}.TWO"
                    try:
                        if hasattr(close2, 'columns') and sym in close2.columns:
                            series = close2[sym].dropna()
                        elif len(missing) == 1:
                            series = close2.dropna()
                        else:
                            series = None

                        if series is not None and len(series) > 0:
                            prices[code] = float(series.iloc[-1])
                    except Exception:
                        pass
            except Exception:
                pass

        return prices

    def get_pnl_summary(self) -> Optional[PnlSummary]:
        """
        計算未實現損益與已實現損益。

        未實現損益：最後一筆 action = '買入' 的持倉，以 yfinance 即時股價計算。
        已實現損益：使用 FIFO 配對，每筆賣出與最早買入配對計算損益。

        Returns:
            PnlSummary，或 None（無法讀取 Sheets）
        """
        try:
            ws = self._get_worksheet()
            raw_records = ws.get_all_records()
        except Exception as e:
            logger.error(f"無法讀取 Google Sheets: {e}")
            return None

        if not raw_records:
            return PnlSummary(
                fetch_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            )

        # Sort ascending by timestamp
        records_sorted = sorted(raw_records, key=lambda r: str(r.get("timestamp", "")))

        # Per-stock FIFO buy queue: deque of (price, quantity, date, stock_name)
        buy_queues: Dict[str, deque] = defaultdict(deque)
        realized_trades: List[RealizedTrade] = []
        # Track last seen stock_name per code (may be empty string)
        stock_names: Dict[str, str] = {}

        for r in records_sorted:
            code = str(r.get("stock_code", "")).strip()
            action = str(r.get("action", "")).strip()
            if not code or action not in ("買入", "賣出"):
                continue

            name = str(r.get("stock_name", "")).strip()
            if name:
                stock_names[code] = name

            try:
                price = float(r.get("price", 0))
                quantity = int(r.get("quantity", 0))
                date = str(r.get("date", "")).strip()
            except (ValueError, TypeError):
                continue

            if action == "買入":
                buy_queues[code].append((price, quantity, date))
            elif action == "賣出":
                # FIFO match against buy queue
                remaining_sell = quantity
                while remaining_sell > 0 and buy_queues[code]:
                    buy_price, buy_qty, buy_date = buy_queues[code][0]
                    matched = min(remaining_sell, buy_qty)

                    pnl = (price - buy_price) * matched
                    pnl_pct = ((price - buy_price) / buy_price * 100) if buy_price else 0.0

                    realized_trades.append(RealizedTrade(
                        stock_code=code,
                        stock_name=stock_names.get(code, ""),
                        entry_price=buy_price,
                        exit_price=price,
                        exit_date=date,
                        quantity=matched,
                        realized_pnl=round(pnl, 2),
                        pnl_pct=round(pnl_pct, 2),
                    ))

                    remaining_sell -= matched
                    if matched == buy_qty:
                        buy_queues[code].popleft()
                    else:
                        buy_queues[code][0] = (buy_price, buy_qty - matched, buy_date)

        # Remaining buy queues → open (unrealized) positions
        open_codes = [c for c, q in buy_queues.items() if q]
        current_prices = self._fetch_current_prices(open_codes)

        unrealized_positions: List[UnrealizedPosition] = []
        for code, queue in buy_queues.items():
            if not queue:
                continue
            # Use VWAP of remaining lots as effective entry
            total_qty = sum(qty for _, qty, _ in queue)
            if total_qty == 0:
                continue
            vwap = sum(p * qty for p, qty, _ in queue) / total_qty
            earliest_date = queue[0][2]

            current_price = current_prices.get(code, 0.0)
            if current_price > 0:
                pnl = (current_price - vwap) * total_qty
                pnl_pct = (current_price - vwap) / vwap * 100 if vwap else 0.0
            else:
                pnl = 0.0
                pnl_pct = 0.0

            unrealized_positions.append(UnrealizedPosition(
                stock_code=code,
                stock_name=stock_names.get(code, ""),
                entry_price=round(vwap, 2),
                entry_date=earliest_date,
                quantity=total_qty,
                current_price=round(current_price, 2),
                unrealized_pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
            ))

        # Sort: unrealized by pnl desc, realized by exit_date desc
        unrealized_positions.sort(key=lambda x: x.unrealized_pnl, reverse=True)
        realized_trades.sort(key=lambda x: x.exit_date, reverse=True)

        total_unrealized = sum(p.unrealized_pnl for p in unrealized_positions)
        total_realized = sum(t.realized_pnl for t in realized_trades)

        return PnlSummary(
            unrealized=unrealized_positions,
            realized=realized_trades,
            total_unrealized_pnl=round(total_unrealized, 2),
            total_realized_pnl=round(total_realized, 2),
            fetch_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
