#!/usr/bin/env python
"""
QC script for bias-adjusted pipeline outputs.

Produces one PNG per variable saved to {work_dir}/qc/.

Usage:
    python test/qc_adjusted_outputs.py /path/to/work_dir [--model MODEL]

Outputs:
    {work_dir}/qc/{var}.png   per-variable QC figure
    Pass/fail summary printed to stdout (exit 0 = all checks passed)
"""
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import geopandas as gpd
import xarray as xr

# nanmean over all-NaN columns (NaN surround outside the test domain) is expected
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)

SEC_PER_DAY = 86400.0
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Per-variable configuration.
#   era5_store / era5_var : ERA5 reference zarr and variable name inside it
#                           (None for derived variables with no direct ERA5 reference)
#   cmip6_var             : variable name in the raw CMIP6 zarr
#                           (None for derived variables)
#   cmip6_scale           : multiply raw CMIP6 values by this (e.g. pr kg m-2 s-1 → mm d-1)
#   min_bound / max_bound : physical plausibility limits
#   force_vmin_zero       : pin the map colour-scale lower bound at 0
VARIABLES = {
    "pr": {
        "label": "Precipitation",
        "units": "mm d⁻¹",
        "era5_store": "pr_era5.zarr",
        "era5_var": "pr",
        "cmip6_var": "pr",
        "cmip6_scale": SEC_PER_DAY,
        "min_bound": 0.0,
        "max_bound": 500.0,
        "cmap": "Blues",
        "delta_threshold": 10.0,
        "force_vmin_zero": True,
    },
    "snw": {
        "label": "Snow Water Equivalent",
        "units": "kg m⁻²",
        "era5_store": "snow_sum_era5.zarr",
        "era5_var": "snow_sum",
        "cmip6_var": "snw",
        "cmip6_scale": 1.0,
        "min_bound": 0.0,
        "max_bound": 50_000.0,
        "cmap": "Blues",
        "delta_threshold": 500.0,
        "force_vmin_zero": True,
    },
    "tasmax": {
        "label": "Daily Maximum Temperature",
        "units": "K",
        "era5_store": "t2max_era5.zarr",
        "era5_var": "t2max",
        "cmip6_var": "tasmax",
        "cmip6_scale": 1.0,
        "min_bound": 200.0,
        "max_bound": 340.0,
        "cmap": "RdYlBu_r",
        "delta_threshold": 20.0,
        "force_vmin_zero": False,
    },
    "dtr": {
        "label": "Diurnal Temperature Range",
        "units": "K",
        "era5_store": "dtr_era5.zarr",
        "era5_var": "dtr",
        "cmip6_var": "dtr",
        "cmip6_scale": 1.0,
        "min_bound": 0.0,
        "max_bound": 60.0,  # QDM upper-tail extrapolation can exceed typical ~30 K Alaska range
        "cmap": "YlOrRd",
        "delta_threshold": 10.0,
        "force_vmin_zero": True,
    },
    "tasmin": {
        "label": "Daily Minimum Temperature",
        "units": "K",
        "era5_store": None,
        "era5_var": None,
        "cmip6_var": None,
        "cmip6_scale": 1.0,
        "min_bound": 200.0,
        "max_bound": 330.0,
        "cmap": "RdYlBu_r",
        "delta_threshold": 20.0,
        "force_vmin_zero": False,
    },
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_zarr(path, varname):
    """Open a zarr store and return the DataArray transposed to (time, y, x)."""
    ds = xr.open_zarr(str(path))
    da = ds[varname]
    if {"time", "y", "x"}.issubset(da.dims):
        da = da.transpose("time", "y", "x")
    return da


def check_physical(arr, label, cfg):
    """Return (passed, message). Checks NaN fraction and min/max bounds."""
    finite = arr[~np.isnan(arr)]
    nan_pct = 100.0 * np.isnan(arr).sum() / arr.size
    n_below = int((finite < cfg["min_bound"]).sum())
    n_above = int((finite > cfg["max_bound"]).sum())
    vmin = float(np.nanmin(arr)) if finite.size else float("nan")
    vmax = float(np.nanmax(arr)) if finite.size else float("nan")
    vmean = float(np.nanmean(arr)) if finite.size else float("nan")
    passed = (n_below == 0) and (nan_pct < 95.0) and (n_above == 0)
    status = "PASS" if passed else "FAIL"
    msg = (
        f"  [{status}] {label}: nan={nan_pct:.1f}%, "
        f"below_min={n_below}, above_max={n_above}, "
        f"range=[{vmin:.3f}, {vmax:.3f}], mean={vmean:.4f}"
    )
    return passed, msg


def monthly_climo(da):
    """Spatial mean then monthly climatology. Returns (12,) array."""
    return da.mean(dim=["y", "x"]).groupby("time.month").mean("time").compute().values


def empirical_cdf(arr, n_sample=50_000):
    """Return (sorted_values, cdf_y) from a random subsample of non-NaN values."""
    vals = arr.ravel()
    vals = vals[~np.isnan(vals)]
    if len(vals) > n_sample:
        rng = np.random.default_rng(42)
        vals = rng.choice(vals, n_sample, replace=False)
    vals = np.sort(vals)
    return vals, np.arange(1, len(vals) + 1) / len(vals)


def map_panel(ax, data, title, cmap, vmin, vmax, units,
              coast, map_extent, x_coords, y_coords):
    im = ax.imshow(data, origin="upper", cmap=cmap, vmin=vmin, vmax=vmax,
                   extent=map_extent, aspect="equal")
    coast.plot(ax=ax, color="black", linewidth=0.6)
    ax.set_xlim(x_coords.min(), x_coords.max())
    ax.set_ylim(y_coords.min(), y_coords.max())
    ax.set_title(title, fontsize=9)
    ax.axis("off")
    plt.colorbar(im, ax=ax, label=units, shrink=0.8, pad=0.02)


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def _map_vrange(arrays, force_vmin_zero):
    vmin = 0.0 if force_vmin_zero else min(np.nanpercentile(a, 1) for a in arrays)
    vmax = max(np.nanpercentile(a, 99) for a in arrays)
    return vmin, vmax


def make_figure_with_ref(var, cfg, hist_arr, ssp_arr, era5_arr, raw_arr,
                          hist_da, era5_da, raw_da,
                          coast, map_extent, x_coords, y_coords, model):
    """Full QC figure for variables that have an ERA5 reference and raw CMIP6."""
    label, units, cmap = cfg["label"], cfg["units"], cfg["cmap"]

    # Maps
    era5_map = np.nanmean(era5_arr, axis=0)
    raw_map  = np.nanmean(raw_arr,  axis=0)
    hist_map = np.nanmean(hist_arr, axis=0)
    ssp_map  = np.nanmean(ssp_arr,  axis=0)
    delta_map = ssp_map - hist_map
    delta_mean = float(np.nanmean(delta_map))
    abs_max_delta = max(np.nanpercentile(np.abs(delta_map), 99), 1e-6)
    vmin_map, vmax_map = _map_vrange([era5_map, raw_map, hist_map, ssp_map],
                                      cfg["force_vmin_zero"])

    # Climatology (DataArrays needed for groupby)
    raw_climo  = monthly_climo(raw_da)
    adj_climo  = monthly_climo(hist_da)
    era5_climo = monthly_climo(era5_da)

    # CDFs
    raw_x,  raw_y  = empirical_cdf(raw_arr)
    adj_x,  adj_y  = empirical_cdf(hist_arr)
    era5_x, era5_y = empirical_cdf(era5_arr)
    quantiles = np.linspace(0.01, 0.99, 99)
    ks = float(np.max(np.abs(np.quantile(adj_x, quantiles) - np.quantile(era5_x, quantiles))))

    # Layout:  line plots | 2×2 maps | delta (full-width)
    fig = plt.figure(figsize=(10, 24))
    fig.suptitle(f"{label} ({var})  —  QC Report\n"
                 f"{model} · Seward Peninsula test domain",
                 fontsize=12, fontweight="bold", y=0.995)

    gs_lines = gridspec.GridSpec(1, 2, figure=fig, top=0.96, bottom=0.80, wspace=0.35)
    gs_maps  = gridspec.GridSpec(2, 2, figure=fig, top=0.76, bottom=0.26,
                                 hspace=0.08, wspace=0.08)
    gs_delta = gridspec.GridSpec(1, 1, figure=fig, top=0.22, bottom=0.02)

    ax_climo = fig.add_subplot(gs_lines[0, 0])
    ax_cdf   = fig.add_subplot(gs_lines[0, 1])
    ax_era5  = fig.add_subplot(gs_maps[0, 0])
    ax_raw   = fig.add_subplot(gs_maps[0, 1])
    ax_hist  = fig.add_subplot(gs_maps[1, 0])
    ax_ssp   = fig.add_subplot(gs_maps[1, 1])
    ax_delta = fig.add_subplot(gs_delta[0])

    months_x = np.arange(1, 13)
    ax_climo.plot(months_x, raw_climo,  "C0--", label="CMIP6 raw", linewidth=1.5)
    ax_climo.plot(months_x, adj_climo,  "C0-",  label="Adjusted",  linewidth=2.0)
    ax_climo.plot(months_x, era5_climo, "C1-",  label="ERA5 ref",  linewidth=1.5)
    ax_climo.set_xticks(months_x)
    ax_climo.set_xticklabels(MONTHS, fontsize=7)
    ax_climo.set_ylabel(f"{var} ({units})")
    ax_climo.set_title("Monthly Climatology (historical)")
    ax_climo.legend(fontsize=8)
    ax_climo.grid(True, alpha=0.3)

    ax_cdf.plot(raw_x, raw_y,   "C0--", label="CMIP6 raw", linewidth=1.5)
    ax_cdf.plot(adj_x, adj_y,   "C0-",  label="Adjusted",  linewidth=2.0)
    ax_cdf.plot(era5_x, era5_y, "C1-",  label="ERA5 ref",  linewidth=1.5)
    ax_cdf.set_xlabel(f"{var} ({units})")
    ax_cdf.set_ylabel("CDF")
    ax_cdf.set_title(f"Empirical CDF  [max dist: {ks:.4f} {units}]")
    ax_cdf.legend(fontsize=8)
    ax_cdf.grid(True, alpha=0.3)

    mk = dict(units=units, coast=coast, map_extent=map_extent,
              x_coords=x_coords, y_coords=y_coords)
    map_panel(ax_era5, era5_map, "ERA5 reference (2000–2009)",      cmap, vmin_map, vmax_map, **mk)
    map_panel(ax_raw,  raw_map,  "CMIP6 raw (2000–2009)",           cmap, vmin_map, vmax_map, **mk)
    map_panel(ax_hist, hist_map, "Adjusted historical (2000–2009)", cmap, vmin_map, vmax_map, **mk)
    map_panel(ax_ssp,  ssp_map,  "Adjusted ssp370 (2045–2054)",     cmap, vmin_map, vmax_map, **mk)
    map_panel(ax_delta, delta_map,
              f"Delta: ssp370 − hist  (domain mean: {delta_mean:+.4f} {units})",
              "RdBu_r", -abs_max_delta, abs_max_delta, **mk)

    return fig


def make_figure_no_ref(var, cfg, hist_arr, ssp_arr, hist_da,
                        coast, map_extent, x_coords, y_coords, model):
    """Reduced QC figure for derived variables with no ERA5/CMIP6 reference."""
    label, units, cmap = cfg["label"], cfg["units"], cfg["cmap"]

    hist_map  = np.nanmean(hist_arr, axis=0)
    ssp_map   = np.nanmean(ssp_arr,  axis=0)
    delta_map = ssp_map - hist_map
    delta_mean = float(np.nanmean(delta_map))
    abs_max_delta = max(np.nanpercentile(np.abs(delta_map), 99), 1e-6)
    vmin_map, vmax_map = _map_vrange([hist_map, ssp_map], cfg["force_vmin_zero"])

    # Show spatial-mean time series since we have no climatology reference
    hist_ts = hist_da.mean(dim=["y", "x"]).compute().values

    fig = plt.figure(figsize=(10, 16))
    fig.suptitle(f"{label} ({var})  —  QC Report\n"
                 f"{model} · Seward Peninsula test domain  (derived variable, no ERA5 reference)",
                 fontsize=12, fontweight="bold", y=0.995)

    gs_ts    = gridspec.GridSpec(1, 1, figure=fig, top=0.96, bottom=0.80)
    gs_maps  = gridspec.GridSpec(1, 2, figure=fig, top=0.76, bottom=0.38, wspace=0.08)
    gs_delta = gridspec.GridSpec(1, 1, figure=fig, top=0.34, bottom=0.02)

    ax_ts    = fig.add_subplot(gs_ts[0])
    ax_hist  = fig.add_subplot(gs_maps[0, 0])
    ax_ssp   = fig.add_subplot(gs_maps[0, 1])
    ax_delta = fig.add_subplot(gs_delta[0])

    ax_ts.plot(hist_ts, linewidth=0.8, color="C0")
    ax_ts.set_ylabel(f"{var} ({units})")
    ax_ts.set_xlabel("Time step")
    ax_ts.set_title("Domain-mean time series — adjusted historical")
    ax_ts.grid(True, alpha=0.3)

    mk = dict(units=units, coast=coast, map_extent=map_extent,
              x_coords=x_coords, y_coords=y_coords)
    map_panel(ax_hist, hist_map, "Adjusted historical (2000–2009)", cmap, vmin_map, vmax_map, **mk)
    map_panel(ax_ssp,  ssp_map,  "Adjusted ssp370 (2045–2054)",     cmap, vmin_map, vmax_map, **mk)
    map_panel(ax_delta, delta_map,
              f"Delta: ssp370 − hist  (domain mean: {delta_mean:+.4f} {units})",
              "RdBu_r", -abs_max_delta, abs_max_delta, **mk)

    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("work_dir",
                        help="Pipeline work directory (contains adjusted/, era5_zarr/, etc.)")
    parser.add_argument("--model", default="MIROC6",
                        help="Model name used in output filenames (default: MIROC6)")
    args = parser.parse_args()
    wd = Path(args.work_dir.rstrip("/"))
    model = args.model

    qc_dir = wd / "qc"
    qc_dir.mkdir(exist_ok=True)

    # Shared grid coordinates — all outputs use the ERA5 grid
    _coords_ds = xr.open_zarr(str(wd / "era5_zarr/pr_era5.zarr"))
    x_coords = _coords_ds.x.values
    y_coords = _coords_ds.y.values
    map_extent = [x_coords.min(), x_coords.max(), y_coords.min(), y_coords.max()]

    ne_path = Path(__file__).parent / "data/natural_earth/ne_50m_coastline.shp"
    coast = gpd.read_file(ne_path).to_crs("EPSG:3338")

    all_pass = True

    for var, cfg in VARIABLES.items():
        hist_store = wd / f"adjusted/{var}_{model}_historical_adjusted.zarr"
        ssp_store  = wd / f"adjusted/{var}_{model}_ssp370_adjusted.zarr"

        if not hist_store.exists() or not ssp_store.exists():
            print(f"\n[{var}] Skipping — adjusted outputs not found in {wd}/adjusted/")
            continue

        print(f"\n{'='*55}")
        print(f"  {cfg['label']} ({var})")
        print(f"{'='*55}")

        hist_da = load_zarr(hist_store, var)
        ssp_da  = load_zarr(ssp_store,  var)
        hist_arr = hist_da.compute().values
        ssp_arr  = ssp_da.compute().values

        var_pass = True

        # 1. Physical plausibility
        print("Physical plausibility:")
        for arr, label in [(hist_arr, f"{var} hist adjusted"),
                           (ssp_arr,  f"{var} ssp370 adjusted")]:
            passed, msg = check_physical(arr, label, cfg)
            var_pass = var_pass and passed
            print(msg)
        if not var_pass and var in ("pr", "snw"):
            print("  NOTE: extreme values in land-only variables are a known QDM upper-tail")
            print("  artifact. Post-processing clipping is required before scientific use.")

        # 2. Bias reduction + figure data
        era5_da = raw_da = era5_arr = raw_arr = None
        has_ref = False

        if cfg["era5_store"] is not None:
            era5_path  = wd / f"era5_zarr/{cfg['era5_store']}"
            cmip6_path = wd / f"cmip6_zarr/{cfg['cmip6_var']}_{model}_historical.zarr"

            if era5_path.exists() and cmip6_path.exists():
                era5_da  = load_zarr(era5_path,  cfg["era5_var"])
                raw_da   = load_zarr(cmip6_path, cfg["cmip6_var"])
                if cfg["cmip6_scale"] != 1.0:
                    raw_da = raw_da * cfg["cmip6_scale"]
                era5_arr = era5_da.compute().values
                raw_arr  = raw_da.compute().values

                raw_climo  = monthly_climo(raw_da)
                adj_climo  = monthly_climo(hist_da)
                era5_climo = monthly_climo(era5_da)
                rmse_before = float(np.sqrt(np.mean((raw_climo  - era5_climo) ** 2)))
                rmse_after  = float(np.sqrt(np.mean((adj_climo  - era5_climo) ** 2)))
                bias_ok = rmse_after < rmse_before
                var_pass = var_pass and bias_ok
                print(f"Bias reduction (monthly climo RMSE): "
                      f"before={rmse_before:.4f}  after={rmse_after:.4f}  "
                      f"{'PASS' if bias_ok else 'FAIL'}")
                has_ref = True
            else:
                print("Bias reduction: skipped (ERA5 or CMIP6 zarr not found)")

        # 3. Future delta sanity
        delta_mean = float(np.nanmean(np.nanmean(ssp_arr, axis=0) - np.nanmean(hist_arr, axis=0)))
        delta_ok = abs(delta_mean) < cfg["delta_threshold"]
        var_pass = var_pass and delta_ok
        print(f"Future delta (ssp370 − hist): {delta_mean:+.4f} {cfg['units']}  "
              f"({'PASS' if delta_ok else 'FAIL — implausibly large'})")

        all_pass = all_pass and var_pass
        print(f"=> {'PASS' if var_pass else 'FAIL'}")

        # 4. Figure
        print("Generating figure...")
        if has_ref:
            fig = make_figure_with_ref(
                var, cfg, hist_arr, ssp_arr, era5_arr, raw_arr,
                hist_da, era5_da, raw_da,
                coast, map_extent, x_coords, y_coords, model,
            )
        else:
            fig = make_figure_no_ref(
                var, cfg, hist_arr, ssp_arr, hist_da,
                coast, map_extent, x_coords, y_coords, model,
            )

        out_path = qc_dir / f"{var}.png"
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved: {out_path}")

    print(f"\n{'='*55}")
    print(f"  OVERALL QC: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*55}\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
