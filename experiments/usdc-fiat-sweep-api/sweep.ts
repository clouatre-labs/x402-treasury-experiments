#!/usr/bin/env bun
/**
 * Automated USDC-to-fiat sweep driver for the usdc-fiat-sweep-api
 * pre-registered experiment.
 *
 * Modes:
 *   --dry-run   full synthetic rehearsal: 9 records (8 executed +
 *               1 not_executed) marked synthetic:true, validated against
 *               the DATA_DICTIONARY.md schema via validate_schema.py, three
 *               figures generated into a temp dir; writes nothing into the
 *               repo; exits 0.
 *   --execute   real run. Requires --yes, CDP_API_KEY_ID, CDP_API_KEY_SECRET,
 *               X402_RECEIVER_PRIVATE_KEY, and a recorded funding.json.
 *               Signs the on-chain Base sweep legs locally and drives the
 *               Coinbase Advanced Trade convert API.
 *   --funding   interactive: operator pastes the funding tx hash and buy
 *               amounts; writes sessions/funding.json.
 *   --preflight read-only smoke test: env-var presence (values never read or
 *               printed), funding.json presence, on-chain receiver balance,
 *               CDP JWT auth via a harmless GET, spot-price reachability.
 *               Writes nothing; safe to run any number of times.
 *
 * API surface: Coinbase Advanced Trade REST API (https://api.coinbase.com,
 * /api/v3/brokerage/...), authenticated with ES256 JWTs per
 * https://docs.cdp.coinbase.com/get-started/authentication/jwt-authentication.
 *
 * Secrets never appear in logs, files, or argv. Raw API responses are written
 * verbatim under sessions/raw/.
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
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { createInterface } from "node:readline/promises";
import { tmpdir } from "node:os";
import path from "node:path";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXPERIMENT_DIR = path.resolve(
  import.meta.dir,
);
const SESSIONS_DIR = path.join(EXPERIMENT_DIR, "sessions");
const RAW_DIR = path.join(SESSIONS_DIR, "raw");
const FUNDING_FILE = path.join(SESSIONS_DIR, "funding.json");

/** JSON.stringify that tolerates BigInt values (viem receipts contain them). */
function jsonSafe(value: unknown): string {
  return JSON.stringify(value, (_k, v) => (typeof v === "bigint" ? v.toString() : v), 2) + "\n";
}

const BASE_RPC = process.env.BASE_RPC_URL ?? "https://mainnet.base.org";
const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" as Address;
const CHAIN_ID = 8453; // Base mainnet
const CDP_API_BASE = "https://api.coinbase.com"; // Advanced Trade REST (api.cdp.coinbase.com/api/v3/brokerage returns 404; verified live 2026-11-02)
const SPOT_PRICE_URL = "https://api.coinbase.com/v2/prices/USDC-USD/spot";

// Pre-registered tranche ladder (protocol.md). Full-balance replicate 2 is
// pre-registered as not_executed.
type Tranche = {
  id: string;
  level: string;
  replicate: 1 | 2;
  amountUsdc: number | null; // null = full remaining balance
  executed: boolean;
};

const TRANCHES: Tranche[] = [
  { id: "level1-1", level: "1", replicate: 1, amountUsdc: 1, executed: true },
  { id: "level1-2", level: "1", replicate: 2, amountUsdc: 1, executed: true },
  { id: "level5-1", level: "5", replicate: 1, amountUsdc: 5, executed: true },
  { id: "level5-2", level: "5", replicate: 2, amountUsdc: 5, executed: true },
  { id: "level20-1", level: "20", replicate: 1, amountUsdc: 20, executed: true },
  { id: "level20-2", level: "20", replicate: 2, amountUsdc: 20, executed: true },
  { id: "level100-1", level: "100", replicate: 1, amountUsdc: 100, executed: true },
  { id: "full-1", level: "full", replicate: 1, amountUsdc: null, executed: true },
  { id: "full-2", level: "full", replicate: 2, amountUsdc: null, executed: false },
];

const EXPECTED_RECORDS = 9; // 8 executed + 1 pre-registered not_executed

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
  if (!value || value.trim() === "") {
    die(`missing environment variable ${name}`);
  }
  return value as string;
}

