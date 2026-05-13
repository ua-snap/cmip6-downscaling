# PR Notes — Running the Pipeline on This System

This file documents how to run the end-to-end test on our specific HPC cluster
and how to publish the GitHub release. It is not part of the general user documentation.

---

## Publishing the GitHub release

Before merging, create a tagged release and attach the test data zip:

```bash
# On the HPC login node, from the repo root
cd /import/home/jdpaul3/cmip6-downscaling

# 1. Push the branch to GitHub (substitute your remote name/branch)
git push origin main

# 2. Create and push an annotated tag
git tag -a v0.1.0 -m "Initial release"
git push origin v0.1.0
```

Then on GitHub:

1. Go to **Releases → Draft a new release**
2. Select tag `v0.1.0`
3. Title: `v0.1.0 — Initial release`
4. In the release body, note the Seward Peninsula test domain and point to `test/README.md`
5. Under **Assets**, attach `test/data_seward_peninsula_test.zip`
   - File is at `/import/home/jdpaul3/cmip6-downscaling/test/data_seward_peninsula_test.zip` (85 MB)
6. Publish the release

Once published, update the placeholder URLs in `README.md` and `test/README.md`:
- Replace `https://github.com/ua-snap/cmip6-downscaling/releases/latest` with the real URL

---

## Environment

| Item | Value |
|------|-------|
| Scheduler | SLURM |
| Test partition | `t2small` |
| conda prefix | `/home/jdpaul3/miniconda3` |
| Python environment | `cmip6-utils` |
| Shared filesystem | `/import/home/jdpaul3/` |
| Large data (BeeGFS) | `/import/beegfs/CMIP6/` |

---

## Required environment variables

Two variables must be set before running any pipeline script. They are normally set
automatically by `conda activate`, but must be exported manually when using `srun`
without a full conda init:

```bash
export PATH=/home/jdpaul3/miniconda3/envs/cmip6-utils/bin:$PATH
export ESMFMKFILE=/home/jdpaul3/miniconda3/envs/cmip6-utils/lib/esmf.mk
```

`ESMFMKFILE` is required by `xESMF` / `ESMF` for all regridding steps. Without it,
every import of `xesmf` will fail with `ImportError: The ESMFMKFILE environment
variable is not available`.

---

## Running the test pipeline

### Interactively via srun

The VS Code integrated terminal does not provide a PTY, so `srun --pty /bin/bash`
does not produce an interactive session. Use `srun` to run the pipeline directly
instead:

```bash
srun --partition=t2small --time=12:00:00 bash -c "
  export PATH=/home/jdpaul3/miniconda3/envs/cmip6-utils/bin:\$PATH
  export ESMFMKFILE=/home/jdpaul3/miniconda3/envs/cmip6-utils/lib/esmf.mk
  cd /import/home/jdpaul3/cmip6-downscaling
  bash test/run_pipeline.sh /import/home/jdpaul3/cmip6_test_run 12
"
```

**Important**: Use a path on the shared filesystem (e.g. `/import/home/jdpaul3/...`)
for the work directory, not `/tmp`. The `/tmp` on a compute node is local to that
node and is not readable from the login node or VS Code.

### From a real terminal (ssh session)

If you have a proper terminal with PTY support, you can start an interactive session:

```bash
srun --partition=t2small --time=12:00:00 --pty /bin/bash
source /home/jdpaul3/miniconda3/etc/profile.d/conda.sh
conda activate cmip6-utils
cd /import/home/jdpaul3/cmip6-downscaling
bash test/run_pipeline.sh /import/home/jdpaul3/cmip6_test_run 12
```

---

## Expected run time

On a single `t2small` node, the test run takes approximately:

