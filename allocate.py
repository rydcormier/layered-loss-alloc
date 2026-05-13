"""
allocate.py
Core reinsurance loss allocation logic.
Four concerns kept separate per spec:
  1. Per-claim layer math  (clamp, cede_excluded, cede_pro_rata, cede_part_of, cede_claim)
  2. AAL bookkeeping       (apply_aal)
  3. Aggregation           (aggregate_cessions)
  4. Public entry point    (allocate_claims)
I/O lives exclusively in run.py — this module does not read or write files.
# """

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ALAE_TREATMENTS = frozenset({"excluded", "pro_rata", "part_of"})

CLAIMS_REQUIRED_COLUMNS = {"claim_id", "date", "loss", "alae"}
LAYERS_REQUIRED_COLUMNS = {"layer_name", "attachment", "limit", "aal", "alae_treatment"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_inputs(claims_df: pd.DataFrame, layers_df: pd.DataFrame) -> None:
    """Validate both input DataFrames and raise ValueError on any problem.

    Checks performed:
    - Required columns present in both DataFrames
    - No duplicate claim_id values
    - No duplicate layer_name values
    - loss and alae are non-negative
    - attachment is non-negative
    - limit and aal are positive (> 0)
    - alae_treatment is one of the three valid values

    Args:
        claims_df: Claims DataFrame as described in the spec.
        layers_df: Layers DataFrame as described in the spec.

    Raises:
        ValueError: If any validation check fails. Message describes the failure.
    """
    missing_claims = CLAIMS_REQUIRED_COLUMNS - set(claims_df.columns)
    if missing_claims:
        raise ValueError(f"claims_df missing columns: {missing_claims}")

    missing_layers = LAYERS_REQUIRED_COLUMNS - set(layers_df.columns)
    if missing_layers:
        raise ValueError(f"layers_df missing columns: {missing_layers}")

    dupes = claims_df["claim_id"][claims_df["claim_id"].duplicated()]
    if not dupes.empty:
        raise ValueError(f"Duplicate claim_id values: {dupes.tolist()}")

    dupes = layers_df["layer_name"][layers_df["layer_name"].duplicated()]
    if not dupes.empty:
        raise ValueError(f"Duplicate layer_name values: {dupes.tolist()}")

    if (claims_df["loss"] < 0).any():
        raise ValueError("loss must be >= 0")

    if (claims_df["alae"] < 0).any():
        raise ValueError("alae must be >= 0")

    if (layers_df["attachment"] < 0).any():
        raise ValueError("attachment must be >= 0")

    if (layers_df["limit"] <= 0).any():
        raise ValueError("limit must be > 0")

    if (layers_df["aal"] <= 0).any():
        raise ValueError("aal must be > 0")

    invalid_treatments = set(layers_df["alae_treatment"]) - VALID_ALAE_TREATMENTS
    if invalid_treatments:
        raise ValueError(f"Unknown alae_treatment values: {invalid_treatments}")


# ---------------------------------------------------------------------------
# Part 1 — Per-claim layer math helpers
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float, hi: float) -> float:
    """Return x clamped to [lo, hi].

    Args:
        x:  Value to clamp.
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).

    Returns:
        Clamped value as float.
    """
    return max(lo, min(x, hi))


def _cede_excluded(loss: float, attachment: float, limit: float) -> float:
    """Compute per-claim layer recovery under the 'excluded' ALAE treatment.

    ALAE is not covered. The layer attaches to loss alone.

        ceded_pre_aal = clamp(loss - attachment, 0, limit)

    Args:
        loss:       Ground-up loss amount for this claim (>= 0).
        attachment: Layer attachment point (>= 0).
        limit:      Per-occurrence limit (> 0).

    Returns:
        ceded_pre_aal as float.
    """
    # TODO: implement excluded treatment
    raise NotImplementedError


def _cede_pro_rata(
    loss: float,
    alae: float,
    attachment: float,
    limit: float,
) -> float:
    """Compute per-claim layer recovery under the 'pro_rata' ALAE treatment.

    The layer attaches to loss alone; ALAE is recovered in the same ratio as
    the loss recovery.

        loss_in_layer = clamp(loss - attachment, 0, limit)
        alae_in_layer = alae * (loss_in_layer / loss)   if loss > 0 else 0
        ceded_pre_aal = loss_in_layer + alae_in_layer

    Args:
        loss:       Ground-up loss amount for this claim (>= 0).
        alae:       ALAE for this claim (>= 0).
        attachment: Layer attachment point (>= 0).
        limit:      Per-occurrence limit (> 0).

    Returns:
        ceded_pre_aal as float.
    """
    # TODO: implement pro_rata treatment
    # NOTE: guard against division by zero — if loss == 0, alae recovery is 0
    raise NotImplementedError


def _cede_part_of(
    loss: float,
    alae: float,
    attachment: float,
    limit: float,
) -> float:
    """Compute per-claim layer recovery under the 'part_of' ALAE treatment.

    ALAE is rolled into the ground-up amount the layer attaches to.

        ground_up     = loss + alae
        ceded_pre_aal = clamp(ground_up - attachment, 0, limit)

    Args:
        loss:       Ground-up loss amount for this claim (>= 0).
        alae:       ALAE for this claim (>= 0).
        attachment: Layer attachment point (>= 0).
        limit:      Per-occurrence limit (> 0).

    Returns:
        ceded_pre_aal as float.
    """
    # TODO: implement part_of treatment
    raise NotImplementedError


