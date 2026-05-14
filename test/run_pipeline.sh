#!/usr/bin/env bash
# End-to-end pipeline test on small test data.
# Usage: bash run_pipeline.sh <work_dir> [resolution]
#   work_dir   : writable directory for all pipeline outputs
#   resolution : 4 or 12 (km); default 12

set -euo pipefail

# Filter out HDF5 C-library diagnostic noise (benign attribute-probe messages
# printed directly to fd-2 by libhdf5; not suppressible from Python).
# Multi-threaded interleaving garbles the lines, so match substrings rather
# than anchored prefixes.  Patterns cover:
#   HDF5-DIAG headers, H5VL/H5O/H5A stack-frame lines, major:/minor: class
#   lines, isolated ":" and "thread N" artifacts from interleaved writes.
exec 2> >(grep -Ev "HDF5|H5VL|H5O__|H5A__|#[0-9]{3}:|major:|minor:|QuantizeBit|^thread [0-9]|^:$" >&2)

WORK_DIR="${1:?Usage: $0 <work_dir> [resolution]}"
RESOLUTION="${2:-12}"

# Paths relative to repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DATA="$REPO_ROOT/test/data"
CMIP6_DIR="$TEST_DATA/cmip6"
ERA5_DIR="$TEST_DATA/wrf_era5"
SFTLF_DIR="$TEST_DATA/cmip6/sftlf"

REGRIDDING="$REPO_ROOT/regridding"
BIAS_ADJUST="$REPO_ROOT/bias_adjust"
DERIVED="$REPO_ROOT/derived"

# Pipeline parameters
MODEL="MIROC6"
SCENARIOS="historical ssp370"

# REGRID_VARS: everything that needs to go through the cascade regridder.
# tasmin is included so DTR = tasmax - tasmin can be computed after regridding
# (step 7), but tasmin is NOT bias-adjusted directly.
REGRID_VARS="pr snw tasmax tasmin"

# ADJUST_VARS: variables that get zarr-converted, QDM-trained, and bias-adjusted.
# tasmin is excluded — it is derived as adjusted_tasmax - adjusted_dtr (step 13).
ADJUST_VARS="pr snw tasmax dtr"

# ERA5_BASE_VARS: ERA5 variables in test/data/wrf_era5/ to zarr-convert.
# ERA5 dtr is computed by step 8 and zarr-converted separately in step 10b.
ERA5_BASE_VARS="pr snow_sum t2max"

# Year ranges — test data covers 2000-2009 (ERA5/historical) and 2045-2054 (ssp370)
# Production defaults are ERA5 1965-2014, future 2015-2100
ERA5_START_YEAR=2000
ERA5_END_YEAR=2009
FUTURE_START_YEAR=2045
FUTURE_END_YEAR=2054

mkdir -p "$WORK_DIR"

echo "========================================"
echo "CMIP6 Downscaling Pipeline — Test Run"
echo "Repo:       $REPO_ROOT"
echo "Work dir:   $WORK_DIR"
echo "Resolution: ${RESOLUTION}km"
echo "========================================"

# ── Step 1: Create intermediate target grid ────────────────────────────────
echo "[1/13] Creating intermediate target grid..."
FIRST_CMIP6_FILE=$(find "$CMIP6_DIR" -name "*.nc" | head -1)
python "$REGRIDDING/make_intermediate_target_grid_file.py" \
    --src_file "$FIRST_CMIP6_FILE" \
    --out_file "$WORK_DIR/intermediate_target.nc" \
    --step 0.5 \
    --resolution "$RESOLUTION"

# ── Step 2: Regrid sftlf to intermediate grid ──────────────────────────────
echo "[2/13] Regridding sftlf to intermediate grid..."
SRC_SFTLF=$(find "$SFTLF_DIR" -name "sftlf_fx_MIROC6*.nc" | head -1)
python "$REGRIDDING/regrid_sftlf_to_target.py" \
    --source_sftlf "$SRC_SFTLF" \
    --target_grid "$WORK_DIR/intermediate_target.nc" \
    --output_sftlf "$WORK_DIR/intermediate_sftlf.nc"

