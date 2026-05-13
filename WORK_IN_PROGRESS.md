# Work-in-Progress: cmip6-downscaling repo build

Point Claude at this file when resuming. Say:
> "Resume building the cmip6-downscaling repo. Read /home/jdpaul3/cmip6-downscaling/WORK_IN_PROGRESS.md for context."

---

## What this repo is

A standalone, HPC-free packaging of the CMIP6 statistical downscaling pipeline
drawn from two source repos (read-only, do NOT edit them):

- `~/cmip6-utils` — main branch only (use `git show main:<path>` to read files)
- `/import/home/jdpaul3/prefect` — main branch only

The new repo lives at `~/cmip6-downscaling`. It removes Prefect, SLURM, Paramiko,
and SSH. Every SLURM launcher (`run_*.py`) becomes a simple sequential Python loop.
No `prep_era5_variables.py`.

---

## Key design decisions

1. Sequential execution only — document that users can manually run parallel copies
2. CDO is an external dependency — document in README under "Required Dependencies"
3. Arctic domain bounds are parameterized (CLI args with defaults)
4. SLURM launchers rewritten as simple Python loops
5. Test data: actual CMIP6 NetCDF files clipped to Seward Peninsula bounding box
6. Year ranges (ERA5 training period, future scenarios) are configurable parameters
7. sftlf paths: user-provided, no hardcoded paths; test suite includes example files
8. Do NOT include `prep_era5_variables.py`; test suite files show the required format

---

## Current status: PIPELINE TESTED END-TO-END ✅, v0.1.1 TAGGED ✅

```
~/cmip6-downscaling/
├── README.md                ✅ — includes ERA5 provenance section
├── environment.yml          ✅
├── config.py                ✅ — year ranges, domain bounds, var LUTs
├── regridding/
│   ├── config.py            ✅ — model_sftlf_lu removed
│   ├── generate_batch_files.py   ✅ — copied as-is
│   ├── regrid.py            ✅ — system-specific output code removed
│   ├── regrid_sftlf_to_target.py ✅ — copied as-is
│   ├── make_intermediate_target_grid_file.py  ✅ — added domain CLI args
│   ├── make_final_target_grid_file.py  ✅ — copied as-is
│   ├── run_first_regrid.py  ✅ — NEW sequential loop
│   └── run_cascade_regrid.py ✅ — NEW sequential loop
├── bias_adjust/
│   ├── config.py            ✅ — copied as-is
│   ├── luts.py              ✅ — year ranges with documented defaults
│   ├── utils.py             ✅ — copied as-is
│   ├── netcdf_to_zarr.py    ✅ — copied as-is
│   ├── train_qm.py          ✅ — copied as-is
│   ├── bias_adjust.py       ✅ — copied as-is
│   ├── run_cmip6_netcdf_to_zarr.py ✅ — sequential loop
│   ├── run_era5_netcdf_to_zarr.py  ✅ — sequential loop
│   ├── run_train_qm.py      ✅ — sequential loop
│   └── run_bias_adjust.py   ✅ — sequential loop
├── derived/
│   ├── config.py            ✅ — copied as-is
│   ├── dtr.py               ✅ — copied as-is
│   ├── difference.py        ✅ — copied as-is
│   ├── run_cmip6_dtr.py     ✅ — sequential loop
│   ├── run_era5_dtr.py      ✅ — sequential loop
│   └── run_difference.py    ✅ — sequential loop
└── test/
    ├── README.md            ✅ — updated for MIROC6 + ERA5 provenance
    ├── run_pipeline.sh      ✅ — updated for MIROC6, pr+snw, historical+ssp370
    ├── extent_check.png     ✅ — EPSG:3338 extent verification image
    └── data/
        ├── cmip6/           ✅ — MIROC6 pr+snw, clipped (see below)
        │   └── sftlf/       ✅ — MIROC6 sftlf, clipped (see below)
        └── wrf_era5/        ✅ — 12km pr+snow_sum 2000-2009, clipped (see below)
```

---

## Test data details

### CMIP6 (4×8 native grid cells after clip)
Source: `/import/beegfs/CMIP6/arctic-cmip6/CMIP6/`

Clip bounds (0-360 lon convention): **lat 63–69°N, lon 190–202°**
= approximately -170 to -158°W, covering the Seward Peninsula of Alaska

Files:
- `cmip6/CMIP/MIROC/MIROC6/historical/r1i1p1f1/day/pr/gn/v20191016/pr_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc`
- `cmip6/CMIP/MIROC/MIROC6/historical/r1i1p1f1/day/snw/gn/v20191016/snw_day_MIROC6_historical_r1i1p1f1_gn_20000101-20091231.nc`
- `cmip6/ScenarioMIP/MIROC/MIROC6/ssp370/r1i1p1f1/day/pr/gn/v20191016/pr_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc`
- `cmip6/ScenarioMIP/MIROC/MIROC6/ssp370/r1i1p1f1/day/snw/gn/v20191016/snw_day_MIROC6_ssp370_r1i1p1f1_gn_20450101-20541231.nc`

### ERA5 12km (62×70 grid cells after clip)
Source:
- pr: `/import/beegfs/CMIP6/jdpaul3/wrf_era5_12km_daily/for_downscaling/pr/`
- snow_sum: `/import/beegfs/CMIP6/jdpaul3/wrf_era5_12km_daily/snow_sum/`

Clip bounds (EPSG:3338): **x: -851,000 to -112,000 m, y: 1,404,000 to 2,243,000 m**
(50km buffer beyond the CMIP6 cell extent)

