"""
Top-level configuration for the CMIP6 downscaling pipeline.

These are the default values used throughout the pipeline. Most can be
overridden by passing CLI arguments to individual scripts; this file serves
as a single place to see and modify defaults.
"""

# ---------------------------------------------------------------------------
# Year ranges
# ---------------------------------------------------------------------------

# ERA5 reference period used for QDM training
ERA5_START_YEAR = 1965
ERA5_END_YEAR = 2014

# Period covered by future-scenario CMIP6 data (after historical)
FUTURE_START_YEAR = 2015
FUTURE_END_YEAR = 2100

# ---------------------------------------------------------------------------
# Arctic domain bounds (0-360 longitude convention)
# Used by make_intermediate_target_grid_file.py
# ---------------------------------------------------------------------------

DOMAIN_4KM = {
    "min_lon": 183,
    "max_lon": 232,
    "min_lat": 54,
    "max_lat": 73,
}

DOMAIN_12KM = {
    "min_lon": 182,
    "max_lon": 254,
    "min_lat": 48,
    "max_lat": 77,
}

# ---------------------------------------------------------------------------
# Variable lookups
# ---------------------------------------------------------------------------

# Mapping from CMIP6 variable IDs to the ERA5 variable names produced by the
# ERA5 pre-processing step (the names used in ERA5 input NetCDF filenames).
CMIP6_TO_ERA5_VARS = {
    "tasmax": "t2max",
    "tasmin": "t2min",
    "tas": "t2",
    "pr": "pr",
    "dtr": "dtr",
    "hurs": "rh2_mean",
    "hursmin": "rh2_min",
    "snw": "snow_sum",
    "sfcWind": "wspd10_mean",
}

# Variables that exist only over land (require land-mask treatment)
LAND_VARIABLES = ["mrro", "mrsol", "mrsos", "snd", "snw"]

# Variables that exist only over sea
SEA_VARIABLES = ["tos", "siconc", "sithick"]

# ---------------------------------------------------------------------------
# Supported models and scenarios
# ---------------------------------------------------------------------------

ALL_MODELS = [
    "CESM2",
    "CNRM-CM6-1-HR",
    "EC-Earth3-Veg",
    "GFDL-ESM4",
    "HadGEM3-GC31-LL",
    "HadGEM3-GC31-MM",
    "KACE-1-0-G",
    "MIROC6",
    "MPI-ESM1-2-HR",
    "MRI-ESM2-0",
    "NorESM2-MM",
    "TaiESM1",
    "E3SM-2-0",
]

ALL_SCENARIOS = ["historical", "ssp126", "ssp245", "ssp370", "ssp585"]

ALL_FREQS = ["day", "mon"]