| Step | Time (approx.) |
|------|----------------|
| Steps 1–3 (grid setup, batch gen) | < 1 min |
| Step 4 (first regrid, 4 files × 10 yrs) | ~45 min |
| Steps 5–6 (cascade regrid setup) | < 5 min |
| Step 6 (cascade regrid, 4 files × 10 yrs) | ~45 min |
| Steps 9–12 (NetCDF→Zarr, train QDM, bias adjust) | ~15 min |
| **Total** | **~2 hours** |

Steps 7 and 8 (DTR derivation) are skipped in the test because the test data only
contains `pr` and `snw`.

---

## Known issues / fixes already applied

### `regrid.py` was empty on first checkout
The file `regridding/regrid.py` was 0 bytes. It was populated from the source
`cmip6-utils` repo (`main` branch) with system-specific output-format code removed
(a post-processing step used by a different downstream system, not needed here).

### snw extreme values in bias-adjusted output (known QDM tail artifact)
QDM extrapolates adjustment factors beyond the training range when a historical CMIP6 quantile
has no analog in the ERA5 reference distribution. On the test run, 663 `snw` cells in the
historical-adjusted store exceed 50,000 kg m⁻² (ERA5 max ~10,000 kg m⁻²). The monthly
climatology and CDFs are otherwise well-behaved — this is a tail issue only.

**No fix applied.** Post-processing is required: clip output to a physically defensible upper
bound (e.g., some multiple of the ERA5 99.9th percentile) before scientific use. This is
documented in `test/README.md` under "Known artifact."

### NaN validation false-positive on small test domains
`regrid.py`'s `validate_file_readback()` function checks the start, middle, and end
slices of each output file for all-NaN values. On a small test clip (4×8 CMIP6 cells
regridded to a 145×59 intermediate grid), all three sample positions fall in the NaN
surround outside the valid data region, causing the validation to fail even though the
file contains real data.

**Fix applied** (`regridding/regrid.py`): when all positional samples are NaN, the
validation now falls back to computing `arr.min()` over the entire array. Only if the
global minimum is also NaN does the validation raise an error. This is harmless for
production runs where the full domain is populated.

---

## Source data locations

The test data was clipped from full-domain production files:

| Dataset | Source path |
|---------|-------------|
| CMIP6 MIROC6 | `/import/beegfs/CMIP6/arctic-cmip6/CMIP6/CMIP/MIROC/MIROC6/` |
| WRF-ERA5 pr | `/import/beegfs/CMIP6/jdpaul3/wrf_era5_12km_daily/for_downscaling/pr/` |
| WRF-ERA5 snow_sum | `/import/beegfs/CMIP6/jdpaul3/wrf_era5_12km_daily/snow_sum/` |
| sftlf | `/import/beegfs/CMIP6/arctic-cmip6/CMIP6/CMIP/MIROC/MIROC6/historical/r1i1p1f1/fx/sftlf/` |

Clip bounds used for the test data:
- **CMIP6** (0–360 lon): lat 63–69°N, lon 190–202° (~Seward Peninsula)
- **WRF-ERA5** (EPSG:3338): x −851,000 to −112,000 m, y 1,404,000 to 2,243,000 m (50 km buffer)

The Python environment used for the clipping operations was
`/home/jdpaul3/miniconda3/envs/cmip6-utils/bin/python`.

---

## Checking pipeline output

After the run, key output paths under `<work_dir>/`:

```
first_regrid/MIROC6/{historical,ssp370}/day/{pr,snw}/   # intermediate regrid
second_regrid/MIROC6/{historical,ssp370}/day/{pr,snw}/  # cascade regrid (final grid)
cmip6_zarr/                                              # CMIP6 Zarr stores
era5_zarr/                                               # WRF-ERA5 Zarr stores
trained/                                                 # trained QDM weights
adjusted/                                                # ⭐ final bias-adjusted output
```

Quick sanity check from Python:

```python
import xarray as xr
ds = xr.open_zarr("<work_dir>/adjusted/pr_MIROC6_historical_adjusted.zarr")
print(ds)
print(ds.pr.min().values, ds.pr.max().values)
```
