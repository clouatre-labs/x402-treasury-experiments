# Protocol: usdc-fiat-sweep

## Research Question

What is the true cost and friction of converting accumulated L2 USDC micropayment revenue to fiat, and how does fixed-cost structure behave at micropayment scale?

This is a supplementary measurement for blog post clouatre-labs/clouatre.ca#2090; tracking issue clouatre-labs/clouatre.ca#2110.

## Design

Dose-response measurement at four pre-registered amount levels, executed by a human operator. There is no randomized control arm and no LLM in the loop. The comparator is the advertised Coinbase fee schedule: each realized conversion is compared against the fee the schedule predicts for that amount (advertised vs realized).

### Tranches

| Level | Amount | Replicates |
|-------|--------|------------|
| 1 | $1 | 2 |
| 2 | $5 | 2 |
| 3 | $20 | 2 |
| 4 | full remaining receiver balance | 2 |

Eight conversions total, executed in one execution pass. No tranche is re-run because a number looked unfavorable.

### Funding and execution order

The tranches are pre-funded by a single inbound USDC transfer into the receiver wallet before the first conversion, then executed in ascending amount order: $1, $1, $5, $5, $20, $20, then the two full-balance replicates. Every tranche is funded solely by the single pre-registered inbound transfer; no replenishment exists or is needed; the full-balance tranche consumes the residual at its position in the ascending sequence. The full-balance tranche is defined as the entire remaining receiver balance at that point in the sequence, so both full-balance replicates are executable without any replenishment procedure between them. With an inbound transfer of approximately $60, the six fixed-amount tranches consume $52 and each full-balance replicate sweeps the remaining balance of approximately $4.

### Endpoints (per tranche)

- Realized percentage fee.
- Fixed fee in USD.
- Spread vs USDC mid at execution time.
- Per-hop latency: on-chain send, Coinbase credit, fiat spendable.
- Manual step count.

## Data Source

The receiver wallet of clouatre.ca x402 revenue (`X402_PAY_TO`). The `MAINNET_PAYER` wallet is excluded: it is spend-side operating float, and payer self-tests are already excluded from revenue accounting. The receiver key is retrieved from the secret store at execution time only and is never committed. Fallback if the receiver key is unreachable: fund from the payer wallet and label the tranche `payer-float treasury` in `pre_acknowledged_limitations`.

## Charity Note

Spreads consumed by the conversion are taken from MICN-bound funds; all residual proceeds still route to the Montreal Indigenous Community NETWORK (MICN).

## Budget

Total inbound volume approximately $60 via a single pre-funding transfer to the receiver wallet; $52 is consumed by the fixed-amount tranches and the remainder (approximately $4 per replicate) by the two full-balance tranches. Expected $1-3 consumed in spreads.

## Analysis Plan

Descriptive only: per-level medians and ranges, and a fee-vs-amount curve. No inferential test.

Statistical test: `none (descriptive dose-response)`.

## Threats to Validity

- The observer sees the fee schedule before executing. The pre-registration seal is on the outcome, not on schedule knowledge.
- The Coinbase fee schedule may change between pre-registration and execution. The schedule is recorded at execution time.
- Price slippage on the USDC/fiat conversion is part of the measured spread, not noise.

## Run Records

Raw observations go verbatim into `sessions/`. Transcription rules and the run-record schema are in [record-extraction.md](record-extraction.md) and [../../DATA_DICTIONARY.md](../../DATA_DICTIONARY.md). The template's `analysis.json` schema governs the final `analysis.json` after the run.
