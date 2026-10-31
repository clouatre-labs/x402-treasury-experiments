# Runbook: usdc-fiat-sweep

Operator instructions for executing the eight pre-registered conversions. Execute one pass only; never re-run a tranche because a number looked unfavorable.

## Before Starting

1. Record the current advertised Coinbase fee schedule (screenshot or verbatim copy) and save it under `sessions/`.
2. Retrieve the receiver key (`X402_PAY_TO`) from the secret store at execution time only; never commit it.

## Executions

For each of the eight tranches (amounts $1, $5, $20, full receiver balance; 2 replicates each):

3. Note the USDC mid price at execution time.
4. Send the tranche amount from the receiver wallet to Coinbase. Capture the on-chain transaction hash and the send timestamp.
5. When Coinbase credits the USDC, capture the credit timestamp.
6. Convert to fiat. Capture the quoted fee screen verbatim (screenshot or exact copy).
7. When the fiat is spendable, capture the spendable timestamp.
8. Count the manual steps performed for this tranche (button presses, confirmations, screen transitions).
9. Write every raw observation verbatim into `sessions/` as it happens. Do not summarize, round, or clean up. Every raw observation goes verbatim into `sessions/`.

## After All Tranches

10. Confirm `sessions/` contains one raw artifact set per tranche (tx hash, timestamps, quoted fee, step count, notes).
11. Transcribe into run records using [record-extraction.md](record-extraction.md). Do not invent values.
