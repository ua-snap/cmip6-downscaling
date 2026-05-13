# PR Notes 

## Conda environment

Clone the repo and create a conda environment from `~cmip6-downscaling/environment.yml`

```bash
conda env create -f ~/cmip6-downscaling/environment.yml
```

## Download test data 

Get the test data archive from the latest GitHub release (https://github.com/ua-snap/cmip6-downscaling/releases/latest) and unzip it into the `~/cmip6-downscaling/test` directory. Note that the source code in the release might not be the version you are testing, but the attached test data archive should be fine to use.

```bash
cd test
unzip /path/to/data_seward_peninsula_test.zip
```

## Running the test pipeline

Start an interactive session on a compute node and run the pipeline:

```bash
srun --partition=t2small --time=12:00:00 --pty /bin/bash
conda activate cmip6-downscaling
cd ~/jdpaul3/cmip6-downscaling
bash test/run_pipeline.sh ~jdpaul3/cmip6_test_run 12
```

Depending on available compute resources, this should take 1-2 hours.

## Run the QC

```bash
python test/qc_adjusted_outputs.py ~jdpaul3/cmip6_test_run
```

This will produce a `qc_report.png` image in the test folder.

## Known issues:

### snw extreme values in bias-adjusted output (known QDM tail artifact)
QDM extrapolates adjustment factors beyond the training range when a historical CMIP6 quantile
has no analog in the ERA5 reference distribution. On the test run, 663 `snw` cells in the
historical-adjusted store exceed 50,000 kg m⁻² (ERA5 max ~10,000 kg m⁻²). The monthly
climatology and CDFs are otherwise well-behaved — this is a tail issue only.

**No fix applied.** Post-processing is required: user will have to clip output to a physically defensible upper
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