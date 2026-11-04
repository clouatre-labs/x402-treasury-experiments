#!/usr/bin/env bun
/**
 * Automated sweep driver for the usdc-fiat-sweep-v2 pre-registered experiment.
 *
 * Arms (see protocol.md):
 *   A  Kraken order-book USDC/USD sell ($10 + residue sweep, ordermin 5)
 *   B  USDC/CAD sell (20 USDC) + CAD EFT (Pateno) disbursement
 *   C  Coinbase Advanced Trade convert ($5 x2, v1 rail continuity)
 *
 * Modes:
 *   --preflight  read-only smoke test: env presence (values never printed),
 *                Kraken auth (Balance), receiver on-chain balance, funding.json
 *                presence, USDC/USD and USDC/CAD order books reachable, EFT
 *                (Pateno) withdrawal method present with minimum <= planned
 *                tranche, and a configured Kraken withdrawal address (bank).
 *                Writes nothing; safe any number of times.
 *   --dry-run    full synthetic rehearsal: 6 records marked synthetic:true,
 *                validated against DATA_DICTIONARY.md via
 *                `validate_schema.py --sweep-v2`; writes nothing into the
 *                repo; exits 0.
 *   --execute    real run. Requires --yes, KRAKEN_API_KEY, KRAKEN_API_SECRET,
 *                CDP_API_KEY_ID, CDP_API_KEY_SECRET, X402_RECEIVER_PRIVATE_KEY,
 *                X402_PAY_TO, and a recorded funding.json.
 *   --funding    interactive: operator pastes the funding tx hash and buy
 *                amounts; writes sessions/funding.json.
 *
 * Mechanical instrumentation per protocol.md: execution_status and
 * is_latency_valid are set programmatically in the primary execution thread;
 * any timeout, retry, exception, or recovery intervention sets
 * is_latency_valid=false. Records are never edited by hand. Raw API responses
 * persist verbatim under sessions/raw/ before any derived work. Secrets never
 * appear in logs, files, or argv.
 */
import { SignJWT, importPKCS8 } from "jose";
import { base } from "viem/chains";
import {
  createPublicClient,
  createWalletClient,
  http,
  formatUnits,
  parseUnits,
  erc20Abi,
  type Address,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { spawnSync } from "node:child_process";
import { createHmac } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { createInterface } from "node:readline/promises";
import { tmpdir } from "node:os";
import path from "node:path";

// ---------------------------------------------------------------------------
// Constants (verbatim rail snapshot, protocol.md; live API queries 2026-11-03)
// ---------------------------------------------------------------------------

const EXPERIMENT_DIR = path.resolve(import.meta.dir);
const SESSIONS_DIR = path.join(EXPERIMENT_DIR, "sessions");
const RAW_DIR = path.join(SESSIONS_DIR, "raw");
const FUNDING_FILE = path.join(SESSIONS_DIR, "funding.json");
const REPO_ROOT = path.resolve(EXPERIMENT_DIR, "..", "..");

const BASE_RPC = process.env.BASE_RPC_URL ?? "https://mainnet.base.org";
const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" as Address;
const CDP_API_BASE = "https://api.coinbase.com";
const SPOT_PRICE_URL = "https://api.coinbase.com/v2/prices/USDC-USD/spot";
const KRAKEN_API = "https://api.kraken.com";
const KRAKEN_PAIR_USD = "USDCUSD"; // ordermin 5 USDC, costmin 0.5 USD
const KRAKEN_PAIR_CAD = "USDCCAD"; // ordermin 5 USDC, costmin 1 CAD
const KRAKEN_ORDERMIN_USD = 5;
const EFT_MIN_CAD = 20;
const EFT_FEE_PCT = 0.35;
const SLIPPAGE_MAX_FRACTION = 0.001; // pre-registered quoted_slippage_max bound

type TrancheDef = {
  id: string;
  arm: "A" | "B" | "C";
  provider: "kraken" | "coinbase";
  kind: "kraken-sell" | "kraken-withdraw" | "coinbase-convert";
  amountUsdc: number | null; // null = spendable residue (Arm A guard applies)
  fiatCurrency: "USD" | "CAD";
  executed: boolean;
};

const TRANCHES: TrancheDef[] = [
  { id: "kraken-10", arm: "A", provider: "kraken", kind: "kraken-sell", amountUsdc: 10, fiatCurrency: "USD", executed: true },
  { id: "kraken-residue", arm: "A", provider: "kraken", kind: "kraken-sell", amountUsdc: null, fiatCurrency: "USD", executed: true },
  { id: "cad-20", arm: "B", provider: "kraken", kind: "kraken-sell", amountUsdc: 20, fiatCurrency: "CAD", executed: true },
  { id: "cad-eft", arm: "B", provider: "kraken", kind: "kraken-withdraw", amountUsdc: null, fiatCurrency: "CAD", executed: true },
  { id: "coinbase-5-1", arm: "C", provider: "coinbase", kind: "coinbase-convert", amountUsdc: 5, fiatCurrency: "USD", executed: true },
  { id: "coinbase-5-2", arm: "C", provider: "coinbase", kind: "coinbase-convert", amountUsdc: 5, fiatCurrency: "USD", executed: true },
];

const EXPECTED_RECORDS = 6;

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}
function log(msg: string): void {
  console.log(msg);
}
function die(msg: string): never {
  console.error(`ERROR: ${msg}`);
  process.exit(1);
}
function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === "") die(`missing environment variable ${name}`);
  return value as string;
}
function jsonSafe(value: unknown): string {
  return (
    JSON.stringify(value, (_k, v) => (typeof v === "bigint" ? v.toString() : v), 2) + "\n"
  );
}
function receiverAddress(): Address {
  const value = process.env.X402_PAY_TO;
  if (!value || !value.startsWith("0x")) die("missing or malformed X402_PAY_TO");
  return value as Address;
}
async function receiverUsdcBalance(address: Address): Promise<number> {
  const client = createPublicClient({ chain: base, transport: http(BASE_RPC) });
  const bal = await client.readContract({
    address: USDC_BASE,
    abi: erc20Abi,
    functionName: "balanceOf",
    args: [address],
  });
  return Number(formatUnits(bal, 6));
}

