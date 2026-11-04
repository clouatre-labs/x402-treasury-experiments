"""Figure (post-hoc, not preregistered): realized vs advertised fee rate per
tranche for the usdc-fiat-sweep-v2 experiment.

This script was written after the sealed execution pass (the pre-registered
recipe set contains only fig1). It reads the same committed run records and
adds what fig1 cannot show at mixed tranche sizes: the rate-level comparison
(realized fee % against the advertised schedule), the not-executed Arm B
rows rendered as greyed structural exclusions, and the post-crash spread
observation per executed tranche. All numbers come from the records; the
advertised schedule constants (Kraken stablecoin 0.20% taker, Coinbase
convert 0%, EFT 0.35%) are pre-registered in protocol.md, following the v1
recipe's ADVERTISED_FIXED_FEE_USD precedent.

Usage:
    uv run python recipe/usdc_fiat_sweep_v2_fig2_rate_comparison.py \
        --records <dir-with-6-records-only> \
        [--out figures/usdc_fiat_sweep_v2_fig2_realized_vs_advertised.svg]
"""
import argparse
import json
import pathlib

W, H = 640, 400
M_L, M_R, M_T, M_B = 150, 16, 40, 60
# Advertised schedule, pre-registered in protocol.md (not measured here).
ADVERTISED_PCT = {
    "kraken-10": 0.20,
    "kraken-residue": 0.20,
    "coinbase-5-1": 0.0,
    "coinbase-5-2": 0.0,
    "cad-20": 0.55,  # 0.20% exchange + 0.35% EFT disbursement
    "cad-eft": 0.35,
}
REALIZED_BLUE = "#2563eb"
ADVERTISED_GRAY = "#9ca3af"
NOT_EXECUTED_GRAY = "#d1d5db"


def load_records(record_dir):
    records = []
    for path in sorted(record_dir.glob("*.json")):
        record = json.loads(path.read_text())
        if "executed" not in record:
            continue
        records.append(record)
    return records


