"""
下載 TAIFEX 期交所每筆成交 tick 資料（Daily_YYYY_MM_DD.zip）

從「前30個交易日期貨每筆成交資料」頁面取得可用清單，自動補下載本地缺少的檔案。

用法:
  python scripts/download_taifex_tick.py           # 補下載所有缺少的（最多近 30 個交易日）
  python scripts/download_taifex_tick.py --out data/taifex_tick
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests

PAGE_URL = "https://www.taifex.com.tw/cht/3/dlFutPrevious30DaysSalesData"
BASE_URL = "https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV"
DEFAULT_OUT = Path(__file__).parent.parent / "data" / "taifex_tick"
SLEEP_SEC = 1.5


def fetch_available(session: requests.Session) -> list[str]:
    """從 TAIFEX 頁面解析可下載的 zip 清單"""
    resp = session.get(PAGE_URL, timeout=15)
    resp.raise_for_status()
    return sorted(set(re.findall(r"Daily_\d{4}_\d{2}_\d{2}\.zip", resp.text)))


def download_one(fname: str, out_dir: Path, session: requests.Session) -> bool:
    dest = out_dir / fname
    if dest.exists():
        print(f"  [skip] {fname} 已存在")
        return False

    url = f"{BASE_URL}/{fname}"
    resp = session.get(url, timeout=30)
    content = resp.content

    if b"<HTML" in content[:20] or content[:5].upper() == b"<!DOC":
        print(f"  [err]  {fname} — 回傳 HTML（非 zip）")
        return False

    dest.write_bytes(content)
    print(f"  [ok]   {fname} ({len(content)//1024} KB)")
    return True


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="補下載 TAIFEX 每筆成交 tick zip")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="輸出目錄")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with requests.Session() as sess:
        sess.headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        sess.headers["Referer"] = PAGE_URL

        print("從 TAIFEX 取得可用清單...")
        available = fetch_available(sess)
        missing = [f for f in available if not (out_dir / f).exists()]
        print(f"可用: {len(available)} 個，缺少: {len(missing)} 個\n")

        ok = skip = err = 0
        for fname in missing:
            if download_one(fname, out_dir, sess):
                ok += 1
                time.sleep(SLEEP_SEC)
            else:
                err += 1

        skip = len(available) - len(missing)

    print(f"\n完成：下載 {ok} 筆，跳過 {skip} 筆，失敗 {err} 筆")
    existing = sorted(out_dir.glob("Daily_*.zip"))
    if existing:
        print(f"目錄現有資料：{existing[0].name} ～ {existing[-1].name}（共 {len(existing)} 個）")


if __name__ == "__main__":
    main()
