"""SqueezeMetrics-parser (DIX/GEX) — ren CSV-parsing uten nett."""

from __future__ import annotations

from setups.fetch.squeeze import parse_dix_csv

CSV = (
    "date,price,dix,gex\n"
    "2011-05-02,1361.22,0.3788,1897312571.49\n"
    "2026-06-15,7554.29,0.4511,6798412328.42\n"
    "2026-06-16,7560.00,,bad\n"          # ufullstendig/ugyldig → hoppes
)


def test_parse_dix_csv_extracts_dix_and_gex():
    rows = parse_dix_csv(CSV)
    assert len(rows) == 2                          # den ugyldige raden hoppet
    assert rows[0] == ("2011-05-02", 0.3788, 1897312571.49)
    assert rows[1][0] == "2026-06-15" and rows[1][1] == 0.4511


def test_parse_dix_csv_empty():
    assert parse_dix_csv("date,price,dix,gex\n") == []
