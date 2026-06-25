"""
Unit tests for run_signals AI 二次過濾失敗時的退回行為

AI 二次過濾為「加分」功能，其失敗（如 OpenRouter 額度不足 402、逾時）
不應讓整個訊號 job/workflow 失敗、也不應讓當日訊號完全漏發。
失敗時應退回發送原始 P1 訊號。
"""
import os
import sys
from argparse import Namespace

import pytest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces.cli import signals_main


def _args(send_telegram=True, ai_filter=True, watch=False):
    return Namespace(send_telegram=send_telegram, ai_filter=ai_filter, watch=watch)


def _patch_scan(monkeypatch, result=None):
    result = result or {"target_date": "2026-06-25", "buy": [], "sell": [], "watch": [], "total_scanned": 1}
    scanner = MagicMock()
    scanner.scan_today.return_value = result
    monkeypatch.setattr(signals_main, "SignalsScanner", lambda: scanner)
    monkeypatch.setattr(signals_main, "display_signals", lambda *a, **k: None)
    monkeypatch.setattr(signals_main, "save_signals_history",
                        lambda r: signals_main.PROJECT_ROOT / "data/signals_log/x.json")
    return result


class TestAIFilterFallback:
    def test_ai_failure_falls_back_to_plain_signals(self, monkeypatch):
        """AI 過濾失敗 + 退回訊號發送成功 → 不應 sys.exit（workflow 不失敗）"""
        _patch_scan(monkeypatch)
        monkeypatch.setattr(signals_main, "run_ai_analysis", lambda *a, **k: False)

        notifier = MagicMock()
        notifier.send_message.return_value = True
        monkeypatch.setattr(signals_main, "TelegramNotifier", lambda: notifier)
        monkeypatch.setattr(signals_main, "format_for_telegram", lambda r: ["chunk1"])

        # 不應拋 SystemExit
        signals_main.run_signals(_args())
        # 確認有退回發送原始訊號
        notifier.send_message.assert_called_once_with("chunk1")

    def test_ai_failure_and_fallback_send_fails_exits(self, monkeypatch):
        """AI 過濾失敗 + 退回訊號也發送失敗 → 才 sys.exit(1)"""
        _patch_scan(monkeypatch)
        monkeypatch.setattr(signals_main, "run_ai_analysis", lambda *a, **k: False)

        notifier = MagicMock()
        notifier.send_message.return_value = False
        monkeypatch.setattr(signals_main, "TelegramNotifier", lambda: notifier)
        monkeypatch.setattr(signals_main, "format_for_telegram", lambda r: ["chunk1"])

        with pytest.raises(SystemExit) as exc:
            signals_main.run_signals(_args())
        assert exc.value.code == 1

    def test_ai_success_no_fallback(self, monkeypatch):
        """AI 過濾成功 → 不應觸發退回（run_ai_analysis 內部已負責發送）"""
        _patch_scan(monkeypatch)
        monkeypatch.setattr(signals_main, "run_ai_analysis", lambda *a, **k: True)

        notifier = MagicMock()
        monkeypatch.setattr(signals_main, "TelegramNotifier", lambda: notifier)
        fmt = MagicMock(return_value=["chunk1"])
        monkeypatch.setattr(signals_main, "format_for_telegram", fmt)

        signals_main.run_signals(_args())
        # 成功路徑不應走退回的 format_for_telegram / send
        notifier.send_message.assert_not_called()

    def test_ai_failure_without_telegram_does_not_exit(self, monkeypatch):
        """未開 telegram 時 AI 失敗不應 exit（純本地執行）"""
        _patch_scan(monkeypatch)
        monkeypatch.setattr(signals_main, "run_ai_analysis", lambda *a, **k: False)
        # 無 send_telegram → 不應有退回發送
        signals_main.run_signals(_args(send_telegram=False))