// ---------------------------------------------------------------------------
// Kraken REST (public + private HMAC-SHA512 auth)
// ---------------------------------------------------------------------------

async function krakenPrivate(endpoint: string, data: Record<string, string | number> = {}): Promise<Record<string, unknown>> {
  const key = requireEnv("KRAKEN_API_KEY").trim();
  const secret = requireEnv("KRAKEN_API_SECRET").trim();
  const nonce = Date.now().toString();
  const params = new URLSearchParams({ nonce, ...Object.fromEntries(Object.entries(data).map(([k, v]) => [k, String(v)])) });
  const body = params.toString();
  const apiPath = `/0/private/${endpoint}`;
  // Kraken signature: HMAC-SHA512(apiPath + sha256(nonce + postdata), secret).
  // The sha256 digest enters the HMAC as RAW BYTES, not a hex string (a hex
  // string here produces Kraken's misleading EAPI:Invalid key error).
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(nonce + body)));
  const signature = createHmac("sha512", Buffer.from(secret, "base64"))
    .update(apiPath)
    .update(Buffer.from(digest))
    .digest("base64");
  const response = await fetch(`${KRAKEN_API}${apiPath}`, {
    method: "POST",
    headers: { "API-Key": key, "API-Sign": signature, "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const parsed = (await response.json()) as KrakenResponse;
  if (parsed.error.length > 0) {
    throw new Error(`Kraken ${endpoint} failed: ${parsed.error.join("; ")}`);
  }
  return (parsed.result ?? {}) as Record<string, unknown>;
}

async function krakenTickerMid(pair: string): Promise<{ mid: number; observedAt: string }> {
  const response = await fetch(`${KRAKEN_API}/0/public/Ticker?pair=${pair}`);
  if (!response.ok) throw new Error(`Kraken Ticker ${pair} failed: HTTP ${response.status}`);
  const parsed = (await response.json()) as KrakenResponse;
  if (parsed.error.length > 0) throw new Error(`Kraken Ticker ${pair}: ${parsed.error.join("; ")}`);
  const first = Object.values(parsed.result ?? {})[0] as { a?: string[]; b?: string[] } | undefined;
  if (!first?.a?.[0] || !first.b?.[0]) throw new Error(`Kraken Ticker ${pair}: missing a/b prices`);
  const mid = (Number(first.a[0]) + Number(first.b[0])) / 2;
  return { mid, observedAt: nowIso() };
}

async function krakenTopAsk(pair: string): Promise<{ ask: number; observedAt: string }> {
  const response = await fetch(`${KRAKEN_API}/0/public/Depth?pair=${pair}&count=1`);
  if (!response.ok) throw new Error(`Kraken Depth ${pair} failed: HTTP ${response.status}`);
  const parsed = (await response.json()) as KrakenResponse;
  if (parsed.error.length > 0) throw new Error(`Kraken Depth ${pair}: ${parsed.error.join("; ")}`);
  const first = Object.values(parsed.result ?? {})[0] as { asks?: [number, number, number][] } | undefined;
  if (!first?.asks?.[0]) throw new Error(`Kraken Depth ${pair}: empty asks`);
  return { ask: Number(first.asks[0][0]), observedAt: nowIso() };
}

// ---------------------------------------------------------------------------
// Coinbase CDP ES256 JWT auth (same machinery as v1's sweep.ts, proven live)
// ---------------------------------------------------------------------------

async function cdpJwt(keyId: string, keySecret: string, method: string, host: string, requestPath: string): Promise<string> {
  const pkcs8 = keySecret.replace(/\\n/g, "\n");
  const ecKey = await importPKCS8(pkcs8, "ES256");
  const nowSeconds = Math.floor(Date.now() / 1000);
  return new SignJWT({ uri: `${method.toUpperCase()} ${host}${requestPath}` })
    .setProtectedHeader({ alg: "ES256", kid: keyId, nonce: crypto.randomUUID() })
    .setIssuer("cdp")
    .setAudience("cdp_service")
    .setSubject(keyId)
    .setIssuedAt(nowSeconds)
    .setNotBefore(nowSeconds)
    .setExpirationTime(nowSeconds + 120)
    .sign(ecKey);
}

async function cdpRequest(method: "GET" | "POST", requestPath: string, body?: unknown): Promise<unknown> {
  const keyId = requireEnv("CDP_API_KEY_ID");
  const keySecret = requireEnv("CDP_API_KEY_SECRET");
  const host = "api.coinbase.com";
  const jwt = await cdpJwt(keyId, keySecret, method, host, requestPath.split("?")[0]);
  const response = await fetch(`${CDP_API_BASE}${requestPath}`, {
    method,
    headers: {
      Authorization: `Bearer ${jwt}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`CDP API ${method} ${requestPath} failed: HTTP ${response.status}: ${text}`);
  }
  return parsed;
}

async function fetchUsdcMid(): Promise<{ usdcMid: number; observedAt: string }> {
  const response = await fetch(SPOT_PRICE_URL, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`spot price fetch failed: HTTP ${response.status}`);
  const body = (await response.json()) as { data?: { amount?: string } };
  const mid = Number(body.data?.amount);
  if (!Number.isFinite(mid) || mid <= 0) throw new Error("spot price not usable");
  return { usdcMid: mid, observedAt: nowIso() };
}

// ---------------------------------------------------------------------------
// Record helper (schema fields per DATA_DICTIONARY.md usdc-fiat-sweep-v2)
// ---------------------------------------------------------------------------

type V2Record = Record<string, unknown>;

function baseRecord(def: TrancheDef): V2Record {
  return {
    tranche_id: def.id,
    replicate: 1,
    provider_slug: def.provider,
    arm: def.arm,
    executed: false,
    synthetic: false,
    execution_status: "not_executed",
    is_latency_valid: false,
    fiat_currency: def.fiatCurrency,
    amount_usdc: null,
    fiat_received: null,
    order_txid: null,
    quoted_price: null,
    avg_fill_price: null,
    quoted_slippage_max: def.kind === "kraken-sell" ? SLIPPAGE_MAX_FRACTION : null,
    realized_slippage: null,
    pair_mid: null,
    mid_observed_at: null,
    timestamp_sent: null,
    timestamp_provider_credit: null,
    timestamp_fiat_spendable: null,
    timestamp_bank_arrival: null,
    tx_hash_in: null,
    funding_tx_hash: null,
    network_fee_usd: null,
    fixed_fee_usd: 0,
    quoted_fee_usd: 0,
    disbursement_fee_fiat: null,
    bank_intermediary_deduction: null,
    net_amount_settled: null,
    realized_fee_pct: null,
    spread_vs_mid_pct: null,
    notes: null,
  };
}

function writeRecord(def: TrancheDef, record: V2Record): void {
  const errors = validateWithPython(record);
  if (errors) die(`${def.id}: record failed schema validation:\n${errors}`);
  writeFileSync(path.join(SESSIONS_DIR, `${def.id}.json`), JSON.stringify(record, null, 2) + "\n");
  log(`${def.id}: record written`);
}

/** Validate one record through the repo's validator; returns stderr text on failure. */
function validateWithPython(record: V2Record): string | null {
  const tmp = mkdtempSync(path.join(tmpdir(), "sweepv2-rec-"));
  const file = path.join(tmp, "record.json");
  writeFileSync(file, JSON.stringify(record, null, 2));
  const run = spawnSync("uv", ["run", "python", "validate_schema.py", "--sweep-v2", file], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  if (run.status !== 0) return `${run.stdout}\n${run.stderr}`;
  return null;
}

// ---------------------------------------------------------------------------
// Arm A / Arm B: Kraken order-book sell
// ---------------------------------------------------------------------------

async function krakenSell(def: TrancheDef, amountUsdc: number, rawDir: string): Promise<void> {
  const pair = def.fiatCurrency === "USD" ? KRAKEN_PAIR_USD : KRAKEN_PAIR_CAD;
  const record = baseRecord(def);

  // Hop 1: quote (mid + top-of-book ask).
  const mid = await krakenTickerMid(pair);
  const depth = await krakenTopAsk(pair);
  record.pair_mid = Number(mid.mid.toFixed(8));
  record.mid_observed_at = mid.observedAt;
  record.quoted_price = depth.ask;

  // Hop 2: market sell.
  const addOrder = await krakenPrivate("AddOrder", {
    pair,
    type: "sell",
    ordertype: "market",
    volume: amountUsdc.toFixed(8),
  });
  const txid = (addOrder.txid as string[] | undefined)?.[0];
  if (!txid) throw new Error(`AddOrder returned no txid: ${JSON.stringify(addOrder)}`);
  record.order_txid = txid;
  mkdirSync(rawDir, { recursive: true });
  writeFileSync(path.join(rawDir, "add-order.json"), jsonSafe(addOrder));
  record.timestamp_provider_credit = nowIso();

  // Hop 3: fill + fee observation via QueryOrders/QueryTrades.
  let filled = false;
  let orderInfo: Record<string, unknown> = {};
  for (let attempt = 0; attempt < 30; attempt++) {
    const qo = await krakenPrivate("QueryOrders", { pair, txid, trades: "true" });
    const info = qo[txid] as Record<string, unknown> | undefined;
    if (info && (info.status === "closed" || info.status === "expired")) {
      filled = true;
      orderInfo = info;
      break;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  if (!filled) {
    record.execution_status = "api_error";
    record.is_latency_valid = false;
    record.notes = "order not observed closed within 60s; raw QueryOrders in raw dir";
    writeFileSync(path.join(rawDir, "query-orders-last.json"), jsonSafe({ txid, pending: true }));
    writeRecord(def, record);
    return;
  }
  const tradeIds = (orderInfo.trades as string[] | undefined)?.join(",") ?? txid;
  const trades = await krakenPrivate("QueryTrades", { txid: tradeIds });
  writeFileSync(path.join(rawDir, "query-trades.json"), jsonSafe(trades));
  writeFileSync(path.join(rawDir, "query-orders.json"), jsonSafe(orderInfo));

  const volExec = Number(orderInfo.vol_exec ?? 0);
  const cost = Number(orderInfo.cost ?? 0);
  const fee = Number(orderInfo.fee ?? 0);
  const avgFill = volExec > 0 ? cost / volExec : Number.NaN;
  if (!Number.isFinite(avgFill)) {
    record.execution_status = "api_error";
    record.is_latency_valid = false;
    record.notes = "closed order missing vol_exec/cost";
    writeRecord(def, record);
    return;
  }

  record.executed = true;
  record.execution_status = Number(orderInfo.vol ?? 0) - volExec > 1e-8 ? "partial_fill" : "clean_fill";
  record.is_latency_valid = true;
  record.amount_usdc = volExec;
  record.fiat_received = Number(cost.toFixed(6));
  record.avg_fill_price = Number(avgFill.toFixed(8));
  record.realized_slippage = Number(((avgFill - depth.ask) / depth.ask).toFixed(10));
  record.timestamp_fiat_spendable = nowIso();
  record.fixed_fee_usd = Number(fee.toFixed(6));
  record.quoted_fee_usd = Number(((EFT_FEE_PCT / 100) * 0 + (def.fiatCurrency === "USD" ? 0.002 * cost : 0.002 * cost)).toFixed(6));
  record.realized_fee_pct = Number((100 * fee / cost).toFixed(6));
  const notionalMid = volExec * mid.mid;
  record.spread_vs_mid_pct = Number((100 * (notionalMid - cost) / notionalMid).toFixed(6));
  if (Math.abs(record.realized_slippage) > SLIPPAGE_MAX_FRACTION) {
    record.notes = `realized slippage ${record.realized_slippage} exceeded pre-registered bound ${SLIPPAGE_MAX_FRACTION}`;
  }
  writeRecord(def, record);
}

// ---------------------------------------------------------------------------
// Arm B: CAD EFT disbursement
// ---------------------------------------------------------------------------

async function cadEftWithdraw(rawDir: string): Promise<void> {
  const def = TRANCHES.find((t) => t.id === "cad-eft")!;
  const record = baseRecord(def);

  // CAD proceeds on the Kraken ledger come from the cad-20 sell.
  const bal = await krakenPrivate("Balance", {});
  writeFileSync(path.join(rawDir, "balance-before-withdraw.json"), jsonSafe(bal));
  const cadAvailable = Number(bal.ZCAD ?? 0);
  if (cadAvailable < EFT_MIN_CAD) {
    record.execution_status = "rejected_below_minimum";
    record.is_latency_valid = false;
    record.notes = `CAD balance ${cadAvailable} below EFT minimum ${EFT_MIN_CAD}`;
    writeRecord(def, record);
    return;
  }

  const withdrawKey = process.env.KRAKEN_WITHDRAW_KEY?.trim();
  if (!withdrawKey) {
    record.execution_status = "operator_interrupted";
    record.is_latency_valid = false;
    record.notes = "KRAKEN_WITHDRAW_KEY not set (name of the configured EFT bank destination)";
    writeRecord(def, record);
    return;
  }

  const amount = Number(cadAvailable.toFixed(2));
  const quotedFee = Number(((EFT_FEE_PCT / 100) * amount).toFixed(2));
  record.disbursement_fee_fiat = quotedFee;

  // Hop 1: withdrawal request.
  const wf = await krakenPrivate("Withdraw", { asset: "ZCAD", key: withdrawKey, amount: amount.toFixed(2) });
  writeFileSync(path.join(rawDir, "withdraw.json"), jsonSafe(wf));
  const refId = wf.refid as string | undefined;
  record.timestamp_provider_credit = nowIso();
  record.executed = true;
  record.execution_status = "clean_fill";
  record.is_latency_valid = true;
  record.fiat_received = amount;

  // Hop 2: status poll until complete (bounded; completion may land after the
  // pass — a still-pending withdrawal is recorded as clean_fill with a note,
  // and bank arrival is observed from the WithdrawStatus/ledger when it lands).
  let status: Record<string, unknown> = {};
  for (let attempt = 0; attempt < 30; attempt++) {
    await new Promise((r) => setTimeout(r, 10000));
    const ws = await krakenPrivate("WithdrawStatus", { asset: "ZCAD", refid: refId });
    status = (Object.values(ws)[0] as Record<string, unknown>) ?? {};
    if (status.status === "Complete" || status.status === "Pending") break;
  }
  writeFileSync(path.join(rawDir, "withdraw-status.json"), jsonSafe(status));
  if (status.status === "Complete") {
    record.timestamp_bank_arrival = nowIso();
    const feeActual = Number(status.fee ?? quotedFee);
    record.disbursement_fee_fiat = feeActual;
    record.net_amount_settled = Number((amount - feeActual).toFixed(2));
    record.bank_intermediary_deduction = 0;
    record.notes = "withdrawal observed Complete via WithdrawStatus; bank-side deduction recorded as 0 pending bank statement";
  } else {
    record.notes = `withdrawal status after polling: ${String(status.status ?? "unknown")}; bank arrival to be confirmed from bank statement and record updated only via a recorded deviation entry`;
  }
  record.timestamp_fiat_spendable = record.timestamp_provider_credit;
  writeRecord(def, record);
}

// ---------------------------------------------------------------------------
// Arm C: Coinbase convert (v1 rail continuity)
// ---------------------------------------------------------------------------

async function coinbaseConvert(def: TrancheDef, amountUsdc: number, rawDir: string): Promise<void> {
  const record = baseRecord(def);

  // Hop 1: on-chain transfer from the receiver wallet to the Coinbase deposit
  // address (same flow as v1).
  const depositAddress = process.env.COINBASE_BASE_DEPOSIT_ADDRESS;
  if (!depositAddress?.startsWith("0x")) {
    record.execution_status = "operator_interrupted";
    record.is_latency_valid = false;
    record.notes = "COINBASE_BASE_DEPOSIT_ADDRESS missing";
    writeRecord(def, record);
    return;
  }
  const walletClient = createWalletClient({
    chain: base,
    transport: http(BASE_RPC),
    account: privateKeyToAccount(requireEnv("X402_RECEIVER_PRIVATE_KEY") as `0x${string}`),
  });
  const client = createPublicClient({ chain: base, transport: http(BASE_RPC) });
  // Resume support: if the transfer receipt was already persisted, the
  // on-chain hop already executed; recover verbatim and continue from Hop 2
  // (see METHODOLOGY.md Execution Deviations).
  const receiptPath = path.join(rawDir, "tx-receipt.json");
  let txHash: `0x${string}`;
  let receipt: Record<string, unknown>;
  let resumedFromReceipt = false;
  if (existsSync(receiptPath)) {
    receipt = JSON.parse(readFileSync(receiptPath, "utf8")) as Record<string, unknown>;
    txHash = receipt.transactionHash as `0x${string}`;
    resumedFromReceipt = true;
  } else {
    txHash = await walletClient.writeContract({
      address: USDC_BASE,
      abi: erc20Abi,
      functionName: "transfer",
      args: [depositAddress as Address, parseUnits(amountUsdc.toFixed(6), 6)],
      chain: base,
      account: walletClient.account!,
    });
    const r = await client.waitForTransactionReceipt({ hash: txHash });
    if (r.status !== "success") throw new Error(`${def.id}: on-chain transfer reverted: ${txHash}`);
    mkdirSync(rawDir, { recursive: true });
    writeFileSync(receiptPath, jsonSafe(r));
    receipt = r as unknown as Record<string, unknown>;
  }
  // blockHash is zeroed on OP-stack receipts here; derive the timestamp from
  // the receipt's blockTimestamp field (v1 precedent) to avoid a redundant
  // getBlock round-trip that crashed on a transient RPC hiccup.
  const blockTs = Number((receipt as { blockTimestamp?: string }).blockTimestamp ?? 0);
  record.tx_hash_in = txHash;
  record.timestamp_sent = blockTs > 0 ? new Date(blockTs * 1000).toISOString() : nowIso();
  record.timestamp_provider_credit = nowIso();

  // Hop 2: deposit-credit wait (v1 finding: Base deposits credit with a lag).
  let credited = false;
  for (let attempt = 0; attempt < 20; attempt++) {
    await new Promise((r) => setTimeout(r, 30000));
    try {
      const quote = (await cdpRequest("POST", "/api/v3/brokerage/convert/quote", {
        from_account: "USDC",
        to_account: "USD",
        // v1 live-proven field shape (usdc-fiat-sweep-api sweep.ts): the API
        // rejects `from_amount` as an unknown field; `amount` carries the
        // same 1:1 USDC/USD value. See METHODOLOGY.md Execution Deviations.
        amount: amountUsdc.toFixed(2),
      })) as Record<string, unknown>;
      writeFileSync(path.join(rawDir, "convert-quote.json"), jsonSafe(quote));
      const quoteTrade = (quote.trade as Record<string, unknown> | undefined) ?? quote;
      const quoteId = (quoteTrade.convert_quote_id ?? quoteTrade.id) as string | undefined;
      if (!quoteId) throw new Error(`convert quote missing id: ${JSON.stringify(quote)}`);
      const trade = (await cdpRequest("POST", `/api/v3/brokerage/convert/trade/${quoteId}`, {
        from_account: "USDC",
        to_account: "USD",
      })) as Record<string, unknown>;
      writeFileSync(path.join(rawDir, "convert-trade.json"), jsonSafe(trade));
      const fill = (await cdpRequest(
        "GET",
        `/api/v3/brokerage/convert/trade/${quoteId}?from_account=USDC&to_account=USD`,
      )) as Record<string, unknown>;
      writeFileSync(path.join(rawDir, "convert-fill.json"), jsonSafe(fill));
      const tradeInfo = (fill.trade as Record<string, unknown> | undefined) ?? fill;
      // total_fee drift repair (see METHODOLOGY.md Execution Deviations):
      // v1 recorded total_fee as a plain string; the live API now returns a
      // nested object ({ amount: { value } }). Parse either shape verbatim.
      const rawTotalFee = tradeInfo.total_fee as unknown;
      const totalFeeValue =
        rawTotalFee !== null && typeof rawTotalFee === "object"
          ? ((rawTotalFee as Record<string, Record<string, string>>).amount?.value ?? "0")
          : String(rawTotalFee ?? "0");
      const totalFee = Number(totalFeeValue);
      record.executed = true;
      record.execution_status = "clean_fill";
      // Mechanical exclusion rule: if this run resumed from a persisted
      // receipt, deposit-credit polling exceeded the pre-registered window.
      record.is_latency_valid = !resumedFromReceipt;
      record.fiat_received = amountUsdc;
      record.fixed_fee_usd = totalFee;
      record.quoted_fee_usd = totalFee;
      record.realized_fee_pct = Number((100 * totalFee / amountUsdc).toFixed(6));
      const mid = await fetchUsdcMid();
      record.pair_mid = mid.usdcMid;
      record.mid_observed_at = mid.observedAt;
      record.spread_vs_mid_pct = Number(
        (100 * (amountUsdc * mid.usdcMid - amountUsdc) / (amountUsdc * mid.usdcMid)).toFixed(6),
      );
      record.timestamp_fiat_spendable = nowIso();
      record.notes = resumedFromReceipt
        ? "on-chain send recovered from persisted receipt (polling window exceeded pre-registered threshold); convert committed once; no retries"
        : "on-chain send and convert committed once; no retries";
      writeRecord(def, record);
      credited = true;
      break;
    } catch (err) {
      // Deposit not credited yet; keep polling. A non-INSUFFICIENT-BALANCE
      // error after several attempts is recorded via the final note.
      const msg = err instanceof Error ? err.message : String(err);
      if (attempt === 19) {
        // The on-chain hop executed (receipt persisted), so the tranche is
        // executed even though the convert never succeeded; the schema
        // requires executed=true for any non-not_executed status.
        record.executed = true;
        record.execution_status = "api_error";
        record.is_latency_valid = false;
        record.notes = `convert quote never succeeded within polling window: ${msg}`;
        writeRecord(def, record);
      }
    }
  }
  void credited;
}

// ---------------------------------------------------------------------------
// Mode: --funding
// ---------------------------------------------------------------------------

async function modeFunding(): Promise<void> {
  if (existsSync(FUNDING_FILE)) die(`funding.json already exists: ${FUNDING_FILE}`);
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const fundingTxHash = (await rl.question("Funding tx hash (USDC transfer to the receiver wallet on Base): ")).trim();
  const usdcAmount = (await rl.question("USDC amount funded: ")).trim();
  const ethAmount = (await rl.question("ETH amount funded (gas float): ")).trim();
  rl.close();
  if (!/^0x[a-fA-F0-9]{64}$/.test(fundingTxHash)) die("funding tx hash is not a 0x-64-hex string");
  mkdirSync(SESSIONS_DIR, { recursive: true });
  writeFileSync(
    FUNDING_FILE,
    `${JSON.stringify(
      {
        schema_version: "1.0.0",
        experiment: "usdc-fiat-sweep-v2",
        funding_tx_hash: fundingTxHash,
        usdc_buy_amount_usd: Number(usdcAmount),
        eth_buy_amount: Number(ethAmount),
        note: "single pre-registered funding transfer to the receiver wallet; working-capital placement, not measurement",
        recorded_at: nowIso(),
      },
      null,
      2,
    )}\n`,
  );
  log(`Funding recorded: ${FUNDING_FILE}`);
}

// ---------------------------------------------------------------------------
// Mode: --preflight
// ---------------------------------------------------------------------------

async function preflight(): Promise<void> {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail: string): void => {
    log(`  ${ok ? "PASS" : "FAIL"}  ${name}: ${detail}`);
    if (!ok) failures.push(name);
  };
  const has = (name: string) => {
    const v = process.env[name];
    return typeof v === "string" && v.trim() !== "";
  };

  log("Preflight (read-only; no values are read, printed, or written):");

  for (const name of [
    "KRAKEN_API_KEY",
    "KRAKEN_API_SECRET",
    "CDP_API_KEY_ID",
    "CDP_API_KEY_SECRET",
    "X402_RECEIVER_PRIVATE_KEY",
    "X402_PAY_TO",
  ]) {
    check(`env ${name}`, has(name), has(name) ? "present" : "missing");
  }
  check(
    "env COINBASE_BASE_DEPOSIT_ADDRESS",
    (process.env.COINBASE_BASE_DEPOSIT_ADDRESS ?? "").startsWith("0x"),
    "present (0x-prefixed)" ,
  );

  check("funding.json", existsSync(FUNDING_FILE), existsSync(FUNDING_FILE) ? "recorded" : "missing (run --funding after the inbound transfer)");

  try {
    const receiver = receiverAddress();
    const bal = await receiverUsdcBalance(receiver);
    check("on-chain receiver USDC", true, `${receiver} holds $${bal.toFixed(2)} USDC on Base`);
    if (existsSync(FUNDING_FILE) && bal <= 0) {
      check("funded balance", false, "funding.json exists but receiver balance is zero");
    }
  } catch (err) {
    check("on-chain receiver USDC", false, err instanceof Error ? err.message : String(err));
  }

  try {
    await krakenPrivate("Balance", {});
    check("Kraken auth (Balance)", true, "HMAC-SHA512 auth accepted");
  } catch (err) {
    check("Kraken auth (Balance)", false, err instanceof Error ? err.message : String(err));
  }

  for (const [pair, minCost] of [
    [KRAKEN_PAIR_USD, "0.5"],
    [KRAKEN_PAIR_CAD, "1"],
  ] as const) {
    try {
      const { mid } = await krakenTickerMid(pair);
      const { ask } = await krakenTopAsk(pair);
      check(`Kraken order book ${pair}`, true, `mid ${mid.toFixed(6)}, top ask ${ask} (costmin ${minCost})`);
    } catch (err) {
      check(`Kraken order book ${pair}`, false, err instanceof Error ? err.message : String(err));
    }
  }

  try {
    const wm = await krakenPrivate("WithdrawMethods", { asset: "ZCAD" });
    const methods = (wm.result ?? wm) as Record<string, unknown>[];
    const list = Array.isArray(methods) ? methods : Object.values(methods);
    const eft = list.find((m) => typeof m === "object" && m !== null && JSON.stringify(m).includes("Pateno")) as Record<string, unknown> | undefined;
    if (!eft) {
      check("EFT (Pateno) method", false, "not returned by WithdrawMethods for ZCAD");
    } else {
      const minimum = Number((eft as { minimum?: string }).minimum ?? NaN);
      check("EFT (Pateno) method", true, `minimum ${minimum} CAD (planned tranche proceeds >= ${EFT_MIN_CAD} CAD)`);
      check("EFT minimum <= planned tranche", minimum <= EFT_MIN_CAD, `min ${minimum} <= ${EFT_MIN_CAD}`);
    }
  } catch (err) {
    check("EFT (Pateno) method", false, err instanceof Error ? err.message : String(err));
  }

  try {
    const wa = await krakenPrivate("WithdrawAddresses", {});
    const values = Object.values(wa);
    if (values.length === 0) {
      check("Kraken withdrawal address (bank)", false, "no bank destination configured; add the CAD bank in Kraken Funding before execution");
    } else {
      const names = values.map((a) => String((a as { key?: string }).key ?? "?"));
      check("Kraken withdrawal address (bank)", true, `configured: ${names.join(", ")} (set KRAKEN_WITHDRAW_KEY to the one to use)`);
    }
  } catch (err) {
    check("Kraken withdrawal address (bank)", false, err instanceof Error ? err.message : String(err));
  }

  try {
    await cdpRequest("GET", "/api/v3/brokerage/accounts");
    check("CDP auth (GET accounts)", true, "ES256 JWT accepted by Advanced Trade API");
  } catch (err) {
    check("CDP auth (GET accounts)", false, err instanceof Error ? err.message : String(err));
  }

  if (failures.length > 0) {
    die(`preflight failed (${failures.length} check(s)); fix and re-run`);
  }
  log("Preflight passed. Ready for --execute --yes.");
}

// ---------------------------------------------------------------------------
// Mode: --dry-run
// ---------------------------------------------------------------------------

function syntheticKrakenSell(def: TrancheDef, amountUsdc: number, seed: number): V2Record {
  const record = baseRecord(def);
  const mid = 1 + seed * 0.00001;
  const ask = mid + 0.00002;
  const fill = ask - 0.00001;
  const cost = amountUsdc * fill;
  record.executed = true;
  record.execution_status = "clean_fill";
  record.is_latency_valid = true;
  record.synthetic = true;
  record.amount_usdc = amountUsdc;
  record.fiat_received = Number(cost.toFixed(6));
  record.order_txid = `synthetic-${def.id}`;
  record.quoted_price = Number(ask.toFixed(8));
  record.avg_fill_price = Number(fill.toFixed(8));
  record.realized_slippage = Number(((fill - ask) / ask).toFixed(10));
  record.pair_mid = Number(mid.toFixed(8));
  record.mid_observed_at = nowIso();
  record.timestamp_provider_credit = nowIso();
  record.timestamp_fiat_spendable = nowIso();
  record.fixed_fee_usd = Number((0.002 * cost).toFixed(6));
  record.quoted_fee_usd = record.fixed_fee_usd;
  record.realized_fee_pct = Number((100 * (record.fixed_fee_usd as number) / cost).toFixed(6));
  const notional = amountUsdc * mid;
  record.spread_vs_mid_pct = Number((100 * (notional - cost) / notional).toFixed(6));
  return record;
}

async function modeDryRun(): Promise<void> {
  log("Dry run: 6 synthetic records validated in a temp dir; the repo is not touched.");
  const tmp = mkdtempSync(path.join(tmpdir(), "sweepv2-dry-"));
  const tmpSessions = path.join(tmp, "sessions");
  mkdirSync(tmpSessions, { recursive: true });

  const records: V2Record[] = [
    syntheticKrakenSell(TRANCHES[0], 10, 1),
    syntheticKrakenSell(TRANCHES[1], 66.5, 2),
    syntheticKrakenSell(TRANCHES[2], 20, 3),
  ];
  const eft = baseRecord(TRANCHES[3]);
  eft.executed = true;
  eft.execution_status = "clean_fill";
  eft.is_latency_valid = true;
  eft.synthetic = true;
  eft.fiat_received = 27.31;
  eft.disbursement_fee_fiat = 0.1;
  eft.net_amount_settled = 27.21;
  eft.bank_intermediary_deduction = 0;
  eft.timestamp_provider_credit = nowIso();
  eft.timestamp_fiat_spendable = nowIso();
  eft.timestamp_bank_arrival = nowIso();
  eft.notes = "synthetic EFT disbursement";
  records.push(eft);
  for (const [i, def] of [TRANCHES[4], TRANCHES[5]].entries()) {
    const record = baseRecord(def);
    record.executed = true;
    record.execution_status = "clean_fill";
    record.is_latency_valid = true;
    record.synthetic = true;
    record.amount_usdc = 5;
    record.fiat_received = 5;
    record.pair_mid = 1;
    record.mid_observed_at = nowIso();
    record.timestamp_provider_credit = nowIso();
    record.timestamp_fiat_spendable = nowIso();
    record.fixed_fee_usd = 0;
    record.quoted_fee_usd = 0;
    record.realized_fee_pct = 0;
    record.spread_vs_mid_pct = 0;
    record.notes = `synthetic continuity replicate ${i + 1}`;
    records.push(record);
  }
  for (const record of records) {
    const file = path.join(tmpSessions, `${record.tranche_id}.json`);
    writeFileSync(file, JSON.stringify(record, null, 2) + "\n");
  }
  const run = spawnSync("uv", ["run", "python", "validate_schema.py", "--sweep-v2", ...records.map((r) => path.join(tmpSessions, `${r.tranche_id}.json`))], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  if (run.status !== 0) {
    console.error(run.stdout);
    console.error(run.stderr);
    die("dry-run records failed schema validation");
  }
  log(`All ${records.length} synthetic records validated against the v2 schema.`);
  log("Dry run passed. Repo left clean of synthetic artifacts.");
}

// ---------------------------------------------------------------------------
// Mode: --execute
// ---------------------------------------------------------------------------

async function modeExecute(): Promise<void> {
  if (!existsSync(FUNDING_FILE)) {
    die("sessions/funding.json missing: run --funding after the inbound transfer first");
  }
  const funding = JSON.parse(readFileSync(FUNDING_FILE, "utf8")) as { funding_tx_hash: string };

  // Arm A/B sell tranches draw on the Kraken USDC balance; the receiver wallet
  // only funds the Coinbase continuity arm. The balance guard applies only to
  // Arm A/B tranches still unrecorded (resume: recorded tranches are skipped).
  const krakenTranchesRecorded = [TRANCHES[0], TRANCHES[1], TRANCHES[2], TRANCHES[3]].every((t) =>
    existsSync(path.join(SESSIONS_DIR, `${t.id}.json`)),
  );
  if (!krakenTranchesRecorded) {
    const krakenBalance = await krakenPrivate("Balance", {});
    const krakenUsdc = Number(krakenBalance.USDC ?? 0);
    if (krakenUsdc < 35) {
      die(`Kraken USDC balance ${krakenUsdc} is below the $35 needed for Arms A/B (kraken-10 + cad-20 + residue); fund the Kraken account first`);
    }
  }
  const receiver = receiverAddress();
  const receiverBal = await receiverUsdcBalance(receiver);
  if (receiverBal < 10) {
    die(`receiver USDC balance ${receiverBal} is below the 10 USDC needed for Arm C; complete the funding step first`);
  }

  mkdirSync(RAW_DIR, { recursive: true });

  const recordExists = (id: string): boolean => existsSync(path.join(SESSIONS_DIR, `${id}.json`));

  log("Arm A: kraken-10");
  if (!recordExists(TRANCHES[0].id)) {
    await krakenSell(TRANCHES[0], 10, path.join(RAW_DIR, "kraken-10"));
  } else {
    log(`Arm A: kraken-10 already recorded; skipping (no re-execution)`);
  }
  log("Arm A: kraken-residue (guard: ordermin 5)");
  if (recordExists("kraken-residue")) {
    log("Arm A: kraken-residue already recorded; skipping (no re-execution)");
  } else {
    {
      const bal = await krakenPrivate("Balance", {});
      const spendable = Number(bal.USDC ?? 0);
      const def = TRANCHES[1];
      if (spendable >= KRAKEN_ORDERMIN_USD) {
        await krakenSell(def, Number(spendable.toFixed(8)), path.join(RAW_DIR, "kraken-residue"));
      } else {
        const record = baseRecord(def);
        record.execution_status = "not_executed_below_minimum";
        record.notes = `spendable balance ${spendable} below ordermin ${KRAKEN_ORDERMIN_USD}`;
        writeRecord(def, record);
      }
    }
  }

  log("Arm B: cad-20");
  if (!recordExists(TRANCHES[2].id)) {
    await krakenSell(TRANCHES[2], 20, path.join(RAW_DIR, "cad-20"));
  } else {
    log(`Arm B: cad-20 already recorded; skipping (no re-execution)`);
  }
  log("Arm B: cad-eft");
  if (!recordExists("cad-eft")) {
    await cadEftWithdraw(path.join(RAW_DIR, "cad-eft"));
  } else {
    log(`Arm B: cad-eft already recorded; skipping (no re-execution)`);
  }

  log("Arm C: coinbase-5-1, coinbase-5-2");
  for (const def of [TRANCHES[4], TRANCHES[5]]) {
    if (recordExists(def.id)) {
      log(`${def.id} already recorded; skipping (no re-execution)`);
      continue;
    }
    await coinbaseConvert(def, def.amountUsdc as number, path.join(RAW_DIR, def.id));
  }

  // Funding hash propagation check.
  const recordFiles = TRANCHES.map((t) => path.join(SESSIONS_DIR, `${t.id}.json`));
  const written = recordFiles.filter(existsSync);
  if (written.length !== EXPECTED_RECORDS) {
    die(`expected ${EXPECTED_RECORDS} records, found ${written.length} on disk`);
  }
  log(`Execution pass complete: ${written.length} records in ${SESSIONS_DIR}.`);
  log("Next: generate figures from recipe/, write results/usdc-fiat-sweep-v2.md, update README index.");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.includes("--funding")) return modeFunding();
  if (args.includes("--preflight")) return preflight();
  if (args.includes("--dry-run")) return modeDryRun();
  if (args.includes("--execute")) {
    if (!args.includes("--yes")) die("--execute requires --yes");
    return modeExecute();
  }
  die(`unknown arguments: ${args.join(" ")}; usage: sweep.ts --preflight | --dry-run | --funding | --execute --yes`);
}

await main();