# ── Step 3: Generate batch files ───────────────────────────────────────────
echo "[3/13] Generating batch files..."
mkdir -p "$WORK_DIR/regrid_batch"
python "$REGRIDDING/generate_batch_files.py" \
    --cmip6_directory "$CMIP6_DIR" \
    --regrid_batch_dir "$WORK_DIR/regrid_batch" \
    --vars "$REGRID_VARS" \
    --freqs "day" \
    --models "$MODEL" \
    --scenarios "$SCENARIOS"

# ── Step 4: First regrid (CMIP6 → intermediate grid) ──────────────────────
echo "[4/13] First regrid: CMIP6 → intermediate grid..."
mkdir -p "$WORK_DIR/first_regrid"
python "$REGRIDDING/run_first_regrid.py" \
    --batch_dir "$WORK_DIR/regrid_batch" \
    --target_grid "$WORK_DIR/intermediate_target.nc" \
    --output_dir "$WORK_DIR/first_regrid" \
    --interp_method bilinear \
    --dst_sftlf_fp "$WORK_DIR/intermediate_sftlf.nc"

# ── Step 5: Make final target grid from ERA5 ──────────────────────────────
echo "[5/13] Creating final target grid from ERA5..."
FIRST_ERA5_FILE=$(find "$ERA5_DIR" -name "*.nc" | head -1)
python "$REGRIDDING/make_final_target_grid_file.py" \
    "$FIRST_ERA5_FILE" \
    "$WORK_DIR/final_target.nc"

# ── Step 5b: Regrid sftlf to final ERA5 target grid ───────────────────────
echo "[5b] Regridding sftlf to final ERA5 target grid..."
python "$REGRIDDING/regrid_sftlf_to_target.py" \
    --source_sftlf "$SRC_SFTLF" \
    --target_grid "$WORK_DIR/final_target.nc" \
    --output_sftlf "$WORK_DIR/final_sftlf.nc"

# ── Step 6: Cascade regrid (intermediate → ERA5 target) ───────────────────
echo "[6/13] Cascade regrid: intermediate → ERA5 target..."
mkdir -p "$WORK_DIR/cascade_batch" "$WORK_DIR/second_regrid"
python "$REGRIDDING/run_cascade_regrid.py" \
    --regridded_dir "$WORK_DIR/first_regrid" \
    --batch_dir "$WORK_DIR/cascade_batch" \
    --target_grid "$WORK_DIR/final_target.nc" \
    --output_dir "$WORK_DIR/second_regrid" \
    --interp_method bilinear \
    --sftlf_dir "$WORK_DIR"

# ── Step 7: Compute CMIP6 DTR ─────────────────────────────────────────────
# Input: regridded tasmax + tasmin in second_regrid. Output written to
# second_regrid/{model}/{scenario}/day/dtr/ alongside the other regridded vars.
echo "[7/13] Computing CMIP6 DTR..."
python "$DERIVED/run_cmip6_dtr.py" \
    --input_dir "$WORK_DIR/second_regrid" \
    --output_dir "$WORK_DIR/second_regrid" \
    --models "$MODEL" \
    --scenarios "$SCENARIOS"

# ── Step 8: Compute ERA5 DTR ───────────────────────────────────────────────
# Output goes to era5_dtr/dtr/ so that run_era5_netcdf_to_zarr.py can find
# files at the expected path: <netcdf_dir>/<var_id>/<var_id>_<year>*.nc
echo "[8/13] Computing ERA5 DTR..."
mkdir -p "$WORK_DIR/era5_dtr/dtr"
python "$DERIVED/run_era5_dtr.py" \
    --era5_dir "$ERA5_DIR" \
    --output_dir "$WORK_DIR/era5_dtr/dtr" \
    --resolution "$RESOLUTION"

