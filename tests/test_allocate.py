"""
tests/test_allocate.py
Test suite for allocate.py.
All sanity check examples from the spec are encoded as named tests.
Fixtures provide reusable DataFrames for common test scenarios.

Run: pytest tests/
Run with coverage: pytest --cov=allocate tests/
"""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from allocate import (
    _apply_aal,
    _cede_claim,
    _cede_excluded,
    _cede_part_of,
    _cede_pro_rata,
    _clamp,
    allocate_claims,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_claim_2023() -> pd.DataFrame:
    """Single claim used in spec sanity check example 1.

    loss=4_000_000, alae=500_000, date=2023-06-01.
    """
    return pd.DataFrame([{
        "claim_id": "C0",
        "date": datetime.date(2023, 6, 1),
        "loss": 4_000_000.0,
        "alae": 500_000.0,
    }])


@pytest.fixture
def three_layer_stack() -> pd.DataFrame:
    """Three-layer stack used in spec sanity check example 1.

    L1: 1M xs 1M, pro_rata
    L2: 3M xs 2M, part_of
    L3: 5M xs 5M, excluded
    """
    return pd.DataFrame([
        {"layer_name": "L1", "attachment": 1_000_000.0, "limit": 1_000_000.0,
         "aal": 2_000_000.0, "alae_treatment": "pro_rata"},
        {"layer_name": "L2", "attachment": 2_000_000.0, "limit": 3_000_000.0,
         "aal": 5_000_000.0, "alae_treatment": "part_of"},
        {"layer_name": "L3", "attachment": 5_000_000.0, "limit": 5_000_000.0,
         "aal": 5_000_000.0, "alae_treatment": "excluded"},
    ])


@pytest.fixture
def aal_exhaustion_claims() -> pd.DataFrame:
    """Three claims used in spec sanity check example 2.

    C1 and C2 in 2023, C3 in 2024. Each has loss=2_000_000, alae=0.
    """
    return pd.DataFrame([
        {"claim_id": "C1", "date": datetime.date(2023, 1, 1),
         "loss": 2_000_000.0, "alae": 0.0},
        {"claim_id": "C2", "date": datetime.date(2023, 2, 1),
         "loss": 2_000_000.0, "alae": 0.0},
        {"claim_id": "C3", "date": datetime.date(2024, 1, 1),
         "loss": 2_000_000.0, "alae": 0.0},
    ])


@pytest.fixture
def aal_exhaustion_layer() -> pd.DataFrame:
    """Single layer used in spec sanity check example 2.

    L1: 1M xs 0, aal=1_500_000, excluded.
    """
    return pd.DataFrame([{
        "layer_name": "L1",
        "attachment": 0.0,
        "limit": 1_000_000.0,
        "aal": 1_500_000.0,
        "alae_treatment": "excluded",
    }])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ceded(result: pd.DataFrame, year: int, layer_name: str) -> float:
    row = result[(result["year"] == year) & (result["layer_name"] == layer_name)]
    return row["ceded_amount"].iloc[0]


# ---------------------------------------------------------------------------
# Unit tests — _clamp
# ---------------------------------------------------------------------------

def test_clamp_below_lo() -> None:
    """Value below lower bound is clamped to lo."""
    assert _clamp(-1.0, 0.0, 10.0) == 0.0


def test_clamp_above_hi() -> None:
    """Value above upper bound is clamped to hi."""
    assert _clamp(15.0, 0.0, 10.0) == 10.0


def test_clamp_within_range() -> None:
    """Value within range is returned unchanged."""
    assert _clamp(5.0, 0.0, 10.0) == 5.0


# ---------------------------------------------------------------------------
# Unit tests — per-claim ALAE treatments
# ---------------------------------------------------------------------------

def test_excluded_alae_treatment() -> None:
    """Excluded treatment ignores ALAE; layer attaches to loss only.

    loss=4M, alae=500K, attachment=1M, limit=1M.
    Expected: clamp(4M - 1M, 0, 1M) = 1_000_000.
    """
    assert _cede_excluded(4_000_000, 1_000_000, 1_000_000) == pytest.approx(1_000_000.0)


def test_excluded_claim_below_attachment() -> None:
    """Claim that does not pierce attachment returns zero under excluded."""
    assert _cede_excluded(500_000, 1_000_000, 1_000_000) == pytest.approx(0.0)


def test_pro_rata_alae_treatment() -> None:
    """Pro-rata treatment: ALAE scales with loss recovery ratio.

    loss=4M, alae=500K, attachment=1M, limit=1M.
    loss_in_layer = 1M, ratio = 1M/4M = 0.25, alae_in_layer = 125K.
    Expected: 1_125_000.
    """
    assert _cede_pro_rata(4_000_000, 500_000, 1_000_000, 1_000_000) == pytest.approx(1_125_000.0)


def test_zero_loss_pro_rata() -> None:
    """When loss is zero under pro_rata, ALAE recovery is also zero."""
    assert _cede_pro_rata(0.0, 500_000, 0.0, 1_000_000) == pytest.approx(0.0)


def test_part_of_alae_treatment() -> None:
    """Part-of treatment: ALAE added to loss before attaching.

    loss=4M, alae=500K, attachment=2M, limit=3M.
    ground_up = 4.5M, ceded = clamp(4.5M - 2M, 0, 3M) = 2_500_000.
    """
    assert _cede_part_of(4_000_000, 500_000, 2_000_000, 3_000_000) == pytest.approx(2_500_000.0)


def test_claim_below_attachment() -> None:
    """Claim that does not pierce attachment returns zero for all treatments."""
    assert _cede_claim(500_000, 0.0, 1_000_000, 1_000_000, "excluded") == pytest.approx(0.0)
    assert _cede_claim(500_000, 0.0, 1_000_000, 1_000_000, "pro_rata") == pytest.approx(0.0)
    assert _cede_claim(500_000, 0.0, 1_000_000, 1_000_000, "part_of") == pytest.approx(0.0)


def test_cede_claim_dispatches_correctly() -> None:
    """_cede_claim routes to the correct treatment function."""
    assert _cede_claim(4_000_000, 500_000, 1_000_000, 1_000_000, "excluded") == pytest.approx(
        _cede_excluded(4_000_000, 1_000_000, 1_000_000)
    )
    assert _cede_claim(4_000_000, 500_000, 1_000_000, 1_000_000, "pro_rata") == pytest.approx(
        _cede_pro_rata(4_000_000, 500_000, 1_000_000, 1_000_000)
    )
    assert _cede_claim(4_000_000, 500_000, 2_000_000, 3_000_000, "part_of") == pytest.approx(
        _cede_part_of(4_000_000, 500_000, 2_000_000, 3_000_000)
    )


def test_cede_claim_unknown_treatment_raises() -> None:
    """_cede_claim raises ValueError for an unknown alae_treatment."""
    with pytest.raises(ValueError):
        _cede_claim(1_000_000, 0, 0, 1_000_000, "unknown_treatment")


# ---------------------------------------------------------------------------
# Unit tests — _apply_aal
# ---------------------------------------------------------------------------

def test_apply_aal_no_exhaustion() -> None:
    """When total pre-AAL cessions are below AAL, all are paid in full."""
    assert _apply_aal([400_000, 300_000], 1_500_000) == pytest.approx([400_000, 300_000])


def test_aal_exhaustion_within_year() -> None:
    """AAL caps total payout; claims after exhaustion cede zero.

    Two claims of 1M each, AAL=1_500_000.
    First pays 1M, second pays 500K (remaining), third would pay 0.
    """
    assert _apply_aal([1_000_000, 1_000_000, 1_000_000], 1_500_000) == pytest.approx(
        [1_000_000, 500_000, 0]
    )


def test_apply_aal_exactly_exhausted() -> None:
    """When AAL is exactly met, subsequent claims cede zero."""
    assert _apply_aal([1_000_000, 500_000, 200_000], 1_500_000) == pytest.approx(
        [1_000_000, 500_000, 0]
    )


def test_apply_aal_empty_list() -> None:
    """Empty input returns empty output."""
    assert _apply_aal([], 1_000_000) == []


# ---------------------------------------------------------------------------
# Integration tests — allocate_claims
# ---------------------------------------------------------------------------

def test_sanity_check_example_1(
    single_claim_2023: pd.DataFrame,
    three_layer_stack: pd.DataFrame,
) -> None:
    """Reproduce spec sanity check example 1 exactly.

    Single claim: loss=4M, alae=500K, year=2023.
    Expected:
        2023 / L1 = 1_125_000  (pro_rata)
        2023 / L2 = 2_500_000  (part_of)
        2023 / L3 = 0.0        (excluded, claim doesn't pierce)
    """
    result = allocate_claims(single_claim_2023, three_layer_stack)
    assert len(result) == 3
    assert _ceded(result, 2023, "L1") == pytest.approx(1_125_000.0)
    assert _ceded(result, 2023, "L2") == pytest.approx(2_500_000.0)
    assert _ceded(result, 2023, "L3") == pytest.approx(0.0)


def test_sanity_check_example_2(
    aal_exhaustion_claims: pd.DataFrame,
    aal_exhaustion_layer: pd.DataFrame,
) -> None:
    """Reproduce spec sanity check example 2 exactly.

    C1 + C2 in 2023, C3 in 2024. AAL = 1_500_000.
    Expected:
        2023 / L1 = 1_500_000  (AAL exhausted)
        2024 / L1 = 1_000_000  (AAL resets)
    """
    result = allocate_claims(aal_exhaustion_claims, aal_exhaustion_layer)
    assert _ceded(result, 2023, "L1") == pytest.approx(1_500_000.0)
    assert _ceded(result, 2024, "L1") == pytest.approx(1_000_000.0)


def test_aal_resets_across_years(
    aal_exhaustion_claims: pd.DataFrame,
    aal_exhaustion_layer: pd.DataFrame,
) -> None:
    """AAL exhaustion in one year does not carry into the next year."""
    result = allocate_claims(aal_exhaustion_claims, aal_exhaustion_layer)
    assert _ceded(result, 2024, "L1") == pytest.approx(1_000_000.0)


def test_same_date_sorted_by_claim_id() -> None:
    """Claims with the same date are processed in claim_id ascending order.

    C1 and C2 share 2023-01-01. AAL=1_200_000, limit=1_000_000.
    Both pre-AAL cessions are 1M. C1 (alphabetically first) consumes 1M;
    C2 gets the remaining 200K. Total = 1_200_000 (== AAL).
    """
    claims = pd.DataFrame([
        {"claim_id": "C1", "date": datetime.date(2023, 1, 1), "loss": 2_000_000.0, "alae": 0.0},
        {"claim_id": "C2", "date": datetime.date(2023, 1, 1), "loss": 2_000_000.0, "alae": 0.0},
    ])
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
        "aal": 1_200_000.0, "alae_treatment": "excluded",
    }])
    result = allocate_claims(claims, layers)
    assert _ceded(result, 2023, "L1") == pytest.approx(1_200_000.0)


