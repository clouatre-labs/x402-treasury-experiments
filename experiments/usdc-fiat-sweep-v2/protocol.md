# Protocol: usdc-fiat-sweep-v2 (DRAFT - externally reviewed, redesigned, ready to re-seal)

> **STATUS: DRAFT — reviewed and operationally verified, ready to seal.**
> Full design review (Gemini): approve-with-revisions, all revisions applied.
> Delta review of the micro-volume redesign: approve-with-revisions, all
> four revisions applied. Design simplified to a single provider (Kraken)
> after a documented gateway-selection survey disqualified the gateway slot
> (see Gateway selection survey). Rail facts verified against Kraken's live
> API on 2026-11-03. Nothing in this file authorizes execution yet. On
> sealing, this notice is removed and the stop-and-record clauses of
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

- Q1: What does an independent exchange (non-issuer rail) actually charge to
  convert micro USDC balances to fiat, realized vs advertised?
  (independent-exchange arm)
- Q2: What does fiat disbursement add in cost and latency after the exchange
  ledger, and how do exchange fees separate from receiving-bank deductions
  on a domestic CAD EFT rail? (disbursement arm)
- Q3: Is v1's zero fee stable at micro volumes on the same Coinbase rail?
  (continuity arm)
- Q4 (qualitative): What do fiat-off-ramp gateways quote for micro-scale
  USDC off-ramps, and why were they disqualified from measurement?
  (gateway selection survey, recorded finding)

## Claim scope (fixed)

All claims in this experiment are restricted to programmatic micro-receipt
off-ramps at $5-$20 scale for automated agent/API workflows. The design does
not speak to treasury off-ramping at institutional volumes, order-book
depth, batch-vs-real-time settlement tradeoffs, or fiat off-ramp cost in
general; those questions require different designs and are out of scope.

## Design

Pre-registered provider-comparison measurement at micro volume; no randomized
control arm exists for a fiat off-ramp. Comparators are advertised provider
fee schedules (advertised vs realized), verbatim-recorded from live
quote/rate-card APIs at execution time.

### Arms and tranches (sealed on commit; one execution pass)

| Arm | Provider/rail | Tranches | Endpoints |
|-----|---------------|----------|-----------|
| A: independent exchange | Kraken (order book USDC/USD, stablecoin fee schedule; USDC deposited natively on Base, verified by live test deposit 2026-11-03) | $10 x1 order-book sell, then one residue sweep defined exactly as `amount = balance_provider_usdc_spendable` at sweep time, with the guard below | realized fee, quoted fee (0.20% advertised), spread vs mid, realized slippage vs quoted price, per-hop latency |
| B: disbursement | Kraken USD ledger -> CAD -> Canadian bank via EFT (Pateno), selected by live `WithdrawMethods` query 2026-11-03 | sell 20 USDC -> CAD x1, then EFT withdrawal of the CAD proceeds x1 | exchange-quoted convert fee and EFT fee (0.35% advertised), external bank/intermediary deduction, net settled amount, hold/arrival latency |
| C: continuity | Coinbase Advanced Trade convert (Base deposit), v1 rail | $5 x2 | realized fee, quoted fee, spread vs mid, per-hop latency |

Total planned conversions/withdrawals: 6 transactions (one pass, ascending
order within arms; no tranche re-run). `not_executed` outcomes are recorded,
never retried.

### Verbatim rail snapshot (live API queries, 2026-11-03)

- Kraken `AssetPairs` USDC/USD: `ordermin` 5 USDC, `costmin` 0.5 USD;
  stablecoin fee schedule 0.20% maker / 0.20% taker at entry tier (Kraken
  support documentation, stablecoin/FX markets, maker equals taker)
- Kraken `WithdrawMethods` ZCAD: `EFT (Pateno)` minimum 20.00 CAD, fee
  0.00 CAD + 0.35%; `Interac E-Transfer` minimum 15.00 CAD, fee 10.00 CAD;
  `Bank Frick (SWIFT) International` minimum 100.00, fee 13.00
- Kraken `WithdrawMethods` ZUSD: only `Bank Frick (SWIFT) International`
  (minimum 100.00 USD, fee 13.00 USD) — no ACH rail exists on this account;
  the originally planned ACH arm is replaced by the CAD EFT arm above
- Receiver wallet (`X402_PAY_TO`) on-chain USDC balance: 0.00 (v1 swept it
  in full), so a funding step is part of the sealed runbook

### Funding step (pre-registered, outside the measured pass)

One funding operation before tranche execution: purchase approximately
$40 USDC plus ~0.0002 ETH Base gas float via the CDP/Coinbase flow, withdraw
USDC on Base to the receiver wallet (`X402_PAY_TO`), recorded verbatim into
`sessions/funding.json` exactly as in v1. Funding is working-capital
placement, not measurement; its cost is recorded but excluded from sweep
endpoints.

### Residue-sweep guard (fixed formula)

Let `amount_residue = balance_provider_usdc_spendable` (the provider's
spendable USDC balance at sweep time, exactly as reported by its API — not
gross deposited, not net-of-anticipated-fees). If
`amount_residue >= provider_min_trade_amount` (the provider's documented
minimum trade size, snapshotted at sealing), execute the convert for
`amount_residue`. If `amount_residue < provider_min_trade_amount`, record
the tranche as `not_executed_below_minimum` with the observed residual
balance and the provider threshold verbatim; this is a recorded outcome,
not a failure exception, and the pass continues.

