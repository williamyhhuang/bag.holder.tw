"""
IC Validator — 因子資訊係數驗證器
=====================================
Phase 2：在正式使用任何因子前，用歷史資料驗證其預測力。

IC (Information Coefficient) = 因子值與未來 N 日報酬的 Spearman 相關係數。

驗收標準：
  IC 均值 > 0.02    → 有預測力
  IC t-stat > 2.0   → 統計顯著（95% 信心水準）
  IC > 0 勝率 > 55% → 方向穩定

輸出指標：
  IC_mean  — 所有交易日的平均 IC
  IC_std   — IC 標準差
  IC_ir    — IC / IC_std（資訊比率，類似 Sharpe）
  t_stat   — IC_mean / (IC_std / sqrt(N))，衡量統計顯著性
  pos_rate — IC > 0 的天數比例
  n_dates  — 有效計算天數

使用方式：
  python main.py ic-report --forward-days 5 10 20

注意：
  - 只使用 OHLCV 資料（不需要法人/財報資料）
  - Spearman 相關係數對離群值穩健
  - 避免 look-ahead bias：因子值只用 target_date 當日可知的資料
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


@dataclass
class ICResult:
    """單一因子在單一預測期間的 IC 統計"""
    factor_name: str
    forward_days: int
    ic_mean: float
    ic_std: float
    ic_ir: float        # IC / IC_std（資訊比率）
    t_stat: float
    pos_rate: float     # IC > 0 的天數比例
    n_dates: int        # 有效計算天數

    @property
    def is_significant(self) -> bool:
        """IC 達到統計顯著（t-stat > 2.0）且方向穩定（pos_rate > 55%）"""
        return self.t_stat > 2.0 and self.pos_rate > 0.55

    @property
    def has_predictive_power(self) -> bool:
        """IC 均值 > 0.02（業界常用門檻）"""
        return self.ic_mean > 0.02


@dataclass
class ICReport:
    """所有因子、所有預測期間的 IC 報告"""
    results: List[ICResult] = field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    universe_size: int = 0

    def get(self, factor_name: str, forward_days: int) -> Optional[ICResult]:
        for r in self.results:
            if r.factor_name == factor_name and r.forward_days == forward_days:
                return r
        return None

    def summary_table(self) -> str:
        """輸出 Markdown 格式摘要表"""
        if not self.results:
            return "（無結果）"

        lines = [
            f"**回測期間**: {self.start_date} ~ {self.end_date}",
            f"**股票池**: {self.universe_size} 支",
            "",
            "| 因子 | 預測期 | IC均值 | IC標準差 | IR | t-stat | IC>0率 | 有效日數 | 通過？ |",
            "|------|--------|--------|----------|----|--------|--------|----------|--------|",
        ]
        for r in sorted(self.results, key=lambda x: (x.factor_name, x.forward_days)):
            passed = "✅" if r.is_significant and r.has_predictive_power else "❌"
            lines.append(
                f"| {r.factor_name} | {r.forward_days}d "
                f"| {r.ic_mean:.4f} | {r.ic_std:.4f} "
                f"| {r.ic_ir:.2f} | {r.t_stat:.2f} "
                f"| {r.pos_rate:.1%} | {r.n_dates} | {passed} |"
            )
        return "\n".join(lines)


def _spearman_correlation(x: List[float], y: List[float]) -> Optional[float]:
    """
    計算兩個序列的 Spearman 相關係數（不依賴 scipy）。
    長度不符或標準差為 0 時回傳 None。
    """
    n = len(x)
    if n != len(y) or n < 3:
        return None

    def _rank(lst: List[float]) -> List[float]:
        """將序列轉換為排名（從 1 開始，平均排名處理並列）"""
        sorted_vals = sorted(enumerate(lst), key=lambda t: t[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and sorted_vals[j + 1][1] == sorted_vals[i][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[sorted_vals[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = _rank(x)
    ry = _rank(y)

    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n

    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((v - mean_rx) ** 2 for v in rx))
    den_y = math.sqrt(sum((v - mean_ry) ** 2 for v in ry))

    if den_x == 0 or den_y == 0:
        return None

    return num / (den_x * den_y)


def _compute_t_stat(ic_mean: float, ic_std: float, n: int) -> float:
    """計算 IC 的 t-statistic：mean / (std / sqrt(n))"""
    if ic_std == 0 or n == 0:
        return 0.0
    return ic_mean / (ic_std / math.sqrt(n))


class ICValidator:
    """
    IC 驗證器：計算多個因子在多個預測期間的 IC 統計。

    使用方式：
        validator = ICValidator()
        report = validator.run(
            stock_data_dict=stock_data,
            factors=["rps_3m", "rps_6m", "vol_ratio", "momentum_20d"],
            forward_days=[5, 10, 20],
            start_date=date(2022, 1, 1),
            end_date=date(2026, 5, 30),
            min_stocks_per_date=30,
        )
        print(report.summary_table())
    """

    # 因子計算視窗（交易日）
    _FACTOR_WINDOWS = {
        "rps_3m": 63,
        "rps_6m": 126,
        "momentum_20d": 20,
        "momentum_5d": 5,
    }

    def run(
        self,
        stock_data_dict: Dict[str, list],
        factors: Optional[List[str]] = None,
        forward_days: Optional[List[int]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_stocks_per_date: int = 20,
        sampling_freq: int = 5,
    ) -> ICReport:
        """
        對所有指定因子與預測期間計算 IC。

        Args:
            stock_data_dict: {symbol: [StockData, ...]}
            factors: 要驗證的因子名稱清單（預設全部）
            forward_days: 預測期間列表（預設 [5, 10, 20]）
            start_date: 計算起始日
            end_date: 計算結束日
            min_stocks_per_date: 每個交易日至少需要多少支股票才計算 IC
            sampling_freq: 每隔幾個交易日取樣一次（1=每天，5=每週，加速計算）

        Returns:
            ICReport
        """
        if factors is None:
            factors = list(self._FACTOR_WINDOWS.keys()) + ["vol_ratio"]
        if forward_days is None:
            forward_days = [5, 10, 20]

        # 排序歷史資料
        sorted_data: Dict[str, list] = {
            sym: sorted(records, key=lambda r: r.date)
            for sym, records in stock_data_dict.items()
        }

        # 收集所有交易日
        all_dates: set = set()
        for records in sorted_data.values():
            for r in records:
                all_dates.add(r.date)

        if start_date:
            all_dates = {d for d in all_dates if d >= start_date}
        if end_date:
            all_dates = {d for d in all_dates if d <= end_date}

        trading_dates = sorted(all_dates)

        # 取樣（避免計算量過大）
        sampled_dates = trading_dates[::sampling_freq]

        logger.info(
            f"IC 驗證：{len(sampled_dates)} 個取樣日（共 {len(trading_dates)} 個交易日，"
            f"每 {sampling_freq} 日取樣）"
        )

        report = ICReport(
            start_date=trading_dates[0] if trading_dates else start_date,
            end_date=trading_dates[-1] if trading_dates else end_date,
            universe_size=len(sorted_data),
        )

        for fwd in forward_days:
            for factor in factors:
                ic_series = self._compute_ic_series(
                    sorted_data=sorted_data,
                    sampled_dates=sampled_dates,
                    trading_dates=trading_dates,
                    factor=factor,
                    forward_days=fwd,
                    min_stocks=min_stocks_per_date,
                )

                if not ic_series:
                    logger.warning(f"[IC] {factor} / {fwd}d：無有效資料")
                    continue

                ic_mean = sum(ic_series) / len(ic_series)
                ic_std = math.sqrt(
                    sum((v - ic_mean) ** 2 for v in ic_series) / len(ic_series)
                ) if len(ic_series) > 1 else 0.0
                ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
                t_stat = _compute_t_stat(ic_mean, ic_std, len(ic_series))
                pos_rate = sum(1 for v in ic_series if v > 0) / len(ic_series)

                result = ICResult(
                    factor_name=factor,
                    forward_days=fwd,
                    ic_mean=round(ic_mean, 4),
                    ic_std=round(ic_std, 4),
                    ic_ir=round(ic_ir, 3),
                    t_stat=round(t_stat, 2),
                    pos_rate=round(pos_rate, 3),
                    n_dates=len(ic_series),
                )
                report.results.append(result)
                logger.info(
                    f"[IC] {factor:15s} fwd={fwd:2d}d: "
                    f"mean={ic_mean:+.4f} t={t_stat:.2f} "
                    f"pos={pos_rate:.1%} n={len(ic_series)}"
                )

        return report

    def _compute_ic_series(
        self,
        sorted_data: Dict[str, list],
        sampled_dates: List[date],
        trading_dates: List[date],
        factor: str,
        forward_days: int,
        min_stocks: int,
    ) -> List[float]:
        """計算指定因子在所有取樣日的 IC 序列"""
        ic_series: List[float] = []
        trading_date_set = set(trading_dates)

        for target_date in sampled_dates:
            # 計算未來 forward_days 個交易日後的日期
            future_date = self._nth_trading_date(
                trading_dates, target_date, forward_days
            )
            if future_date is None:
                continue  # 未來資料不足

            factor_vals: List[float] = []
            future_returns: List[float] = []

            for sym, records in sorted_data.items():
                # 計算因子值
                fv = self._compute_factor(records, target_date, factor)
                if fv is None:
                    continue

                # 計算未來報酬
                cur_price = self._get_close(records, target_date)
                fut_price = self._get_close(records, future_date)
                if cur_price is None or fut_price is None or cur_price == 0:
                    continue

                fwd_return = (fut_price - cur_price) / cur_price
                factor_vals.append(fv)
                future_returns.append(fwd_return)

            if len(factor_vals) < min_stocks:
                continue

            ic = _spearman_correlation(factor_vals, future_returns)
            if ic is not None:
                ic_series.append(ic)

        return ic_series

    @staticmethod
    def _nth_trading_date(
        trading_dates: List[date], base_date: date, n: int
    ) -> Optional[date]:
        """回傳 base_date 之後第 n 個交易日"""
        try:
            idx = trading_dates.index(base_date)
        except ValueError:
            # base_date 不在清單中，找最近的
            later = [d for d in trading_dates if d > base_date]
            if not later:
                return None
            idx = trading_dates.index(later[0]) - 1
            if idx < 0:
                return None

        target_idx = idx + n
        if target_idx >= len(trading_dates):
            return None
        return trading_dates[target_idx]

    @staticmethod
    def _get_close(records: list, target_date: date) -> Optional[float]:
        """取得截至 target_date 最近一個有效收盤價"""
        valid = [r for r in records if r.date <= target_date]
        if not valid:
            return None
        return float(valid[-1].close_price)

    def _compute_factor(
        self, records: list, target_date: date, factor: str
    ) -> Optional[float]:
        """計算單支股票在 target_date 的因子值"""
        valid = [r for r in records if r.date <= target_date]
        valid_sorted = sorted(valid, key=lambda r: r.date)

        if factor in self._FACTOR_WINDOWS:
            n = self._FACTOR_WINDOWS[factor]
            if len(valid_sorted) < n + 1:
                return None
            cur = float(valid_sorted[-1].close_price)
            past = float(valid_sorted[-(n + 1)].close_price)
            if past == 0:
                return None
            return (cur - past) / past

        elif factor == "vol_ratio":
            if len(valid_sorted) < 21:
                return None
            today_vol = float(valid_sorted[-1].volume)
            ma20_vol = sum(float(r.volume) for r in valid_sorted[-21:-1]) / 20
            if ma20_vol == 0:
                return None
            return today_vol / ma20_vol

        else:
            logger.warning(f"未知因子: {factor}")
            return None
