"""Figure 2: per-hop latency (on-chain send to Coinbase credit to fiat
spendable) per tranche.

Reads usdc-fiat-sweep run records (default: experiments/usdc-fiat-sweep/sessions/,
override with --records) and writes an SVG in the house chart style.
"""
import datetime

from usdc_fiat_sweep_common import load_records, parse_args, write_svg

W, H = 640, 400
M_L, M_R, M_T, M_B = 90, 16, 40, 90


def _ts(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    args = parse_args("Figure 2: per-hop latency per tranche")
    records = [r for r in load_records(args.records, args.include_synthetic) if r["amount_usdc"] is not None]
    assert records, "no executed run records found"
    rows = sorted(
        (
            r["tranche_id"],
            (_ts(r["timestamp_coinbase_credit"]) - _ts(r["timestamp_sent"])).total_seconds(),
            (_ts(r["timestamp_fiat_spendable"]) - _ts(r["timestamp_coinbase_credit"])).total_seconds(),
        )
        for r in records
    )

    bar_h, gap = 14, 10
    plot_h = len(rows) * (bar_h * 2 + gap)
    max_sec = max(a + b for _, a, b in rows)
    plot_w = W - M_L - M_R

    body = [
        f'  <text x="{W / 2}" y="24" text-anchor="middle" font-size="16" '
        f'font-family="sans-serif">Fiat spendable lands within two minutes of the send</text>'
    ]
    y = M_T
    for label, send_credit, credit_spend in rows:
        w1 = send_credit / max_sec * plot_w
        w2 = credit_spend / max_sec * plot_w
        body.append(
            f'  <text x="{M_L - 8}" y="{y + bar_h}" text-anchor="end" font-size="11" '
            f'font-family="sans-serif">{label}</text>'
            f'  <rect x="{M_L}" y="{y}" width="{w1:.1f}" height="{bar_h}" fill="#1a6ee0"/>'
            f'  <rect x="{M_L + w1:.1f}" y="{y}" width="{w2:.1f}" height="{bar_h}" fill="#e08a1a"/>'
            f'  <text x="{M_L + w1 + w2 + 6:.1f}" y="{y + bar_h}" font-size="11" '
            f'font-family="sans-serif">{send_credit + credit_spend:g}s</text>'
        )
        y += bar_h + gap
    body.append(
        f'  <rect x="{M_L}" y="{H - M_B + 34}" width="12" height="12" fill="#1a6ee0"/>'
        f'  <text x="{M_L + 18}" y="{H - M_B + 44}" font-size="11" font-family="sans-serif">'
        f"send to Coinbase credit</text>"
        f'  <rect x="{M_L + 180}" y="{H - M_B + 34}" width="12" height="12" fill="#e08a1a"/>'
        f'  <text x="{M_L + 198}" y="{H - M_B + 44}" font-size="11" font-family="sans-serif">'
        f"credit to fiat spendable</text>"
        f'  <text x="{(M_L + W - M_R) / 2}" y="{H - 8}" text-anchor="middle" '
        f'font-size="12" font-family="sans-serif">seconds per hop (stacked)</text>'
    )
    write_svg(args, "usdc_fiat_sweep_fig2_hop_latency.svg", "\n".join(body),
              "Per-hop latency per tranche: send, Coinbase credit, fiat spendable")


if __name__ == "__main__":
    main()