def test_zero_rows_included_in_output() -> None:
    """Output includes (year, layer_name) rows even when no claims hit that layer.

    Claim loss=500K does not pierce L2 (attachment=1M), so 2023/L2 must
    appear in output with ceded_amount=0.
    """
    claims = pd.DataFrame([{
        "claim_id": "C1", "date": datetime.date(2023, 1, 1),
        "loss": 500_000.0, "alae": 0.0,
    }])
    layers = pd.DataFrame([
        {"layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
         "aal": 2_000_000.0, "alae_treatment": "excluded"},
        {"layer_name": "L2", "attachment": 1_000_000.0, "limit": 1_000_000.0,
         "aal": 2_000_000.0, "alae_treatment": "excluded"},
    ])
    result = allocate_claims(claims, layers)
    assert len(result) == 2
    assert _ceded(result, 2023, "L1") == pytest.approx(500_000.0)
    assert _ceded(result, 2023, "L2") == pytest.approx(0.0)


def test_output_columns_and_types() -> None:
    """Output DataFrame has exactly the required columns with correct types."""
    claims = pd.DataFrame([{
        "claim_id": "C1", "date": datetime.date(2023, 1, 1),
        "loss": 1_000_000.0, "alae": 0.0,
    }])
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
        "aal": 2_000_000.0, "alae_treatment": "excluded",
    }])
    result = allocate_claims(claims, layers)
    assert result.columns.tolist() == ["year", "layer_name", "ceded_amount"]
    assert result["year"].dtype == int
    assert result["ceded_amount"].dtype == float


