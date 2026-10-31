# Methodology

Experimental design and analysis plan for experiments in this repository. Replace each `TODO` section per experiment; keep this top-level document as the shared methodological contract.

## Research Question

TODO: State the hypothesis or question the repo's experiments address. Frame it so a null result is still informative.

## Pre-Registration

Every experiment MUST have its protocol, rubric, and scoring prompts committed under `experiments/<slug>/` BEFORE any session is run. The commit containing the pre-registration must precede the first run record; edits after data collection begins require a dated addendum in the experiment's `protocol.md`.

- Rubric criteria are defined before examining any model output.
- Group assignments are sealed in `label-map.json` before scoring begins.
- Statistical tests are named in the protocol before data collection.

## Experimental Design

TODO: Describe per experiment:

- Task and target (issue, dataset, or benchmark used).
- Groups: control and treatment conditions, with exact prompt text or deltas.
- Sample size per group and stopping rule.
- Agent or model configuration (model, temperature, provider, extensions).

## Blind Scoring

Scorers receive only the output artifacts and the rubric. No group labels, run metadata, or sibling outputs are visible during scoring. Report any inter-rater reliability checks and their agreement statistics.

## Analysis Plan

Analysis results land in `experiments/<slug>/analysis.json` (schema in [DATA_DICTIONARY.md](DATA_DICTIONARY.md), enforced by `validate_schema.py`). Scores with per-criterion justifications land in `scores.json`. Figures are generated from `recipe/` scripts into `figures/`.

## Threats to Validity

TODO: Enumerate, at minimum:

- Ceiling or floor effects in the rubric.
- Rubric-scorer co-design bias.
- Run-to-run variance and seed/provider nondeterminism.
- Contamination of the task in model training data.
