"""Apply QDM bias adjustment sequentially for each model/scenario/variable.

Requires pre-trained QDM stores from run_train_qm.py.

Example usage:
    python run_bias_adjust.py \
        --sim_dir /path/to/cmip6_zarr \
        --train_dir /path/to/trained_models \
        --output_dir /path/to/adjusted \
        --tmp_dir /path/to/dask_tmp \
        --models "GFDL-ESM4 CESM2" \
        --scenarios "historical ssp370" \
        --variables "tasmax pr dtr"
"""

import argparse
import logging
import subprocess
import sys
from itertools import product
from pathlib import Path

from config import cmip6_zarr_tmp_fn, trained_qm_tmp_fn, cmip6_adjusted_tmp_fn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim_dir", type=str, required=True,
                        help="Directory containing CMIP6 Zarr stores")
    parser.add_argument("--train_dir", type=str, required=True,
                        help="Directory containing trained QDM Zarr stores")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Directory to write bias-adjusted Zarr stores")
    parser.add_argument("--tmp_dir", type=str, required=True,
                        help="Dask temporary file directory")
    parser.add_argument("--models", type=str, required=True,
                        help="Space-separated list of model names")
    parser.add_argument("--scenarios", type=str, required=True,
                        help="Space-separated list of scenarios")
    parser.add_argument("--variables", type=str, required=True,
                        help="Space-separated list of variable IDs")
    parser.add_argument(
        "--worker_script",
        type=str,
        default=str(Path(__file__).parent / "bias_adjust.py"),
        help="Path to bias_adjust.py (default: same directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sim_dir = Path(args.sim_dir)
    train_dir = Path(args.train_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    models = args.models.split()
    scenarios = args.scenarios.split()
    variables = args.variables.split()
    combos = list(product(models, scenarios, variables))
    errors = []

    for count, (model, scenario, var_id) in enumerate(combos, 1):
        train_path = train_dir / trained_qm_tmp_fn.format(var_id=var_id, model=model)
        if not train_path.exists():
            logging.warning(
                f"[{count}/{len(combos)}] Skipping {model}/{scenario}/{var_id}: "
                f"trained model {train_path.name} not found"
            )
            continue

        sim_path = sim_dir / cmip6_zarr_tmp_fn.format(
            model=model, scenario=scenario, var_id=var_id
        )
        if not sim_path.exists():
            logging.warning(
                f"[{count}/{len(combos)}] Skipping {model}/{scenario}/{var_id}: "
                f"sim store {sim_path.name} not found"
            )
            continue

        adj_path = output_dir / cmip6_adjusted_tmp_fn.format(
            var_id=var_id, model=model, scenario=scenario
        )

        logging.info(f"[{count}/{len(combos)}] Bias-adjusting: {model}/{scenario}/{var_id}")

        cmd = [
            sys.executable, args.worker_script,
            "--train_path", str(train_path),
            "--sim_path", str(sim_path),
            "--adj_path", str(adj_path),
            "--tmp_path", args.tmp_dir,
        ]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Failed: {model}/{scenario}/{var_id}")
            errors.append(f"{model}/{scenario}/{var_id}")

    if errors:
        logging.error(f"{len(errors)}/{len(combos)} bias-adjustment jobs failed: {errors}")
        sys.exit(1)

    logging.info("Bias adjustment completed")
