"""scripts/download_taifex_tick.py 舊 tick 檔清理"""
import importlib.util
from datetime import date
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parent.parent / "scripts" / "download_taifex_tick.py"
    spec = importlib.util.spec_from_file_location("download_taifex_tick", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _touch(d: Path, *names):
    for n in names:
        (d / n).write_bytes(b"x")


def test_prunes_daily_zips_older_than_retention(tmp_path):
    mod = _load()
    _touch(tmp_path, "Daily_2026_04_17.zip", "Daily_2026_04_18.zip", "Daily_2026_10_15.zip")

    removed = mod.prune_old_ticks(tmp_path, 180, today=date(2026, 10, 15))

    # cutoff = 2026-04-18：早於 cutoff 才刪
    assert removed == ["Daily_2026_04_17.zip"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Daily_2026_04_18.zip", "Daily_2026_10_15.zip"]


def test_keeps_unrelated_and_malformed_files(tmp_path):
    mod = _load()
    _touch(tmp_path, "2025_fut.zip", "Daily_2020_13_40.zip", "Daily_old.zip", "Daily_2020_01_01.zip")

    removed = mod.prune_old_ticks(tmp_path, 180, today=date(2026, 10, 15))

    assert removed == ["Daily_2020_01_01.zip"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2025_fut.zip", "Daily_2020_13_40.zip", "Daily_old.zip"]


def test_zero_retention_disables_pruning(tmp_path):
    mod = _load()
    _touch(tmp_path, "Daily_2020_01_01.zip")

    assert mod.prune_old_ticks(tmp_path, 0, today=date(2026, 10, 15)) == []
    assert (tmp_path / "Daily_2020_01_01.zip").exists()


def test_default_retention_is_180_days():
    from config.settings import settings

    assert settings.download.taifex_tick_retention_days == 180
