# Data Dictionary

This document defines the schema and field meanings for experiment data files in this repository. `validate_schema.py` enforces the required fields below; run `uv run python validate_schema.py` before every PR that touches `experiments/`.

## Layout

Each experiment directory `experiments/<slug>/` contains:

- `analysis.json`: run metadata, message counts, and evaluation scores (schema below)
- `scores.json`: per-criterion rubric scores with justifications
- `protocol.md`, `runner-prompt.md`, `scorer-prompt.md`: pre-registration artifacts
- `sessions/`: raw session logs or database exports

## analysis.json

### Top-level schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `experiment` | string | no | Experiment slug, matches the directory name |
| `schema_version` | string | no | Version of this schema the record conforms to |
| `title` | string | no | Human-readable experiment title |
| `issue` | string \| null | yes | Target issue or task reference |
| `date` | string | no | Experiment date (YYYY-MM-DD) |
| `model` | string | no | Model identifier under test |
| `n_per_group` | integer | no | Number of runs per group |
| `control_condition` | string | no | Description of the control condition |
| `treatment_condition` | string | no | Description of the treatment condition |
| `rubric_version` | string | no | Rubric identifier used for scoring |
| `orchestrator_session` | string \| null | yes | Orchestrator session reference, if any |
| `repo_head` | string | no | Repository commit at run time |
| `experiment_start` | string | no | ISO 8601 timestamp with UTC offset of first run |
| `experiment_end` | string | no | ISO 8601 timestamp with UTC offset of last run |
| `analyzed_at` | string | no | ISO 8601 timestamp with UTC offset of analysis |
| `runs` | object | no | Map of run ID to run record |
| `scores` | object | no | Scoring summary keyed by run ID |
| `statistical_test` | string | no | Pre-registered statistical test name |
| `conclusion` | string | no | Result summary |
| `pre_acknowledged_limitations` | array | no | Limitations stated before analysis |

### Run record schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `group` | string | no | `control` or `treatment` |
| `session_id` | string | no | Session identifier from the run harness |
| `messages` | integer | no | Message count in the session |
| `input_tokens` | integer | no | Accumulated input tokens |
| `output_tokens` | integer | no | Accumulated output tokens |
| `total_tokens` | integer | no | Sum of input and output tokens |
| `wall_clock_seconds` | number | no | Elapsed wall-clock seconds |
| `bytes` | integer \| null | yes | Session byte size, if recorded |
| `note` | string \| null | yes | Optional note (e.g. failure reason) |

## scores.json

Free-form per-criterion scoring keyed by run ID; each entry SHOULD include the score value, per-criterion results, and scorer justifications.

## usdc-fiat-sweep run-record schema

Per-tranche JSON records stored under `experiments/usdc-fiat-sweep/sessions/`. Raw session artifacts are transcribed into these records per `experiments/usdc-fiat-sweep/record-extraction.md`.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `tranche_id` | string | no | Tranche identifier (level plus replicate) |
| `replicate` | integer | no | Replicate number within the amount level (1 or 2) |
| `amount_usdc` | number \| null | yes | USDC amount converted; non-null for every executed tranche, null only for the pre-registered `not_executed` replicate, which must carry a populated `notes` entry |
| `tx_hash_in` | string | no | On-chain transaction hash of the send to Coinbase |
| `timestamp_sent` | string \| null | yes | Timestamp the on-chain send was made; null only if the hop failed or was unobserved, which requires a populated `notes` entry explaining which hop failed |
| `timestamp_coinbase_credit` | string \| null | yes | Timestamp Coinbase credited the USDC; null only if the hop failed or was unobserved, which requires a populated `notes` entry explaining which hop failed |
| `timestamp_fiat_spendable` | string \| null | yes | Timestamp the fiat became spendable; null only if the hop failed or was unobserved, which requires a populated `notes` entry explaining which hop failed |
| `fiat_received` | number | no | Fiat amount received after fees |
| `funding_tx_hash` | string \| null | yes | On-chain transaction hash of the single pre-registered inbound pre-funding transfer; identical on every record of the experiment since there is exactly one transfer; null is not expected — if unrecorded, a populated `notes` entry must explain why |
| `network_fee_usd` | number \| null | yes | On-chain network (gas) fee for the inbound transfer and deposit legs, in USD; null only when the network fee was zero, in which case a populated `notes` entry must state this |
| `fixed_fee_usd` | number | no | Coinbase quoted fixed conversion fee for the tranche, in USD; 0 is allowed |
| `quoted_fee_usd` | number | no | Fee quoted by Coinbase at conversion, verbatim from the source |
| `realized_fee_pct` | number | no | Derived quantity, not recorded directly: computed from `fixed_fee_usd`, `network_fee_usd`, and `amount_usdc` |
| `spread_vs_mid_pct` | number | no | Derived quantity, not recorded directly: computed from the fiat received and the observed USDC mid at execution time |
| `manual_steps` | integer | no | Count of manual operator steps for the tranche |
| `notes` | string \| null | yes | Optional note (e.g. fallback used, missing-value explanation) |

