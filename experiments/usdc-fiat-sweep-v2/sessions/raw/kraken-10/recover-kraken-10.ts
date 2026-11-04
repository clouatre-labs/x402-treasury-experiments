// Recovery for tranche kraken-10 (see METHODOLOGY.md Execution Deviations,
// 2026-11-04): the sealed pass filled this sell but crashed before writing
// the record. This script rebuilds the record VERBATIM from read-only Kraken
// queries of the already-executed fill (QueryOrders + QueryTrades with the
// order's trade ids). It places no orders and moves no funds.
// is_latency_valid = false per the mechanical exclusion rule (recovery
// intervention). pair_mid/mid_observed_at/quoted_price are re-observed from
// the live ticker post-crash and flagged in notes.
import { createHmac } from "node:crypto";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import path from "node:path";

const KRAKEN_API = "https://api.kraken.com";
const REPO_ROOT = path.resolve(import.meta.dir, "..", "..", "..", "..", "..");
const SESSIONS_DIR = path.resolve(import.meta.dir, "..", "..");
const RAW_DIR = import.meta.dir;
const SLIPPAGE_MAX_FRACTION = 0.001;
const ORDER_TXID = "OX6CYI-EUPXR-OWAK3C";

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}
function jsonSafe(value: unknown): string {
  return JSON.stringify(value, (_k, v) => (typeof v === "bigint" ? v.toString() : v), 2) + "\n";
}
async function krakenPrivate(endpoint: string, data: Record<string, string | number> = {}): Promise<Record<string, unknown>> {
  const key = process.env.KRAKEN_API_KEY!.trim();
  const secret = process.env.KRAKEN_API_SECRET!.trim();
  const nonce = Date.now().toString();
  const params = new URLSearchParams({ nonce, ...Object.fromEntries(Object.entries(data).map(([k, v]) => [k, String(v)])) });
  const body = params.toString();
  const apiPath = `/0/private/${endpoint}`;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(nonce + body)));
  const signature = createHmac("sha512", Buffer.from(secret, "base64")).update(apiPath).update(Buffer.from(digest)).digest("base64");
  const response = await fetch(`${KRAKEN_API}${apiPath}`, {
    method: "POST",
    headers: { "API-Key": key, "API-Sign": signature, "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const parsed = (await response.json()) as { error: string[]; result?: Record<string, unknown> };
  if (parsed.error.length > 0) throw new Error(`Kraken ${endpoint} failed: ${parsed.error.join("; ")}`);
  return (parsed.result ?? {}) as Record<string, unknown>;
}
async function krakenTickerMid(pair: string): Promise<{ mid: number; observedAt: string }> {
  const res = (await (await fetch(`${KRAKEN_API}/0/public/Ticker?pair=${pair}`)).json()) as { result: Record<string, { a: string[]; b: string[] }> };
  const t = Object.values(res.result)[0]!;
  return { mid: (Number(t.a[0]) + Number(t.b[0])) / 2, observedAt: nowIso() };
}
async function krakenTopAsk(pair: string): Promise<{ ask: number }> {
  const res = (await (await fetch(`${KRAKEN_API}/0/public/Depth?pair=${pair}&count=1`)).json()) as { result: Record<string, { asks: [string, string, number][] }> };
  return { ask: Number(Object.values(res.result)[0]!.asks[0]![0]) };
}

async function main(): Promise<void> {
  // Read-only re-query of the executed order and its trades.
  const qo = await krakenPrivate("QueryOrders", { pair: "USDCUSD", txid: ORDER_TXID, trades: "true" });
  writeFileSync(path.join(RAW_DIR, "query-orders.json"), jsonSafe(qo));
  const orderInfo = qo[ORDER_TXID] as Record<string, unknown>;
  if (!orderInfo || orderInfo.status !== "closed") {
    throw new Error(`order ${ORDER_TXID} not observed closed: ${JSON.stringify(orderInfo)}`);
  }
  const tradeIds = (orderInfo.trades as string[]).join(",");
  const trades = await krakenPrivate("QueryTrades", { txid: tradeIds });
  writeFileSync(path.join(RAW_DIR, "query-trades.json"), jsonSafe(trades));

  // Post-crash quote observation (flagged in notes).
  const mid = await krakenTickerMid("USDCUSD");
  const depth = await krakenTopAsk("USDCUSD");

  const volExec = Number(orderInfo.vol_exec ?? 0);
  const cost = Number(orderInfo.cost ?? 0);
  const fee = Number(orderInfo.fee ?? 0);
  const avgFill = volExec > 0 ? cost / volExec : Number.NaN;
  if (!Number.isFinite(avgFill)) throw new Error("closed order missing vol_exec/cost");

  const funding = JSON.parse(readFileSync(path.join(SESSIONS_DIR, "funding.json"), "utf8")) as { funding_tx_hash: string };

  const record: Record<string, unknown> = {
    tranche_id: "kraken-10",
    replicate: 1,
    provider_slug: "kraken",
    arm: "A",
    executed: true,
    synthetic: false,
    execution_status: Number(orderInfo.vol ?? 0) - volExec > 1e-8 ? "partial_fill" : "clean_fill",
    is_latency_valid: false, // mechanical rule: recovery intervention
    fiat_currency: "USD",
    amount_usdc: volExec,
    fiat_received: Number(cost.toFixed(6)),
    order_txid: ORDER_TXID,
    quoted_price: depth.ask,
    avg_fill_price: Number(avgFill.toFixed(8)),
    quoted_slippage_max: SLIPPAGE_MAX_FRACTION,
    realized_slippage: Number(((avgFill - depth.ask) / depth.ask).toFixed(10)),
    pair_mid: Number(mid.mid.toFixed(8)),
    mid_observed_at: mid.observedAt,
    timestamp_sent: null,
    timestamp_provider_credit: new Date(Number(orderInfo.closetm) * 1000).toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    timestamp_fiat_spendable: new Date(Number(orderInfo.closetm) * 1000).toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    timestamp_bank_arrival: null,
    tx_hash_in: null,
    funding_tx_hash: funding.funding_tx_hash,
    network_fee_usd: 0,
    fixed_fee_usd: Number(fee.toFixed(6)),
    quoted_fee_usd: Number((0.002 * cost).toFixed(6)),
    disbursement_fee_fiat: null,
    bank_intermediary_deduction: null,
    net_amount_settled: null,
    realized_fee_pct: Number((100 * fee / cost).toFixed(6)),
    spread_vs_mid_pct: Number((100 * (volExec * mid.mid - cost) / (volExec * mid.mid)).toFixed(6)),
    notes:
      "record recovered from read-only QueryOrders/QueryTrades of the already-executed fill after a QueryTrades " +
      "order-txid crash (see METHODOLOGY.md Execution Deviations 2026-11-04); is_latency_valid=false per mechanical " +
      "recovery rule; pair_mid/mid_observed_at/quoted_price re-observed from the live ticker post-crash, so " +
      "realized_slippage and spread_vs_mid_pct are vs a post-crash quote observation, not the placement-time book",
  };

  const tmp = "/tmp/kraken-10-recovery-record.json";
  writeFileSync(tmp, JSON.stringify(record, null, 2));
  const run = Bun.spawnSync(["uv", "run", "python", "validate_schema.py", "--sweep-v2", tmp], { cwd: REPO_ROOT, stdout: "pipe", stderr: "pipe" });
  if (run.exitCode !== 0) {
    throw new Error(`schema validation failed:\n${run.stdout.toString()}\n${run.stderr.toString()}`);
  }
  writeFileSync(path.join(SESSIONS_DIR, "kraken-10.json"), JSON.stringify(record, null, 2) + "\n");
  mkdirSync(RAW_DIR, { recursive: true });
  console.log(`kraken-10: recovered record written (status=${record.execution_status}, is_latency_valid=false)`);
}
await main();
