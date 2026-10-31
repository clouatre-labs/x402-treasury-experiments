# Example Fixture

This directory is a complete, minimal pre-registration scaffold and a live CI
fixture. CI runs `uv run python validate_schema.py`, which iterates every
`experiments/*/` directory; without this directory the schema check would pass
vacuously. Copy this layout (do not edit it in place) when starting a real
experiment.

- `protocol.md`: pre-registered design, committed before any run
- `runner-prompt.md`: exact prompt given to the runner/agent
- `scorer-prompt.md`: exact prompt given to the scorer
- `analysis.json`: run metadata and scores (schema in `DATA_DICTIONARY.md`)
- `scores.json`: per-criterion rubric scores with justifications
- `sessions/`: raw session logs or database exports (empty in the fixture)

The `analysis.json` here is the minimal valid record; it must keep
`experiment` equal to the directory slug (`example-fixture`) or CI fails.
