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
