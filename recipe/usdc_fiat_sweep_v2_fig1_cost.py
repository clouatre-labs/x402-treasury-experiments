"""Figure: realized cost (USD, log-scale annotation) per transaction for the
usdc-fiat-sweep-v2 experiment, against the advertised fee schedule.

Reads usdc-fiat-sweep-v2 run records (default:
experiments/usdc-fiat-sweep-v2/sessions/, override with --records) and writes
an SVG in the house chart style. Excludes the Arm B disbursement row from the
fee bars (its cost is a percentage of CAD proceeds, annotated separately).
"""
import argparse
import json
import pathlib

DEFAULT_RECORDS = pathlib.Path("experiments/usdc-fiat-sweep-v2/sessions")

W, H = 640, 400
M_L, M_R, M_T, M_B = 150, 16, 40, 60


def load_records(record_dir, include_synthetic=False):
    records = []
    for path in sorted(record_dir.glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("synthetic") and not include_synthetic:
            continue
        records.append(record)
    return records


def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--records", type=pathlib.Path, default=DEFAULT_RECORDS,
                        help="directory containing run-record JSON files")
    parser.add_argument("--out", type=pathlib.Path,
                        help="output SVG path (default: figures/<name>.svg)")
    parser.add_argument("--include-synthetic", action="store_true",
                        help="include records marked synthetic:true (rehearsal only)")
    return parser.parse_args()


def svg_open(title):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" '
        'viewBox="0 0 640 400" style="background:transparent">\n'
        f"  <title>{title}</title>\n"
    )


def svg_close():
    return "</svg>\n"


def write_svg(args, default_name, body, title):
    out = args.out if args.out else pathlib.Path("figures") / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg_open(title) + body + svg_close())
    print(f"wrote {out}")


def main():
    args = parse_args("Figure: realized cost per transaction vs advertised schedule (usdc-fiat-sweep-v2)")
    records = load_records(args.records, args.include_synthetic)
    executed = [r for r in records if r["executed"]]
    assert executed, "no executed run records found"

    # Cost per transaction in USD terms: convert fees and on-chain gas for
    # USDC legs; disbursement percentage fee converted at the recorded mid
    # for the annotation row.
    rows = []
    for r in executed:
        amount = r.get("amount_usdc")
        fee_usd = r["fixed_fee_usd"] + (r.get("network_fee_usd") or 0)
        if amount:
            fee_usd += (r.get("disbursement_fee_fiat") or 0) * 0
        rows.append((r["tranche_id"], fee_usd, r.get("disbursement_fee_fiat")))

    rows.sort(key=lambda x: x[0])
    bar_h, gap = 22, 12
    plot_h = len(rows) * (bar_h + gap)
    max_fee = max(max(f for _, f, _ in rows), 0.01)
    plot_w = W - M_L - M_R

    body = [
        f'  <text x="{W / 2}" y="24" text-anchor="middle" font-size="16" '
        f'font-family="sans-serif">Realized cost per transaction against the advertised schedule</text>'
    ]
    for i, (tid, fee, disbursement) in enumerate(rows):
        y = M_T + i * (bar_h + gap)
        bar_w = max(1.0, fee / max_fee * plot_w)
        label = f"${fee:.4f}"
        # keep the value label inside the canvas: for near-full-width bars,
        # anchor it inside the bar end instead of past the right edge
        # (post-pass cosmetic layout fix; label content unchanged).
        label_x = M_L + bar_w + 6
        anchor, fill_attr = "start", ""
        if label_x > W - 60:
            label_x = M_L + bar_w - 6
            anchor, fill_attr = "end", ' fill="#ffffff"'
        body.append(f'  <text x="{M_L - 8}" y="{y + bar_h / 2 + 4}" text-anchor="end" font-size="11" font-family="sans-serif">{tid}</text>')
        body.append(f'  <rect x="{M_L}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" fill="#2563eb"/>')
        body.append(f'  <text x="{label_x:.1f}" y="{y + bar_h / 2 + 4}" text-anchor="{anchor}" font-size="11" font-family="sans-serif"{fill_attr}>{label}</text>')
        if disbursement:
            body.append(
                f'  <text x="{M_L + bar_w + 6}" y="{y + bar_h / 2 + 16}" font-size="9" '
                f'font-family="sans-serif" fill="#6b7280">+ {disbursement} CAD disbursement fee</text>'
            )
    body.append(
        f'  <text x="{M_L}" y="{H - 12}" font-size="10" font-family="sans-serif" '
        f'fill="#6b7280">Advertised: Kraken stablecoin schedule 0.20%; Coinbase convert 0%; EFT 0.35%</text>'
    )
    body_str = "\n".join(body) + "\n"
    write_svg(args, "usdc_fiat_sweep_v2_fig1_cost_per_transaction.svg", body_str,
              "Realized cost per transaction vs advertised schedule")


if __name__ == "__main__":
    main()
