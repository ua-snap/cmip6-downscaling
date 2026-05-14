# Work-in-Progress: cmip6-downscaling repo build

Point Claude at this file when resuming. Say:
> "Resume building the cmip6-downscaling repo. Read /import/home/jdpaul3/cmip6-downscaling/WORK_IN_PROGRESS.md for context."

---

## What this repo is

A standalone, HPC-free packaging of the CMIP6 statistical downscaling pipeline
drawn from two source repos (read-only, do NOT edit them):

- `~/cmip6-utils` — main branch only (use `git show main:<path>` to read files)
- `/import/home/jdpaul3/prefect` — main branch only

The new repo lives at `/import/home/jdpaul3/cmip6-downscaling` and is published at
`https://github.com/ua-snap/cmip6-downscaling` (tag `v0.1.1`). It removes Prefect,
SLURM, Paramiko, and SSH. Every SLURM launcher (`run_*.py`) becomes a simple
sequential Python loop. No `prep_era5_variables.py`.

---

## Key design decisions

1. Sequential execution only — document that users can manually run parallel copies
2. CDO dependency status is **under investigation** (see task 1 in Remaining tasks)
3. Arctic domain bounds are parameterized (CLI args with defaults)
4. SLURM launchers rewritten as simple Python loops
5. Test data: actual CMIP6 NetCDF files clipped to Seward Peninsula bounding box
6. Year ranges (ERA5 training period, future scenarios) are configurable parameters
7. sftlf paths: user-provided, no hardcoded paths; test suite includes example files
8. Do NOT include `prep_era5_variables.py`; test suite files show the required format

---

## Current status: TEMPERATURE PATH VALIDATED — READY FOR README + GITHUB RELEASE (2026-05-14)

```
/import/home/jdpaul3/cmip6-downscaling/
├── README.md                ✅ — general-purpose docs, no HPC assumptions
├── PR_NOTES.md              ✅ — HPC-specific run instructions for reviewers
├── WORK_IN_PROGRESS.md      ✅ — this file
├── .gitignore               ✅
├── environment.yml          ✅ — name: cmip6-downscaling (see task 0 re solver)
├── config.py                ✅ — year ranges, domain bounds, var LUTs
├── regridding/
│   ├── config.py            ✅ — model_sftlf_lu removed
│   ├── generate_batch_files.py   ✅
│   ├── regrid.py            ✅ — rasdafy removed; NaN validation fix applied
│   ├── regrid_sftlf_to_target.py ✅
│   ├── make_intermediate_target_grid_file.py  ✅ — domain CLI args added
│   ├── make_final_target_grid_file.py  ✅
│   ├── run_first_regrid.py  ✅ — sequential loop
│   └── run_cascade_regrid.py ✅ — sequential loop
├── bias_adjust/
│   ├── config.py            ✅
│   ├── luts.py              ✅ — year ranges with documented defaults
│   ├── utils.py             ✅
│   ├── netcdf_to_zarr.py    ✅
│   ├── train_qm.py          ✅
│   ├── bias_adjust.py       ✅
│   ├── run_cmip6_netcdf_to_zarr.py ✅
│   ├── run_era5_netcdf_to_zarr.py  ✅
│   ├── run_train_qm.py      ✅
│   └── run_bias_adjust.py   ✅
├── derived/
│   ├── config.py            ✅
│   ├── dtr.py               ✅
│   ├── difference.py        ✅
│   ├── run_cmip6_dtr.py     ✅
│   ├── run_era5_dtr.py      ✅
│   └── run_difference.py    ✅
└── test/
    ├── README.md            ✅ — Seward Peninsula domain, known snw artifact noted
    ├── run_pipeline.sh      ✅ — pr+snw, historical+ssp370, correct year ranges
    ├── qc_adjusted_outputs.py ✅ — QC script; run after pipeline, saves qc_report.png
    ├── test_area.png        ✅ — EPSG:3338 map of Seward Peninsula test domain
    ├── data_seward_peninsula_test.zip  ✅ — test data archive (attached to GH release)
    └── data/                   — gitignored; unzip from data_seward_peninsula_test.zip
        ├── cmip6/             — MIROC6 pr+snw historical+ssp370, sftlf
        └── wrf_era5/          — 12km pr+snow_sum 2000-2009
```

### Python environment

**Active env: `cmip6-downscaling`** (confirmed working as of 2026-05-14).
Key pins required: `esmf=*=nompi*`, `esmpy=*=nompi*`, `importlib_metadata<5`.
Use `conda env create -f environment.yml --solver=libmamba`.

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
- Python env for geo operations: `cmip6-utils` (see "Python environment" section above)

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

0. ✅ **`environment.yml` confirmed working.** `cmip6-downscaling` env created successfully.
   Key pins: `esmf=*=nompi*`, `esmpy=*=nompi*`, `importlib_metadata<5`.

1. ✅ **CDO confirmed unused and removed.**

2. ✅ **Full temperature-path pipeline run completed (2026-05-14).** All 13 steps
   confirmed working for pr, snw, tasmax, tasmin, dtr. QC images generated for all
   5 variables in `qc/`. Bugs fixed this session:
   - `run_cmip6_dtr.py`: `get_tmax_tmin_fps_cmip6` was reading text batch files instead
     of globbing the actual second_regrid directory — replaced with `rglob`.
   - `dtr.py`: stale `max_retries` kwarg in `validate_file_readback` call — removed.
   - `train_qm.py`: zarr write failed on coordinate chunk encoding mismatch — encoding
     dict now covers coords as well as data vars, with `"chunks": None`.
   - `bias_adjust.py`: xclim All-NaN RuntimeWarning filtered (expected for masked cells).
   - All 6 scripts: false-positive start/middle/end NaN warnings removed (now only
     fail if global min is also NaN).
   - `regridding/regrid.py`, `bias_adjust/netcdf_to_zarr.py`: HDF5 C-library noise
     suppressed via `h5py._errors.silence_errors()` + `exec 2> grep` filter in pipeline.

3. ✅ **READMEs updated** (CDO removed, temperature variables added, data layout updated).

4. **Add methodology section to README.md.**
   - Port content from https://github.com/ua-snap/cmip6-utils/blob/main/downscaling/README.md
     (the upstream source repo's method description).
   - Explain algorithm parameters that aren't obvious:
     - Jitter values (what they are, why they're applied, which variables)
     - Squeezing of `pr` and `dtr` (clipping to physical bounds, why)
     - `tasmin` floor at 203.15 K in `difference.py`
     - QDM training period (ERA5 reference years) and why it matters
     - Cascade regridding rationale (why two steps instead of one)
     - Land/sea masking with sftlf
   - This should be a "Methodology" section sitting between the current
     "Pipeline overview" and "Running the pipeline" sections.

5. ✅ **Test data zip repackaged** (2026-05-14). New `test/data_seward_peninsula_test.zip`
   (177 MB) includes t2max/t2min ERA5 dirs and tasmax/tasmin CMIP6 dirs.
   **Still needed**: upload to GitHub release to replace the old asset.

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
