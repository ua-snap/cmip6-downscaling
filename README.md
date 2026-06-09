# CMIP6 Statistical Downscaling

Standalone pipeline for statistically downscaling daily CMIP6 climate model data to high-resolution grids using Quantile Delta Mapping (QDM) bias adjustment. The reference dataset is ERA5 dynamically downscaled using the Weather Research and Forecasting Model (WRF).

This repo packages the core computation scripts from the [cmip6-utils](https://github.com/ua-snap/cmip6-utils) repository into a form that can be run sequentially on any infrastructure — no Prefect, no SLURM, no HPC required. Each script is a standalone tool; you chain them together using bash scripts, a Jupyter notebook, or any other method you prefer.

---

## Methodology

### Algorithm: Quantile Delta Mapping (QDM)

Bias adjustment uses [Quantile Delta Mapping](https://doi.org/10.1175/JCLI-D-14-00754.1) (QDM) as implemented by [xclim](https://xclim.readthedocs.io/en/stable/sdba.html). The pipeline follows the approach of [Lavoie et al. (2024)](https://doi.org/10.1038/s41597-023-02855-z), which used detrended quantile mapping for the same variables.

**Training configuration** (same for all variables unless noted below):
- **Quantiles**: 100
- **Grouping**: `time.dayofyear` with a 31-day window (day-of-year quantiles estimated from a ±15-day window centred on each calendar day)
- **Training period**: WRF-downscaled ERA5 reference years (default 1965–2014; configurable in `config.py`)
- **Extrapolation**: `"constant"` — adjustment factors are held constant beyond the training quantile range, preventing runaway extrapolation in the tails
- **Interpolation**: `"nearest"` quantile lookup

### Zero-inflated variables: jitter and frequency adaptation

`pr`, `dtr`, and `snw` contain many exact-zero (or near-zero) values that would distort quantile estimation. Two preprocessing steps address this:

1. **Jitter** — Values below a small threshold are replaced with uniform random noise in `[0, threshold)` during QDM training of the historical/reference distributions only. This spreads the zero-mass across the lowest quantiles so they can be matched continuously rather than as a point mass. Jitter is **not** applied when adjusting scenario/projection data, so projected-era values are allowed to be exactly `0`.

   | Variable | Jitter threshold |
   |----------|-----------------|
   | `pr` | 0.01 mm d⁻¹ |
   | `dtr` | 1×10⁻⁴ K |
   | `snw` | 0.01 kg m⁻² |

2. **Frequency adaptation** (`adapt_freq`) — xclim's frequency-adaptation algorithm adjusts for differences in wet-day (or non-zero) frequency between the model and reference. Applied to `pr` and `snw` with a threshold of 0.254 mm d⁻¹ / kg m⁻² respectively.

### Multiplicative vs. additive adjustment

| Variable | Adjustment kind | Rationale |
|----------|----------------|-----------|
| `tasmax` | Additive (`+`) | Temperature differences are physically meaningful |
| `dtr` | Multiplicative (`*`) | Range must remain non-negative |
| `pr` | Multiplicative (`*`) | Ratio-based; preserves non-negativity |
| `snw` | Multiplicative (`*`) | Ratio-based; preserves non-negativity |
| `sfcWind`, `hurs`, `hursmin` | See `config.py` | Same rationale as above by variable type |

### Post-adjustment squeezing (physical bounds clipping)

After adjustment, outputs are clipped to physically defensible bounds to prevent tail extrapolation artifacts from propagating into the final dataset:

| Variable | Lower bound | Upper bound |
|----------|------------|------------|
| `tasmax` | _(none)_ | 333.15 K (60 °C) |
| `pr` | 0 mm d⁻¹ | 1,650 mm d⁻¹ |
| `dtr` | 0.0000002-quantile | 0.9999998-quantile (computed from histogram) |
| `tasmin` | 203.15 K (−70 °C) | _(none)_ |

`dtr` uses a quantile-based squeeze rather than fixed bounds because physically plausible DTR spans a wider range than temperature or precipitation and the tail extrapolation magnitude varies by domain. `tasmin` is derived after adjustment (see below) and its floor of 203.15 K corresponds to the lowest recorded surface air temperature on Earth.

### `tasmin` derivation

`tasmin` is not bias-adjusted directly. Instead it is derived as:

```
tasmin = adjusted_tasmax − adjusted_dtr
```

This ensures that `tasmin < tasmax` everywhere by construction and avoids the need for a separate QDM model for `tasmin`. DTR is trained and adjusted independently (see [Notes on special variables](#notes-on-special-variables)).

### Cascade regridding

Native CMIP6 grids (~1°) are orders of magnitude coarser than the target WRF-downscaled ERA5 grid (~4–12 km). A single interpolation step across this gap produces substantial error. The pipeline instead uses a two- or three-stage cascade that steps down through intermediate resolutions — see [Cascade regridding strategy](#cascade-regridding-strategy) for details.

### Land/sea masking

Land-only variables (`snw` and similar) use model-specific `sftlf` (land area fraction) files to mask ocean cells throughout the pipeline. The mask is regridded to each intermediate grid resolution alongside the data so that ocean cells remain masked at every cascade stage.

---

## Getting started

```bash
# 1. Clone the repo
git clone <repo-url>
cd cmip6-downscaling

# 2. Download the test data archive from the latest GitHub release and unzip it
#    (link: https://github.com/ua-snap/cmip6-downscaling/releases/latest)
cd test
unzip data_seward_peninsula_test.zip
cd ..

# 3. Create the conda environment (libmamba solver required)
conda env create -f environment.yml --solver=libmamba
conda activate cmip6-downscaling

# 4. Run the test pipeline
bash test/run_pipeline.sh /path/to/work_dir 12
```

The test run covers the Seward Peninsula, Alaska (see [Test Suite](#test-suite)). Processing time will vary based on your system.

---

## Table of Contents

1. [Methodology](#methodology)
2. [Overview](#overview)
3. [Required Dependencies](#required-dependencies)
4. [Input Data Requirements](#input-data-requirements)
5. [Pipeline Steps](#pipeline-steps)
6. [Configuration](#configuration)
7. [Output Directory Structure](#output-directory-structure)
8. [Parallelization](#parallelization)
9. [Test Suite](#test-suite)
10. [Variable Reference](#variable-reference)

---

## Overview

The pipeline performs five major operations, each composed of one or more scripts:

1. **Cascade Regridding** — Three-step regridding from native CMIP6 grids to the target WRF-downscaled ERA5 grid, reducing interpolation error when large grid-spacing differences are involved.
2. **DTR Derivation** (optional) — Compute Diurnal Temperature Range from raw CMIP6 tasmax and tasmin, and from WRF-downscaled ERA5 t2max/t2min, if `dtr` or `tasmin` is requested.
3. **NetCDF → Zarr Conversion** — Convert regridded CMIP6 and WRF-downscaled ERA5 reference data to Zarr for efficient random-access during bias adjustment.
4. **QDM Training** — Train a Quantile Delta Mapping model for each model/variable using the historical period, comparing CMIP6 against WRF-downscaled ERA5.
5. **Bias Adjustment** — Apply the trained QDM to all requested scenarios (historical and future).
6. **tasmin Derivation** (optional) — Compute bias-adjusted tasmin = adjusted tasmax − adjusted dtr.

---

## Required Dependencies

### Python environment

```bash
conda env create -f environment.yml --solver=libmamba
conda activate cmip6-downscaling
```

> **Note:** `--solver=libmamba` is required — the default conda solver hangs on this dependency set. If you don't have it, install it first: `conda install -n base conda-libmamba-solver`

See [environment.yml](environment.yml) for the full package list. Key packages:
- `xarray`, `xesmf`, `xclim`, `esmf`, `cf_xarray`, `dask`, `zarr`, `netcdf4`, `h5netcdf`
- `pyproj`, `numpy`, `pandas`, `cftime`

---

## Input Data Requirements

### CMIP6 data

Raw daily CMIP6 NetCDF files, organized in the standard CMIP6 DRS directory structure:

```
<cmip6_dir>/
├── ScenarioMIP/<institution>/<model>/<scenario>/<variant>/day/<variable>/<grid>/<version>/*.nc
└── CMIP/<institution>/<model>/historical/<variant>/day/<variable>/<grid>/<version>/*.nc
```

### WRF-downscaled ERA5 reference data

Daily WRF-downscaled ERA5 NetCDF files **already preprocessed** to the target grid resolution (4km or 12km), with one file per year per variable. The directory structure must be:

```
<era5_dir>/
├── <variable>/
│   ├── <variable>_<year>_era5_<resolution>km_3338.nc
│   ├── ...
```

#### WRF-downscaled ERA5 data provenance

The WRF-downscaled ERA5 files used with this pipeline were prepared in two steps:

**Step 1 — Hourly to daily aggregation** using the
[wrf-downscaled-era5-curation](https://github.com/ua-snap/wrf-downscaled-era5-curation)
repository. That pipeline ingests hourly WRF-downscaled ERA5 output (Chris Waigl, 2026: data release in progress) and produces
annual daily-frequency NetCDF files for each variable (e.g., daily maximum temperature,
daily precipitation accumulation, daily mean wind speed).

**Step 2 — Variable renaming and unit conversion** using
[`prep_era5_variables.py`](https://github.com/ua-snap/cmip6-utils/blob/main/downscaling/prep_era5_variables.py)
from the [cmip6-utils](https://github.com/ua-snap/cmip6-utils) repository. This script:
- Renames WRF output variable names to the conventions expected by this pipeline
  (e.g., `rainnc_sum` → `pr`, `t2_max` → `t2max`, `t2_min` → `t2min`)
- Renames the variable name inside each NetCDF file to match, along with directory
  and file names
- Converts temperature variables (`t2_max`, `t2_min`) from degrees Celsius to Kelvin

The `snow_mean` variable is passed through without renaming. The output of this step
is what is placed in the `<era5_dir>` expected by this pipeline.

#### Variable naming conventions

WRF-downscaled ERA5 variable directory names must match these expected names (the test suite provides
working examples of all required naming and format conventions):

| CMIP6 variable | WRF-downscaled ERA5 directory name | Notes |
|----------------|---------------------|-------|
| `tasmax` | `t2max` | Temperature in Kelvin |
| `tasmin` | `t2min` | Temperature in Kelvin |
| `dtr` | `dtr` | Computed from t2max − t2min |
| `pr` | `pr` | Precipitation |
| `hurs` | `rh2_mean` | Relative humidity |
| `hursmin` | `rh2_min` | Daily minimum relative humidity |
| `snw` | `snow_mean` | Snow amount |
| `sfcWind` | `wspd10_mean` | Wind speed |

See the [test suite](test/README.md) for concrete file format examples.

### Land/sea mask files (sftlf)

Required only for land-only variables (`snw`, `mrro`, `mrsol`, `mrsos`, `snd`). Provide one NetCDF file per model containing the `sftlf` variable (percentage land fraction). The test suite includes example sftlf files for the test models.

### Target grid files

The cascade regridding requires a target grid file at each stage. Both are generated automatically by the pipeline:
- The intermediate grid is derived from the first CMIP6 file found in the input directory.
- The final target grid is derived from the first WRF-ERA5 file found in the ERA5 input directory.


---

## Pipeline Steps

Run all scripts with `conda activate cmip6-downscaling` active. Each step below is a Python script that can be called directly.

> **Note on parallelization**: All launcher scripts (`run_*.py`) execute jobs sequentially. If you want to speed things up, see the [Parallelization](#parallelization) section.

---

### Prerequisites: edit `config.py`

Open [config.py](config.py) and set your run-specific parameters before starting:

```python
# Year ranges for training and projection
ERA5_START_YEAR = 1965
ERA5_END_YEAR = 2014
FUTURE_START_YEAR = 2015
FUTURE_END_YEAR = 2100

# Domain bounds (degrees, 0–360 longitude convention)
# Defaults are for Arctic 12km. Override for your domain.
DOMAIN_12KM = {"min_lon": 182, "max_lon": 254, "min_lat": 48, "max_lat": 77}
DOMAIN_4KM  = {"min_lon": 183, "max_lon": 232, "min_lat": 54, "max_lat": 73}
```

---

### Step 0: Compute CMIP6 DTR (only if running `dtr` or `tasmin`)

Compute diurnal temperature range from raw CMIP6 tasmax and tasmin files before regridding.

```bash
python derive/run_cmip6_dtr.py \
    --input_dir /path/to/cmip6_dir \
    --output_dir /path/to/run_dir/cmip6_dtr \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370" \
    --worker_script derive/dtr.py
```

---

### Step 1: Generate batch files

Scans the CMIP6 directory, groups files by model/scenario/variable/grid, and writes text "batch files" listing the files to be regridded. Batch files go in `<slurm_dir>/first_regrid/batch/`.

```bash
python regrid/generate_batch_files.py \
    --cmip6_directory /path/to/cmip6_dir \
    --regrid_batch_dir /path/to/run_dir/batches/first_regrid \
    --vars "tasmax pr" \
    --freqs "day" \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370"
```

If you also need DTR files regridded, run again pointing at the DTR output:

```bash
python regrid/generate_batch_files.py \
    --cmip6_directory /path/to/run_dir/cmip6_dtr \
    --regrid_batch_dir /path/to/run_dir/batches/first_regrid \
    --vars "dtr" \
    --freqs "day" \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370"
```

---

### Step 2: Create first intermediate target grid

Creates the first intermediate grid file (between native CMIP6 resolution and the final WRF-downscaled ERA5 grid). The `--step` argument controls the degree spacing.

```bash
python regrid/make_intermediate_target_grid_file.py \
    --src_file /path/to/any_cmip6_file.nc \
    --out_file /path/to/run_dir/first_regrid_target.nc \
    --step 0.5 \
    --resolution 12
```

For a custom domain, override the bounds:

```bash
python regrid/make_intermediate_target_grid_file.py \
    --src_file /path/to/any_cmip6_file.nc \
    --out_file /path/to/run_dir/first_regrid_target.nc \
    --step 0.5 \
    --min_lon 182 --max_lon 254 --min_lat 48 --max_lat 77
```

---

### Step 3: Regrid land masks to first intermediate grid (land variables only)

Only needed if processing land-only variables (`snw`, etc.).

```bash
python regrid/regrid_sftlf_to_target.py \
    --source_sftlf /path/to/GFDL-ESM4_sftlf.nc \
    --target_grid /path/to/run_dir/first_regrid_target.nc \
    --output_sftlf /path/to/run_dir/first_sftlf/first_regrid_target_sftlf_GFDL-ESM4.nc
```

Run once per model.

---

### Step 4: First regrid (native CMIP6 → intermediate grid 1)

Regrids all files listed in the batch files to the first intermediate grid.

```bash
python regrid/run_first_regrid.py \
    --batch_dir /path/to/run_dir/batches/first_regrid \
    --target_grid /path/to/run_dir/first_regrid_target.nc \
    --output_dir /path/to/run_dir/first_regrid \
    --interp_method bilinear \
    --worker_script regrid/regrid.py
```

For land variables, add `--sftlf_dir /path/to/run_dir/first_sftlf`.

> **Interpolation method**: Use `bilinear` for all variables except `snw` (use `conservative`). Do not mix methods in a single run if `snw` is combined with other variables.

---

### Step 5: Create second intermediate target grid

```bash
python regrid/make_intermediate_target_grid_file.py \
    --src_file /path/to/any_cmip6_file.nc \
    --out_file /path/to/run_dir/second_regrid_target.nc \
    --step 0.25 \
    --resolution 12
```

---

### Step 6: Regrid land masks to second intermediate grid (land variables only)

```bash
python regrid/regrid_sftlf_to_target.py \
    --source_sftlf /path/to/GFDL-ESM4_sftlf.nc \
    --target_grid /path/to/run_dir/second_regrid_target.nc \
    --output_sftlf /path/to/run_dir/second_sftlf/second_regrid_target_sftlf_GFDL-ESM4.nc
```

---

### Step 7: Second regrid (intermediate grid 1 → intermediate grid 2)

```bash
python regrid/run_cascade_regrid.py \
    --input_dir /path/to/run_dir/first_regrid \
    --target_grid /path/to/run_dir/second_regrid_target.nc \
    --output_dir /path/to/run_dir/second_regrid \
    --interp_method bilinear \
    --stage second \
    --worker_script regrid/regrid.py
```

---

### Step 8: Create final target grid from ERA5 file

Extracts the first time slice from a WRF-downscaled ERA5 file to use as the final regridding target.

```bash
python regrid/make_final_target_grid_file.py \
    /path/to/era5/t2max/t2max_1965_era5_12km_3338.nc \
    /path/to/run_dir/final_regrid_target.nc
```

Or use a bundled default:

```bash
cp regrid/default_target_grids/era5_12km_default_target_grid.nc \
   /path/to/run_dir/final_regrid_target.nc
```

---

### Step 9: Regrid land masks to final (WRF-downscaled ERA5) grid (land variables only)

```bash
python regrid/regrid_sftlf_to_target.py \
    --source_sftlf /path/to/GFDL-ESM4_sftlf.nc \
    --target_grid /path/to/run_dir/final_regrid_target.nc \
    --output_sftlf /path/to/run_dir/final_sftlf/final_regrid_target_sftlf_GFDL-ESM4.nc
```

---

### Step 10: Final regrid (intermediate grid 2 → WRF-downscaled ERA5 grid)

```bash
python regrid/run_cascade_regrid.py \
    --input_dir /path/to/run_dir/second_regrid \
    --target_grid /path/to/run_dir/final_regrid_target.nc \
    --output_dir /path/to/run_dir/final_regrid \
    --interp_method bilinear \
    --stage final \
    --worker_script regrid/regrid.py
```

---

### Step 11: Compute WRF-downscaled ERA5 DTR (only if running `dtr` or `tasmin`)

```bash
python derive/run_era5_dtr.py \
    --era5_dir /path/to/era5 \
    --output_dir /path/to/era5/dtr \
    --resolution 12 \
    --worker_script derive/dtr.py
```

---

### Step 12: Convert CMIP6 regridded data to Zarr

```bash
python bias_adjust/run_cmip6_netcdf_to_zarr.py \
    --netcdf_dir /path/to/run_dir/final_regrid \
    --output_dir /path/to/run_dir/cmip6_zarr \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370" \
    --variables "tasmax pr" \
    --worker_script bias_adjust/netcdf_to_zarr.py
```

---

### Step 13: Convert WRF_downscaled ERA5 data to Zarr

```bash
python bias_adjust/run_era5_netcdf_to_zarr.py \
    --netcdf_dir /path/to/era5 \
    --output_dir /path/to/run_dir/era5_zarr \
    --variables "t2max pr" \
    --resolution 12 \
    --worker_script bias_adjust/netcdf_to_zarr.py
```

---

### Step 14: Train QDM bias adjustment

Trains one QDM model per model/variable combination using the historical period only.

```bash
python bias_adjust/run_train_qm.py \
    --sim_dir /path/to/run_dir/cmip6_zarr \
    --ref_dir /path/to/run_dir/era5_zarr \
    --output_dir /path/to/run_dir/trained_datasets \
    --tmp_dir /path/to/run_dir/tmp \
    --models "GFDL-ESM4 CESM2" \
    --variables "tasmax pr" \
    --era5_start_year 1965 \
    --era5_end_year 2014 \
    --worker_script bias_adjust/train_qm.py
```

---

### Step 15: Apply bias adjustment

Applies the trained QDM to all requested scenarios (historical and future).

```bash
python bias_adjust/run_bias_adjust.py \
    --sim_dir /path/to/run_dir/cmip6_zarr \
    --train_dir /path/to/run_dir/trained_datasets \
    --output_dir /path/to/run_dir/adjusted \
    --tmp_dir /path/to/run_dir/tmp \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370" \
    --variables "tasmax pr" \
    --worker_script bias_adjust/bias_adjust.py
```

---

### Step 16: Derive tasmin (only if `tasmin` was requested)

Computes tasmin = adjusted tasmax − adjusted dtr.

```bash
python derive/run_difference.py \
    --input_dir /path/to/run_dir/adjusted \
    --output_dir /path/to/run_dir/adjusted \
    --minuend_template "tasmax_{model}_{scenario}_adjusted.zarr" \
    --subtrahend_template "dtr_{model}_{scenario}_adjusted.zarr" \
    --output_template "tasmin_{model}_{scenario}_adjusted.zarr" \
    --new_var_id tasmin \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370" \
    --worker_script derive/difference.py
```

---

## Configuration

[config.py](config.py) is the **single file to edit** when adapting the pipeline to a new domain or compute environment. All pipeline scripts import from it; no other files need to be changed for the settings below.

### Year ranges

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ERA5_START_YEAR` | `1965` | First year of WRF-downscaled ERA5 reference data for training |
| `ERA5_END_YEAR` | `2014` | Last year of WRF-downscaled ERA5 reference data for training |
| `FUTURE_START_YEAR` | `2015` | First year of future scenarios |
| `FUTURE_END_YEAR` | `2100` | Last year of future scenarios |

### Domain bounds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DOMAIN_4KM` | Arctic 4km bounds | `{min_lon, max_lon, min_lat, max_lat}` (0–360 lon) |
| `DOMAIN_12KM` | Arctic 12km bounds | `{min_lon, max_lon, min_lat, max_lat}` (0–360 lon) |

### Dask cluster resources

All five worker scripts (`regrid.py`, `train_qm.py`, `bias_adjust.py`, `dtr.py`, `difference.py`) read these values from `config.py`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DASK_N_WORKERS` | `4` | Number of worker processes |
| `DASK_THREADS_PER_WORKER` | `4` | Threads per process |
| `DASK_MEMORY_LIMIT` | `"28GB"` | Memory cap per worker |
| `DASK_MEMORY_TARGET` | `0.70` | Fraction at which workers start managing memory |
| `DASK_MEMORY_SPILL` | `0.80` | Fraction at which workers spill to disk |
| `DASK_MEMORY_PAUSE` | `0.85` | Fraction at which workers pause accepting tasks |
| `DASK_MEMORY_TERMINATE` | `0.95` | Fraction at which workers are killed |
| `DASK_ARRAY_CHUNK_SIZE` | `"128 MiB"` | Target size for individual array chunks |

**Total memory used = `DASK_N_WORKERS × DASK_MEMORY_LIMIT`.** With the defaults, the cluster uses ~112 GB. A practical starting point for other machines:

```python
# For a machine with T GB of RAM and C CPU cores:
DASK_N_WORKERS = C // 4
DASK_MEMORY_LIMIT = f"{int(T * 0.8 / n_workers)}GB"  # leave 20% for the OS
```

Example — **32 GB / 8-core laptop**: `DASK_N_WORKERS = 2`, `DASK_MEMORY_LIMIT = "12GB"` (24 GB total)

Example — **256 GB / 32-core workstation**: `DASK_N_WORKERS = 8`, `DASK_MEMORY_LIMIT = "28GB"` (224 GB total)

> **Note:** `train_qm.py` and `bias_adjust.py` require the entire time dimension to be a single chunk (`time=-1`). This is an xclim requirement for QDM. If you reduce `DASK_MEMORY_LIMIT` significantly, also reduce the spatial chunk sizes (`x`/`y`) in the rechunking calls inside those scripts to keep individual chunks below your worker memory limit.

### QDM training parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `QDM_NQUANTILES` | `100` | Number of quantiles used to build empirical CDFs |
| `QDM_WINDOW` | `31` | Day-of-year window half-width (31 = ±15 days around each calendar day) |

### Post-adjustment squeeze bounds

After bias adjustment, outputs are clipped to these physically defensible limits. See [Post-adjustment squeezing](#post-adjustment-squeezing-physical-bounds-clipping) for rationale.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SQUEEZE_TASMAX_MAX` | `333.15` K | Upper ceiling for tasmax (60 °C) |
| `SQUEEZE_PR_MIN` | `0` mm d⁻¹ | Lower floor for precipitation |
| `SQUEEZE_PR_MAX` | `1650` mm d⁻¹ | Upper ceiling for precipitation |
| `SQUEEZE_DTR_LOWER_QUANTILE` | `0.0000002` | Lower tail quantile for DTR squeeze |
| `SQUEEZE_DTR_UPPER_QUANTILE` | `0.9999998` | Upper tail quantile for DTR squeeze |
| `SQUEEZE_TASMIN_MIN` | `203.15` K | Lower floor for tasmin (−70 °C) |

### Regridding

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CASCADE_BATCH_SIZE` | `200` | Files processed per subprocess call in cascade regridding |

Variable-to-ERA5 name mappings and adjustment type (additive/multiplicative) are defined in [config.py](config.py) (`sim_ref_var_lu`, `varid_adj_kind_lu`).

---

## Output Directory Structure

After a full run, your output directory will look like:

```
<run_dir>/
├── batches/
│   └── first_regrid/          # Text files listing CMIP6 files for first regrid
├── first_regrid/              # Intermediate regrid step 1
│   └── <model>/<scenario>/day/<variable>/
├── second_regrid/             # Intermediate regrid step 2
│   └── <model>/<scenario>/day/<variable>/
├── final_regrid/              # Final regridded NetCDF (on ERA5 grid)
│   └── <model>/<scenario>/day/<variable>/
├── cmip6_dtr/                 # CMIP6 DTR files (if requested)
├── cmip6_zarr/                # CMIP6 Zarr stores
│   └── <variable>_<model>_<scenario>.zarr/
├── era5_zarr/                 # ERA5 Zarr stores
│   └── <variable>_era5.zarr/
├── trained_datasets/          # Trained QDM weights
│   └── trained_qdm_<variable>_<model>.zarr/
├── adjusted/                  # ⭐ Final downscaled output
│   └── <variable>_<model>_<scenario>_adjusted.zarr/
├── first_regrid_target.nc
├── second_regrid_target.nc
└── final_regrid_target.nc
```

### Converting output Zarr to NetCDF

```python
import xarray as xr
ds = xr.open_zarr("adjusted/tasmax_GFDL-ESM4_historical_adjusted.zarr")
ds.to_netcdf("tasmax_GFDL-ESM4_historical_adjusted.nc")
```

---

## Parallelization

All `run_*.py` launcher scripts are sequential by design. To parallelize:

**Option 1 — Run multiple launcher instances in parallel** (simplest):
```bash
# In separate terminals or background processes
python bias_adjust/run_train_qm.py --models "GFDL-ESM4" --variables "tasmax pr" ... &
python bias_adjust/run_train_qm.py --models "CESM2" --variables "tasmax pr" ... &
wait
```

**Option 2 — Call the worker scripts directly in a loop** (maximum control):
Each `run_*.py` script is a thin loop that calls a `worker_script`. You can replicate that loop with your own parallelism (GNU parallel, Python multiprocessing, etc.).

**Option 3 — Use the worker scripts in a Jupyter notebook**:
Import the worker functions directly and call them in whatever order suits your workflow.

---

## Dask cluster configuration

All Dask settings are centralised in [config.py](config.py). See the [Dask cluster resources](#dask-cluster-resources) table in the Configuration section above for the full parameter list and sizing guidance.

---

## Test Suite

See [test/README.md](test/README.md) for a complete walkthrough using the bundled test data.

The test domain is the **Seward Peninsula, Alaska** — a small 4×8 cell CMIP6 clip (~63–68°N, 168–159°W) paired with a 62×70 cell WRF-downscaled ERA5 clip at 12 km resolution. It exercises the full pipeline with one model (MIROC6), two scenarios (historical 2000–2009, ssp370 2045–2054), and four variables (`pr`, `snw`, `tasmax`, `tasmin`). The DTR derivation path is fully exercised.

Download the test data archive from `[https://github.com/ua-snap/cmip6-downscaling/releases/download/v0.1.1/data_seward_peninsula_test.zip]` and unzip it into `test/data/` before running.

```bash
bash test/run_pipeline.sh /path/to/work_dir 12
```

---

## Variable Reference

### Supported variables

| CMIP6 ID | WRF-downscaled ERA5 ID | Adjustment | Interpolation | Land-only | Zero-inflated |
|----------|---------|------------|---------------|-----------|---------------|
| `tasmax` | `t2max` | additive (+) | bilinear | No | No |
| `tasmin` | `t2min` | additive (+) | bilinear | No | No |
| `tas` | `t2` | additive (+) | bilinear | No | No |
| `dtr` | `dtr` | multiplicative (*) | bilinear | No | Yes |
| `pr` | `pr` | multiplicative (*) | bilinear | No | Yes |
| `hurs` | `rh2_mean` | additive (+) | bilinear | No | No |
| `hursmin` | `rh2_min` | additive (+) | bilinear | No | No |
| `snw` | `snow_mean` | multiplicative (*) | **conservative** | Yes | Yes |
| `sfcWind` | `wspd10_mean` | multiplicative (*) | bilinear | No | No |

### Notes on special variables

- **`dtr`** — Must be derived from tasmax and tasmin before regridding (Step 0). Run both CMIP6 DTR (Step 0) and WRF-downscaled ERA5 DTR (Step 11).
- **`tasmin`** — Can be processed directly OR derived as tasmax − dtr after bias adjustment (Step 16). The derivation approach is generally preferred.
- **`snw`** — Uses conservative interpolation (not bilinear). Do not mix `snw` with other variables in the same batch run, as different interpolation methods cannot be combined.
- **Zero-inflated variables** (`pr`, `dtr`, `snw`) — The QDM applies jitter preprocessing and frequency adaptation automatically (configured in `config.py` via `jitter_under_lu` and `adapt_freq_thresh_lu`).

### Cascade regridding strategy

Three-step regridding minimizes interpolation error when native CMIP6 grids are much coarser than the target WRF-downscaled ERA5 grid:

1. **Step ~0.5°** — Large intermediate grid (step=0.5 for `make_intermediate_target_grid_file.py`)
2. **Step ~0.25°** — Smaller intermediate grid (step=0.25)
3. **Final** — WRF-downscaled ERA5 target resolution (~4km or ~12km)

Land/sea masking is applied at every regridding stage using model-specific `sftlf` files regridded to each intermediate grid resolution.
