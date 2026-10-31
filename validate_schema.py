"""
Validate schema of experiment analysis.json files.

Checks that every experiments/*/analysis.json contains the required
top-level fields with correct scalar types, ISO date/timestamp formats,
enum values, token totals consistency, a well-formed scores object, and
that the `experiment` field matches the parent directory slug. Certain
fields are nullable (allowed to be null) while others must have values.

Usage:
    uv run python validate_schema.py [--self-test] [FILE ...]

With no FILE arguments, discovers and validates all
experiments/*/analysis.json files under the repository root.

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


def validate_path(path):
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
    # Discovery mode: missing analysis.json must fail, empty experiments/ passes.
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        missing = base / "experiments" / "exp-missing"
        missing.mkdir(parents=True)
        present = base / "experiments" / "exp-present"
        present.mkdir()
        record = _load_json_strict(json.dumps(MINIMAL_VALID_RECORD))
        record["experiment"] = "exp-present"
        (present / "analysis.json").write_text(json.dumps(record))
        if validate_discovery(base):
            print("self-test FAILED: discovery accepted missing analysis.json")
            return False
        empty_base = pathlib.Path(tempfile.mkdtemp())
        try:
            (empty_base / "experiments").mkdir()
            if not validate_discovery(empty_base):
                print("self-test FAILED: discovery rejected empty experiments dir")
                return False
        finally:
            shutil.rmtree(empty_base)
    print(
        "self-test passed: valid record accepted, each rule rejects its invalid case, discovery flags missing analysis.json"
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
            print(f"Validation error: missing {analysis}")
            all_ok = False
            continue
        if not validate_path(analysis):
            all_ok = False
    return all_ok


def main():
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    file_args = [arg for arg in sys.argv[1:] if arg != "--self-test"]
    if file_args:
        all_ok = all(validate_path(pathlib.Path(arg)) for arg in file_args)
        sys.exit(0 if all_ok else 1)
    sys.exit(0 if validate_discovery(pathlib.Path(".").resolve()) else 1)


if __name__ == "__main__":
    main()