def svg_open(title):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" '
        'viewBox="0 0 640 400" style="background:transparent">\n'
        f"  <title>{title}</title>\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Post-hoc figure: realized vs advertised fee rate per tranche (usdc-fiat-sweep-v2)"
    )
    parser.add_argument("--records", type=pathlib.Path, required=True,
                        help="directory containing run-record JSON files")
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("figures/usdc_fiat_sweep_v2_fig2_realized_vs_advertised.svg"))
    args = parser.parse_args()

    records = load_records(args.records)
    assert len(records) == 6, f"expected 6 run records, found {len(records)}"
    records.sort(key=lambda r: ["kraken-10", "kraken-residue", "coinbase-5-1",
                                 "coinbase-5-2", "cad-20", "cad-eft"].index(r["tranche_id"]))

    bar_h, gap, group_w = 14, 6, 9
    plot_w = W - M_L - M_R
    # Rate scale: 0 to 0.6% covers the largest advertised rate (0.55%).
    max_pct = 0.6

    body = [
        f'  <text x="{W / 2}" y="24" text-anchor="middle" font-size="16" '
        f'font-family="sans-serif">Realized vs advertised fee rate per tranche</text>',
        # x-axis ticks at 0, 0.2, 0.4, 0.6 percent
    ]
    for tick in (0.0, 0.2, 0.4, 0.6):
        x = M_L + tick / max_pct * plot_w
        body.append(
            f'  <text x="{x:.1f}" y="{H - 40}" text-anchor="middle" font-size="10" '
            f'font-family="sans-serif" fill="#374151">{tick:.1f}%</text>'
        )
        body.append(
            f'  <line x1="{x:.1f}" y1="{M_T}" x2="{x:.1f}" y2="{H - 46}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
        )

    rows = []
    for r in records:
        tid = r["tranche_id"]
        executed = r["executed"]
        realized = r.get("realized_fee_pct")
        spread = r.get("spread_vs_mid_pct")
        note = r.get("execution_status")
        rows.append((tid, executed, realized, spread, note))

    for i, (tid, executed, realized, spread, status) in enumerate(rows):
        y = M_T + 6 + i * (bar_h * 2 + gap + 8)
        body.append(
            f'  <text x="{M_L - 8}" y="{y + bar_h}" text-anchor="end" font-size="11" '
            f'font-family="sans-serif">{tid}</text>'
        )
        # advertised bar
        adv_w = max(1.0, ADVERTISED_PCT[tid] / max_pct * plot_w)
        y2 = y + bar_h + 4
        if executed and realized is not None:
            body.append(
                f'  <rect x="{M_L}" y="{y}" width="{adv_w:.1f}" height="{bar_h}" '
                f'fill="{ADVERTISED_GRAY}"/>'
            )
            adv_label = f"advertised {ADVERTISED_PCT[tid]:.2f}%"
            body.append(
                f'  <text x="{M_L + adv_w + 6:.1f}" y="{y + bar_h / 2 + 4}" font-size="10" '
                f'font-family="sans-serif" fill="#6b7280">{adv_label}</text>'
            )
            # realized bar (grouped below advertised)
            real_w = max(1.0, realized / max_pct * plot_w)
            body.append(
                f'  <rect x="{M_L}" y="{y2}" width="{real_w:.1f}" height="{bar_h}" fill="{REALIZED_BLUE}"/>'
            )
            label = f"realized {realized:.4f}%"
            if spread is not None:
                label += f" (spread {spread:+.4f}%, post-crash obs)"
            body.append(
                f'  <text x="{M_L + real_w + 6:.1f}" y="{y2 + bar_h / 2 + 4}" font-size="10" '
                f'font-family="sans-serif">{label}</text>'
            )
        else:
            # structural exclusion: greyed advertised bar, annotated inside; no realized bar
            body.append(
                f'  <rect x="{M_L}" y="{y}" width="{adv_w:.1f}" height="{bar_h}" '
                f'fill="{NOT_EXECUTED_GRAY}"/>'
            )
            body.append(
                f'  <text x="{M_L + 6}" y="{y + bar_h / 2 + 4}" font-size="10" '
                f'font-family="sans-serif" fill="#374151">advertised {ADVERTISED_PCT[tid]:.2f}% '
                f"— not executed ({status})</text>"
            )
            body.append(
                f'  <rect x="{M_L}" y="{y2}" width="1" height="{bar_h}" fill="{NOT_EXECUTED_GRAY}"/>'
            )

    body.append(
        f'  <rect x="{M_L}" y="{H - 28}" width="10" height="10" fill="{REALIZED_BLUE}"/>'
        f'<text x="{M_L + 16}" y="{H - 19}" font-size="10" font-family="sans-serif">realized</text>'
        f'<rect x="{M_L + 80}" y="{H - 28}" width="10" height="10" fill="{ADVERTISED_GRAY}"/>'
        f'<text x="{M_L + 96}" y="{H - 19}" font-size="10" font-family="sans-serif">advertised</text>'
        f'<rect x="{M_L + 180}" y="{H - 28}" width="10" height="10" fill="{NOT_EXECUTED_GRAY}"/>'
        f'<text x="{M_L + 196}" y="{H - 19}" font-size="10" font-family="sans-serif">'
        f'structural exclusion (not executed)</text>'
    )
    body.append(
        f'  <text x="{W / 2}" y="{H - 6}" text-anchor="middle" font-size="9" '
        f'font-family="sans-serif" fill="#6b7280">Post-hoc figure (not preregistered). '
        f'Single pass, n=1 per tranche; no uncertainty is estimable.</text>'
    )

    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg_open("Realized vs advertised fee rate per tranche, usdc-fiat-sweep-v2")
                   + "\n".join(body) + "\n</svg>\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
