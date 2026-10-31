# Protocol: usdc-fiat-sweep-api

## Research Question

What is the true cost and friction of converting accumulated L2 USDC micropayment revenue to fiat when the conversion is executed programmatically through the Coinbase Advanced Trade API, and how does fixed-cost structure behave at micropayment scale on that rail?

This is a supplementary measurement for blog post clouatre-labs/clouatre.ca#2090; tracking issue clouatre-labs/clouatre.ca#2110.

This experiment supersedes the human-executed Coinbase retail design pre-registered in [../usdc-fiat-sweep/](../usdc-fiat-sweep/). The prior design was withdrawn before execution with zero outcomes observed; see the Superseded section in [../usdc-fiat-sweep/protocol.md](../usdc-fiat-sweep/protocol.md).

## Design

Dose-response measurement at five pre-registered amount levels, executed entirely by a committed script (`sweep.ts` in this directory) driven by environment-variable API keys. There is no randomized control arm and no LLM in the loop. The comparator is the advertised Coinbase Advanced Trade taker fee schedule: each realized conversion is compared against the fee that schedule predicts for that amount (advertised vs realized).

### Tranches

| Level | Amount | Replicates |
|-------|--------|------------|
| 1 | $1 | 2 |
| 2 | $5 | 2 |
| 3 | $20 | 2 |
| 4 | $100 | 1 |
| 5 | full remaining receiver balance | 2 (one executable) |

Nine pre-registered records total: 8 executed conversions plus 1 pre-registered `not_executed` record. No tranche is re-run because a number looked unfavorable.

### Funding and execution order

The tranches are pre-funded by a single inbound transfer into the receiver wallet before the first conversion, then executed in ascending amount order: $1, $1, $5, $5, $20, $20, $100, then the full-balance replicate. Every tranche is funded solely by the single pre-registered inbound transfer; no replenishment exists; the full-balance tranche consumes the residual at its position in the ascending sequence. The full-balance tranche is defined as the entire remaining receiver balance at that point in the sequence, so its replicate 1 is executable without any replenishment procedure and its replicate 2 is pre-registered as `not_executed` with reason "single-balance wallet: the full-balance tranche by definition exhausts the residual, so it has one executable replicate".

Funding is acquired by the operator in a single Coinbase purchase flow: approximately $153 of USDC plus approximately $0.10 of ETH bought on Coinbase and withdrawn together to the receiver wallet (`X402_PAY_TO`) as one inbound on-chain transfer. The transaction hash is recorded once via the script's `--funding` subcommand and reused on every record for independent recomputation. There is no external on-chain funding wallet and no additional key custody.

### API surface and authentication

The measurement targets the Coinbase Advanced Trade REST API on `https://api.cdp.coinbase.com` (paths under `/api/v3/brokerage/`), authenticated with JSON Web Tokens signed ES256 from the operator's Coinbase Developer Platform API keys (`CDP_API_KEY_ID` / `CDP_API_KEY_SECRET`), per the vendor documentation at `https://docs.cdp.coinbase.com/get-started/authentication/jwt-authentication` (claims: `sub` = key name, `iss` = `cdp`, `aud` = `[cdp_service]`, `nbf`, `exp` 120 s, `uri` = `METHOD host path`; sent as `Authorization: Bearer <jwt>`). Convert quote/execute endpoints verified against `https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/convert/create-convert-quote` (`POST /api/v3/brokerage/convert/quote`) and `.../convert/convert-trade` (`POST`/`GET /api/v3/brokerage/convert/trade/{trade_id}`). The legacy `api.coinbase.com` Exchange surface is not used. The unauthenticated spot-price endpoint (`GET https://api.developer.coinbase.com/v2/prices/USDC-USD/spot`) supplies the USDC mid at execution time.

The on-chain sweep legs are signed locally with `viem` from `X402_RECEIVER_PRIVATE_KEY`, which the operator exports in their shell at execution time only. Private key custody rules are in the Data Source section below.

### Endpoints (per tranche)

- Realized percentage fee.
- Fixed fee in USD.
- Spread vs USDC mid at execution time.
- Per-hop latency: on-chain send (Base mainnet), Coinbase credit/convert fill, fiat or USD balance spendable.

There is no `manual_steps` endpoint: execution is fully automated, so the manual-step metric is dropped for this experiment. The only manual operator action is the one-time funding purchase and withdrawal.

## Data Source

The receiver wallet of clouatre.ca x402 revenue (`X402_PAY_TO`, Base mainnet). The `MAINNET_PAYER` wallet is excluded: it is spend-side operating float, and payer self-tests are already excluded from revenue accounting.

### Receiver private key custody rule

`X402_RECEIVER_PRIVATE_KEY` is exported by the operator in their shell immediately before running the script with `--execute` and unset immediately afterwards (`unset X402_RECEIVER_PRIVATE_KEY`). It is never committed, never written to any file, never echoed or logged by the script, and never passed through any command-line argument. The Coinbase API secret (`CDP_API_KEY_SECRET`) is read from the shell environment only and likewise never logged, echoed, or persisted. Raw API responses are written verbatim to `sessions/raw/`; these response bodies contain no credentials.

Fallback if the receiver key is unavailable: do not execute. There is no key fallback for this experiment; a missing key aborts the run before any tranche.

## Budget

Total inbound volume: a single pre-funding transfer of approximately $153 USDC plus approximately $0.10 ETH. The seven fixed-amount tranches consume $152; the full-balance replicate sweeps the remainder (approximately $1). Expected consumption in spreads is single-digit dollars. The operator-approved maximum inbound volume for this experiment is $160; the superseded design's approximately $60 budget predates the added $100 tranche level and does not apply. The funding transfer transaction hash is recorded once in the funding record and reused in every run record for independent recomputation.

## Analysis Plan

Descriptive only: per-level medians and ranges, a fee-vs-amount curve with the published Advanced Trade taker schedule overlaid, and per-hop latency decomposition. No inferential test.

Statistical test: `none (descriptive dose-response)`.

## Threats to Validity

- The observer sees the fee schedule before executing. The pre-registration seal is on the outcome, not on schedule knowledge.
- The Coinbase fee schedule may change between pre-registration and execution. The schedule is recorded at execution time.
- Price slippage on the USDC/USD conversion is part of the measured spread, not noise.
- The script executes the conversion path deterministically; differences from the superseded human-executed design measure the rail and the automation together, not the rail alone.
- The convert fill timing is subject to Coinbase-side processing latency outside the script's control; per-hop timestamps come verbatim from API responses and chain receipts.

## Run Records

Raw observations go verbatim into `sessions/raw/`; structured run records go into `sessions/`. Transcription rules and the run-record schema are in [record-extraction.md](record-extraction.md) and [../../DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) (`usdc-fiat-sweep-api run-record schema`). The template's `analysis.json` schema governs the final `analysis.json` after the run.
