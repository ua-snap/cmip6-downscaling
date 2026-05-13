#!/usr/bin/env bash
# End-to-end pipeline test on small test data.
# Usage: bash run_pipeline.sh <work_dir> [resolution]
#   work_dir   : writable directory for all pipeline outputs
#   resolution : 4 or 12 (km); default 12

set -euo pipefail

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
VARIABLES="pr snw"
ERA5_VARS="pr snow_sum"

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
    --vars "$VARIABLES" \
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

# ── Step 7: Compute CMIP6 DTR (skip if not needed) ────────────────────────
# Uncomment if tasmax and tasmin are available:
# echo "[7/13] Computing CMIP6 DTR..."
# python "$DERIVED/run_cmip6_dtr.py" \
#     --input_dir "$WORK_DIR/second_regrid" \
#     --output_dir "$WORK_DIR/second_regrid" \
#     --models "$MODEL" \
#     --scenarios "$SCENARIOS"
echo "[7/13] Skipping CMIP6 DTR (pr+snw test data, no temperature variables)"

# ── Step 8: Compute ERA5 DTR ───────────────────────────────────────────────
# Uncomment if t2max and t2min ERA5 files are available:
# echo "[8/13] Computing ERA5 DTR..."
# python "$DERIVED/run_era5_dtr.py" \
#     --era5_dir "$ERA5_DIR" \
#     --output_dir "$WORK_DIR/era5_dtr" \
#     --resolution "$RESOLUTION"
echo "[8/13] Skipping ERA5 DTR (pr+snw test data, no temperature variables)"

# ── Step 9: Convert regridded CMIP6 → Zarr ────────────────────────────────
echo "[9/13] Converting regridded CMIP6 NetCDF → Zarr..."
mkdir -p "$WORK_DIR/cmip6_zarr"
python "$BIAS_ADJUST/run_cmip6_netcdf_to_zarr.py" \
    --netcdf_dir "$WORK_DIR/second_regrid" \
    --output_dir "$WORK_DIR/cmip6_zarr" \
    --models "$MODEL" \
    --scenarios "$SCENARIOS" \
    --variables "$VARIABLES" \
    --era5_start_year "$ERA5_START_YEAR" \
    --era5_end_year "$ERA5_END_YEAR" \
    --future_start_year "$FUTURE_START_YEAR" \
    --future_end_year "$FUTURE_END_YEAR"

# ── Step 10: Convert ERA5 → Zarr ──────────────────────────────────────────
echo "[10/13] Converting ERA5 NetCDF → Zarr..."
mkdir -p "$WORK_DIR/era5_zarr"
python "$BIAS_ADJUST/run_era5_netcdf_to_zarr.py" \
    --netcdf_dir "$ERA5_DIR" \
    --output_dir "$WORK_DIR/era5_zarr" \
    --variables "$ERA5_VARS" \
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
    --variables "$VARIABLES"

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
    --variables "$VARIABLES"

# ── Step 13: Derive tasmin (skip — tasmin not in test variables) ───────────
echo "[13/13] Skipping tasmin derivation (not in test variables)"
# To derive tasmin from tasmax - dtr:
# python "$DERIVED/run_difference.py" \
#     --input_dir "$WORK_DIR/adjusted" \
#     --output_dir "$WORK_DIR/adjusted" \
#     --minuend_tmp_fn "tasmax_{model}_{scenario}_adjusted.zarr" \
#     --subtrahend_tmp_fn "dtr_{model}_{scenario}_adjusted.zarr" \
#     --out_tmp_fn "tasmin_{model}_{scenario}_adjusted.zarr" \
#     --new_var_id tasmin \
#     --models "$MODEL" \
#     --scenarios "$SCENARIOS"

echo ""
echo "========================================"
echo "Pipeline test complete!"
echo "Adjusted outputs: $WORK_DIR/adjusted/"
echo "========================================"
