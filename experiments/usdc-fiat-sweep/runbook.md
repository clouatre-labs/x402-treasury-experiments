# Runbook: usdc-fiat-sweep

Operator instructions for executing the seven executed conversions among the eight pre-registered records (the second full-balance replicate is pre-registered as `not_executed`). Execute one pass only; never re-run a tranche because a number looked unfavorable.

## Before Starting

1. Record the current advertised Coinbase fee schedule (screenshot or verbatim copy) and save it under `sessions/`.
2. Retrieve the receiver key (`X402_PAY_TO`) from the secret store at execution time only; never commit it.
3. Acquire approximately $60 of USDC on Coinbase via fiat-to-USDC conversion in the same account, recording the conversion quote and timestamp; then make a single inbound USDC transfer into the receiver wallet. This pre-funds all tranches; no replenishment transfer is made during execution.
4. Rehearsal (synthetic, zero cost): before execution, create 8 synthetic run records marked `synthetic:true` covering all tranche shapes including the `not_executed` replicate, validate them against the DATA_DICTIONARY.md schema by hand-check or ad-hoc script, generate all three figures from the synthetic data, then delete every synthetic artifact. Synthetic records are never committed to `sessions/`.
5. Execute the tranches in ascending amount order: $1, $1, $5, $5, $20, $20, then the full-balance replicate. Do not execute the second full-balance replicate; it is pre-registered as `not_executed`.

## Executions

For each of the executed tranches (7):

3. Note the USDC mid price at execution time.
4. Send the tranche amount from the receiver wallet to Coinbase. Capture the on-chain transaction hash and the send timestamp.
5. When Coinbase credits the USDC, capture the credit timestamp.
6. Convert to fiat. Capture the quoted fee screen verbatim (screenshot or exact copy).
7. When the fiat is spendable, capture the spendable timestamp.
8. Count the manual steps performed for this tranche (button presses, confirmations, screen transitions).
9. For the full-balance tranche, send the entire remaining receiver balance at that point in the sequence instead of a fixed amount; capture the sent amount as `amount_usdc`.
10. For the pre-registered `not_executed` full-balance replicate, write a run record with `amount_usdc` null (per the schema, null is allowed only for the pre-registered `not_executed` replicate) and a populated `notes` entry stating the pre-registered `not_executed` reason.
11. Write every raw observation verbatim into `sessions/` as it happens. Do not summarize, round, or clean up. Every raw observation goes verbatim into `sessions/`.

## After All Tranches

12. Confirm `sessions/` contains one raw artifact set per tranche (tx hash, timestamps, quoted fee, step count, notes).
13. Transcribe into run records using [record-extraction.md](record-extraction.md). Do not invent values.
