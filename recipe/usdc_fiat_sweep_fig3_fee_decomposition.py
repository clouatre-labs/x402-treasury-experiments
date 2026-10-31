"""Figure 3: fee decomposition per tranche (fixed fee, percentage fee,
spread).

Reads usdc-fiat-sweep run records (default: experiments/usdc-fiat-sweep/sessions/,
override with --records) and writes an SVG in the house chart style.

Decomposition per tranche: fixed fee (quoted), spread cost
(amount * spread_vs_mid_pct / 100), and network fee (shared across the
experiment's single pre-funding transfer; shown as its own component).
"""
from usdc_fiat_sweep_common import load_records, parse_args, write_svg

W, H = 640, 400
M_L, M_R, M_T, M_B = 90, 16, 40, 90


def main():
    args = parse_args("Figure 3: fee decomposition per tranche")
    records = [r for r in load_records(args.records, args.include_synthetic) if r["amount_usdc"] is not None]
    assert records, "no executed run records found"
    rows = sorted(
        (
            r["tranche_id"],
            r["fixed_fee_usd"],
            r["amount_usdc"] * r["spread_vs_mid_pct"] / 100,
            r["network_fee_usd"] or 0.0,
        )
        for r in records
    )

    bar_h, gap = 14, 10
    plot_w = W - M_L - M_R
    max_cost = max(f + s + n for _, f, s, n in rows)

    body = [
        f'  <text x="{W / 2}" y="24" text-anchor="middle" font-size="16" '
        f'font-family="sans-serif">Fixed fee dominates cost at micropayment scale</text>'
    ]
    y = M_T
    for label, fixed, spread, net in rows:
        total = fixed + spread + net
        wf, ws, wn = (fixed / max_cost * plot_w, spread / max_cost * plot_w,
                      net / max_cost * plot_w)
        body.append(
            f'  <text x="{M_L - 8}" y="{y + bar_h}" text-anchor="end" font-size="11" '
            f'font-family="sans-serif">{label}</text>'
            f'  <rect x="{M_L}" y="{y}" width="{wf:.1f}" height="{bar_h}" fill="#1a6ee0"/>'
            f'  <rect x="{M_L + wf:.1f}" y="{y}" width="{ws:.1f}" height="{bar_h}" fill="#e08a1a"/>'
            f'  <rect x="{M_L + wf + ws:.1f}" y="{y}" width="{wn:.1f}" height="{bar_h}" fill="#4aa15a"/>'
            f'  <text x="{M_L + wf + ws + wn + 6:.1f}" y="{y + bar_h}" font-size="11" '
            f'font-family="sans-serif">${total:.3f}</text>'
        )
        y += bar_h + gap
    legend = [
        ("#1a6ee0", "fixed fee", 0),
        ("#e08a1a", "spread cost", 130),
        ("#4aa15a", "network fee", 250),
    ]
    for color, text, dx in legend:
        body.append(
            f'  <rect x="{M_L + dx}" y="{H - M_B + 34}" width="12" height="12" fill="{color}"/>'
            f'  <text x="{M_L + dx + 18}" y="{H - M_B + 44}" font-size="11" '
            f'font-family="sans-serif">{text}</text>'
        )
    body.append(
        f'  <text x="{(M_L + W - M_R) / 2}" y="{H - 8}" text-anchor="middle" '
        f'font-size="12" font-family="sans-serif">USD cost per tranche (stacked)</text>'
    )
    write_svg(args, "usdc_fiat_sweep_fig3_fee_decomposition.svg", "\n".join(body),
              "Fee decomposition per tranche: fixed fee, spread, network fee")


if __name__ == "__main__":
    main()
