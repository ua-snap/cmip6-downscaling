# Test Suite

This directory contains a minimal end-to-end test for the downscaling pipeline.

## Test domain

The test data covers the **Seward Peninsula, Alaska** — a small geographic region chosen to keep file sizes manageable while exercising the full pipeline.

| | Detail |
|---|---|
| **Region** | Seward Peninsula, Alaska (approx. 63–68°N, 168–159°W) |
| **CMIP6 clip** | 4×8 grid cells (native MIROC6 resolution ~1.4°) |
| **WRF-ERA5 clip** | 62×70 grid cells at 12 km (EPSG:3338) |
| **Model** | MIROC6 |
| **Scenarios** | historical (2000–2009), ssp370 (2045–2054) |
| **Variables** | `pr` (precipitation), `snw` (snow amount) |

This is not a scientifically meaningful domain — it is purely a functional test to verify that each pipeline step runs without error and produces non-empty output.

## Test data layout

```
test/data/
├── cmip6/
│   ├── CMIP/MIROC/MIROC6/historical/r1i1p1f1/day/
│   │   ├── pr/gn/v20191016/pr_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   └── snw/gn/v20191016/snw_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   ├── ScenarioMIP/MIROC/MIROC6/ssp370/r1i1p1f1/day/
│   │   ├── pr/gn/v20191016/pr_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   └── snw/gn/v20191016/snw_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   └── sftlf/
│       └── sftlf_fx_MIROC6_historical_r1i1p1f1_gn.nc
└── wrf_era5/
    ├── pr/
    │   └── pr_{2000..2009}_daily_era5_12km_3338.nc
    └── snow_sum/
        └── snow_sum_{2000..2009}_daily_era5_12km_3338.nc
```

CMIP6 training period: 2000–2009 (historical). Future scenario: ssp370 2045–2054.

**Note:** The `wrf_era5` files are WRF-downscaled ERA5 at 12 km resolution (EPSG:3338),
not raw ERA5. They are clipped to the Seward Peninsula, Alaska test domain.

**Obtaining test data:** Download `data_seward_peninsula_test.zip` from the
[latest GitHub release](https://github.com/ua-snap/cmip6-downscaling/releases/latest)
and unzip it here:

```bash
cd cmip6-downscaling/test
unzip data_seward_peninsula_test.zip
```

This produces the `test/data/` directory with the layout shown above.
Do not commit `test/data/` to the repo — it is covered by `.gitignore`.

## Required dependencies (beyond the conda environment)

- CDO: used by `regrid.py` for bilinear/conservative interpolation.
  Install: `conda install -c conda-forge cdo`

## Running the full pipeline on test data

```bash
cd test
bash run_pipeline.sh /path/to/work_dir 12
```

Arguments:
- `work_dir`: writable directory for all intermediate and final outputs
- `resolution`: `4` or `12` (km); controls domain bounds in cascade regridding

## Pipeline steps

| Step | Script | Description |
|------|--------|-------------|
| 1 | `regridding/make_intermediate_target_grid_file.py` | Create 0.5° intermediate cascade grid |
| 2 | `regridding/regrid_sftlf_to_target.py` | Regrid sftlf to intermediate grid |
| 3 | `regridding/generate_batch_files.py` | Scan CMIP6 dir, write batch .txt files |
| 4 | `regridding/run_first_regrid.py` | Regrid CMIP6 → intermediate grid |
| 5 | `regridding/run_cascade_regrid.py` | Regrid intermediate → ERA5 target |
| 6 | `regridding/make_final_target_grid_file.py` | Extract ERA5 slice as final target grid |
| 7 | `derived/run_cmip6_dtr.py` | Compute CMIP6 DTR (if needed) |
| 8 | `derived/run_era5_dtr.py` | Compute ERA5 DTR (if needed) |
| 9 | `bias_adjust/run_cmip6_netcdf_to_zarr.py` | Convert regridded CMIP6 → Zarr |
| 10 | `bias_adjust/run_era5_netcdf_to_zarr.py` | Convert ERA5 → Zarr |
| 11 | `bias_adjust/run_train_qm.py` | Train QDM bias adjustment models |
| 12 | `bias_adjust/run_bias_adjust.py` | Apply bias adjustment |
| 13 | `derived/run_difference.py` | Derive tasmin = tasmax − dtr (if needed) |

## Expected outputs

After a successful run on the test data:

```
work_dir/
├── intermediate_target.nc      # 0.5° intermediate grid
├── final_target.nc             # ERA5 slice (final target grid)
├── first_regrid/               # CMIP6 → intermediate regridded files
├── cascade_batch/              # Batch files for cascade stage
├── second_regrid/              # Intermediate → ERA5 regridded files
├── cmip6_zarr/                 # Zarr stores of regridded CMIP6 data
├── era5_zarr/                  # Zarr stores of ERA5 data
├── trained/                    # Trained QDM model stores
└── adjusted/                   # Bias-adjusted output stores
```

## WRF-ERA5 file format

WRF-ERA5 files must have the following structure expected by `netcdf_to_zarr.py`:
- Time dimension with daily values
- Variable named matching the ERA5 variable ID (e.g., `t2max`)
- Projected coordinates (x/y) in EPSG:3338 with a `spatial_ref` coordinate,
  **or** geographic coordinates (lat/lon)

ERA5 variable names (ERA5 ID → CMIP6 variable):
- `t2max` → `tasmax`
- `t2min` → `tasmin`
- `pr` → `pr`
- `snow_sum` → `snw`
- `rh2_mean` → `hurs`
- `wspd10_mean` → `sfcWind`
- `dtr` → `dtr` (derived, not a raw ERA5 variable)