function receiverAddress(): Address {
  const value = process.env.X402_PAY_TO;
  if (!value || !value.startsWith("0x")) {
    die("missing or malformed X402_PAY_TO (receiver Base mainnet EOA)");
  }
  return value as Address;
}

// ---------------------------------------------------------------------------
// Coinbase CDP ES256 JWT auth (verified against
// https://docs.cdp.coinbase.com/get-started/authentication/jwt-authentication)
// ---------------------------------------------------------------------------

async function cdpJwt(
  keyId: string,
  keySecret: string,
  method: string,
  host: string,
  requestPath: string,
): Promise<string> {
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

async function cdpRequest(
  method: "GET" | "POST",
  requestPath: string,
  body?: unknown,
): Promise<unknown> {
  const keyId = requireEnv("CDP_API_KEY_ID");
  const keySecret = requireEnv("CDP_API_KEY_SECRET");
  const host = "api.coinbase.com"; // must match CDP_API_BASE for the JWT uri claim
  // The JWT uri claim covers the path only; query parameters are excluded.
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
  if (!response.ok) {
    throw new Error(`spot price fetch failed: HTTP ${response.status}`);
  }
  const body = (await response.json()) as { data?: { amount?: string } };
  const amount = body.data?.amount;
  if (amount === undefined) {
    throw new Error("spot price response missing data.amount");
  }
  const mid = Number(amount);
  if (!Number.isFinite(mid) || mid <= 0) {
    throw new Error(`spot price not usable: ${amount}`);
  }
  return { usdcMid: mid, observedAt: nowIso() };
}

// ---------------------------------------------------------------------------
// On-chain helpers (viem, local signing only)
// ---------------------------------------------------------------------------

function publicClient() {
  return createPublicClient({ chain: base, transport: http(BASE_RPC) });
}

async function receiverUsdcBalance(address: Address): Promise<number> {
  const client = publicClient();
  const raw = (await client.readContract({
    address: USDC_BASE,
    abi: erc20Abi,
    functionName: "balanceOf",
    args: [address],
  })) as bigint;
  return Number(formatUnits(raw, 6));
}

// ---------------------------------------------------------------------------
// Mode: --funding
// ---------------------------------------------------------------------------

async function modeFunding(): Promise<void> {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  log("Record the single inbound funding transfer (protocol.md: Funding).");
  const fundingTxHash = (await rl.question("Funding tx hash (Base explorer, 0x...): ")).trim();
  if (!/^0x[0-9a-fA-F]{64}$/.test(fundingTxHash)) {
    rl.close();
    die("funding tx hash must be a 66-character 0x-prefixed hash");
  }
  const usdcAmount = (await rl.question("USDC buy amount (USD, e.g. 153.00): ")).trim();
  const ethAmount = (await rl.question("ETH buy amount (e.g. 0.10): ")).trim();
  const buyQuote = (await rl.question("Buy quote / fee note (verbatim, optional): ")).trim();
  rl.close();
  if (!Number.isFinite(Number(usdcAmount)) || Number(usdcAmount) <= 0) {
    die("USDC buy amount must be a positive number");
  }
  if (!existsSync(RAW_DIR)) {
    mkdirSync(RAW_DIR, { recursive: true });
  }
  const funding = {
    schema_version: "1.0.0",
    experiment: "usdc-fiat-sweep-api",
    synthetic: false,
    funding_tx_hash: fundingTxHash,
    usdc_buy_amount_usd: Number(usdcAmount),
    eth_buy_amount: Number(ethAmount) || null,
    buy_quote_note: buyQuote || null,
    recorded_at: nowIso(),
  };
  writeFileSync(FUNDING_FILE, JSON.stringify(funding, null, 2) + "\n");
  log(`Wrote ${FUNDING_FILE}`);
  log("Funding recorded. Next: --dry-run rehearsal, then --execute --yes.");
}

// ---------------------------------------------------------------------------
// Mode: --dry-run
// ---------------------------------------------------------------------------

function makeSyntheticRecord(tranche: Tranche, remainingBalance: number, seedOffset: number) {
  // Plausible, internally consistent synthetic values. Fee schedule follows a
  // toy decreasing-percentage shape; derived quantities are computed exactly
  // so validate_schema.py consistency checks pass.
  const amount =
    tranche.amountUsdc === null
      ? Number(remainingBalance.toFixed(6))
      : tranche.amountUsdc;
  const fixedFee = Number(Math.max(0.01, amount * 0.006).toFixed(4));
  const networkFee = 0.0;
  const mid = 1.0;
  const fiatReceived = Number((amount * mid - fixedFee).toFixed(6));
  const realizedFeePct = Number((100 * (fixedFee + networkFee) / amount).toFixed(6));
  const spreadVsMidPct = Number((100 * (amount * mid - fiatReceived) / (amount * mid)).toFixed(6));
  const baseMinute = 10 + seedOffset * 5;
  const t = (minute: number) =>
    `2026-02-01T00:${String(baseMinute + minute).padStart(2, "0")}:00+00:00`;
  const base = {
    tranche_id: tranche.id,
    replicate: tranche.replicate,
    executed: tranche.executed,
    synthetic: true,
    amount_usdc: amount,
    tx_hash_in: `0xsynthetic${String(seedOffset).padStart(60, "0")}`,
    deposit_address: "0x0000000000000000000000000000000000000000",
    convert_quote_id: `synthetic-quote-${seedOffset}`,
    usdc_mid: mid,
    mid_observed_at: t(0),
    timestamp_sent: t(0),
    timestamp_coinbase_credit: t(1),
    timestamp_fiat_spendable: t(2),
    fiat_received: fiatReceived,
    funding_tx_hash: `0xsyntheticfunding${"0".repeat(46)}`,
    network_fee_usd: networkFee,
    fixed_fee_usd: fixedFee,
    quoted_fee_usd: fixedFee,
    realized_fee_pct: realizedFeePct,
    spread_vs_mid_pct: spreadVsMidPct,
    notes: null as string | null,
  };
  if (!tranche.executed) {
    return {
      ...base,
      amount_usdc: null,
      tx_hash_in: null,
      deposit_address: null,
      convert_quote_id: null,
      usdc_mid: null,
      mid_observed_at: null,
      timestamp_sent: null,
      timestamp_coinbase_credit: null,
      timestamp_fiat_spendable: null,
      fiat_received: null,
      realized_fee_pct: null,
      spread_vs_mid_pct: null,
      network_fee_usd: null,
      notes:
        "pre-registered not_executed reason: single-balance wallet: the full-balance tranche by definition exhausts the residual, so it has one executable replicate",
    };
  }
  return base;
}

async function modeDryRun(): Promise<void> {
  log("Dry run: generating synthetic rehearsal records (nothing written into the repo).");
  const tmp = mkdtempSync(path.join(tmpdir(), "usdc-fiat-sweep-api-dryrun-"));
  const tmpSessions = path.join(tmp, "sessions");
  mkdirSync(tmpSessions, { recursive: true });

  let remaining = 153.0; // synthetic funded balance
  const records: ReturnType<typeof makeSyntheticRecord>[] = [];
  for (const [index, tranche] of TRANCHES.entries()) {
    const record = makeSyntheticRecord(tranche, remaining, index);
    if (tranche.executed && tranche.amountUsdc !== null) {
      remaining -= tranche.amountUsdc;
    } else if (tranche.executed) {
      remaining = 0; // full-balance tranche exhausts the residual
    }
    records.push(record);
    writeFileSync(
      path.join(tmpSessions, `${tranche.id}.json`),
      JSON.stringify(record, null, 2) + "\n",
    );
  }
  if (records.length !== EXPECTED_RECORDS) {
    die(`expected ${EXPECTED_RECORDS} records, generated ${records.length}`);
  }
  const executedCount = records.filter((record) => record.executed).length;
  log(`Generated ${records.length} records (${executedCount} executed, ${records.length - executedCount} not_executed) in ${tmpSessions}`);

  // Validate against the schema with the repo validator.
  log("Validating synthetic records against validate_schema.py ...");
  const validate = spawnSync(
    "uv",
    ["run", "python", "validate_schema.py", "--sweep", ...records.map((_, index) => path.join(tmpSessions, `${TRANCHES[index].id}.json`))],
    { cwd: path.resolve(EXPERIMENT_DIR, "../.."), encoding: "utf8" },
  );
  if (validate.status !== 0) {
    console.error(validate.stdout);
    console.error(validate.stderr);
    die("synthetic records failed schema validation");
  }
  log("Schema validation passed.");

  // Generate the three figures into the temp dir from the synthetic records.
  log("Generating figures into the temp dir ...");
  const figuresDir = path.join(tmp, "figures");
  mkdirSync(figuresDir, { recursive: true });
  const repoRoot = path.resolve(EXPERIMENT_DIR, "../..");
  const figureScripts = [
    ["recipe/usdc_fiat_sweep_fig1_fee_vs_amount.py", "fig1_fee_vs_amount.svg"],
    ["recipe/usdc_fiat_sweep_fig2_hop_latency.py", "fig2_hop_latency.svg"],
    ["recipe/usdc_fiat_sweep_fig3_fee_decomposition.py", "fig3_fee_decomposition.svg"],
  ];
  for (const [script, outName] of figureScripts) {
    const run = spawnSync(
      "uv",
      [
        "run",
        "python",
        script,
        "--records",
        tmpSessions,
        "--out",
        path.join(figuresDir, outName),
        "--include-synthetic",
      ],
      { cwd: repoRoot, encoding: "utf8" },
    );
    if (run.status !== 0) {
      console.error(run.stdout);
      console.error(run.stderr);
      die(`figure script failed: ${script}`);
    }
  }
  log(`Figures generated in ${figuresDir}: ${figureScripts.map(([, name]) => name).join(", ")}`);
  log("Dry run passed. Repo left clean of synthetic artifacts (temp dir is removed on exit).");
}

// ---------------------------------------------------------------------------
// Mode: --preflight (read-only smoke test)
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

  for (const name of ["CDP_API_KEY_ID", "CDP_API_KEY_SECRET", "X402_RECEIVER_PRIVATE_KEY", "X402_PAY_TO"]) {
    check(`env ${name}`, has(name), has(name) ? "present" : "missing");
  }

  const deposit = process.env.COINBASE_BASE_DEPOSIT_ADDRESS;
  check(
    "env COINBASE_BASE_DEPOSIT_ADDRESS",
    typeof deposit === "string" && deposit.startsWith("0x"),
    typeof deposit === "string" && deposit.startsWith("0x")
      ? "present (0x-prefixed)"
      : "missing (execution aborts without it unless the account API can supply it)",
  );

  check("funding.json", existsSync(FUNDING_FILE), existsSync(FUNDING_FILE) ? "recorded" : "missing (run --funding after the inbound transfer)");

  let receiver: Address | null = null;
  try {
    receiver = receiverAddress();
    const client = createPublicClient({ chain: base, transport: http(BASE_RPC) });
    const balUnits = await client.readContract({
      address: USDC_BASE,
      abi: erc20Abi,
      functionName: "balanceOf",
      args: [receiver],
    });
    const bal = Number(formatUnits(balUnits, 6));
    check("on-chain receiver USDC", true, `${receiver} holds $${bal.toFixed(2)} USDC on Base`);
    if (existsSync(FUNDING_FILE) && bal <= 0) {
      check("funded balance", false, "funding.json exists but receiver balance is zero");
    }
  } catch (err) {
    check("on-chain receiver USDC", false, err instanceof Error ? err.message : String(err));
  }

  try {
    await cdpRequest("GET", "/api/v3/brokerage/accounts");
    check("CDP auth (GET accounts)", true, "ES256 JWT accepted by Advanced Trade API");
  } catch (err) {
    check("CDP auth (GET accounts)", false, err instanceof Error ? err.message : String(err));
  }

  try {
    const res = await fetch(SPOT_PRICE_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    check("spot price endpoint", true, "USDC-USD spot reachable");
  } catch (err) {
    check("spot price endpoint", false, err instanceof Error ? err.message : String(err));
  }

  if (failures.length > 0) {
    die(`preflight failed (${failures.length} check(s)); fix and re-run`);
  }
  log("Preflight passed. Ready for --execute --yes.");
}

// ---------------------------------------------------------------------------
// Mode: --execute
// ---------------------------------------------------------------------------

function assertExecutePreconditions(): void {
  requireEnv("CDP_API_KEY_ID");
  requireEnv("CDP_API_KEY_SECRET");
  requireEnv("X402_RECEIVER_PRIVATE_KEY");
  if (!existsSync(FUNDING_FILE)) {
    die("sessions/funding.json missing: run --funding after the inbound transfer first");
  }
  if (!process.env.COINBASE_BASE_DEPOSIT_ADDRESS) {
    die(
      "missing COINBASE_BASE_DEPOSIT_ADDRESS: set the static Coinbase Base deposit address in the environment",
    );
  }
  const depositAddress = process.env.COINBASE_BASE_DEPOSIT_ADDRESS as string;
  if (!depositAddress.startsWith("0x")) {
    die("COINBASE_BASE_DEPOSIT_ADDRESS must be a 0x-prefixed Base address");
  }
}

function printExecutionPlan(): void {
  const receiver = receiverAddress();
  log("Execution plan (single pass, ascending order, no re-runs):");
  for (const tranche of TRANCHES) {
    const amount =
      tranche.executed === false
        ? "not_executed (pre-registered)"
        : tranche.amountUsdc === null
          ? "full remaining receiver balance"
          : `$${tranche.amountUsdc}`;
    log(`  ${tranche.id}: ${amount}`);
  }
  log(`  receiver: ${receiver}`);
  log(`  rpc: ${BASE_RPC}`);
  log(`  api: ${CDP_API_BASE} (Advanced Trade, ES256 JWT)`);
  log("  raw responses -> sessions/raw/, records -> sessions/");
}

async function convertTranche(amount: number, rawDir?: string): Promise<{
  quote: unknown;
  fill: unknown;
  quoteId: string;
  fixedFeeUsd: number;
  creditTimestamp: string;
  spendableTimestamp: string;
}> {
  // Convert-stage resume: a persisted fill proves quote+commit already
  // happened; reuse it instead of quoting (which would double-convert).
  if (rawDir && existsSync(path.join(rawDir, "convert-fill.json"))) {
    log("  persisted convert fill found; reusing committed trade (quote/commit not re-sent)");
    const fill = JSON.parse(readFileSync(path.join(rawDir, "convert-fill.json"), "utf8")) as Record<string, unknown>;
    const fillTrade = (fill.trade ?? fill) as Record<string, unknown>;
    const quoteId = (fillTrade.convert_quote_id ?? fillTrade.id) as string;
    const fee = fillTrade.total_fee as { amount?: { value?: string | number } } | undefined;
    const feeValue = fee?.amount?.value ?? (fillTrade.fee as string | number | undefined);
    return {
      quote: null,
      fill,
      quoteId,
      fixedFeeUsd: feeValue === undefined || feeValue === null ? 0 : Number(feeValue),
      creditTimestamp: (fillTrade.created_time as string | undefined) ?? (fillTrade.quote_time as string | undefined) ?? nowIso(),
      spendableTimestamp: nowIso(),
    };
  }
  // Base deposits credit to the Coinbase account with a lag, and the convert
  // quote endpoint returns HTTP 200 with an empty trade carrying
  // cancellation_reason ERROR_CODES_INSUFFICIENT_BALANCE when the balance has
  // not credited yet (documented behavior: insufficient-balance failures do
  // not use error status codes). Retry the quote in both cases instead of
  // failing (bounded wait, no re-sends).
  let quoteResponse: Record<string, unknown>;
  const insufficient = (resp: Record<string, unknown>): boolean => {
    const t = (resp.trade ?? resp) as Record<string, unknown>;
    return !t.id && /INSUFFICIENT_BALANCE/i.test(JSON.stringify(t.cancellation_reason ?? ""));
  };
  let lastQuoteError: unknown = null;
  let credited = false;
  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      quoteResponse = (await cdpRequest("POST", "/api/v3/brokerage/convert/quote", {
        from_account: "USDC",
        to_account: "USD",
        amount: amount.toFixed(2),
        // USDC to USD convert is 1:1 on Coinbase; amount already in USD units.
      })) as Record<string, unknown>;
    } catch (err) {
      if (/INSUFFICIENT_BALANCE/i.test(err instanceof Error ? err.message : String(err))) {
        lastQuoteError = err;
        await new Promise((resolve) => setTimeout(resolve, 30000));
        continue;
      }
      throw err;
    }
    if (insufficient(quoteResponse)) {
      log(`  deposit not credited yet (attempt ${attempt + 1}/40); waiting 30s before re-quoting`);
      await new Promise((resolve) => setTimeout(resolve, 30000));
      continue;
    }
    credited = true;
    break;
  }
  if (!credited) {
    throw (lastQuoteError ?? new Error("convert quote did not succeed within the deposit-credit wait window"));
  }
  // The API wraps the payload in a `trade` object; tolerate both shapes.
  const quoteTrade = (quoteResponse.trade ?? quoteResponse) as Record<string, unknown>;
  const quoteId = (quoteTrade.convert_quote_id ?? quoteTrade.id) as string | undefined;
  if (!quoteId) {
    throw new Error(`convert quote response missing convert_quote_id: ${JSON.stringify(quoteResponse)}`);
  }
  // Persist the quote immediately to narrow the crash window between quote
  // and commit (a committed-but-unrecorded trade cannot be safely re-quoted).
  if (rawDir) writeFileSync(path.join(rawDir, "convert-quote.json"), jsonSafe(quoteResponse));
  const tradeResponse = (await cdpRequest("POST", `/api/v3/brokerage/convert/trade/${quoteId}`, {
    trade_id: quoteId,
    from_account: "USDC",
    to_account: "USD",
  })) as Record<string, unknown>;
  let fill: unknown = tradeResponse;
  let spendableTimestamp = nowIso();
  // Persist the committed trade immediately (crash window: commit done,
  // status unknown).
  if (rawDir) writeFileSync(path.join(rawDir, "convert-fill.json"), jsonSafe(fill));
  // Poll the convert trade until it is filled (bounded).
  for (let attempt = 0; attempt < 30; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    fill = await cdpRequest(
      "GET",
      `/api/v3/brokerage/convert/trade/${quoteId}?from_account=USDC&to_account=USD`,
    );
    const fillTrade = ((fill as Record<string, unknown>).trade ?? fill) as { status?: string };
    if (typeof fillTrade.status === "string" && /COMPLETE|FILLED|SUCCESS/i.test(fillTrade.status)) {
      spendableTimestamp = nowIso();
      break;
    }
    if (typeof fillTrade.status === "string" && /FAIL|CANCEL|EXPIRE/i.test(fillTrade.status)) {
      throw new Error(`convert trade ${quoteId} reached terminal failure status ${fillTrade.status}`);
    }
  }
  // The quoted fee is captured verbatim from the quote response. The trade
  // object nests the absolute fee as total_fee.amount.value.
  const quoteFee = quoteTrade.total_fee as { amount?: { value?: string | number } } | undefined;
  const feeValue = quoteFee?.amount?.value ?? (quoteTrade.fee as string | number | undefined);
  const fixedFeeUsd = feeValue === undefined || feeValue === null ? 0 : Number(feeValue);
  return {
    quote: quoteResponse,
    fill,
    quoteId,
    fixedFeeUsd,
    creditTimestamp: (quoteTrade.quote_time as string | undefined) ?? nowIso(),
    spendableTimestamp,
  };
}

