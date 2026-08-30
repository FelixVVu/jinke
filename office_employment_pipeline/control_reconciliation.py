"""Constrained fine-control by industry reconciliation for office employment.

The official Fifth Economic Census publishes two compatible sets of margins at
different grains: district-by-industry employment and fine geographic total
employment.  This module constructs the otherwise unobserved contingency table
with a maximum-entropy (independence-prior RAS/IPF) reconciliation.  An explicit
OTHER column closes the all-industry row margins.

Audited residual strata are retained as separate rows so the matrix grand total
remains the exact district total.  Where a bulletin explicitly identifies
the residual as finance (or finance plus construction), the finance assignment
is fixed before IPF instead of being spread back into street/town controls.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


CORE_CODES = ("I", "J", "M")
SELECTED_72_CODES = ("721", "723", "724", "725")
OFFICE_CODES = (*CORE_CODES, *SELECTED_72_CODES)
MATRIX_CODES = (*OFFICE_CODES, "OTHER")
SCENARIOS = ("low_office_intensity", "base", "high_office_intensity")

# These residual descriptions establish a sector-compatible deterministic
# assignment.  The residual row first absorbs official district finance (J),
# up to its published row total; any remaining residual capacity is OTHER.
FINANCE_TIED_RESIDUAL_CLASSES = {
    "finance_regulator_return",
    "construction_plus_finance_unsplit",
    "directly_managed_finance",
    "finance",
    "finance_plus_national_channel_construction",
}


@dataclass(frozen=True)
class IPFResult:
    values: np.ndarray
    iterations: int
    maximum_margin_error: float


def _ipf(
    prior: np.ndarray,
    row_targets: np.ndarray,
    column_targets: np.ndarray,
    *,
    tolerance: float = 1e-9,
    maximum_iterations: int = 10_000,
) -> IPFResult:
    """Fit non-negative values to exact row and column margins with RAS/IPF."""

    values = np.asarray(prior, dtype=float).copy()
    row_targets = np.asarray(row_targets, dtype=float)
    column_targets = np.asarray(column_targets, dtype=float)
    if values.shape != (len(row_targets), len(column_targets)):
        raise ValueError("IPF prior shape does not match its margins.")
    if not math.isclose(
        float(row_targets.sum()), float(column_targets.sum()), abs_tol=tolerance
    ):
        raise ValueError("IPF row and column margins have different grand totals.")
    if (values < 0).any() or (row_targets < 0).any() or (column_targets < 0).any():
        raise ValueError("IPF inputs must be non-negative.")
    zero_columns = column_targets == 0
    values[:, zero_columns] = 0.0
    positive = np.outer(row_targets > 0, column_targets > 0)
    if (values[positive] <= 0).any():
        raise ValueError("Positive IPF margins require a strictly positive prior.")

    error = float("inf")
    for iteration in range(1, maximum_iterations + 1):
        row_sums = values.sum(axis=1)
        row_scale = np.divide(
            row_targets,
            row_sums,
            out=np.ones_like(row_targets),
            where=row_sums > 0,
        )
        values *= row_scale[:, None]
        column_sums = values.sum(axis=0)
        column_scale = np.divide(
            column_targets,
            column_sums,
            out=np.ones_like(column_targets),
            where=column_sums > 0,
        )
        values *= column_scale[None, :]
        error = max(
            float(np.max(np.abs(values.sum(axis=1) - row_targets))),
            float(np.max(np.abs(values.sum(axis=0) - column_targets))),
        )
        if error <= tolerance:
            return IPFResult(values=values, iterations=iteration, maximum_margin_error=error)
    raise RuntimeError(f"IPF did not converge; maximum margin error is {error}.")


def _controlled_integer_round(
    values: np.ndarray,
    row_targets: np.ndarray,
    column_targets: np.ndarray,
) -> np.ndarray:
    """Round an IPF table to integers while retaining both margins exactly."""

    floor = np.floor(values + 1e-10).astype(np.int64)
    row_need = np.asarray(row_targets, dtype=np.int64) - floor.sum(axis=1)
    column_need = np.asarray(column_targets, dtype=np.int64) - floor.sum(axis=0)
    if (row_need < 0).any() or (column_need < 0).any():
        raise RuntimeError("Controlled rounding produced a negative remainder.")
    if int(row_need.sum()) != int(column_need.sum()):
        raise RuntimeError("Controlled-rounding remainders do not balance.")
    if int(row_need.sum()) == 0:
        return floor

    n_rows, n_columns = values.shape
    variable_count = n_rows * n_columns
    constraint = lil_matrix((n_rows + n_columns, variable_count), dtype=float)
    for row in range(n_rows):
        start = row * n_columns
        constraint[row, start : start + n_columns] = 1.0
    for column in range(n_columns):
        constraint[n_rows + column, column::n_columns] = 1.0
    target = np.concatenate([row_need, column_need]).astype(float)
    fractional = (values - floor).reshape(-1)
    # The tiny stable index term resolves otherwise equivalent optima.
    tie_break = np.arange(variable_count, dtype=float) * 1e-12
    objective = -fractional + tie_break
    upper = (values.reshape(-1) > 0).astype(float)
    result = milp(
        c=objective,
        integrality=np.ones(variable_count, dtype=np.int8),
        bounds=Bounds(np.zeros(variable_count), upper),
        constraints=LinearConstraint(constraint.tocsr(), target, target),
        options={"presolve": True},
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"Controlled integer rounding failed: {result.message}")
    additions = np.rint(result.x).astype(np.int64).reshape(values.shape)
    rounded = floor + additions
    if not np.array_equal(rounded.sum(axis=1), np.asarray(row_targets, dtype=np.int64)):
        raise RuntimeError("Controlled rounding failed a row margin.")
    if not np.array_equal(
        rounded.sum(axis=0), np.asarray(column_targets, dtype=np.int64)
    ):
        raise RuntimeError("Controlled rounding failed a column margin.")
    return rounded


def _district_column_targets(
    district: str,
    scenario: str,
    district_total: int,
    district_industry: pd.DataFrame,
    subgroup_scenarios: pd.DataFrame,
) -> dict[str, int]:
    core = (
        district_industry.loc[
            district_industry["district"].eq(district)
            & district_industry["industry_code"].isin(CORE_CODES)
        ]
        .set_index("industry_code")["district_industry_employment"]
        .astype(int)
    )
    selected = (
        subgroup_scenarios.loc[
            subgroup_scenarios["district"].eq(district)
            & subgroup_scenarios["scenario"].eq(scenario)
            & subgroup_scenarios["industry_code"].isin(SELECTED_72_CODES)
        ]
        .set_index("industry_code")["scenario_district_subgroup_employment"]
        .astype(int)
    )
    if set(core.index) != set(CORE_CODES) or set(selected.index) != set(
        SELECTED_72_CODES
    ):
        raise ValueError(f"Missing district industry margins for {district}, {scenario}.")
    targets = {code: int(core.loc[code]) for code in CORE_CODES}
    targets.update({code: int(selected.loc[code]) for code in SELECTED_72_CODES})
    targets["OTHER"] = district_total - sum(targets.values())
    if targets["OTHER"] < 0:
        raise ValueError(f"Office industries exceed total employment in {district}.")
    return targets


def construct_control_industry_matrix(
    fine_controls: pd.DataFrame,
    residual_strata: pd.DataFrame,
    district_industry: pd.DataFrame,
    subgroup_scenarios: pd.DataFrame,
    *,
    priority_districts: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build three exact control-by-industry matrices and district diagnostics."""

    fine = fine_controls.loc[fine_controls["district"].isin(priority_districts)].copy()
    residual = residual_strata.loc[
        residual_strata["district"].isin(priority_districts)
    ].copy()
    if fine.empty or fine["accounting_stratum_id"].duplicated().any():
        raise ValueError("Fine accounting strata must be non-empty and unique.")
    if residual["residual_id"].duplicated().any():
        raise ValueError("District residual strata must be unique.")

    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for district in priority_districts:
            district_fine = fine.loc[fine["district"].eq(district)].copy()
            district_residuals = residual.loc[residual["district"].eq(district)]
            if len(district_residuals) > 1:
                raise ValueError(f"Expected at most one residual stratum for {district}.")
            district_residual = (
                district_residuals.iloc[0] if len(district_residuals) else None
            )
            fine_total = int(district_fine["employment_reconciled"].sum())
            residual_total = (
                int(district_residual["employment_nominal"])
                if district_residual is not None
                else 0
            )
            district_total = fine_total + residual_total
            targets = _district_column_targets(
                district,
                scenario,
                district_total,
                district_industry,
                subgroup_scenarios,
            )

            residual_is_fixed = bool(
                district_residual is not None
                and district_residual["residual_class"]
                in FINANCE_TIED_RESIDUAL_CLASSES
            )
            fixed_residual = {code: 0 for code in MATRIX_CODES}
            if residual_is_fixed:
                fixed_residual["J"] = min(residual_total, targets["J"])
                fixed_residual["OTHER"] = residual_total - fixed_residual["J"]
                active_rows = district_fine
                active_row_targets = active_rows["employment_reconciled"].to_numpy(
                    dtype=np.int64
                )
            elif district_residual is not None:
                residual_row = {
                    "district": district,
                    "accounting_stratum_id": district_residual["residual_id"],
                    "official_control_name_2023": district_residual["residual_id"],
                    "control_type": "residual",
                    "employment_reconciled": residual_total,
                    "geometry_is_approximate": True,
                }
                active_rows = pd.concat(
                    [district_fine, pd.DataFrame([residual_row])], ignore_index=True
                )
                active_row_targets = active_rows["employment_reconciled"].to_numpy(
                    dtype=np.int64
                )
            else:
                active_rows = district_fine
                active_row_targets = active_rows["employment_reconciled"].to_numpy(
                    dtype=np.int64
                )

            active_column_targets = np.array(
                [targets[code] - fixed_residual[code] for code in MATRIX_CODES],
                dtype=np.int64,
            )
            if (active_column_targets < 0).any():
                raise RuntimeError(f"Fixed residual assignment overdraws {district} margins.")
            if int(active_row_targets.sum()) != int(active_column_targets.sum()):
                raise RuntimeError(f"Active margins do not balance for {district}.")

            # The independence table is the maximum-entropy prior when only row and
            # column margins are known.  RAS is still executed and its convergence
            # is recorded, making the construction auditable and extensible.
            grand_total = int(active_row_targets.sum())
            prior = np.outer(active_row_targets, active_column_targets) / grand_total
            fitted = _ipf(prior, active_row_targets, active_column_targets)
            rounded = _controlled_integer_round(
                fitted.values, active_row_targets, active_column_targets
            )

            for row_index, row in active_rows.reset_index(drop=True).iterrows():
                stratum_id = str(row["accounting_stratum_id"])
                is_residual = bool(
                    district_residual is not None
                    and stratum_id == str(district_residual["residual_id"])
                )
                for column_index, code in enumerate(MATRIX_CODES):
                    records.append(
                        {
                            "scenario": scenario,
                            "district": district,
                            "accounting_stratum_id": stratum_id,
                            "control_name": row["official_control_name_2023"],
                            "control_type": "residual" if is_residual else row["control_type"],
                            "row_is_official_fine_control": bool(
                                row.get("row_is_official_fine_control", True)
                            )
                            and not is_residual,
                            "official_row_total_employment": int(
                                row["employment_reconciled"]
                            ),
                            "industry_code": code,
                            "control_industry_employment": int(
                                rounded[row_index, column_index]
                            ),
                            "industry_margin_source": (
                                "official district-by-industry"
                                if code in CORE_CODES
                                else (
                                    "reviewed Core+ district composition scenario"
                                    if code in SELECTED_72_CODES
                                    else "balancing non-office remainder"
                                )
                            ),
                            "matrix_method": (
                                "maximum-entropy independence prior fitted by RAS/IPF; "
                                "deterministic controlled integer rounding"
                            ),
                            "residual_sector_assignment": (
                                "IPF because bulletin residual is not sector-classified"
                                if is_residual
                                else "not applicable"
                            ),
                            "ipf_iterations": fitted.iterations,
                            "ipf_maximum_margin_error": fitted.maximum_margin_error,
                            "geometry_is_approximate": True,
                        }
                    )

            if residual_is_fixed and district_residual is not None:
                for code in MATRIX_CODES:
                    records.append(
                        {
                            "scenario": scenario,
                            "district": district,
                            "accounting_stratum_id": str(district_residual["residual_id"]),
                            "control_name": str(district_residual["residual_id"]),
                            "control_type": "residual",
                            "row_is_official_fine_control": False,
                            "official_row_total_employment": residual_total,
                            "industry_code": code,
                            "control_industry_employment": int(fixed_residual[code]),
                            "industry_margin_source": (
                                "official district-by-industry"
                                if code in CORE_CODES
                                else (
                                    "reviewed Core+ district composition scenario"
                                    if code in SELECTED_72_CODES
                                    else "balancing non-office remainder"
                                )
                            ),
                            "matrix_method": (
                                "bulletin-compatible fixed residual assignment before "
                                "maximum-entropy RAS/IPF"
                            ),
                            "residual_sector_assignment": (
                                "official J assigned to finance-tied residual up to row total; "
                                "remaining residual is OTHER"
                            ),
                            "ipf_iterations": fitted.iterations,
                            "ipf_maximum_margin_error": fitted.maximum_margin_error,
                            "geometry_is_approximate": True,
                        }
                    )

            diagnostics.append(
                {
                    "scenario": scenario,
                    "district": district,
                    "fine_control_count": int(len(district_fine)),
                    "fine_control_employment": fine_total,
                    "residual_employment": residual_total,
                    "district_total_employment": district_total,
                    "residual_class": (
                        district_residual["residual_class"]
                        if district_residual is not None
                        else "none"
                    ),
                    "residual_finance_fixed_employment": fixed_residual["J"],
                    "residual_other_fixed_employment": fixed_residual["OTHER"],
                    "residual_composition_method": (
                        "bulletin-compatible finance assignment"
                        if residual_is_fixed
                        else (
                            "maximum-entropy district composition"
                            if district_residual is not None
                            else "no residual stratum"
                        )
                    ),
                    "ipf_iterations": fitted.iterations,
                    "ipf_maximum_margin_error": fitted.maximum_margin_error,
                    **{f"district_margin_{code}": targets[code] for code in MATRIX_CODES},
                }
            )

    matrix = pd.DataFrame(records)
    matrix["accounting_stratum_id"] = matrix["accounting_stratum_id"].astype(str)
    district_diagnostics = pd.DataFrame(diagnostics)
    validate_control_industry_matrix(
        matrix,
        fine,
        residual,
        district_industry,
        subgroup_scenarios,
        priority_districts=priority_districts,
    )
    return matrix, district_diagnostics


