#!/usr/bin/env python3
"""K1-spike: mål hvor mye D1-historikk Skilling/cTrader faktisk serverer.

READ-ONLY. Plasserer INGEN ordre. Sekvens:
  connect -> ApplicationAuth -> AccountAuth -> SymbolsList ->
  for hvert mål-symbol: paginer D1-trendbarer bakover til tomt svar.

Bruk:  python3 ctrader_depth_spike.py [demo|live]
Krever ctrader-open-api (samme miljø som bedrock-boten) + ~/.bedrock/secrets.env.

Svarer på audit K1: antall år D1 pr instrument + ev. per-request-cap.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
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

SECRETS = Path("~/.bedrock/secrets.env").expanduser()
TOKEN_ENDPOINT = "https://connect.spotware.com/apps/token"
D1 = ProtoOATrendbarPeriod.Value("D1")

# Mål-symboler: gull (lav basis), ett indeks-CFD, ett olje-CFD. Kandidat-navn
# matches mot meglerens symbolName (første treff vinner).
TARGETS = {
    "Gull":  ["XAUUSD", "GOLD", "Gold"],
    "Indeks": ["US500", "SP500", "SPX500", "US 500", "USA500", "S&P 500"],
    "Olje":  ["OIL WTI", "OIL BRENT", "OIL-WTI", "XTIUSD", "WTI", "USOIL"],
}

CHUNK_DAYS = 365          # 1 år pr request (godt under D1-cap)
MAX_CHUNKS = 30           # opp til ~30 år bakover
MS_DAY = 86_400_000


def load_secrets() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in SECRETS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


S = load_secrets()
HOST_KIND = sys.argv[1] if len(sys.argv) > 1 else "demo"
HOST = EndPoints.PROTOBUF_DEMO_HOST if HOST_KIND == "demo" else EndPoints.PROTOBUF_LIVE_HOST
ACCOUNT_ID = int(S["CTRADER_ACCOUNT_ID"])
ACCESS = {"token": S["CTRADER_ACCESS_TOKEN"]}  # mutbar (refresh)

client = Client(HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)

state = {"queue": [], "i": 0, "to_ms": 0, "earliest": None, "total": 0, "chunk": 0, "refreshed": False}


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def send(msg):
    d = client.send(msg, responseTimeoutInSeconds=30)
    d.addErrback(lambda f: print(f"[SEND-ERR] {f}"))
    return d


def refresh_token() -> bool:
    print("[AUTH] access token utløpt — forsøker refresh...")
    rt = S.get("CTRADER_REFRESH_TOKEN")
    if not rt:
        print("[AUTH] ingen refresh-token — avbryt.")
        return False
    r = requests.post(TOKEN_ENDPOINT, data={
        "grant_type": "refresh_token", "refresh_token": rt,
        "client_id": S["CTRADER_CLIENT_ID"], "client_secret": S["CTRADER_CLIENT_SECRET"],
    }, timeout=15)
    if r.status_code != 200 or "access_token" not in r.json():
        print(f"[AUTH] refresh feilet: {r.status_code} {r.text[:200]}")
        return False
    body = r.json()
    ACCESS["token"] = body["access_token"]
    # Persister nye tokens (Spotware roterer begge) så bedrock holder seg i sync.
    txt = SECRETS.read_text().splitlines()
    new_rt = body.get("refresh_token", rt)
    for i, ln in enumerate(txt):
        if ln.startswith("CTRADER_ACCESS_TOKEN="):
            txt[i] = f"CTRADER_ACCESS_TOKEN={body['access_token']}"
        elif ln.startswith("CTRADER_REFRESH_TOKEN="):
            txt[i] = f"CTRADER_REFRESH_TOKEN={new_rt}"
    SECRETS.write_text("\n".join(txt) + "\n")
    print("[AUTH] tokens refreshet + persistert.")
    return True


def on_connected(_c):
    print(f"[TILKOBLET] {HOST}:{EndPoints.PROTOBUF_PORT} ({HOST_KIND})")
    req = ProtoOAApplicationAuthReq()
    req.clientId = S["CTRADER_CLIENT_ID"]
    req.clientSecret = S["CTRADER_CLIENT_SECRET"]
    send(req)


def auth_account():
    req = ProtoOAAccountAuthReq()
    req.ctidTraderAccountId = ACCOUNT_ID
    req.accessToken = ACCESS["token"]
    send(req)


def on_message(_c, message):
    m = Protobuf.extract(message)
    if isinstance(m, ProtoOAApplicationAuthRes):
        print("[AUTH] app OK -> konto-auth")
        auth_account()
    elif isinstance(m, ProtoOAAccountAuthRes):
        print(f"[AUTH] konto {ACCOUNT_ID} OK -> symbol-liste")
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = ACCOUNT_ID
        req.includeArchivedSymbols = False
        send(req)
    elif isinstance(m, ProtoOASymbolsListRes):
        on_symbols(m)
    elif isinstance(m, ProtoOAGetTrendbarsRes):
        on_trendbars(m)
    elif isinstance(m, ProtoOAErrorRes):
        code = getattr(m, "errorCode", "")
        print(f"[FEIL] {code}: {getattr(m, 'description', '')}")
        if code in ("CH_ACCESS_TOKEN_INVALID", "ACCESS_TOKEN_EXPIRED",
                    "CH_ACCESS_TOKEN_EXPIRED", "OA_AUTH_TOKEN_EXPIRED") and not state["refreshed"]:
            state["refreshed"] = True
            if refresh_token():
                auth_account()
                return
        stop()


def on_symbols(res):
    names = {s.symbolName: s.symbolId for s in res.symbol}
    print(f"[SYMBOLER] {len(names)} totalt")
    queue = []
    for label, cands in TARGETS.items():
        hit = next((c for c in cands if c in names), None)
        if hit:
            queue.append((label, hit, names[hit]))
            print(f"  {label}: '{hit}' (sid={names[hit]})")
        else:
            # vis nærliggende navn for å hjelpe matching
            near = [n for n in names if any(t.lower() in n.lower() for t in ("gold", "xau", "500", "spx", "oil", "wti", "us30", "nas"))]
            print(f"  {label}: INGEN match. Kandidater i listen: {sorted(near)[:15]}")
    if not queue:
        print("[STOPP] fant ingen mål-symboler.")
        stop()
        return
    state["queue"] = queue
    start_target()


def start_target():
    state["to_ms"] = now_ms()
    state["earliest"] = None
    state["total"] = 0
    state["chunk"] = 0
    send_chunk()


def send_chunk():
    _, name, sid = state["queue"][state["i"]]
    to_ms = state["to_ms"]
    from_ms = to_ms - CHUNK_DAYS * MS_DAY
    req = ProtoOAGetTrendbarsReq()
    req.ctidTraderAccountId = ACCOUNT_ID
    req.symbolId = sid
    req.period = D1
    req.fromTimestamp = from_ms
    req.toTimestamp = to_ms
    send(req)


def on_trendbars(res):
    label, sname, _sid = state["queue"][state["i"]]
    bars = list(res.trendbar)
    if bars:
        state["total"] += len(bars)
        e = min(b.utcTimestampInMinutes for b in bars)
        if state["earliest"] is None or e < state["earliest"]:
            state["earliest"] = e
        state["chunk"] += 1
        state["to_ms"] = state["to_ms"] - CHUNK_DAYS * MS_DAY
        if state["chunk"] < MAX_CHUNKS:
            send_chunk()
            return
    finish_target(label, sname)


def finish_target(label, sname):
    e = state["earliest"]
    if e:
        edate = datetime.fromtimestamp(e * 60, tz=timezone.utc).date()
        years = (now_ms() / 1000 - e * 60) / (365.25 * 86400)
        print(f"[RESULTAT] {label} ({sname}): {state['total']} D1-barer, "
              f"eldste {edate} (~{years:.1f} år)")
    else:
        print(f"[RESULTAT] {label} ({sname}): INGEN barer returnert")
    state["i"] += 1
    if state["i"] < len(state["queue"]):
        start_target()
    else:
        print("[FERDIG] depth-spike komplett.")
        stop()


def stop():
    try:
        if reactor.running:
            reactor.stop()
    except Exception:
        pass


def on_disconnected(_c, reason):
    print(f"[FRAKOBLET] {reason}")
    stop()


client.setConnectedCallback(on_connected)
client.setDisconnectedCallback(on_disconnected)
client.setMessageReceivedCallback(on_message)
client.startService()
reactor.callLater(120, lambda: (print("[TIMEOUT] 120s"), stop()))
reactor.run()