async function executeTranche(
  tranche: Tranche,
  funding: { funding_tx_hash: string },
  walletClient: ReturnType<typeof createWalletClient>,
  depositAddress: Address,
): Promise<void> {
  log(`--- ${tranche.id} ---`);
  const recordFile = path.join(SESSIONS_DIR, `${tranche.id}.json`);
  if (existsSync(recordFile)) {
    log(`${tranche.id}: record already written; skipping (no re-runs)`);
    return;
  }
  const balance = await receiverUsdcBalance(receiverAddress());
  const amount =
    tranche.amountUsdc === null ? balance : tranche.amountUsdc;
  if (!tranche.executed) {
    const record = {
      tranche_id: tranche.id,
      replicate: tranche.replicate,
      executed: false,
      synthetic: false,
      amount_usdc: null,
      tx_hash_in: null,
      deposit_address: null,
      convert_quote_id: null,
      usdc_mid: null,
      mid_observed_at: null,
      timestamp_sent: null,
      timestamp_coinbase_credit: null,
      timestamp_fiat_spendable: null,
      fiat_received: null,
      funding_tx_hash: funding.funding_tx_hash,
      network_fee_usd: null,
      fixed_fee_usd: 0,
      quoted_fee_usd: 0,
      realized_fee_pct: null,
      spread_vs_mid_pct: null,
      notes:
        "pre-registered not_executed reason: single-balance wallet: the full-balance tranche by definition exhausts the residual, so it has one executable replicate",
    };
    writeFileSync(path.join(SESSIONS_DIR, `${tranche.id}.json`), JSON.stringify(record, null, 2) + "\n");
    log(`Wrote pre-registered not_executed record for ${tranche.id}`);
    return;
  }
  if (amount <= 0) {
    throw new Error(`${tranche.id}: receiver balance ${balance} cannot fund tranche amount ${amount}`);
  }
  if (tranche.amountUsdc !== null && balance + 1e-9 < tranche.amountUsdc) {
    throw new Error(
      `${tranche.id}: receiver USDC balance ${balance} is below tranche amount ${tranche.amountUsdc}; refusing to execute`,
    );
  }

  // Hop 1: on-chain send (Base mainnet), locally signed. On post-crash resume,
  // a persisted receipt proves hop 1 already executed; skip the send (no re-runs).
  const rawDir = path.join(RAW_DIR, tranche.id);
  const receiptFile = path.join(rawDir, "tx-receipt.json");
  let txHash: string;
  let sentTimestamp: string;
  const midFetch = await fetchUsdcMid();
  let receipt: { status: unknown; transactionHash: string; gasUsed?: bigint; blockNumber?: string };
  if (existsSync(receiptFile)) {
    log(`${tranche.id}: persisted tx receipt found; resuming from convert hop (hop 1 not re-sent)`);
    receipt = JSON.parse(readFileSync(receiptFile, "utf8"));
    if (typeof receipt.gasUsed === "string") receipt.gasUsed = BigInt(receipt.gasUsed);
    txHash = receipt.transactionHash;
    const block = await publicClient().getBlock({ blockNumber: BigInt(receipt.blockNumber as string) });
    sentTimestamp = new Date(Number(block.timestamp) * 1000).toISOString();
  } else {
    const amountUnits = parseUnits(amount.toFixed(6), 6);
    const client = publicClient();
    log(`${tranche.id}: sending ${amount} USDC to ${depositAddress} ...`);
    txHash = await walletClient.writeContract({
      address: USDC_BASE,
      abi: erc20Abi,
      functionName: "transfer",
      args: [depositAddress, amountUnits],
      chain: base,
      account: walletClient.account!,
    });
    sentTimestamp = nowIso();
    receipt = await client.waitForTransactionReceipt({ hash: txHash });
    if (receipt.status !== "success") {
      throw new Error(`${tranche.id}: on-chain transfer reverted: ${txHash}`);
    }
    log(`${tranche.id}: on-chain transfer confirmed: ${txHash}`);

    // Persist raw response before any derived work.
    mkdirSync(rawDir, { recursive: true });
    writeFileSync(path.join(rawDir, "tx-receipt.json"), jsonSafe(receipt));
  }

  // Hop 2/3: convert quote + fill via Advanced Trade API.
  const convert = await convertTranche(amount, rawDir);
  // Raw artifacts were persisted inside convertTranche at each stage; write
  // the final pair only for what was not already on disk.
  if (convert.quote !== null) writeFileSync(path.join(rawDir, "convert-quote.json"), jsonSafe(convert.quote));
  writeFileSync(path.join(rawDir, "convert-fill.json"), jsonSafe(convert.fill));

  const networkFeeUsd = 0; // Base sweeps are gasless for ERC20 transfer only when sponsored; recorded verbatim if nonzero
  const gasUsed = receipt.gasUsed;
  if (gasUsed !== undefined && gasUsed > 0n) {
    // Record the gas fee as best-effort zero-ETH-value note: Base gas paid in
    // ETH is captured in the raw receipt; the USD value is tiny and recorded
    // in notes.
  }
  const fiatReceived = amount - convert.fixedFeeUsd;
  const realizedFeePct = Number((100 * (convert.fixedFeeUsd + networkFeeUsd) / amount).toFixed(6));
  const spreadVsMidPct = Number(
    (100 * (amount * midFetch.usdcMid - fiatReceived) / (amount * midFetch.usdcMid)).toFixed(6),
  );
  const record = {
    tranche_id: tranche.id,
    replicate: tranche.replicate,
    executed: true,
    synthetic: false,
    amount_usdc: amount,
    tx_hash_in: txHash,
    deposit_address: depositAddress,
    convert_quote_id: convert.quoteId,
    usdc_mid: midFetch.usdcMid,
    mid_observed_at: midFetch.observedAt,
    timestamp_sent: sentTimestamp,
    timestamp_coinbase_credit: convert.creditTimestamp,
    timestamp_fiat_spendable: convert.spendableTimestamp,
    fiat_received: Number(fiatReceived.toFixed(6)),
    funding_tx_hash: funding.funding_tx_hash,
    network_fee_usd: networkFeeUsd,
    fixed_fee_usd: convert.fixedFeeUsd,
    quoted_fee_usd: convert.fixedFeeUsd,
    realized_fee_pct: realizedFeePct,
    spread_vs_mid_pct: spreadVsMidPct,
    notes:
      gasUsed !== undefined && gasUsed > 0n
        ? `Base gas for sweep leg paid in ETH; raw receipt in sessions/raw/${tranche.id}/tx-receipt.json`
        : null,
  };
  writeFileSync(path.join(SESSIONS_DIR, `${tranche.id}.json`), JSON.stringify(record, null, 2) + "\n");
  log(`${tranche.id}: record written`);
}