The template's `analysis.json` schema above still governs the final `experiments/usdc-fiat-sweep/analysis.json` after the run, with `control_condition` = "advertised Coinbase fee schedule", `treatment_condition` = "realized conversion cost per tranche", and `model` = "n/a (human-executed off-ramp)".

## usdc-fiat-sweep-api run-record schema

Per-tranche JSON records stored directly under `experiments/usdc-fiat-sweep-api/sessions/` (raw API artifacts live under `sessions/raw/`). Records are written and schema-validated by `experiments/usdc-fiat-sweep-api/sweep.ts`; transcription rules are in `experiments/usdc-fiat-sweep-api/record-extraction.md`. Mirrors the `usdc-fiat-sweep` schema, dropping `manual_steps` (execution is fully automated) and adding the fields the automated rail observes directly.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `tranche_id` | string | no | Tranche identifier (level plus replicate) |
| `replicate` | integer | no | Replicate number within the amount level (1 or 2) |
| `executed` | boolean | no | True if the tranche was executed; false only for the pre-registered `not_executed` replicate |
| `synthetic` | boolean | no | True only in `--dry-run` rehearsal records, which are never committed to `sessions/` |
| `amount_usdc` | number \| null | yes | USDC amount converted; non-null for every executed tranche, null only for the pre-registered `not_executed` replicate, which must carry a populated `notes` entry |
| `tx_hash_in` | string \| null | yes | On-chain transaction hash of the send from the receiver wallet to the Coinbase deposit address; null only for the `not_executed` replicate or if the on-chain hop failed, each of which requires a populated `notes` entry |
| `deposit_address` | string \| null | yes | Coinbase Base deposit address used as the sweep destination; null only for the `not_executed` replicate |
| `convert_quote_id` | string \| null | yes | Advanced Trade convert quote identifier, verbatim from the API; null only for the `not_executed` replicate or if the quote hop failed, each of which requires a populated `notes` entry |
| `usdc_mid` | number \| null | yes | USDC-USD spot mid at execution time; null only for the `not_executed` replicate |
| `mid_observed_at` | string \| null | yes | ISO 8601 timestamp with UTC offset at which `usdc_mid` was captured; null only for the `not_executed` replicate |
| `timestamp_sent` | string \| null | yes | Timestamp the on-chain send was made; null only if the hop failed or was unobserved, which requires a populated `notes` entry explaining which hop failed |
| `timestamp_coinbase_credit` | string \| null | yes | Timestamp Coinbase credited the USDC (convert quote accepted); null only if the hop failed or was unobserved, which requires a populated `notes` entry explaining which hop failed |
| `timestamp_fiat_spendable` | string \| null | yes | Timestamp the USD balance became spendable (convert fill observed); null only if the hop failed or was unobserved, which requires a populated `notes` entry explaining which hop failed |
| `fiat_received` | number \| null | yes | USD amount received after fees; null only for the `not_executed` replicate or if the convert hop failed, each of which requires a populated `notes` entry |
| `funding_tx_hash` | string \| null | yes | On-chain transaction hash of the single pre-registered inbound pre-funding transfer; identical on every record of the experiment since there is exactly one transfer; null is not expected — if unrecorded, a populated `notes` entry must explain why |
| `network_fee_usd` | number \| null | yes | On-chain network (gas) fee for the inbound transfer and sweep legs, in USD; null only when the network fee was zero, in which case a populated `notes` entry must state this |
| `fixed_fee_usd` | number | no | Coinbase quoted fixed conversion fee for the tranche, in USD; 0 is allowed |
| `quoted_fee_usd` | number | no | Fee quoted by the Advanced Trade convert API at conversion, verbatim from the source |
| `realized_fee_pct` | number \| null | yes | Derived quantity, not recorded directly: computed from `fixed_fee_usd`, `network_fee_usd`, and `amount_usdc`; null only for the `not_executed` replicate |
| `spread_vs_mid_pct` | number \| null | yes | Derived quantity, not recorded directly: computed from `fiat_received`, `amount_usdc`, and the observed USDC mid at execution time; null only for the `not_executed` replicate |
| `notes` | string \| null | yes | Optional note (e.g. failure reason, missing-value explanation) |

The template's `analysis.json` schema still governs the final `experiments/usdc-fiat-sweep-api/analysis.json` after the run, with `control_condition` = "published Advanced Trade taker fee schedule", `treatment_condition` = "realized conversion cost per tranche (automated)", and `model` = "n/a (script-executed off-ramp)".
