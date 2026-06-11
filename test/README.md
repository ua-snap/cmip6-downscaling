# Test Suite

This directory contains a minimal end-to-end test for the downscaling pipeline.

## Test domain

The test data covers the **Seward Peninsula, Alaska**, a small geographic region chosen to keep file sizes manageable while exercising the full pipeline.

| | Detail |
|---|---|
| **Region** | Seward Peninsula, Alaska (approx. 63–68°N, 168–159°W) |
| **CMIP6 clip** | 4×8 grid cells (native MIROC6 resolution ~1.4°) |
| **WRF-downscaled ERA5 clip** | 62×70 grid cells at 12 km (EPSG:3338) |
| **Model** | MIROC6 |
| **Scenarios** | historical (2000–2009), ssp370 (2045–2054) |
| **Variables** | `pr`, `snw`, `tasmax`, `tasmin` (→ `dtr`), `hurs`, `hursmin`, `sfcWind` |

`pr`, `hurs`, `hursmin`, and `sfcWind` are atmospheric variables present on all grid cells. `snw` is a land-only variable: its
CMIP6 output is masked to land cells using the `sftlf` (land area fraction) file. Including `snw`
in the test exercises the land-masking code path that requires `sftlf`. Any land-only variable
(e.g., `mrso`, `mrros`) follows the same path.

`tasmax` and `tasmin` exercise the DTR derivation path: `dtr = tasmax − tasmin`. It is computed after
regridding CMIP6, while WRF-downscaled ERA5 `dtr` is computed from `t2max` and `t2min` in the same way. Bias-adjusted `tasmin`
is re-derived as `adjusted tasmax − adjusted dtr`.

This is not a scientifically meaningful domain — it is purely a functional test to verify that each pipeline step runs without error and produces non-empty output.

## Test data layout

```
test/data/
├── cmip6/
│   ├── CMIP/MIROC/MIROC6/historical/r1i1p1f1/day/
│   │   ├── pr/gn/v20191016/pr_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   ├── snw/gn/v20191016/snw_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   ├── tasmax/gn/v20191016/tasmax_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   ├── tasmin/gn/v20191016/tasmin_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   ├── hurs/gn/v20191016/hurs_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   ├── hursmin/gn/v20191016/hursmin_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   │   └── sfcWind/gn/v20200804/sfcWind_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc
│   ├── ScenarioMIP/MIROC/MIROC6/ssp370/r1i1p1f1/day/
│   │   ├── pr/gn/v20191016/pr_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   ├── snw/gn/v20191016/snw_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   ├── tasmax/gn/v20191016/tasmax_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   ├── tasmin/gn/v20191016/tasmin_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   ├── hurs/gn/v20191016/hurs_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   ├── hursmin/gn/v20191016/hursmin_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   │   └── sfcWind/gn/v20200323/sfcWind_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc
│   └── sftlf/
│       └── sftlf_fx_MIROC6_historical_r1i1p1f1_gn.nc
└── wrf_era5/
    ├── pr/
    │   └── pr_{2000..2009}_daily_era5_12km_3338.nc
    ├── snow_mean/
    │   └── snow_mean_{2000..2009}_daily_era5_12km_3338.nc
    ├── t2max/
    │   └── t2max_{2000..2009}_daily_era5_12km_3338.nc
    ├── t2min/
    │   └── t2min_{2000..2009}_daily_era5_12km_3338.nc
    ├── rh2_mean/
    │   └── rh2_mean_{2000..2009}_daily_era5_12km_3338.nc
    ├── rh2_min/
    │   └── rh2_min_{2000..2009}_daily_era5_12km_3338.nc
    └── wspd10_mean/
        └── wspd10_mean_{2000..2009}_daily_era5_12km_3338.nc
```

CMIP6 training period: historical 2000–2009. Future scenario: ssp370 2045–2054.

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

## Configure the pipeline

Read the `config.py` to see your options for configuring the pipeline. Pay special attention to the dask configuration to avoid running out of memory.

