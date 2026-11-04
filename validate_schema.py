"""
Validate schema of experiment analysis.json files.

Checks that every experiments/*/analysis.json contains the required
top-level fields with correct scalar types, ISO date/timestamp formats,
enum values, token totals consistency, a well-formed scores object, and
that the `experiment` field matches the parent directory slug. Certain
fields are nullable (allowed to be null) while others must have values.

Usage:
    uv run python validate_schema.py [--self-test] [--sweep] [FILE ...]

With no FILE arguments, discovers and validates all
experiments/*/analysis.json files under the repository root. With --sweep,
each FILE is validated as a usdc-fiat-sweep-api sweep run record.

Exits with 0 if all files pass validation, 1 if any validation fails.

Standard library only; no third-party imports.
"""

import datetime
import json
import math
import pathlib
import re
import shutil
import sys
import tempfile

# Top-level fields that are allowed to be null.
NULLABLE_TOP_FIELDS = {"issue", "orchestrator_session"}

# Run-record fields that are allowed to be null.
NULLABLE_RUN_FIELDS = {"bytes", "note"}

# Top-level fields required to be non-null strings.
STRING_TOP_FIELDS = [
    "schema_version",
    "title",
    "date",
    "model",
    "control_condition",
    "treatment_condition",
    "rubric_version",
    "repo_head",
    "experiment_start",
    "experiment_end",
    "analyzed_at",
    "statistical_test",
    "conclusion",
]

# Top-level fields required to be non-null integers (bool is not an int here).
INTEGER_TOP_FIELDS = ["n_per_group"]

# ISO date (YYYY-MM-DD) and ISO 8601 timestamp formats enforced on top fields.
DATE_TOP_FIELDS = ["date"]
TIMESTAMP_TOP_FIELDS = ["experiment_start", "experiment_end", "analyzed_at"]

REQUIRED_TOP_FIELDS = [
    "experiment",
    *STRING_TOP_FIELDS[:2],
    "issue",
    *STRING_TOP_FIELDS[2:],
    *INTEGER_TOP_FIELDS,
    "orchestrator_session",
    "runs",
    "scores",
    "pre_acknowledged_limitations",
]

REQUIRED_RUN_FIELDS = [
    "group",
    "session_id",
    "messages",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "wall_clock_seconds",
    "bytes",
    "note",
]

# Integer run-record fields (bool is not accepted as an integer).
INTEGER_RUN_FIELDS = ["messages", "input_tokens", "output_tokens", "total_tokens"]

# Number run-record fields (int or float).
NUMBER_RUN_FIELDS = ["wall_clock_seconds"]

ALLOWED_GROUPS = {"control", "treatment"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}")


def _reject_constant(name):
    """json.loads parse_constant hook: reject NaN/Infinity tokens."""
    raise ValueError(f"invalid JSON constant {name}")


def _load_json_strict(text):
    return json.loads(text, parse_constant=_reject_constant)


