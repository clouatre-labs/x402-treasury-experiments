#!/usr/bin/env python3
"""Figure: send-to-spendable latency for the three clean tranches.

Supplementary figure, generated outside the frozen recipe/ pipeline (which is
sealed post-execution): reads the committed run records, plots send-to-spendable
latency ONLY for the tranches whose credit timestamps are genuine fill moments
(level20-2, level100-1, full-1), and writes a dark-mode-adaptive SVG plus a
white-background PNG render.

The five earlier tranches (level1-1, level1-2, level5-1, level5-2, level20-1)
are excluded: their timestamp_coinbase_credit values are recovery-time
artifacts of the level1-1 remediation, not fill moments (see METHODOLOGY.md,
Execution Deviations).

Usage: uv run python figures/usdc_fiat_sweep_hop_latency_clean.py
"""

import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent
RECORDS = HERE.parent / "experiments" / "usdc-fiat-sweep-api" / "sessions"
CLEAN = ["level20-2", "level100-1", "full-1"]
AMOUNTS = {"level20-2": "$20", "level100-1": "$100", "full-1": "$5.26 residual"}


def hms(seconds):
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def main():
    pts = []
    for tranche in CLEAN:
        record = json.loads((RECORDS / f"{tranche}.json").read_text())
        sent = record["timestamp_sent"]
        credit = record["timestamp_coinbase_credit"]
        # both ISO-8601 UTC; seconds resolution
        from datetime import datetime

        t0 = datetime.fromisoformat(sent.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(credit.replace("Z", "+00:00"))
        pts.append((tranche, int((t1 - t0).total_seconds())))
    pts.sort(key=lambda p: -p[1])
    assert pts == [("level100-1", 263), ("level20-2", 236), ("full-1", 5)], pts

    W, H = 640, 240
    M_L, M_R, M_T, M_B = 226, 96, 40, 34
    bar_h = 26
    gap = 16
    max_v = max(v for _, v in pts)
    scale = (W - M_L - M_R) / max_v

    def X(v):
        return M_L + v * scale

    rows = []
    y = M_T
    for name, v in pts:
        rows.append(
            f'  <text x="{M_L - 10}" y="{y + bar_h / 2 + 4}" text-anchor="end" '
            f'class="label">{name} ({AMOUNTS[name]})</text>'
            f'\n  <rect x="{M_L}" y="{y}" width="{X(v) - M_L:.1f}" height="{bar_h}" rx="3" class="mark"/>'
            f'\n  <text x="{X(v) + 8:.1f}" y="{y + bar_h / 2 + 4}" class="value">{hms(v)}</text>'
        )
        y += bar_h + gap

    note_y = y + 4
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Send-to-spendable latency for the three clean tranches">
  <style>
    text {{ font-family: ui-monospace, Menlo, monospace; }}
    .title {{ font-size: 14px; font-weight: 600; fill: #18181b; }}
    .label {{ font-size: 13px; fill: #18181b; }}
    .value {{ font-size: 13px; fill: #18181b; }}
    .note {{ font-size: 12px; fill: #52525b; }}
    .mark {{ fill: #075985; }}
  </style>
  <text x="{W / 2}" y="24" text-anchor="middle" class="title">Fiat lands spendable within five minutes of the send</text>
{chr(10).join(rows)}
  <text x="{M_L}" y="{note_y}" class="note">Clean tranches only: the five earlier tranches' credit</text>
  <text x="{M_L}" y="{note_y + 16}" class="note">timestamps are recovery-time artifacts (METHODOLOGY.md).</text>
</svg>
'''

    svg_path = HERE / "usdc_fiat_sweep_hop_latency_clean.svg"
    svg_path.write_text(svg)
    print(f"wrote {svg_path}")
    subprocess.run(
        [
            "rsvg-convert", "-z", "2", "-b", "#ffffff",
            "-o", str(HERE / "usdc_fiat_sweep_hop_latency_clean.png"),
            str(svg_path),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
