"""Compute DTR = tasmax - tasmin for regridded CMIP6 data, sequentially.

Outputs are written under:
  <output_dir>/<model>/<scenario>/day/dtr/

Example usage:
    python run_cmip6_dtr.py \
        --input_dir /path/to/regrid_output \
        --output_dir /path/to/regrid_output \
        --models "GFDL-ESM4 CESM2" \
        --scenarios "historical ssp370"
"""

import argparse
import logging
import subprocess
import sys
from itertools import product
from pathlib import Path

from config import dtr_tmp_fn, dtr_tmp_dir_structure

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", type=str, required=True,
                        help="Root directory with regridded CMIP6 files")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Root directory to write DTR output files")
    parser.add_argument("--models", type=str, required=True,
                        help="Space-separated list of model names")
    parser.add_argument("--scenarios", type=str, required=True,
                        help="Space-separated list of scenarios")
    parser.add_argument(
        "--worker_script",
        type=str,
        default=str(Path(__file__).parent / "dtr.py"),
        help="Path to dtr.py (default: same directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    models = args.models.split()
    scenarios = args.scenarios.split()
    combos = list(product(models, scenarios))
    errors = []

    for count, (model, scenario) in enumerate(combos, 1):
        out_dir = output_dir / dtr_tmp_dir_structure.format(model=model, scenario=scenario)
        out_dir.mkdir(parents=True, exist_ok=True)

        dtr_fn_format = {
            "model": model,
            "scenario": scenario,
            "start_date": "{start_date}",
            "end_date": "{end_date}",
        }

        logging.info(f"[{count}/{len(combos)}] Computing DTR: {model}/{scenario}")

        cmd = [
            sys.executable, args.worker_script,
            "--input_dir", str(input_dir),
            "--model", model,
            "--scenario", scenario,
            "--output_dir", str(out_dir),
            "--dtr_tmp_fn", dtr_tmp_fn.format(**dtr_fn_format),
        ]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Failed: {model}/{scenario}")
            errors.append(f"{model}/{scenario}")

    if errors:
        logging.error(f"{len(errors)}/{len(combos)} DTR jobs failed: {errors}")
        sys.exit(1)

    logging.info("CMIP6 DTR computation completed")
