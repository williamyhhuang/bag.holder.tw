#!/usr/bin/env python3
"""
富邦 e01 期貨 API 測試腳本

使用方式：
    source venv/bin/activate
    python scripts/test_fubon_futures.py --user-id A123456789 --cert-password A123456789

或設定 .env 後直接執行：
    python scripts/test_fubon_futures.py
"""
import asyncio
import sys
import os
import argparse
from pathlib import Path
from decimal import Decimal

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.fubon_client import FubonClient, FubonAPIError, get_near_month_symbol

# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description='富邦期貨 API 測試')
    p.add_argument('--user-id', help='身分證字號（覆蓋 FUBON_USER_ID）')
    p.add_argument('--cert-password', help='憑證密碼，預設與身分證字號相同')
    p.add_argument('--api-key', help='API Key（覆蓋 FUBON_API_KEY）')
    p.add_argument('--cert-path', help='憑證 .p12 路徑（覆蓋 FUBON_CERT_PATH）')
    p.add_argument('--no-trade', action='store_true', help='跳過下單測試（只查詢）')
    return p.parse_args()


async def test_connection(client: FubonClient):
    """測試登入連線"""
    print("\n[1/5] 測試登入連線...")
    print(f"  ✓ 登入成功")
    if client.accounts and client.accounts.data:
        for acc in client.accounts.data:
            acc_type = getattr(acc, 'account_type', 'unknown')
            acc_no = getattr(acc, 'account', '?')
            name = getattr(acc, 'name', '?')
            print(f"  帳號: {name} / {acc_no} (類型: {acc_type})")


async def test_near_month_symbol():
    """測試近月合約代號計算"""
    print("\n[2/5] 計算近月合約代號...")
    for product in ['TXF', 'MXF', 'MTX']:
        symbol = get_near_month_symbol(product)
        print(f"  {product} 近月合約: {symbol}")


async def test_futures_tickers(client: FubonClient):
    """測試期貨商品清單查詢"""
    print("\n[3/5] 查詢期貨商品清單 (TXF)...")
    try:
        tickers = await client.get_futures_tickers(product='TXF')
        if tickers:
            print(f"  查詢到 {len(tickers)} 個 TXF 合約")
            for t in tickers[:3]:
                print(f"  - {t['symbol']} ({t['name']}) 結算日: {t.get('settlement_date', '')}")
        else:
            print("  ⚠ 無合約資料（可能非交易時段或帳號無期貨權限）")
    except FubonAPIError as e:
        print(f"  ✗ 查詢失敗: {e}")


async def test_futures_quote(client: FubonClient):
    """測試期貨即時報價"""
    print("\n[4/5] 查詢期貨即時報價...")
    products = [('TXF', '大台'), ('MXF', '小台'), ('MTX', '微台')]

    for product, name in products:
        symbol = get_near_month_symbol(product)
        print(f"  查詢 {name} ({symbol})...")
        try:
            quote = await client.get_futures_quote(symbol)
            if quote:
                print(f"    成交價: {quote.get('last_price', quote.get('close_price', 'N/A'))}")
                print(f"    漲跌: {quote.get('change', 'N/A')} ({quote.get('change_percent', 'N/A')}%)")
                print(f"    成交量: {quote.get('volume', 'N/A')} 口")
                print(f"    最高/最低: {quote.get('high_price', 'N/A')} / {quote.get('low_price', 'N/A')}")
            else:
                print(f"    ⚠ 無報價資料（可能非交易時段）")
        except FubonAPIError as e:
            print(f"    ✗ 查詢失敗: {e}")


async def test_futures_positions(client: FubonClient):
    """測試期貨部位查詢"""
    print("\n[5/5] 查詢期貨部位...")
    try:
        acc = client.get_futopt_account()
        if acc is None:
            print("  ⚠ 無期貨帳號")
            return

        positions = await client.get_futures_positions(acc)
        if positions:
            print(f"  目前部位 {len(positions)} 筆:")
            for pos in positions:
                print(f"  - {pos['symbol']} {pos['buy_sell']} {pos['orig_lots']} 口 "
                      f"@{pos['price']} 損益:{pos['profit_or_loss']:.0f}")
        else:
            print("  無未平倉部位")

        equity = await client.get_futures_margin_equity(acc)
        if equity:
            print(f"\n  帳戶權益:")
            print(f"  - 今日餘額:   {equity['today_balance']:,.0f} {equity['currency']}")
            print(f"  - 今日權益:   {equity['today_equity']:,.0f}")
            print(f"  - 原始保證金: {equity['initial_margin']:,.0f}")
            print(f"  - 可動用保證金: {equity['available_margin']:,.0f}")
            print(f"  - 風險指標:   {equity['risk_index']:.2f}%")
            print(f"  - 未平倉損益: {equity['fut_unrealized_pnl']:,.0f}")
        else:
            print("  ⚠ 無法取得帳戶權益")

    except FubonAPIError as e:
        print(f"  ✗ 查詢失敗: {e}")


