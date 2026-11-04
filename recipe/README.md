# Recipes

Analysis recipes (notebooks, scripts) that regenerate figures from experiment data live here. Figures are generated only from these scripts into `figures/`.

## Planned Figures (usdc-fiat-sweep)

To be generated after the run completes:

- **Figure 1 (primary):** realized fee vs tranche amount, with the advertised Coinbase fee schedule overlaid.
- **Figure 2:** per-hop latency (on-chain send, Coinbase credit, fiat spendable) per tranche.
- **Figure 3:** fee decomposition per tranche (fixed fee, percentage fee, spread).

All figures follow the clouatre.ca house chart style: transparent background, 640px viewBox, declarative titles.

## Planned Figures (usdc-fiat-sweep-api)

To be generated after the run completes; the same three scripts, pointed at `experiments/usdc-fiat-sweep-api/sessions/` (`--records experiments/usdc-fiat-sweep-api/sessions`):

- **Figure 1 (primary):** realized fee vs tranche amount, with the published Coinbase Advanced Trade taker fee schedule overlaid (schedule values recorded verbatim at execution time).
- **Figure 2:** per-hop latency (on-chain send on Base, Coinbase credit/convert fill, fiat or USD balance spendable) per tranche.
- **Figure 3:** fee decomposition per tranche (fixed fee, percentage fee, spread vs USDC mid).

## Post-hoc Figures (usdc-fiat-sweep-v2)

Added after the sealed pass (the pre-registration recipe set contains fig1
only); reads the committed records plus the pre-registered advertised
schedule constants from `protocol.md`:

- **Figure 2 (post-hoc, not preregistered):** realized fee rate vs
  advertised rate per tranche on a common 0-0.6% axis, with the
  not-executed Arm B rows greyed as structural exclusions
  (`usdc_fiat_sweep_v2_fig2_rate_comparison.py`, same `--records`
  indirection as fig1).

Post-pass cosmetic layout fix (2026-11-04, disclosed): fig1's per-bar value
labels are now anchored inside the bar end when they would otherwise clip at
the canvas edge; label content (the record-derived fee) is unchanged.
