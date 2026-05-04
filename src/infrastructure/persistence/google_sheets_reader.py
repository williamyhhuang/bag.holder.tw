"""
Google Sheets trade reader — reads existing records to determine open positions.
"""
import json
from dataclasses import dataclass
from typing import List

from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class HoldingRecord:
    stock_code: str   # e.g. '2330' (no .TW/.TWO suffix)
    entry_price: float
    entry_date: str   # YYYY-MM-DD
    quantity: int


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
