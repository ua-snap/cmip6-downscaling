"""Train QDM bias adjustment models sequentially for each model/variable combination.

Only the historical CMIP6 data is used for training. Saves one trained model
(.zarr) per (model, variable) pair.

Example usage:
    python run_train_qm.py \
        --sim_dir /path/to/cmip6_zarr \
        --ref_dir /path/to/era5_zarr \
        --output_dir /path/to/trained_models \
        --tmp_dir /path/to/dask_tmp \
        --models "GFDL-ESM4 CESM2" \
        --variables "tasmax pr dtr"
"""

import argparse
import logging
import subprocess
import sys
from itertools import product
from pathlib import Path

from config import cmip6_zarr_tmp_fn, era5_zarr_tmp_fn, trained_qm_tmp_fn
from luts import sim_ref_var_lu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim_dir", type=str, required=True,
                        help="Directory containing CMIP6 Zarr stores")
    parser.add_argument("--ref_dir", type=str, required=True,
                        help="Directory containing ERA5 Zarr stores")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Directory to write trained QDM Zarr stores")
    parser.add_argument("--tmp_dir", type=str, required=True,
                        help="Dask temporary file directory")
    parser.add_argument("--models", type=str, required=True,
                        help="Space-separated list of model names")
    parser.add_argument("--variables", type=str, required=True,
                        help="Space-separated list of variable IDs")
    parser.add_argument(
        "--worker_script",
        type=str,
        default=str(Path(__file__).parent / "train_qm.py"),
        help="Path to train_qm.py (default: same directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sim_dir = Path(args.sim_dir)
    ref_dir = Path(args.ref_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    models = args.models.split()
    variables = args.variables.split()
    combos = list(product(models, variables))
    errors = []

    for count, (model, var_id) in enumerate(combos, 1):
        sim_path = sim_dir / cmip6_zarr_tmp_fn.format(
            model=model, scenario="historical", var_id=var_id
        )
        if not sim_path.exists():
            logging.warning(
                f"[{count}/{len(combos)}] Skipping {model}/{var_id}: {sim_path} not found"
            )
            continue

        ref_var_id = sim_ref_var_lu.get(var_id)
        if ref_var_id is None:
            logging.warning(
                f"[{count}/{len(combos)}] Skipping {var_id}: not in sim_ref_var_lu"
            )
            continue

        ref_path = ref_dir / era5_zarr_tmp_fn.format(var_id=ref_var_id)
        train_path = output_dir / trained_qm_tmp_fn.format(var_id=var_id, model=model)

        logging.info(f"[{count}/{len(combos)}] Training QDM: {model}/{var_id}")

        cmd = [
            sys.executable, args.worker_script,
            "--sim_path", str(sim_path),
            "--ref_path", str(ref_path),
            "--train_path", str(train_path),
            "--tmp_path", args.tmp_dir,
        ]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Failed: {model}/{var_id}")
            errors.append(f"{model}/{var_id}")

    if errors:
        logging.error(f"{len(errors)}/{len(combos)} training jobs failed: {errors}")
        sys.exit(1)

    logging.info("QDM training completed")
