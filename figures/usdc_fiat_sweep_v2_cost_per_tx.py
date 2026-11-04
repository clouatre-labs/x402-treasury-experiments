#!/usr/bin/env python3
"""Figure: realized cost per transaction for the usdc-fiat-sweep-v2 pass.

Supplementary figure, generated outside the frozen recipe/ pipeline (which
is sealed post-execution): reads the committed run records and plots the
realized exchange fee per executed tranche in USD, in the same dark-mode-
adaptive style as usdc_fiat_sweep_hop_latency_clean.py (explicit fills,
rendered to a white-background PNG; the transparent SVG is never embedded
directly because GitHub dark mode renders unstyled text unreadably).

Not-executed tranches are excluded from the bars here; the rate-level
figure (usdc_fiat_sweep_v2_rate_comparison.py) renders them as structural
exclusions.

Usage: uv run python figures/usdc_fiat_sweep_v2_cost_per_tx.py
"""

import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent
RECORDS = HERE.parent / "experiments" / "usdc-fiat-sweep-v2" / "sessions"
# protocol tranche order
ORDER = ["kraken-10", "kraken-residue", "coinbase-5-1", "coinbase-5-2"]
ADVERTISED_NOTE = (
    "Advertised: Kraken stablecoin 0.20% taker; Coinbase convert 0%."
)


def main():
    rows = []
    for tranche in ORDER:
        record = json.loads((RECORDS / f"{tranche}.json").read_text())
        assert record["executed"] and record["execution_status"] == "clean_fill"
        fee = record["fixed_fee_usd"] + (record.get("network_fee_usd") or 0)
        rows.append((tranche, fee))
    # ascending fee order like the v1 latency chart (largest on top reads
    # naturally in a horizontal bar chart)
    rows.sort(key=lambda r: -r[1])

    W, H = 640, 280
    M_L, M_R, M_T, M_B = 150, 110, 40, 34
    bar_h = 26
    gap = 16
    max_v = max(v for _, v in rows)
    scale = (W - M_L - M_R) / max_v

    def X(v):
        return M_L + v * scale

    parts = []
    y = M_T
    for name, v in rows:
        parts.append(
            f'  <text x="{M_L - 10}" y="{y + bar_h / 2 + 4}" text-anchor="end" '
            f'class="label">{name}</text>'
            f'\n  <rect x="{M_L}" y="{y}" width="{X(v) - M_L:.1f}" height="{bar_h}" rx="3" class="mark"/>'
            f'\n  <text x="{X(v) + 8:.1f}" y="{y + bar_h / 2 + 4}" class="value">${v:.4f}</text>'
        )
        y += bar_h + gap

    note_y = y + 4
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Realized cost per transaction against the advertised schedule, usdc-fiat-sweep-v2">
  <style>
    text {{ font-family: ui-monospace, Menlo, monospace; }}
    .title {{ font-size: 14px; font-weight: 600; fill: #18181b; }}
    .label {{ font-size: 13px; fill: #18181b; }}
    .value {{ font-size: 13px; fill: #18181b; }}
    .note {{ font-size: 12px; fill: #52525b; }}
    .mark {{ fill: #075985; }}
  </style>
  <text x="{W / 2}" y="24" text-anchor="middle" class="title">Realized exchange fee per transaction (USD)</text>
{chr(10).join(parts)}
  <text x="{M_L}" y="{note_y}" class="note">{ADVERTISED_NOTE}</text>
  <text x="{M_L}" y="{note_y + 16}" class="note">Executed tranches only; not-executed Arm B rows are structural</text>
  <text x="{M_L}" y="{note_y + 32}" class="note">exclusions (see the rate-comparison figure).</text>
</svg>
'''

    svg_path = HERE / "usdc_fiat_sweep_v2_cost_per_tx.svg"
    svg_path.write_text(svg)
    print(f"wrote {svg_path}")
    subprocess.run(
        [
            "rsvg-convert", "-z", "2", "-b", "#ffffff",
            "-o", str(HERE / "usdc_fiat_sweep_v2_cost_per_tx.png"),
            str(svg_path),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
