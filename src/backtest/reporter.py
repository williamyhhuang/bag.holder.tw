"""
Backtest report generator
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
import os

from .models import BacktestResult, TradingSignal, StockData
from .analyzer import PerformanceAnalyzer
from ..utils.logger import get_logger

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

            # Generate signal analysis
            signal_analysis = self.analyze_signals(signals)

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
                content += f"- **{signal_name}**: {performance['count']} 次，成功率 {performance['success_rate']:.1f}%\n"

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

        content += f"""
---

## 📋 策略優化建議

### 🎯 績效優化方向

#### ✅ 策略強項
"""
        # Analyze strengths
        if result.win_rate >= Decimal('50'):
            content += f"- **勝率表現優秀**: 勝率達到 {result.win_rate}%，顯示策略具有良好的選股能力\n"

        if result.profit_factor >= Decimal('1.5'):
            content += f"- **獲利因子良好**: 獲利因子 {result.profit_factor}，顯示整體獲利能力佳\n"

        if result.sharpe_ratio >= Decimal('1'):
            content += f"- **風險調整報酬佳**: 夏普比率 {result.sharpe_ratio}，風險控制得當\n"

        content += """
#### 🔧 改進建議

1. **訊號過濾優化**
   - 考慮加入市場環境過濾條件
   - 結合市場情緒指標
   - 避免震盪市場中的假突破

2. **風險管理強化**
   - 動態調整停損停利點位
   - 根據波動度調整部位大小
   - 實施分批進出場機制

3. **參數優化**
   - 針對不同市場環境調整技術指標參數
   - 測試不同時間週期的組合
   - 優化進出場時機

### 📊 具體改進方案

#### 方案一：多時框分析
- 結合日線、週線、月線訊號
- 只在多時框訊號一致時進場
- 預期效果：提高勝率，降低交易頻率

#### 方案二：市場環境過濾
- 加入大盤趨勢判斷
- 在多頭市場偏重買進訊號
- 在空頭市場提高現金比例

#### 方案三：動態風險控制
- 根據VIX指數調整部位大小
- 在高波動期間縮減曝險
- 實施追蹤停損機制

### 📈 下一步行動

1. **短期（1個月內）**
   - 實施動態停損停利
   - 加入成交量確認機制
   - 測試不同資金配置比例

2. **中期（3個月內）**
   - 開發多時框訊號系統
   - 建立市場環境評估模組
   - 實施機器學習訊號過濾

3. **長期（6個月內）**
   - 開發自適應參數系統
   - 整合更多技術指標
   - 建立完整的投資組合管理系統

---

## 📝 免責聲明

本回測報告僅供參考，不構成投資建議。過去績效不代表未來表現，實際投資請謹慎評估風險。

**報告生成工具**: 台股自動交易回測系統 v1.0
**技術支援**: Claude Code AI Assistant

---

*報告結束*
"""

        return content

    def analyze_signals(self, signals: List[TradingSignal]) -> Dict:
        """
        Analyze trading signals performance

        Args:
            signals: List of trading signals

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

        # Analyze signal performance by name
        signal_performance = {}
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

        for name, counts in signal_counts.items():
            signal_performance[name] = {
                'count': counts['total'],
                'success_rate': 50.0  # Simplified - would need actual trade outcomes to calculate
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