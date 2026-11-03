# Protocol: usdc-fiat-sweep-v2 (DRAFT - not sealed)

> **STATUS: DRAFT — externally reviewed, revisions incorporated, ready to seal.**
> Gemini independent review returned approve-with-revisions (8-point verdict);
> all six required revisions are incorporated in this text: Arm B network
> parity, Arm C fee decomposition, slippage endpoints, provider selection
> criteria, strictly descriptive latency with mechanical `is_latency_valid`
> exclusion rules, FX benchmark fixation, and the dry-run-before-seal sequence
> reorder. Nothing in this file authorizes execution yet. On sealing, this
> notice is removed, the file is committed, and the
> stop-and-record clauses of [METHODOLOGY.md](../../METHODOLOGY.md) apply.

## Motivation

v1 (`usdc-fiat-sweep-api`) verified Coinbase's 1:1 USDC/USD convert on Base at
sub-$100 volumes and produced a degenerate (constant-zero) fee result. External
review of v1 identified three confounds the design cannot address:

1. **Platform subsidy**: the zero fee is Coinbase's issuer-redemption policy on
   its own custodial rail, not a property of fiat off-ramps.
2. **Scale truncation**: max executed tranche $100 cannot detect tier
   boundaries, order-book spread, or retail-API allowance limits.
3. **Infrastructure coupling**: Base deposit into Coinbase custody is an
   integrated issuer rail; no independent provider or network was measured.

v1 also stopped at the exchange ledger: `fiat_spendable` means spendable on
Coinbase, not delivered to a bank account. v2 measures the off-ramp cost
surface beyond that boundary.

## Research questions

- Q1: Does the 1:1 convert hold at treasury-relevant volumes, or do tier
  boundaries / spreads appear? (tier-boundary arm)
- Q2: What is realized vs advertised off-ramp cost at independent providers
  (non-issuer rails)? (cross-provider arm)
- Q3: What does bank disbursement add in cost and latency after the exchange
  ledger? (disbursement endpoint)
- Q4: Is v1's zero fee stable over time, or a promotional snapshot?
  (time-lapse re-sweep)

## Design

Pre-registered dose-response and provider-comparison measurement; no
randomized control arm exists for a fiat off-ramp. Comparators are advertised
provider fee schedules (advertised vs realized), verbatim-recorded from live
quote/rate-card APIs at execution time (correcting v1's stale-overlay
deviation).

### Arms and tranches (sealed on commit; one execution pass)

| Arm | Provider/rail | Tranches | Endpoints |
|-----|---------------|----------|-----------|
| A: tier boundary | Coinbase Advanced Trade convert (Base deposit) | $250 x1, $500 x1, $1,000 x1 | realized fee, quoted fee, spread vs mid, per-hop latency, gas per leg |
| B: cross-provider | two independent providers selected before sealing, restricted strictly to rails supporting native USDC deposits on Base to prevent network gas asymmetry (candidates: Dexter, AsterPay, Kraken; final selection recorded in the sealed runbook with fee schedule snapshot) | $100 x1 each, plus each provider's minimum practical tranche | realized fee, quoted fee, spread vs mid, realized slippage vs quoted price (broker/AMM rails), per-hop latency |
| C: disbursement | exchange USD ledger -> external bank account (ACH first; wire once as boundary probe) | $500 x1 ACH, $500 x1 wire | exchange-quoted disbursement fee, external bank/intermediary deduction, net settled amount, hold/arrival latency |
| D: time-lapse | Coinbase Advanced Trade convert (repeat of v1 levels) | $20 x1, $100 x1 | realized fee, quoted fee, spread vs mid |

Total planned conversions: 11 (one pass, ascending order within arms;
no tranche re-run). `not_executed` outcomes are recorded, never retried.

### Volume-cap rationale

The $1,000 top tranche is a deliberate cap, not an oversight. Coinbase retail
convert volume tiers typically trigger at $10,000+ 30-day trailing volume,
which is out of scope for a retail convert endpoint; $1,000 adequately probes
consumer/prosumer retail convert spread boundaries. Raising the top tranche
to $5,000-$10,000 would increase automated compliance-hold,
source-of-funds-freeze, and multi-day disbursement-review risk that could
stall execution mid-protocol. Total gross working capital across arms is
approximately $3,120-$3,270, cycling back to the operator's own fiat.

### Sealed-before-execution artifacts