### Platform-minimum handling (sealed rule)

If any API rejects a conversion or disbursement because the amount is below
a platform minimum (trade minimum, withdrawal minimum, or equivalent), the
script records the error response verbatim, sets
`execution_status = "rejected_below_minimum"`, and proceeds to the next
tranche without halting the runbook. A minimum rejection is a valid
cost-surface observation, not an execution fault.

### Gateway selection survey (recorded finding, Q4)

The gateway architecture (specialized fiat off-ramp, non-exchange) was
probed for measurement and disqualified at selection; the survey itself is
recorded as a qualitative finding. All quotes observed 2026-11-03:

| Provider | Offer for $10 USDC sell | Disqualification reason |
|----------|------------------------|--------------------------|
| Dexter | none — no operator fiat off-ramp exists in the product (facilitator/wallet infrastructure only) | no fiat disbursement capability |
| Transak | 10 USDC -> 5.86 USD via card payout on Ethereum mainnet only (~41% effective cost at $10, quote observed in vendor widget) | Ethereum-only sell rail (no Base), card payout not bank deposit, effective cost off-scale |

Consequence: the cross-architecture comparison narrows to independent
exchange (Kraken) vs issuer rail (Coinbase), which is what the data can
support; the gateway cost surface is documented by this survey instead.

### Working capital and cost budget

Float on Kraken: 101 USDC already deposited (working capital, cycles back
to the operator's fiat at Arm B); Coinbase side approximately $40 funded
per the funding step. Worst-case real cost budget: under $1 across all
arms (advertised schedules imply roughly 0.20% on Arm A sells, 0.20% +
0.35% on the Arm B convert-and-EFT path, ~0% on Arm C, Base gas fractions
of a cent per leg). If realized cost exceeds the budget, records still
commit as measured; the budget is a design expectation, not a censoring
rule.

### CAD leg note (fixed)

Arm B sells USDC into CAD on the Kraken order book before the EFT
withdrawal; the USDC/CAD pair mid is observed from the same order book at
execution time and recorded verbatim, so the FX leg is measured with the
same realized-vs-quoted logic as the USD legs. CAD proceeds are reported
separately and never averaged into USD results.

### Sealed-before-execution artifacts

- Provider selection and verbatim fee-schedule snapshots per provider
- Per-tranche amounts and replicate counts (table above)
- Endpoint definitions and the extended record schema (extends
  [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) with `provider_slug`,
  `arm`, `execution_status` (enum: `clean_fill`, `network_timeout`,
  `api_error`, `operator_interrupted`, `partial_fill`,
  `rejected_below_minimum`, `not_executed_below_minimum`), `is_latency_valid`
  (boolean, see Statistical stance), `quoted_slippage_max` and
  `realized_slippage` (broker/AMM rails), `exchange_disbursement_fee_usd`,
  `external_bank_intermediary_fee_usd`, `net_amount_settled_usd`)
- Figure recipes (regenerated from run records only; no hand-typed numbers)
- Budget and working-capital source; wallet/keying rules inherited from v1
  (receiver wallet sourced from the secret store at execution time only)

### Out of scope (explicit)

- Tier-boundary probing at $250-$1,000+ volumes (requires manufactured
  float; provider schedules document these boundaries; can be pre-registered
  separately if real revenue ever reaches them)
- EUR and non-CAD fiat legs
- Wire/SWIFT disbursement (measured costs documented in the rail snapshot;
  a $13 fee on a $100 minimum is recorded as a survey fact, not executed)
- Time-lapse re-measurement (folded into future work; Q3 covers continuity)

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

1. External validation (done: full design review + delta review, both
   approve-with-revisions, all revisions applied)
2. Finalize rail snapshots (done: live API queries recorded in the Verbatim
   rail snapshot section); update DATA_DICTIONARY.md and
   `validate_schema.py`; run the preflight checklist, which must verify:
   Kraken API key auth (Balance query), EFT (Pateno) minimum 20.00 CAD <=
   the planned Arm B tranche proceeds, USDC/CAD order book reachable, and
   receiver wallet funded per the funding step; then run the mock dry-run
   (non-transacting script verification and read-only API pings) so code
   correctness is proven BEFORE anything is frozen
3. Seal: commit protocol, schemas, and frozen recipes; freeze repository
   state; remove the DRAFT notice
4. Live execution pass only — the single transacting pass; preflight checks
   are read-only and no code changes are permitted from here on
5. Commit records verbatim; generate figures; write
   `results/usdc-fiat-sweep-v2.md`; update README index

## Acceptance criteria

- [ ] Delta review findings addressed (claim-scope restriction, residue
      formula and guard, platform-minimum failure classification,
      disbursement-minimum preflight check — all applied)
- [ ] Kraken rail snapshot recorded verbatim (done, from live API queries)
- [ ] All transactions one pass, ascending, no re-runs; failures recorded with
      `execution_status` and `is_latency_valid` set programmatically
- [ ] Records validate against the extended schema in CI
- [ ] Figures regenerate from committed records only
- [ ] Disbursement cost and latency reported with exchange fees and
      external bank deductions separated
- [ ] Real cost within the <$1 budget (or the overage recorded and discussed
      in the results report)
- [ ] No private keys, seeds, or credentials in any committed file
