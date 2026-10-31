"""Figure 1: realized fee vs tranche amount, with the advertised Coinbase
fee schedule overlaid.

Reads usdc-fiat-sweep run records (default: experiments/usdc-fiat-sweep/sessions/,
override with --records) and writes an SVG in the house chart style:
transparent background, 640px viewBox, declarative title.
"""
from usdc_fiat_sweep_common import (ADVERTISED_FIXED_FEE_USD, load_records,
                                    parse_args, write_svg)

W, H = 640, 400
M_L, M_R, M_T, M_B = 56, 16, 40, 48


def main():
    args = parse_args("Figure 1: realized fee vs tranche amount")
    records = [r for r in load_records(args.records, args.include_synthetic) if r["amount_usdc"] is not None]
    assert records, "no executed run records found"
    pts = sorted((r["amount_usdc"], r["realized_fee_pct"]) for r in records)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = 0, max(xs) * 1.05
    y0, y1 = 0, max(max(ys), ADVERTISED_FIXED_FEE_USD / min(xs) * 100) * 1.1

    def X(v):
        return M_L + (v - x0) / (x1 - x0) * (W - M_L - M_R)

    def Y(v):
        return H - M_B - (v - y0) / (y1 - y0) * (H - M_T - M_B)

    body = [
        # declarative title
        f'  <text x="{W / 2}" y="24" text-anchor="middle" font-size="16" '
        f'font-family="sans-serif">Realized fee falls as tranche amount grows</text>',
        f'  <line x1="{M_L}" y1="{H - M_B}" x2="{W - M_R}" y2="{H - M_B}" stroke="#333"/>',
        f'  <line x1="{M_L}" y1="{M_T}" x2="{M_L}" y2="{H - M_B}" stroke="#333"/>',
    ]
    # advertised schedule overlay: pct = fixed / amount * 100
    a0 = ADVERTISED_FIXED_FEE_USD / x1 * 100
    body.append(
        f'  <line x1="{X(min(xs))}" y1="{Y(a0)}" x2="{X(x1)}" y2="{Y(a0 * min(xs) / x1)}" '
        f'stroke="#888" stroke-dasharray="4 4"/>'
        f'  <text x="{X(x1)}" y="{Y(a0 * min(xs) / x1) - 6}" text-anchor="end" '
        f'font-size="11" fill="#666" font-family="sans-serif">'
        f"advertised schedule (${ADVERTISED_FIXED_FEE_USD:.2f} fixed)</text>"
    )
    for x, y in pts:
        body.append(
            f'  <circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4" fill="#1a6ee0"/>'
            f'  <text x="{X(x):.1f}" y="{H - M_B + 16}" text-anchor="middle" '
            f'font-size="11" font-family="sans-serif">${x:g}</text>'
            f'  <text x="{X(x):.1f}" y="{Y(y):.1f} - 8" text-anchor="middle" '
            f'font-size="11" fill="#1a6ee0" font-family="sans-serif">{y:g}%</text>'
        )
    body.append(
        f'  <text x="12" y="{H / 2}" font-size="12" font-family="sans-serif" '
        f'transform="rotate(-90 12 {H / 2})" text-anchor="middle">realized fee (%)</text>'
        f'  <text x="{(M_L + W - M_R) / 2}" y="{H - 8}" text-anchor="middle" '
        f'font-size="12" font-family="sans-serif">tranche amount (USDC)</text>'
    )
    write_svg(args, "usdc_fiat_sweep_fig1_fee_vs_amount.svg", "\n".join(body),
              "Realized fee vs tranche amount with advertised Coinbase fee schedule")


if __name__ == "__main__":
    main()
