"""Convert regridded CMIP6 NetCDF files to Zarr format sequentially.

For each model/scenario/variable combination, calls netcdf_to_zarr.py to
consolidate annual NetCDF files into a single time-chunked Zarr store.

Example usage:
    python run_cmip6_netcdf_to_zarr.py \
        --netcdf_dir /path/to/regrid_output \
        --output_dir /path/to/cmip6_zarr \
        --models "GFDL-ESM4 CESM2" \
        --scenarios "historical ssp370" \
        --variables "tasmax pr dtr"
"""

import argparse
import logging
import subprocess
import sys
from itertools import product
from pathlib import Path

from config import cmip6_regrid_tmp_fn, cmip6_zarr_tmp_fn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netcdf_dir", type=str, required=True,
                        help="Root directory of regridded CMIP6 NetCDF files")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Directory to write Zarr stores")
    parser.add_argument("--models", type=str, required=True,
                        help="Space-separated list of model names")
    parser.add_argument("--scenarios", type=str, required=True,
                        help="Space-separated list of scenarios")
    parser.add_argument("--variables", type=str, required=True,
                        help="Space-separated list of variable IDs")
    parser.add_argument("--era5_start_year", type=int, default=1965,
                        help="First year of ERA5 training period (historical scenario)")
    parser.add_argument("--era5_end_year", type=int, default=2014,
                        help="Last year of ERA5 training period (historical scenario)")
    parser.add_argument("--future_start_year", type=int, default=2015,
                        help="First year of future scenario data")
    parser.add_argument("--future_end_year", type=int, default=2100,
                        help="Last year of future scenario data")
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

    models = args.models.split()
    scenarios = args.scenarios.split()
    variables = args.variables.split()

    year_ranges = {
        "historical": {"start_year": args.era5_start_year, "end_year": args.era5_end_year},
        "ssp126": {"start_year": args.future_start_year, "end_year": args.future_end_year},
        "ssp245": {"start_year": args.future_start_year, "end_year": args.future_end_year},
        "ssp370": {"start_year": args.future_start_year, "end_year": args.future_end_year},
        "ssp585": {"start_year": args.future_start_year, "end_year": args.future_end_year},
    }

    combos = list(product(models, scenarios, variables))
    errors = []

    for count, (model, scenario, var_id) in enumerate(combos, 1):
        yr = year_ranges.get(scenario, year_ranges["ssp370"])
        start_year = yr["start_year"]
        end_year = yr["end_year"]

        year_str = (
            f"{model}/{scenario}/day/{var_id}/"
            + cmip6_regrid_tmp_fn.format(
                model=model, scenario=scenario, var_id=var_id, year="{year}"
            )
        )
        zarr_path = output_dir / cmip6_zarr_tmp_fn.format(
            model=model, scenario=scenario, var_id=var_id
        )

        logging.info(f"[{count}/{len(combos)}] {model}/{scenario}/{var_id}")

        cmd = [
            sys.executable, args.worker_script,
            "--netcdf_dir", str(netcdf_dir),
            "--year_str", year_str,
            "--start_year", str(start_year),
            "--end_year", str(end_year),
            "--zarr_path", str(zarr_path),
        ]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Failed: {model}/{scenario}/{var_id}")
            errors.append(f"{model}/{scenario}/{var_id}")

    if errors:
        logging.error(f"{len(errors)}/{len(combos)} combinations failed: {errors}")
        sys.exit(1)

    logging.info("All CMIP6 NetCDF-to-Zarr conversions completed")
