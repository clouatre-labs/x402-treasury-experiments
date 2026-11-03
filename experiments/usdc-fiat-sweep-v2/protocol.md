# Protocol: usdc-fiat-sweep-v2 (DRAFT - externally reviewed, redesigned, ready to re-seal)

> **STATUS: DRAFT.** This protocol supersedes the previous v2 draft (4 arms,
> ~$3,270 working capital) after a KISS/cost re-review. The original Gemini
> review (approve-with-revisions, 8-point verdict) was applied to that draft;
> this redesign keeps every structural review fix (mechanical latency
> exclusion rules, provider selection criteria, network parity, dry-run
> before seal, descriptive-only latency) and re-scopes the measurement to
> micro-volume sweeps, which match the actual x402 treasury pattern: revenue
> arrives as micro-receipts and is swept as small accumulated balances.
> Nothing in this file authorizes execution yet. On sealing, this notice is
> removed and the stop-and-record clauses of
> [METHODOLOGY.md](../../METHODOLOGY.md) apply.

## Motivation

v1 (`usdc-fiat-sweep-api`) verified Coinbase's 1:1 USDC/USD convert on Base at
sub-$100 volumes and produced a degenerate (constant-zero) fee result. The
prior v2 draft addressed v1's confounds with tier-boundary and $1,000-scale
tranches; a KISS/cost re-review rejected that scale: ~$2,700 of round-trip
working capital to probe a fee tier the target audience does not reach, when
every cost endpoint except tier boundaries is measurable at micro volumes.

This protocol measures the off-ramp cost surface at the volumes x402
operators actually sweep: micro-receipt revenue accumulated into small
balances. Fixed fees, percentage fees, spreads, slippage, per-hop latency,
and bank-disbursement deductions are all observable in receipts at these
sizes; tier boundaries are explicitly out of scope (they are documented in
provider schedules and can be probed later as their own pre-registered
conversion when real revenue volume justifies it).

## Research questions

- Q1: What do independent providers (non-issuer rails) actually charge to
  convert micro USDC balances to fiat, realized vs advertised? (cross-provider arm)
- Q2: What does bank disbursement add in cost and latency after the exchange
  ledger, and how do exchange fees separate from bank deductions?
  (disbursement arm)
- Q3: Is v1's zero fee stable at micro volumes on the same Coinbase rail?
  (continuity arm)

## Design

Pre-registered provider-comparison measurement at micro volume; no randomized
control arm exists for a fiat off-ramp. Comparators are advertised provider
fee schedules (advertised vs realized), verbatim-recorded from live
quote/rate-card APIs at execution time.

### Arms and tranches (sealed on commit; one execution pass)

| Arm | Provider/rail | Tranches | Endpoints |
|-----|---------------|----------|-----------|
| A: cross-provider | two independent providers selected before sealing, restricted strictly to rails supporting native USDC deposits on Base (candidates: Dexter, Kraken; final selection recorded in the sealed runbook with verbatim fee-schedule snapshot) | $10 x1 each, then one residue sweep per provider (accumulated remainder, pre-registered formula: whatever the deposit leaves) | realized fee, quoted fee, spread vs mid, realized slippage vs quoted price (broker/AMM rails), per-hop latency |
| B: disbursement | exchange USD ledger -> external bank account via ACH, from one Arm A provider chosen at sealing | $20 x1 | exchange-quoted disbursement fee, external bank/intermediary deduction, net settled amount, hold/arrival latency |
| C: continuity | Coinbase Advanced Trade convert (Base deposit), v1 rail | $5 x2 | realized fee, quoted fee, spread vs mid, per-hop latency |

Total planned conversions: 7 (one pass, ascending order within arms;
no tranche re-run). `not_executed` outcomes are recorded, never retried.

### Working capital and cost budget

Total float: approximately $65, cycling back to the operator's own fiat.
Worst-case real cost budget: under $1 (advertised schedules imply roughly
$0.02 Kraken convert on $10, Dexter 0.1-0.5% on $10, ACH $0, Base gas
fractions of a cent per leg). If realized cost would exceed the budget,
records still commit as measured; the budget is a design expectation, not a
censoring rule.

### Out of scope (explicit)

- Tier-boundary probing at $250-$1,000+ volumes (requires manufactured
  float; provider schedules document these boundaries; can be pre-registered
  separately if real revenue ever reaches them)
- EUR/FX arms and any cross-currency decomposition
- Wire disbursement (ACH only; wire adds cost without changing the
  exchange-vs-bank separation logic at these amounts)
