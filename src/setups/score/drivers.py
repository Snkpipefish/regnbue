"""Driver-registry + gjenbrukbare drivere.

Hver driver returnerer en :class:`DriverResult` med ``score`` i [-1, 1] der **positivt =
bullish** for instrumentet. Fingerprintene (YAML) komponerer disse med vekt + params.
Egne implementasjoner; ingen kopiering fra bedrock.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from setups.score.context import ScoreContext


@dataclass
class DriverResult:
    name: str
    ok: bool
    score: float            # [-1, 1], + = bullish
    value: float | None = None
    detail: str = ""
    params: dict = field(default_factory=dict)


DriverFn = Callable[[ScoreContext, dict], DriverResult]
_REGISTRY: dict[str, DriverFn] = {}


def register(name: str) -> Callable[[DriverFn], DriverFn]:
    def deco(fn: DriverFn) -> DriverFn:
        if name in _REGISTRY:
            raise ValueError(f"driver allerede registrert: {name}")
        _REGISTRY[name] = fn
        return fn
    return deco


def get_driver(name: str) -> DriverFn:
    if name not in _REGISTRY:
        raise KeyError(f"ukjent driver: {name} (registrert: {sorted(_REGISTRY)})")
    return _REGISTRY[name]


def registered() -> list[str]:
    return sorted(_REGISTRY)


# --- hjelpere ---
def _sign(bull_when: str) -> int:
    """+1 hvis bullish når verdien er høy, -1 hvis bullish når verdien er lav."""
    return 1 if bull_when == "high" else -1


def _percentile(history: list[float], current: float) -> float:
    """Andel av historikk <= current, i [0, 1]."""
    if not history:
        return 0.5
    return sum(1 for h in history if h <= current) / len(history)


def _within_lookback(series: list[tuple[str, float]], as_of: str,
                     lookback_days: int) -> list[tuple[str, float]]:
    cutoff = (date.fromisoformat(as_of) - timedelta(days=lookback_days)).isoformat()
    return [(d, v) for d, v in series if d >= cutoff]


def _miss(name: str, why: str, params: dict) -> DriverResult:
    return DriverResult(name=name, ok=False, score=0.0, detail=f"mangler data: {why}",
                        params=params)


# --- drivere ---
@register("level_percentile")
def level_percentile(ctx: ScoreContext, params: dict) -> DriverResult:
    """Hvor dagens nivå ligger i sin lookback-fordeling (mean-reversion/regime)."""
    series = _within_lookback(ctx.series(params["series"]), ctx.as_of,
                              params.get("lookback_days", 504))
    if len(series) < 20:
        return _miss("level_percentile", params["series"], params)
    vals = [v for _, v in series]
    cur = vals[-1]
    p = _percentile(vals, cur)
    score = (2 * p - 1) * _sign(params.get("bull_when", "high"))
    return DriverResult("level_percentile", True, round(score, 4), cur,
                        f"{params['series']} nivå {cur:.3g} = p{p*100:.0f}", params)


@register("momentum")
def momentum(ctx: ScoreContext, params: dict) -> DriverResult:
    """Normalisert endring over horisont; trend-driver."""
    series = ctx.series(params["series"])
    horizon = params.get("horizon_days", 21)
    if len(series) < horizon + 20:
        return _miss("momentum", params["series"], params)
    vals = [v for _, v in series]
    changes = [vals[i] - vals[i - horizon] for i in range(horizon, len(vals))]
    cur_change = vals[-1] - vals[-1 - horizon]
    sd = statistics.pstdev(changes) or 1e-9
    z = cur_change / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("momentum", True, round(score, 4), cur_change,
                        f"{params['series']} {horizon}d-endring {cur_change:+.3g} (z={z:+.2f})",
                        params)


@register("price_momentum")
def price_momentum(ctx: ScoreContext, params: dict) -> DriverResult:
    """Pris-momentum på NIVÅ-feeden (z-skåret prosentvis endring); trend-driver.

    Instrument-agnostisk — komplementerer price_vs_sma (nivå vs snitt) med endrings-tempo.
    """
    closes = ctx.closes(params["symbol"], params.get("tf", "D1"))
    horizon = params.get("horizon_days", 20)
    if len(closes) < horizon + 30:
        return _miss("price_momentum", params["symbol"], params)
    vals = [c for _, c in closes]
    rets = [(vals[i] - vals[i - horizon]) / vals[i - horizon] for i in range(horizon, len(vals))]
    cur = (vals[-1] - vals[-1 - horizon]) / vals[-1 - horizon]
    sd = statistics.pstdev(rets) or 1e-9
    z = cur / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("price_momentum", True, round(score, 4), cur,
                        f"{params['symbol']} {horizon}d {cur*100:+.1f}% (z={z:+.2f})", params)


@register("series_spread_percentile")
def series_spread_percentile(ctx: ScoreContext, params: dict) -> DriverResult:
    """Persentil av en spread (minuend − subtrahend), f.eks. realrente el. rentediff."""
    spread = _within_lookback(ctx.spread_series(params["minuend"], params["subtrahend"]),
                              ctx.as_of, params.get("lookback_days", 504))
    if len(spread) < 20:
        return _miss("series_spread_percentile",
                     f"{params['minuend']}-{params['subtrahend']}", params)
    vals = [v for _, v in spread]
    cur = vals[-1]
    p = _percentile(vals, cur)
    score = (2 * p - 1) * _sign(params.get("bull_when", "high"))
    return DriverResult("series_spread_percentile", True, round(score, 4), cur,
                        f"{params['minuend']}-{params['subtrahend']} = {cur:+.3g} (p{p*100:.0f})",
                        params)


@register("price_vs_sma")
def price_vs_sma(ctx: ScoreContext, params: dict) -> DriverResult:
    """Avstand fra glidende snitt på NIVÅ-feeden; trend-driver (bullish over).

    Avviket (close−SMA)/SMA z-skåres mot instrumentets EGEN avviks-spredning over en
    historikk, så driveren beholder gradering på tvers av instrumenter og bare metter ved
    ekte ekstremer (i stedet for en vilkårlig fast skala som metter alt volatilt).
    """
    closes = ctx.closes(params["symbol"], params.get("tf", "D1"))
    window = params.get("window", 200)
    hist = params.get("hist", 250)
    if len(closes) < window + 1:
        return _miss("price_vs_sma", params["symbol"], params)
    vals = [c for _, c in closes]
    # Avviks-serie over de siste `hist` punktene (rullerende SMA).
    devs: list[float] = []
    for t in range(max(window, len(vals) - hist), len(vals) + 1):
        sma = statistics.fmean(vals[t - window:t])
        devs.append((vals[t - 1] - sma) / sma if sma else 0.0)
    cur = devs[-1]
    sd = statistics.pstdev(devs) or 1e-9
    z = cur / sd
    score = math.tanh(z)
    return DriverResult("price_vs_sma", True, round(score, 4), cur,
                        f"{params['symbol']} {cur*100:+.1f}% vs SMA{window} (z={z:+.2f})", params)


@register("cot_spec_net_percentile")
def cot_spec_net_percentile(ctx: ScoreContext, params: dict) -> DriverResult:
    """Spekulant netto-posisjonering (long_spec − short_spec), persentil over lookback."""
    rows = ctx.cot(params["market"])
    lookback = params.get("lookback_weeks", 156)
    rows = rows[-lookback:]
    nets: list[float] = []
    for r in rows:
        ls, ss, oi = r["long_spec"], r["short_spec"], r["open_interest"]
        if ls is None or ss is None:
            continue
        net = ls - ss
        nets.append(net / oi if oi else net)
    if len(nets) < 20:
        return _miss("cot_spec_net_percentile", params["market"], params)
    cur = nets[-1]
    p = _percentile(nets, cur)
    score = (2 * p - 1) * _sign(params.get("bull_when", "high"))
    return DriverResult("cot_spec_net_percentile", True, round(score, 4), cur,
                        f"{params['market']} spec-net p{p*100:.0f}", params)


@register("ethanol_parity")
def ethanol_parity(ctx: ScoreContext, params: dict) -> DriverResult:
    """Etanol-paritet: brasiliansk hydrous-etanol i USD relativt til sukkerprisen.

    Når etanol (omregnet til USD via BRL) er dyrt relativt til sukker, lønner det seg for
    møllene å lage etanol → mindre sukker på markedet → bullish sukker (bull_when high).
    Forholdet z-skåres mot egen historikk. Egen, frisk implementasjon.

    NB: ANP-etanolserien er grunn (~2 år) → tynt base-rate-grunnlag, men korrekt driver.
    """
    from bisect import bisect_right

    eth = ctx.series(params.get("ethanol_series", "ANP_ETANOL_HIDR_CS_BRL_LITER"))
    brl = ctx.series(params.get("brl_series", "DEXBZUS"))  # BRL pr USD
    sugar = ctx.closes(params.get("symbol", "Sugar"), params.get("tf", "D1"))
    if len(eth) < 20 or not brl or len(sugar) < 20:
        return _miss("ethanol_parity", "etanol/BRL/sukker", params)

    bdates, bvals = [d for d, _ in brl], [v for _, v in brl]
    edates, evals = [d for d, _ in eth], [v for _, v in eth]

    def _ffill(dates, vals, on):
        i = bisect_right(dates, on) - 1
        return vals[i] if i >= 0 else None

    ratios: list[float] = []
    for d, sclose in sugar:
        if d < edates[0] or sclose <= 0:
            continue
        e = _ffill(edates, evals, d)
        b = _ffill(bdates, bvals, d)
        if e is None or b is None or b <= 0:
            continue
        eth_usd = e / b               # BRL/liter ÷ (BRL/USD) = USD/liter
        ratios.append(eth_usd / sclose)
    if len(ratios) < 20:
        return _miss("ethanol_parity", "for kort overlapp", params)

    cur = ratios[-1]
    mean = statistics.fmean(ratios)
    sd = statistics.pstdev(ratios) or 1e-9
    z = (cur - mean) / sd
    score = math.tanh(z)              # høyt forhold = etanol dyrt vs sukker = bullish
    return DriverResult("ethanol_parity", True, round(score, 4), round(cur, 5),
                        f"etanol/sukker z={z:+.2f}", params)


@register("etf_flow")
def etf_flow(ctx: ScoreContext, params: dict) -> DriverResult:
    """Fysisk investerings-flyt: z-skåret endring i ETF-beholdning (tonn) over et vindu.

    For gull/sølv er ETF-beholdning (f.eks. GLD tonnes-in-trust) en direkte fysisk
    etterspørsels-flyt: stigende beholdning = inn-flyt fra investorer = bullish (bull_when
    high). Prosentvis endring over horisonten z-skåres mot egen historikk. Egen, frisk
    implementasjon (gjenbruk av bedrock-data, ikke kode).
    """
    series = ctx.etf_holdings(params["ticker"])
    horizon = params.get("horizon_days", 63)
    if len(series) < horizon + 30:
        return _miss("etf_flow", params["ticker"], params)
    vals = [v for _, v in series]
    rets = [(vals[i] - vals[i - horizon]) / vals[i - horizon]
            for i in range(horizon, len(vals)) if vals[i - horizon]]
    if vals[-1 - horizon] <= 0 or len(rets) < 20:
        return _miss("etf_flow", "for kort/ugyldig overlapp", params)
    cur = (vals[-1] - vals[-1 - horizon]) / vals[-1 - horizon]
    sd = statistics.pstdev(rets) or 1e-9
    z = cur / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("etf_flow", True, round(score, 4), round(cur, 4),
                        f"{params['ticker']} {horizon}d-beholdning {cur*100:+.1f}% (z={z:+.2f})",
                        params)


@register("rainfall_anomaly")
def rainfall_anomaly(ctx: ScoreContext, params: dict) -> DriverResult:
    """Sesongjustert nedbør-anomali; BEGGE ekstremer = bullish (ikke-monoton).

    For en avling som sukker/kaffe forstyrrer både tørke (cane-stress) og styrtregn
    (høst-forstyrrelse, lavt sukkerinnhold) tilbudet → bullish. Normalt vær = bearish.
    Vi summerer nedbør over et vindu og z-skårer mot SAMME kalenderperiode i tidligere år
    (så sesongen ikke forveksles med anomali), og mapper |z| slik at ekstremt = positivt.
    """
    region = params.get("region", "brazil_cs_cane")
    win = params.get("window_days", 30)
    seasonal_halfwidth = params.get("seasonal_halfwidth", 15)
    series = ctx.weather_precip(region)
    if len(series) < 365 * 3:
        return _miss("rainfall_anomaly", region, params)

    dates = [date.fromisoformat(d) for d, _ in series]
    vals = [v for _, v in series]
    # Rullerende vindu-sum (krever ~sammenhengende daglige data fra Open-Meteo).
    from collections import deque
    roll: list[float] = []
    acc = 0.0
    q: deque[float] = deque()
    for v in vals:
        q.append(v)
        acc += v
        if len(q) > win:
            acc -= q.popleft()
        roll.append(acc)

    cur_doy = dates[-1].timetuple().tm_yday
    cur_sum = roll[-1]

    def _doy_dist(a: int, b: int) -> int:
        d = abs(a - b)
        return min(d, 366 - d)

    # Sesong-baseline: vindu-summer på samme tid på året i tidligere år (ikke siste 60 dager).
    baseline = [roll[i] for i in range(len(roll) - 60)
                if _doy_dist(dates[i].timetuple().tm_yday, cur_doy) <= seasonal_halfwidth]
    if len(baseline) < 20:
        return _miss("rainfall_anomaly", "for tynt sesong-grunnlag", params)

    mean = statistics.fmean(baseline)
    sd = statistics.pstdev(baseline) or 1e-9
    z = (cur_sum - mean) / sd
    # |z|<1 (normalt) → negativt (bearish); |z|>1 (tørke ELLER styrtregn) → positivt (bullish).
    score = math.tanh(abs(z) - 1.0)
    kind = "tørt" if z < 0 else "vått"
    return DriverResult("rainfall_anomaly", True, round(score, 4), round(z, 3),
                        f"{region} {win}d-nedbør {kind} z={z:+.2f}", params)


@register("degree_days_anomaly")
def degree_days_anomaly(ctx: ScoreContext, params: dict) -> DriverResult:
    """Temperatur-drevet energi-etterspørsel vs sesong-norm (begge ekstremer = etterspørsel).

    For naturgass gir BÅDE kulde (oppvarming, HDD) og hete (kjøling, CDD) etterspørsel:
    degree-days = |døgnmiddel − komfort-basis|. Vi summerer over et nylig vindu og z-skårer
    mot SAMME kalenderperiode i tidligere år, så «kaldere/varmere enn normalt» (over-normal
    etterspørsel) = bullish. Normalt vær = bearish. Egen, frisk implementasjon.
    """
    region = params.get("region", "us_gas_demand")
    base = params.get("comfort_base_c", 18.0)
    win = params.get("window_days", 14)
    seasonal_halfwidth = params.get("seasonal_halfwidth", 15)
    series = ctx.weather_tmean(region)
    if len(series) < 365 * 3:
        return _miss("degree_days_anomaly", region, params)

    dates = [date.fromisoformat(d) for d, _ in series]
    dd = [abs(v - base) for _, v in series]  # degree-days (HDD+CDD)
    from collections import deque
    roll: list[float] = []
    acc = 0.0
    q: deque[float] = deque()
    for v in dd:
        q.append(v)
        acc += v
        if len(q) > win:
            acc -= q.popleft()
        roll.append(acc)

    cur_doy = dates[-1].timetuple().tm_yday
    cur_sum = roll[-1]

    def _doy_dist(a: int, b: int) -> int:
        d = abs(a - b)
        return min(d, 366 - d)

    baseline = [roll[i] for i in range(len(roll) - 30)
                if _doy_dist(dates[i].timetuple().tm_yday, cur_doy) <= seasonal_halfwidth]
    if len(baseline) < 20:
        return _miss("degree_days_anomaly", "for tynt sesong-grunnlag", params)
    mean = statistics.fmean(baseline)
    sd = statistics.pstdev(baseline) or 1e-9
    z = (cur_sum - mean) / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("degree_days_anomaly", True, round(score, 4), round(z, 3),
                        f"{region} {win}d degree-days z={z:+.2f}", params)


@register("seasonal_anomaly")
def seasonal_anomaly(ctx: ScoreContext, params: dict) -> DriverResult:
    """Retningsbestemt avvik fra sesong-norm for en sterkt sesongbetont makro-serie.

    For lager (olje/gass) er rånivået sesongbetont (vinter-trekk, skulder-bygg); det
    informative er om lageret er HØYT eller LAVT vs samme uke i tidligere år. Vi z-skårer
    dagens verdi mot same-DOY-fordelingen (±halvbredde) i historikken. For lager:
    over sesong-norm = overforsynt = bearish (bull_when low). Egen, frisk implementasjon.
    """
    series = _within_lookback(ctx.series(params["series"]), ctx.as_of,
                              params.get("lookback_days", 3650))
    if len(series) < 365:
        return _miss("seasonal_anomaly", params["series"], params)
    dates = [date.fromisoformat(d) for d, _ in series]
    vals = [v for _, v in series]
    seasonal_halfwidth = params.get("seasonal_halfwidth", 10)
    cur_doy = dates[-1].timetuple().tm_yday
    cur = vals[-1]

    def _doy_dist(a: int, b: int) -> int:
        d = abs(a - b)
        return min(d, 366 - d)

    # Sesong-baseline: samme tid på året i tidligere perioder (ekskluder siste ~30 dager).
    baseline = [vals[i] for i in range(len(vals) - 30)
                if _doy_dist(dates[i].timetuple().tm_yday, cur_doy) <= seasonal_halfwidth]
    if len(baseline) < 15:
        return _miss("seasonal_anomaly", "for tynt sesong-grunnlag", params)
    mean = statistics.fmean(baseline)
    sd = statistics.pstdev(baseline) or 1e-9
    z = (cur - mean) / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("seasonal_anomaly", True, round(score, 4), round(cur, 1),
                        f"{params['series']} vs sesong z={z:+.2f}", params)


@register("price_ratio")
def price_ratio(ctx: ScoreContext, params: dict) -> DriverResult:
    """Z-skåret relativverdi mellom to NIVÅ-feed-symboler (teller/nevner).

    Relativverdi-/substitusjons-driver, IKKE pris-trend: f.eks. platinum/gull. Lav ratio
    (bull_when low) = platinum historisk billig vs gull → substitusjon i autokatalysatorer →
    mean-reversion bullish platinum. Forholdet forward-fylles på felles datoer og z-skåres
    mot egen historikk. Egen, frisk implementasjon.
    """
    from bisect import bisect_right

    a = ctx.closes(params["numerator"], params.get("tf", "D1"))
    b = ctx.closes(params["denominator"], params.get("tf", "D1"))
    if len(a) < 30 or len(b) < 30:
        return _miss("price_ratio", f"{params['numerator']}/{params['denominator']}", params)
    bdates = [d[:10] for d, _ in b]
    bvals = [v for _, v in b]
    ratios: list[float] = []
    for ts, av in a:
        i = bisect_right(bdates, ts[:10]) - 1
        if i >= 0 and bvals[i]:
            ratios.append(av / bvals[i])
    if len(ratios) < 30:
        return _miss("price_ratio", "for kort overlapp", params)
    cur = ratios[-1]
    mean = statistics.fmean(ratios)
    sd = statistics.pstdev(ratios) or 1e-9
    z = (cur - mean) / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("price_ratio", True, round(score, 4), round(cur, 4),
                        f"{params['numerator']}/{params['denominator']} {cur:.3f} (z={z:+.2f})",
                        params)


@register("frost_anomaly")
def frost_anomaly(ctx: ScoreContext, params: dict) -> DriverResult:
    """Frost-risiko: anomalt kald natt i et kaffe-/avlingsbelte = tilbudssjokk = bullish.

    For arabica (Brasil, Sul de Minas) er geada (frost) i austral vinter den klassiske
    pris-spiker (1975/1994/2021). Vi tar den KALDESTE natta (min tmin) i et nylig vindu,
    z-skårer mot SAMME kalenderperiode i tidligere år, og lar bare ekte kuldeanomalier slå
    ut (asymmetrisk: bare kaldt = bullish; varmt/normalt = 0). En absolutt kulde-gate hindrer
    at sommer-kjøligheter feilaktig fyrer (frost krever faktisk lave temperaturer). Egen impl.
    """
    region = params.get("region", "brazil_sul_minas")
    win = params.get("window_days", 10)
    seasonal_halfwidth = params.get("seasonal_halfwidth", 15)
    abs_gate = params.get("abs_cold_gate_c", 10.0)
    series = ctx.weather_tmin(region)
    if len(series) < 365 * 3:
        return _miss("frost_anomaly", region, params)

    dates = [date.fromisoformat(d) for d, _ in series]
    vals = [v for _, v in series]
    # Rullerende minimum (kaldeste natt) over vinduet.
    from collections import deque
    roll_min: list[float] = []
    q: deque[float] = deque()
    for v in vals:
        q.append(v)
        if len(q) > win:
            q.popleft()
        roll_min.append(min(q))

    cur_doy = dates[-1].timetuple().tm_yday
    cur_min = roll_min[-1]

    def _doy_dist(a: int, b: int) -> int:
        d = abs(a - b)
        return min(d, 366 - d)

    baseline = [roll_min[i] for i in range(len(roll_min) - 60)
                if _doy_dist(dates[i].timetuple().tm_yday, cur_doy) <= seasonal_halfwidth]
    if len(baseline) < 20:
        return _miss("frost_anomaly", "for tynt sesong-grunnlag", params)

    mean = statistics.fmean(baseline)
    sd = statistics.pstdev(baseline) or 1e-9
    z = (cur_min - mean) / sd
    # Bare reelt kaldt (under abs-gate) OG anomalt kaldt (z<−1) gir bullish utslag.
    if cur_min > abs_gate:
        score = 0.0
    else:
        score = math.tanh(max(0.0, -z - 1.0))
    return DriverResult("frost_anomaly", True, round(score, 4), round(cur_min, 1),
                        f"{region} kaldeste natt {cur_min:.1f}°C (z={z:+.2f})", params)


@register("series_ratio")
def series_ratio(ctx: ScoreContext, params: dict) -> DriverResult:
    """Z-skåret forhold mellom to dype serier (teller/nevner), forward-fylt på felles datoer.

    Brukes f.eks. som dyp proxy for sukker sin etanol-divergering: energi/sukker
    (WTI ÷ IMF-sukkerpris) — høyt = energi dyrt vs sukker → cane til etanol → bullish sukker.
    """
    from bisect import bisect_right

    a = ctx.series(params["numerator"])
    b = ctx.series(params["denominator"])
    if len(a) < 20 or len(b) < 20:
        return _miss("series_ratio", f"{params['numerator']}/{params['denominator']}", params)
    bdates, bvals = [d for d, _ in b], [v for _, v in b]
    ratios: list[tuple[str, float]] = []
    for d, av in a:
        i = bisect_right(bdates, d) - 1
        if i >= 0 and bvals[i]:
            ratios.append((d, av / bvals[i]))
    ratios = _within_lookback(ratios, ctx.as_of, params.get("lookback_days", 1825))
    if len(ratios) < 20:
        return _miss("series_ratio", "for kort overlapp", params)
    vals = [v for _, v in ratios]
    cur = vals[-1]
    mean = statistics.fmean(vals)
    sd = statistics.pstdev(vals) or 1e-9
    z = (cur - mean) / sd
    score = math.tanh(z) * _sign(params.get("bull_when", "high"))
    return DriverResult("series_ratio", True, round(score, 4), round(cur, 4),
                        f"{params['numerator']}/{params['denominator']} z={z:+.2f}", params)