def _cede_claim(
    loss: float,
    alae: float,
    attachment: float,
    limit: float,
    alae_treatment: str,
) -> float:
    """Dispatch to the correct ALAE treatment and return ceded_pre_aal.

    This is the single entry point for per-claim layer math.
    All three treatments are pure functions — no state, no side effects.

    Args:
        loss:           Ground-up loss amount for this claim (>= 0).
        alae:           ALAE for this claim (>= 0).
        attachment:     Layer attachment point (>= 0).
        limit:          Per-occurrence limit (> 0).
        alae_treatment: One of 'excluded', 'pro_rata', 'part_of'.

    Returns:
        ceded_pre_aal as float.

    Raises:
        ValueError: If alae_treatment is not a recognised value.
    """
    # TODO: dispatch to _cede_excluded, _cede_pro_rata, or _cede_part_of
    # TODO: raise ValueError for unknown treatment (should already be caught by
    #       validation, but defensive check here is fine)
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Part 2 — AAL bookkeeping
# ---------------------------------------------------------------------------

def _apply_aal(
    pre_aal_cessions: list[float],
    aal: float,
) -> list[float]:
    """Apply the annual aggregate limit to a sequence of pre-AAL cessions.

    Claims must already be sorted chronologically (date asc, claim_id asc)
    before calling this function. This function only applies the cap.

    Algorithm (from spec):
        paid_so_far = 0
        for each ceded_pre_aal:
            remaining_aal = aal - paid_so_far
            ceded = min(ceded_pre_aal, max(remaining_aal, 0))
            paid_so_far += ceded

    Args:
        pre_aal_cessions: Ordered list of per-claim pre-AAL cession amounts.
        aal:              Annual aggregate limit for this (year, layer) pair.

    Returns:
        List of post-AAL cession amounts, same length as pre_aal_cessions.
    """
    # TODO: implement AAL accumulation loop
    # NOTE: once paid_so_far >= aal, all subsequent cessions are 0
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Part 3 — Aggregation
# ---------------------------------------------------------------------------

def _aggregate_cessions(
    records: list[dict],
    years: list[int],
    layer_names: list[str],
) -> pd.DataFrame:
    """Sum post-AAL cessions by (year, layer_name) and ensure zero rows exist.

    The spec requires one row per (year, layer_name) combination in the output,
    including combinations where no claims hit the layer that year.

    Args:
        records:     List of dicts with keys 'year', 'layer_name', 'ceded'.
                     One entry per (claim, layer) pair after AAL is applied.
        years:       All accident years present in the claims data.
        layer_names: All layer names present in the layers data.

    Returns:
        DataFrame with columns ['year', 'layer_name', 'ceded_amount'],
        one row per (year, layer_name) combination, ceded_amount >= 0.
    """
    # TODO: build DataFrame from records
    # TODO: group by (year, layer_name) and sum ceded
    # TODO: build complete index from itertools.product(years, layer_names)
    # TODO: reindex to ensure zero rows are present for missing combinations
    # TODO: reset index, rename column, return
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def allocate_claims(
    claims_df: pd.DataFrame,
    layers_df: pd.DataFrame,
) -> pd.DataFrame:
    """Allocate claims to reinsurance layers and return a year-by-layer cession report.

    For each accident year and each layer, computes the total amount ceded
    after applying per-occurrence ALAE treatment and the annual aggregate limit.

    Args:
        claims_df: DataFrame with columns:
            - claim_id (str):  Unique claim identifier.
            - date (date):     Loss date; accident year = date.year.
            - loss (float):    Ground-up loss amount, >= 0.
            - alae (float):    Allocated loss adjustment expense, >= 0.

        layers_df: DataFrame with columns:
            - layer_name (str):      Layer identifier, e.g. 'L1'.
            - attachment (float):    Attachment point, >= 0.
            - limit (float):         Per-occurrence limit, > 0.
            - aal (float):           Annual aggregate limit, > 0.
            - alae_treatment (str):  One of 'excluded', 'pro_rata', 'part_of'.

    Returns:
        Long-format DataFrame with columns:
            - year (int):            Accident year.
            - layer_name (str):      Layer identifier.
            - ceded_amount (float):  Total ceded to this layer in this year.
        One row per (year, layer_name) combination.
        Zero rows are included where no claims hit a layer in a given year.

    Raises:
        ValueError: If inputs fail validation (see _validate_inputs).

    Example:
        >>> result = allocate_claims(claims_df, layers_df)
        >>> result.columns.tolist()
        ['year', 'layer_name', 'ceded_amount']
    """
    # TODO: call _validate_inputs(claims_df, layers_df)

    # TODO: derive accident year from date column

    # TODO: get sorted list of unique years and layer names (for zero-row completeness)

    # TODO: for each (year, layer) combination:
    #   a. filter claims to this year
    #   b. sort by date asc, then claim_id asc
    #   c. compute ceded_pre_aal for each claim using _cede_claim
    #   d. apply AAL using _apply_aal
    #   e. collect (year, layer_name, ceded) records

    # TODO: call _aggregate_cessions and return result

    raise NotImplementedError