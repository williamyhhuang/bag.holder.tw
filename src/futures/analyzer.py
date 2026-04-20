"""
Taiwan futures market analyzer
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import requests
from pathlib import Path

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.utils.logger import get_logger
from config.settings import settings
from src.telegram.simple_notifier import TelegramNotifier

logger = get_logger(__name__)

class FuturesAnalyzer:
    """Analyzer for Taiwan futures market (focusing on TAIEX Mini futures)"""

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.telegram = TelegramNotifier()

    def get_futures_data_from_fubon(self) -> Optional[Dict]:
        """
        Get MTX futures data.
        Tries TAIFEX public CSV endpoint first; Fubon SDK integration is a future enhancement.

        Returns:
            Dict with futures data or None
        """
        result = self._get_mtx_from_taifex()
        if result:
            return result

        self.logger.warning("Fubon API integration not fully implemented, TAIFEX fetch also failed")
        return None

    def _get_mtx_from_taifex(self) -> Optional[Dict]:
        """
        Fetch MTX near-month futures data from TAIFEX public CSV download API.
        Tries today and up to 5 previous calendar days to handle weekends/holidays.

        Returns:
            Dict with futures data or None
        """
        try:
            import io, csv as csvmod
            today = datetime.now().date()

            for offset in range(6):
                query_date = today - timedelta(days=offset)
                # Skip weekends
                if query_date.weekday() >= 5:
                    continue
                date_str = query_date.strftime('%Y/%m/%d')
                r = requests.post(
                    'https://www.taifex.com.tw/cht/3/futDataDown',
                    data={
                        'down_type': '1',
                        'commodity_id': 'MTX',
                        'queryStartDate': date_str,
                        'queryEndDate': date_str,
                    },
                    headers={
                        'User-Agent': 'Mozilla/5.0',
                        'Referer': 'https://www.taifex.com.tw/cht/3/futDataDown',
                    },
                    timeout=10
                )
                r.raise_for_status()
                text = r.content.decode('big5', errors='replace')
                rows = list(csvmod.reader(io.StringIO(text)))

                # Filter: regular session only, standard monthly contracts (no 'W' in expiry)
                regular_monthly = [
                    row for row in rows[1:]
                    if len(row) > 11
                    and (len(row) <= 17 or row[17].strip() == '一般')
                    and 'W' not in row[2]
                    and '/' not in row[2]
                    and row[6].strip() not in ('', '-')
                ]

                if not regular_monthly:
                    continue

                # Pick near-month contract (earliest expiry with highest volume)
                def sort_key(row):
                    try:
                        vol = int(row[9].replace(',', '')) if row[9].strip() not in ('', '-') else 0
                    except ValueError:
                        vol = 0
                    return (row[2], -vol)

                regular_monthly.sort(key=sort_key)
                best = regular_monthly[0]

                def to_float(s):
                    try:
                        return float(s.replace(',', '').replace('+', '').replace('%', ''))
                    except (ValueError, AttributeError):
                        return 0.0

                close_price = to_float(best[6])
                change = to_float(best[7])
                change_pct_str = best[8].strip().replace('%', '').replace('+', '')
                try:
                    change_pct = float(change_pct_str)
                except ValueError:
                    change_pct = (change / (close_price - change) * 100) if (close_price - change) else 0.0
                volume = int(best[9].replace(',', '')) if best[9].strip() not in ('', '-') else 0
                open_interest = int(best[11].replace(',', '')) if len(best) > 11 and best[11].strip() not in ('', '-') else 0

                self.logger.info(f"MTX data from TAIFEX ({date_str}): {best[2]} close={close_price}")
                return {
                    'symbol': f"MTX {best[2]}",
                    'current_price': close_price,
                    'change': change,
                    'change_percent': change_pct,
                    'volume': volume,
                    'open_interest': open_interest,
                    'high': to_float(best[4]),
                    'low': to_float(best[5]),
                    'open': to_float(best[3]),
                    'data_date': date_str,
                    'timestamp': datetime.now(),
                }

            self.logger.warning("No MTX data found from TAIFEX for recent trading days")
            return None

        except Exception as e:
            self.logger.error(f"Error fetching MTX data from TAIFEX: {e}")
            return None

    def get_taiex_index_data(self) -> Optional[Dict]:
        """
        Get TAIEX index data for comparison.
        Tries TWSE public API first, then falls back to yfinance.

        Returns:
            Dict with TAIEX data or None
        """
        # Try TWSE public API first
        result = self._get_taiex_from_twse()
        if result:
            return result

        # Fallback to yfinance
        return self._get_taiex_from_yfinance()

    def _get_taiex_from_twse(self) -> Optional[Dict]:
        """Get TAIEX data from TWSE public API"""
        try:
            today = datetime.now().strftime('%Y%m%d')
            url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={today}&type=MS"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Look for TAIEX in the stat table (index code 0001)
            for table in data.get('tables', []):
                for row in table.get('data', []):
                    if len(row) >= 5 and '加權股價指數' in str(row[0]):
                        try:
                            close_price = float(str(row[1]).replace(',', ''))
                            change_str = str(row[3]).replace(',', '').replace('+', '')
                            change = float(change_str) if change_str not in ('', '--') else 0.0
                            prev_close = close_price - change
                            change_pct = (change / prev_close * 100) if prev_close else 0.0
                            return {
                                'symbol': 'TAIEX',
                                'current_price': close_price,
                                'change': change,
                                'change_percent': change_pct,
                                'volume': 0,
                                'high': close_price,
                                'low': close_price,
                                'timestamp': datetime.now()
                            }
                        except (ValueError, IndexError):
                            continue
            return None
        except Exception as e:
            self.logger.warning(f"TWSE API unavailable: {e}")
            return None

    def _get_taiex_from_yfinance(self) -> Optional[Dict]:
        """Get TAIEX data from yfinance"""
        try:
            import yfinance as yf

            taiex = yf.Ticker("^TWII")
            hist = taiex.history(period="5d")

            if hist.empty:
                self.logger.warning("No TAIEX data available from yfinance")
                return None

            latest = hist.iloc[-1]
            previous = hist.iloc[-2] if len(hist) > 1 else latest

            change = latest['Close'] - previous['Close']
            change_pct = (change / previous['Close']) * 100

            return {
                'symbol': 'TAIEX',
                'current_price': latest['Close'],
                'change': change,
                'change_percent': change_pct,
                'volume': latest['Volume'],
                'high': latest['High'],
                'low': latest['Low'],
                'timestamp': datetime.now()
            }

        except Exception as e:
            self.logger.error(f"Error getting TAIEX data: {e}")
            return None

    def calculate_technical_analysis(self, price_data: List[float]) -> Dict:
        """
        Calculate technical analysis indicators

        Args:
            price_data: List of recent prices

        Returns:
            Dict with technical indicators
        """
        try:
            if len(price_data) < 5:
                return {}

            df = pd.Series(price_data)

            # Simple moving averages
            ma5 = df.rolling(window=5).mean().iloc[-1] if len(df) >= 5 else None
            ma20 = df.rolling(window=20).mean().iloc[-1] if len(df) >= 20 else None

            # Support and resistance (simple implementation)
            recent_high = df.max()
            recent_low = df.min()

            current_price = price_data[-1]

            # Trend analysis
            if ma5 and ma20:
                if ma5 > ma20:
                    trend = "上升"
                elif ma5 < ma20:
                    trend = "下降"
                else:
                    trend = "橫盤"
            else:
                # Simple trend based on price movement
                if len(price_data) >= 3:
                    recent_change = price_data[-1] - price_data[-3]
                    trend = "上升" if recent_change > 0 else "下降"
                else:
                    trend = "橫盤"

            return {
                'ma5': ma5,
                'ma20': ma20,
                'support': recent_low,
                'resistance': recent_high,
                'trend': trend,
                'current_price': current_price
            }

        except Exception as e:
            self.logger.error(f"Error calculating technical analysis: {e}")
            return {}

    def generate_trading_recommendation(self, futures_data: Dict, taiex_data: Optional[Dict]) -> Dict:
        """
        Generate trading recommendation based on analysis

        Args:
            futures_data: Futures market data
            taiex_data: TAIEX index data

        Returns:
            Dict with recommendation
        """
        try:
            recommendation = "觀察"  # Default: observe
            confidence = 0.5
            reasoning = []

            # Get current prices
            futures_price = futures_data.get('current_price', 0)
            taiex_price = taiex_data.get('current_price', 0) if taiex_data else 0

            # Price change analysis
            futures_change = futures_data.get('change_percent', 0)
            taiex_change = taiex_data.get('change_percent', 0) if taiex_data else None

            # Volume analysis
            volume = futures_data.get('volume', 0)

            # Basic momentum strategy
            if futures_change > 1 and volume > 100000:
                recommendation = "做多"
                confidence += 0.2
                reasoning.append("期貨價格上漲且成交量充足")

            elif futures_change < -1 and volume > 100000:
                recommendation = "做空"
                confidence += 0.2
                reasoning.append("期貨價格下跌且成交量充足")

            # TAIEX correlation (only when TAIEX data is available)
            if taiex_change is not None and abs(futures_change - taiex_change) < 0.5:
                confidence += 0.1
                reasoning.append("期貨與現貨走勢一致")
            elif taiex_change is None:
                reasoning.append("現貨指數資料暫時無法取得")

            # Risk factors
            if volume < 50000:
                confidence -= 0.2
                reasoning.append("成交量偏低，流動性風險")

            if abs(futures_change) > 3:
                confidence -= 0.1
                reasoning.append("波動較大，風險增加")

            # Final confidence adjustment
            confidence = max(0.1, min(0.9, confidence))

            return {
                'recommendation': recommendation,
                'confidence': confidence,
                'reasoning': reasoning,
                'futures_price': futures_price,
                'taiex_price': taiex_price,
                'futures_change': futures_change,
                'volume': volume,
                'analysis_time': datetime.now()
            }

        except Exception as e:
            self.logger.error(f"Error generating recommendation: {e}")
            return {
                'recommendation': '觀察',
                'confidence': 0.5,
                'reasoning': ['分析錯誤'],
                'analysis_time': datetime.now()
            }

    def run_analysis(self) -> Dict:
        """
        Run complete futures analysis

        Returns:
            Dict with analysis results
        """
        try:
            self.logger.info("Starting futures market analysis...")

            # Get market data
            futures_data = self.get_futures_data_from_fubon()
            taiex_data = self.get_taiex_index_data()

            if not futures_data:
                self.logger.error("Failed to get futures data")
                return {
                    'success': False,
                    'error': 'Unable to fetch futures data'
                }

            if not taiex_data:
                self.logger.warning("TAIEX data unavailable, proceeding without it")

            # Generate recommendation
            recommendation = self.generate_trading_recommendation(futures_data, taiex_data)

            # Combine all analysis
            analysis_result = {
                'success': True,
                'futures_data': futures_data,
                'taiex_data': taiex_data,
                'recommendation': recommendation['recommendation'],
                'confidence': recommendation['confidence'],
                'reasoning': recommendation['reasoning'],
                'analysis_time': datetime.now()
            }

            self.logger.info(f"Analysis complete: {recommendation['recommendation']}")
            return analysis_result

        except Exception as e:
            self.logger.error(f"Error in futures analysis: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def format_analysis_for_telegram(self, analysis: Dict) -> str:
        """
        Format analysis results for Telegram

        Args:
            analysis: Analysis results

        Returns:
            Formatted message string
        """
        try:
            if not analysis.get('success'):
                return f"❌ 期貨分析失敗: {analysis.get('error', '未知錯誤')}"

            futures_data = analysis['futures_data']
            recommendation = analysis['recommendation']
            confidence = analysis['confidence']

            # Recommendation emoji
            rec_emoji = {
                '做多': '📈',
                '做空': '📉',
                '觀察': '👀'
            }.get(recommendation, '👀')

            message = f"🔮 *微台期貨分析*\\n\\n"

            message += f"{rec_emoji} *建議操作: {recommendation}*\\n"
            message += f"📊 信心度: {confidence:.1%}\\n\\n"

            # Market data
            price = futures_data.get('current_price', 0)
            change = futures_data.get('change', 0)
            change_pct = futures_data.get('change_percent', 0)
            volume = futures_data.get('volume', 0)

            message += f"💰 目前價位: {price:,.0f}\\n"
            message += f"📈 漲跌: {change:+.0f} ({change_pct:+.2f}%)\\n"
            message += f"📊 成交量: {volume:,.0f}\\n\\n"

            # Reasoning
            reasoning = analysis.get('reasoning', [])
            if reasoning:
                message += f"💡 *分析依據:*\\n"
                for i, reason in enumerate(reasoning[:3], 1):
                    message += f"{i}\\. {reason}\\n"

            message += f"\\n⏰ 分析時間: {datetime.now().strftime('%H:%M')}"

            return message

        except Exception as e:
            self.logger.error(f"Error formatting analysis: {e}")
            return "❌ 期貨分析格式化失敗"

    def send_analysis_to_telegram(self) -> bool:
        """
        Run analysis and send to Telegram

        Returns:
            True if sent successfully
        """
        try:
            analysis = self.run_analysis()
            message = self.format_analysis_for_telegram(analysis)

            success = self.telegram.send_message(message)
            if success:
                self.logger.info("Futures analysis sent to Telegram")
            else:
                self.logger.error("Failed to send futures analysis to Telegram")

            return success

        except Exception as e:
            self.logger.error(f"Error sending analysis to Telegram: {e}")
            return False