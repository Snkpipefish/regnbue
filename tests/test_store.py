"""Fase 1: datastore-schema + seed-integritet."""

from __future__ import annotations

import pytest

from setups import seed, store

EXPECTED_TABLES = {
    "cot_positions", "macro_series", "comex_inventory",
    "weather", "etf_holdings", "seed_log",
}


def test_init_db_creates_tables(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        store.init_db(conn)
        assert EXPECTED_TABLES <= store.table_names(conn)
        # Tomt rett etter init.
        assert store.row_count(conn, "cot_positions") == 0


def test_row_count_rejects_unknown_table(tmp_path):
    with store.connect(tmp_path / "t.db") as conn:
        store.init_db(conn)
        with pytest.raises(ValueError):
            store.row_count(conn, "no_such_table")


@pytest.mark.skipif(not seed.BEDROCK_DB.exists(), reason="bedrock.db ikke tilgjengelig")
def test_seed_integrity(tmp_path):
    db = tmp_path / "seeded.db"
    counts = seed.seed(db)

    # Hver bias-kategori skal ha fått data for MVP-instrumentene.
    for table in ("cot_positions", "macro_series", "comex_inventory", "weather", "etf_holdings"):
        assert counts[table] > 0, f"ingen rader seedet til {table}"

    with store.connect(db) as conn:
        # Alle 3 MVP-markeder har COT-posisjoner.
        markets = {r[0] for r in conn.execute("SELECT DISTINCT market FROM cot_positions")}
        assert {"Gold", "EURUSD", "Coffee"} <= markets

        # Ingen rad mangler både long_spec og short_spec (ellers er mappingen feil).
        bad = conn.execute(
            "SELECT COUNT(*) FROM cot_positions WHERE long_spec IS NULL AND short_spec IS NULL"
        ).fetchone()[0]
        assert bad == 0

        # Realrente-byggesteiner for gull er på plass.
        series = {r[0] for r in conn.execute("SELECT DISTINCT series_id FROM macro_series")}
        assert {"DGS10", "T10YIE"} <= series

        gld = conn.execute("SELECT COUNT(*) FROM etf_holdings WHERE ticker='gld'").fetchone()[0]
        gold = conn.execute(
            "SELECT COUNT(*) FROM comex_inventory WHERE metal='gold'"
        ).fetchone()[0]
        assert gld > 0 and gold > 0


@pytest.mark.skipif(not seed.BEDROCK_DB.exists(), reason="bedrock.db ikke tilgjengelig")
def test_seed_is_idempotent(tmp_path):
    db = tmp_path / "seeded.db"
    first = seed.seed(db)
    second = seed.seed(db)
    assert first == second  # INSERT OR REPLACE → ingen duplisering
