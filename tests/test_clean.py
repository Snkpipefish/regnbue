"""Datavask: reparerer 10er-potens skala-glitcher uten å røre ekte bevegelser."""

from __future__ import annotations

from setups import store
from setups.clean import clean_symbol


def _seed(conn, closes):
    for i, c in enumerate(closes):
        ts = f"2020-01-{i+1:02d}T00:00:00Z"
        conn.execute(
            "INSERT INTO prices(symbol,tf,ts,open,high,low,close) VALUES ('X','D1',?,?,?,?,?)",
            (ts, c, c, c, c),
        )


def test_repairs_scale_glitches(tmp_path):
    # Nivå ~2000 med annenhver bar feilnotert på ×0.1 (200) — slik SPX500-feilen så ut.
    good = 2000.0
    closes = []
    for i in range(40):
        closes.append(good * (0.1 if (10 <= i <= 25 and i % 2 == 0) else 1.0))
    with store.connect(tmp_path / "c.db") as conn:
        store.init_db(conn)
        _seed(conn, closes)
        n = clean_symbol(conn, "X")
        fixed = [r[0] for r in conn.execute(
            "SELECT close FROM prices WHERE symbol='X' ORDER BY ts")]
    assert n >= 8
    # Ingen bar skal lenger ligge en 10x unna nivået.
    assert all(1000 < c < 4000 for c in fixed)


def test_leaves_real_moves_untouched(tmp_path):
    # En ekte 8% bevegelse (ingen 10x-faktor passer) skal IKKE røres.
    closes = [100.0] * 20 + [108.0] + [108.0] * 19
    with store.connect(tmp_path / "c.db") as conn:
        store.init_db(conn)
        _seed(conn, closes)
        n = clean_symbol(conn, "X")
    assert n == 0