- Time-lapse re-measurement (folded into future work; Q3 covers continuity)

### Sealed-before-execution artifacts

- Provider selection and verbatim fee-schedule snapshots per provider
- Per-tranche amounts and replicate counts (table above)
- Endpoint definitions and the extended record schema (extends
  [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) with `provider_slug`,
  `arm`, `execution_status` (enum: `clean_fill`, `network_timeout`,
  `api_error`, `operator_interrupted`, `partial_fill`), `is_latency_valid`
  (boolean, see Statistical stance), `quoted_slippage_max` and
  `realized_slippage` (broker/AMM rails), `exchange_disbursement_fee_usd`,
  `external_bank_intermediary_fee_usd`, `net_amount_settled_usd`)
- Figure recipes (regenerated from run records only; no hand-typed numbers)
- Budget and working-capital source; wallet/keying rules inherited from v1
  (receiver wallet sourced from the secret store at execution time only)

### Provider selection criteria (fixed in the sealed text)

Selection of the two Arm A providers is locked at sealing, before any live
keying or funds move. Exactly two providers are chosen under these inclusion
criteria:

1. Deposit network parity: native USDC deposits on Base required (must be
   verified against the provider's current supported-networks documentation
   at selection time; Kraken's Base support is unconfirmed as of this draft
   and disqualifies Kraken if absent).
2. Account readiness: full verification completed and disbursement rails
   active prior to sealing; no unverified accounts permitted.
3. Rail typology: exactly one centralized-exchange alternative with an
   order-book/convert tool (e.g., Kraken) and one specialized fiat off-ramp
   or payments gateway (e.g., Dexter); no duplicate architectures.

## Statistical stance

- Fee/spread results per arm are deterministic observations at fixed volumes;
  no regression or elasticity modeling. Tabular point estimates and variance
  comparisons against advertised rate cards are the correct form.
- Latency: strictly descriptive across ALL arms — median, range, and observed
  run-order times only. No inferential distribution modeling, parametric
  confidence intervals, quantile projections, or SLA estimations will be
  performed at any sample size. The v1 latency endpoint (n=3) remains
  exploratory; v2 does not pool v1 and v2 latency.
- Mechanical latency exclusion rule (fixed in the sealed text): a record is
  excluded from latency calculations if and only if `is_latency_valid == false`.
  The script shall automatically set `is_latency_valid = false` if any HTTP
  call times out, if manual operator recovery is invoked, or if deposit
  credit polling exceeds the pre-registered timeout threshold.
  `is_latency_valid` is computed programmatically in the primary execution
  thread; any retry, exception, or recovery intervention sets it false.
  No post-execution judgment enters the exclusion; failure of any hop is a
  recorded outcome, never a dropped record.

## Known-observer limitation

Single-wallet, operator-executed measurement; timestamps from the operator
script. Every deviation is recorded verbatim per METHODOLOGY stop-and-record.
Scope caveat inherited from the v1 review: results describe the measured
providers and rails at micro volumes; they do not generalize to other
networks, providers, or volume tiers.

## Sequence

1. External validation of this redesign (short delta review, same Gemini
   session as the original v2 review); incorporate or rebut findings
2. Finalize provider selection (verify Base-deposit support per criterion 1),
   fee-schedule snapshots, and extended schema; update DATA_DICTIONARY.md and
   `validate_schema.py`; run the mock dry-run (non-transacting script
   verification and sandbox/zero-value API ping) so code correctness is
   proven BEFORE anything is frozen
3. Seal: commit protocol, schemas, and frozen recipes; freeze repository
   state; remove the DRAFT notice
4. Live execution pass only — the single transacting pass; preflight checks
   are read-only and no code changes are permitted from here on
5. Commit records verbatim; generate figures; write
   `results/usdc-fiat-sweep-v2.md`; update README index

## Acceptance criteria

- [ ] Delta review findings addressed or rebutted in this file before sealing
- [ ] Provider fee schedules snapshotted verbatim before first conversion
- [ ] All conversions one pass, ascending, no re-runs; failures recorded with
      `execution_status` and `is_latency_valid` set programmatically
- [ ] Records validate against the extended schema in CI
- [ ] Figures regenerate from committed records only
- [ ] Bank-disbursement cost and latency reported with exchange fees and
      external bank deductions separated
- [ ] Total float within the ~$65 budget; real cost within the <$1 budget
      (or the overage recorded and discussed in the results report)
- [ ] No private keys, seeds, or credentials in any committed file