# ── Step 9: Convert regridded CMIP6 → Zarr ────────────────────────────────
echo "[9/13] Converting regridded CMIP6 NetCDF → Zarr..."
mkdir -p "$WORK_DIR/cmip6_zarr"
python "$BIAS_ADJUST/run_cmip6_netcdf_to_zarr.py" \
    --netcdf_dir "$WORK_DIR/second_regrid" \
    --output_dir "$WORK_DIR/cmip6_zarr" \
    --models "$MODEL" \
    --scenarios "$SCENARIOS" \
    --variables "$ADJUST_VARS" \
    --era5_start_year "$ERA5_START_YEAR" \
    --era5_end_year "$ERA5_END_YEAR" \
    --future_start_year "$FUTURE_START_YEAR" \
    --future_end_year "$FUTURE_END_YEAR"

# ── Step 10a: Convert ERA5 base vars → Zarr ───────────────────────────────
echo "[10a/13] Converting ERA5 base vars (pr, snow_sum, t2max) → Zarr..."
mkdir -p "$WORK_DIR/era5_zarr"
python "$BIAS_ADJUST/run_era5_netcdf_to_zarr.py" \
    --netcdf_dir "$ERA5_DIR" \
    --output_dir "$WORK_DIR/era5_zarr" \
    --variables "$ERA5_BASE_VARS" \
    --resolution "$RESOLUTION" \
    --start_year "$ERA5_START_YEAR" \
    --end_year "$ERA5_END_YEAR"

# ── Step 10b: Convert ERA5 DTR → Zarr ─────────────────────────────────────
echo "[10b/13] Converting ERA5 DTR → Zarr..."
python "$BIAS_ADJUST/run_era5_netcdf_to_zarr.py" \
    --netcdf_dir "$WORK_DIR/era5_dtr" \
    --output_dir "$WORK_DIR/era5_zarr" \
    --variables "dtr" \
    --resolution "$RESOLUTION" \
    --start_year "$ERA5_START_YEAR" \
    --end_year "$ERA5_END_YEAR"

# ── Step 11: Train QDM ────────────────────────────────────────────────────
echo "[11/13] Training QDM bias adjustment models..."
mkdir -p "$WORK_DIR/trained" "$WORK_DIR/dask_tmp"
python "$BIAS_ADJUST/run_train_qm.py" \
    --sim_dir "$WORK_DIR/cmip6_zarr" \
    --ref_dir "$WORK_DIR/era5_zarr" \
    --output_dir "$WORK_DIR/trained" \
    --tmp_dir "$WORK_DIR/dask_tmp" \
    --models "$MODEL" \
    --variables "$ADJUST_VARS"

# ── Step 12: Apply bias adjustment ────────────────────────────────────────
echo "[12/13] Applying bias adjustment..."
mkdir -p "$WORK_DIR/adjusted"
python "$BIAS_ADJUST/run_bias_adjust.py" \
    --sim_dir "$WORK_DIR/cmip6_zarr" \
    --train_dir "$WORK_DIR/trained" \
    --output_dir "$WORK_DIR/adjusted" \
    --tmp_dir "$WORK_DIR/dask_tmp" \
    --models "$MODEL" \
    --scenarios "$SCENARIOS" \
    --variables "$ADJUST_VARS"

# ── Step 13: Derive tasmin = adjusted tasmax − adjusted dtr ───────────────
echo "[13/13] Deriving tasmin from adjusted tasmax − dtr..."
python "$DERIVED/run_difference.py" \
    --input_dir "$WORK_DIR/adjusted" \
    --output_dir "$WORK_DIR/adjusted" \
    --minuend_tmp_fn "tasmax_{model}_{scenario}_adjusted.zarr" \
    --subtrahend_tmp_fn "dtr_{model}_{scenario}_adjusted.zarr" \
    --out_tmp_fn "tasmin_{model}_{scenario}_adjusted.zarr" \
    --new_var_id tasmin \
    --models "$MODEL" \
    --scenarios "$SCENARIOS"

echo ""
echo "========================================"
echo "Pipeline test complete!"
echo "Adjusted outputs: $WORK_DIR/adjusted/"
echo "========================================"
