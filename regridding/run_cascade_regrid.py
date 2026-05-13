"""Run cascade regridding sequentially on all files in a regridded directory.

Replaces the SLURM-based run_regrid_again job array. Writes batch files grouped
by model, then calls regrid.py on each batch against a new target grid.

Run this script twice for a 3-stage cascade:
  1. first_regrid → intermediate_1   (run_first_regrid.py)
  2. intermediate_1 → intermediate_2 (this script)
  3. intermediate_2 → final ERA5 grid (this script again, different target_grid)

Example usage:
    python run_cascade_regrid.py \
        --regridded_dir /path/to/first_regrid_output \
        --batch_dir /path/to/cascade_batch \
        --target_grid /path/to/second_intermediate_target.nc \
        --output_dir /path/to/second_regrid_output \
        --interp_method bilinear
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

BATCH_SIZE = 200


def write_batch_files(src_fps, batch_dir):
    """Write batch files grouped by model (for model-specific sftlf support)."""
    files_by_model = {}
    for fp in src_fps:
        # expected structure: .../model/scenario/frequency/variable/file.nc
        model = fp.parts[-5] if len(fp.parts) >= 5 else "unknown"
        files_by_model.setdefault(model, []).append(fp)

    batch_infos = []
    batch_num = 1
    for model, model_files in sorted(files_by_model.items()):
        logging.info(f"  Model {model}: {len(model_files)} files")
        for i in range(0, len(model_files), BATCH_SIZE):
            chunk = model_files[i : i + BATCH_SIZE]
            batch_file = batch_dir / f"batch_{batch_num}_{model}.txt"
            with open(batch_file, "w") as f:
                for fp in chunk:
                    f.write(f"{fp}\n")
            batch_infos.append((batch_file, model))
            batch_num += 1

    return batch_infos


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regridded_dir",
        type=str,
        required=True,
        help="Directory containing already-regridded NetCDF files",
    )
    parser.add_argument(
        "--batch_dir",
        type=str,
        required=True,
        help="Directory to write cascade batch files (will be created)",
    )
    parser.add_argument(
        "--target_grid",
        type=str,
        required=True,
        help="Target grid file for this cascade stage",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Directory to write cascade-regridded output files",
    )
    parser.add_argument(
        "--interp_method",
        type=str,
        required=True,
        help="Interpolation method: bilinear or conservative",
    )
    parser.add_argument(
        "--sftlf_dir",
        type=str,
        default=None,
        help=(
            "Directory with model-specific sftlf files named "
            "'cascade_regrid_target_sftlf_<MODEL>.nc' (optional)"
        ),
    )
    parser.add_argument(
        "--no_clobber",
        action="store_true",
        help="Skip files that have already been regridded",
    )
    parser.add_argument(
        "--regrid_script",
        type=str,
        default=str(Path(__file__).parent / "regrid.py"),
        help="Path to regrid.py (default: same directory as this script)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    regridded_dir = Path(args.regridded_dir)
    batch_dir = Path(args.batch_dir)
    output_dir = Path(args.output_dir)
    sftlf_dir = Path(args.sftlf_dir) if args.sftlf_dir else None

    batch_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    src_fps = list(regridded_dir.glob("**/*.nc"))
    if not src_fps:
        logging.error(f"No .nc files found in {regridded_dir}")
        sys.exit(1)

    logging.info(f"Found {len(src_fps)} files to cascade-regrid")
    batch_infos = write_batch_files(src_fps, batch_dir)
    logging.info(f"Created {len(batch_infos)} batch files in {batch_dir}")

    errors = []
    for i, (batch_file, model) in enumerate(batch_infos, 1):
        logging.info(
            f"Cascade batch {i}/{len(batch_infos)}: {batch_file.name} (model={model})"
        )

        cmd = [
            sys.executable,
            args.regrid_script,
            "-b", str(batch_file),
            "-d", args.target_grid,
            "-o", str(output_dir),
            "--interp_method", args.interp_method,
        ]

        if sftlf_dir:
            sftlf_fp = sftlf_dir / f"cascade_regrid_target_sftlf_{model}.nc"
            if sftlf_fp.exists():
                cmd += ["--src_sftlf_fp", str(sftlf_fp), "--dst_sftlf_fp", str(sftlf_fp)]
                logging.info(f"  Using model sftlf: {sftlf_fp.name}")
            else:
                logging.info(f"  No sftlf for model {model}, skipping land masking")

        if args.no_clobber:
            cmd += ["--no-clobber"]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Cascade batch {batch_file.name} failed (exit {result.returncode})")
            errors.append(batch_file.name)

    if errors:
        logging.error(f"{len(errors)}/{len(batch_infos)} cascade batches failed: {errors}")
        sys.exit(1)

    logging.info(f"All {len(batch_infos)} cascade batches completed successfully")
