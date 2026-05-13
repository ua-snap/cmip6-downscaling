#!/usr/bin/env python
"""
QC script for bias-adjusted pipeline outputs.

Usage:
    python test/qc_adjusted_outputs.py /path/to/work_dir

Outputs:
    {work_dir}/qc_report.png  — multi-panel summary figure
    Pass/fail summary printed to stdout (exit 0 = all checks passed)
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import geopandas as gpd
import xarray as xr

SEC_PER_DAY = 86400.0
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def load_zarr(work_dir, subpath, varname):
    """Open a zarr store and return the variable, always transposed to (time, y, x)."""
    ds = xr.open_zarr(f"{work_dir}/{subpath}")
    da = ds[varname]
    if {"time", "y", "x"}.issubset(da.dims):
        da = da.transpose("time", "y", "x")
    return da


PR_MAX_BOUND  = 500.0    # mm d-1  — absolute physical ceiling for daily precipitation
SNW_MAX_BOUND = 50_000.0 # kg m-2  — ~5× ERA5 test-domain max; flags QDM extrapolation blowup


def check_physical(da, label, max_bound):
    """Return (passed, message).

    Checks:
      - no negatives
      - NaN fraction < 95%  (high NaN is expected for small domains padded with NaN surround)
      - no values exceeding max_bound
    """
    arr = da.values
    n_nan = int(np.isnan(arr).sum())
    nan_pct = 100.0 * n_nan / arr.size
    n_neg = int((arr < 0).sum())
    n_extreme = int((arr > max_bound).sum())
    vmin = float(np.nanmin(arr))
    vmax = float(np.nanmax(arr))
    vmean = float(np.nanmean(arr))
    passed = (n_neg == 0) and (nan_pct < 95.0) and (n_extreme == 0)
    status = "PASS" if passed else "FAIL"
    msg = (
        f"  [{status}] {label}: "
        f"nan={nan_pct:.1f}%, neg={n_neg}, extreme(>{max_bound:.0f})={n_extreme}, "
        f"range=[{vmin:.3f}, {vmax:.2f}], mean={vmean:.4f}"
    )
    return passed, msg


def monthly_climo(da):
    """Spatial mean then monthly climatology. Returns array of shape (12,)."""
    return da.mean(dim=["y", "x"]).groupby("time.month").mean("time").compute().values


def empirical_cdf(da, n_sample=50_000):
    """Return (x_sorted, cdf_y) from a random subsample of non-NaN values."""
    vals = da.values.ravel()
    vals = vals[~np.isnan(vals)]
    if len(vals) > n_sample:
        rng = np.random.default_rng(42)
        vals = rng.choice(vals, n_sample, replace=False)
    vals = np.sort(vals)
    return vals, np.arange(1, len(vals) + 1) / len(vals)


def time_mean_map(da):
    return da.mean("time").compute().values


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("work_dir", help="Pipeline work directory (contains adjusted/, era5_zarr/, etc.)")
    args = parser.parse_args()
    wd = args.work_dir.rstrip("/")

    # ------------------------------------------------------------------
    # Load all stores
    # ------------------------------------------------------------------
    print("Loading data...")
    pr_hist_adj  = load_zarr(wd, "adjusted/pr_MIROC6_historical_adjusted.zarr", "pr")
    pr_ssp_adj   = load_zarr(wd, "adjusted/pr_MIROC6_ssp370_adjusted.zarr",     "pr")
    snw_hist_adj = load_zarr(wd, "adjusted/snw_MIROC6_historical_adjusted.zarr", "snw")
    snw_ssp_adj  = load_zarr(wd, "adjusted/snw_MIROC6_ssp370_adjusted.zarr",     "snw")
    # Raw CMIP6: pr in kg m-2 s-1 → mm d-1
    pr_hist_raw  = load_zarr(wd, "cmip6_zarr/pr_MIROC6_historical.zarr", "pr") * SEC_PER_DAY
    snw_hist_raw = load_zarr(wd, "cmip6_zarr/snw_MIROC6_historical.zarr", "snw")
    # ERA5 reference
    pr_era5  = load_zarr(wd, "era5_zarr/pr_era5.zarr",          "pr")
    snw_era5 = load_zarr(wd, "era5_zarr/snow_sum_era5.zarr", "snow_sum")

    all_pass = True

    # ------------------------------------------------------------------
    # 1. Physical plausibility
    # ------------------------------------------------------------------
    print("\n=== 1. Physical plausibility ===")
    plaus_results = []
    for da, label, bound in [
        (pr_hist_adj.compute(),  "pr  hist adjusted",  PR_MAX_BOUND),
        (pr_ssp_adj.compute(),   "pr  ssp370 adjusted", PR_MAX_BOUND),
        (snw_hist_adj.compute(), "snw hist adjusted",  SNW_MAX_BOUND),
        (snw_ssp_adj.compute(),  "snw ssp370 adjusted", SNW_MAX_BOUND),
    ]:
        passed, msg = check_physical(da, label, bound)
        plaus_results.append(passed)
        print(msg)
    plaus_pass = all(plaus_results)
    all_pass = all_pass and plaus_pass
    print(f"  => {'PASS' if plaus_pass else 'FAIL'}")
    if not plaus_pass:
        print("  NOTE: extreme values in land-only variables (e.g. snw) are a known QDM")
        print("  upper-tail artifact. Post-processing (output clipping) is required before")
        print("  scientific use. See test/README.md for details.")

    # ------------------------------------------------------------------
    # 2. Bias reduction — monthly climatology
    # ------------------------------------------------------------------
    print("\n=== 2. Bias reduction (monthly climatology RMSE) ===")
    pr_raw_climo   = monthly_climo(pr_hist_raw)
    pr_adj_climo   = monthly_climo(pr_hist_adj)
    pr_era5_climo  = monthly_climo(pr_era5)
    snw_raw_climo  = monthly_climo(snw_hist_raw)
    snw_adj_climo  = monthly_climo(snw_hist_adj)
    snw_era5_climo = monthly_climo(snw_era5)

    pr_rmse_before  = float(np.sqrt(np.mean((pr_raw_climo  - pr_era5_climo)**2)))
    pr_rmse_after   = float(np.sqrt(np.mean((pr_adj_climo  - pr_era5_climo)**2)))
    snw_rmse_before = float(np.sqrt(np.mean((snw_raw_climo - snw_era5_climo)**2)))
    snw_rmse_after  = float(np.sqrt(np.mean((snw_adj_climo - snw_era5_climo)**2)))
    pr_bias_pass  = pr_rmse_after  < pr_rmse_before
    snw_bias_pass = snw_rmse_after < snw_rmse_before
    bias_pass = pr_bias_pass and snw_bias_pass
    all_pass = all_pass and bias_pass
    print(f"  pr:  RMSE before={pr_rmse_before:.4f}  after={pr_rmse_after:.4f}  "
          f"{'PASS' if pr_bias_pass else 'FAIL'}")
    print(f"  snw: RMSE before={snw_rmse_before:.2f}  after={snw_rmse_after:.2f}  "
          f"{'PASS' if snw_bias_pass else 'FAIL'}")
    print(f"  => {'PASS' if bias_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # 3. CDFs
    # ------------------------------------------------------------------
    print("\n=== 3. Distribution (CDF) — computing... ===")
    pr_raw_x,  pr_raw_y  = empirical_cdf(pr_hist_raw.compute())
    pr_adj_x,  pr_adj_y  = empirical_cdf(pr_hist_adj.compute())
    pr_era5_x, pr_era5_y = empirical_cdf(pr_era5.compute())
    snw_raw_x,  snw_raw_y  = empirical_cdf(snw_hist_raw.compute())
    snw_adj_x,  snw_adj_y  = empirical_cdf(snw_hist_adj.compute())
    snw_era5_x, snw_era5_y = empirical_cdf(snw_era5.compute())

    # KS-distance: max |CDF_adjusted - CDF_ERA5| at common quantile levels
    quantiles = np.linspace(0.01, 0.99, 99)
    pr_adj_q  = np.quantile(pr_adj_x,  quantiles)
    pr_era5_q = np.quantile(pr_era5_x, quantiles)
    pr_ks = float(np.max(np.abs(pr_adj_q - pr_era5_q)))
    snw_adj_q  = np.quantile(snw_adj_x,  quantiles)
    snw_era5_q = np.quantile(snw_era5_x, quantiles)
    snw_ks = float(np.max(np.abs(snw_adj_q - snw_era5_q)))
    print(f"  pr  max quantile gap (adj vs ERA5): {pr_ks:.4f} mm d-1")
    print(f"  snw max quantile gap (adj vs ERA5): {snw_ks:.2f} kg m-2")

    # ------------------------------------------------------------------
    # 4. Spatial mean maps
    # ------------------------------------------------------------------
    print("\n=== 4. Spatial mean maps — computing... ===")
    pr_era5_map      = time_mean_map(pr_era5)
    pr_raw_map       = time_mean_map(pr_hist_raw)
    pr_hist_adj_map  = time_mean_map(pr_hist_adj)
    snw_era5_map     = time_mean_map(snw_era5)
    snw_raw_map      = time_mean_map(snw_hist_raw)
    snw_hist_adj_map = time_mean_map(snw_hist_adj)

    # ------------------------------------------------------------------
    # 5. Future delta sanity
    # ------------------------------------------------------------------
    print("\n=== 5. Future delta sanity (ssp370 − hist) ===")
    pr_ssp_adj_map  = time_mean_map(pr_ssp_adj)
    snw_ssp_adj_map = time_mean_map(snw_ssp_adj)
    pr_delta_map  = pr_ssp_adj_map  - pr_hist_adj_map
    snw_delta_map = snw_ssp_adj_map - snw_hist_adj_map
    pr_delta_mean  = float(np.nanmean(pr_delta_map))
    snw_delta_mean = float(np.nanmean(snw_delta_map))
    # Flag if domain-mean change is implausibly large (>10 mm d-1 or >500 kg m-2)
    pr_delta_ok  = abs(pr_delta_mean)  < 10.0
    snw_delta_ok = abs(snw_delta_mean) < 500.0
    delta_pass = pr_delta_ok and snw_delta_ok
    all_pass = all_pass and delta_pass
    print(f"  pr  mean delta: {pr_delta_mean:+.4f} mm d-1  "
          f"({'PASS' if pr_delta_ok else 'FAIL — extreme value'})")
    print(f"  snw mean delta: {snw_delta_mean:+.2f} kg m-2  "
          f"({'PASS' if snw_delta_ok else 'FAIL — extreme value'})")
    print(f"  => {'PASS' if delta_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*42}")
    print(f"  OVERALL QC: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*42}\n")

    # ------------------------------------------------------------------
    # Figure  (7 rows × 2 cols, split into two GridSpec blocks so there
    # is an explicit gap between the line plots and the map panels)
    # Rows 0–1: monthly climatology / empirical CDFs
    # Rows 2–6: spatial mean maps + delta maps
    # ------------------------------------------------------------------
    print("Generating figure...")
    import matplotlib.gridspec as gridspec
    fig = plt.figure(figsize=(14, 30))
    fig.suptitle("QC Report — Bias-Adjusted Pipeline Outputs\n"
                 "(MIROC6 · Seward Peninsula · pr & snw · 2000–2009 training)",
                 fontsize=13, fontweight="bold", y=0.995)

    # top block: 2 rows of line plots  (figure coords 0.72 → 0.97)
    gs_top = gridspec.GridSpec(2, 2, figure=fig,
                               top=0.97, bottom=0.72, hspace=0.40)
    # bottom block: 5 rows of map panels (figure coords 0.02 → 0.67)
    gs_bot = gridspec.GridSpec(5, 2, figure=fig,
                               top=0.67, bottom=0.02, hspace=0.35)

    axes = {}
    for r in range(2):
        for c in range(2):
            axes[(r, c)] = fig.add_subplot(gs_top[r, c])
    for r in range(5):
        for c in range(2):
            axes[(r + 2, c)] = fig.add_subplot(gs_bot[r, c])
    months_x = np.arange(1, 13)

    # --- Row 0: Monthly climatology ---
    ax = axes[(0, 0)]
    ax.plot(months_x, pr_raw_climo,  "C0--", label="CMIP6 raw", linewidth=1.5)
    ax.plot(months_x, pr_adj_climo,  "C0-",  label="Adjusted",  linewidth=2.0)
    ax.plot(months_x, pr_era5_climo, "C1-",  label="ERA5 ref",  linewidth=1.5)
    ax.set_xticks(months_x)
    ax.set_xticklabels(MONTHS, fontsize=8)
    ax.set_ylabel("pr (mm d⁻¹)")
    ax.set_title("pr — Monthly Climatology (historical)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[(0, 1)]
    ax.plot(months_x, snw_raw_climo,  "C2--", label="CMIP6 raw", linewidth=1.5)
    ax.plot(months_x, snw_adj_climo,  "C2-",  label="Adjusted",  linewidth=2.0)
    ax.plot(months_x, snw_era5_climo, "C3-",  label="ERA5 ref",  linewidth=1.5)
    ax.set_xticks(months_x)
    ax.set_xticklabels(MONTHS, fontsize=8)
    ax.set_ylabel("snw (kg m⁻²)")
    ax.set_title("snw — Monthly Climatology (historical)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- Row 1: Empirical CDFs ---
    ax = axes[(1, 0)]
    ax.plot(pr_raw_x,  pr_raw_y,  "C0--", label="CMIP6 raw", linewidth=1.5)
    ax.plot(pr_adj_x,  pr_adj_y,  "C0-",  label="Adjusted",  linewidth=2.0)
    ax.plot(pr_era5_x, pr_era5_y, "C1-",  label="ERA5 ref",  linewidth=1.5)
    ax.set_xlabel("pr (mm d⁻¹)")
    ax.set_ylabel("CDF")
    ax.set_xlim(left=0)
    ax.set_title(f"pr — Empirical CDF (historical)  [max gap: {pr_ks:.3f} mm d⁻¹]")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[(1, 1)]
    ax.plot(snw_raw_x,  snw_raw_y,  "C2--", label="CMIP6 raw", linewidth=1.5)
    ax.plot(snw_adj_x,  snw_adj_y,  "C2-",  label="Adjusted",  linewidth=2.0)
    ax.plot(snw_era5_x, snw_era5_y, "C3-",  label="ERA5 ref",  linewidth=1.5)
    ax.set_xlabel("snw (kg m⁻²)")
    ax.set_ylabel("CDF")
    ax.set_xlim(left=0)
    ax.set_title(f"snw — Empirical CDF (historical)  [max gap: {snw_ks:.2f} kg m⁻²]")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Load grid coordinates (EPSG:3338) from ERA5 zarr — all outputs share this grid
    _ds_coords = xr.open_zarr(f"{wd}/era5_zarr/pr_era5.zarr")
    x_coords = _ds_coords.x.values   # shape (62,) — easting, metres
    y_coords = _ds_coords.y.values   # shape (70,) — northing, metres (y[0] = north)

    # Load and reproject Natural Earth coastline to EPSG:3338
    ne_path = Path(__file__).parent / "data/natural_earth/ne_50m_coastline.shp"
    coast = gpd.read_file(ne_path).to_crs("EPSG:3338")

    # extent for imshow: [left, right, bottom, top] in EPSG:3338 metres
    # origin="upper" so that array row 0 (northernmost) maps to the top of the axes
    map_extent = [x_coords.min(), x_coords.max(), y_coords.min(), y_coords.max()]

    def map_panel(ax, data, title, label, cmap, vmin=None, vmax=None):
        if vmin is None:
            vmin = np.nanmin(data)
        if vmax is None:
            vmax = np.nanpercentile(data, 99)
        im = ax.imshow(data, origin="upper", cmap=cmap, vmin=vmin, vmax=vmax,
                       extent=map_extent, aspect="equal")
        coast.plot(ax=ax, color="black", linewidth=0.6)
        ax.set_xlim(x_coords.min(), x_coords.max())
        ax.set_ylim(y_coords.min(), y_coords.max())
        ax.set_title(title, fontsize=9)
        ax.axis("off")
        plt.colorbar(im, ax=ax, label=label, shrink=0.8, pad=0.02)
        return im

    # --- Row 2: ERA5 mean ---
    # Shared colour scales across all mean-value rows (ERA5 / raw / hist adj / ssp370 adj)
    vmin_pr  = 0
    vmax_pr  = max(np.nanpercentile(pr_era5_map,     99),
                   np.nanpercentile(pr_raw_map,       99),
                   np.nanpercentile(pr_hist_adj_map,  99),
                   np.nanpercentile(pr_ssp_adj_map,   99))
    vmin_snw = 0
    vmax_snw = max(np.nanpercentile(snw_era5_map,     99),
                   np.nanpercentile(snw_raw_map,       99),
                   np.nanpercentile(snw_hist_adj_map,  99),
                   np.nanpercentile(snw_ssp_adj_map,   99))

    # --- Row 2: ERA5 mean ---
    map_panel(axes[(2, 0)], pr_era5_map,      "pr mean — ERA5 (2000–2009)",            "mm d⁻¹", "Blues", vmin_pr,  vmax_pr)
    map_panel(axes[(2, 1)], snw_era5_map,     "snw mean — ERA5 (2000–2009)",           "kg m⁻²", "Blues", vmin_snw, vmax_snw)

    # --- Row 3: CMIP6 raw mean ---
    map_panel(axes[(3, 0)], pr_raw_map,       "pr mean — CMIP6 raw (2000–2009)",       "mm d⁻¹", "Blues", vmin_pr,  vmax_pr)
    map_panel(axes[(3, 1)], snw_raw_map,      "snw mean — CMIP6 raw (2000–2009)",      "kg m⁻²", "Blues", vmin_snw, vmax_snw)

    # --- Row 4: Adjusted historical mean ---
    map_panel(axes[(4, 0)], pr_hist_adj_map,  "pr mean — Adjusted hist (2000–2009)",   "mm d⁻¹", "Blues", vmin_pr,  vmax_pr)
    map_panel(axes[(4, 1)], snw_hist_adj_map, "snw mean — Adjusted hist (2000–2009)",  "kg m⁻²", "Blues", vmin_snw, vmax_snw)

    # --- Row 5: Adjusted ssp370 mean ---
    map_panel(axes[(5, 0)], pr_ssp_adj_map,   "pr mean — Adjusted ssp370 (2045–2054)", "mm d⁻¹", "Blues", vmin_pr,  vmax_pr)
    map_panel(axes[(5, 1)], snw_ssp_adj_map,  "snw mean — Adjusted ssp370 (2045–2054)","kg m⁻²", "Blues", vmin_snw, vmax_snw)

    # --- Row 6: Future delta maps ---
    abs_max_pr  = max(np.nanpercentile(np.abs(pr_delta_map),  99), 1e-6)
    abs_max_snw = max(np.nanpercentile(np.abs(snw_delta_map), 99), 1e-6)
    map_panel(axes[(6, 0)], pr_delta_map,  f"pr delta ssp370 − hist  (mean: {pr_delta_mean:+.3f})",   "mm d⁻¹", "RdBu_r", -abs_max_pr,  abs_max_pr)
    map_panel(axes[(6, 1)], snw_delta_map, f"snw delta ssp370 − hist  (mean: {snw_delta_mean:+.1f})", "kg m⁻²", "RdBu_r", -abs_max_snw, abs_max_snw)

    outpath = f"{wd}/qc_report.png"
    fig.savefig(outpath, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure saved: {outpath}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
