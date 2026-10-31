# Record Extraction: usdc-fiat-sweep

Instructions for transcribing raw session artifacts in `sessions/` into run records.

1. Transcribe exactly. No rounding beyond what the source shows.
2. Do not infer missing values. A value missing from the raw artifact is `null` with a note explaining why.
3. One record per tranche, using the schema in [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) (`usdc-fiat-sweep run-record schema`): `tranche_id`, `replicate`, `amount_usdc`, `tx_hash_in`, `timestamp_sent`, `timestamp_coinbase_credit`, `timestamp_fiat_spendable`, `fiat_received`, `quoted_fee_usd`, `realized_fee_pct`, `spread_vs_mid_pct`, `manual_steps`, `notes`.
4. Timestamps are transcribed in the format the source shows; note the timezone if the source does not show UTC.
5. If the fallback (`payer-float treasury`) was used, say so in `notes`.
6. Raw artifacts stay untouched in `sessions/`; records are derived copies only.
