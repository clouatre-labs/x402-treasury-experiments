# Contributing

Thanks for contributing to x402-treasury-experiments. This repository hosts pre-registered experiments; the rules below exist to keep results trustworthy.

## Pre-Registration Requirement

Before running any experiment, commit `experiments/<slug>/protocol.md` describing the task, groups, sample size, and statistical test. The pre-registration commit must precede the first run. Post-hoc protocol edits require a dated addendum, never a silent rewrite.

The remaining artifacts depend on the experiment type. LLM experiments additionally commit `runner-prompt.md` and `scorer-prompt.md`, are executed via the runner, and are scored blind against the rubric. Measurement experiments additionally commit `runbook.md` and `record-extraction.md`, are executed by a human operator in a single pass, and are transcribed verbatim from raw artifacts.

## Schema Validation

Every experiment must contain a valid `analysis.json` (schema in [DATA_DICTIONARY.md](DATA_DICTIONARY.md)). Run the validator before opening a PR:

```bash
uv run python validate_schema.py
```

CI runs the same validator in self-test mode; a PR whose `analysis.json` files fail validation will not merge.

## Adding an Experiment

1. Create `experiments/<slug>/` following the layout in [experiments/README.md](experiments/README.md).
2. Commit the pre-registration artifacts.
3. Run the experiment; store raw session artifacts under `sessions/`.
4. LLM experiments: score blind against the rubric; write `scores.json` and `analysis.json`. Measurement experiments: transcribe raw artifacts per `record-extraction.md`; write `analysis.json`.
5. Validate, then update the experiment index table in [README.md](README.md).

## General Guidelines

- Conventional Commits are enforced by commitlint in CI.
- Large binary artifacts do not belong in git; summarize or reference them.
- Security-relevant files under `.github/` require review from `@clouatre-labs/security-reviewers` (see `CODEOWNERS`).
- See [AI_POLICY.md](AI_POLICY.md) for the AI-assisted contribution policy.
