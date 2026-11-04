# Operator runbook: usdc-fiat-sweep-v2

This is a PUBLIC repository. Secret values are never printed, echoed, or
committed. Pre-registration is sealed: one execution pass, ascending tranche
order within arms, never re-run a tranche because a number looked
unfavorable; if a tranche fails, the record captures it (`execution_status`,
`is_latency_valid` — both set programmatically). Do not edit `protocol.md`,
`sweep.ts`, the tranche table, or recipe scripts during or after execution.

## Prerequisites (before sealing)

- Kraken account with: Base deposit verified (2026-11-03 live test), USDC
  balance >= 35 (Arms A/B), CAD bank destination configured under
  Funding -> Withdraw (EFT/Pateno; preflight fails without it), API key
  `x402-treasury-experiments-v2` with Query/Withdraw/Orders/Ledger
  permissions
- Coinbase/CDP account with USDC ~$40 and ~0.0002 ETH available for the
  funding step, and the Advanced Trade convert path working (v1-proven)

## Environment (secret store; never committed)

```
KRAKEN_API_KEY, KRAKEN_API_SECRET
KRAKEN_WITHDRAW_KEY     # name of the configured EFT bank destination
CDP_API_KEY_ID, CDP_API_KEY_SECRET
X402_RECEIVER_PRIVATE_KEY   # secret store, execution time only
X402_PAY_TO
COINBASE_BASE_DEPOSIT_ADDRESS
```

## Session sequence

1. `git pull` on `main` (post-merge and post-seal)
2. Fund the receiver wallet (pre-registered step, outside the measured
   pass): CDP/Coinbase buy ~$40 USDC + ~0.0002 ETH, withdraw on Base to
   `X402_PAY_TO`; verify the address character-by-character
3. `bun run experiments/usdc-fiat-sweep-v2/sweep.ts --funding` — paste the
   funding tx hash and amounts; writes `sessions/funding.json` once
4. `bun run experiments/usdc-fiat-sweep-v2/sweep.ts --preflight` — every
   check must PASS
5. `bun run experiments/usdc-fiat-sweep-v2/sweep.ts --dry-run` — must exit 0
   and leave the repo clean
6. In the shell: `export X402_RECEIVER_PRIVATE_KEY=...` (paste from the
   secret store), run
   `bun run experiments/usdc-fiat-sweep-v2/sweep.ts --execute --yes`, then
   `unset X402_RECEIVER_PRIVATE_KEY` and confirm with
   `test -z "$X402_RECEIVER_PRIVATE_KEY" && echo ok`
7. Verify `sessions/` holds exactly 6 records; `git status` shows only code,
   docs, and records
8. Generate the figure from `recipe/`:
   `uv run python recipe/usdc_fiat_sweep_v2_fig1_cost.py` (figures/ output)
9. Commit records, raw artifacts, and the figure as separate conventional
   commits (ASCII, signoff); write `results/usdc-fiat-sweep-v2.md`; update
   the README experiment index

## Stop-and-record

Every deviation is recorded verbatim in METHODOLOGY.md's Execution
Deviations section at the moment it happens, per protocol. The script sets
`execution_status` and `is_latency_valid` mechanically; no manual edits to
records, ever. If the bank-arrival hop is still pending when the pass ends,
the record notes it and bank arrival is confirmed later via a recorded
deviation entry (bank statement), never by rewriting the record.
