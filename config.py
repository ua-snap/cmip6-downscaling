"""
Pipeline-wide configuration for CMIP6 statistical downscaling.

This is the single file to edit when customising a run. It covers:
  - Year ranges used for training and projection
  - Spatial domain bounds
  - Dask cluster resource settings
  - QDM training parameters and post-adjustment squeeze bounds
  - Regridding configuration (variable allowlist, model-institution mapping)
  - Bias adjustment lookup tables (variable mappings, adjustment kinds, jitter)

All pipeline scripts import from this file; you should not need to edit
anything else to adapt the pipeline to a new domain or compute environment.
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
# Arctic domain bounds (0–360 longitude convention)
# Used by make_intermediate_target_grid_file.py to subset CMIP6 data.
# Override for a different region.
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
# Dask cluster configuration
# ---------------------------------------------------------------------------
# Edit these three values to match your compute resources.
# Every worker script (regrid, train_qm, bias_adjust, dtr, difference) reads
# from here, so this is the only place you need to change.
#
# Total memory consumed = DASK_N_WORKERS × DASK_MEMORY_LIMIT
# A practical starting point:
#   n_workers  = cpu_count // 4      (4 threads per worker is a good default)
#   memory_limit = total_ram * 0.8 / n_workers   (leave ~20 % for the OS)
#
# Example — 32 GB / 8-core laptop:
#   DASK_N_WORKERS = 2, DASK_MEMORY_LIMIT = "12GB"  (24 GB total)
# Example — 256 GB / 32-core workstation:
#   DASK_N_WORKERS = 8, DASK_MEMORY_LIMIT = "28GB"  (224 GB total)

DASK_N_WORKERS = 4
DASK_THREADS_PER_WORKER = 4
DASK_MEMORY_LIMIT = "28GB"

# Dask worker memory management — fractions of per-worker memory limit.
# Workers start spilling to disk at SPILL, pause accepting new tasks at PAUSE,
# and are killed at TERMINATE. Lowering these thresholds reduces OOM risk at
# the cost of more disk I/O.
DASK_MEMORY_TARGET = 0.70
DASK_MEMORY_SPILL = 0.80
DASK_MEMORY_PAUSE = 0.85
DASK_MEMORY_TERMINATE = 0.95

# Target size for individual array chunks passed to Dask workers.
DASK_ARRAY_CHUNK_SIZE = "128 MiB"

# ---------------------------------------------------------------------------
# QDM training parameters
# ---------------------------------------------------------------------------

# Number of quantiles used to build the empirical CDFs.
# Higher values capture more distributional detail but use more memory.
QDM_NQUANTILES = 100

# Half-width of the day-of-year window used when grouping by calendar day
# (group="time.dayofyear"). A window of 31 means each calendar day is
# estimated from a ±15-day band of observations across all training years.
QDM_WINDOW = 31

# ---------------------------------------------------------------------------
# Post-adjustment squeeze bounds (physical plausibility limits)
# Values outside these ranges are clipped after bias adjustment.
# ---------------------------------------------------------------------------

# tasmax: upper ceiling of 60 °C (333.15 K)
SQUEEZE_TASMAX_MAX = 333.15  # K

# precipitation: non-negative, capped at the highest observed daily total
SQUEEZE_PR_MIN = 0       # mm d⁻¹
SQUEEZE_PR_MAX = 1650    # mm d⁻¹

# dtr: quantile-based squeeze (avoids hard physical limits for a range variable)
SQUEEZE_DTR_LOWER_QUANTILE = 0.0000002
SQUEEZE_DTR_UPPER_QUANTILE = 0.9999998

# tasmin: lower floor of −70 °C (203.15 K) — the lowest recorded surface temperature
SQUEEZE_TASMIN_MIN = 203.15  # K

# hurs / hursmin: relative humidity is physically bounded [0, 100] %
SQUEEZE_HURS_MIN = 0    # %
SQUEEZE_HURS_MAX = 100  # %

# ---------------------------------------------------------------------------
# Regridding — configuration
# ---------------------------------------------------------------------------

# Number of files processed per subprocess call in cascade regridding.
# Reduce if individual batches are too slow; increase to reduce subprocess overhead.
CASCADE_BATCH_SIZE = 200

# Batch file naming template (one file per model/scenario/frequency/variable/grid)
batch_tmp_fn = "batch_{model}_{scenario}_{frequency}_{var_id}_{grid_name}_{count}.txt"

# CMIP6 model → publishing institution mapping (used to build ESGF directory paths)
model_inst_lu = {
    "CESM2": "NCAR",
    "CNRM-CM6-1-HR": "CNRM-CERFACS",
    "E3SM-2-0": "E3SM-Project",
    "EC-Earth3-Veg": "EC-Earth-Consortium",
    "GFDL-ESM4": "NOAA-GFDL",
    "HadGEM3-GC31-LL": "MOHC",
    "HadGEM3-GC31-MM": "MOHC",
    "KACE-1-0-G": "NIMS-KMA",
    "MIROC6": "MIROC",
    "MPI-ESM1-2-HR": "DKRZ",  # historical uses "MPI-M"; see get_institution_id() in generate_batch_files.py
    "MRI-ESM2-0": "MRI",
    "NorESM2-MM": "NCC",
    "TaiESM1": "AS-RCEC",
}

# List of CMIP6 variable IDs that regrid/regrid.py can process.
# Only variables listed here are accepted by the regridder's get_var_id() gate.
# "name" sets the long_name attribute on regridded output; "table_ids" must
# include "day" (this pipeline processes daily data only).
# sftlf is regridded separately by regrid/regrid_sftlf_to_target.py and is
# not processed through the main regrid.py pipeline.
variables = {
    "tasmax":  {"name": "maximum_near_surface_air_temperature",          "table_ids": ["day"]},
    "tasmin":  {"name": "minimum_near_surface_air_temperature",          "table_ids": ["day"]},
    "pr":      {"name": "precipitation",                                  "table_ids": ["day"]},
    "dtr":     {"name": "diurnal_temperature_range",                     "table_ids": ["day"]},
    "hurs":    {"name": "near_surface_relative_humidity",                "table_ids": ["day"]},
    "hursmin": {"name": "daily_minimum_near_surface_relative_humidity",  "table_ids": ["day"]},
    "snw":     {"name": "surface_snow_amount",                           "table_ids": ["day"]},
    "sfcWind": {"name": "near_surface_wind_speed",                       "table_ids": ["day"]},
}

# Variables that require land/sea masking during regridding.
# regrid/regrid.py applies sftlf-derived masks to variables listed here.
landsea_variables = {
    "snw": "land",
}

# ---------------------------------------------------------------------------
# Bias adjustment — variable lookup tables
# ---------------------------------------------------------------------------

# CMIP6 variable → ERA5 reference variable name used as the QDM training reference.
# Only variables listed here can be bias-adjusted.
sim_ref_var_lu = {
    "tasmax": "t2max",
    "tasmin": "t2min",
    "dtr": "dtr",
    "pr": "pr",
    "hurs": "rh2_mean",
    "hursmin": "rh2_min",
    "snw": "snow_mean",
    "sfcWind": "wspd10_mean",
}

# QDM adjustment kind per variable.
# "+" additive (temperature-like); "*" multiplicative (ratio-based, non-negative).
varid_adj_kind_lu = {
    "tasmax": "+",
    "tasmin": "+",
    "dtr": "*",
    "pr": "*",
    "hurs": "+",
    "hursmin": "+",
    "snw": "*",
    "sfcWind": "*",
}

# Jitter thresholds: values below this are replaced with uniform random noise
# before QDM training to spread the zero-mass across the lowest quantiles.
# Applied to historical/training data only; projected values may reach exactly 0.
jitter_under_lu = {"pr": "0.01 mm d-1", "dtr": "1e-4 K", "snw": "0.01 kg m-2"}

# Frequency-adaptation thresholds for xclim's adapt_freq, which corrects for
# differences in wet-day / non-zero frequency between model and reference.
adapt_freq_thresh_lu = {"pr": "0.254 mm d-1", "snw": "0.254 kg m-2"}

# ---------------------------------------------------------------------------
# Bias adjustment — file-naming templates
# Used by bias_adjust/run_*.py runner scripts
# ---------------------------------------------------------------------------

# Input: regridded CMIP6 NetCDF files (one per year)
cmip6_regrid_tmp_fn = "{var_id}_day_{model}_{scenario}_regrid_{year}0101-{year}1231.nc"

# Input: ERA5 NetCDF files (glob pattern; matched by year within run_era5_netcdf_to_zarr.py)
era5_tmp_fn = "{var_id}_{year}*_era5_{resolution}km_3338.nc"

# Intermediate: Zarr stores for CMIP6 and ERA5 data
cmip6_zarr_tmp_fn = "{var_id}_{model}_{scenario}.zarr"
era5_zarr_tmp_fn = "{var_id}_era5.zarr"

# Intermediate: trained QDM weights
trained_qm_tmp_fn = "trained_qdm_{var_id}_{model}.zarr"

# Output: bias-adjusted Zarr stores
cmip6_adjusted_tmp_fn = "{var_id}_{model}_{scenario}_adjusted.zarr"

# ---------------------------------------------------------------------------
# DTR / difference derivation — file-naming templates
# Used by derive/run_*.py runner scripts
# ---------------------------------------------------------------------------

# Directory structure for derived CMIP6 DTR files
dtr_tmp_dir_structure = "{model}/{scenario}/day/dtr"
dtr_tmp_fn = "dtr_day_{model}_{scenario}_regrid_{start_date}-{end_date}.nc"

# ERA5 DTR output files
era5_dtr_tmp_fn = "dtr_{year}_era5_{resolution}km_3338.nc"
