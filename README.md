# Layered Loss Allocation

Reinsurance loss allocation across layers with three ALAE treatments and annual aggregate limits (AAL).

---

## Setup

Python 3.11+ required.

```bash
pip install -r requirements.txt
```

---

## Run

```bash
python run.py --claims claims.csv --layers layers.csv --output cessions.csv
```

Reads `claims.csv` and `layers.csv`, runs the allocation, and writes `cessions.csv` — one row per `(year, layer_name)` combination.

---

## Test

```bash
pytest tests/
```

```bash
pytest --cov=allocate tests/
```

---

## Code organisation

Four concerns are kept strictly separate per the spec:

| Module | Function(s) | Responsibility |
|--------|-------------|----------------|
| `allocate.py` | `_cede_excluded`, `_cede_pro_rata`, `_cede_part_of`, `_cede_claim` | Pure per-claim layer math — no state, no I/O |
| `allocate.py` | `_apply_aal` | Stateful AAL accumulation loop over a sorted claim sequence |
| `allocate.py` | `_aggregate_cessions` | Group/sum post-AAL cessions; fill zero rows for all `(year, layer)` pairs |
| `allocate.py` | `allocate_claims` | Public entry point — validates inputs, drives the computation |
| `run.py` | `load_claims`, `load_layers`, `write_output`, `main` | All file I/O; no business logic |

---

## Tradeoffs

**Loops over vectorisation.** AAL bookkeeping is sequential — each claim depends on the running total before it — so a plain Python loop is the natural fit. Vectorised alternatives exist but would obscure the logic without a meaningful correctness or performance benefit at realistic portfolio sizes.

**Zero-row completeness.** The output reindexes against the full year × layer grid so every `(year, layer_name)` pair appears, even when nothing ceded. Filtering to non-zero rows would be faster but would violate the spec requirement.

---

## AI usage note

This project was built with Claude as a coding assistant. Claude was used to:

- Review AAL bookkeeping logic against the sanity check examples
- Generate pytest fixture scaffolding
- Review docstring completeness

All mathematical logic — the three ALAE treatments, the AAL accumulation loop, the sort order — was written and verified by hand against the spec. The sanity check examples were verified manually before being encoded as tests.

The `CLAUDE.md` file in the repo root captures the mathematical invariants, validation rules, and code-organisation constraints that were used to guide and constrain the assistant's output throughout the session.
