"""
ACGS-2 Data Package
Constitutional Hash: 608508a9bd224290

Contains reference baseline data for drift detection.

Files:
- reference/training_baseline.csv: Pre-generated baseline dataset (CSV format)
- reference/training_baseline.parquet: Baseline dataset (parquet format)
"""

from pathlib import Path

# Package paths
DATA_DIR = Path(__file__).parent
REFERENCE_DIR = DATA_DIR / "reference"
BASELINE_CSV_PATH = REFERENCE_DIR / "training_baseline.csv"
BASELINE_PARQUET_PATH = REFERENCE_DIR / "training_baseline.parquet"


def get_baseline_path() -> Path:
    """
    Get the path to the baseline dataset.

    Returns parquet path if it exists, otherwise CSV path.

    Returns:
        Path to the baseline dataset
    """
    if BASELINE_PARQUET_PATH.exists():
        return BASELINE_PARQUET_PATH
    elif BASELINE_CSV_PATH.exists():
        return BASELINE_CSV_PATH
    else:
        raise FileNotFoundError(
            f"Baseline dataset not found. Expected at {BASELINE_PARQUET_PATH} or {BASELINE_CSV_PATH}"
        )


__all__ = [
    "BASELINE_CSV_PATH",
    "BASELINE_PARQUET_PATH",
    "DATA_DIR",
    "REFERENCE_DIR",
    "get_baseline_path",
]
