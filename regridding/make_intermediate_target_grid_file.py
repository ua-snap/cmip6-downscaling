"""Create a grid with user-defined degree resolution for cascade regridding.

Bounds default to the panarctic domain for 4km or 12km ERA5 resolution.
Override with --min_lon/--max_lon/--min_lat/--max_lat for other domains.

Example usage:
    python make_intermediate_target_grid_file.py \
        --src_file /path/to/any_cmip6_file.nc \
        --out_file /path/to/intermediate_target.nc \
        --step 0.5 \
        --resolution 12
"""

import argparse
import logging
import xarray as xr
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Arctic domain defaults keyed by resolution (0-360 longitude)
_DOMAIN_DEFAULTS = {
    4:  {"min_lon": 183, "max_lon": 232, "min_lat": 54, "max_lat": 73},
    12: {"min_lon": 182, "max_lon": 254, "min_lat": 48, "max_lat": 77},
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src_file",
        type=str,
        required=True,
        help="Path to any CMIP6 NetCDF file (used as a grid template)",
    )
    parser.add_argument(
        "--out_file",
        type=str,
        required=True,
        help="Path to write the intermediate target grid file",
    )
    parser.add_argument(
        "--step",
        type=float,
        required=True,
        help="Grid step size in degrees",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        required=True,
        help="Target resolution in km (4 or 12); sets domain defaults",
    )
    parser.add_argument(
        "--min_lon",
        type=float,
        default=None,
        help="Minimum longitude (0-360). Defaults to Arctic value for --resolution.",
    )
    parser.add_argument(
        "--max_lon",
        type=float,
        default=None,
        help="Maximum longitude (0-360). Defaults to Arctic value for --resolution.",
    )
    parser.add_argument(
        "--min_lat",
        type=float,
        default=None,
        help="Minimum latitude. Defaults to Arctic value for --resolution.",
    )
    parser.add_argument(
        "--max_lat",
        type=float,
        default=None,
        help="Maximum latitude. Defaults to Arctic value for --resolution.",
    )
    args = parser.parse_args()

    # Fill domain defaults from resolution if not explicitly provided
    defaults = _DOMAIN_DEFAULTS.get(args.resolution)
    if defaults is None and any(
        v is None for v in [args.min_lon, args.max_lon, args.min_lat, args.max_lat]
    ):
        raise ValueError(
            f"Unsupported resolution {args.resolution}: must supply "
            "--min_lon/--max_lon/--min_lat/--max_lat explicitly."
        )
    if defaults:
        if args.min_lon is None:
            args.min_lon = defaults["min_lon"]
        if args.max_lon is None:
            args.max_lon = defaults["max_lon"]
        if args.min_lat is None:
            args.min_lat = defaults["min_lat"]
        if args.max_lat is None:
            args.max_lat = defaults["max_lat"]

    return (
        args.src_file,
        args.out_file,
        args.step,
        args.resolution,
        args.min_lon,
        args.max_lon,
        args.min_lat,
        args.max_lat,
    )


def get_num(min_val, max_val, step):
    return int((max_val - min_val) / step) + 1


def create_intermediate_target_grid(
    src_file, out_file, step, resolution, min_lon, max_lon, min_lat, max_lat
):
    lon_num = get_num(min_lon, max_lon, step)
    lat_num = get_num(min_lat, max_lat, step)

    new_lon = np.linspace(min_lon, max_lon, lon_num)
    new_lat = np.linspace(min_lat, max_lat, lat_num)

    ds = xr.open_dataset(src_file)
    assert (
        ds.lon.values[0] < ds.lon.values[-1]
    ), "Longitude values are not in increasing order"
    mid_res_ds = ds.isel(time=0, drop=True).interp(
        lat=new_lat, lon=new_lon, method="linear"
    )
    del mid_res_ds.encoding["unlimited_dims"]

    logger.info(
        f"Creating intermediate target grid at {out_file} with "
        f"{lon_num} lon × {lat_num} lat at {step}° resolution "
        f"(lon {min_lon}–{max_lon}, lat {min_lat}–{max_lat})"
    )
    mid_res_ds.to_netcdf(out_file)


if __name__ == "__main__":
    src_file, out_file, step, resolution, min_lon, max_lon, min_lat, max_lat = parse_args()
    create_intermediate_target_grid(src_file, out_file, step, resolution, min_lon, max_lon, min_lat, max_lat)