def test_multiple_years_multiple_layers() -> None:
    """Allocation works correctly across multiple years and multiple layers.

    C1 in 2023 (loss=1M), C2 in 2024 (loss=2M). Two excluded layers.
    Expected 4 rows total; each (year, layer) amount is independently correct.
    """
    claims = pd.DataFrame([
        {"claim_id": "C1", "date": datetime.date(2023, 1, 1), "loss": 1_000_000.0, "alae": 0.0},
        {"claim_id": "C2", "date": datetime.date(2024, 1, 1), "loss": 2_000_000.0, "alae": 0.0},
    ])
    layers = pd.DataFrame([
        {"layer_name": "L1", "attachment": 0.0, "limit": 500_000.0,
         "aal": 1_000_000.0, "alae_treatment": "excluded"},
        {"layer_name": "L2", "attachment": 1_000_000.0, "limit": 1_000_000.0,
         "aal": 2_000_000.0, "alae_treatment": "excluded"},
    ])
    result = allocate_claims(claims, layers)
    assert len(result) == 4
    assert _ceded(result, 2023, "L1") == pytest.approx(500_000.0)
    assert _ceded(result, 2023, "L2") == pytest.approx(0.0)
    assert _ceded(result, 2024, "L1") == pytest.approx(500_000.0)
    assert _ceded(result, 2024, "L2") == pytest.approx(1_000_000.0)


