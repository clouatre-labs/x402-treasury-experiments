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

Added after the sealed pass, following the
`figures/usdc_fiat_sweep_hop_latency_clean.py` precedent: styled SVG plus a
white-background PNG render (the PNG is what the docs embed, since directly
embedded transparent SVGs are unreadable on GitHub dark mode). They read
only the committed records plus the pre-registered advertised schedule
constants from `protocol.md`:

- **Realized vs advertised fee rate per tranche** (post-hoc, not
  preregistered): common 0-0.6% rate axis, not-executed Arm B rows rendered
  as greyed structural exclusions (`figures/usdc_fiat_sweep_v2_rate_comparison.py`).
- **Realized exchange fee per executed transaction (USD)**: same content as
  the frozen fig1 recipe's SVG, in the dark-mode-safe house style
  (`figures/usdc_fiat_sweep_v2_cost_per_tx.py`). The frozen recipe and its
  SVG remain untouched as a pipeline artifact, not embedded.
