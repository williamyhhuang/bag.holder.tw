"""
MTX 微台指模擬交易 Google Sheets 記錄器

當 MTX_LIVE_ORDER=False（預設）時，所有進出場動作寫入
Google Sheets「微台交易紀錄」頁籤，而不透過富邦 API 下單。

工作表欄位：
  timestamp | date | time | session | symbol | direction |
  action    | price | lots | pnl_pts | pnl_twd | reason | mode
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from ...utils.logger import get_logger

logger = get_logger(__name__)

# 每點台幣價值（微台指 1 點 = NT$10）
MTX_POINT_VALUE_TWD = 10

# 欄位定義（順序 = Google Sheets 欄位順序）
MTX_SHEET_HEADERS = [
    "timestamp",   # ISO 8601 timestamp (台北時間)
    "date",        # YYYY-MM-DD
    "time",        # HH:MM:SS
    "session",     # 日盤 | 夜盤
    "symbol",      # e.g. FIMTXE6
    "direction",   # LONG | SHORT
    "action",      # 進場 | 出場
    "price",       # 成交價（模擬）
    "lots",        # 口數
    "pnl_pts",     # 損益點數（出場才有值）
    "pnl_twd",     # 損益台幣（出場才有值）
    "reason",      # 進出場原因
    "mode",        # 模擬 | 實單
]

_TZ = ZoneInfo("Asia/Taipei")


class MTXSheetsRecorder:
    """
    將 MTX 模擬交易紀錄追加到 Google Sheets 工作表。

    工作表名稱由 ``settings.mtx_trader.sim_worksheet_name`` 決定
    （預設：「微台交易紀錄」）。

    同一個 spreadsheet 與股票交易記錄共用，保持一份試算表管理所有交易。
    """

    def __init__(self, worksheet_name: Optional[str] = None) -> None:
        self._ws_name = worksheet_name  # None → 從 settings 讀取
        self._client = None
        self._worksheet = None

    # ------------------------------------------------------------------
    # Internal: lazy worksheet initialisation

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

        ws_name = self._ws_name or settings.mtx_trader.sim_worksheet_name

        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]

        if gs_cfg.credentials_json:
            creds = Credentials.from_service_account_info(
                json.loads(gs_cfg.credentials_json), scopes=scopes
            )
        elif gs_cfg.credentials_file:
            creds = Credentials.from_service_account_file(
                gs_cfg.credentials_file, scopes=scopes
            )
        else:
            raise RuntimeError("請設定 GOOGLE_CREDENTIALS_JSON 或 GOOGLE_CREDENTIALS_FILE")

        self._client = gspread.authorize(creds)
        spreadsheet = self._client.open_by_key(gs_cfg.spreadsheet_id)

        try:
            self._worksheet = spreadsheet.worksheet(ws_name)
        except Exception:
            self._worksheet = spreadsheet.add_worksheet(
                title=ws_name, rows=2000, cols=len(MTX_SHEET_HEADERS)
            )
            self._worksheet.append_row(MTX_SHEET_HEADERS)
            logger.info(f"已建立工作表：{ws_name}")

        # 補標題（工作表存在但為空）
        existing = self._worksheet.get_all_values()
        if not existing:
            self._worksheet.append_row(MTX_SHEET_HEADERS)

        return self._worksheet

    # ------------------------------------------------------------------
    # Public API

    def record_open(
        self,
        symbol: str,
        direction: str,
        price: float,
        lots: int,
        reason: str,
        session: str,
    ) -> bool:
        """
        記錄「進場」事件。

        Parameters
        ----------
        symbol    : 合約代號，e.g. ``FIMTXE6``
        direction : ``'LONG'`` 或 ``'SHORT'``
        price     : 進場模擬成交價
        lots      : 口數
        reason    : 進場原因
        session   : ``'日盤'`` 或 ``'夜盤'``
        """
        return self._append_row(
            symbol=symbol,
            direction=direction,
            action="進場",
            price=price,
            lots=lots,
            pnl_pts=None,
            pnl_twd=None,
            reason=reason,
            session=session,
        )

    def record_close(
        self,
        symbol: str,
        direction: str,
        price: float,
        lots: int,
        pnl_pts: float,
        reason: str,
        session: str,
    ) -> bool:
        """
        記錄「出場」事件，含損益計算。

        Parameters
        ----------
        pnl_pts : 單口點數損益；台幣損益 = pnl_pts × lots × MTX_POINT_VALUE_TWD
        """
        pnl_twd = pnl_pts * lots * MTX_POINT_VALUE_TWD
        return self._append_row(
            symbol=symbol,
            direction=direction,
            action="出場",
            price=price,
            lots=lots,
            pnl_pts=round(pnl_pts, 1),
            pnl_twd=round(pnl_twd, 0),
            reason=reason,
            session=session,
        )

    # ------------------------------------------------------------------
    # Internal helpers

    def _append_row(
        self,
        symbol: str,
        direction: str,
        action: str,
        price: float,
        lots: int,
        pnl_pts: Optional[float],
        pnl_twd: Optional[float],
        reason: str,
        session: str,
    ) -> bool:
        try:
            ws = self._get_worksheet()
            now = datetime.now(_TZ)
            row = [
                now.isoformat(timespec="seconds"),   # timestamp
                now.strftime("%Y-%m-%d"),             # date
                now.strftime("%H:%M:%S"),             # time
                session,                              # session
                symbol,                               # symbol
                direction,                            # direction
                action,                               # action
                price,                                # price
                lots,                                 # lots
                "" if pnl_pts is None else pnl_pts,  # pnl_pts
                "" if pnl_twd is None else pnl_twd,  # pnl_twd
                reason,                               # reason
                "模擬",                               # mode
            ]
            ws.append_row(row, value_input_option="USER_ENTERED")
            logger.info(
                f"[模擬] Sheets 寫入 {action} {direction} {lots}口 @ {price:.0f}"
                + (f" PnL={pnl_pts:+.0f}pts" if pnl_pts is not None else "")
            )
            return True
        except Exception as exc:
            logger.error(f"MTX Sheets 寫入失敗：{exc}")
            return False

    def is_available(self) -> bool:
        """快速檢查 Google Sheets 設定是否完整（不實際連線）。"""
        try:
            from config.settings import settings
            gs = settings.google_sheets
            return bool(
                gs.enabled
                and gs.spreadsheet_id
                and (gs.credentials_json or gs.credentials_file)
            )
        except Exception:
            return False
