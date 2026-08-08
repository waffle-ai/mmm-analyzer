# -*- coding: utf-8 -*-
"""Adstock & Hill transforms (Robyn-compliant)."""
import numpy as np


def adstock_transform(x: np.ndarray, lambda_: float) -> np.ndarray:
    """Geometric (Koyck) Adstock: x*_t = x_t + λ * x*_{t-1}  λ∈[0,0.9]"""
    result = np.zeros(len(x), dtype=float)
    result[0] = float(x[0])
    for t in range(1, len(x)):
        result[t] = float(x[t]) + lambda_ * result[t - 1]
    return result


def hill_transform(x: np.ndarray, alpha: float, gamma: float) -> np.ndarray:
    """Hill saturation: H(x) = x^α / (x^α + γ_abs^α)
    gamma is expressed as a quantile in [0,1] of non-zero x values.
    """
    if x.max() == 0:
        return np.zeros_like(x, dtype=float)
    non_zero = x[x > 0]
    if len(non_zero) == 0:
        return np.zeros_like(x, dtype=float)
    gamma_abs = float(np.quantile(non_zero, gamma))
    if gamma_abs == 0:
        gamma_abs = float(x.max()) * 0.5 + 1e-10
    x_a = np.power(x.astype(float), alpha)
    g_a = gamma_abs ** alpha
    return x_a / (x_a + g_a)


def apply_transforms(x: np.ndarray, lambda_: float, alpha: float, gamma: float) -> np.ndarray:
    """Adstock → Hill pipeline for a single channel."""
    adstocked = adstock_transform(x, lambda_)
    return hill_transform(adstocked, alpha, gamma)


def marginal_roi_hill(x_current: float, x_adstocked_ref: np.ndarray,
                      coef: float, alpha: float, gamma: float,
                      cost_per_unit: float, delta_cost: float = 10000.0) -> float:
    """Marginal ROI: additional CV per ¥1万 extra spend at current level."""
    if cost_per_unit <= 0 or x_adstocked_ref.max() == 0:
        return 0.0
    non_zero = x_adstocked_ref[x_adstocked_ref > 0]
    if len(non_zero) == 0:
        return 0.0
    gamma_abs = float(np.quantile(non_zero, gamma))
    if gamma_abs == 0:
        return 0.0

    def hill_scalar(val):
        val = max(val, 0.0)
        va = val ** alpha
        ga = gamma_abs ** alpha
        return va / (va + ga)

    delta_units = delta_cost / max(cost_per_unit, 1.0)
    cv_diff = (hill_scalar(x_current + delta_units) - hill_scalar(x_current)) * coef
    return cv_diff / (delta_cost / 10000.0)
