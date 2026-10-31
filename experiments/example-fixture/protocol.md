# Protocol: example-fixture

Pre-registered before any run. Do not modify after data collection begins;
changes require a new experiment slug.

- Task: single-turn instruction-following prompt answered by the model under test.
- Groups: `control` receives standard instructions; `treatment` receives modified instructions.
- Sample size: 5 runs per group (`n_per_group`).
- Statistical test: Fisher exact test on pass/fail counts (`statistical_test: fisher-exact`).
- Scoring: blind rubric scoring against `scorer-prompt.md`; results in `scores.json`.
- Threats to validity: small sample size (see `pre_acknowledged_limitations` in `analysis.json`).
