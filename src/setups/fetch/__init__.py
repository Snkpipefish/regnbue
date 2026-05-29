"""Lean fetch-lag for BIAS-data (ikke nivåer).

Henter kun høyverdi-kilder som fingerprintene faktisk trenger, via gjenbrukte API-nøkler
i `~/.bedrock/secrets.env`. Historikk seedes engangs (`setups.seed`); fetch holder ferskt.

Nivå-priser hentes IKKE her — se `setups.ctrader_prices`.
"""
