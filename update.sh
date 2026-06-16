#!/usr/bin/env bash
# Regnbue — fersk data → pipeline → publiser setups.json (commit kun ved endring).
# Mønster (flock + add/commit/rebase/push) inspirert av cot-explorer, egen implementasjon.
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
LOCK=".git/push.lock"

# Hindre overlappende kjøringer (systemd-timer + manuell).
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[update] en kjøring pågår allerede — hopper over."
  exit 0
fi

# Fersk bias + nivå-data. Nettverkssteg er best-effort: feiler de (f.eks. token utløpt),
# publiserer vi likevel på eksisterende data heller enn å blokkere.
echo "[update] henter makro (FRED) …"
$PY -m setups.fetch.fred || echo "[update] FRED-fetch feilet, fortsetter."
echo "[update] henter energi-lager (EIA) …"
$PY -m setups.fetch.eia || echo "[update] EIA-fetch feilet, fortsetter."
echo "[update] henter vær (Open-Meteo) …"
$PY -m setups.fetch.weather || echo "[update] vær-fetch feilet, fortsetter."
echo "[update] henter dealer-gamma (Deribit BTC/ETH) …"
$PY -m setups.fetch.gamma || echo "[update] gamma-fetch feilet, fortsetter."
echo "[update] henter ferske priser (cTrader) …"
$PY -m setups.ctrader_prices GOLD EURUSD Coffee --years 1 || echo "[update] pris-fetch feilet, fortsetter."

echo "[update] vasker pris-data (skala-glitcher) …"
$PY -m setups.clean || echo "[update] datavask feilet, fortsetter."

echo "[update] kjører pipeline …"
$PY -m setups.run

if git diff --quiet -- web/data/setups.json; then
  echo "[update] ingen endring i setups.json — ingen commit."
  exit 0
fi

git add web/data/setups.json
git commit -m "data: oppdater setups.json ($(date -u +%FT%TZ))"
git pull --rebase --autostash origin main || true
git push origin main
echo "[update] publisert."