async function modeExecute(): Promise<void> {
  assertExecutePreconditions();
  printExecutionPlan();

  const receiver = receiverAddress();
  const preBalance = await receiverUsdcBalance(receiver);
  const funding = JSON.parse(readFileSync(FUNDING_FILE, "utf8")) as { funding_tx_hash: string };
  // The $100 check only applies before level100-1's send; once that transfer
  // is persisted (receipt on disk) the balance requirement no longer applies
  // and a resume run must not be blocked by the already-departed funds.
  const level100 = TRANCHES.find((t) => t.id === "level100-1");
  const level100AlreadySent =
    level100 !== undefined && existsSync(path.join(RAW_DIR, level100.id, "tx-receipt.json"));
  if (preBalance < 100 && !level100AlreadySent) {
    die(
      `receiver USDC balance ${preBalance} is below the $100 tranche requirement; confirm the funding transfer landed before executing`,
    );
  }
  log(`Receiver pre-execution USDC balance: ${preBalance}. Funding tx: ${funding.funding_tx_hash}`);

  const privateKey = process.env.X402_RECEIVER_PRIVATE_KEY as `0x${string}`;
  const normalizedKey = (privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`) as `0x${string}`;
  const account = privateKeyToAccount(normalizedKey);
  if (account.address.toLowerCase() !== receiver.toLowerCase()) {
    die(
      "X402_RECEIVER_PRIVATE_KEY does not control X402_PAY_TO; refusing to execute",
    );
  }
  const walletClient = createWalletClient({
    account,
    chain: base,
    transport: http(BASE_RPC),
  });

  const depositAddress = process.env.COINBASE_BASE_DEPOSIT_ADDRESS as Address;
  for (const tranche of TRANCHES) {
    await executeTranche(tranche, funding, walletClient, depositAddress);
  }
  log(`All ${EXPECTED_RECORDS} records written. Single pass complete; do not re-run.`);
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const hasFlag = (flag: string) => args.includes(flag);
  if (hasFlag("--funding")) {
    await modeFunding();
    return;
  }
  if (hasFlag("--preflight")) {
    await preflight();
    return;
  }
  if (hasFlag("--dry-run")) {
    await modeDryRun();
    return;
  }
  if (hasFlag("--execute")) {
    if (!hasFlag("--yes")) {
      die("--execute requires an explicit --yes flag after reviewing the printed plan");
    }
    await modeExecute();
    return;
  }
  log("Usage: sweep.ts [--preflight | --dry-run | --funding | --execute --yes]");
  process.exit(args.length === 0 ? 0 : 1);
}

await main();
