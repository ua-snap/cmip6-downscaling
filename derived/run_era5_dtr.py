"""Compute DTR = t2max - t2min for ERA5 data.

ERA5 files must be in:
  <era5_dir>/t2max/<files>
  <era5_dir>/t2min/<files>

Example usage:
    python run_era5_dtr.py \
        --era5_dir /path/to/era5_netcdf \
        --output_dir /path/to/era5_dtr \
        --resolution 12
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from config import era5_dtr_tmp_fn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

ERA5_TMAX_VAR = "t2max"
ERA5_TMIN_VAR = "t2min"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--era5_dir", type=str, required=True,
                        help="Root directory of ERA5 NetCDF files")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Directory to write ERA5 DTR output files")
    parser.add_argument("--resolution", type=str, default="12",
                        help="ERA5 resolution in km (default: 12)")
    parser.add_argument(
        "--worker_script",
        type=str,
        default=str(Path(__file__).parent / "dtr.py"),
        help="Path to dtr.py (default: same directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    era5_dir = Path(args.era5_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dtr_fn = era5_dtr_tmp_fn.format(year="{year}", resolution=args.resolution)

    logging.info(f"Computing ERA5 DTR from {era5_dir}")

    cmd = [
        sys.executable, args.worker_script,
        "--tmax_dir", str(era5_dir / ERA5_TMAX_VAR),
        "--tmin_dir", str(era5_dir / ERA5_TMIN_VAR),
        "--output_dir", str(output_dir),
        "--dtr_tmp_fn", dtr_fn,
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        logging.error("ERA5 DTR computation failed")
        sys.exit(1)

    logging.info("ERA5 DTR computation completed")