## Running the full pipeline on test data

```bash
cd test
bash run_pipeline.sh /path/to/work_dir 12
```

Arguments:
- `work_dir`: writable directory for all intermediate and final outputs
- `resolution`: `4` or `12` (km); controls domain bounds in cascade regridding

## Pipeline steps

The test uses a **2-stage cascade regrid** (native CMIP6 → one intermediate grid → ERA5 target).
The full production pipeline described in the main README uses a 3-stage cascade (one additional
intermediate step). The scripts support both — `run_cascade_regrid.py` can be called twice for 3 stages.

| Step | Script | Description |
|------|--------|-------------|
| 1 | `regridding/make_intermediate_target_grid_file.py` | Create 0.5° intermediate cascade grid |
| 2 | `regridding/regrid_sftlf_to_target.py` | Regrid sftlf to intermediate grid |
| 3 | `regridding/generate_batch_files.py` | Scan CMIP6 dir, write batch .txt files |
| 4 | `regridding/run_first_regrid.py` | Regrid CMIP6 → intermediate grid |
| 5 | `regridding/make_final_target_grid_file.py` | Extract ERA5 slice as final target grid |
| 5b | `regridding/regrid_sftlf_to_target.py` | Regrid sftlf to final ERA5 target grid |
| 6 | `regridding/run_cascade_regrid.py` | Regrid intermediate → ERA5 target |
| 7 | `derived/run_cmip6_dtr.py` | Compute CMIP6 DTR from regridded tasmax/tasmin |
| 8 | `derived/run_era5_dtr.py` | Compute ERA5 DTR from t2max/t2min |
| 9 | `bias_adjust/run_cmip6_netcdf_to_zarr.py` | Convert regridded CMIP6 → Zarr (pr, snw, tasmax, dtr) |
| 10a | `bias_adjust/run_era5_netcdf_to_zarr.py` | Convert ERA5 base vars → Zarr (pr, snow_mean, t2max) |
| 10b | `bias_adjust/run_era5_netcdf_to_zarr.py` | Convert ERA5 DTR → Zarr |
| 11 | `bias_adjust/run_train_qm.py` | Train QDM bias adjustment models |
| 12 | `bias_adjust/run_bias_adjust.py` | Apply bias adjustment |
| 13 | `derived/run_difference.py` | Derive tasmin = adjusted tasmax − adjusted dtr |

## Expected outputs

After a successful run on the test data:

```
work_dir/
├── intermediate_target.nc      # 0.5° intermediate grid
├── final_target.nc             # WRF-downscaled ERA5 slice (final target grid)
├── first_regrid/               # CMIP6 → intermediate regridded files
├── cascade_batch/              # Batch files for cascade stage
├── second_regrid/              # Intermediate → WRF-downscaled ERA5 regridded files
├── cmip6_zarr/                 # Zarr stores of regridded CMIP6 data
├── era5_zarr/                  # Zarr stores of WRF-downscaled ERA5 data
├── trained/                    # Trained QDM model stores
└── adjusted/                   # Bias-adjusted output stores
```

## QC script

After a successful pipeline run, assess the bias-adjusted outputs with:

```bash
python test/qc_adjusted_outputs.py /path/to/work_dir
```

This produces one PNG per variable in `{work_dir}/qc/` (e.g. `qc/pr.png`, `qc/snw.png`) and a printed pass/fail summary covering:

| Check | What it tests |
|-------|--------------|
| Physical plausibility | No negative values, NaN fraction, no extreme outliers |
| Bias reduction | Monthly climatology RMSE before vs after adjustment |
| CDF comparison | Empirical distribution of adjusted vs WRF-downscaled ERA5 reference |
| Spatial mean maps | Side-by-side WRF-downscaled ERA5 vs adjusted historical means |
| Future delta sanity | ssp370 − historical mean change within plausible bounds |

The script exits with status 0 if all checks pass, 1 otherwise.