Files: `wrf_era5/pr/pr_{2000..2009}_daily_era5_12km_3338.nc`
       `wrf_era5/snow_sum/snow_sum_{2000..2009}_daily_era5_12km_3338.nc`

### sftlf (4×8 cells, same clip as CMIP6)
Source: `/import/beegfs/CMIP6/arctic-cmip6/CMIP6/CMIP/MIROC/MIROC6/historical/r1i1p1f1/fx/sftlf/gn/v20190311/sftlf_fx_MIROC6_historical_r1i1p1f1_gn.nc`

File: `cmip6/sftlf/sftlf_fx_MIROC6_historical_r1i1p1f1_gn.nc`

### Coordinate system notes
- CMIP6 uses **0-360 longitude** convention; -168 to -160°W = 192 to 200° (0-360)
- ERA5 is in **EPSG:3338** (Alaska Albers) with x/y projected coordinates
- ERA5 y axis is **descending** (north→south); clip requires `slice(Y_MAX, Y_MIN)`
- Python env for geo operations: `/home/jdpaul3/miniconda3/envs/cmip6-utils/bin/python`

---

## run_pipeline.sh parameters

The test pipeline is configured for:
- **MODEL**: MIROC6
- **SCENARIOS**: historical ssp370
- **VARIABLES**: pr snw
- **ERA5_VARS**: pr snow_sum
- **RESOLUTION**: 12 (km)

**Important**: The ERA5 training period in the test data is 2000–2009 (not the
default 1965–2014). When running the pipeline, pass year range overrides to the
bias_adjust scripts:
- `--start_year 2000 --end_year 2009` to `run_era5_netcdf_to_zarr.py`
- `--era5_start_year 2000 --era5_end_year 2009` to `run_train_qm.py`

The `run_pipeline.sh` script passes these year ranges correctly. The pipeline
ran end-to-end successfully on a t2small node (~2 hours, all 13 steps).

---

## Remaining tasks

0. **Investigate `environment.yml` solver failure.** The `conda env create` for
   `cmip6-downscaling` appeared to hang or fail to solve. Compare the spec against
   the working `cmip6-utils` environment (`conda env export -n cmip6-utils`) to
   identify conflicts. Likely culprits: `xesmf==0.8.4` and `xclim==0.47.0` installed
   via pip while their compiled dependencies (ESMF, cf_xarray) come from conda-forge —
   may need pinned conda-forge versions instead of pip installs, or a different Python
   version pin. Resolve before re-running the pipeline test.

1. **Check whether CDO is actually used by the pipeline.** `cdo` is listed as a
   required dependency in `environment.yml` and mentioned in `test/README.md`, but
   it may have been replaced by xESMF for all regridding. Grep the pipeline scripts
   for `cdo` calls, confirm whether it can be dropped, and update `environment.yml`
   and the READMEs accordingly.

2. **Create a second test domain and data for temperature variables** (`tasmax`,
   `tasmin`, `dtr`) to exercise the DTR derivation path (steps 7–8 and 13 in
   `run_pipeline.sh`). This path is currently skipped in the Seward Peninsula test
   because it only contains `pr` and `snw`. Need to:
   - Choose a second geographic clip (or reuse Seward Peninsula)
   - Clip CMIP6 `tasmax` and `tasmin` (historical + ssp370)
   - Clip WRF-ERA5 `t2max`, `t2min`, `dtr` for the matching period
   - Add a second `run_pipeline.sh` (or extend the existing one) that runs the full
     DTR → bias-adjust → difference chain
   - Verify `tasmin = tasmax − dtr` output is produced correctly

3. **Update all READMEs** once tasks 1 and 2 are resolved:
   - `README.md`: update dependency list (CDO yes/no), add temperature test domain
   - `test/README.md`: document the new temperature test, update pipeline steps table
   - `PR_NOTES.md`: note any new known issues or run instructions for the temp test

---

## How to read source files without switching branches

```bash
# cmip6-utils main branch (currently on new_var_notebooks)
git -C ~/cmip6-utils show main:regridding/regrid.py
git -C ~/cmip6-utils show main:bias_adjust/luts.py

# prefect repo (already on main)
cat /import/home/jdpaul3/prefect/downscaling/downscale_cmip6.py
```

---

## Pipeline step order

1. `regridding/make_intermediate_target_grid_file.py` — create intermediate cascade grid
2. `regridding/regrid_sftlf_to_target.py` — regrid sftlf land masks to cascade grid
3. `regridding/generate_batch_files.py` — scan CMIP6 dir, create batch .txt files
4. `regridding/run_first_regrid.py` — first cascade regrid (native → intermediate)
5. `regridding/run_cascade_regrid.py` — second cascade regrid (intermediate → ERA5 target)
6. `regridding/make_final_target_grid_file.py` — extract ERA5 slice as final target grid
7. `derived/run_cmip6_dtr.py` — compute DTR = tasmax − tasmin (if needed)
8. `derived/run_era5_dtr.py` — compute ERA5 DTR (if needed)
9. `bias_adjust/run_cmip6_netcdf_to_zarr.py` — convert regridded CMIP6 NetCDF → Zarr
10. `bias_adjust/run_era5_netcdf_to_zarr.py` — convert ERA5 NetCDF → Zarr
11. `bias_adjust/run_train_qm.py` — train QDM models
12. `bias_adjust/run_bias_adjust.py` — apply QDM bias adjustment
13. `derived/run_difference.py` — compute tasmin from (tasmax − dtr) if needed
