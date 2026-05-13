"""Convert ERA5 NetCDF files to Zarr format sequentially.

For each variable, calls netcdf_to_zarr.py to combine annual ERA5 NetCDF files
into a single time-chunked Zarr store.

ERA5 files are expected under: <netcdf_dir>/<var_id>/<var_id>_<year>*_era5_<resolution>km_3338.nc

Example usage:
    python run_era5_netcdf_to_zarr.py \
        --netcdf_dir /path/to/era5_netcdf \
        --output_dir /path/to/era5_zarr \
        --variables "t2max t2min pr dtr" \
        --resolution 12
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from config import era5_tmp_fn, era5_zarr_tmp_fn
from luts import era5_start_year as _default_start, era5_end_year as _default_end

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netcdf_dir", type=str, required=True,
                        help="Root directory of ERA5 NetCDF files")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Directory to write Zarr stores")
    parser.add_argument("--variables", type=str, required=True,
                        help="Space-separated list of ERA5 variable IDs")
    parser.add_argument("--start_year", type=int, default=_default_start,
                        help=f"First year to include (default: {_default_start})")
    parser.add_argument("--end_year", type=int, default=_default_end,
                        help=f"Last year to include (default: {_default_end})")
    parser.add_argument("--resolution", type=str, default="12",
                        help="ERA5 resolution in km (default: 12)")
    parser.add_argument(
        "--worker_script",
        type=str,
        default=str(Path(__file__).parent / "netcdf_to_zarr.py"),
        help="Path to netcdf_to_zarr.py (default: same directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    netcdf_dir = Path(args.netcdf_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    variables = args.variables.split()
    errors = []

    for i, var_id in enumerate(variables, 1):
        year_str = (
            f"{var_id}/"
            + era5_tmp_fn.format(var_id=var_id, year="{year}", resolution=args.resolution)
        )
        zarr_path = output_dir / era5_zarr_tmp_fn.format(var_id=var_id)

        logging.info(f"[{i}/{len(variables)}] {var_id} ({args.start_year}–{args.end_year})")

        cmd = [
            sys.executable, args.worker_script,
            "--netcdf_dir", str(netcdf_dir),
            "--year_str", year_str,
            "--start_year", str(args.start_year),
            "--end_year", str(args.end_year),
            "--zarr_path", str(zarr_path),
        ]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Failed: {var_id}")
            errors.append(var_id)

    if errors:
        logging.error(f"{len(errors)}/{len(variables)} variables failed: {errors}")
        sys.exit(1)

    logging.info("All ERA5 NetCDF-to-Zarr conversions completed")
