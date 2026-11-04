#!/usr/bin/env python3
"""Figure: realized vs advertised fee rate per tranche, usdc-fiat-sweep-v2.

Supplementary figure, generated outside the frozen recipe/ pipeline (which
is sealed post-execution). Post-hoc (not preregistered): reads the committed
run records plus the pre-registered advertised schedule constants from
protocol.md, and plots realized fee rate against the advertised rate per
tranche on a common 0-0.6% axis, with the not-executed Arm B tranches
rendered as greyed structural exclusions rather than omitted. Same style as
usdc_fiat_sweep_hop_latency_clean.py (explicit fills, rendered to a white-
background PNG; the transparent SVG is never embedded directly because
GitHub dark mode renders unstyled text unreadably).

Single pass, n=1 per tranche: no uncertainty is estimable, so no error bars
are drawn. Quote context (spread) was re-observed post-recovery; see the
records' notes.

Usage: uv run python figures/usdc_fiat_sweep_v2_rate_comparison.py
"""

import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent
RECORDS = HERE.parent / "experiments" / "usdc-fiat-sweep-v2" / "sessions"

# protocol tranche order
ORDER = ["kraken-10", "kraken-residue", "coinbase-5-1", "coinbase-5-2",
         "cad-20", "cad-eft"]
# pre-registered advertised schedule, protocol.md (not measured here)
ADVERTISED_PCT = {
    "kraken-10": 0.20,
    "kraken-residue": 0.20,
    "coinbase-5-1": 0.0,
    "coinbase-5-2": 0.0,
    "cad-20": 0.55,  # 0.20% exchange + 0.35% EFT disbursement
    "cad-eft": 0.35,
}
MAX_PCT = 0.6
TICKS = [0.0, 0.2, 0.4, 0.6]


def main():
    data = []
    for tranche in ORDER:
        record = json.loads((RECORDS / f"{tranche}.json").read_text())
        data.append((
            tranche,
            record["executed"],
            record.get("realized_fee_pct"),
            ADVERTISED_PCT[tranche],
            record.get("execution_status"),
        ))

    W, H = 640, 0  # H computed from content below
    M_L, M_R, M_T = 138, 96, 40
    bar_h = 11
    pair_gap = 3
    row_gap = 14
    plot_w = W - M_L - M_R
    scale = plot_w / MAX_PCT

    def X(v):
        return M_L + v * scale

    parts = []
    y = M_T
    for tranche, executed, realized, adv, status in data:
        parts.append(
            f'  <text x="{M_L - 10}" y="{y + bar_h + 2}" text-anchor="end" '
            f'class="label">{tranche}</text>'
        )
        # advertised bar
        adv_w = max(1.5, adv / MAX_PCT * plot_w)
        if executed and realized is not None:
            parts.append(
                f'  <rect x="{M_L}" y="{y}" width="{adv_w:.1f}" height="{bar_h}" rx="2" class="adv"/>'
            )
            # realized bar directly below
            y2 = y + bar_h + pair_gap
            real_w = max(1.5, realized / MAX_PCT * plot_w)
            parts.append(
                f'  <rect x="{M_L}" y="{y2}" width="{real_w:.1f}" height="{bar_h}" rx="2" class="mark"/>'
                f'\n  <text x="{X(realized) + 8:.1f}" y="{y2 + bar_h / 2 + 4}" class="value">'
                f'{realized:.4f}%</text>'
            )
        else:
            # structural exclusion: greyed advertised bar, cause annotated inside
            parts.append(
                f'  <rect x="{M_L}" y="{y}" width="{adv_w:.1f}" height="{bar_h}" rx="2" class="excl"/>'
                f'\n  <text x="{M_L + 8}" y="{y + bar_h / 2 + 4}" class="exclnote">'
                f'not executed ({status})</text>'
            )
        y += bar_h * 2 + pair_gap + row_gap

    grid = []
    GRID_BOTTOM = y + 18
    TICK_Y = GRID_BOTTOM + 16
    for t in TICKS:
        grid.append(
            f'  <line x1="{X(t):.1f}" y1="{M_T}" x2="{X(t):.1f}" y2="{GRID_BOTTOM}" '
            f'class="grid"/>'
            f'\n  <text x="{X(t):.1f}" y="{TICK_Y}" text-anchor="middle" '
            f'class="tick">{t:.1f}%</text>'
        )

    legend_y = TICK_Y + 24
    NOTES = [
        "Post-hoc, not preregistered. Single pass, n=1 per tranche;",
        "no uncertainty is estimable.",
        "Advertised: Kraken 0.20% taker; Coinbase convert 0%;",
        "EFT +0.35% (cad-20 = 0.20% + 0.35%).",
    ]
    notes = []
    ny = legend_y + 34
    for line in NOTES:
        notes.append(f'  <text x="{M_L}" y="{ny}" class="note">{line}</text>')
        ny += 17
    H = ny + 10
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Realized vs advertised fee rate per tranche, usdc-fiat-sweep-v2">
  <style>
    text {{ font-family: ui-monospace, Menlo, monospace; }}
    .title {{ font-size: 14px; font-weight: 600; fill: #18181b; }}
    .label {{ font-size: 13px; fill: #18181b; }}
    .value {{ font-size: 12px; fill: #18181b; }}
    .tick {{ font-size: 12px; fill: #52525b; }}
    .grid {{ stroke: #e4e4e7; stroke-width: 1; }}
    .note {{ font-size: 12px; fill: #52525b; }}
    .exclnote {{ font-size: 12px; fill: #52525b; }}
    .mark {{ fill: #075985; }}
    .adv {{ fill: #94a3b8; }}
    .excl {{ fill: #e4e4e7; }}
    .swatch {{ font-size: 12px; fill: #18181b; }}
  </style>
  <text x="{W / 2}" y="24" text-anchor="middle" class="title">Realized vs advertised fee rate per tranche</text>
{chr(10).join(grid)}
{chr(10).join(parts)}
  <rect x="{M_L}" y="{legend_y}" width="12" height="12" rx="2" class="mark"/>
  <text x="{M_L + 18}" y="{legend_y + 11}" class="swatch">realized</text>
  <rect x="{M_L + 110}" y="{legend_y}" width="12" height="12" rx="2" class="adv"/>
  <text x="{M_L + 128}" y="{legend_y + 11}" class="swatch">advertised</text>
  <rect x="{M_L + 230}" y="{legend_y}" width="12" height="12" rx="2" class="excl"/>
  <text x="{M_L + 248}" y="{legend_y + 11}" class="swatch">structural exclusion</text>
{chr(10).join(notes)}
</svg>
'''

    svg_path = HERE / "usdc_fiat_sweep_v2_rate_comparison.svg"
    svg_path.write_text(svg)
    print(f"wrote {svg_path}")
    subprocess.run(
        [
            "rsvg-convert", "-z", "2", "-b", "#ffffff",
            "-o", str(HERE / "usdc_fiat_sweep_v2_rate_comparison.png"),
            str(svg_path),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