def validate_control_industry_matrix(
    matrix: pd.DataFrame,
    fine_controls: pd.DataFrame,
    residual_strata: pd.DataFrame,
    district_industry: pd.DataFrame,
    subgroup_scenarios: pd.DataFrame,
    *,
    priority_districts: tuple[str, ...],
) -> None:
    """Enforce every published row margin and district industry margin exactly."""

    if (matrix["control_industry_employment"] < 0).any():
        raise RuntimeError("Control-industry matrix contains negative employment.")
    if matrix.duplicated(
        ["scenario", "accounting_stratum_id", "industry_code"]
    ).any():
        raise RuntimeError("Control-industry matrix contains duplicate cells.")
    if set(matrix["scenario"]) != set(SCENARIOS):
        raise RuntimeError("Control-industry matrix is missing a scenario.")
    if set(matrix["industry_code"]) != set(MATRIX_CODES):
        raise RuntimeError("Control-industry matrix is missing an industry column.")

    fine = fine_controls.loc[fine_controls["district"].isin(priority_districts)].copy()
    residual = residual_strata.loc[
        residual_strata["district"].isin(priority_districts)
    ].copy()
    expected_rows = pd.concat(
        [
            fine[["accounting_stratum_id", "employment_reconciled"]].rename(
                columns={"employment_reconciled": "expected"}
            ),
            residual[["residual_id", "employment_nominal"]]
            .rename(
                columns={
                    "residual_id": "accounting_stratum_id",
                    "employment_nominal": "expected",
                }
            ),
        ],
        ignore_index=True,
    )
    expected_rows["accounting_stratum_id"] = expected_rows[
        "accounting_stratum_id"
    ].astype(str)
    observed_rows = matrix.groupby(
        ["scenario", "accounting_stratum_id"], as_index=False
    )["control_industry_employment"].sum()
    checked_rows = observed_rows.merge(
        expected_rows, on="accounting_stratum_id", validate="many_to_one"
    )
    if not (
        checked_rows["control_industry_employment"].astype(int)
        == checked_rows["expected"].astype(int)
    ).all():
        raise RuntimeError("A control-industry row does not match its official total.")

    for scenario in SCENARIOS:
        observed = (
            matrix.loc[matrix["scenario"].eq(scenario)]
            .groupby(["district", "industry_code"])["control_industry_employment"]
            .sum()
        )
        for district in priority_districts:
            district_total = int(
                expected_rows.merge(
                    matrix.loc[
                        matrix["scenario"].eq(scenario),
                        ["accounting_stratum_id", "district"],
                    ].drop_duplicates(),
                    on="accounting_stratum_id",
                    validate="one_to_one",
                )
                .loc[lambda x: x["district"].eq(district), "expected"]
                .sum()
            )
            targets = _district_column_targets(
                district,
                scenario,
                district_total,
                district_industry,
                subgroup_scenarios,
            )
            for code in MATRIX_CODES:
                if int(observed.loc[(district, code)]) != targets[code]:
                    raise RuntimeError(
                        f"Matrix margin failed for {district}, {scenario}, {code}."
                    )
