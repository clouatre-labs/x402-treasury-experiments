"""Shared helpers for usdc-fiat-sweep figure scripts.

House chart style: transparent background, 640px viewBox, declarative titles.
Stdlib only. Run records are JSON files under experiments/usdc-fiat-sweep/sessions/
by default; pass --records DIR to point at any record directory.
"""
import argparse
import json
import pathlib

DEFAULT_RECORDS = pathlib.Path("experiments/usdc-fiat-sweep/sessions")

# Advertised Coinbase fee schedule used as the Figure 1 overlay. At execution
# time the operator records the live schedule verbatim; update these values
# then. These are placeholder values matching the published standard schedule.
ADVERTISED_FIXED_FEE_USD = 0.25


def load_records(record_dir, include_synthetic=False):
    """Load all run-record JSON files from record_dir, sorted by tranche_id."""
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
