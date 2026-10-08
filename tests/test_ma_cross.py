"""
Unit tests for ma-cross 功能：
  - src/domain/services/ma_cross_screener.py
  - src/domain/services/sub_industry_index.py
  - src/utils/sub_industry_mapper.py（HTML 解析、快取）
  - src/application/services/ma_cross_scanner.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.application.services.ma_cross_scanner import MACrossScanner, load_price_frames
from src.domain.services.ma_cross_screener import detect_ma_cross_flat60
from src.domain.services.sub_industry_index import (
    build_daily_snapshot,
    compute_sub_industry_metrics,
    latest_trading_date,
    select_hot_sub_industries,
)
from src.utils import sub_industry_mapper as sim


# ── 測試資料產生 ─────────────────────────────────────────────────────────────

def make_df(closes, volume=1000, start="2026-01-01"):
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"date": dates, "close": closes, "volume": volume})


def cross_series():
    """長期下跌後打底、近期急拉：60MA 下彎，20MA 在最後幾天才穿越 60MA"""
    down = list(np.linspace(120, 90, 70))       # 下跌段：60MA 一路下彎
    base = [90.0] * 20                          # 打底
    up = list(np.linspace(91, 110, 30))         # 急拉：短均線先上穿，20MA 最後才上穿
    return down + base + up


def find_cross_len(closes):
    """截到 20MA 剛穿越 60MA 的那天，確保測試資料落在 lookback 視窗內"""
    s = pd.Series(closes, dtype=float)
    diff = s.rolling(20).mean() - s.rolling(60).mean()
    for i in range(61, len(s)):
        if diff.iloc[i - 1] <= 0 < diff.iloc[i]:
            return i + 1
    raise AssertionError("測試資料沒有產生穿越")


def default_cfg(**over):
    base = dict(
        lookback_days=5, ma60_slope_days=5, ma60_flat_tolerance=0.002,
        enable_sub_industry_filter=True, sub_industry_min_trade_value=1e4,
        sub_industry_top_n=10, sub_industry_weighting="equal",
        sub_industry_cache_ttl_hours=168, output_dir="unused",
    )
    base.update(over)
    return SimpleNamespace(**base)


# ── detect_ma_cross_flat60 ───────────────────────────────────────────────────

class TestDetectMaCross:
    def test_detects_fresh_cross_over_declining_ma60(self):
        closes = cross_series()
        n = find_cross_len(closes)
        df = make_df(closes[:n + 2])
        hit = detect_ma_cross_flat60(df)
        assert hit is not None
        assert hit["ma5"] > hit["ma60"] and hit["ma10"] > hit["ma60"] and hit["ma20"] > hit["ma60"]
        assert hit["ma60_slope"] <= 0.002
        assert hit["cross_date"] == df["date"].iloc[n - 1].date()

    def test_rejects_rising_ma60(self):
        # 長期上漲：60MA 上揚，不符合「下彎或走平」
        closes = list(np.linspace(50, 150, 120))
        assert detect_ma_cross_flat60(make_df(closes)) is None

    def test_rejects_old_cross_outside_lookback(self):
        closes = cross_series()
        n = find_cross_len(closes)
        # 穿越後再過 10 天（> lookback 5 天），視窗第一天 20MA 已在 60MA 上方
        extended = closes[:n] + [closes[n - 1]] * 10
        assert detect_ma_cross_flat60(make_df(extended), lookback_days=5, flat_tolerance=1) is None

    def test_rejects_when_short_ma_below_ma60(self):
        closes = list(np.linspace(120, 80, 120))  # 一路下跌，均線都在 60MA 下
        assert detect_ma_cross_flat60(make_df(closes)) is None

    def test_insufficient_history(self):
        assert detect_ma_cross_flat60(make_df([100.0] * 50)) is None

    def test_flat_tolerance_controls_slope(self):
        closes = cross_series()
        n = find_cross_len(closes)
        df = make_df(closes[:n + 2])
        # 容忍度設成極嚴格的負值（要求 60MA 至少下彎 50%）→ 不通過
        assert detect_ma_cross_flat60(df, flat_tolerance=-0.5) is None


# ── 細產業指標 ───────────────────────────────────────────────────────────────

@pytest.fixture
def frames():
    d = pd.to_datetime(["2026-10-06", "2026-10-07"])
    return {
        "1111": pd.DataFrame({"date": d, "close": [100.0, 110.0], "volume": [1000, 1000]}),   # +10%, 11萬
        "2222": pd.DataFrame({"date": d, "close": [50.0, 49.0], "volume": [10000, 10000]}),   # -2%, 49萬
        "3333": pd.DataFrame({"date": d, "close": [10.0, 10.5], "volume": [100, 100]}),       # +5%, 1050
        "4444": pd.DataFrame({"date": d[:1], "close": [10.0], "volume": [100]}),              # 停牌
    }


SUBS = {
    "A100": {"name": "甲", "chain": "鏈A", "codes": ["1111", "2222"]},
    "B100": {"name": "乙", "chain": "鏈B", "codes": ["3333", "4444"]},
    "C100": {"name": "丙", "chain": "鏈C", "codes": ["9999"]},           # 無資料
}


class TestSubIndustryIndex:
    def test_snapshot(self, frames):
        snap = build_daily_snapshot(frames, date(2026, 10, 7))
        assert set(snap.index) == {"1111", "2222", "3333"}
        assert snap.loc["1111", "change_pct"] == pytest.approx(10.0)
        assert snap.loc["2222", "trade_value"] == pytest.approx(490000)

    def test_equal_weight(self, frames):
        snap = build_daily_snapshot(frames, date(2026, 10, 7))
        m = compute_sub_industry_metrics(snap, SUBS, "equal").set_index("sub_id")
        assert "C100" not in m.index
        assert m.loc["A100", "change_pct"] == pytest.approx((10 - 2) / 2)
        assert m.loc["A100", "trade_value"] == pytest.approx(110000 + 490000)
        assert m.loc["B100", "members"] == 1

    def test_value_weight(self, frames):
        snap = build_daily_snapshot(frames, date(2026, 10, 7))
        m = compute_sub_industry_metrics(snap, SUBS, "value").set_index("sub_id")
        expected = (10 * 110000 + (-2) * 490000) / 600000
        assert m.loc["A100", "change_pct"] == pytest.approx(expected)

    def test_invalid_weighting(self, frames):
        snap = build_daily_snapshot(frames, date(2026, 10, 7))
        with pytest.raises(ValueError):
            compute_sub_industry_metrics(snap, SUBS, "cap")

    def test_select_hot(self):
        metrics = pd.DataFrame({
            "sub_id": ["a", "b", "c", "d"],
            "chain": ["x"] * 4, "name": ["x"] * 4, "members": [1] * 4,
            "trade_value": [2e10, 5e9, 3e10, 1.5e10],
            "change_pct": [1.0, 9.0, 3.0, 2.0],
        })
        hot = select_hot_sub_industries(metrics, min_trade_value=1e10, top_n=2)
        # b 漲最多但成交值不足 → 排除；其餘依漲幅取前 2
        assert list(hot["sub_id"]) == ["c", "d"]
        assert len(select_hot_sub_industries(metrics, 1e10, 0)) == 3

    def test_latest_trading_date_uses_mode(self, frames):
        frames = dict(frames)
        frames["dirty"] = pd.DataFrame({"date": pd.to_datetime(["2026-10-11"]), "close": [1.0], "volume": [1]})
        assert latest_trading_date(frames) == date(2026, 10, 7)
        assert latest_trading_date({}) is None


# ── 產業價值鏈平台 HTML 解析 ─────────────────────────────────────────────────

INDEX_HTML = """
<a href="introduce.php?ic=D000" class="link">半導體</a>
<a href="introduce.php?ic=J000" class="link">被動元件</a>
<a href="introduce.php?ic=J000" class="link">被動元件</a>
"""

CHAIN_HTML = """
<div class="page-header text-start"><h3>被動元件產業鏈簡介</h3></div>
<div id="companyList_J800" title="濾波器、振盪器(石英)" class="x-hidden"><div class="company-list"><table>
<tr><td class='company' rowspan='1'><b>本國上市公司(2家)</b></td>
<td class="company"><a href="company_basic.php?stk_code=2484" title="希華">希華</a></td>
<td class="company"><a href="company_basic.php?stk_code=6174" title="安碁">安碁</a></td>
<tr><td class='company' rowspan='1'><b>本國上櫃公司(1家)</b></td>
<td class="company"><a href="company_basic.php?stk_code=8289" title="泰藝">泰藝</a></td>
<tr><td class='company' rowspan='1'><b>本國興櫃公司(1家)</b></td>
<td class="company"><a href="company_basic.php?stk_code=7896" title="喬越">喬越</a></td>
<tr><td class='company' rowspan='1'><b>知名外國企業(1家)</b></td>
<td class="company"><a href="https://www.murata.com/" title="村田">村田</a></td>
</table></div></div>
<div id="companyList_J900" title="只有興櫃" class="x-hidden"><div class="company-list"><table>
<tr><td class='company'><b>本國興櫃公司(1家)</b></td>
<td class="company"><a href="company_basic.php?stk_code=7896" title="喬越">喬越</a></td>
</table></div></div>
"""


class TestSubIndustryMapper:
    def test_parse_chain_ids_dedup(self):
        assert sim.parse_chain_ids(INDEX_HTML) == ["D000", "J000"]

    def test_parse_chain_page_keeps_listed_and_otc_only(self):
        result = sim.parse_chain_page("J000", CHAIN_HTML)
        assert list(result) == ["J800"]  # J900 只有興櫃 → 略過
        info = result["J800"]
        assert info["chain"] == "被動元件"
        assert info["name"] == "濾波器、振盪器"
        assert info["codes"] == ["2484", "6174", "8289"]
        assert sim.format_sub_industry(info) == "被動元件/濾波器、振盪器"

    def test_build_stock_to_sub_industries(self):
        subs = {"A": {"codes": ["1", "2"]}, "B": {"codes": ["2"]}}
        assert sim.build_stock_to_sub_industries(subs) == {"1": ["A"], "2": ["A", "B"]}

    def test_cache_roundtrip_and_ttl(self, tmp_path):
        cache = tmp_path / "sub.json"
        data = {"J800": {"name": "n", "chain": "c", "chain_id": "J000", "codes": ["1"]}}
        with patch.object(sim, "CACHE_FILE", cache):
            sim._save_cache(data)
            assert sim.get_sub_industries(ttl_hours=1) == data
            # 過期 → 重新抓取
            payload = json.loads(cache.read_text())
            payload["cached_at"] = (datetime.now() - timedelta(hours=5)).isoformat()
            cache.write_text(json.dumps(payload))
            with patch.object(sim, "fetch_sub_industries", return_value={"X": {"codes": []}}) as f:
                assert sim.get_sub_industries(ttl_hours=1) == {"X": {"codes": []}}
                f.assert_called_once()

    def test_fetch_failure_falls_back_to_stale_cache(self, tmp_path):
        cache = tmp_path / "sub.json"
        data = {"J800": {"codes": ["1"]}}
        cache.write_text(json.dumps({
            "cached_at": (datetime.now() - timedelta(days=30)).isoformat(),
            "sub_industries": data,
        }))
        with patch.object(sim, "CACHE_FILE", cache), \
                patch.object(sim, "fetch_sub_industries", return_value={}):
            assert sim.get_sub_industries(ttl_hours=1) == data


# ── MACrossScanner 整合 ──────────────────────────────────────────────────────

class TestMACrossScanner:
    def _frames(self):
        closes = cross_series()
        n = find_cross_len(closes)
        hit = make_df(closes[:n + 1], volume=1000)
        flat = make_df([100.0] * (n + 1), volume=1000)
        return {
            "1111": {"market": "TW", "df": hit},
            "2222": {"market": "TWO", "df": hit.copy()},
            "3333": {"market": "TW", "df": flat},
        }

    def _scan(self, subs, **cfg):
        scanner = MACrossScanner(cfg=default_cfg(**cfg))
        return scanner.scan(
            price_frames=self._frames(),
            sub_industries=subs,
            names={"1111.TW": "甲公司", "2222.TWO": "乙公司"},
            industries={"1111": "28"},
        )

    def test_filter_keeps_only_hot_sub_industries(self):
        subs = {
            "HOT": {"name": "熱", "chain": "鏈", "codes": ["1111"]},
            "COLD": {"name": "冷", "chain": "鏈", "codes": ["2222", "3333"]},
        }
        # top_n=1：1111 漲幅高於 COLD 平均 → 只有 HOT 入選
        result = self._scan(subs, sub_industry_top_n=1)
        assert set(result.candidates["code"]) == {"1111", "2222"}
        assert list(result.hot_sub_industries["sub_id"]) == ["HOT"]
        assert list(result.stocks["code"]) == ["1111"]
        row = result.stocks.iloc[0]
        assert row["name"] == "甲公司"
        assert row["market"] == "上市"
        assert row["sector"] == "電子零組件"
        assert row["hot_sub_industries"] == "鏈/熱"
        assert row["main_sub_industry"] == "鏈/熱"
        df = self._frames()["1111"]["df"]
        expected = round((df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100, 2)
        assert row["change_pct"] == expected

    def test_trade_value_threshold_excludes_all(self):
        subs = {"HOT": {"name": "熱", "chain": "鏈", "codes": ["1111"]}}
        result = self._scan(subs, sub_industry_min_trade_value=1e15)
        assert result.hot_sub_industries.empty
        assert result.stocks.empty
        assert len(result.candidates) == 2

    def test_filter_disabled(self):
        result = self._scan({}, enable_sub_industry_filter=False)
        assert len(result.stocks) == len(result.candidates) == 2

    def test_save_outputs_csv(self, tmp_path):
        subs = {"HOT": {"name": "熱", "chain": "鏈", "codes": ["1111"]}}
        scanner = MACrossScanner(cfg=default_cfg())
        result = scanner.scan(price_frames=self._frames(), sub_industries=subs, names={}, industries={})
        path = scanner.save(result, str(tmp_path))
        assert os.path.exists(path)
        assert any(p.name.startswith("sub_industry_metrics_") for p in tmp_path.iterdir())


class TestMainSubIndustry:
    SUBS = {
        "A": {"name": "甲", "chain": "鏈"},
        "B": {"name": "乙", "chain": "鏈"},
        "C": {"name": "丙", "chain": "鏈"},
    }

    def test_picks_best_ranked_hot_sub(self):
        assert MACrossScanner._main_sub_industry(["A", "B", "C"], {"C": 0, "B": 3}, self.SUBS) == "鏈/丙"

    def test_falls_back_to_first_sub(self):
        assert MACrossScanner._main_sub_industry(["B", "A"], {}, self.SUBS) == "鏈/乙"
        assert MACrossScanner._main_sub_industry([], {}, self.SUBS) == ""


class TestLoadPriceFrames:
    def test_skips_test_files_and_normalises_dates(self, tmp_path):
        (tmp_path / "1234_TW.csv").write_text(
            "date,open,high,low,close,volume,symbol\n"
            "2026-10-07 00:00:00+08:00,1,1,1,11,100,1234.TW\n"
            "2026-10-06,1,1,1,10,100,1234.TW\n"
            "2026-10-06,1,1,1,10.5,100,1234.TW\n"
        )
        (tmp_path / "TEST_TW.csv").write_text("date,close,volume\n2026-10-11,1,1\n")
        frames = load_price_frames(str(tmp_path))
        assert list(frames) == ["1234"]
        df = frames["1234"]["df"]
        assert frames["1234"]["market"] == "TW"
        assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2026-10-06", "2026-10-07"]
        assert df["close"].iloc[0] == 10.5  # 重複日期保留最後一筆


# ── CLI：Telegram 訊息與排程保護 ─────────────────────────────────────────────

from src.application.services.ma_cross_scanner import MACrossScanResult, RESULT_COLUMNS
from src.interfaces.cli import ma_cross_main as cli


def _result(n_stocks=2, hot=True):
    rows = [{
        "cross_date": date(2026, 10, 6), "code": f"{8000 + i}", "name": f"股{i}", "market": "上市",
        "sector": "電子零組件", "sub_industries": "被動元件/電容器", "hot_sub_industries": "被動元件/電容器",
        "main_sub_industry": "被動元件/電容器",
        "close": 126.0, "change_pct": 9.92, "ma5": 1.0, "ma10": 1.0, "ma20": 1.0, "ma60": 113.25, "ma60_slope_pct": -3.54,
        "volume": 1000,
    } for i in range(n_stocks)]
    stocks = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    hot_df = pd.DataFrame([{"sub_id": "J600", "chain": "被動元件", "name": "電容器", "members": 16,
                            "trade_value": 1.3249e11, "change_pct": 3.85}]) if hot else pd.DataFrame(
        columns=["sub_id", "chain", "name", "members", "trade_value", "change_pct"])
    return MACrossScanResult(date(2026, 10, 7), stocks, stocks, pd.DataFrame(), hot_df)


class TestTelegramFormat:
    def test_header_and_rows(self):
        chunks = cli.format_for_telegram(_result(), show_filter=True)
        assert chunks == [
            "<b>📈 均線穿越 60MA</b>\n2026-10-07（三）・細產業過濾後 <b>2</b> 檔\n\n"
            "🏷 <b>被動元件/電容器</b>\n"
            "<b>8000</b>  股0  126.00  +9.92%\n<b>8001</b>  股1  126.00  +9.92%"
        ]
        # 不用 <pre>（手機複製按鈕會遮住內容），也不含細產業漲幅排行
        assert "<pre>" not in chunks[0] and "熱門細產業" not in chunks[0]

    def test_grouped_by_hot_rank_and_other_last(self):
        res = _result(4)
        res.stocks.loc[0, "main_sub_industry"] = "鏈/乙"
        res.stocks.loc[1, "main_sub_industry"] = ""
        res.stocks.loc[2, "main_sub_industry"] = "鏈/甲"
        res.stocks.loc[3, "main_sub_industry"] = "鏈/乙"
        res.hot_sub_industries = pd.DataFrame([
            {"sub_id": "A", "chain": "鏈", "name": "甲", "members": 1, "trade_value": 1e11, "change_pct": 5.0},
            {"sub_id": "B", "chain": "鏈", "name": "乙", "members": 1, "trade_value": 1e11, "change_pct": 3.0},
        ])
        text = cli.format_for_telegram(res, True)[0]
        groups = [line for line in text.splitlines() if line.startswith("🏷")]
        assert groups == ["🏷 <b>鏈/甲</b>", "🏷 <b>鏈/乙</b>", "🏷 <b>其他</b>"]
        # 同組股票維持原順序
        yi = text.split("🏷 <b>鏈/乙</b>\n")[1].split("\n\n")[0].splitlines()
        assert [line.split("</b>")[0][3:] for line in yi] == ["8000", "8003"]

    def test_change_pct_sign_and_missing(self):
        res = _result(2)
        res.stocks.loc[0, "change_pct"] = -1.5
        res.stocks.loc[1, "change_pct"] = float("nan")
        lines = cli.format_for_telegram(res, True)[0].splitlines()
        assert "<b>8000</b>  股0  126.00  -1.50%" in lines
        assert "<b>8001</b>  股1  126.00" in lines

    def test_html_escaped(self):
        res = _result(1)
        res.stocks.loc[0, "name"] = "A<B>&C"
        text = cli.format_for_telegram(res, True)[0]
        assert "A&lt;B&gt;&amp;C" in text

    def test_empty_results(self):
        text = "\n".join(cli.format_for_telegram(_result(0, hot=False), show_filter=True))
        assert "今日無符合條件的股票" in text

    def test_max_stocks_truncation(self):
        text = "\n".join(cli.format_for_telegram(_result(5), show_filter=True, max_stocks=2))
        assert "8001" in text and "8002" not in text
        assert "另有 3 檔" in text

    def test_chunking_respects_limit(self):
        chunks = cli.format_for_telegram(_result(400), show_filter=True, max_stocks=0)
        assert len(chunks) > 1
        assert all(len(c) <= cli.TELEGRAM_CHUNK_LIMIT for c in chunks)
        assert sum(c.count(" 股") for c in chunks) == 400
        assert chunks[0].startswith("<b>📈") and not chunks[1].startswith("<b>📈")

    def test_send_uses_html_and_configured_chat(self):
        with patch.object(cli, "TelegramNotifier") as notifier_cls:
            notifier_cls.return_value.send_message.return_value = True
            assert cli.send_telegram(["a", "b"], chat_id="-100123")
            calls = notifier_cls.return_value.send_message.call_args_list
            assert [c.args[0] for c in calls] == ["a", "b"]
            assert all(c.kwargs == {"chat_id": "-100123", "parse_mode": "HTML"} for c in calls)


class TestCliMain:
    def _run(self, result, argv, today=date(2026, 10, 7)):
        with patch.object(cli, "MACrossScanner") as scanner_cls, \
                patch.object(cli, "today_taipei", return_value=today), \
                patch.object(cli, "send_telegram", return_value=True) as send:
            scanner_cls.return_value.scan.return_value = result
            scanner_cls.return_value.save.return_value = "out.csv"
            code = cli.main(argv)
            return code, send, scanner_cls.return_value.save

    def test_require_today_skips_stale_data(self):
        code, send, save = self._run(_result(), ["--send-telegram", "--require-today"], today=date(2026, 10, 8))
        assert code == 0
        send.assert_not_called()
        save.assert_not_called()

    def test_sends_when_data_is_today(self):
        code, send, save = self._run(_result(), ["--send-telegram", "--require-today"])
        assert code == 0
        send.assert_called_once()
        save.assert_called_once()

    def test_no_telegram_by_default(self):
        code, send, _ = self._run(_result(), [])
        assert code == 0
        send.assert_not_called()

    def test_telegram_failure_returns_error(self):
        with patch.object(cli, "MACrossScanner") as scanner_cls, \
                patch.object(cli, "send_telegram", return_value=False):
            scanner_cls.return_value.scan.return_value = _result()
            scanner_cls.return_value.save.return_value = "out.csv"
            assert cli.main(["--send-telegram"]) == 1