- Provider selection and verbatim fee-schedule snapshots per provider
- Per-tranche amounts and replicate counts (table above)
- Endpoint definitions and the extended record schema (extends
  [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) with `provider_slug`,
  `arm`, `execution_status` (enum: `clean_fill`, `network_timeout`,
  `api_error`, `operator_interrupted`, `partial_fill`), `is_latency_valid`
  (boolean, see Statistical stance), `quoted_slippage_max` and
  `realized_slippage` (broker/AMM rails), `exchange_disbursement_fee_usd`,
  `external_bank_intermediary_fee_usd`, `net_amount_settled_usd`, and the
  EUR-arm fields defined in the EUR-arm note)
- Figure recipes (regenerated from run records only; no hand-typed numbers)
- Budget and working-capital source; wallet/keying rules inherited from v1
  (receiver wallet sourced from the secret store at execution time only)

### Provider selection criteria (fixed in the sealed text)

Selection of the two Arm B providers is locked at sealing, before any live
keying or funds move. Exactly two providers are chosen under these inclusion
criteria:

1. Deposit network parity: native USDC deposits on Base required.
2. Account readiness: full verification completed and disbursement rails
   active prior to sealing; no unverified accounts permitted.
3. Rail typology: exactly one centralized-exchange alternative with an
   order-book/convert tool (e.g., Kraken) and one specialized fiat off-ramp
   or payments gateway (e.g., Dexter/AsterPay); no duplicate architectures.

### EUR-arm note

If AsterPay (or any EUR-settling provider) is selected, FX is a second
variable; results are reported separately, never averaged into USD arms. The
FX benchmark is fixed in the sealed text: mid-market EUR/USD is the real-time
rate polled from the Kraken EUR/USD public ticker at the exact UNIX timestamp
of conversion order submission; the benchmark rate and its timestamp are
recorded verbatim in every EUR record. Each EUR record decomposes the
conversion as: `gross_usdc_debited`, `eur_received_pre_disbursement`,
`benchmark_eur_usd_rate`, `effective_eur_usd_rate`, and
`implied_fx_spread_bps` (derived), so provider spread, provider fees, and FX
loss are separable.

## Statistical stance

- Fee/spread results per arm are deterministic observations at fixed volumes;
  no regression or elasticity modeling (v1 review finding: zero variance
  supports no dose-response inference).
- Latency: strictly descriptive across ALL arms — median, range, and observed
  run-order times only. No inferential distribution modeling, parametric
  confidence intervals, quantile projections, or SLA estimations will be
  performed at any sample size (cross-system financial-rail latency is
  multimodal and right-skewed; no n threshold licenses inference). The v1
  latency endpoint (n=3) remains exploratory; v2 does not pool v1 and v2
  latency.
- Mechanical latency exclusion rule (fixed in the sealed text): a record is
  excluded from latency calculations if and only if `is_latency_valid ==
  false`. The script shall automatically set `is_latency_valid = false` if
  any HTTP call times out, if manual operator recovery is invoked, or if
  deposit credit polling exceeds the pre-registered timeout threshold.
  `is_latency_valid` is computed programmatically in the primary execution
  thread; any retry, exception, or recovery intervention sets it false.
  No post-execution judgment enters the exclusion; failure of any hop is a
  recorded outcome, never a dropped record.

## Known-observer limitation

Single-wallet, operator-executed measurement; timestamps from the operator
script. Every deviation is recorded verbatim per METHODOLOGY stop-and-record.

## Sequence

1. External validation of this draft (Gemini review); incorporate or rebut
   each finding in this file
2. Finalize provider selection, fee-schedule snapshots, and extended schema;
   update DATA_DICTIONARY.md and `validate_schema.py`; run the mock dry-run
   (non-transacting script verification and sandbox/zero-value API ping) so
   code correctness is proven BEFORE anything is frozen
3. Seal: commit protocol, schemas, and frozen recipes; freeze repository
   state; remove the DRAFT notice
4. Live execution pass only — the single transacting pass; preflight
   checks are read-only and no code changes are permitted from here on
5. Commit records verbatim; generate figures; write
   `results/usdc-fiat-sweep-v2.md`; update README index and #2090

## Acceptance criteria

- [ ] All six external-review revisions incorporated (network parity, fee
      decomposition, slippage endpoints, selection criteria, latency rules,
      sequence reorder)
- [ ] Provider fee schedules snapshotted verbatim before first conversion
- [ ] All conversions one pass, ascending, no re-runs; failures recorded with
      `execution_status` and `is_latency_valid` set programmatically
- [ ] Records validate against the extended schema in CI
- [ ] Figures regenerate from committed records only
- [ ] Bank-disbursement cost and latency reported with exchange fees and
      external bank deductions separated
- [ ] No private keys, seeds, or credentials in any committed file