def _is_finite_number(value):
    """True for a non-bool int or float that is finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_timestamp(value):
    """Accept only full ISO 8601 timestamps with a UTC offset."""
    if not TIMESTAMP_RE.match(value):
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return False
    return True


def validate_top_level(data):
    """Check required keys, scalar types, and date/timestamp formats."""
    errors = []
    for field in REQUIRED_TOP_FIELDS:
        if field not in data:
            errors.append(f"missing top-level field {field}")
            continue
        value = data[field]
        if value is None and field not in NULLABLE_TOP_FIELDS:
            errors.append(f"top-level field {field} is null")
    for field in STRING_TOP_FIELDS:
        if data.get(field) is not None and not isinstance(data[field], str):
            errors.append(f"top-level field {field} is not a string")
    for field in INTEGER_TOP_FIELDS:
        if not _is_int(data.get(field)):
            errors.append(f"top-level field {field} is not an integer")
    for field in DATE_TOP_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and not DATE_RE.match(value):
            errors.append(f"top-level field {field} is not an ISO date (YYYY-MM-DD)")
        elif isinstance(value, str):
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                errors.append(f"top-level field {field} is not a valid calendar date")
    for field in ("issue", "orchestrator_session"):
        if data.get(field) is not None and not isinstance(data[field], str):
            errors.append(f"top-level field {field} is not a string or null")
    for field in TIMESTAMP_TOP_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and not _parse_timestamp(value):
            errors.append(f"top-level field {field} is not an ISO 8601 timestamp")
    limitations = data.get("pre_acknowledged_limitations")
    if limitations is not None:
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) for item in limitations
        ):
            errors.append(
                "top-level field pre_acknowledged_limitations is not an array of strings"
            )
    experiment = data.get("experiment")
    if experiment is not None and not isinstance(experiment, str):
        errors.append("top-level field experiment is not a string")
    return errors


def validate_runs(runs):
    """Check run record structure, enum values, and token totals."""
    errors = []
    if not isinstance(runs, dict):
        return [f"runs is not an object: {type(runs).__name__}"]
    for run_id, record in runs.items():
        if not isinstance(record, dict):
            errors.append(f"run {run_id} is not an object")
            continue
        for field in REQUIRED_RUN_FIELDS:
            if field not in record:
                errors.append(f"run {run_id} missing {field}")
            elif record[field] is None and field not in NULLABLE_RUN_FIELDS:
                errors.append(f"run {run_id} has null {field}")
        group = record.get("group")
        if group is not None and not isinstance(group, str):
            errors.append(f"run {run_id} group is not a string")
        elif group is not None and group not in ALLOWED_GROUPS:
            errors.append(
                f"run {run_id} group {group!r} not in {sorted(ALLOWED_GROUPS)}"
            )
        for field in INTEGER_RUN_FIELDS:
            value = record.get(field)
            if field in record and value is not None and not _is_int(value):
                errors.append(f"run {run_id} field {field} is not an integer")
            elif field in record and value is not None and value < 0:
                errors.append(f"run {run_id} field {field} is negative")
        for field in NUMBER_RUN_FIELDS:
            value = record.get(field)
            if field in record and value is not None and not _is_finite_number(value):
                errors.append(f"run {run_id} field {field} is not a finite number")
            elif field in record and value is not None and value < 0:
                errors.append(f"run {run_id} field {field} is negative")
        for field in ("session_id", "note"):
            if field in record and record[field] is not None and not isinstance(record[field], str):
                errors.append(f"run {run_id} field {field} is not a string or null")
        if "bytes" in record and record["bytes"] is not None and not _is_int(record["bytes"]):
            errors.append(f"run {run_id} field bytes is not an integer or null")
        elif "bytes" in record and record["bytes"] is not None and record["bytes"] < 0:
            errors.append(f"run {run_id} field bytes is negative")
        if (
            _is_int(record.get("input_tokens"))
            and _is_int(record.get("output_tokens"))
            and _is_int(record.get("total_tokens"))
            and record["input_tokens"] + record["output_tokens"] != record["total_tokens"]
        ):
            errors.append(f"run {run_id} total_tokens != input_tokens + output_tokens")
    return errors


def validate_scores(scores, runs):
    """Check the scores object shape: dict of run ID to dict."""
    errors = []
    if not isinstance(scores, dict):
        errors.append(f"scores is not an object: {type(scores).__name__}")
        return errors
    known = set(runs) if isinstance(runs, dict) else set()
    for run_id, entry in scores.items():
        if not isinstance(entry, dict):
            errors.append(f"scores[{run_id}] is not an object")
        if run_id not in known:
            errors.append(f"scores key {run_id} does not match any run ID")
    return errors


def validate_record(data, expected_slug=None):
    """Validate a full analysis.json record.

    If expected_slug is given, the `experiment` field must equal it.
    """
    if not isinstance(data, dict):
        return [f"top-level JSON value is not an object: {type(data).__name__}"]
    errors = validate_top_level(data)
    runs = data.get("runs")
    errors.extend(validate_runs(runs))
    errors.extend(validate_scores(data.get("scores"), runs))
    if (
        expected_slug is not None
        and isinstance(data.get("experiment"), str)
        and data["experiment"] != expected_slug
    ):
        errors.append(
            f"experiment {data['experiment']!r} does not match directory slug {expected_slug!r}"
        )
    return errors


def validate_path(path, sweep_record=False):
    if sweep_record:
        return validate_sweep_path(path)
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_record(data, expected_slug=pathlib.Path(path).parent.name)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


# Run-record fields for usdc-fiat-sweep-api sweep records. Nullable fields
# carry explicit null-requires-notes rules enforced by validate_sweep_record.
SWEEP_NULLABLE_FIELDS = [
    "amount_usdc",
    "tx_hash_in",
    "deposit_address",
    "convert_quote_id",
    "usdc_mid",
    "mid_observed_at",
    "timestamp_sent",
    "timestamp_coinbase_credit",
    "timestamp_fiat_spendable",
    "fiat_received",
    "funding_tx_hash",
    "network_fee_usd",
    "realized_fee_pct",
    "spread_vs_mid_pct",
    "notes",
]

SWEEP_REQUIRED_NON_NULL_FIELDS = [
    "tranche_id",
    "replicate",
    "executed",
    "synthetic",
    "fixed_fee_usd",
    "quoted_fee_usd",
]

SWEEP_TIMESTAMP_FIELDS = [
    "mid_observed_at",
    "timestamp_sent",
    "timestamp_coinbase_credit",
    "timestamp_fiat_spendable",
]

# Fields that must be null exactly when the record is not_executed.
SWEEP_NOT_EXECUTED_NULLABLE = [
    "amount_usdc",
    "tx_hash_in",
    "deposit_address",
    "convert_quote_id",
    "usdc_mid",
    "mid_observed_at",
    "fiat_received",
    "realized_fee_pct",
    "spread_vs_mid_pct",
]


def _sweep_has_notes(data):
    return isinstance(data.get("notes"), str) and data["notes"].strip() != ""


# usdc-fiat-sweep-v2 run-record schema (see DATA_DICTIONARY.md).
SWEEP_V2_EXECUTION_STATUS_ENUM = [
    "clean_fill",
    "network_timeout",
    "api_error",
    "operator_interrupted",
    "partial_fill",
    "rejected_below_minimum",
    "not_executed",
    "not_executed_below_minimum",
]

SWEEP_V2_REQUIRED_NON_NULL_FIELDS = [
    "tranche_id",
    "replicate",
    "provider_slug",
    "arm",
    "executed",
    "synthetic",
    "execution_status",
    "is_latency_valid",
    "fiat_currency",
    "fixed_fee_usd",
    "quoted_fee_usd",
]

SWEEP_V2_NULLABLE_FIELDS = [
    "amount_usdc",
    "fiat_received",
    "order_txid",
    "quoted_price",
    "avg_fill_price",
    "quoted_slippage_max",
    "realized_slippage",
    "pair_mid",
    "mid_observed_at",
    "timestamp_sent",
    "timestamp_provider_credit",
    "timestamp_fiat_spendable",
    "timestamp_bank_arrival",
    "tx_hash_in",
    "funding_tx_hash",
    "network_fee_usd",
    "disbursement_fee_fiat",
    "bank_intermediary_deduction",
    "net_amount_settled",
    "realized_fee_pct",
    "spread_vs_mid_pct",
    "notes",
]

SWEEP_V2_TIMESTAMP_FIELDS = [
    "mid_observed_at",
    "timestamp_sent",
    "timestamp_provider_credit",
    "timestamp_fiat_spendable",
    "timestamp_bank_arrival",
]

SWEEP_V2_NUMBER_FIELDS = [
    "fixed_fee_usd",
    "quoted_fee_usd",
    "amount_usdc",
    "fiat_received",
    "quoted_price",
    "avg_fill_price",
    "quoted_slippage_max",
    "realized_slippage",
    "pair_mid",
    "network_fee_usd",
    "disbursement_fee_fiat",
    "bank_intermediary_deduction",
    "net_amount_settled",
    "realized_fee_pct",
    "spread_vs_mid_pct",
]


def validate_v2_sweep_record(data):
    """Validate one usdc-fiat-sweep-v2 run record against DATA_DICTIONARY.md."""
    if not isinstance(data, dict):
        return [f"top-level JSON value is not an object: {type(data).__name__}"]
    errors = []
    for field in SWEEP_V2_REQUIRED_NON_NULL_FIELDS:
        if field not in data:
            errors.append(f"missing field {field}")
        elif data[field] is None:
            errors.append(f"field {field} is null")
    for field in SWEEP_V2_NULLABLE_FIELDS:
        if field not in data:
            errors.append(f"missing field {field}")
    if errors:
        return errors
    for field in ("tranche_id", "provider_slug", "arm", "fiat_currency",
                  "order_txid", "tx_hash_in", "funding_tx_hash", "notes"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"field {field} is not a string or null")
    for field in SWEEP_V2_TIMESTAMP_FIELDS:
        value = data.get(field)
        if value is not None and (not isinstance(value, str) or not _parse_timestamp(value)):
            errors.append(f"field {field} is not an ISO 8601 timestamp")
    if not _is_int(data.get("replicate")) or data["replicate"] < 1:
        errors.append("field replicate is not an integer >= 1")
    for field in ("executed", "synthetic", "is_latency_valid"):
        if not isinstance(data.get(field), bool):
            errors.append(f"field {field} is not a boolean")
    if data.get("execution_status") not in SWEEP_V2_EXECUTION_STATUS_ENUM:
        errors.append(f"execution_status is not one of {SWEEP_V2_EXECUTION_STATUS_ENUM}")
    if data.get("provider_slug") not in ("kraken", "coinbase"):
        errors.append("provider_slug is not 'kraken' or 'coinbase'")
    if data.get("arm") not in ("A", "B", "C"):
        errors.append("arm is not 'A', 'B', or 'C'")
    if data.get("fiat_currency") not in ("USD", "CAD"):
        errors.append("fiat_currency is not 'USD' or 'CAD'")
    for field in SWEEP_V2_NUMBER_FIELDS:
        value = data.get(field)
        if value is not None and not _is_finite_number(value):
            errors.append(f"field {field} is not a finite number or null")
        elif value is not None and value < 0 and field not in (
            "realized_slippage",
            "spread_vs_mid_pct",
        ):
            # Slippage and spread on a sell can legitimately be negative when
            # the fill lands above the reference price.
            errors.append(f"field {field} is negative")
    if errors:
        return errors

    executed = data["executed"]
    notes_ok = _sweep_has_notes(data)
    if not executed:
        for field in ("amount_usdc", "fiat_received", "pair_mid", "mid_observed_at"):
            if data.get(field) is not None:
                errors.append(f"non-executed record has non-null {field}")
        if not notes_ok:
            errors.append("non-executed record requires a populated notes entry")
        if data["execution_status"] not in (
            "not_executed",
            "not_executed_below_minimum",
            "rejected_below_minimum",
        ):
            errors.append("non-executed record has an executed execution_status")
    else:
        if data["execution_status"] in (
            "not_executed",
            "not_executed_below_minimum",
            "rejected_below_minimum",
        ):
            errors.append("executed record has a non-executed execution_status")
        for field in ("timestamp_provider_credit", "timestamp_fiat_spendable"):
            if data.get(field) is None and not notes_ok:
                errors.append(f"executed record has null {field} without a populated notes entry")
        if data.get("fiat_received") is None and not notes_ok:
            errors.append("executed record has null fiat_received without a populated notes entry")
        # Order-book consistency (Kraken arms only).
        if data.get("provider_slug") == "kraken" and data.get("order_txid") is not None:
            qp = data.get("quoted_price")
            afp = data.get("avg_fill_price")
            rsl = data.get("realized_slippage")
            if _is_finite_number(qp) and qp > 0 and _is_finite_number(afp) and _is_finite_number(rsl):
                expected = (afp - qp) / qp
                if abs(rsl - expected) > 1e-6:
                    errors.append("realized_slippage does not match quoted_price and avg_fill_price")
        # Spread consistency.
        amount = data.get("amount_usdc")
        mid = data.get("pair_mid")
        fiat = data.get("fiat_received")
        svp = data.get("spread_vs_mid_pct")
        if (
            _is_finite_number(amount)
            and amount > 0
            and _is_finite_number(mid)
            and mid > 0
            and _is_finite_number(fiat)
            and _is_finite_number(svp)
        ):
            expected = 100.0 * (amount * mid - fiat) / (amount * mid)
            if abs(svp - expected) > 0.005:
                errors.append("spread_vs_mid_pct does not match fiat_received, amount_usdc, pair_mid")
        # Realized fee consistency (USDC-denominated legs only).
        fixed = data.get("fixed_fee_usd")
        net = data.get("network_fee_usd") or 0
        rfp = data.get("realized_fee_pct")
        if (
            _is_finite_number(amount)
            and amount > 0
            and _is_finite_number(fixed)
            and _is_finite_number(rfp)
        ):
            if abs(rfp - 100.0 * (fixed + net) / amount) > 0.005:
                errors.append("realized_fee_pct does not match fixed_fee_usd, network_fee_usd, amount_usdc")
    # Disbursement arm rules.
    if data.get("arm") == "B" and data.get("tranche_id") == "cad-eft":
        if data.get("disbursement_fee_fiat") is None and not notes_ok:
            errors.append("disbursement record has null disbursement_fee_fiat without a populated notes entry")
    else:
        for field in ("timestamp_bank_arrival", "net_amount_settled", "bank_intermediary_deduction"):
            if data.get(field) is not None:
                errors.append(f"non-disbursement record has non-null {field}")
    return errors


def validate_v2_sweep_path(path):
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_v2_sweep_record(data)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


def validate_sweep_record(data):
    """Validate one usdc-fiat-sweep-api run record against DATA_DICTIONARY.md."""
    if not isinstance(data, dict):
        return [f"top-level JSON value is not an object: {type(data).__name__}"]
    errors = []
    for field in SWEEP_REQUIRED_NON_NULL_FIELDS:
        if field not in data:
            errors.append(f"missing field {field}")
        elif data[field] is None:
            errors.append(f"field {field} is null")
    for field in SWEEP_NULLABLE_FIELDS:
        if field not in data:
            errors.append(f"missing field {field}")
    if errors:
        return errors
    for field in ("tranche_id", "tx_hash_in", "deposit_address", "convert_quote_id", "notes", "funding_tx_hash"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"field {field} is not a string or null")
    for field in SWEEP_TIMESTAMP_FIELDS:
        value = data.get(field)
        if value is not None and (not isinstance(value, str) or not _parse_timestamp(value)):
            errors.append(f"field {field} is not an ISO 8601 timestamp")
    for field in ("replicate",):
        if not _is_int(data.get(field)):
            errors.append(f"field {field} is not an integer")
        elif data[field] not in (1, 2):
            errors.append(f"field {field} is not 1 or 2")
    for field in ("executed", "synthetic"):
        if not isinstance(data.get(field), bool):
            errors.append(f"field {field} is not a boolean")
    for field in ("fixed_fee_usd", "quoted_fee_usd", "amount_usdc", "usdc_mid",
                  "fiat_received", "network_fee_usd", "realized_fee_pct", "spread_vs_mid_pct"):
        value = data.get(field)
        if value is not None and not _is_finite_number(value):
            errors.append(f"field {field} is not a finite number or null")
        elif value is not None and value < 0:
            errors.append(f"field {field} is negative")
    if errors:
        return errors

    executed = data["executed"]
    if not executed:
        for field in SWEEP_NOT_EXECUTED_NULLABLE:
            if data.get(field) is not None:
                errors.append(f"not_executed record has non-null {field}")
        if not _sweep_has_notes(data):
            errors.append("not_executed record requires a populated notes entry")
    else:
        for field in SWEEP_NOT_EXECUTED_NULLABLE:
            if data.get(field) is None:
                errors.append(f"executed record has null {field}")
        # Null-requires-notes rules for executed records.
        hop_fields = [
            ("tx_hash_in", "tx_hash_in"),
            ("timestamp_sent", "timestamp_sent"),
            ("timestamp_coinbase_credit", "timestamp_coinbase_credit"),
            ("timestamp_fiat_spendable", "timestamp_fiat_spendable"),
        ]
        for field, _ in hop_fields:
            if data.get(field) is None and not _sweep_has_notes(data):
                errors.append(f"executed record has null {field} without a populated notes entry")
        if data.get("network_fee_usd") is None and not _sweep_has_notes(data):
            errors.append("executed record has null network_fee_usd without a populated notes entry")
        if data.get("funding_tx_hash") is None and not _sweep_has_notes(data):
            errors.append("executed record has null funding_tx_hash without a populated notes entry")
        if data.get("fiat_received") is None and not _sweep_has_notes(data):
            errors.append("executed record has null fiat_received without a populated notes entry")
        amount = data.get("amount_usdc")
        fixed = data.get("fixed_fee_usd")
        net = data.get("network_fee_usd") or 0
        rfp = data.get("realized_fee_pct")
        if (
            _is_finite_number(amount)
            and amount > 0
            and _is_finite_number(fixed)
            and _is_finite_number(rfp)
            and abs(rfp - 100.0 * (fixed + net) / amount) > 0.005
        ):
            errors.append("realized_fee_pct does not match fixed_fee_usd, network_fee_usd, amount_usdc")
        mid = data.get("usdc_mid")
        fiat = data.get("fiat_received")
        svp = data.get("spread_vs_mid_pct")
        if (
            _is_finite_number(amount)
            and amount > 0
            and _is_finite_number(mid)
            and mid > 0
            and _is_finite_number(fiat)
            and _is_finite_number(svp)
        ):
            expected = 100.0 * (amount * mid - fiat) / (amount * mid)
            if abs(svp - expected) > 0.005:
                errors.append("spread_vs_mid_pct does not match fiat_received, amount_usdc, usdc_mid")
    return errors


def validate_sweep_path(path):
    try:
        with open(path) as f:
            data = _load_json_strict(f.read())
    except (OSError, ValueError) as exc:
        print(f"Failed to load {path}: {exc}")
        return False
    errors = validate_sweep_record(data)
    if errors:
        for error in errors:
            print(f"{path}: {error}")
        return False
    return True


MINIMAL_VALID_RECORD = {
    "experiment": "exp-example",
    "schema_version": "1.0.0",
    "title": "Example Experiment",
    "issue": None,
    "date": "2026-01-01",
    "model": "model-under-test",
    "n_per_group": 5,
    "control_condition": "standard instructions",
    "treatment_condition": "modified instructions",
    "rubric_version": "rubric-v1",
    "orchestrator_session": None,
    "repo_head": "0000000000000000000000000000000000000000",
    "experiment_start": "2026-01-01T00:00:00Z",
    "experiment_end": "2026-01-01T01:00:00Z",
    "analyzed_at": "2026-01-02T00:00:00Z",
    "runs": {
        "control_1": {
            "group": "control",
            "session_id": "20260101_01",
            "messages": 10,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "wall_clock_seconds": 30,
            "bytes": 1024,
            "note": None,
        }
    },
    "scores": {"control_1": {"pass": True}},
    "statistical_test": "fisher-exact",
    "conclusion": "No effect observed.",
    "pre_acknowledged_limitations": ["small sample size"],
}


def _mutated(**changes):
    record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    for dotted, value in changes.items():
        parts = dotted.split("__")
        target = record
        for part in parts[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[parts[-1]]
        else:
            target[parts[-1]] = value
    return record


class _Delete:
    pass


_DELETE = _Delete()


def _expect_errors(record, substring, label):
    errors = validate_record(record)
    if not any(substring in error for error in errors):
        print(f"self-test FAILED: {label} not caught: {errors}")
        return False
    return True


def self_test():
    if validate_record(MINIMAL_VALID_RECORD):
        print("self-test FAILED: minimal valid record reported errors")
        return False
    if validate_record(MINIMAL_VALID_RECORD, expected_slug="exp-example"):
        print("self-test FAILED: valid record with matching slug reported errors")
        return False
    cases = [
        (_mutated(title=_DELETE), "missing top-level field title", "missing required key"),
        (_mutated(title=42), "title is not a string", "wrong scalar type"),
        (_mutated(n_per_group=True), "n_per_group is not an integer", "bool not int"),
        (_mutated(n_per_group=1.5), "n_per_group is not an integer", "float not int"),
        (_mutated(date="2026-13-45"), "not a valid calendar date", "invalid date format"),
        (_mutated(date="not-a-date"), "not an ISO date", "non-date string"),
        (_mutated(date="2026-02-30"), "not a valid calendar date", "impossible calendar date"),
        (_mutated(analyzed_at="01/02/2026T00:00:00Z"), "not an ISO 8601 timestamp", "bad timestamp"),
        (
            _mutated(runs__control_1={"group": "placebo"}),
            "not in ['control', 'treatment']",
            "invalid group enum",
        ),
        (
            _mutated(runs__control_1__total_tokens=999),
            "total_tokens != input_tokens + output_tokens",
            "token totals mismatch",
        ),
        (
            _mutated(runs__control_1__messages="ten"),
            "messages is not an integer",
            "non-integer run field",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds="slow"),
            "wall_clock_seconds is not a finite number",
            "non-number wall clock",
        ),
        (
            _mutated(runs__control_1__group=_DELETE),
            "run control_1 missing group",
            "missing run field",
        ),
        (_mutated(scores=[]), "scores is not an object", "scores wrong container"),
        (
            _mutated(scores={"control_1": "pass"}),
            "scores[control_1] is not an object",
            "score entry not object",
        ),
        (
            _mutated(scores={"unknown-run": {"pass": True}}),
            "does not match any run ID",
            "unknown scores key",
        ),
        (
            _mutated(pre_acknowledged_limitations=[1, 2]),
            "not an array of strings",
            "non-string limitation",
        ),
        ([MINIMAL_VALID_RECORD], "not an object: list", "array top level"),
        ("not-an-object", "not an object: str", "scalar top level"),
        (
            _mutated(runs__control_1__group=[]),
            "run control_1 group is not a string",
            "non-hashable group value",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds=True),
            "wall_clock_seconds is not a finite number",
            "boolean wall clock",
        ),
        (
            _mutated(runs__control_1__wall_clock_seconds=-1.5),
            "wall_clock_seconds is negative",
            "negative wall clock",
        ),
        (
            _mutated(runs__control_1__input_tokens=-10),
            "input_tokens is negative",
            "negative input tokens",
        ),
        (
            _mutated(scores={"unknown-run": {"pass": True}}, runs={}),
            "scores key unknown-run does not match any run ID",
            "orphan score key with zero runs",
        ),
        (
            _mutated(runs__control_1__session_id=42),
            "session_id is not a string or null",
            "non-string session_id",
        ),
        (
            _mutated(runs__control_1__bytes="big"),
            "bytes is not an integer or null",
            "non-integer bytes",
        ),
        (
            _mutated(runs__control_1__note=3.14),
            "note is not a string or null",
            "non-string note",
        ),
        (
            _mutated(analyzed_at="2026-01-02T00:00:00"),
            "not an ISO 8601 timestamp",
            "naive timestamp without offset",
        ),
        (
            _mutated(analyzed_at="2026-01-02"),
            "not an ISO 8601 timestamp",
            "date-only timestamp",
        ),
    ]
    for record, substring, label in cases:
        if not _expect_errors(record, substring, label):
            return False
    nan_record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    nan_record["runs"]["control_1"]["wall_clock_seconds"] = float("nan")
    if not _expect_errors(
        nan_record, "wall_clock_seconds is not a finite number", "NaN wall clock"
    ):
        return False
    inf_record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
    inf_record["runs"]["control_1"]["wall_clock_seconds"] = float("inf")
    if not _expect_errors(
        inf_record, "wall_clock_seconds is not a finite number", "Infinity wall clock"
    ):
        return False
    accepted = [
        (_mutated(issue=None), "null issue accepted"),
        (_mutated(orchestrator_session=None), "null orchestrator_session accepted"),
        (_mutated(runs__control_1__bytes=None), "null bytes accepted"),
        (_mutated(runs__control_1__note=None), "null note accepted"),
        (_mutated(analyzed_at="2026-01-02T00:00:00+00:00"), "offset timestamp accepted"),
    ]
    for record, label in accepted:
        if validate_record(record):
            print(f"self-test FAILED: {label}: {validate_record(record)}")
            return False
    slug_record = json.loads(json.dumps(MINIMAL_VALID_RECORD))
    slug_record["experiment"] = "exp-other"
    slug_errors = validate_record(slug_record, expected_slug="exp-example")
    if not any("does not match directory slug" in error for error in slug_errors):
        print(f"self-test FAILED: slug mismatch not caught: {slug_errors}")
        return False

    # usdc-fiat-sweep-api sweep-record validator.
    def _sweep_mutated(**changes):
        record = _load_json_strict(json.dumps(MINIMAL_SWEEP_EXECUTED))
        record.update(changes)
        return record

    def _sweep_deleted(key):
        record = _load_json_strict(json.dumps(MINIMAL_SWEEP_EXECUTED))
        del record[key]
        return record

    MINIMAL_SWEEP_EXECUTED = {
        "tranche_id": "1-1",
        "replicate": 1,
        "executed": True,
        "synthetic": False,
        "amount_usdc": 1.0,
        "tx_hash_in": "0x" + "a" * 64,
        "deposit_address": "0x" + "b" * 40,
        "convert_quote_id": "quote-123",
        "usdc_mid": 1.0,
        "mid_observed_at": "2026-02-01T00:00:00Z",
        "timestamp_sent": "2026-02-01T00:00:01Z",
        "timestamp_coinbase_credit": "2026-02-01T00:00:10Z",
        "timestamp_fiat_spendable": "2026-02-01T00:00:20Z",
        "fiat_received": 0.99,
        "funding_tx_hash": "0x" + "c" * 64,
        "network_fee_usd": 0.0,
        "fixed_fee_usd": 0.01,
        "quoted_fee_usd": 0.01,
        "realized_fee_pct": 1.0,
        "spread_vs_mid_pct": 1.0,
        "notes": None,
    }
    if validate_sweep_record(_load_json_strict(json.dumps(MINIMAL_SWEEP_EXECUTED))):
        print("self-test FAILED: minimal valid sweep record reported errors")
        return False
    sweep_cases = [
        (_sweep_deleted("tranche_id"), "missing field tranche_id", "sweep missing required key"),
        (_sweep_mutated( tranche_id=42), "tranche_id is not a string or null", "sweep wrong scalar type"),
        (_sweep_mutated( fixed_fee_usd=None), "field fixed_fee_usd is null", "sweep null non-nullable"),
        (_sweep_mutated( replicate=3), "replicate is not 1 or 2", "sweep bad replicate"),
        (_sweep_mutated( executed="yes"), "executed is not a boolean", "sweep non-bool executed"),
        (_sweep_mutated( fixed_fee_usd=-1), "fixed_fee_usd is negative", "sweep negative fee"),
        (_sweep_mutated( timestamp_sent="01/02/2026"), "timestamp_sent is not an ISO 8601 timestamp", "sweep bad timestamp"),
        (_sweep_mutated( amount_usdc=None), "executed record has null amount_usdc", "sweep executed null amount"),
        (_sweep_mutated( realized_fee_pct=2.0), "realized_fee_pct does not match", "sweep derived fee mismatch"),
        (_sweep_mutated( spread_vs_mid_pct=9.9), "spread_vs_mid_pct does not match", "sweep derived spread mismatch"),
    ]
    for record, substring, label in sweep_cases:
        errors = validate_sweep_record(record)
        if not any(substring in error for error in errors):
            print(f"self-test FAILED: {label} not caught: {errors}")
            return False
    not_executed = _load_json_strict(json.dumps(MINIMAL_SWEEP_EXECUTED))
    not_executed.update(
        {
            "executed": False,
            "amount_usdc": None,
            "tx_hash_in": None,
            "deposit_address": None,
            "convert_quote_id": None,
            "usdc_mid": None,
            "mid_observed_at": None,
            "timestamp_sent": None,
            "timestamp_coinbase_credit": None,
            "timestamp_fiat_spendable": None,
            "fiat_received": None,
            "realized_fee_pct": None,
            "spread_vs_mid_pct": None,
            "network_fee_usd": None,
            "notes": "pre-registered not_executed reason",
        }
    )
    if validate_sweep_record(not_executed):
        print(f"self-test FAILED: not_executed record rejected: {validate_sweep_record(not_executed)}")
        return False
    bad_ne = _load_json_strict(json.dumps(not_executed))
    bad_ne["notes"] = None
    if not any(
        "not_executed record requires a populated notes entry" in error
        for error in validate_sweep_record(bad_ne)
    ):
        print("self-test FAILED: not_executed missing notes not caught")
        return False
    bad_ne2 = _load_json_strict(json.dumps(not_executed))
    bad_ne2["amount_usdc"] = 1.0
    if not any(
        "not_executed record has non-null amount_usdc" in error
        for error in validate_sweep_record(bad_ne2)
    ):
        print("self-test FAILED: not_executed non-null amount not caught")
        return False

    # usdc-fiat-sweep-v2 sweep-record validator.
    MINIMAL_V2_EXECUTED = {
        "tranche_id": "kraken-10",
        "replicate": 1,
        "provider_slug": "kraken",
        "arm": "A",
        "executed": True,
        "synthetic": False,
        "execution_status": "clean_fill",
        "is_latency_valid": True,
        "fiat_currency": "USD",
        "amount_usdc": 10.0,
        "fiat_received": 9.98,
        "order_txid": "OABC-123",
        "quoted_price": 0.9999,
        "avg_fill_price": 0.9998,
        "quoted_slippage_max": 0.001,
        "realized_slippage": (0.9998 - 0.9999) / 0.9999,
        "pair_mid": 0.99995,
        "mid_observed_at": "2026-02-01T00:00:00Z",
        "timestamp_sent": None,
        "timestamp_provider_credit": "2026-02-01T00:00:10Z",
        "timestamp_fiat_spendable": "2026-02-01T00:00:20Z",
        "timestamp_bank_arrival": None,
        "tx_hash_in": None,
        "funding_tx_hash": None,
        "network_fee_usd": None,
        "fixed_fee_usd": 0.0,
        "quoted_fee_usd": 0.0,
        "disbursement_fee_fiat": None,
        "bank_intermediary_deduction": None,
        "net_amount_settled": None,
        "realized_fee_pct": 0.0,
        "spread_vs_mid_pct": None,
        "notes": None,
    }

    def _v2_mutated(**changes):
        record = _load_json_strict(json.dumps(MINIMAL_V2_EXECUTED))
        record.update(changes)
        return record

    def _v2_deleted(key):
        record = _load_json_strict(json.dumps(MINIMAL_V2_EXECUTED))
        del record[key]
        return record

    if validate_v2_sweep_record(_load_json_strict(json.dumps(MINIMAL_V2_EXECUTED))):
        errors = validate_v2_sweep_record(_load_json_strict(json.dumps(MINIMAL_V2_EXECUTED)))
        print(f"self-test FAILED: minimal valid v2 record reported errors: {errors}")
        return False
    v2_cases = [
        (_v2_deleted("provider_slug"), "missing field provider_slug", "v2 missing required key"),
        (_v2_mutated(execution_status="exploded"), "execution_status is not one of", "v2 bad enum"),
        (_v2_mutated(provider_slug="binance"), "provider_slug is not 'kraken' or 'coinbase'", "v2 bad provider"),
        (_v2_mutated(arm="D"), "arm is not 'A', 'B', or 'C'", "v2 bad arm"),
        (_v2_mutated(fiat_currency="EUR"), "fiat_currency is not 'USD' or 'CAD'", "v2 bad currency"),
        (_v2_mutated(is_latency_valid="yes"), "is_latency_valid is not a boolean", "v2 non-bool latency flag"),
        (_v2_mutated(replicate=0), "replicate is not an integer >= 1", "v2 bad replicate"),
        (_v2_mutated(timestamp_bank_arrival="2026-02-01T01:00:00Z"), "non-disbursement record has non-null timestamp_bank_arrival", "v2 bank field outside arm B"),
        (
            _v2_mutated(realized_slippage=0.5),
            "realized_slippage does not match quoted_price and avg_fill_price",
            "v2 slippage mismatch",
        ),
        (
            _v2_mutated(spread_vs_mid_pct=5.0),
            "spread_vs_mid_pct does not match fiat_received, amount_usdc, pair_mid",
            "v2 spread mismatch",
        ),
    ]
    for record, substring, label in v2_cases:
        errors = validate_v2_sweep_record(record)
        if not any(substring in error for error in errors):
            print(f"self-test FAILED: {label} not caught: {errors}")
            return False
    v2_not_executed = _load_json_strict(json.dumps(MINIMAL_V2_EXECUTED))
    v2_not_executed.update(
        {
            "executed": False,
            "execution_status": "not_executed_below_minimum",
            "amount_usdc": None,
            "fiat_received": None,
            "pair_mid": None,
            "mid_observed_at": None,
            "is_latency_valid": False,
            "order_txid": None,
            "quoted_price": None,
            "avg_fill_price": None,
            "realized_slippage": None,
            "timestamp_provider_credit": None,
            "timestamp_fiat_spendable": None,
            "notes": "residue below provider minimum trade size",
        }
    )
    if validate_v2_sweep_record(v2_not_executed):
        print(f"self-test FAILED: v2 not_executed record rejected: {validate_v2_sweep_record(v2_not_executed)}")
        return False
    v2_bad_ne = _load_json_strict(json.dumps(v2_not_executed))
    v2_bad_ne["notes"] = None
    if not any(
        "non-executed record requires a populated notes entry" in error
        for error in validate_v2_sweep_record(v2_bad_ne)
    ):
        print("self-test FAILED: v2 not_executed missing notes not caught")
        return False
    # Discovery mode: a protocol-only directory (no sessions content) is skipped
    # as pre-registration state; sessions content or no protocol.md with missing
    # analysis.json must fail; empty experiments/ passes.
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        pre_reg = base / "experiments" / "exp-pre-reg"
        pre_reg.mkdir(parents=True)
        (pre_reg / "protocol.md").write_text("# Protocol\n")
        (pre_reg / "sessions").mkdir()
        (pre_reg / "sessions" / ".gitkeep").write_text("")
        pending = base / "experiments" / "exp-pending"
        pending.mkdir(parents=True)
        (pending / "protocol.md").write_text("# Protocol\n")
        (pending / "sessions").mkdir()
        (pending / "sessions" / "raw.txt").write_text("raw\n")
        (pending / "sessions" / ".gitkeep").write_text("")
        present = base / "experiments" / "exp-present"
        present.mkdir()
        record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
        record["experiment"] = "exp-present"
        (present / "analysis.json").write_text(json.dumps(record))
        if validate_discovery(base):
            print("self-test FAILED: discovery accepted sessions content without analysis.json")
            return False
        pre_reg_only_base = pathlib.Path(tempfile.mkdtemp())
        try:
            only_pre = pre_reg_only_base / "experiments" / "exp-pre-reg"
            only_pre.mkdir(parents=True)
            (only_pre / "protocol.md").write_text("# Protocol\n")
            (only_pre / "sessions").mkdir()
            (only_pre / "sessions" / ".gitkeep").write_text("")
            if not validate_discovery(pre_reg_only_base):
                print("self-test FAILED: discovery rejected pre-registration-only state")
                return False
        finally:
            shutil.rmtree(pre_reg_only_base)
        empty_base = pathlib.Path(tempfile.mkdtemp())
        try:
            (empty_base / "experiments").mkdir()
            if not validate_discovery(empty_base):
                print("self-test FAILED: discovery rejected empty experiments dir")
                return False
        finally:
            shutil.rmtree(empty_base)
    print(
        "self-test passed: valid record accepted, each rule rejects its invalid case, discovery skips pre-registration state and flags sessions content without analysis.json"
    )
    return True


def validate_discovery(base):
    experiments_dir = pathlib.Path(base) / "experiments"
    if not experiments_dir.is_dir():
        print("No experiments/ directory found; nothing to validate.")
        return True
    exp_dirs = sorted(
        d
        for d in experiments_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if not exp_dirs:
        print("No experiments/* directories found; nothing to validate.")
        return True
    all_ok = True
    for exp_dir in exp_dirs:
        analysis = exp_dir / "analysis.json"
        if not analysis.is_file():
            if exp_dir.name == "usdc-fiat-sweep-api":
                # Run-record experiment: sweep records under sessions/ are
                # validated directly; raw/ artifacts are not structured
                # records. Pre-registration state (no records yet) is skipped.
                sessions_dir = exp_dir / "sessions"
                sweep_records = (
                    sorted(sessions_dir.glob("*.json")) if sessions_dir.is_dir() else []
                )
                if not sweep_records:
                    print(
                        f"Skipping {exp_dir.name}: pre-registration state "
                        "(no analysis.json, no sweep run records yet)"
                    )
                    continue
                for record_path in sweep_records:
                    if record_path.name == "funding.json":
                        # funding.json is the single funding-transfer record,
                        # not a per-tranche run record; it has its own shape.
                        continue
                    if not validate_sweep_path(record_path):
                        all_ok = False
                continue
            if exp_dir.name == "usdc-fiat-sweep-v2":
                # v2 sweep records under sessions/ are validated with the v2
                # schema; funding.json and raw/ are not per-tranche records.
                sessions_dir = exp_dir / "sessions"
                v2_records = (
                    sorted(sessions_dir.glob("*.json")) if sessions_dir.is_dir() else []
                )
                if not v2_records:
                    print(
                        f"Skipping {exp_dir.name}: pre-registration state "
                        "(no analysis.json, no sweep run records yet)"
                    )
                    continue
                for record_path in v2_records:
                    if record_path.name == "funding.json":
                        continue
                    if not validate_v2_sweep_path(record_path):
                        all_ok = False
                continue
            sessions_dir = exp_dir / "sessions"
            has_sessions_content = sessions_dir.is_dir() and any(
                p.is_file() and p.name != ".gitkeep" for p in sessions_dir.rglob("*")
            )
            if (exp_dir / "protocol.md").is_file() and not has_sessions_content:
                print(
                    f"Skipping {exp_dir.name}: pre-registration state "
                    "(protocol.md present, no sessions content, no analysis.json)"
                )
                continue
            print(f"Validation error: missing {analysis}")
            all_ok = False
            continue
        if not validate_path(analysis):
            all_ok = False
    return all_ok


def main():
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    sweep_mode = "--sweep" in sys.argv
    sweep_v2_mode = "--sweep-v2" in sys.argv
    file_args = [
        arg
        for arg in sys.argv[1:]
        if arg not in ("--self-test", "--sweep", "--sweep-v2")
    ]
    if file_args:
        all_ok = True
        for arg in file_args:
            if sweep_v2_mode:
                all_ok = all_ok and validate_v2_sweep_path(arg)
            else:
                all_ok = all_ok and validate_path(pathlib.Path(arg), sweep_record=sweep_mode)
        sys.exit(0 if all_ok else 1)
    sys.exit(0 if validate_discovery(pathlib.Path(".").resolve()) else 1)


if __name__ == "__main__":
    main()
