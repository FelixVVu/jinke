"""Uniform, raw-building, and non-negative calibrated workplace allocations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

from .grid import POI_COLUMNS

RAW_FEATURE_COLUMNS = ("jrc_nres_volume_m3", *POI_COLUMNS)
MODEL_FEATURE_NAMES = (
    "log1p_jrc_nres_volume_total",
    "log1p_poi_business_finance_total",
    "log1p_poi_industry_logistics_total",
    "log1p_poi_education_research_total",
    "log1p_poi_retail_hospitality_total",
    "log1p_poi_health_public_total",
    "log1p_poi_other_economic_total",
)


@dataclass(frozen=True)
class PpmlFit:
    intercept: float
    coefficients: np.ndarray
    feature_means: np.ndarray
    feature_scales: np.ndarray
    nuisance_names: tuple[str, ...]
    nuisance_coefficients: np.ndarray
    alpha: float
    converged: bool
    iterations: int
    objective: float


def aggregate_control_predictors(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    working = grid.copy()
    working["_centroid_x_area"] = (
        working["center_x"].to_numpy(dtype=float)
        * working["cell_area_m2"].to_numpy(dtype=float)
    )
    working["_centroid_y_area"] = (
        working["center_y"].to_numpy(dtype=float)
        * working["cell_area_m2"].to_numpy(dtype=float)
    )
    aggregations: dict[str, str] = {
        "district": "first",
        "control_name": "first",
        "control_type": "first",
        "control_employment": "first",
        "cell_area_m2": "sum",
        "_centroid_x_area": "sum",
        "_centroid_y_area": "sum",
        **{column: "sum" for column in RAW_FEATURE_COLUMNS},
    }
    controls = working.groupby("accounting_control", as_index=False).agg(aggregations)
    controls = controls.rename(columns={"cell_area_m2": "control_area_m2"})
    controls["area_cell_equivalents"] = controls["control_area_m2"] / 10_000.0
    if (controls["area_cell_equivalents"] <= 0).any():
        raise ValueError("A control has zero analytical exposure.")
    controls["centroid_x"] = controls["_centroid_x_area"] / controls["control_area_m2"]
    controls["centroid_y"] = controls["_centroid_y_area"] / controls["control_area_m2"]
    controls = controls.drop(columns=["_centroid_x_area", "_centroid_y_area"])
    for raw, feature in zip(RAW_FEATURE_COLUMNS, MODEL_FEATURE_NAMES, strict=True):
        controls[feature] = np.log1p(controls[raw].clip(lower=0.0))
    district_medians = controls.groupby("district")[["centroid_x", "centroid_y"]].median()
    median_x = controls["district"].map(district_medians["centroid_x"])
    median_y = controls["district"].map(district_medians["centroid_y"])
    controls["spatial_holdout_fold"] = (
        (controls["centroid_x"] >= median_x).astype(int)
        + 2 * (controls["centroid_y"] >= median_y).astype(int)
    )
    return controls


def _nuisance_names(controls: pd.DataFrame) -> tuple[str, ...]:
    districts = sorted(controls["district"].astype(str).unique())
    control_types = sorted(controls["control_type"].astype(str).unique())
    return tuple(
        [f"district={value}" for value in districts[1:]]
        + [f"control_type={value}" for value in control_types[1:]]
    )


def _nuisance_matrix(
    controls: pd.DataFrame,
    names: tuple[str, ...],
) -> np.ndarray:
    columns: list[np.ndarray] = []
    for name in names:
        field, value = name.split("=", maxsplit=1)
        columns.append((controls[field].astype(str) == value).to_numpy(dtype=float))
    if not columns:
        return np.empty((len(controls), 0), dtype=float)
    return np.column_stack(columns)


def _fit_ppml_arrays(
    x_raw: np.ndarray,
    z: np.ndarray,
    y: np.ndarray,
    alpha: float,
    nuisance_names: tuple[str, ...],
) -> PpmlFit:
    if (y <= 0).any():
        raise ValueError("PPML targets must be positive.")
    means = x_raw.mean(axis=0)
    scales = x_raw.std(axis=0)
    scales[scales <= 1e-12] = 1.0
    x = (x_raw - means) / scales
    scale = float(y.sum())
    feature_stop = 1 + x.shape[1]
    start = np.zeros(feature_stop + z.shape[1], dtype=float)
    start[0] = np.log(y.mean())

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        intercept = parameters[0]
        beta = parameters[1:feature_stop]
        nuisance = parameters[feature_stop:]
        eta = intercept + x @ beta + z @ nuisance
        if float(np.max(eta)) > 700:
            return float("inf"), np.full_like(parameters, 1e100)
        mu = np.exp(eta)
        residual = mu - y
        nuisance_penalty = 1e-4
        value = float(
            (mu - y * eta).sum() / scale
            + alpha * np.dot(beta, beta)
            + nuisance_penalty * np.dot(nuisance, nuisance)
        )
        gradient = np.concatenate(
            (
                [residual.sum() / scale],
                x.T @ residual / scale + 2.0 * alpha * beta,
                z.T @ residual / scale + 2.0 * nuisance_penalty * nuisance,
            )
        )
        return value, gradient

    result = minimize(
        objective,
        start,
        method="L-BFGS-B",
        jac=True,
        bounds=(
            [(None, None)]
            + [(0.0, None)] * x.shape[1]
            + [(None, None)] * z.shape[1]
        ),
        options={"maxiter": 5_000, "ftol": 1e-12, "gtol": 1e-9},
    )
    if not np.isfinite(result.fun):
        raise RuntimeError("PPML optimization returned a non-finite objective.")
    return PpmlFit(
        intercept=float(result.x[0]),
        coefficients=np.asarray(result.x[1:feature_stop], dtype=float),
        feature_means=np.asarray(means, dtype=float),
        feature_scales=np.asarray(scales, dtype=float),
        nuisance_names=nuisance_names,
        nuisance_coefficients=np.asarray(result.x[feature_stop:], dtype=float),
        alpha=float(alpha),
        converged=bool(result.success),
        iterations=int(result.nit),
        objective=float(result.fun),
    )


def predict_control_counts(fit: PpmlFit, controls: pd.DataFrame) -> np.ndarray:
    x_raw = controls[list(MODEL_FEATURE_NAMES)].to_numpy(dtype=float)
    x = (x_raw - fit.feature_means) / fit.feature_scales
    z = _nuisance_matrix(controls, fit.nuisance_names)
    eta = fit.intercept + x @ fit.coefficients + z @ fit.nuisance_coefficients
    if float(np.max(eta)) > 700:
        raise RuntimeError("Calibrated model prediction overflows; inspect source predictors.")
    return np.exp(eta)


def _cross_validated_predictions(
    controls: pd.DataFrame,
    alpha: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    predictions = np.full(len(controls), np.nan, dtype=float)
    folds: list[dict[str, Any]] = []
    nuisance_names = _nuisance_names(controls)
    z = _nuisance_matrix(controls, nuisance_names)
    for held_out in sorted(controls["spatial_holdout_fold"].unique()):
        train = controls["spatial_holdout_fold"] != held_out
        test = ~train
        fit = _fit_ppml_arrays(
            controls.loc[train, list(MODEL_FEATURE_NAMES)].to_numpy(dtype=float),
            z[train.to_numpy()],
            controls.loc[train, "control_employment"].to_numpy(dtype=float),
            alpha,
            nuisance_names,
        )
        fold_predictions = predict_control_counts(fit, controls.loc[test])
        predictions[np.flatnonzero(test.to_numpy())] = fold_predictions
        actual = controls.loc[test, "control_employment"].to_numpy(dtype=float)
        folds.append(
            {
                "held_out_spatial_quadrant": int(held_out),
                "test_controls": int(test.sum()),
                "test_districts": sorted(controls.loc[test, "district"].unique()),
                "mae_people": float(np.mean(np.abs(fold_predictions - actual))),
                "weighted_absolute_percentage_error": float(
                    np.abs(fold_predictions - actual).sum() / actual.sum() * 100.0
                ),
                "converged": fit.converged,
            }
        )
    if not np.isfinite(predictions).all():
        raise RuntimeError("A geographic holdout fold produced no prediction.")
    return predictions, folds


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    correlation = spearmanr(actual, predicted).statistic
    return {
        "mae_people": float(np.mean(np.abs(predicted - actual))),
        "mean_absolute_percentage_error": float(
            np.mean(np.abs(predicted - actual) / actual) * 100.0
        ),
        "weighted_absolute_percentage_error": float(
            np.abs(predicted - actual).sum() / actual.sum() * 100.0
        ),
        "spearman_rank_correlation": float(correlation),
    }


def fit_calibrated_workplace_model(
    grid: gpd.GeoDataFrame,
    *,
    candidate_alphas: tuple[float, ...] = (0.001, 0.01, 0.1, 1.0, 10.0),
) -> tuple[PpmlFit, pd.DataFrame, dict[str, Any]]:
    controls = aggregate_control_predictors(grid)
    candidates: list[dict[str, Any]] = []
    candidate_predictions: dict[float, np.ndarray] = {}
    candidate_folds: dict[float, list[dict[str, Any]]] = {}
    actual = controls["control_employment"].to_numpy(dtype=float)
    for alpha in candidate_alphas:
        predictions, folds = _cross_validated_predictions(controls, alpha)
        candidate_predictions[alpha] = predictions
        candidate_folds[alpha] = folds
        metrics = _metrics(actual, predictions)
        candidates.append({"alpha": alpha, **metrics})
    candidate_table = pd.DataFrame(candidates)
    # Minimize count-weighted error. Ties prefer the larger stabilizing penalty.
    best_row = candidate_table.sort_values(
        ["weighted_absolute_percentage_error", "alpha"], ascending=[True, False]
    ).iloc[0]
    selected_alpha = float(best_row["alpha"])
    cv_predictions = candidate_predictions[selected_alpha]
    nuisance_names = _nuisance_names(controls)
    final = _fit_ppml_arrays(
        controls[list(MODEL_FEATURE_NAMES)].to_numpy(dtype=float),
        _nuisance_matrix(controls, nuisance_names),
        actual,
        selected_alpha,
        nuisance_names,
    )
    controls = controls.copy()
    controls["geographic_holdout_prediction"] = cv_predictions
    controls["full_fit_prediction"] = predict_control_counts(final, controls)
    top_threshold = float(np.quantile(actual, 0.75))
    top = actual >= top_threshold
    obvious = controls.loc[
        top & (controls["geographic_holdout_prediction"] < 0.5 * controls["control_employment"]),
        [
            "district",
            "accounting_control",
            "control_name",
            "control_employment",
            "geographic_holdout_prediction",
        ],
    ].copy()
    if not obvious.empty:
        obvious["prediction_as_pct_of_actual"] = (
            obvious["geographic_holdout_prediction"]
            / obvious["control_employment"]
            * 100.0
        )
    diagnostics = {
        "model": "non-negative ridge-regularized Poisson pseudo-maximum likelihood count model",
        "formula": (
            "E[control employment] = exp(intercept + district effect + control-type "
            "effect + sum(beta_k × standardized log1p(control proxy total)))"
        ),
        "cell_weight_formula": (
            "clipped area fraction × exp(sum(beta_k × standardized "
            "log1p(cell proxy / clipped area fraction))); equivalently an uncapped "
            "multiplicative power surface using the fitted log-total slopes"
        ),
        "ecological_transfer_disclosure": (
            "coefficients are identified from control-level totals and transferred to "
            "100 m proxy densities; this is evaluated by geographic control holdout, "
            "then every surface is normalized to the observed control total"
        ),
        "coefficient_constraint": (
            "all spatial predictor coefficients are non-negative; district and "
            "control-type calibration effects are unconstrained and cancel during "
            "within-control normalization"
        ),
        "upper_tail_treatment": "no cap, winsorization, log1p target, district min-max, or GDP weights",
        "cross_validation_design": (
            "four within-district geographic-block folds defined by control-centroid "
            "quadrants; the same quadrant is held out across all eight districts; "
            "predictions are evaluated before within-control normalization"
        ),
        "alpha_selection": "minimum geographic-CV weighted absolute percentage error",
        "candidate_alpha_metrics": candidate_table.to_dict(orient="records"),
        "selected_alpha": selected_alpha,
        "all_control_metrics": _metrics(actual, cv_predictions),
        "top_employment_control_definition": f"observed employment >= 75th percentile ({top_threshold:.0f})",
        "top_employment_control_metrics": _metrics(actual[top], cv_predictions[top]),
        "obvious_high_employment_underprediction_rule": (
            "top-quartile control predicted below 50% of observed employment"
        ),
        "obvious_high_employment_underprediction": obvious.to_dict(orient="records"),
        "geographic_folds": candidate_folds[selected_alpha],
        "final_fit": {
            "converged": final.converged,
            "iterations": final.iterations,
            "objective": final.objective,
            "intercept": final.intercept,
            "standardized_spatial_coefficients": dict(
                zip(MODEL_FEATURE_NAMES, final.coefficients.tolist(), strict=True)
            ),
            "unstandardized_log_total_slopes": dict(
                zip(
                    MODEL_FEATURE_NAMES,
                    (final.coefficients / final.feature_scales).tolist(),
                    strict=True,
                )
            ),
            "feature_means": dict(
                zip(MODEL_FEATURE_NAMES, final.feature_means.tolist(), strict=True)
            ),
            "feature_scales": dict(
                zip(MODEL_FEATURE_NAMES, final.feature_scales.tolist(), strict=True)
            ),
            "calibration_effects": dict(
                zip(
                    final.nuisance_names,
                    final.nuisance_coefficients.tolist(),
                    strict=True,
                )
            ),
            "nuisance_penalty": 0.0001,
        },
    }
    return final, controls, diagnostics


def _cell_model_matrix(grid: gpd.GeoDataFrame) -> np.ndarray:
    exposure = grid["area_fraction"].to_numpy(dtype=float)
    if (exposure <= 0).any():
        raise ValueError("Grid contains a zero-area cell.")
    columns = []
    for raw in RAW_FEATURE_COLUMNS:
        density = grid[raw].to_numpy(dtype=float) / exposure
        columns.append(np.log1p(np.clip(density, 0.0, None)))
    return np.column_stack(columns)


def _normalize_within_controls(
    grid: gpd.GeoDataFrame,
    raw_weight: np.ndarray,
    output_column: str,
) -> np.ndarray:
    allocated = np.zeros(len(grid), dtype=float)
    controls = grid["accounting_control"].to_numpy()
    targets = grid["control_employment"].to_numpy(dtype=float)
    for control in pd.unique(controls):
        indices = np.flatnonzero(controls == control)
        weights = np.asarray(raw_weight[indices], dtype=float)
        if not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError(f"Invalid {output_column} weights in control {control}.")
        if float(weights.sum()) <= 0:
            weights = grid.iloc[indices]["area_fraction"].to_numpy(dtype=float)
        target_values = np.unique(targets[indices])
        if len(target_values) != 1:
            raise ValueError(f"Control {control} has inconsistent employment targets.")
        target = float(target_values[0])
        values = target * weights / weights.sum()
        values[int(np.argmax(weights))] += target - float(values.sum())
        if (values < -1e-8).any():
            raise RuntimeError(f"Allocation became negative in control {control}.")
        allocated[indices] = np.clip(values, 0.0, None)
    return allocated


def allocate_control_employment(
    grid: gpd.GeoDataFrame,
    fit: PpmlFit,
) -> gpd.GeoDataFrame:
    output = grid.copy()
    uniform_weight = output["cell_area_m2"].to_numpy(dtype=float)
    building_weight = output["jrc_nres_volume_m3"].to_numpy(dtype=float)
    x = _cell_model_matrix(output)
    standardized_x = (x - fit.feature_means) / fit.feature_scales
    log_weight = (
        np.log(output["area_fraction"].to_numpy(dtype=float))
        + standardized_x @ fit.coefficients
    )
    calibrated_weight = np.zeros(len(output), dtype=float)
    controls = output["accounting_control"].to_numpy()
    for control in pd.unique(controls):
        indices = np.flatnonzero(controls == control)
        local = log_weight[indices]
        calibrated_weight[indices] = np.exp(local - float(local.max()))
    output["cell_employment_uniform"] = _normalize_within_controls(
        output, uniform_weight, "uniform"
    )
    output["cell_employment_building_volume"] = _normalize_within_controls(
        output, building_weight, "building_volume"
    )
    output["cell_employment_calibrated_workplace"] = _normalize_within_controls(
        output, calibrated_weight, "calibrated_workplace"
    )
    output["allocation_model"] = "three retained: uniform/building_volume/calibrated_workplace"
    return output


def allocate_finance_residuals(
    allocated_grid: gpd.GeoDataFrame,
    residuals: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Locate only bulletin-identified finance residuals; leave all others in the ledger."""

    frames: list[gpd.GeoDataFrame] = []
    spatial_flag = residuals["central_is_spatially_allocated"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    )
    spatial = residuals.loc[spatial_flag]
    ordinary = allocated_grid.loc[
        allocated_grid["control_type"].isin(["street", "town"])
    ].copy()
    for residual in spatial.itertuples(index=False):
        frame = ordinary.loc[ordinary["district"] == residual.district].copy()
        frame["residual_mask_control"] = frame["accounting_control"].astype(str)
        finance = frame["poi_business_finance"].to_numpy(dtype=float)
        exposure = frame["area_fraction"].to_numpy(dtype=float)
        building_density = frame["jrc_nres_volume_m3"].to_numpy(dtype=float) / exposure
        weights = finance * (1.0 + np.log1p(np.clip(building_density, 0.0, None)))
        if float(weights.sum()) <= 0:
            weights = frame["jrc_nres_volume_m3"].to_numpy(dtype=float)
        if float(weights.sum()) <= 0:
            raise RuntimeError(f"No finance-specific workplace evidence in {residual.district}.")
        values = float(residual.employment_nominal) * weights / weights.sum()
        values[int(np.argmax(weights))] += float(residual.employment_nominal) - float(
            values.sum()
        )
        frame["accounting_control"] = residual.residual_id
        frame["control_name"] = residual.residual_id
        frame["control_type"] = "residual_finance"
        frame["control_employment"] = int(residual.employment_nominal)
        frame["cell_employment_uniform"] = 0.0
        frame["cell_employment_building_volume"] = 0.0
        frame["cell_employment_calibrated_workplace"] = 0.0
        frame["cell_employment_residual_central"] = values
        frame["allocation_model"] = "finance-specific Overture workplace evidence"
        frame["residual_treatment"] = residual.central_rule
        frame["boundary_source"] = "ordinary OSM controls used as a district mask"
        frame["cell_id"] = (
            frame["accounting_control"].astype(str)
            + ":"
            + frame["residual_mask_control"]
            + ":"
            + frame["grid_row"].astype(str)
            + ":"
            + frame["grid_col"].astype(str)
        )
        frames.append(frame)
    if not frames:
        return gpd.GeoDataFrame(columns=allocated_grid.columns, geometry=[], crs=allocated_grid.crs)
    result = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=allocated_grid.crs)
    if result["cell_id"].duplicated().any():
        raise RuntimeError("Residual allocation grid has duplicate cell IDs.")
    return result
