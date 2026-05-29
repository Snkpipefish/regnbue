"""Fase 2: OHLC-konvertering + lagring (uten nettverk)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC

from setups import store
from setups.ctrader_prices import Bar, _trendbar_to_bar, store_bars


@dataclass
class FakeTrendbar:
    low: int
    deltaOpen: int
    deltaHigh: int
    deltaClose: int
    volume: int
    utcTimestampInMinutes: int


def test_trendbar_to_bar_scales_and_offsets():
    # low=2000.00, open=+10, high=+25, close=+5 (priser × 1e5).
    tb = FakeTrendbar(
        low=200_000_000, deltaOpen=1_000_000, deltaHigh=2_500_000,
        deltaClose=500_000, volume=123, utcTimestampInMinutes=29_000_000,
    )
    bar = _trendbar_to_bar(tb)
    assert bar.low == 2000.0
    assert bar.open == 2010.0
    assert bar.high == 2025.0
    assert bar.close == 2005.0
    assert bar.volume == 123.0
    # OHLC-invariant.
    assert bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
    assert bar.iso().endswith("Z")


def test_store_bars_persists_and_dedupes(tmp_path):
    from datetime import datetime
    bars = [
        Bar(datetime(2026, 1, 1, tzinfo=UTC), 1, 2, 0.5, 1.5, 10),
        Bar(datetime(2026, 1, 2, tzinfo=UTC), 1.5, 2.5, 1, 2, 11),
        # duplikat av dag 1 (skal kollapse på PK).
        Bar(datetime(2026, 1, 1, tzinfo=UTC), 9, 9, 9, 9, 99),
    ]
    db = tmp_path / "p.db"
    with store.connect(db) as conn:
        store.init_db(conn)
        store_bars(conn, "GOLD", bars)
    with store.connect(db) as conn:
        rows = conn.execute("SELECT ts,close FROM prices ORDER BY ts").fetchall()
    assert len(rows) == 2  # duplikat kollapset