async def test_place_order(client: FubonClient):
    """測試期貨下單（下跌停限價委託，幾乎不會成交，安全測試用）"""
    print("\n[OPTIONAL] 期貨下單測試（跌停限價，測試用）...")
    symbol = get_near_month_symbol('MXF')  # 用小台測試
    print(f"  使用商品: {symbol} (小台)")

    try:
        acc = client.get_futopt_account()
        if acc is None:
            print("  ✗ 無期貨帳號，跳過")
            return

        # 先查報價取得跌停價
        quote = await client.get_futures_quote(symbol)
        if not quote:
            print("  ⚠ 無法取得報價，跳過下單測試")
            return

        last_price = float(quote.get('last_price') or quote.get('close_price') or 0)
        if last_price <= 0:
            print("  ⚠ 無有效報價，跳過")
            return

        # 設定一個很低的跌停限價（不太可能成交）
        test_price = str(int(last_price * 0.85))  # 85% 跌停測試
        print(f"  最新價: {last_price}, 測試限價: {test_price}")

        confirm = input(f"  確認要送出測試委託 (MXF買1口@{test_price})? [y/N] ").strip().lower()
        if confirm != 'y':
            print("  跳過下單測試")
            return

        result = await client.place_futures_order(
            symbol=symbol,
            buy_sell='Buy',
            price=test_price,
            lot=1,
            price_type='Limit',
            time_in_force='ROD',
            order_type='Auto',
            account=acc
        )
        print(f"  ✓ 委託送出: 委託書號={result.get('order_no')}, 狀態={result.get('status')}")

        # 立即取消
        order_no = result.get('order_no')
        if order_no:
            await asyncio.sleep(1)
            cancel = await client.cancel_futures_order(order_no, acc)
            print(f"  ✓ 撤單: {cancel}")

    except FubonAPIError as e:
        print(f"  ✗ 下單失敗: {e}")
    except KeyboardInterrupt:
        print("  取消")


async def main():
    args = parse_args()

    # Load env
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')

    user_id = args.user_id or os.environ.get('FUBON_USER_ID', '')
    api_key = args.api_key or os.environ.get('FUBON_API_KEY', '')
    cert_path = args.cert_path or os.environ.get('FUBON_CERT_PATH', '')
    cert_password = args.cert_password or os.environ.get('FUBON_CERT_PASSWORD', '') or user_id

    if not user_id:
        print("錯誤：請設定 FUBON_USER_ID 或使用 --user-id 參數")
        print("範例: python scripts/test_fubon_futures.py --user-id A123456789")
        sys.exit(1)

    if not cert_path or not Path(cert_path).exists():
        print(f"錯誤：找不到憑證檔 {cert_path}")
        print("請確認 FUBON_CERT_PATH 設定正確")
        sys.exit(1)

    if not api_key:
        print("錯誤：請設定 FUBON_API_KEY")
        sys.exit(1)

    print("=" * 60)
    print("富邦 e01 期貨 API 測試")
    print("=" * 60)
    print(f"身分證字號: {user_id[:3]}****{user_id[-2:]}")
    print(f"API Key: {api_key[:8]}...")
    print(f"憑證路徑: {cert_path}")
    print(f"憑證密碼: {'(同身分證)' if cert_password == user_id else '(自訂)'}")

    # Run tests
    async with FubonClient(
        user_id=user_id,
        api_key=api_key,
        cert_path=cert_path,
        cert_password=cert_password,
        is_simulation=False,
    ) as client:
        await test_connection(client)
        await test_near_month_symbol()
        await test_futures_tickers(client)
        await test_futures_quote(client)
        await test_futures_positions(client)

        if not args.no_trade:
            await test_place_order(client)

    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
