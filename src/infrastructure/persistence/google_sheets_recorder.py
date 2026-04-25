"""
Google Sheets trade recorder
"""
import json
from datetime import datetime
from typing import Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)

# 工作表欄位定義（順序即 Google Sheets 欄位順序）
SHEET_HEADERS = [
    "timestamp", "date", "time", "stock_code", "action",
    "price", "quantity", "amount", "notes"
]


class GoogleSheetsRecorder:
    """將交易記錄寫入 Google Sheets"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self._client = None
        self._worksheet = None

    def _get_worksheet(self):
        """取得或初始化 Google Sheets worksheet（lazy init）"""
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

        # 支援兩種憑證來源：JSON 字串 或 檔案路徑
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
        spreadsheet = self._client.open_by_key(gs_cfg.spreadsheet_id)

        # 取得或新建工作表
        try:
            self._worksheet = spreadsheet.worksheet(gs_cfg.worksheet_name)
        except Exception:
            self._worksheet = spreadsheet.add_worksheet(
                title=gs_cfg.worksheet_name, rows=1000, cols=len(SHEET_HEADERS)
            )
            # 寫入標題列
            self._worksheet.append_row(SHEET_HEADERS)
            self.logger.info(f"已建立工作表: {gs_cfg.worksheet_name}")

        # 若工作表為空則補標題
        existing = self._worksheet.get_all_values()
        if not existing:
            self._worksheet.append_row(SHEET_HEADERS)

        return self._worksheet

    def record_trade(
        self,
        stock_code: str,
        action: str,          # '買入' or '賣出'
        price: float,
        quantity: int = 1000,
        notes: Optional[str] = None,
    ) -> bool:
        """
        將一筆交易記錄追加到 Google Sheets

        Args:
            stock_code: 股票代號
            action: 操作方向（'買入' / '賣出'）
            price: 成交價格
            quantity: 股數（預設 1000 股 = 1 張）
            notes: 備註

        Returns:
            True if succeeded
        """
        try:
            ws = self._get_worksheet()
            now = datetime.now()
            amount = round(price * quantity, 2)

            row = [
                now.isoformat(timespec="seconds"),   # timestamp
                now.strftime("%Y-%m-%d"),             # date
                now.strftime("%H:%M:%S"),             # time
                stock_code,                           # stock_code
                action,                               # action
                price,                                # price
                quantity,                             # quantity
                amount,                               # amount
                notes or "",                          # notes
            ]

            ws.append_row(row, value_input_option="USER_ENTERED")
            self.logger.info(
                f"Google Sheets 記錄成功: {stock_code} {action} {price} x {quantity}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Google Sheets 寫入失敗: {e}")
            return False

    def is_available(self) -> bool:
        """檢查 Google Sheets 是否可用（設定完整且可連線）"""
        try:
            from config.settings import settings
            gs_cfg = settings.google_sheets
            return bool(
                gs_cfg.enabled
                and gs_cfg.spreadsheet_id
                and (gs_cfg.credentials_json or gs_cfg.credentials_file)
            )
        except Exception:
            return False
