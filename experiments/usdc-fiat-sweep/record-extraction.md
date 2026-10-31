# Record Extraction: usdc-fiat-sweep

Instructions for transcribing raw session artifacts in `sessions/` into run records.

1. Transcribe exactly. No rounding beyond what the source shows.
2. Do not infer missing values. Amounts, fees, and identifiers are never null; a value missing from the raw artifact is a transcription error and must be resolved against the raw artifacts. The three timestamp fields (`timestamp_sent`, `timestamp_coinbase_credit`, `timestamp_fiat_spendable`) may be null only when the hop failed or was unobserved; every null timestamp requires a populated `notes` entry explaining which hop failed or was unobserved.
3. One record per tranche, using the schema in [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) (`usdc-fiat-sweep run-record schema`): `tranche_id`, `replicate`, `amount_usdc`, `tx_hash_in`, `timestamp_sent`, `timestamp_coinbase_credit`, `timestamp_fiat_spendable`, `fiat_received`, `network_fee_usd`, `fixed_fee_usd`, `quoted_fee_usd`, `realized_fee_pct`, `spread_vs_mid_pct`, `manual_steps`, `notes`. Record the USDC mid-price source and the time it was observed for each tranche in `notes`, so the recorded `spread_vs_mid_pct` is recomputable. `realized_fee_pct` and `spread_vs_mid_pct` are derived quantities computed from the recorded fee and amount fields, not recorded values.
4. Timestamps are transcribed in the format the source shows; note the timezone if the source does not show UTC.
5. If the fallback (`payer-float treasury`) was used, say so in `notes`.
6. Raw artifacts stay untouched in `sessions/`; records are derived copies only.
