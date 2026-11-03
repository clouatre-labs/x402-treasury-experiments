# Protocol: usdc-fiat-sweep-v2 (DRAFT - not sealed)

> **STATUS: DRAFT.** This protocol is pre-registration text under construction.
> It must pass external methodological review (planned: Gemini independent
> review of design, mirroring the v1 review) before it is sealed by commit and
> before any tranche executes. Nothing in this file authorizes execution yet.
> On sealing, this notice is removed, the file is committed, and the
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
| B: cross-provider | two independent providers selected before sealing (candidates: Dexter, AsterPay EUR rail, Kraken deposit; final selection recorded in the sealed runbook with fee schedule snapshot) | $100 x1 each, plus each provider's minimum practical tranche | realized fee, quoted fee, spread vs mid, per-hop latency |
| C: disbursement | exchange USD ledger -> external bank account (ACH first; wire once as boundary probe) | $500 x1 ACH, $500 x1 wire | disbursement fee, hold/arrival latency, arrival amount vs sent amount |
| D: time-lapse | Coinbase Advanced Trade convert (repeat of v1 levels) | $20 x1, $100 x1 | realized fee, quoted fee, spread vs mid |

Total planned conversions: 11 (one pass, ascending order within arms;
no tranche re-run). `not_executed` outcomes are recorded, never retried.

### Sealed-before-execution artifacts

- Provider selection and verbatim fee-schedule snapshots per provider
- Per-tranche amounts and replicate counts (table above)
- Endpoint definitions and the extended record schema (extends
  [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) with
  `disbursement_fee_usd`, `timestamp_bank_arrival`, `arrival_amount_usd`,
  `provider_slug`, `arm`)
- Figure recipes (regenerated from run records only; no hand-typed numbers)
- Budget and working-capital source; wallet/keying rules inherited from v1
  (receiver wallet sourced from the secret store at execution time only)

### EUR-arm note

If AsterPay's EUR rail is selected, FX is a second variable; records carry the
mid at execution and the post-trade FX statement verbatim, and EUR results are
reported separately, never averaged into USD arms.

## Statistical stance

- Fee/spread results per arm are deterministic observations at fixed volumes;
  no regression or elasticity modeling (v1 review finding: zero variance
  supports no dose-response inference).
- Latency: reported per-tranche, descriptive only unless an arm yields >= 8
  clean observations; failure of any hop is a recorded outcome, never a
  dropped record (no post hoc pruning; exclusions must be mechanical,
  schema-level, and stated in the sealed protocol).
- The v1 latency endpoint (n=3) remains exploratory; v2 does not pool v1 and
  v2 latency.

## Known-observer limitation

Single-wallet, operator-executed measurement; timestamps from the operator
script. Every deviation is recorded verbatim per METHODOLOGY stop-and-record.

## Sequence

1. External validation of this draft (Gemini review); incorporate or rebut
   each finding in this file
2. Finalize provider selection, fee-schedule snapshots, and extended schema;
   update DATA_DICTIONARY.md and `validate_schema.py`
3. Seal: commit this file minus the DRAFT notice; freeze recipes
4. Preflight, dry-run, then the single execution pass (runbook modeled on v1's)
5. Commit records verbatim; generate figures; write
   `results/usdc-fiat-sweep-v2.md`; update README index and #2090

## Acceptance criteria

- [ ] External review findings addressed or rebutted in this file before sealing
- [ ] Provider fee schedules snapshotted verbatim before first conversion
- [ ] All conversions one pass, ascending, no re-runs; failures recorded
- [ ] Records validate against the extended schema in CI
- [ ] Figures regenerate from committed records only
- [ ] Bank-disbursement cost and latency reported as first-class endpoints
- [ ] No private keys, seeds, or credentials in any committed file
