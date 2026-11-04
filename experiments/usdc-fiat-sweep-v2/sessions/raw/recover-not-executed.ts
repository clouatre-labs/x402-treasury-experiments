// Recovery for Arm B tranches (cad-20, cad-eft) that cannot execute under the
// sealed design (see METHODOLOGY.md Execution Deviations, 2026-11-04): the
// sealed residue formula consumed the entire spendable USDC balance before
// Arm B, leaving 0 USDC for cad-20 and no CAD proceeds for cad-eft. Writes
// recorded-outcome records in the sealed baseRecord shape. Places no orders,
// moves no funds.
// Usage: bun recover-not-executed.ts <tranche_id> <arm> <fiat> <notes>
import { writeFileSync, readFileSync } from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(import.meta.dir, "..", "..", "..", "..");
const SESSIONS_DIR = path.resolve(import.meta.dir, "..");

const [trancheId, arm, fiat, notes] = process.argv.slice(2);
if (!trancheId || !arm || !fiat || !notes) {
  throw new Error("usage: recover-not-executed.ts <tranche_id> <arm> <fiat> <notes>");
}

const funding = JSON.parse(readFileSync(path.join(SESSIONS_DIR, "funding.json"), "utf8")) as { funding_tx_hash: string };

const record: Record<string, unknown> = {
  tranche_id: trancheId,
  replicate: 1,
  provider_slug: "kraken",
  arm,
  executed: false,
  synthetic: false,
  execution_status: "not_executed_below_minimum",
  is_latency_valid: false,
  fiat_currency: fiat,
  amount_usdc: null,
  fiat_received: null,
  order_txid: null,
  quoted_price: null,
  avg_fill_price: null,
  quoted_slippage_max: null,
  realized_slippage: null,
  pair_mid: null,
  mid_observed_at: null,
  timestamp_sent: null,
  timestamp_provider_credit: null,
  timestamp_fiat_spendable: null,
  timestamp_bank_arrival: null,
  tx_hash_in: null,
  funding_tx_hash: funding.funding_tx_hash,
  network_fee_usd: null,
  fixed_fee_usd: 0,
  quoted_fee_usd: 0,
  disbursement_fee_fiat: null,
  bank_intermediary_deduction: null,
  net_amount_settled: null,
  realized_fee_pct: null,
  spread_vs_mid_pct: null,
  notes,
};

const tmp = `/tmp/${trancheId}-recovery-record.json`;
writeFileSync(tmp, JSON.stringify(record, null, 2));
const run = Bun.spawnSync(["uv", "run", "python", "validate_schema.py", "--sweep-v2", tmp], { cwd: REPO_ROOT, stdout: "pipe", stderr: "pipe" });
if (run.exitCode !== 0) {
  throw new Error(`schema validation failed:\n${run.stdout.toString()}\n${run.stderr.toString()}`);
}
writeFileSync(path.join(SESSIONS_DIR, `${trancheId}.json`), JSON.stringify(record, null, 2) + "\n");
console.log(`${trancheId}: not_executed_below_minimum record written`);