# ---------------------------------------------------------------------------
# Validation tests — allocate_claims raises ValueError
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_claims() -> pd.DataFrame:
    return pd.DataFrame([{
        "claim_id": "C1", "date": datetime.date(2023, 1, 1),
        "loss": 1_000_000.0, "alae": 0.0,
    }])


@pytest.fixture
def minimal_layer() -> pd.DataFrame:
    return pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
        "aal": 2_000_000.0, "alae_treatment": "excluded",
    }])


def test_invalid_alae_treatment_raises(minimal_claims: pd.DataFrame) -> None:
    """ValueError raised when alae_treatment is not a valid value."""
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
        "aal": 2_000_000.0, "alae_treatment": "invalid",
    }])
    with pytest.raises(ValueError):
        allocate_claims(minimal_claims, layers)


def test_negative_loss_raises(minimal_layer: pd.DataFrame) -> None:
    """ValueError raised when any loss value is negative."""
    claims = pd.DataFrame([{
        "claim_id": "C1", "date": datetime.date(2023, 1, 1),
        "loss": -1.0, "alae": 0.0,
    }])
    with pytest.raises(ValueError):
        allocate_claims(claims, minimal_layer)


def test_negative_alae_raises(minimal_layer: pd.DataFrame) -> None:
    """ValueError raised when any alae value is negative."""
    claims = pd.DataFrame([{
        "claim_id": "C1", "date": datetime.date(2023, 1, 1),
        "loss": 0.0, "alae": -1.0,
    }])
    with pytest.raises(ValueError):
        allocate_claims(claims, minimal_layer)


def test_negative_attachment_raises(minimal_claims: pd.DataFrame) -> None:
    """ValueError raised when any attachment value is negative."""
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": -1.0, "limit": 1_000_000.0,
        "aal": 2_000_000.0, "alae_treatment": "excluded",
    }])
    with pytest.raises(ValueError):
        allocate_claims(minimal_claims, layers)


def test_nonpositive_limit_raises(minimal_claims: pd.DataFrame) -> None:
    """ValueError raised when limit is zero or negative."""
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 0.0,
        "aal": 2_000_000.0, "alae_treatment": "excluded",
    }])
    with pytest.raises(ValueError):
        allocate_claims(minimal_claims, layers)


def test_nonpositive_aal_raises(minimal_claims: pd.DataFrame) -> None:
    """ValueError raised when aal is zero or negative."""
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
        "aal": 0.0, "alae_treatment": "excluded",
    }])
    with pytest.raises(ValueError):
        allocate_claims(minimal_claims, layers)


def test_duplicate_claim_id_raises(minimal_layer: pd.DataFrame) -> None:
    """ValueError raised when claims_df contains duplicate claim_id values."""
    claims = pd.DataFrame([
        {"claim_id": "C1", "date": datetime.date(2023, 1, 1), "loss": 0.0, "alae": 0.0},
        {"claim_id": "C1", "date": datetime.date(2023, 2, 1), "loss": 0.0, "alae": 0.0},
    ])
    with pytest.raises(ValueError):
        allocate_claims(claims, minimal_layer)


def test_duplicate_layer_name_raises(minimal_claims: pd.DataFrame) -> None:
    """ValueError raised when layers_df contains duplicate layer_name values."""
    layers = pd.DataFrame([
        {"layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
         "aal": 2_000_000.0, "alae_treatment": "excluded"},
        {"layer_name": "L1", "attachment": 0.0, "limit": 2_000_000.0,
         "aal": 2_000_000.0, "alae_treatment": "excluded"},
    ])
    with pytest.raises(ValueError):
        allocate_claims(minimal_claims, layers)


def test_missing_claims_column_raises(minimal_layer: pd.DataFrame) -> None:
    """ValueError raised when a required column is missing from claims_df."""
    claims = pd.DataFrame([{
        "claim_id": "C1", "date": datetime.date(2023, 1, 1), "alae": 0.0,
    }])
    with pytest.raises(ValueError):
        allocate_claims(claims, minimal_layer)


def test_missing_layers_column_raises(minimal_claims: pd.DataFrame) -> None:
    """ValueError raised when a required column is missing from layers_df."""
    layers = pd.DataFrame([{
        "layer_name": "L1", "attachment": 0.0, "limit": 1_000_000.0,
        "alae_treatment": "excluded",
    }])
    with pytest.raises(ValueError):
        allocate_claims(minimal_claims, layers)
