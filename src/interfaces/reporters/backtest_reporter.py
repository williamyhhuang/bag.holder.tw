"""
Backtest report generator
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
import os

from ...domain.models import BacktestResult, TradingSignal
from ...domain.models.stock import StockData
from ...application.services.performance_analyzer import PerformanceAnalyzer
from ...utils.logger import get_logger

logger = get_logger(__name__)


class BacktestReporter:
    """Generate comprehensive backtest reports"""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        self.analyzer = PerformanceAnalyzer()
        self.logger = get_logger(self.__class__.__name__)

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

    def generate_markdown_report(
        self,
        result: BacktestResult,
        signals: List[TradingSignal],
        benchmark_data: Optional[List[StockData]] = None,
        filename: str = None
    ) -> str:
        """
        Generate comprehensive markdown report

        Args:
            result: Backtest result
            signals: Trading signals used
            benchmark_data: Benchmark data for comparison
            filename: Output filename

        Returns:
            Path to generated report
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backtest_report_{timestamp}.md"

        filepath = os.path.join(self.output_dir, filename)

        try:
            # Generate performance summary
            summary = self.analyzer.generate_performance_summary(result)

            # Generate benchmark comparison if available
            benchmark_comparison = {}
            if benchmark_data:
                benchmark_comparison = self.analyzer.calculate_benchmark_comparison(
                    result.portfolio_history, benchmark_data
                )

            # Generate signal analysis with actual trade outcomes
            signal_analysis = self.analyze_signals(signals, result.trades)

            # Create markdown content
            content = self._create_markdown_content(
                result, summary, benchmark_comparison, signal_analysis
            )

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            self.logger.info(f"Generated markdown report: {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error generating markdown report: {e}")
            raise

    def _create_markdown_content(
        self,
        result: BacktestResult,
        summary: Dict,
        benchmark_comparison: Dict,
        signal_analysis: Dict
    ) -> str:
        """Create markdown content for the report"""

        content = f"""# 回測報告

## 📊 執行概要

**回測期間**: {result.start_date} 至 {result.end_date} ({(result.end_date - result.start_date).days} 天)
**策略**: 技術分析多重訊號策略
**報告生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 💰 投資績效

### 📈 整體表現
| 指標 | 數值 |
|------|------|
| 初始資金 | {result.initial_capital:,} TWD |
| 最終資金 | {result.final_capital:,} TWD |
| 總報酬 | {result.total_return:,} TWD |
| 總報酬率 | {result.total_return_pct}% |
| 年化報酬率 | {result.annualized_return}% |

### 📉 風險指標
| 指標 | 數值 |
|------|------|
| 最大回撤 | {result.max_drawdown}% |
| 夏普比率 | {result.sharpe_ratio} |
"""

        # Add benchmark comparison if available
        if benchmark_comparison:
            content += f"""
### 🎯 基準比較 (vs TAIEX)
| 指標 | 策略 | 大盤 | 超額報酬 |
|------|------|------|---------|
| 總報酬率 | {benchmark_comparison.get('strategy_total_return', 0)}% | {benchmark_comparison.get('benchmark_total_return', 0)}% | {benchmark_comparison.get('excess_return', 0)}% |
| 波動度 | {benchmark_comparison.get('strategy_volatility', 0)}% | {benchmark_comparison.get('benchmark_volatility', 0)}% | - |
| Alpha | {benchmark_comparison.get('alpha', 0)}% | - | - |
| Beta | {benchmark_comparison.get('beta', 0)} | - | - |
"""

        content += f"""
---

## 📈 交易統計

### 🎯 交易績效
| 指標 | 數值 |
|------|------|
| 總交易次數 | {result.total_trades} |
| 獲利交易 | {result.winning_trades} |
| 虧損交易 | {result.losing_trades} |
| **勝率** | **{result.win_rate}%** |
| 獲利因子 | {result.profit_factor} |
| 平均持倉天數 | {result.avg_holding_period} 天 |

### 💵 損益分析
| 指標 | 數值 |
|------|------|
| 平均獲利 | {result.avg_win:,} TWD |
| 平均虧損 | {result.avg_loss:,} TWD |
| 最大獲利 | {result.largest_win:,} TWD |
| 最大虧損 | {result.largest_loss:,} TWD |
"""

        # Add detailed trade analysis
        if 'detailed_trade_analysis' in summary:
            trade_analysis = summary['detailed_trade_analysis']
            content += f"""
### 📊 詳細交易分析
| 指標 | 數值 |
|------|------|
| 平均獲利幅度 | {trade_analysis.get('avg_win_percent', 0)}% |
| 平均虧損幅度 | {trade_analysis.get('avg_loss_percent', 0)}% |
| 平衡交易次數 | {trade_analysis.get('break_even_trades', 0)} |

#### 🏆 最佳/最差交易
"""
            if trade_analysis.get('best_trade'):
                best = trade_analysis['best_trade']
                content += f"- **最佳交易**: {best.symbol} ({best.entry_date} - {best.exit_date}) +{best.pnl:,} TWD ({best.pnl_percent}%)\n"

            if trade_analysis.get('worst_trade'):
                worst = trade_analysis['worst_trade']
                content += f"- **最差交易**: {worst.symbol} ({worst.entry_date} - {worst.exit_date}) {worst.pnl:,} TWD ({worst.pnl_percent}%)\n"

        # Add signal analysis
        content += f"""
---

## 🔍 訊號分析

### 📡 訊號統計
| 訊號類型 | 數量 | 比例 |
|----------|------|------|
| 買進訊號 | {signal_analysis.get('buy_count', 0)} | {signal_analysis.get('buy_percentage', 0):.1f}% |
| 賣出訊號 | {signal_analysis.get('sell_count', 0)} | {signal_analysis.get('sell_percentage', 0):.1f}% |
| 觀察訊號 | {signal_analysis.get('watch_count', 0)} | {signal_analysis.get('watch_percentage', 0):.1f}% |
| **總計** | **{signal_analysis.get('total_signals', 0)}** | **100%** |

### 🎯 訊號效果分析
"""

        if 'signal_performance' in signal_analysis:
            for signal_name, performance in signal_analysis['signal_performance'].items():
                traded = performance.get('traded', 0)
                rate = performance.get('success_rate')
                if rate is not None:
                    rate_str = f"{rate:.1f}%"
                else:
                    rate_str = "無交易資料"
                content += (
                    f"- **{signal_name}**: 產生訊號 {performance['count']} 次，"
                    f"觸發交易 {traded} 次，實際勝率 {rate_str}\n"
                )

        # Add risk analysis
        if 'detailed_risk_analysis' in summary:
            risk_analysis = summary['detailed_risk_analysis']
            content += f"""
---

## ⚠️ 風險分析

### 📉 詳細風險指標
| 指標 | 數值 |
|------|------|
| 日平均報酬 | {risk_analysis.get('avg_daily_return', 0)}% |
| 日波動率 | {risk_analysis.get('daily_volatility', 0)}% |
| 年化波動率 | {risk_analysis.get('annualized_volatility', 0)}% |
| 最佳單日 | {risk_analysis.get('best_day', 0)}% |
| 最差單日 | {risk_analysis.get('worst_day', 0)}% |
| VaR (95%) | {risk_analysis.get('var_95', 0)}% |
| CVaR (95%) | {risk_analysis.get('cvar_95', 0)}% |
| Sortino比率 | {risk_analysis.get('sortino_ratio', 0)} |
| Calmar比率 | {risk_analysis.get('calmar_ratio', 0)} |
"""

        # --- Data-driven optimization section ---
        win_rate = result.win_rate
        profit_factor = result.profit_factor
        sharpe = result.sharpe_ratio
        avg_win = result.avg_win
        avg_loss = result.avg_loss

        content += """
---

## 📋 策略優化建議

### 🎯 績效診斷

#### ✅ 策略強項
"""
        strengths = []
        if win_rate >= Decimal('50'):
            strengths.append(f"- **勝率 {win_rate}%**：多於一半的交易獲利，選股方向正確")
        if profit_factor >= Decimal('1.5'):
            strengths.append(f"- **獲利因子 {profit_factor}**：每虧 1 元可賺回 {profit_factor} 元")
        if sharpe >= Decimal('1'):
            strengths.append(f"- **夏普比率 {sharpe}**：風險調整後報酬良好")
        if avg_win and avg_loss and abs(avg_win) > abs(avg_loss):
            strengths.append(f"- **報酬風險比 > 1**：平均獲利 {avg_win} > 平均虧損絕對值 {abs(avg_loss)}")
        if not strengths:
            strengths.append("- 目前尚無顯著強項，策略需全面調整")
        content += "\n".join(strengths) + "\n"

        content += "\n#### 🔧 數據驅動改進建議\n\n"

        if win_rate < Decimal('45'):
            content += (
                f"1. **提高進場品質（勝率 {win_rate}% 偏低）**\n"
                f"   - 要求多個訊號同時觸發才進場（目前單一訊號即進場）\n"
                f"   - 加入成交量確認：進場當天成交量需 > 20日均量 1.5 倍\n"
                f"   - 排除整體趨勢向下的股票（股價在 60MA 以下不做多）\n\n"
            )
        else:
            content += (
                f"1. **維持進場品質（勝率 {win_rate}%）**\n"
                f"   - 目前訊號過濾已具基礎，可增加訊號強度門檻\n\n"
            )

        if profit_factor < Decimal('1.0'):
            if avg_win and avg_loss and avg_loss != 0:
                rr_ratio = abs(avg_win / avg_loss)
                content += (
                    f"2. **改善損益比（獲利因子 {profit_factor} < 1，策略整體虧損）**\n"
                    f"   - 平均獲利 {avg_win} / 平均虧損 {avg_loss} = 報酬風險比 {rr_ratio:.2f}\n"
                    f"   - 停損已從 10% 縮至 5%，並加入追蹤停損保留上漲空間\n\n"
                )
        else:
            content += (
                f"2. **損益比良好（獲利因子 {profit_factor}）**\n"
                f"   - 繼續維持停損紀律，避免讓虧損擴大\n\n"
            )

        if 'signal_performance' in signal_analysis:
            best_signal = None
            worst_signal = None
            best_rate = -1.0
            worst_rate = 101.0
            for sig_name, perf in signal_analysis['signal_performance'].items():
                rate = perf.get('success_rate')
                traded = perf.get('traded', 0)
                if rate is None or traded < 5:
                    continue
                if rate > best_rate:
                    best_rate = rate
                    best_signal = (sig_name, traded, rate)
                if rate < worst_rate:
                    worst_rate = rate
                    worst_signal = (sig_name, traded, rate)

            content += "3. **訊號優先順序（基於實際交易勝率）**\n"
            if best_signal:
                content += (
                    f"   - ✅ 優先使用：**{best_signal[0]}**"
                    f"（{best_signal[1]} 次交易，勝率 {best_signal[2]:.1f}%）\n"
                )
            if worst_signal and worst_signal != best_signal:
                content += (
                    f"   - ⚠️ 考慮停用：**{worst_signal[0]}**"
                    f"（{worst_signal[1]} 次交易，勝率 {worst_signal[2]:.1f}%）\n"
                )
            if not best_signal:
                content += "   - 訊號交易次數不足，需更多樣本才能判斷\n"
            content += "\n"

        content += """
---

## 📝 免責聲明

本回測報告僅供參考，不構成投資建議。過去績效不代表未來表現，實際投資請謹慎評估風險。

**報告生成工具**: 台股自動交易回測系統 v1.0
**技術支援**: Claude Code AI Assistant

---

*報告結束*
"""

        return content

    def analyze_signals(self, signals: List[TradingSignal], closed_positions: List = None) -> Dict:
        """
        Analyze trading signals performance.

        Args:
            signals: List of trading signals
            closed_positions: Closed Position objects used to compute actual win rates
                              per signal type (requires Position.entry_signal_name).

        Returns:
            Dictionary with signal analysis
        """
        if not signals:
            return {
                'total_signals': 0,
                'buy_count': 0,
                'sell_count': 0,
                'watch_count': 0,
                'buy_percentage': 0,
                'sell_percentage': 0,
                'watch_percentage': 0,
                'signal_performance': {}
            }

        total_signals = len(signals)
        buy_count = len([s for s in signals if s.signal_type.value == 'BUY'])
        sell_count = len([s for s in signals if s.signal_type.value == 'SELL'])
        watch_count = len([s for s in signals if s.signal_type.value == 'WATCH'])

        buy_percentage = (buy_count / total_signals * 100) if total_signals > 0 else 0
        sell_percentage = (sell_count / total_signals * 100) if total_signals > 0 else 0
        watch_percentage = (watch_count / total_signals * 100) if total_signals > 0 else 0

        # Count signals by name
        signal_counts = {}
        for signal in signals:
            name = signal.signal_name
            if name not in signal_counts:
                signal_counts[name] = {'total': 0, 'buy': 0, 'sell': 0}
            signal_counts[name]['total'] += 1
            if signal.signal_type.value == 'BUY':
                signal_counts[name]['buy'] += 1
            elif signal.signal_type.value == 'SELL':
                signal_counts[name]['sell'] += 1

        # Build actual win rates from real trade outcomes
        from decimal import Decimal
        signal_traded: Dict[str, int] = {}
        signal_wins: Dict[str, int] = {}
        if closed_positions:
            for pos in closed_positions:
                name = getattr(pos, 'entry_signal_name', None)
                if not name:
                    continue
                signal_traded[name] = signal_traded.get(name, 0) + 1
                if (pos.pnl or Decimal('0')) > 0:
                    signal_wins[name] = signal_wins.get(name, 0) + 1

        signal_performance = {}
        for name, counts in signal_counts.items():
            traded = signal_traded.get(name, 0)
            wins = signal_wins.get(name, 0)
            success_rate = (wins / traded * 100) if traded > 0 else None
            signal_performance[name] = {
                'count': counts['total'],
                'traded': traded,
                'success_rate': success_rate,
            }

        return {
            'total_signals': total_signals,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'watch_count': watch_count,
            'buy_percentage': buy_percentage,
            'sell_percentage': sell_percentage,
            'watch_percentage': watch_percentage,
            'signal_performance': signal_performance
        }

    def export_all_results(
        self,
        result: BacktestResult,
        signals: List[TradingSignal],
        benchmark_data: Optional[List[StockData]] = None
    ) -> Dict[str, str]:
        """
        Export all backtest results (CSV and Markdown)

        Args:
            result: Backtest result
            signals: Trading signals
            benchmark_data: Benchmark data

        Returns:
            Dictionary with paths to exported files
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        exported_files = {}

        try:
            # Export trades to CSV
            trades_file = self.analyzer.export_trades_to_csv(
                result.trades, f"trades_{timestamp}.csv"
            )
            exported_files['trades_csv'] = trades_file

            # Export portfolio history to CSV
            portfolio_file = self.analyzer.export_portfolio_to_csv(
                result.portfolio_history, f"portfolio_{timestamp}.csv"
            )
            exported_files['portfolio_csv'] = portfolio_file

            # Export signals to CSV
            signals_file = self.export_signals_to_csv(signals, f"signals_{timestamp}.csv")
            exported_files['signals_csv'] = signals_file

            # Generate markdown report
            report_file = self.generate_markdown_report(
                result, signals, benchmark_data, f"report_{timestamp}.md"
            )
            exported_files['markdown_report'] = report_file

            self.logger.info(f"Exported all results with timestamp: {timestamp}")
            return exported_files

        except Exception as e:
            self.logger.error(f"Error exporting results: {e}")
            raise

    def export_signals_to_csv(self, signals: List[TradingSignal], filename: str = None) -> str:
        """
        Export signals to CSV

        Args:
            signals: List of trading signals
            filename: Output filename

        Returns:
            Path to exported file
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"trading_signals_{timestamp}.csv"

        filepath = os.path.join("data", filename)  # Use data directory for CSV files

        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)

        try:
            import csv
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow([
                    'Date', 'Symbol', 'Signal Type', 'Signal Name', 'Price',
                    'Description', 'Strength'
                ])

                # Write signal data
                for signal in signals:
                    writer.writerow([
                        signal.date.strftime('%Y-%m-%d'),
                        signal.symbol,
                        signal.signal_type.value,
                        signal.signal_name,
                        str(signal.price),
                        signal.description,
                        signal.strength
                    ])

            self.logger.info(f"Exported {len(signals)} signals to {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error exporting signals to CSV: {e}")
            raise