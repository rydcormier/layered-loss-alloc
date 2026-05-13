# CLAUDE.md — reinsurance-loss-alloc

## What this project is

A Python implementation of layered reinsurance loss allocation. Given a portfolio of insurance claims and a set of reinsurance layers, compute how much each layer pays in each accident year, accounting for three ALAE treatment methods and annual aggregate limits (AAL).

This is a Lockton RE coding assignment. The spec is the authoritative source. When in doubt, implement what the spec says — do not add features, optimizations, or reinsurance logic beyond the spec.

---

## Key mathematical invariants

These are the rules the implementation must satisfy. Verify any change you make against all of them.

**Per-claim layer math (Part 2)**

Three ALAE treatments — implement exactly as specified, no variations:

- `excluded`: `ceded_pre_aal = clamp(loss - attachment, 0, limit)`
- `pro_rata`: loss in layer first, then ALAE scales proportionally. If `loss == 0`, ALAE recovery is 0.
- `part_of`: `ground_up = loss + alae`, then `ceded_pre_aal = clamp(ground_up - attachment, 0, limit)`

`clamp(x, lo, hi)` means `max(lo, min(x, hi))`.

**AAL bookkeeping (Part 3)**

- AAL applies per `(year, layer_name)` independently — layers do not interact
- Claims within a `(year, layer_name)` are processed in chronological order by `date`, then by `claim_id` ascending for ties
- `paid_so_far` starts at 0 for each `(year, layer_name)` and accumulates
- `ceded = min(ceded_pre_aal, max(remaining_aal, 0))`
- Once AAL is exhausted, all subsequent claims in that year cede zero to that layer
- AAL resets at the start of each new accident year

**Output requirements**

- Long format: one row per `(year, layer_name)` combination
- Include zero rows where no claims hit a layer in a given year
- `year` derived from `date.year` (accident year, not calendar year of payment)
- `ceded_amount` is the sum of individual claim cessions after AAL

---

## Code organization

The spec explicitly evaluates this. Keep these four concerns in separate functions:

1. **Per-claim layer math** — pure calculation, no side effects, no state. Takes `loss`, `alae`, `attachment`, `limit`, `alae_treatment` and returns `ceded_pre_aal`. One function per treatment or one dispatch function — either is fine.

2. **AAL bookkeeping** — stateful loop over sorted claims within a `(year, layer_name)`. Takes pre-AAL cessions and returns post-AAL cessions.

3. **Aggregation** — sums post-AAL cessions by `(year, layer_name)`, ensures zero rows are present for all combinations.

4. **I/O** — only in `run.py`. `allocate.py` should not read or write files.

---

## Sanity checks

Two examples from the spec. Any correct implementation must reproduce these exactly.

**Example 1 — per-claim math, no AAL binding**

Single claim: `loss=4_000_000`, `alae=500_000`, year 2023

| layer | attachment | limit | aal | alae_treatment | expected_ceded |
|-------|-----------|-------|-----|----------------|---------------|
| L1 | 1_000_000 | 1_000_000 | 2_000_000 | pro_rata | 1_125_000.00 |
| L2 | 2_000_000 | 3_000_000 | 5_000_000 | part_of | 2_500_000.00 |
| L3 | 5_000_000 | 5_000_000 | 5_000_000 | excluded | 0.00 |

Verify L1 manually: `loss_in_layer = clamp(4M - 1M, 0, 1M) = 1M`. `alae_in_layer = 500K * (1M / 4M) = 125K`. Total = `1_125_000`. ✓

Verify L2 manually: `ground_up = 4M + 500K = 4.5M`. `ceded = clamp(4.5M - 2M, 0, 3M) = clamp(2.5M, 0, 3M) = 2_500_000`. ✓

Verify L3 manually: `ceded = clamp(4M - 5M, 0, 5M) = clamp(-1M, 0, 5M) = 0`. ✓

**Example 2 — AAL exhaustion and annual reset**

Three claims, one layer (`attachment=0`, `limit=1_000_000`, `aal=1_500_000`, `excluded`):

| claim | date | loss | expected ceded |
|-------|------|------|---------------|
| C1 | 2023-01-01 | 2_000_000 | 1_000_000 (hits limit) |
| C2 | 2023-02-01 | 2_000_000 | 500_000 (AAL has 500K remaining) |
| C3 | 2024-01-01 | 2_000_000 | 1_000_000 (AAL resets) |

Expected output: 2023/L1 = 1_500_000, 2024/L1 = 1_000_000. ✓

---

## Validation rules

`allocate_claims` must raise `ValueError` for:

- Missing required columns in either DataFrame
- Unknown `alae_treatment` value (not one of `excluded`, `pro_rata`, `part_of`)
- Negative `loss` or `alae`
- Non-positive `limit` or `aal`
- Negative `attachment`
- Duplicate `layer_name` values in `layers_df`
- Duplicate `claim_id` values in `claims_df`

---

## Test conventions

Tests live in `tests/test_allocate.py`. Use pytest fixtures for reusable DataFrames.

Name test functions descriptively:
- `test_excluded_alae_treatment`
- `test_pro_rata_alae_treatment`
- `test_part_of_alae_treatment`
- `test_aal_exhaustion_within_year`
- `test_aal_resets_across_years`
- `test_sanity_check_example_1`
- `test_sanity_check_example_2`
- `test_zero_loss_pro_rata`
- `test_claim_below_attachment`
- `test_same_date_sorted_by_claim_id`
- `test_zero_rows_included_in_output`
- `test_invalid_alae_treatment_raises`
- `test_negative_loss_raises`

Run tests: `pytest tests/`
Run with coverage: `pytest --cov=allocate tests/`

---

## What is out of scope

Do not implement any of the following — they are explicitly excluded by the spec:

- Reinstatements
- FX / currency handling
- Participation / co-insurance percentages
- Cession on a cession (retrocession)
- Performance optimization / vectorization
- Plotting or reporting beyond CSV output

If asked to add any of these, decline and reference the spec.

---

## File layout

```
reinsurance-loss-alloc/
├── allocate.py        # allocate_claims() and all helper functions
├── run.py             # CLI driver — I/O only, no business logic
├── claims.csv         # sample input
├── layers.csv         # sample input
├── cessions.csv       # expected output from sample inputs
├── requirements.txt   # pandas>=2.0.0, pytest>=7.0.0
├── README.md          # setup, run, test, tradeoffs, AI usage note
├── CLAUDE.md          # this file
└── tests/
    ├── __init__.py
    └── test_allocate.py
```

---

## Run commands

```bash
# Install
pip install -r requirements.txt

# Run against sample data
python run.py --claims claims.csv --layers layers.csv --output cessions.csv

# Run tests
pytest tests/

# Run with coverage
pytest --cov=allocate tests/
```

