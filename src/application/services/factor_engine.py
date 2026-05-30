"""
Factor Engine — 截面因子計算與排名
=====================================
Phase 1：計算三個核心截面因子，輸出每支股票的綜合排名分數。

因子：
1. RPS 3個月 (63 交易日) — 股價相對強度百分位
2. RPS 6個月 (126 交易日) — 股價相對強度百分位
3. 量能比率 — 今日量 / 20日均量的截面百分位
4. 法人連續買超分數 — 外資+投信連續買超天數加權截面百分位

綜合分數 = RPS_3m * 0.25 + RPS_6m * 0.25 + 量能 * 0.20 + 法人 * 0.30

截面排名邏輯：在全部候選股票（通常是 BUY 候選清單）中排名，
分數越高代表該因子表現越強。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

# 因子權重（加總 = 1.0）
_WEIGHT_RPS_3M = 0.25
_WEIGHT_RPS_6M = 0.25
_WEIGHT_VOL_RATIO = 0.20
_WEIGHT_INST = 0.30

# RPS 計算窗口（交易日數）
_RPS_3M_DAYS = 63
_RPS_6M_DAYS = 126


@dataclass
class FactorScores:
    """單支股票的截面因子分數（均為 0~1 百分位）"""
    rps_3m: float = 0.5        # 3個月相對強度百分位
    rps_6m: float = 0.5        # 6個月相對強度百分位
    vol_ratio_rank: float = 0.5  # 量能比率截面百分位
    inst_score: float = 0.5    # 法人連續買超截面百分位
    composite: float = 0.5     # 加權綜合分數


def _percentile_rank(raw: Dict[str, float]) -> Dict[str, float]:
    """
    將原始值 dict 轉換為 0~1 截面百分位排名。
    同值排名相同（平均排名法）。
    """
    if not raw:
        return {}
    if len(raw) == 1:
        return {list(raw.keys())[0]: 0.5}

    sorted_syms = sorted(raw.keys(), key=lambda s: raw[s])
    n = len(sorted_syms)
    return {sym: i / (n - 1) for i, sym in enumerate(sorted_syms)}


class FactorEngine:
    """
    截面因子計算引擎。

    使用方式：
        engine = FactorEngine()
        scores = engine.compute_factor_scores(
            stock_data_dict=stock_data,          # 全市場 OHLCV
            candidate_symbols=buy_candidates,    # BUY 候選清單
            target_date=today,
            inst_consecutive=consecutive_dict,   # 來自 InstitutionalHistoryLoader
        )
        # scores: {symbol: FactorScores}
        sorted_syms = sorted(scores, key=lambda s: scores[s].composite, reverse=True)
    """

    def compute_factor_scores(
        self,
        stock_data_dict: Dict[str, list],
        candidate_symbols: List[str],
        target_date: date,
        inst_consecutive: Optional[Dict[str, dict]] = None,
    ) -> Dict[str, "FactorScores"]:
        """
        計算所有候選股票的截面因子分數。

        Args:
            stock_data_dict: {symbol: [StockData, ...]}，全市場歷史資料
            candidate_symbols: BUY 候選股票代號清單
            target_date: 計算基準日
            inst_consecutive: {symbol: {"foreign_consecutive": int, "trust_consecutive": int}}
                              來自 InstitutionalHistoryLoader.build_consecutive_days()

        Returns:
            {symbol: FactorScores}
        """
        if not candidate_symbols:
            return {}

        # 只對候選股票計算因子（節省計算量），截面排名也僅在候選池內
        candidates_set = set(candidate_symbols)
        candidate_data = {
            sym: data
            for sym, data in stock_data_dict.items()
            if sym in candidates_set
        }

        # 1. RPS
        rps_3m_raw = self._compute_rps(candidate_data, target_date, _RPS_3M_DAYS)
        rps_6m_raw = self._compute_rps(candidate_data, target_date, _RPS_6M_DAYS)

        # 2. 量能比率
        vol_ratio_raw = self._compute_vol_ratio(candidate_data, target_date)

        # 3. 法人連續買超分數
        inst_raw = self._compute_inst_score(inst_consecutive or {}, candidates_set)

        # 4. 截面百分位
        rps_3m_pct = _percentile_rank(rps_3m_raw)
        rps_6m_pct = _percentile_rank(rps_6m_raw)
        vol_ratio_pct = _percentile_rank(vol_ratio_raw)
        inst_pct = _percentile_rank(inst_raw)

        # 5. 合成
        result: Dict[str, FactorScores] = {}
        for sym in candidate_symbols:
            r3 = rps_3m_pct.get(sym, 0.5)
            r6 = rps_6m_pct.get(sym, 0.5)
            v = vol_ratio_pct.get(sym, 0.5)
            i = inst_pct.get(sym, 0.5)

            composite = (
                r3 * _WEIGHT_RPS_3M
                + r6 * _WEIGHT_RPS_6M
                + v * _WEIGHT_VOL_RATIO
                + i * _WEIGHT_INST
            )
            result[sym] = FactorScores(
                rps_3m=round(r3, 3),
                rps_6m=round(r6, 3),
                vol_ratio_rank=round(v, 3),
                inst_score=round(i, 3),
                composite=round(composite, 3),
            )

            logger.debug(
                f"[factor] {sym}: RPS3m={r3:.2f} RPS6m={r6:.2f} "
                f"Vol={v:.2f} Inst={i:.2f} → {composite:.3f}"
            )

        return result

    # ── 私有計算方法 ────────────────────────────────────────────────

    @staticmethod
    def _get_sorted_closes(data: list, target_date: date) -> List[float]:
        """取得截至 target_date 的所有收盤價（升序）"""
        valid = [d for d in data if d.date <= target_date]
        valid.sort(key=lambda d: d.date)
        return [float(d.close_price) for d in valid]

    def _compute_rps(
        self,
        candidate_data: Dict[str, list],
        target_date: date,
        n_days: int,
    ) -> Dict[str, float]:
        """
        計算 N 交易日報酬率（用於截面 RPS 排名）。
        資料不足時略過該股票（不影響其他股票排名）。
        """
        returns: Dict[str, float] = {}
        for sym, data in candidate_data.items():
            closes = self._get_sorted_closes(data, target_date)
            if len(closes) < n_days + 1:
                continue
            cur = closes[-1]
            past = closes[-(n_days + 1)]
            if past > 0:
                returns[sym] = (cur - past) / past
        return returns

    @staticmethod
    def _compute_vol_ratio(
        candidate_data: Dict[str, list],
        target_date: date,
    ) -> Dict[str, float]:
        """
        計算今日成交量 / 20日均量（量能比率）。
        """
        ratios: Dict[str, float] = {}
        for sym, data in candidate_data.items():
            valid = [d for d in data if d.date <= target_date]
            valid.sort(key=lambda d: d.date)
            if len(valid) < 21:
                continue
            today_vol = float(valid[-1].volume)
            ma20_vol = sum(float(d.volume) for d in valid[-21:-1]) / 20
            if ma20_vol > 0:
                ratios[sym] = today_vol / ma20_vol
        return ratios

    @staticmethod
    def _compute_inst_score(
        inst_consecutive: Dict[str, dict],
        candidates_set: set,
    ) -> Dict[str, float]:
        """
        計算法人連續買超加權分數。
        score = 外資連續買超天數 * 0.6 + 投信連續買超天數 * 0.4

        只計算候選股票，上櫃等無法人資料的股票得到中位數（排名時視為 0.5）。
        """
        scores: Dict[str, float] = {}
        for sym in candidates_set:
            inst = inst_consecutive.get(sym)
            if inst is None:
                continue
            f = inst.get("foreign_consecutive", 0)
            t = inst.get("trust_consecutive", 0)
            scores[sym] = f * 0.6 + t * 0.4
        return scores
