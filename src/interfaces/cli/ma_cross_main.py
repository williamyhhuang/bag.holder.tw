"""
均線穿越 60MA 篩選 CLI

用法：
    python -m src.interfaces.cli.ma_cross_main            # 套用細產業指標過濾
    python -m src.interfaces.cli.ma_cross_main --no-sub-industry-filter
    python -m src.interfaces.cli.ma_cross_main --refresh-sub-industries
"""
import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from config.settings import settings
from src.application.services.ma_cross_scanner import MACrossScanner, MACrossScanResult
from src.utils.logger import get_logger
from src.utils.sub_industry_mapper import get_sub_industries

logger = get_logger(__name__)


def _fmt_value(v: float) -> str:
    return f"{v / 1e8:,.1f}億"


def print_result(result: MACrossScanResult, show_filter: bool) -> None:
    cfg = settings.ma_cross
    print(f"\n📅 基準日：{result.as_of}")

    if show_filter:
        print(
            f"\n🔥 熱門細產業（成交值 ≥ {_fmt_value(cfg.sub_industry_min_trade_value)}，"
            f"漲幅前 {cfg.sub_industry_top_n} 名，{cfg.sub_industry_weighting} 加權）"
        )
        for i, r in result.hot_sub_industries.iterrows():
            print(
                f"  {i + 1:>2}. {r['chain']}/{r['name']:<20} 漲幅 {r['change_pct']:+.2f}%  "
                f"成交值 {_fmt_value(r['trade_value'])}  成分股 {r['members']}"
            )

    print(
        f"\n📈 5/10/20MA 穿越下彎或走平 60MA：{len(result.candidates)} 檔"
        + (f"，細產業過濾後 {len(result.stocks)} 檔" if show_filter else "")
    )
    for _, r in result.stocks.iterrows():
        subs = r["hot_sub_industries"] if show_filter else r["sub_industries"]
        print(
            f"  {r['cross_date']}  {r['code']:<6} {r['name']:<8} {r['sector']:<6} "
            f"收 {r['close']:>8.2f}  60MA {r['ma60']:>8.2f} ({r['ma60_slope_pct']:+.2f}%)  {subs}"
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="5/10/20MA 穿越下彎或走平 60MA 篩選 + 細產業指標過濾")
    parser.add_argument("--no-sub-industry-filter", action="store_true", help="不套用細產業指標過濾")
    parser.add_argument("--refresh-sub-industries", action="store_true", help="強制重新抓取細產業對照")
    parser.add_argument("--output-dir", help=f"輸出目錄（預設 {settings.ma_cross.output_dir}）")
    args = parser.parse_args(argv)

    sub_industries = None
    if args.refresh_sub_industries:
        sub_industries = get_sub_industries(use_cache=False)

    scanner = MACrossScanner()
    show_filter = not args.no_sub_industry_filter
    result = scanner.scan(sub_industries=sub_industries, apply_sub_industry_filter=show_filter)
    if result.as_of is None:
        logger.error(f"{scanner.stocks_dir} 沒有可用的日K資料")
        return 1

    print_result(result, show_filter)
    path = scanner.save(result, args.output_dir)
    print(f"\n💾 已輸出：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
