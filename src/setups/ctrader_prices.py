"""NIVÅ-feed: read-only OHLC fra Skilling via cTrader Open API.

Eneste kilde for entry/SL/TP-koordinater (K3/§5b). Henter D1-trendbarer, konverterer
til OHLC og lagrer i `store.prices`. READ-ONLY — legger aldri ordre.

Egen, frisk klient (klasse-basert). Protokoll-sekvensen (app-auth → konto-auth →
symbol-liste → trendbarer) er cTraders API-kontrakt; `scripts/ctrader_depth_spike.py`
er referanse for samme sekvens.

Bruk:
    python -m setups.ctrader_prices GOLD EURUSD COFFEE --years 15
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests
from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod
from twisted.internet import reactor

from setups import store
from setups.secrets import get_secret, require_secret

SECRETS_PATH = Path("~/.bedrock/secrets.env").expanduser()
TOKEN_ENDPOINT = "https://connect.spotware.com/apps/token"
D1 = ProtoOATrendbarPeriod.Value("D1")

MS_DAY = 86_400_000
CHUNK_DAYS = 365          # 1 år pr request (under D1-cap)
PRICE_SCALE = 100_000     # cTrader trendbar-priser er heltall = pris × 1e5
TOKEN_ERRORS = {
    "CH_ACCESS_TOKEN_INVALID", "ACCESS_TOKEN_EXPIRED",
    "CH_ACCESS_TOKEN_EXPIRED", "OA_AUTH_TOKEN_EXPIRED",
}


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def iso(self) -> str:
        return self.ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _trendbar_to_bar(tb) -> Bar:
    low = tb.low / PRICE_SCALE
    return Bar(
        ts=datetime.fromtimestamp(tb.utcTimestampInMinutes * 60, tz=UTC),
        open=(tb.low + tb.deltaOpen) / PRICE_SCALE,
        high=(tb.low + tb.deltaHigh) / PRICE_SCALE,
        low=low,
        close=(tb.low + tb.deltaClose) / PRICE_SCALE,
        volume=float(tb.volume),
    )


def _now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)


class CTraderPrices:
    """Henter D1-OHLC for et sett symboler i én reactor-kjøring."""

    def __init__(self, symbols: Sequence[str], years: int = 15, host_kind: str = "demo",
                 period_name: str = "D1", chunk_days: int = 365) -> None:
        self.symbols = list(symbols)
        self.max_chunks = max(1, years)
        self.period = ProtoOATrendbarPeriod.Value(period_name)
        self.tf = period_name
        self.chunk_days = chunk_days       # vindu pr request (mindre for intraday-cap)
        self.host_kind = host_kind
        host = (EndPoints.PROTOBUF_DEMO_HOST if host_kind == "demo"
                else EndPoints.PROTOBUF_LIVE_HOST)
        self.account_id = int(require_secret("CTRADER_ACCOUNT_ID"))
        self._token = require_secret("CTRADER_ACCESS_TOKEN")
        self._refreshed = False
        self.client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.results: dict[str, list[Bar]] = {s: [] for s in self.symbols}
        self.error: str | None = None
        # Per-symbol paginerings-tilstand.
        self._queue: list[tuple[str, int]] = []
        self._i = 0
        self._to_ms = 0
        self._chunk = 0

    # --- offentlig ---
    def run(self) -> dict[str, list[Bar]]:
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(lambda _c, _r: self._stop())
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()
        reactor.callLater(180, self._stop)
        reactor.run()
        return self.results

    # --- auth ---
    def _send(self, msg):
        d = self.client.send(msg, responseTimeoutInSeconds=30)
        d.addErrback(lambda f: setattr(self, "error", str(f)))
        return d

    def _on_connected(self, _c) -> None:
        req = ProtoOAApplicationAuthReq()
        req.clientId = require_secret("CTRADER_CLIENT_ID")
        req.clientSecret = require_secret("CTRADER_CLIENT_SECRET")
        self._send(req)

    def _auth_account(self) -> None:
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = self.account_id
        req.accessToken = self._token
        self._send(req)

    def _refresh_token(self) -> bool:
        rt = get_secret("CTRADER_REFRESH_TOKEN")
        if not rt:
            return False
        r = requests.post(TOKEN_ENDPOINT, data={
            "grant_type": "refresh_token", "refresh_token": rt,
            "client_id": require_secret("CTRADER_CLIENT_ID"),
            "client_secret": require_secret("CTRADER_CLIENT_SECRET"),
        }, timeout=15)
        body = r.json() if r.status_code == 200 else {}
        if "access_token" not in body:
            self.error = f"token-refresh feilet: {r.status_code}"
            return False
        self._token = body["access_token"]
        self._persist_tokens(body["access_token"], body.get("refresh_token", rt))
        return True

    def _persist_tokens(self, access: str, refresh: str) -> None:
        if not SECRETS_PATH.exists():
            return
        lines = SECRETS_PATH.read_text().splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("CTRADER_ACCESS_TOKEN="):
                lines[i] = f"CTRADER_ACCESS_TOKEN={access}"
            elif ln.startswith("CTRADER_REFRESH_TOKEN="):
                lines[i] = f"CTRADER_REFRESH_TOKEN={refresh}"
        SECRETS_PATH.write_text("\n".join(lines) + "\n")

    # --- meldingsruting ---
    def _on_message(self, _c, message) -> None:
        m = Protobuf.extract(message)
        if isinstance(m, ProtoOAApplicationAuthRes):
            self._auth_account()
        elif isinstance(m, ProtoOAAccountAuthRes):
            req = ProtoOASymbolsListReq()
            req.ctidTraderAccountId = self.account_id
            req.includeArchivedSymbols = False
            self._send(req)
        elif isinstance(m, ProtoOASymbolsListRes):
            self._on_symbols(m)
        elif isinstance(m, ProtoOAGetTrendbarsRes):
            self._on_trendbars(m)
        elif isinstance(m, ProtoOAErrorRes):
            code = getattr(m, "errorCode", "")
            if code in TOKEN_ERRORS and not self._refreshed:
                self._refreshed = True
                if self._refresh_token():
                    self._auth_account()
                    return
            self.error = f"{code}: {getattr(m, 'description', '')}"
            self._stop()

    def _on_symbols(self, res) -> None:
        ids = {s.symbolName: s.symbolId for s in res.symbol}
        for sym in self.symbols:
            if sym in ids:
                self._queue.append((sym, ids[sym]))
            else:
                self.error = f"ukjent symbol: {sym}"
        if not self._queue:
            self._stop()
            return
        self._start_symbol()

    # --- paginering bakover ---
    def _start_symbol(self) -> None:
        self._to_ms = _now_ms()
        self._chunk = 0
        self._send_chunk()

    def _send_chunk(self) -> None:
        _sym, sid = self._queue[self._i]
        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = sid
        req.period = self.period
        req.fromTimestamp = self._to_ms - self.chunk_days * MS_DAY
        req.toTimestamp = self._to_ms
        self._send(req)

    def _on_trendbars(self, res) -> None:
        sym, _sid = self._queue[self._i]
        bars = list(res.trendbar)
        if bars:
            self.results[sym].extend(_trendbar_to_bar(tb) for tb in bars)
            self._chunk += 1
            self._to_ms -= self.chunk_days * MS_DAY
            if self._chunk < self.max_chunks:
                self._send_chunk()
                return
        self._finish_symbol()

    def _finish_symbol(self) -> None:
        self._i += 1
        if self._i < len(self._queue):
            self._start_symbol()
        else:
            self._stop()

    def _stop(self) -> None:
        try:
            if reactor.running:
                reactor.stop()
        except Exception:
            pass


def store_bars(conn, symbol: str, bars: Sequence[Bar], tf: str = "D1") -> int:
    """Lagre OHLC i datastoren (idempotent pr (symbol, tf, ts))."""
    rows = sorted({b.iso(): b for b in bars}.values(), key=lambda b: b.ts)
    conn.executemany(
        "INSERT OR REPLACE INTO prices(symbol,tf,ts,open,high,low,close,volume)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [(symbol, tf, b.iso(), b.open, b.high, b.low, b.close, b.volume) for b in rows],
    )
    return len(rows)


def fetch_and_store(symbols: Sequence[str], years: int = 15, host_kind: str = "demo",
                    db_path: Path | str = store.DEFAULT_DB_PATH,
                    period_name: str = "D1", chunk_days: int = 365) -> dict[str, int]:
    """Hent OHLC for valgt periode og persister. Returnerer radtelling pr symbol."""
    fetcher = CTraderPrices(symbols, years=years, host_kind=host_kind,
                            period_name=period_name, chunk_days=chunk_days)
    results = fetcher.run()
    if fetcher.error and not any(results.values()):
        raise RuntimeError(f"cTrader-feil: {fetcher.error}")
    counts: dict[str, int] = {}
    with store.connect(db_path) as conn:
        store.init_db(conn)
        for sym, bars in results.items():
            counts[sym] = store_bars(conn, sym, bars, tf=period_name)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Hent read-only D1-OHLC fra Skilling (cTrader).")
    ap.add_argument("symbols", nargs="+", help="Skilling-tickere, f.eks. GOLD EURUSD COFFEE")
    ap.add_argument("--years", type=int, default=15, help="antall chunk-vinduer bakover")
    ap.add_argument("--host", choices=["demo", "live"], default="demo")
    ap.add_argument("--period", default="D1", help="trendbar-periode (D1, H1, M30, …)")
    ap.add_argument("--chunk-days", type=int, default=365, help="vindu pr request")
    ap.add_argument("--db", default=str(store.DEFAULT_DB_PATH))
    args = ap.parse_args()

    counts = fetch_and_store(args.symbols, years=args.years, host_kind=args.host,
                             db_path=args.db, period_name=args.period, chunk_days=args.chunk_days)
    print(f"Hentet {args.period}-OHLC:")
    for sym, n in counts.items():
        print(f"  {sym}: {n} barer")


if __name__ == "__main__":
    main()
