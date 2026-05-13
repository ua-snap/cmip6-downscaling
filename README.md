# CMIP6 Statistical Downscaling

Standalone pipeline for statistically downscaling daily CMIP6 climate model data to high-resolution grids using Quantile Delta Mapping (QDM) bias adjustment with dynamically downscaled ERA5 as the reference dataset.

This repo packages the core computation scripts from the [cmip6-utils](https://github.com/ua-snap/cmip6-utils) repository into a form that can be run sequentially on any infrastructure — no Prefect, no SLURM, no HPC required. Each script is a standalone tool; you chain them together using bash scripts, a Jupyter notebook, or any other method you prefer.

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

# 3. Create the conda environment
conda env create -f environment.yml
conda activate cmip6-downscaling

# 4. Run the test pipeline
bash test/run_pipeline.sh /path/to/work_dir 12
```

The test run covers the Seward Peninsula, Alaska (see [Test Suite](#test-suite)). Processing time will vary based on your system.

---

## Table of Contents

1. [Overview](#overview)
2. [Required Dependencies](#required-dependencies)
3. [Input Data Requirements](#input-data-requirements)
4. [Pipeline Steps](#pipeline-steps)
5. [Configuration](#configuration)
6. [Output Directory Structure](#output-directory-structure)
7. [Parallelization](#parallelization)
8. [Test Suite](#test-suite)
9. [Variable Reference](#variable-reference)

---

## Overview

The pipeline performs five major operations, each composed of one or more scripts:

1. **Cascade Regridding** — Three-step regridding from native CMIP6 grids to the target ERA5 grid, reducing interpolation error when large grid-spacing differences are involved.
2. **DTR Derivation** (optional) — Compute Diurnal Temperature Range from raw CMIP6 tasmax and tasmin, and from ERA5 t2max/t2min, if `dtr` or `tasmin` is requested.
3. **NetCDF → Zarr Conversion** — Convert regridded CMIP6 and ERA5 reference data to Zarr for efficient random-access during bias adjustment.
4. **QDM Training** — Train a Quantile Delta Mapping model for each model/variable using the historical period, comparing CMIP6 against ERA5.
5. **Bias Adjustment** — Apply the trained QDM to all requested scenarios (historical and future).
6. **tasmin Derivation** (optional) — Compute bias-adjusted tasmin = adjusted tasmax − adjusted dtr.

---

## Required Dependencies

### External tools

| Tool | Install | Used for |
|------|---------|----------|
| **CDO** (Climate Data Operators) | `conda install -c conda-forge cdo` | All regridding steps |

CDO must be available on your `PATH`. Verify with `cdo --version`.

### Python environment

```bash
conda env create -f environment.yml
conda activate cmip6-downscaling
```

See [environment.yml](environment.yml) for the full package list. Key packages:
- `xarray`, `xesmf`, `xclim`, `dask`, `zarr`, `netcdf4`, `h5netcdf`
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

### ERA5 reference data

Daily ERA5 NetCDF files **already preprocessed** to your target grid resolution (4km or 12km), with one file per year per variable. The directory structure must be:

```
<era5_dir>/
├── <variable>/
│   ├── <variable>_<year>_era5_<resolution>km_3338.nc
│   ├── ...
```

#### ERA5 data provenance

The ERA5 files used with this pipeline were prepared in two steps:

**Step 1 — Hourly to daily aggregation** using the
[wrf-downscaled-era5-curation](https://github.com/ua-snap/wrf-downscaled-era5-curation)
repository. That pipeline ingests hourly WRF-downscaled ERA5 output and produces
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

The `snow_sum` variable is passed through without renaming. The output of this step
is what is placed in the `<era5_dir>` expected by this pipeline.

#### Variable naming conventions

ERA5 variable directory names must match these expected names (the test suite provides
working examples of all required naming and format conventions):

| CMIP6 variable | ERA5 directory name | Notes |
|----------------|---------------------|-------|
| `tasmax` | `t2max` | Temperature in Kelvin |
| `tasmin` | `t2min` | Temperature in Kelvin |
| `dtr` | `dtr` | Computed from t2max − t2min |
| `pr` | `pr` | Precipitation |
| `hurs` | `rh2_mean` | Relative humidity |
| `hursmin` | `rh2_min` | Daily minimum relative humidity |
| `snw` | `snow_sum` | Snow amount |
| `sfcWind` | `wspd10_mean` | Wind speed |

See the [test suite](test/README.md) for concrete file format examples.

### Land/sea mask files (sftlf)

Required only for land-only variables (`snw`, `mrro`, `mrsol`, `mrsos`, `snd`). Provide one NetCDF file per model containing the `sftlf` variable (percentage land fraction). The test suite includes example sftlf files for the test models.

### Target grid files

The cascade regridding requires a target grid file at each stage. These are generated by scripts in this pipeline. You will also need:
- One raw CMIP6 file (any variable) to use as the coordinate template for the intermediate grids.
- One ERA5 file to use as the template for the final target grid.

Default ERA5 target grid files for 4km and 12km Arctic grids are bundled in `regridding/default_target_grids/`.

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
python derived/run_cmip6_dtr.py \
    --input_dir /path/to/cmip6_dir \
    --output_dir /path/to/run_dir/cmip6_dtr \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370" \
    --worker_script derived/dtr.py
```

---

### Step 1: Generate batch files

Scans the CMIP6 directory, groups files by model/scenario/variable/grid, and writes text "batch files" listing the files to be regridded. Batch files go in `<slurm_dir>/first_regrid/batch/`.

```bash
python regridding/generate_batch_files.py \
    --cmip6_directory /path/to/cmip6_dir \
    --regrid_batch_dir /path/to/run_dir/batches/first_regrid \
    --vars "tasmax pr" \
    --freqs "day" \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370"
```

If you also need DTR files regridded, run again pointing at the DTR output:

```bash
python regridding/generate_batch_files.py \
    --cmip6_directory /path/to/run_dir/cmip6_dtr \
    --regrid_batch_dir /path/to/run_dir/batches/first_regrid \
    --vars "dtr" \
    --freqs "day" \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370"
```

---

### Step 2: Create first intermediate target grid

Creates the first intermediate grid file (between native CMIP6 resolution and the final ERA5 grid). The `--step` argument controls the degree spacing.

```bash
python regridding/make_intermediate_target_grid_file.py \
    --src_file /path/to/any_cmip6_file.nc \
    --out_file /path/to/run_dir/first_regrid_target.nc \
    --step 0.5 \
    --resolution 12
```

For a custom domain, override the bounds:

```bash
python regridding/make_intermediate_target_grid_file.py \
    --src_file /path/to/any_cmip6_file.nc \
    --out_file /path/to/run_dir/first_regrid_target.nc \
    --step 0.5 \
    --min_lon 182 --max_lon 254 --min_lat 48 --max_lat 77
```

---

### Step 3: Regrid land masks to first intermediate grid (land variables only)

Only needed if processing land-only variables (`snw`, etc.).

```bash
python regridding/regrid_sftlf_to_target.py \
    --source_sftlf /path/to/GFDL-ESM4_sftlf.nc \
    --target_grid /path/to/run_dir/first_regrid_target.nc \
    --output_sftlf /path/to/run_dir/first_sftlf/first_regrid_target_sftlf_GFDL-ESM4.nc
```

Run once per model.

---

### Step 4: First regrid (native CMIP6 → intermediate grid 1)

Regrids all files listed in the batch files to the first intermediate grid.

```bash
python regridding/run_first_regrid.py \
    --batch_dir /path/to/run_dir/batches/first_regrid \
    --target_grid /path/to/run_dir/first_regrid_target.nc \
    --output_dir /path/to/run_dir/first_regrid \
    --interp_method bilinear \
    --worker_script regridding/regrid.py
```

For land variables, add `--sftlf_dir /path/to/run_dir/first_sftlf`.

> **Interpolation method**: Use `bilinear` for all variables except `snw` (use `conservative`). Do not mix methods in a single run if `snw` is combined with other variables.

---

### Step 5: Create second intermediate target grid

```bash
python regridding/make_intermediate_target_grid_file.py \
    --src_file /path/to/any_cmip6_file.nc \
    --out_file /path/to/run_dir/second_regrid_target.nc \
    --step 0.25 \
    --resolution 12
```

---

### Step 6: Regrid land masks to second intermediate grid (land variables only)

```bash
python regridding/regrid_sftlf_to_target.py \
    --source_sftlf /path/to/GFDL-ESM4_sftlf.nc \
    --target_grid /path/to/run_dir/second_regrid_target.nc \
    --output_sftlf /path/to/run_dir/second_sftlf/second_regrid_target_sftlf_GFDL-ESM4.nc
```

---

### Step 7: Second regrid (intermediate grid 1 → intermediate grid 2)

```bash
python regridding/run_cascade_regrid.py \
    --input_dir /path/to/run_dir/first_regrid \
    --target_grid /path/to/run_dir/second_regrid_target.nc \
    --output_dir /path/to/run_dir/second_regrid \
    --interp_method bilinear \
    --stage second \
    --worker_script regridding/regrid.py
```

---

### Step 8: Create final target grid from ERA5 file

Extracts the first time slice from an ERA5 file to use as the final regridding target.

```bash
python regridding/make_final_target_grid_file.py \
    /path/to/era5/t2max/t2max_1965_era5_12km_3338.nc \
    /path/to/run_dir/final_regrid_target.nc
```

Or use a bundled default:

```bash
cp regridding/default_target_grids/era5_12km_default_target_grid.nc \
   /path/to/run_dir/final_regrid_target.nc
```

---

### Step 9: Regrid land masks to final (ERA5) grid (land variables only)

```bash
python regridding/regrid_sftlf_to_target.py \
    --source_sftlf /path/to/GFDL-ESM4_sftlf.nc \
    --target_grid /path/to/run_dir/final_regrid_target.nc \
    --output_sftlf /path/to/run_dir/final_sftlf/final_regrid_target_sftlf_GFDL-ESM4.nc
```

---

### Step 10: Final regrid (intermediate grid 2 → ERA5 grid)

```bash
python regridding/run_cascade_regrid.py \
    --input_dir /path/to/run_dir/second_regrid \
    --target_grid /path/to/run_dir/final_regrid_target.nc \
    --output_dir /path/to/run_dir/final_regrid \
    --interp_method bilinear \
    --stage final \
    --worker_script regridding/regrid.py
```

---

### Step 11: Compute ERA5 DTR (only if running `dtr` or `tasmin`)

```bash
python derived/run_era5_dtr.py \
    --era5_dir /path/to/era5 \
    --output_dir /path/to/era5/dtr \
    --resolution 12 \
    --worker_script derived/dtr.py
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

### Step 13: Convert ERA5 data to Zarr

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
python derived/run_difference.py \
    --input_dir /path/to/run_dir/adjusted \
    --output_dir /path/to/run_dir/adjusted \
    --minuend_template "tasmax_{model}_{scenario}_adjusted.zarr" \
    --subtrahend_template "dtr_{model}_{scenario}_adjusted.zarr" \
    --output_template "tasmin_{model}_{scenario}_adjusted.zarr" \
    --new_var_id tasmin \
    --models "GFDL-ESM4 CESM2" \
    --scenarios "historical ssp370" \
    --worker_script derived/difference.py
```

---

## Configuration

Open [config.py](config.py) to adjust the following parameters before running:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ERA5_START_YEAR` | `1965` | First year of ERA5 reference data for training |
| `ERA5_END_YEAR` | `2014` | Last year of ERA5 reference data for training |
| `FUTURE_START_YEAR` | `2015` | First year of future scenarios |
| `FUTURE_END_YEAR` | `2100` | Last year of future scenarios |
| `DOMAIN_4KM` | Arctic 4km bounds | `{min_lon, max_lon, min_lat, max_lat}` |
| `DOMAIN_12KM` | Arctic 12km bounds | `{min_lon, max_lon, min_lat, max_lat}` |

Variable-to-ERA5 name mappings and adjustment type (additive/multiplicative) are defined in [bias_adjust/luts.py](bias_adjust/luts.py).

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

## Test Suite

See [test/README.md](test/README.md) for a complete walkthrough using the bundled test data.

The test domain is the **Seward Peninsula, Alaska** — a small 4×8 cell CMIP6 clip (~63–68°N, 168–159°W) paired with a 62×70 cell WRF-ERA5 clip at 12 km resolution. It exercises the full pipeline with one model (MIROC6), two scenarios (historical 2000–2009, ssp370 2045–2054), and two variables (`pr`, `snw`).

Download the test data archive from `[link TBD]` and unzip it into `test/data/` before running.

```bash
bash test/run_pipeline.sh /path/to/work_dir 12
```

---

## Variable Reference

### Supported variables

| CMIP6 ID | ERA5 ID | Adjustment | Interpolation | Land-only | Zero-inflated |
|----------|---------|------------|---------------|-----------|---------------|
| `tasmax` | `t2max` | additive (+) | bilinear | No | No |
| `tasmin` | `t2min` | additive (+) | bilinear | No | No |
| `tas` | `t2` | additive (+) | bilinear | No | No |
| `dtr` | `dtr` | multiplicative (*) | bilinear | No | Yes |
| `pr` | `pr` | multiplicative (*) | bilinear | No | Yes |
| `hurs` | `rh2_mean` | additive (+) | bilinear | No | No |
| `hursmin` | `rh2_min` | additive (+) | bilinear | No | No |
| `snw` | `snow_sum` | multiplicative (*) | **conservative** | Yes | Yes |
| `sfcWind` | `wspd10_mean` | multiplicative (*) | bilinear | No | No |

### Notes on special variables

- **`dtr`** — Must be derived from tasmax and tasmin before regridding (Step 0). Run both CMIP6 DTR (Step 0) and ERA5 DTR (Step 11).
- **`tasmin`** — Can be processed directly OR derived as tasmax − dtr after bias adjustment (Step 16). The derivation approach is generally preferred.
- **`snw`** — Uses conservative interpolation (not bilinear). Do not mix `snw` with other variables in the same batch run, as different interpolation methods cannot be combined.
- **Zero-inflated variables** (`pr`, `dtr`, `snw`) — The QDM applies jitter preprocessing and frequency adaptation automatically (configured in `bias_adjust/luts.py`).

### Cascade regridding strategy

Three-step regridding minimizes interpolation error when native CMIP6 grids are much coarser than the target ERA5 grid:

1. **Step ~0.5°** — Large intermediate grid (step=0.5 for `make_intermediate_target_grid_file.py`)
2. **Step ~0.25°** — Smaller intermediate grid (step=0.25)
3. **Final** — ERA5 target resolution (~4km or ~12km)

Land/sea masking is applied at every regridding stage using model-specific `sftlf` files regridded to each intermediate grid resolution.
