# Contributing

Thanks for contributing to {{REPO_NAME}}. This repository hosts pre-registered experiments; the rules below exist to keep results trustworthy.

## Pre-Registration Requirement

Before running any experiment, commit `experiments/<slug>/protocol.md`, `runner-prompt.md`, and `scorer-prompt.md` describing the task, groups, sample size, rubric, and statistical test. The pre-registration commit must precede the first run. Post-hoc protocol edits require a dated addendum, never a silent rewrite.

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
4. Score blind against the rubric; write `scores.json` and `analysis.json`.
5. Validate, then update the experiment index table in [README.md](README.md).

## General Guidelines

- Conventional Commits are enforced by commitlint in CI.
- Large binary artifacts do not belong in git; summarize or reference them.
- Security-relevant files under `.github/` require review from `@clouatre-labs/security-reviewers` (see `CODEOWNERS`).
- See [AI_POLICY.md](AI_POLICY.md) for the AI-assisted contribution policy.
