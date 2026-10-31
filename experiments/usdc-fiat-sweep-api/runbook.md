# Runbook: usdc-fiat-sweep-api

Operator instructions for executing the nine executed conversions among the ten pre-registered records (the second full-balance replicate is pre-registered as `not_executed`). Execute one pass only; never re-run a tranche because a number looked unfavorable. All conversion work is done by [sweep.ts](sweep.ts); the operator never clicks through a conversion UI.

## Operator steps

Written for a non-involved owner. The receiver private key never appears in any file, any command-line argument, or any log output.

### a. Confirm the CDP key

1. `CDP_API_KEY_ID` and `CDP_API_KEY_SECRET` should already be present in the shell environment (Coinbase Developer Platform keys with Advanced Trade enabled). Confirm with `test -n "$CDP_API_KEY_ID" && test -n "$CDP_API_KEY_SECRET" && echo ok`. Do not print their values.
2. Confirm the key has the Convert (USDC to USD) permission enabled in the Coinbase Developer Platform console.

### b. One-time funding (manual, in the Coinbase app or website)

1. Buy approximately $153 of USDC and approximately $0.10 of ETH with USD in the Coinbase account.
2. Withdraw both assets in a single flow to the receiver wallet address `X402_PAY_TO` (Base mainnet). This is the only inbound funding transfer; verify the address character-by-character before sending. Real funds are involved in this step only; nothing else in this experiment settles funds without your key.
3. After the transfer confirms on Base, capture the inbound transaction hash from the Base explorer and run:

   ```sh
   bun run experiments/usdc-fiat-sweep-api/sweep.ts --funding
   ```

   and paste the funding transaction hash, the USDC buy amount, and the ETH buy amount when prompted. This writes `sessions/funding.json` once.

### c. Rehearsal, then execution

1. Rehearsal (synthetic, zero cost, writes nothing into the repo):

   ```sh
   bun run experiments/usdc-fiat-sweep-api/sweep.ts --dry-run
   ```

   It must exit 0 and leave the repository free of synthetic artifacts.

2. Export the receiver key in the current shell only, run the executor, then unset it:

   ```sh
   export X402_RECEIVER_PRIVATE_KEY=...   # paste from the secret store
   bun run experiments/usdc-fiat-sweep-api/sweep.ts --execute --yes
   unset X402_RECEIVER_PRIVATE_KEY
   ```

   The script prints the execution plan and refuses to run without `--yes`. If any balance looks wrong (receiver USDC below the expected funding, or nonzero balance before funding is recorded), it aborts before the first tranche.

### d. Afterwards

1. Confirm the key is unset: `test -z "$X402_RECEIVER_PRIVATE_KEY" && echo ok`.
2. Confirm `sessions/raw/` contains one artifact set per tranche and `sessions/` contains ten run records.
3. Verify the repository contains no key material: `git diff` and `git status` show only code, docs, and session records.

## Execution detail (performed by the script)

For each tranche in ascending order ($1, $1, $5, $5, $20, $20, $100, then the full-balance replicate):

1. Read the receiver USDC balance on-chain (Base mainnet RPC `https://mainnet.base.org`, USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`).
2. Obtain the Coinbase Base deposit address (environment `COINBASE_BASE_DEPOSIT_ADDRESS`; the address is static per Coinbase account, and the script refuses to run without it unless it can fetch it from the account API).
3. Send the tranche amount with `viem` (signed locally by `X402_RECEIVER_PRIVATE_KEY`), wait for the Base receipt, and record the transaction hash and timestamps.
4. Request a convert quote (USDC to USD) via the Advanced Trade API authenticated with a CDP ES256 JWT; execute the convert trade; poll the fill. Capture the quote id, fill, fees, and timestamps verbatim.
5. Write every raw API response verbatim into `sessions/raw/<tranche_id>/` and one structured run record into `sessions/`.

The pre-registered `not_executed` full-balance replicate is written directly by the script as a record with a null `amount_usdc` and a populated `notes` entry stating the pre-registered reason; it involves no transaction and no API call.

## After All Tranches

Confirm the repository is clean of key material, then transcribe nothing by hand: the run records are already schema-validated by the script at write time (`validate_schema.py`). Generate figures with the recipes in [../../recipe/README.md](../../recipe/README.md).
