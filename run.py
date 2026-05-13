"""
run.py
CLI driver for the reinsurance loss allocation tool.
This file handles all I/O — reading input CSVs and writing output CSV.
No business logic lives here; all computation is delegated to allocate.py.

Usage:
  python run.py --claims claims.csv --layers layers.csv --output cessions.csv
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from allocate import allocate_claims


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list to parse. Defaults to sys.argv[1:] if None.

    Returns:
        Namespace with attributes: claims, layers, output.
    """
    parser = argparse.ArgumentParser(
        description="Allocate reinsurance losses to layers and write a cession report."
    )
    parser.add_argument("--claims", required=True, help="Path to claims CSV")
    parser.add_argument("--layers", required=True, help="Path to layers CSV")
    parser.add_argument("--output", required=True, help="Path for output CSV")
    return parser.parse_args(argv)


def load_claims(path: str) -> pd.DataFrame:
    """Read claims CSV and return a DataFrame with correct column types.

    Args:
        path: File path to claims CSV.

    Returns:
        DataFrame with claim_id as str, date parsed as datetime.date,
        loss and alae as float.

    Raises:
        SystemExit: If the file cannot be read or parsed.
    """
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        df["claim_id"] = df["claim_id"].astype(str)
        df["date"] = df["date"].dt.date
        for col in ("loss", "alae"):
            df[col] = df[col].astype(float)
        return df
    except FileNotFoundError:
        print(f"Error: claims file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error reading claims file {path!r}: {exc}", file=sys.stderr)
        sys.exit(1)


def load_layers(path: str) -> pd.DataFrame:
    """Read layers CSV and return a DataFrame with correct column types.

    Args:
        path: File path to layers CSV.

    Returns:
        DataFrame with layer_name and alae_treatment as str,
        attachment, limit, and aal as float.

    Raises:
        SystemExit: If the file cannot be read or parsed.
    """
    try:
        df = pd.read_csv(path)
        df["layer_name"] = df["layer_name"].astype(str)
        df["alae_treatment"] = df["alae_treatment"].astype(str)
        for col in ("attachment", "limit", "aal"):
            df[col] = df[col].astype(float)
        return df
    except FileNotFoundError:
        print(f"Error: layers file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error reading layers file {path!r}: {exc}", file=sys.stderr)
        sys.exit(1)


def write_output(result: pd.DataFrame, path: str) -> None:
    """Write the cession report DataFrame to a CSV file.

    Args:
        result: DataFrame with columns year, layer_name, ceded_amount.
        path:   Output file path.

    Raises:
        SystemExit: If the file cannot be written.
    """
    try:
        result.to_csv(path, index=False)
    except IOError as exc:
        print(f"Error writing output to {path!r}: {exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """Main entry point — parse args, load data, run allocation, write output.

    Args:
        argv: Argument list. Defaults to sys.argv[1:] if None.
    """
    args = parse_args(argv)
    claims_df = load_claims(args.claims)
    layers_df = load_layers(args.layers)
    try:
        result = allocate_claims(claims_df, layers_df)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    write_output(result, args.output)
    print(f"Wrote {len(result)} rows to {args.output}")


if __name__ == "__main__":
    main()