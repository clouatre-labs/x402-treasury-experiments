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
- 2026-11-04, tranche `kraken-10` (execution pass crash before record write):
  the market sell filled cleanly on Kraken (order `OX6CYI-EUPXR-OWAK3C`,
  trade `TXH2XG-5QPJ4-23ORQK`, sell 10 USDC @ 0.9998, cost 9.998 USD, fee
  0.019996 USD), but `sweep.ts` line 357 then called private `QueryTrades`
  with the ORDER txid; Kraken's `QueryTrades` accepts trade txids only and
  returned `EOrder:Invalid order`, the script threw, and the process exited
  before `writeRecord` and before the `query-orders.json`/`query-trades.json`
  raw artifacts. Tranches 2-6 never started; the receiver wallet was
  untouched. Remediation before resuming the single pass: (1) the raw fill
  data was recovered verbatim from read-only `QueryOrders`/`QueryTrades`
  (with the trade txid from the order's `trades` array) into
  `sessions/raw/kraken-10/`; (2) `sweep.ts` was patched to pass the order's
  trade ids to `QueryTrades` (observation call only; no order-placement or
  measurement logic changed) and `modeExecute` now skips any tranche whose
  record already exists on disk, so `kraken-10` is not re-executed;
  (3) `kraken-10`'s record was written from the recovered verbatim fill data
  by a recovery script replicating the sealed record computation. Net effect
  on the measurement: `kraken-10`'s `is_latency_valid = false` per the
  mechanical exclusion rule (recovery intervention); its `pair_mid`,
  `mid_observed_at`, and `quoted_price` were re-observed from the live ticker
  after the crash rather than at order placement, so its
  `realized_slippage` and `spread_vs_mid_pct` are computed against a
  post-crash quote observation and are flagged as such in the record notes;
  all fill-derived endpoints (`avg_fill_price`, fees, cost) come verbatim
  from the executed fill. No tranche was re-run; the pass continued in
  ascending order from `kraken-residue` with fresh quote/mid observations.
- 2026-11-04, tranche `kraken-residue` (same crash class as `kraken-10`):
  the resumed pass's first fix passed the order's trade ids to `QueryTrades`,
  but `krakenSell`'s `QueryOrders` poll did not request the `trades` field,
  so the fix fell back to the order txid and `kraken-residue` (order
  `OLN7MO-CSKO7-U3Y6BN`, sell 91 USDC @ market, fill 90.9818 USD, fee 0.1820
  USD) crashed before record write, identically to `kraken-10`. Remediation:
  `QueryOrders` now requests `trades: true` so trade ids are always present;
  the residue record was recovered verbatim from read-only
  `QueryOrders`/`QueryTrades` by the shared recovery script
  (`sessions/raw/recover-kraken-sell.ts`), same flags as `kraken-10`
  (`is_latency_valid = false`, post-crash quote observation noted). No
  tranche was re-run; the pass continued in ascending order.
- 2026-11-04, Arm B (`cad-20`, `cad-eft`) structurally unexecutable under the
  sealed design: the sealed residue formula
  (`amount_residue = balance_provider_usdc_spendable`) arithmetically consumes
  the ENTIRE spendable USDC balance before Arm B runs (ascending tranche
  order: kraken-10 sold 10 of 101, residue sold all 91, leaving Kraken USDC
  balance 0 at cad-20 time), so cad-20 has no USDC to sell and cad-eft has no
  CAD proceeds. `modeExecute`'s pre-pass guard (USDC >= 35 for Arms A/B)
  aborted the resumed run before any tranche; no orders were placed and no
  state changed. This is a design inconsistency, not bad luck: for ANY
  working capital W, residue = W - 10 sells everything, so a fixed-size 20
  USDC Arm B tranche after the residue can never execute. Operator decision
  (2026-11-04): recorded outcomes, not top-up — funding 20 new USDC mid-pass
  was rejected because it would change Kraken 30-day volume (fee tier state)
  and execute the CAD leg at an undefined working-capital state; the
  pre-registered protocol defines no such scenario. Remediation: cad-20 and
  cad-eft records written as `not_executed_below_minimum` outcomes with the
  verbatim cause in notes, and the pass continued in ascending order to Arm
  C, which is fully funded and executable. Pass-2 recommendation: reserve the
  sealed Arm B amount (`amount_residue = spendable - 20`) or order Arm B
  before the residue sweep; either change belongs in a pre-registered pass-2
  protocol, not a mid-pass edit.
- 2026-11-04, resume guard: `modeExecute`'s pre-pass Kraken USDC balance
  guard (>= 35) is written for a fresh pass and aborted the resumed run even
  though all Arm A/B tranches were already recorded and the only remaining
  work (Arm C) draws on the receiver wallet. Remediation: the guard now
  applies only when an Arm A/B tranche is still unrecorded. No tranche was
  re-run; no funds were added.
- 2026-11-04, tranche `coinbase-5-1` (on-chain hop executed; crash before
  convert): the 5 USDC transfer to the Coinbase deposit address succeeded
  (tx `0xc31e0c60189bbe84de1d28c0b6f5261c15b4bbfb091aadd9e7899dd307b166e3`,
  block 53513932, receipt persisted verbatim to
  `sessions/raw/coinbase-5-1/tx-receipt.json`), but the immediately following
  `getBlock` failed with a transient public-RPC `BlockNotFoundError` and the
  process exited before the deposit-credit wait and convert. Remediation (v1
  precedent): `coinbaseConvert` now resumes from a persisted receipt — if
  `tx-receipt.json` exists the on-chain hop is recovered verbatim (transfer
  NOT re-sent) and the flow continues from Hop 2; `timestamp_sent` derives
  from the receipt's `blockTimestamp` (second precision) instead of a
  `getBlock` round-trip that crashed on the transient error. No tranche was
  re-sent; the pass continued in ascending order.
- 2026-11-04, tranche `coinbase-5-1` (deposit-credit polling window exceeded):
  after resuming from the persisted receipt, the deposit-credit poll never
  succeeded within the pre-registered 20 x 30 s window (the second latent
  failure path set `execution_status = "api_error"` with `executed = false`,
  which the schema validator correctly rejects — the on-chain hop HAD
  executed). Read-only CDP query confirmed the USDC deposit credited after
  the window closed. Remediation: the failure path now records
  `executed = true` with the verbatim note; the resumed tranche carries
  `is_latency_valid = false` per the mechanical exclusion rule (deposit
  credit polling exceeded the pre-registered threshold), so only
  `coinbase-5-2` contributes a valid latency observation in Arm C. The
  convert then committed once, on the first quote attempt of the resumed
  pass. No tranche was re-sent.
- 2026-11-04, Arm C convert quote (`coinbase-5-1`, `coinbase-5-2`): the
  convert quote endpoint rejected the v2 payload field `from_amount` as an
  unknown field (`HTTP 400 proto: unknown field "from_amount"`), so the
  quote failed on every poll and NEITHER convert committed. v2's payload
  drifted from v1's live-proven shape: v1's sealed script
  (`experiments/usdc-fiat-sweep-api/sweep.ts:557`) sends
  `amount: <value>.toFixed(2)` and recorded `TRADE_STATUS_COMPLETED` with a
  $0.00 fee on this exact endpoint, keys, and account family; the trade/fill
  calls after the quote match v1's shape unchanged. Both on-chain hops had
  ALREADY executed and credited (tx `0xc31e0c60...66e3` and
  `0xfd86fec1...965d`, 5 USDC each; receipts persisted verbatim). Operator
  decision: apply the one-field API-contract repair (zero measurement logic;
  fee still comes from the fill's `total_fee`; conversion still 1:1) and
  resume both tranches from their persisted receipts — deposit-credited
  state, convert commits once each, transfer NOT re-sent. Both tranches
  carry `is_latency_valid = false` mechanically (resumed tranches). Retry
  semantics left unchanged (no broadening beyond the sealed loop).
- 2026-11-04, stale Arm C records from the pre-fix crashed attempt: the
  `api_error` records written by the `from_amount`-crashed attempt (before
  the API-contract repair) blocked the resume via the skip-if-record-exists
  guard. Both converts had never committed, so those records described an
  unrecoverable attempt, not a measured outcome. Remediation: both stale
  records preserved verbatim as crash artifacts
  (`sessions/raw/coinbase-{5-1,5-2}/api-error-crashed-attempt.json`) and
  removed from `sessions/` so the resume could re-enter `coinbaseConvert`
  from the persisted receipts. No transfer was re-sent; the converts commit
  once each on the resumed pass.
- 2026-11-04, Arm C fill parse (`coinbase-5-1`, `coinbase-5-2`): after the
  `from_amount` repair the quote and trade commit SUCCEEDED (trade
  `2cbbb2ce-7f94-435e-b4fd-0bf491df5794` for coinbase-5-1; commit accepted,
  fee $0.00), but the record write failed schema validation because the live
  fill response now returns `total_fee` as a nested object
  (`{ amount: { value: "0", currency: "USD" } }`) while v2's sealed parser
  expected v1's plain string, producing a null `fixed_fee_usd`. Parse repair
  only: accept either shape, value verbatim from the fill. No measurement
  logic changed; no re-sent transactions.
- 2026-11-04, tranche `coinbase-5-1` double convert commit: the convert for
  5-1 committed (trade `2cbbb2ce-7f94-435e-b4fd-0bf491df5794`,
  `TRADE_STATUS_CREATED`, fee $0.00) during the attempt that then crashed on
  the `total_fee` parse, and the resumed pass committed a SECOND convert for
  the same tranche (trade `9cd251ae-5d1b-4bda-8cce-50b77b7100a1`, fee $0.00)
  because the skip guard keys on the record file, which the crashed attempt
  never wrote, and the commit had no persisted idempotency token. Net
  on-ledger effect: coinbase-5-1 converted 10 USDC -> 10 USD instead of 5
  (two 5 USDC commits, both 1:1, both $0.00 fee); coinbase-5-2 converted its
  planned 5 once (trade `05411000-655a-444f-a209-4ecddb9c194a`, fee $0.00).
  Fee observations are unaffected (all commits $0.00, exchange rate 1.0);
  the duplicated principal is a working-capital placement effect, not a
  measured-cost effect. The committed record's notes carry the duplicate
  trade id verbatim. Pass-2 recommendation: persist the committed trade id
  to `raw/` immediately after commit so resume can short-circuit an already
  committed convert (v1 precedent).
- 2026-11-04, figure generation: the sealed fig1 recipe's record loader
  glob-reads every `*.json` in the records directory and crashes with
  `KeyError: 'executed'` on `sessions/funding.json` (which has no `executed`
  field and is a funding artifact, not a run record). Recipe scripts are
  frozen, so the figure was generated with `--records` pointing at a
  temporary directory of symlinks to the six run records only; content of
  the records is untouched.
