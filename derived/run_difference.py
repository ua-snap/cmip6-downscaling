"""Compute a derived variable by subtracting one Zarr store from another, sequentially.

Primary use: derive tasmin = tasmax - dtr after bias adjustment.

Template filenames use {model} and {scenario} placeholders.

Example usage:
    python run_difference.py \
        --input_dir /path/to/adjusted \
        --output_dir /path/to/derived \
        --minuend_tmp_fn "tasmax_{model}_{scenario}_adjusted.zarr" \
        --subtrahend_tmp_fn "dtr_{model}_{scenario}_adjusted.zarr" \
        --out_tmp_fn "tasmin_{model}_{scenario}_adjusted.zarr" \
        --new_var_id tasmin \
        --models "GFDL-ESM4 CESM2" \
        --scenarios "historical ssp370"
"""

import argparse
import logging
import subprocess
import sys
from itertools import product
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", type=str, required=True,
                        help="Directory containing input Zarr stores")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Directory to write output Zarr stores")
    parser.add_argument("--minuend_tmp_fn", type=str, required=True,
                        help="Template filename for the minuend store (uses {model}, {scenario})")
    parser.add_argument("--subtrahend_tmp_fn", type=str, required=True,
                        help="Template filename for the subtrahend store")
    parser.add_argument("--out_tmp_fn", type=str, required=True,
                        help="Template filename for the output store")
    parser.add_argument("--new_var_id", type=str, required=True,
                        help="Variable ID to assign to the output")
    parser.add_argument("--models", type=str, required=True,
                        help="Space-separated list of model names")
    parser.add_argument("--scenarios", type=str, required=True,
                        help="Space-separated list of scenarios")
    parser.add_argument(
        "--worker_script",
        type=str,
        default=str(Path(__file__).parent / "difference.py"),
        help="Path to difference.py (default: same directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    models = args.models.split()
    scenarios = args.scenarios.split()
    combos = list(product(models, scenarios))
    errors = []

    for count, (model, scenario) in enumerate(combos, 1):
        minuend = input_dir / args.minuend_tmp_fn.format(model=model, scenario=scenario)
        subtrahend = input_dir / args.subtrahend_tmp_fn.format(model=model, scenario=scenario)

        if not minuend.exists() or not subtrahend.exists():
            logging.warning(
                f"[{count}/{len(combos)}] Skipping {model}/{scenario}: "
                f"minuend={minuend.exists()}, subtrahend={subtrahend.exists()}"
            )
            continue

        out_store = output_dir / args.out_tmp_fn.format(model=model, scenario=scenario)

        logging.info(f"[{count}/{len(combos)}] {args.new_var_id}: {model}/{scenario}")

        cmd = [
            sys.executable, args.worker_script,
            "--minuend_store", str(minuend),
            "--subtrahend_store", str(subtrahend),
            "--output_store", str(out_store),
            "--new_var_id", args.new_var_id,
        ]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Failed: {model}/{scenario}")
            errors.append(f"{model}/{scenario}")

    if errors:
        logging.error(f"{len(errors)}/{len(combos)} difference jobs failed: {errors}")
        sys.exit(1)

    logging.info(f"{args.new_var_id} derivation completed")
