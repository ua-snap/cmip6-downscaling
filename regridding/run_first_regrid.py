"""Run regrid.py sequentially on all batch files in a directory.

Replaces the SLURM-based regrid job array with a simple sequential loop.
To process batches in parallel, run multiple instances of this script with
non-overlapping subsets of batch files (split --batch_dir into separate dirs).

Example usage:
    python run_first_regrid.py \
        --batch_dir /path/to/regrid_batch \
        --target_grid /path/to/intermediate_target.nc \
        --output_dir /path/to/first_regrid_output \
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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch_dir",
        type=str,
        required=True,
        help="Directory containing batch .txt files from generate_batch_files.py",
    )
    parser.add_argument(
        "--target_grid",
        type=str,
        required=True,
        help="Intermediate target grid file for first-stage regridding",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Directory to write regridded output files",
    )
    parser.add_argument(
        "--interp_method",
        type=str,
        required=True,
        help="Interpolation method: bilinear or conservative",
    )
    parser.add_argument(
        "--src_sftlf_fp",
        type=str,
        default=None,
        help="Source sftlf file for land/sea masking (optional)",
    )
    parser.add_argument(
        "--dst_sftlf_fp",
        type=str,
        default=None,
        help="Destination sftlf file for land/sea masking (optional)",
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
    batch_dir = Path(args.batch_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_files = sorted(batch_dir.glob("*.txt"))
    if not batch_files:
        logging.error(f"No batch .txt files found in {batch_dir}")
        sys.exit(1)

    logging.info(f"Found {len(batch_files)} batch files in {batch_dir}")

    errors = []
    for i, batch_file in enumerate(batch_files, 1):
        logging.info(f"Processing batch {i}/{len(batch_files)}: {batch_file.name}")

        cmd = [
            sys.executable,
            args.regrid_script,
            "-b", str(batch_file),
            "-d", args.target_grid,
            "-o", str(output_dir),
            "--interp_method", args.interp_method,
        ]
        if args.src_sftlf_fp:
            cmd += ["--src_sftlf_fp", args.src_sftlf_fp]
        if args.dst_sftlf_fp:
            cmd += ["--dst_sftlf_fp", args.dst_sftlf_fp]
        if args.no_clobber:
            cmd += ["--no-clobber"]

        result = subprocess.run(cmd)
        if result.returncode != 0:
            logging.error(f"Batch {batch_file.name} failed (exit {result.returncode})")
            errors.append(batch_file.name)

    if errors:
        logging.error(f"{len(errors)}/{len(batch_files)} batches failed: {errors}")
        sys.exit(1)

    logging.info(f"All {len(batch_files)} batches completed successfully")
