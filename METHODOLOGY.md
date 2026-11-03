# Methodology

Experimental design and analysis plan for experiments in this repository. Each experiment's `protocol.md` states the specifics; this top-level document is the shared measurement contract.

## Research Question

Each experiment states its question in `experiments/<slug>/protocol.md`. Questions are framed so that a descriptive result is still informative; for LLM-free experiments there is no hypothesis test, only measurement.

## Pre-Registration

Every experiment MUST have its protocol, operator runbook, and record-extraction instructions committed under `experiments/<slug>/` BEFORE any session is run. The commit containing the pre-registration must precede the first run record; edits after data collection begins require a dated addendum in the experiment's `protocol.md`.

- Endpoints and tranche levels are defined before examining any raw output.
- The comparator condition (for example, an advertised fee schedule) is named in the protocol before data collection.
- The analysis plan is stated in the protocol before data collection.

## Experimental Design

Each experiment states in its protocol:

- The quantity measured and the data source (wallet, endpoint, or artifact).
- Dose levels, replicates, and the stopping rule.
- The execution pass rule: a single pass; no tranche is re-run because a number looked unfavorable.
- Comparator condition and how it is recorded at execution time.

## Measurement Contract

Experiments in this repository may be human-executed measurements rather than LLM runs. The contract is:

- Pre-registration before execution: protocol, runbook, and record-extraction rules are fixed in git before the first conversion or measurement.
- Single pass: each pre-registered measurement is taken exactly once; no re-runs on unfavorable outcomes.
- Descriptive analysis: results are reported as medians, ranges, and curves; no inferential statistical tests unless a protocol pre-registers one.
- Raw observations are captured verbatim into `sessions/`; derived records are transcriptions, never reconstructions.
- Figures are generated only from scripts in `recipe/` into `figures/`.

## Analysis Plan

Analysis results land in `experiments/<slug>/analysis.json` (schema in [DATA_DICTIONARY.md](DATA_DICTIONARY.md), enforced by `validate_schema.py`). Raw run records land under `experiments/<slug>/sessions/`. Figures are generated from `recipe/` scripts into `figures/`.

## Threats to Validity

Each experiment enumerates its own threats in `protocol.md`. Recurring ones:

- Observer knowledge of the comparator before execution; the pre-registration seal is on the outcome, not on comparator knowledge.
- Comparator drift between pre-registration and execution; the comparator is recorded at execution time.
- Slippage and spread that are part of the measured quantity, not noise.

## Execution Deviations (recorded, per protocol "stop and record")

- 2026-11-03, tranche `level1-1`: the on-chain USDC transfer succeeded (tx
  `0xed5eaf0af7c22c1215dcdacbf6526d9f5ef8274f9fed98af8b4b696dd6c51166`, verified on Base mainnet) but the script crashed before writing any
  record or raw artifact (`JSON.stringify` cannot serialize the `BigInt` values in a viem transaction receipt). Tranches 2-9 never started.
  Remediation before resuming the single pass: (1) the genuine receipt was
  recovered verbatim from a Base RPC `eth_getTransactionReceipt` call into
  `sessions/raw/level1-1/tx-receipt.json`; (2) `sweep.ts` was patched to use
  BigInt-safe JSON serialization and to skip the on-chain transfer for any
  tranche whose persisted receipt already exists (resume-from-convert-hop), so
  `level1-1` is not re-sent. Net effect on the measurement: `level1-1`'s
  `timestamp_sent` is derived from its confirmed block timestamp (second
  precision) rather than a local wall-clock send timestamp; all other
  endpoints are unchanged. No tranche was re-run; the pass continued in
  ascending order with fresh quote/mid observations at convert time.
- 2026-11-03, tranche `level1-1` (convert stage): the convert quote and commit
  calls succeeded (trade `38e3ee63-593b-4107-8bfa-97539e42fd5c`) but the status
  poll returned HTTP 401 because the ES256 JWT `uri` claim was signed over the
  request path including its query string; the claim covers the path only.
  Remediation: `cdpRequest` now signs the path without the query string; raw
  artifacts are persisted immediately after the quote and after the commit to
  narrow the crash window; the convert stage supports resume from a persisted
  fill; and the fill-status matcher accepts the live `TRADE_STATUS_*` values.
  `level1-1`'s committed trade was recovered verbatim via a read-only GET into
  `sessions/raw/level1-1/convert-fill.json` (status `TRADE_STATUS_COMPLETED`,
  total fee `$0.00`). Net effect on the measurement: `level1-1`'s
  `timestamp_coinbase_credit` and `timestamp_fiat_spendable` are the recovery
  time rather than the original fill moment (the trade had already completed
  before recovery), and its quote response is absent (the fill response is the
  verbatim record). The convert itself committed exactly once; no tranche was
  re-sent or re-converted.
- 2026-11-03, tranches `level20-1`/`level20-2` (convert stage): Base deposits
  credit to the Coinbase account with a lag, so quoting immediately after an
  on-chain send returned `ERROR_CODES_INSUFFICIENT_BALANCE` twice. Remediation:
  the quote retries on `INSUFFICIENT_BALANCE` with a 30s backoff (bounded at
  20 attempts), and tranches whose record file already exists are skipped
  entirely so re-invocations never overwrite executed records. No funds were
  added and no tranche was re-sent; the pass continued in ascending order.
- 2026-11-03, tranche `level100-1` (convert stage): the convert quote endpoint
  returns HTTP 200 with an empty trade and `cancellation_reason`
  `ERROR_CODES_INSUFFICIENT_BALANCE` when the deposit has not credited yet
  (documented behavior: insufficient-balance failures do not use error status
  codes), so the exception-based retry never engaged. Remediation: the quote
  retry now inspects the parsed response body as well as thrown errors, with a
  bounded 20-minute wait window. No tranche was re-sent; `level100-1`'s
  on-chain transfer was persisted and is resumed from the convert hop.
- 2026-11-03, figure 3 (fee decomposition): the recipe divides each cost
  component by the maximum observed cost, and every component is zero across
  all executed tranches (convert fee quoted and charged at $0.00, spread 0%,
  network fee 0), so the figure is degenerate (division by zero) and is not
  generated. This is the measured result, not missing data: figures 1 and 2
  are generated from the same records. Also note the recipe's
  `ADVERTISED_FIXED_FEE_USD = 0.25` overlay constant predates execution and
  could not be updated (recipe scripts are frozen post-execution); the
  advertised fee recorded verbatim from the live convert quote API at
  execution time is $0.00, which equals the realized fee on every tranche.
