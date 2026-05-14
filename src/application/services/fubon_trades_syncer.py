"""
Fubon 今日成交記錄同步至 Google Sheets

流程：
1. 登入 Fubon SDK（與 FubonDownloadClient 相同驗證方式）
2. 呼叫 sdk.stock.get_order_results() 查詢今日所有委託
3. 篩選出 filled_qty > 0 的已成交委託
4. 透過 GoogleSheetsRecorder 寫入「交易記錄」頁籤
"""
import base64
import os
import tempfile
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from ...infrastructure.persistence.google_sheets_recorder import GoogleSheetsRecorder

logger = get_logger(__name__)


def _get_attr(obj: Any, *snake_keys: str, default: Any = 0) -> Any:
    """從 SDK 物件或 dict 取出欄位值，依序嘗試 snake_case key。"""
    if isinstance(obj, dict):
        for k in snake_keys:
            if k in obj:
                return obj[k]
    else:
        for k in snake_keys:
            if hasattr(obj, k):
                return getattr(obj, k)
    return default


class FubonTradesSyncer:
    """查詢 Fubon 今日成交委託並寫入 Google Sheets 交易記錄頁籤"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def sync(self) -> Dict[str, int]:
        """
        查詢今日成交記錄並逐筆寫入 Google Sheets。

        Returns:
            {'synced': int, 'skipped': int, 'errors': int}
        """
        from config.settings import settings

        filled_orders = self._fetch_filled_orders(settings.fubon)
        self.logger.info(f"今日已成交委託：{len(filled_orders)} 筆")

        if not filled_orders:
            return {'synced': 0, 'skipped': 0, 'errors': 0}

        recorder = GoogleSheetsRecorder()

        if not recorder.is_available():
            self.logger.warning("Google Sheets 未設定，略過寫入")
            return {'synced': 0, 'skipped': len(filled_orders), 'errors': 0}

        synced = errors = 0
        for order in filled_orders:
            try:
                symbol      = _get_attr(order, 'symbol', 'stock_no', default='')
                buy_sell    = str(_get_attr(order, 'buy_sell', 'buy_sell_type', default=''))
                filled_qty  = int(_get_attr(order, 'filled_qty', 'filled_quantity', default=0))
                filled_money = float(_get_attr(order, 'filled_money', 'filled_amount', default=0))
                order_no    = _get_attr(order, 'order_no', 'order_number', default='')
                self.logger.debug(f"[order-raw] symbol={symbol!r} buy_sell={buy_sell!r} qty={filled_qty} money={filled_money}")

                # 計算每股均價
                filled_price = round(filled_money / filled_qty, 2) if filled_qty > 0 else 0.0

                # BSAction 轉中文
                action = '買入' if 'Buy' in buy_sell or buy_sell in ('B', 'Buy') else '賣出'

                ok = recorder.record_trade(
                    stock_code=symbol,
                    action=action,
                    price=filled_price,
                    quantity=filled_qty,
                    notes=f"Fubon委託 {order_no}",
                )
                if ok:
                    synced += 1
                    self.logger.info(f"已寫入：{symbol} {action} {filled_price}x{filled_qty}")
                else:
                    errors += 1
            except Exception as e:
                self.logger.error(f"寫入委託失敗（{order}）: {e}")
                errors += 1

        return {'synced': synced, 'skipped': 0, 'errors': errors}

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_filled_orders(self, fubon_cfg) -> List[Any]:
        """登入 Fubon、取今日委託，回傳 filled_qty > 0 的清單。"""
        sdk, accounts, cert_tmp = self._login(fubon_cfg)
        try:
            stock_account = self._get_stock_account(accounts)
            if stock_account is None:
                self.logger.error("找不到證券帳戶")
                return []

            result = sdk.stock.get_order_results(stock_account)
            if not result.is_success:
                self.logger.error(f"get_order_results 失敗：{result.message}")
                return []

            all_orders = result.data or []
            self.logger.info(f"今日委託合計：{len(all_orders)} 筆")
            if all_orders:
                first = all_orders[0]
                if isinstance(first, dict):
                    self.logger.debug(f"[order-keys] {list(first.keys())}")
                else:
                    self.logger.debug(f"[order-attrs] {[a for a in dir(first) if not a.startswith('_')]}")
            return [o for o in all_orders if int(_get_attr(o, 'filled_qty', default=0)) > 0]
        finally:
            self._logout(sdk, cert_tmp)

    def _login(self, fubon_cfg):
        """登入 Fubon SDK，回傳 (sdk, accounts_result, cert_tmpfile_path_or_None)。"""
        cert_path = fubon_cfg.cert_path
        cert_tmp: Optional[str] = None

        if not cert_path and fubon_cfg.cert_base64:
            tmp = tempfile.NamedTemporaryFile(suffix=".p12", delete=False)
            tmp.write(base64.b64decode(fubon_cfg.cert_base64))
            tmp.flush()
            tmp.close()
            cert_path = tmp.name
            cert_tmp = cert_path
            self.logger.debug(f"已解碼 FUBON_CERT_BASE64 至暫存檔：{cert_path}")

        try:
            from fubon_neo.sdk import FubonSDK
        except ImportError:
            raise RuntimeError(
                "fubon_neo SDK 未安裝，請至 https://www.fbs.com.tw/TradeAPI 下載並安裝。"
            )

        cert_password = fubon_cfg.cert_password or fubon_cfg.user_id

        sdk = FubonSDK()
        if fubon_cfg.api_key and fubon_cfg.user_id and cert_path:
            result = sdk.apikey_login(fubon_cfg.user_id, fubon_cfg.api_key, cert_path, cert_password)
            method = "API Key"
        elif fubon_cfg.user_id and fubon_cfg.password and cert_path:
            result = sdk.login(fubon_cfg.user_id, fubon_cfg.password, cert_path, cert_password)
            method = "Certificate"
        else:
            raise RuntimeError(
                "Fubon 驗證未設定，請設定 FUBON_USER_ID + FUBON_API_KEY + FUBON_CERT_PATH"
            )

        if not result.is_success:
            raise RuntimeError(f"Fubon 登入失敗（{method}）：{result.message}")

        sdk.init_realtime()
        self.logger.info(f"Fubon SDK 登入成功（{method}）")

        # 登入成功後即可刪除暫存憑證（已載入至 SDK 記憶體）
        if cert_tmp:
            try:
                os.unlink(cert_tmp)
                cert_tmp = None
            except OSError:
                pass

        return sdk, result, cert_tmp

    def _logout(self, sdk, cert_tmp: Optional[str]) -> None:
        try:
            if sdk and hasattr(sdk, 'logout'):
                sdk.logout()
                self.logger.info("Fubon SDK 已登出")
        except Exception as e:
            self.logger.warning(f"登出時發生錯誤：{e}")

        if cert_tmp:
            try:
                os.unlink(cert_tmp)
            except OSError:
                pass

    @staticmethod
    def _get_stock_account(accounts_result):
        """從登入結果取出證券帳戶，找不到時回傳第一個帳戶。"""
        data = getattr(accounts_result, 'data', None) or []
        for acc in data:
            if getattr(acc, 'account_type', None) == 'stock':
                return acc
        return data[0] if data else None
