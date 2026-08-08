# -*- coding: utf-8 -*-
"""MMM core: Pareto search + L-BFGS-B + Dummy auto-search + NN-Ridge."""
import numpy as np
import pandas as pd
from sklearn.linear_model import BayesianRidge
from sklearn.preprocessing import StandardScaler
from scipy.optimize import minimize
from joblib import Parallel, delayed
from typing import Optional
import warnings

warnings.filterwarnings('ignore')

from .transforms import apply_transforms, adstock_transform, hill_transform


# ──────────────────────────────────────────────
# Parameter bounds (channel-type-specific, frequency-aware, profile-switchable)
# ──────────────────────────────────────────────
# λ semantics differ by data frequency:
#   daily  λ = carryover fraction PER DAY  (Robyn weekly 0.3 ≈ daily 0.3^(1/7)≈0.845)
#   weekly λ = carryover fraction PER WEEK (Robyn default range)
#
# 'default' profile: designed for daily data based on marketing theory of carryover duration
# 'industry' profile: derived from Robyn/Meridian published weekly defaults, converted to daily
#   (Robyn: SEM=0~0.3wk, Social=0~0.5wk, Awareness/TV=0~0.8wk → daily equivalents)
_LAMBDA_PROFILES = {
    'default': {
        # ── Digital ───────────────────────────────────────────────────────
        'intent':    {'daily': (0.0, 0.15), 'weekly': (0.0, 0.10)},  # SEM・アフィリ・リタゲ・メール
        'pmax':      {'daily': (0.0, 0.25), 'weekly': (0.0, 0.20)},  # Pmax
        'social':    {'daily': (0.0, 0.40), 'weekly': (0.0, 0.45)},  # SNS・Display・チラシ
        'awareness': {'daily': (0.0, 0.75), 'weekly': (0.0, 0.75)},  # 動画・META・OOH・PR
        # ── Offline / non-digital ─────────────────────────────────────────
        'campaign':  {'daily': (0.0, 0.10), 'weekly': (0.0, 0.08)},  # キャンペーン・プロモ
        'event':     {'daily': (0.0, 0.65), 'weekly': (0.0, 0.65)},  # 展示会・セミナー
        # TV CM: Robyn weekly λ≤0.80 → daily λ≤0.97; capped at 0.92 for stability
        'tv':        {'daily': (0.0, 0.92), 'weekly': (0.0, 0.85)},  # テレビCM
        '_fallback': {'daily': (0.0, 0.40), 'weekly': (0.0, 0.45)},
    },
    'industry': {
        # Tighter: Robyn/Meridian weekly defaults scaled to daily
        # SEM ≤0.3wk→daily≤0.10, Social ≤0.5wk→daily≤0.20, Awareness/TV ≤0.8wk→daily≤0.55
        'intent':    {'daily': (0.0, 0.10), 'weekly': (0.0, 0.10)},
        'pmax':      {'daily': (0.0, 0.15), 'weekly': (0.0, 0.15)},
        'social':    {'daily': (0.0, 0.20), 'weekly': (0.0, 0.35)},
        'awareness': {'daily': (0.0, 0.55), 'weekly': (0.0, 0.70)},
        'campaign':  {'daily': (0.0, 0.10), 'weekly': (0.0, 0.08)},
        'event':     {'daily': (0.0, 0.55), 'weekly': (0.0, 0.60)},
        'tv':        {'daily': (0.0, 0.88), 'weekly': (0.0, 0.82)},
        '_fallback': {'daily': (0.0, 0.30), 'weekly': (0.0, 0.40)},
    },
}

# Rules checked in order — more specific prefixes first.
# magazine_ must precede any shorter prefix that could shadow it (none currently).
_LAMBDA_TYPE_RULES = [
    # ── Search / Direct-response digital ─────────────────────────────────
    (('SEM_',),                                              'intent'),
    (('Pmax_', 'GOOGLE_PMAX', 'google_pmax', 'pmax_'),       'pmax'),
    (('bing_', 'msn_', 'yahoo_search_'),                     'intent'),   # Bing/Yahoo検索
    (('affiliate_', 'aff_'),                                 'intent'),   # アフィリエイト
    (('rtg_', 'retarget_', 'remarketing_'),                  'intent'),   # リターゲティング
    (('email_', 'newsletter_', 'mail_'),                     'intent'),   # メール/メルマガ
    # ── Social / Display digital ──────────────────────────────────────────
    (('X_MV',),                                              'awareness'),# X video (before X_)
    (('X_',),                                                'social'),
    (('DEMAND_',),                                           'social'),
    (('gdn_', 'display_'),                                   'social'),   # GDN・ディスプレイ
    (('line_',),                                             'social'),   # LINE広告
    (('tiktok_', 'tt_'),                                     'social'),   # TikTok
    (('ig_',),                                               'social'),   # Instagram
    # ── Awareness / Video digital ─────────────────────────────────────────
    (('META',),                                              'awareness'),
    (('MOVIE_',),                                            'awareness'),
    (('Tver',),                                              'awareness'),
    (('youtube_', 'yt_'),                                    'awareness'), # YouTube
    (('smartnews_', 'gunosy_', 'logly_', 'popin_'),         'awareness'), # ネイティブアド
    (('spotify_', 'podcast_'),                               'awareness'), # Audio
    # ── TV / Mass media ───────────────────────────────────────────────────
    (('tvcm_', 'tv_', 'grp_'),                               'tv'),       # テレビCM / GRP
    (('radio_',),                                            'awareness'), # ラジオ
    (('newspaper_', 'shimbun_', 'magazine_'),                'awareness'), # 新聞・雑誌
    # ── OOH / Out-of-home ─────────────────────────────────────────────────
    (('ooh_', 'outdoor_', 'billboard_', 'transit_',
      'train_ad_', 'kotsukokoku_'),                          'awareness'), # 屋外・交通広告
    # ── Offline direct ────────────────────────────────────────────────────
    (('chirashi_', 'flyer_', 'dm_', 'leaflet_',
      'direct_mail_', 'orikomi_', 'posting_'),               'social'),   # チラシ・折込
    (('campaign_', 'promo_', 'sale_'),                       'campaign'), # キャンペーン
    (('pr_', 'press_', 'mention_', 'coverage_',
      'article_', 'earned_'),                                'awareness'),# PR・メディア掲載
    (('event_', 'expo_', 'seminar_',
      'exhibition_', 'webinar_'),                            'event'),    # 展示会・セミナー
]
# Convenience aliases for the default profile (backward-compat)
LAMBDA_BOUNDS_BY_TYPE = {k: v for k, v in _LAMBDA_PROFILES['default'].items() if k != '_fallback'}
_LAMBDA_BOUNDS_FALLBACK = _LAMBDA_PROFILES['default']['_fallback']
LAMBDA_BOUNDS = (0.0, 0.40)   # kept for backward-compat; prefer get_lambda_bounds()

ALPHA_BOUNDS  = (0.3, 1.0)   # Default: diminishing returns only. Per-channel override via get_alpha_bounds().
GAMMA_BOUNDS  = (0.3, 1.0)   # Robyn default: wider saturation search

# Channel types where S-curve (α > 1) is theoretically grounded:
# TV/OOH/video require repeated exposure before effect kicks in → threshold + saturation.
_SCURVE_CHANNEL_KEYWORDS = (
    'tvcm', 'tv_', 'grp', 'ooh', 'outdoor', 'billboard', 'transit',
    'youtube', 'yt_', 'movie', 'tver', 'spotify', 'radio',
    'newspaper', 'shimbun', 'magazine',
)


def get_alpha_bounds(ch: str, spend_arr: np.ndarray, n_periods: int, freq: str = 'weekly') -> tuple:
    """Per-channel alpha bounds. Allows S-curve (α > 1) only when all 3 conditions hold:
      1. Data volume:     ≥52 weeks or ≥180 days
      2. Spend variation: CV ≥ 0.40  AND  max/min ≥ 5×  AND  sparsity ≤ 30%
      3. Channel type:    TV / OOH / video (threshold effects are theoretically plausible)
    SMB budgets / digital-only channels default to (0.3, 1.0) to prevent overfitting.
    """
    non_zero = spend_arr[spend_arr > 0]
    if len(non_zero) < 5:
        return (0.3, 1.0)

    min_periods = 52 if freq == 'weekly' else 180
    data_ok = n_periods >= min_periods

    cv = float(non_zero.std() / non_zero.mean()) if non_zero.mean() > 0 else 0.0
    range_ratio = float(non_zero.max() / non_zero.min()) if float(non_zero.min()) > 0 else 1.0
    sparsity = float((spend_arr == 0).mean())
    variation_ok = cv >= 0.40 and range_ratio >= 5.0 and sparsity <= 0.30

    ch_lower = ch.lower()
    type_ok = any(kw in ch_lower for kw in _SCURVE_CHANNEL_KEYWORDS)

    if data_ok and variation_ok and type_ok:
        return (0.5, 2.0)
    return (0.3, 1.0)


def get_lambda_bounds(ch: str, freq: str = 'daily', profile: str = 'default') -> tuple:
    """Return (lo, hi) lambda bounds for a channel based on its marketing type, data frequency, and profile."""
    freq_key = 'weekly' if freq == 'weekly' else 'daily'
    prof = _LAMBDA_PROFILES.get(profile, _LAMBDA_PROFILES['default'])
    for prefixes, ch_type in _LAMBDA_TYPE_RULES:
        for prefix in prefixes:
            if prefix.endswith('_'):
                if ch.startswith(prefix):
                    return prof[ch_type][freq_key]
            else:
                if ch == prefix or ch.startswith(prefix + '_'):
                    return prof[ch_type][freq_key]
    return prof['_fallback'][freq_key]


def _build_features(media: dict, params: dict, controls: dict, dummy_cols: np.ndarray = None) -> np.ndarray:
    """Build feature matrix: [adstocked_hill channels] + [controls] + [dummies]."""
    cols = []
    channels = list(media.keys())
    for ch in channels:
        p = params[ch]
        x_t = apply_transforms(media[ch], p['lambda'], p['alpha'], p['gamma'])
        cols.append(x_t)
    for arr in controls.values():
        cols.append(arr.astype(float))
    if dummy_cols is not None and dummy_cols.shape[0] > 0:
        for i in range(dummy_cols.shape[1]):
            cols.append(dummy_cols[:, i])
    return np.column_stack(cols)


class NNRidgeModel:
    """Non-Negative Ridge: L2-penalized OLS with beta >= 0 constraint.

    Drop-in replacement for BayesianRidge. Guarantees non-negative channel
    coefficients, eliminating the need for post-hoc is_zero workarounds caused
    by negative estimates on sparse SMB data.

    Attributes match sklearn interface: coef_, intercept_, predict().
    sigma_ is intentionally absent; CI uses bootstrap SE instead.
    """

    def __init__(self, alpha: float = 1.0):
        self.alpha = float(alpha)
        self.coef_: np.ndarray = None
        self.intercept_: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> 'NNRidgeModel':
        n_feat = X.shape[1]

        def obj(params):
            beta, intercept = params[:n_feat], params[n_feat]
            r = y - (X @ beta + intercept)
            return float(r @ r + self.alpha * (beta @ beta))

        def jac(params):
            beta, intercept = params[:n_feat], params[n_feat]
            r = y - (X @ beta + intercept)
            return np.append(-2.0 * (X.T @ r) + 2.0 * self.alpha * beta,
                             -2.0 * r.sum())

        bounds = [(0.0, None)] * n_feat + [(None, None)]
        res = minimize(obj, np.zeros(n_feat + 1), jac=jac,
                       bounds=bounds, method='L-BFGS-B',
                       options={'maxiter': 500, 'ftol': 1e-10})
        self.coef_ = res.x[:n_feat]
        self.intercept_ = float(res.x[n_feat])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return X @ self.coef_ + self.intercept_


def _fit_nn_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1.0):
    """Fit NNRidgeModel on standardised features; returns model + scaler."""
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    model = NNRidgeModel(alpha=alpha)
    model.fit(X_s, y)
    return model, scaler


def _bootstrap_coef_se(X_raw: np.ndarray, y: np.ndarray,
                        n_ch: int, alpha: float = 1.0,
                        n_bootstrap: int = 300, seed: int = 0) -> np.ndarray:
    """Bootstrap SE for the first n_ch (channel) coefficients in raw feature space."""
    rng = np.random.default_rng(seed)
    n = len(y)
    coefs = np.zeros((n_bootstrap, n_ch))
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        sc = StandardScaler()
        X_bs = sc.fit_transform(X_raw[idx])
        m = NNRidgeModel(alpha=alpha)
        m.fit(X_bs, y[idx])
        coefs[b] = m.coef_[:n_ch] / sc.scale_[:n_ch]
    return coefs.std(axis=0)


def _fit_bayesian_ridge(X: np.ndarray, y: np.ndarray):
    """Legacy: BayesianRidge estimator (kept for reference / A-B comparison)."""
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    model = BayesianRidge(max_iter=300, tol=1e-4)
    model.fit(X_s, y)
    return model, scaler


def _score(model, scaler, X_train, y_train, X_hold, y_hold,
           costs: dict, channels: list, coefs: np.ndarray,
           n_channels: int, total_spend: float) -> dict:
    """Compute NRMSE (train), NRMSE (holdout), RSSD, MAPE, R²."""
    y_range = y_train.max() - y_train.min()
    if y_range == 0:
        y_range = 1.0

    pred_train = model.predict(scaler.transform(X_train))
    nrmse_train = np.sqrt(np.mean((y_train - pred_train) ** 2)) / y_range

    pred_hold = model.predict(scaler.transform(X_hold))
    y_hold_range = y_hold.max() - y_hold.min() if (y_hold.max() - y_hold.min()) > 0 else 1.0
    nrmse_hold = np.sqrt(np.mean((y_hold - pred_hold) ** 2)) / y_hold_range

    ss_res = np.sum((y_train - pred_train) ** 2)
    ss_tot = np.sum((y_train - y_train.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    nonzero = y_train != 0
    mape = np.mean(np.abs((y_train[nonzero] - pred_train[nonzero]) / y_train[nonzero])) if nonzero.any() else 1.0

    # Use unscaled coefficients (coef / scale_) to compute channel contribution shares for RSSD.
    # This mirrors compute_final_metrics and prevents features with larger raw-scale variance
    # from being systematically under-weighted in Pareto selection.
    unscaled_ch_coefs = coefs[:n_channels] / scaler.scale_[:n_channels]
    ch_contribs = np.array([
        max(unscaled_ch_coefs[i] * X_train[:, i].mean(), 0) for i in range(n_channels)
    ])
    total_contrib = ch_contribs.sum()
    contrib_shares = ch_contribs / total_contrib if total_contrib > 0 else np.zeros(n_channels)

    spend_totals = np.array([costs[ch].sum() for ch in channels[:n_channels]])
    spend_shares = spend_totals / spend_totals.sum() if spend_totals.sum() > 0 else np.zeros(n_channels)

    rssd = float(np.sqrt(np.sum((contrib_shares - spend_shares) ** 2)))

    return {
        'nrmse_train': float(nrmse_train),
        'nrmse_hold':  float(nrmse_hold),
        'r2':          float(r2),
        'mape':        float(mape),
        'rssd':        float(rssd),
        'pred_train':  pred_train,
        'pred_hold':   pred_hold,
        'ch_contribs': ch_contribs,
        'contrib_shares': contrib_shares,
        'spend_shares': spend_shares,
    }


def _run_batch(indices: list, all_params: list,
               media_train: dict, media_hold: dict,
               controls_train: dict, controls_hold: dict,
               y_train: np.ndarray, y_hold: np.ndarray,
               costs: dict, channels: list,
               n_ch: int, holdout_weight: float) -> list:
    """Run a batch of Pareto trials sequentially in one worker process.

    Batching amortizes process-startup and pickle overhead, which dominates
    when individual trials are fast (~4ms each).
    """
    import warnings
    warnings.filterwarnings('ignore')
    batch = []
    for i in indices:
        params = all_params[i]
        X_tr = _build_features(media_train, params, controls_train)
        X_ho = _build_features(media_hold,  params, controls_hold)
        model, scaler = _fit_nn_ridge(X_tr, y_train)
        coefs = model.coef_
        sc = _score(model, scaler, X_tr, y_train, X_ho, y_hold,
                    costs, channels, coefs, n_ch, 0)
        combined = ((1 - holdout_weight) * (sc['nrmse_train'] + sc['rssd'])
                    + holdout_weight * sc['nrmse_hold'])
        batch.append({'trial': i, 'params': params, 'combined': combined, **sc})
    return batch


def pareto_search(media_train: dict, costs: dict, controls_train: dict,
                  y_train: np.ndarray, y_hold: np.ndarray,
                  media_hold: dict = None, controls_hold: dict = None,
                  n_trials: int = 2000,
                  holdout_weight: float = 0.3,
                  seed: int = 42,
                  n_jobs: int = -1,
                  freq: str = 'daily',
                  lambda_profile: str = 'default') -> list:
    """Random Pareto search over Adstock/Hill params for each channel.

    Trials are split into batches (one per worker) to amortize IPC overhead.
    Returns list sorted by combined_score ascending.
    """
    import os
    rng = np.random.default_rng(seed)
    channels = list(media_train.keys())
    n_ch = len(channels)

    if media_hold is None:
        media_hold = {ch: np.zeros(len(y_hold)) for ch in channels}
    if controls_hold is None:
        controls_hold = {k: np.zeros(len(y_hold)) for k in controls_train}

    # Per-channel alpha bounds: S-curve (α > 1) only when data + channel type support it
    n_train = len(y_train)
    alpha_bounds_by_ch = {ch: get_alpha_bounds(ch, costs[ch], n_train, freq) for ch in channels}

    # Pre-generate all params upfront to guarantee reproducibility regardless of n_jobs
    all_params = []
    for _ in range(n_trials):
        params = {ch: {
            'lambda': float(rng.uniform(*get_lambda_bounds(ch, freq, lambda_profile))),
            'alpha':  float(rng.uniform(*alpha_bounds_by_ch[ch])),
            'gamma':  float(rng.uniform(*GAMMA_BOUNDS)),
        } for ch in channels}
        all_params.append(params)

    n_cores = os.cpu_count() or 1
    actual_jobs = n_cores if n_jobs == -1 else max(1, min(n_jobs, n_cores))

    # Split trial indices into equal-sized batches (one batch per worker)
    idx = list(range(n_trials))
    batch_size = max(1, n_trials // actual_jobs)
    batches = [idx[i:i + batch_size] for i in range(0, n_trials, batch_size)]

    batch_results = Parallel(n_jobs=actual_jobs, backend='loky')(
        delayed(_run_batch)(
            b, all_params,
            media_train, media_hold,
            controls_train, controls_hold,
            y_train, y_hold,
            costs, channels, n_ch, holdout_weight,
        )
        for b in batches
    )

    results = [r for batch in batch_results for r in batch]
    results.sort(key=lambda x: x['combined'])
    return results


def local_optimize(best_trial: dict, media_train: dict, costs: dict, controls_train: dict,
                   y_train: np.ndarray, y_hold: np.ndarray,
                   media_hold: dict = None, controls_hold: dict = None,
                   holdout_weight: float = 0.3,
                   freq: str = 'daily',
                   lambda_profile: str = 'default') -> dict:
    """L-BFGS-B local optimization starting from best Pareto trial."""
    channels = list(media_train.keys())
    n_ch = len(channels)

    if media_hold is None:
        media_hold = {ch: np.zeros(len(y_hold)) for ch in channels}
    if controls_hold is None:
        controls_hold = {k: np.zeros(len(y_hold)) for k in controls_train}

    init_params = best_trial['params']
    x0 = []
    for ch in channels:
        p = init_params[ch]
        x0.extend([p['lambda'], p['alpha'], p['gamma']])

    n_train = len(y_train)
    alpha_bounds_by_ch = {ch: get_alpha_bounds(ch, costs[ch], n_train, freq) for ch in channels}

    bounds = []
    for ch in channels:
        bounds.extend([get_lambda_bounds(ch, freq, lambda_profile), alpha_bounds_by_ch[ch], GAMMA_BOUNDS])

    def objective(x):
        params = {}
        for i, ch in enumerate(channels):
            params[ch] = {'lambda': x[3*i], 'alpha': x[3*i+1], 'gamma': x[3*i+2]}
        try:
            X_tr = _build_features(media_train, params, controls_train)
            X_ho = _build_features(media_hold,  params, controls_hold)
            model, scaler = _fit_nn_ridge(X_tr, y_train)
            sc = _score(model, scaler, X_tr, y_train, X_ho, y_hold,
                        costs, channels, model.coef_, n_ch, 0)
            return (1 - holdout_weight) * (sc['nrmse_train'] + sc['rssd']) + holdout_weight * sc['nrmse_hold']
        except Exception:
            return 1e6

    res = minimize(objective, x0, method='L-BFGS-B', bounds=bounds,
                   options={'maxiter': 200, 'ftol': 1e-9})

    opt_params = {}
    for i, ch in enumerate(channels):
        opt_params[ch] = {
            'lambda': float(np.clip(res.x[3*i],   *get_lambda_bounds(ch, freq, lambda_profile))),
            'alpha':  float(np.clip(res.x[3*i+1], *alpha_bounds_by_ch[ch])),
            'gamma':  float(np.clip(res.x[3*i+2], *GAMMA_BOUNDS)),
        }
    X_tr = _build_features(media_train, opt_params, controls_train)
    X_ho = _build_features(media_hold,  opt_params, controls_hold)
    model, scaler = _fit_nn_ridge(X_tr, y_train)
    sc = _score(model, scaler, X_tr, y_train, X_ho, y_hold,
                costs, channels, model.coef_, n_ch, 0)
    combined = (1 - holdout_weight) * (sc['nrmse_train'] + sc['rssd']) + holdout_weight * sc['nrmse_hold']

    return {
        'params': opt_params,
        'combined': combined,
        'model': model,
        'scaler': scaler,
        **sc,
    }


def auto_dummy_search(best_result: dict, media_train: dict, costs: dict, controls_train: dict,
                      y_train: np.ndarray, y_hold: np.ndarray, dates_train,
                      media_hold: dict = None, controls_hold: dict = None,
                      max_dummies: int = 32, target_r2: float = 0.95,
                      holdout_weight: float = 0.3,
                      dummy_cap_pct: float = 0.05, patience: int = 2) -> dict:
    """Iteratively add dummy variables for large-residual dates.

    Stopping conditions (whichever triggers first):
      1. R² >= target_r2
      2. Holdout NRMSE shows no improvement for `patience` consecutive steps
      3. Hard cap: min(max_dummies, int(n_train * dummy_cap_pct))
    """
    channels = list(media_train.keys())
    n_ch = len(channels)
    n_train = len(y_train)
    n_hold = len(y_hold)
    params = best_result['params']

    if media_hold is None:
        media_hold = {ch: np.zeros(n_hold) for ch in channels}
    if controls_hold is None:
        controls_hold = {k: np.zeros(n_hold) for k in controls_train}

    # ハードキャップ: 絶対上限 と データ長比率の小さいほうを採用
    effective_max = min(max_dummies, max(1, int(n_train * dummy_cap_pct)))

    dummy_cols = np.zeros((n_train, 0))
    dummy_cols_hold = np.zeros((n_hold, 0))
    dummy_dates = []
    current_result = dict(best_result)

    best_hold_nrmse = best_result.get('nrmse_hold', np.inf)
    no_improve_count = 0

    for iteration in range(effective_max):
        # 停止条件①: R²目標達成
        if current_result['r2'] >= target_r2:
            break

        X_tr = _build_features(media_train, params, controls_train,
                                dummy_cols if dummy_cols.shape[1] > 0 else None)
        model = current_result.get('model')
        scaler = current_result.get('scaler')
        if model is None:
            model, scaler = _fit_nn_ridge(X_tr, y_train)

        pred = model.predict(scaler.transform(X_tr))
        residuals = y_train - pred
        abs_res = np.abs(residuals)

        excluded = set(dummy_dates)
        best_date_idx = None
        best_score = -np.inf
        for idx in np.argsort(-abs_res):
            d = str(dates_train[idx])[:10]
            if d not in excluded:
                best_date_idx = idx
                best_date = d
                best_score = abs_res[idx]
                break

        if best_date_idx is None or best_score < 0.5:
            break

        new_dummy_tr = np.zeros(n_train)
        for i, d in enumerate(dates_train):
            if str(d)[:10] == best_date:
                new_dummy_tr[i] = 1.0
        new_dummy_ho = np.zeros(n_hold)

        new_dummy_cols      = np.column_stack([dummy_cols, new_dummy_tr])      if dummy_cols.shape[1] > 0      else new_dummy_tr.reshape(-1, 1)
        new_dummy_cols_hold = np.column_stack([dummy_cols_hold, new_dummy_ho]) if dummy_cols_hold.shape[1] > 0 else new_dummy_ho.reshape(-1, 1)

        X_new_tr = _build_features(media_train, params, controls_train, new_dummy_cols)
        X_ho     = _build_features(media_hold,  params, controls_hold,  new_dummy_cols_hold)

        new_model, new_scaler = _fit_nn_ridge(X_new_tr, y_train)
        sc = _score(new_model, new_scaler, X_new_tr, y_train, X_ho, y_hold,
                    costs, channels, new_model.coef_, n_ch, 0)
        combined = (1 - holdout_weight) * (sc['nrmse_train'] + sc['rssd']) + holdout_weight * sc['nrmse_hold']

        dummy_cols      = new_dummy_cols
        dummy_cols_hold = new_dummy_cols_hold
        dummy_dates.append(best_date)
        current_result = {
            'params': params,
            'combined': combined,
            'model': new_model,
            'scaler': new_scaler,
            'dummy_cols': dummy_cols,
            'dummy_cols_hold': dummy_cols_hold,
            'dummy_dates': dummy_dates,
            **sc,
        }

        # 停止条件②: holdout NRMSE が patience 回連続で改善しなければ打ち切り
        if sc['nrmse_hold'] < best_hold_nrmse:
            best_hold_nrmse = sc['nrmse_hold']
            no_improve_count = 0
        else:
            no_improve_count += 1
            if no_improve_count >= patience:
                break

    return {
        **current_result,
        'dummy_cols': dummy_cols,
        'dummy_dates': dummy_dates,
        'dummy_cols_hold': dummy_cols_hold,
    }


def compute_final_metrics(result: dict, media_train: dict, costs: dict, controls_train: dict,
                          cv_uu: np.ndarray, dates: np.ndarray,
                          y_train: np.ndarray, y_hold: np.ndarray,
                          n_holdout: int,
                          media_hold: dict = None, controls_hold: dict = None) -> dict:
    """Compute all output metrics after final model is selected."""
    channels = list(media_train.keys())
    n_ch = len(channels)
    n_train = len(y_train)
    params = result['params']

    if media_hold is None:
        media_hold = {ch: np.zeros(n_holdout) for ch in channels}
    if controls_hold is None:
        controls_hold = {k: np.zeros(n_holdout) for k in controls_train}

    dummy_cols      = result.get('dummy_cols',      np.zeros((n_train,   0)))
    dummy_cols_hold = result.get('dummy_cols_hold', np.zeros((n_holdout, 0)))

    X_tr = _build_features(media_train, params, controls_train,
                            dummy_cols if dummy_cols.shape[1] > 0 else None)
    X_ho = _build_features(media_hold,  params, controls_hold,
                            dummy_cols_hold if dummy_cols_hold.shape[1] > 0 else None)

    model   = result['model']
    scaler  = result['scaler']
    coefs   = model.coef_

    pred_train_sqrt = model.predict(scaler.transform(X_tr))
    pred_hold_sqrt  = model.predict(scaler.transform(X_ho))

    pred_train_cv = pred_train_sqrt ** 2
    pred_hold_cv  = pred_hold_sqrt ** 2
    actual_train_cv = y_train ** 2
    actual_hold_cv  = y_hold ** 2

    # Channel contributions (in sqrt space, then scaled to CV)
    # Robyn-aligned: use unscaled coefficients (coef / scaler.scale_) to decompose raw feature values
    total_pred_sqrt = model.predict(scaler.transform(X_tr))

    X_tr_raw = X_tr
    # Unscale: model.coef_ are in standardised space; divide by scale_ to get raw-space coefs
    unscaled_coefs = coefs / scaler.scale_

    # Per-week per-channel contributions in sqrt-space (n_train × n_ch)
    ch_contrib_ts = X_tr_raw[:, :n_ch] * unscaled_coefs[:n_ch]
    # Average positive contribution per channel (used for channel-level ratio)
    ch_contribs_sqrt = np.maximum(ch_contrib_ts, 0).mean(axis=0)
    media_sqrt = ch_contribs_sqrt.sum()

    # 95% CI: bootstrap SE for NNRidge; Bayesian posterior SE for legacy BayesianRidge
    try:
        if hasattr(model, 'sigma_'):
            _se_scaled = np.sqrt(np.maximum(np.diag(model.sigma_[:n_ch, :n_ch]), 0))
            _se = _se_scaled / scaler.scale_[:n_ch]
        else:
            _se = _bootstrap_coef_se(X_tr, y_train, n_ch,
                                     alpha=getattr(model, 'alpha', 1.0))
        _xm = X_tr_raw[:, :n_ch].mean(axis=0)
        contrib_ci_low_sqrt  = np.maximum((unscaled_coefs[:n_ch] - 1.96 * _se) * _xm, 0)
        contrib_ci_high_sqrt = np.maximum((unscaled_coefs[:n_ch] + 1.96 * _se) * _xm, 0)
        _ci_available = True
    except Exception:
        contrib_ci_low_sqrt  = ch_contribs_sqrt.copy()
        contrib_ci_high_sqrt = ch_contribs_sqrt.copy()
        _ci_available = False

    # Non-media contributions (controls + dummies): same unscaling
    non_media_contribs_sqrt = np.maximum(
        X_tr_raw[:, n_ch:] * unscaled_coefs[n_ch:], 0
    ).mean(axis=0)
    non_media_sqrt = non_media_contribs_sqrt.sum()

    # Adjusted intercept: prediction when all raw features = 0
    # intercept_ is fit in scaled space, so subtract the centering offset
    adjusted_intercept = float(model.intercept_) - float(np.dot(unscaled_coefs, scaler.mean_))
    baseline_sqrt = max(adjusted_intercept, 0.0)

    # Robyn-aligned MCR: media / (baseline + controls + media)
    # Using clamped positive contributions so MCR stays in [0, 1]
    total_sqrt = baseline_sqrt + non_media_sqrt + media_sqrt
    media_fraction = media_sqrt / max(total_sqrt, 1e-9)

    total_cv = actual_train_cv.sum()
    if media_sqrt > 0:
        ch_cv_contribs = ch_contribs_sqrt / media_sqrt * total_cv * media_fraction
        _cv_scale = total_cv * media_fraction / media_sqrt
        ch_cv_ci_low  = contrib_ci_low_sqrt  * _cv_scale
        ch_cv_ci_high = contrib_ci_high_sqrt * _cv_scale
    else:
        ch_cv_contribs = np.zeros(n_ch)
        ch_cv_ci_low   = np.zeros(n_ch)
        ch_cv_ci_high  = np.zeros(n_ch)
    total_ch_cv = ch_cv_contribs.sum()

    spend_totals = np.array([costs[ch].sum() for ch in channels])
    total_spend = spend_totals.sum()

    channel_metrics = {}
    for i, ch in enumerate(channels):
        cv_contrib = float(ch_cv_contribs[i])
        spend = float(spend_totals[i])
        spend_man = spend / 10000.0
        cpa = spend / cv_contrib if cv_contrib > 0 else None
        roi = cv_contrib / spend_man if spend_man > 0 and cv_contrib > 0 else 0.0

        # 95% CI on ROI / CPA propagated from β posterior
        cv_ci_low   = float(ch_cv_ci_low[i])
        cv_ci_high  = float(ch_cv_ci_high[i])
        roi_ci_low  = cv_ci_low  / spend_man if spend_man > 0 else 0.0
        roi_ci_high = cv_ci_high / spend_man if spend_man > 0 else 0.0
        cpa_ci_low  = spend / cv_ci_high if cv_ci_high > 0 else None
        cpa_ci_high = spend / cv_ci_low  if cv_ci_low  > 0 else None

        is_zero = (coefs[i] <= 1e-6)
        channel_metrics[ch] = {
            'lambda':     params[ch]['lambda'],
            'alpha':      params[ch]['alpha'],
            'gamma':      params[ch]['gamma'],
            'coef':       float(coefs[i]),
            'is_zero':    bool(is_zero),
            'cv_contrib': cv_contrib,
            'spend':      spend,
            'spend_man':  spend_man,
            'cpa':        cpa,
            'roi':        roi,
            'roi_ci_low':  roi_ci_low,
            'roi_ci_high': roi_ci_high,
            'cpa_ci_low':  cpa_ci_low,
            'cpa_ci_high': cpa_ci_high,
            'ci_available': _ci_available,
            'contrib_share': float(ch_cv_contribs[i] / max(total_ch_cv, 1e-9)),
            'spend_share':   float(spend / max(total_spend, 1)),
        }

    # Pre-compute response curve data using actual adstock-transformed media values
    from .metrics import response_curve as _response_curve
    for i, ch in enumerate(channels):
        if not channel_metrics[ch]['is_zero']:
            channel_metrics[ch]['curve_data'] = _response_curve(
                media_train[ch], params[ch], float(coefs[i])
            )
        else:
            channel_metrics[ch]['curve_data'] = None

    ch_cv_arr = np.array([channel_metrics[ch]['cv_contrib'] for ch in channels])
    spend_shares = np.array([channel_metrics[ch]['spend_share'] for ch in channels])
    contrib_shares = np.array([channel_metrics[ch]['contrib_share'] for ch in channels])
    rssd = float(np.sqrt(np.sum((contrib_shares - spend_shares) ** 2)))

    ss_res = np.sum((y_train - pred_train_sqrt) ** 2)
    ss_tot = np.sum((y_train - y_train.mean()) ** 2)
    r2 = float(1 - ss_res / max(ss_tot, 1e-10))

    y_range = y_train.max() - y_train.min() if y_train.max() != y_train.min() else 1.0
    nrmse = float(np.sqrt(np.mean((y_train - pred_train_sqrt) ** 2)) / y_range)

    hold_range = y_hold.max() - y_hold.min() if y_hold.max() != y_hold.min() else 1.0
    nrmse_hold = float(np.sqrt(np.mean((y_hold - pred_hold_sqrt) ** 2)) / hold_range)

    nonzero = y_train > 0
    mape = float(np.mean(np.abs((y_train[nonzero] - pred_train_sqrt[nonzero]) / y_train[nonzero]))) if nonzero.any() else 1.0

    n_zero = sum(1 for ch in channels if channel_metrics[ch]['is_zero'])
    n_valid = n_ch - n_zero

    dummy_info = _classify_dummies(result.get('dummy_dates', []), dates)

    # Per-channel daily contributions (for monthly stacked bar chart)
    # Use unscaled coefs × raw X for correct absolute decomposition
    X_tr_scaled = scaler.transform(X_tr)
    pred_sqrt_ts = model.predict(X_tr_scaled)
    ch_daily_contrib = {}
    for i, ch in enumerate(channels):
        raw = np.maximum(unscaled_coefs[i] * X_tr_raw[:, i], 0)
        frac = raw / np.maximum(pred_sqrt_ts, 1e-8)
        ch_daily_contrib[ch] = (frac * actual_train_cv).tolist()

    # Marginal ROI per channel (chain rule: × 2 × sqrt(CV_mean) to convert to CV units)
    # coef must be unscaled (raw-space) because Hill operates on raw adstocked values
    from .metrics import compute_marginal_roi as _mroi
    pred_sqrt_mean = float(np.maximum(pred_sqrt_ts, 0).mean())
    for i, ch in enumerate(channels):
        try:
            channel_metrics[ch]['marginal_roi'] = _mroi(
                media_train[ch], costs[ch], params[ch], unscaled_coefs[i],
                pred_sqrt_mean=pred_sqrt_mean,
            )
        except Exception:
            channel_metrics[ch]['marginal_roi'] = 0.0

    # Saturation score = marginal_roi / avg_roi (飽和度合いの指標)
    # > 0.5: 伸び代あり / 0.2-0.5: 適正域 / < 0.2: 飽和域
    # 全体支出の0.5%未満のチャネルは信号が少なすぎて計算が壊れるため計測不能扱い
    total_spend_man = total_spend / 10000
    for ch in channels:
        mroi = channel_metrics[ch].get('marginal_roi', 0.0)
        avg_roi = channel_metrics[ch]['roi']
        is_zero = channel_metrics[ch]['is_zero']
        spend_share = channel_metrics[ch]['spend_man'] / total_spend_man if total_spend_man > 0 else 0.0
        if is_zero:
            sat_score = 0.0
            sat_label = '係数ゼロ'
        elif spend_share < 0.005:
            sat_score = 0.0
            sat_label = '計測不能'
        elif avg_roi <= 0:
            sat_score = 0.0
            sat_label = '計測不能'
        else:
            sat_score = mroi / avg_roi
            sat_label = ('伸び代あり' if sat_score > 0.5 else
                         '適正域'    if sat_score >= 0.2 else
                         '飽和域')
        channel_metrics[ch]['saturation_score'] = sat_score
        channel_metrics[ch]['saturation_label'] = sat_label

    # Dummy coefficients (coefs ordered: channels → controls → dummies)
    n_ctrl = len(controls_train)
    n_dum = dummy_cols.shape[1]
    dum_coefs = list(coefs[n_ch + n_ctrl: n_ch + n_ctrl + n_dum]) if n_dum > 0 else []
    for di, info in enumerate(dummy_info):
        info['coef'] = float(dum_coefs[di]) if di < len(dum_coefs) else 0.0

    return {
        'channel_metrics': channel_metrics,
        'channels': channels,
        'r2': r2,
        'nrmse': nrmse,
        'nrmse_hold': nrmse_hold,
        'rssd': rssd,
        'mape': mape,
        'n_zero': n_zero,
        'n_valid': n_valid,
        'total_cv': float(total_cv),
        'total_spend': float(total_spend),
        'media_fraction': float(media_fraction),
        'baseline_fraction': float(1.0 - media_fraction),
        'pred_train_sqrt': pred_train_sqrt,
        'pred_hold_sqrt':  pred_hold_sqrt,
        'actual_train_cv': actual_train_cv,
        'actual_hold_cv':  actual_hold_cv,
        'dates_train': dates[:n_train],
        'dates_hold':  dates[n_train:],
        'dummy_info': dummy_info,
        'n_dummies': len(result.get('dummy_dates', [])),
        'ch_daily_contrib': ch_daily_contrib,
    }


def detect_collinear_groups(
    media_data: dict,
    cv_array: np.ndarray,
    corr_threshold: float = 0.70,
) -> dict:
    """多重共線性チャネルをグループ化し、代表チャネルを選出する。

    Returns:
        {representative_ch: [all members including rep], ...}
        単独チャネルも含む（1要素リスト）。
    代表チャネル = グループ内でCVとの|相関|が最も高いチャネル。
    """
    channels = list(media_data.keys())
    if len(channels) <= 1:
        return {ch: [ch] for ch in channels}

    # log1p変換で外れ値の影響を抑えて相関行列を計算
    mat  = np.column_stack([np.log1p(np.maximum(media_data[ch], 0)) for ch in channels])
    df   = pd.DataFrame(mat, columns=channels)
    corr = df.corr().abs().fillna(0.0)

    # Greedy clustering: 先着優先で r >= threshold のチャネルを同グループに統合
    visited  = set()
    clusters = []
    for ch in channels:
        if ch in visited:
            continue
        cluster = [ch]
        visited.add(ch)
        for other in channels:
            if other not in visited and float(corr.loc[ch, other]) >= corr_threshold:
                cluster.append(other)
                visited.add(other)
        clusters.append(cluster)

    # 代表チャネル = |corr with CV| 最大のチャネル
    cv_log = np.log1p(np.maximum(cv_array, 0))
    cv_s   = pd.Series(cv_log)
    groups: dict = {}
    for cluster in clusters:
        if len(cluster) == 1:
            groups[cluster[0]] = cluster
        else:
            rep = max(cluster, key=lambda c: abs(float(df[c].corr(cv_s))))
            groups[rep] = cluster

    return groups


def redistribute_collinear_attribution(
    channel_metrics: dict,
    collinear_groups: dict,
    all_costs: dict,
) -> dict:
    """代表チャネルのCV帰属を、グループ内の実スペンド比で全メンバーに再分配する。

    統合されたチャネルには is_merged=True / merged_into=<rep> フラグを付与。
    代表チャネル自身も spend-proportional な値に更新する。
    """
    import copy
    metrics = copy.deepcopy(channel_metrics)

    total_spend_all = max(sum(float(v.sum()) for v in all_costs.values()), 1.0)
    total_cv_all    = max(sum(m.get('cv_contrib', 0.0) for m in metrics.values()), 1.0)

    for rep, members in collinear_groups.items():
        non_reps = [m for m in members if m != rep]
        if not non_reps:
            continue
        if rep not in metrics:
            continue

        rep_cv = metrics[rep].get('cv_contrib', 0.0)

        group_spends      = {m: float(all_costs[m].sum()) for m in members if m in all_costs}
        total_group_spend = max(sum(group_spends.values()), 1e-9)

        rep_m = metrics[rep]  # snapshot before overwrite

        for m in members:
            raw_spend   = group_spends.get(m, 0.0)
            share       = raw_spend / total_group_spend
            m_cv        = rep_cv * share
            m_spend_man = raw_spend / 10_000.0

            if m == rep:
                metrics[m].update({
                    'cv_contrib':    m_cv,
                    'spend':         raw_spend,
                    'spend_man':     m_spend_man,
                    'cpa':           raw_spend / m_cv if m_cv > 0 else None,
                    'roi':           m_cv / m_spend_man if m_spend_man > 0 and m_cv > 0 else 0.0,
                    'contrib_share': m_cv / total_cv_all,
                    'spend_share':   raw_spend / total_spend_all,
                    'is_merged':     False,
                })
            else:
                metrics[m] = {
                    'lambda':           rep_m.get('lambda', 0.0),
                    'alpha':            rep_m.get('alpha', 1.0),
                    'gamma':            rep_m.get('gamma', 1.0),
                    'coef':             rep_m.get('coef', 0.0),
                    'is_zero':          rep_m.get('is_zero', False),
                    'cv_contrib':       m_cv,
                    'spend':            raw_spend,
                    'spend_man':        m_spend_man,
                    'cpa':              raw_spend / m_cv if m_cv > 0 else None,
                    'roi':              m_cv / m_spend_man if m_spend_man > 0 and m_cv > 0 else 0.0,
                    'contrib_share':    m_cv / total_cv_all,
                    'spend_share':      raw_spend / total_spend_all,
                    'marginal_roi':     rep_m.get('marginal_roi', 0.0),
                    'saturation_score': rep_m.get('saturation_score', 0.0),
                    'saturation_label': rep_m.get('saturation_label', '計測不能'),
                    'curve_data':       rep_m.get('curve_data'),
                    'is_merged':        True,
                    'merged_into':      rep,
                }

    return metrics


def data_quality_check(
    media_data: dict,
    cv_array: np.ndarray,
    inverse_ratio_threshold: float = 0.6,
    min_active_days: int = 7,
) -> dict:
    """データ品質を自動チェックし、問題チャネルを分類する。

    Returns:
        {
            'sparse_channels': {ch: n_active},  # 稼働日不足 → モデルから除外
            'inverse_channels': [ch, ...],       # 逆相関 → コントロール変数化
            'warnings': [str, ...],
        }
    """
    warnings_list: list = []
    sparse_channels: dict = {}
    inverse_channels: list = []

    for ch, vals in media_data.items():
        active_mask = vals > 0
        n_active   = int(active_mask.sum())
        n_inactive = int((~active_mask).sum())

        if n_active < min_active_days:
            sparse_channels[ch] = n_active
            warnings_list.append(
                f'{ch}: 稼働日数 {n_active}日（< {min_active_days}日）→ 係数推定不能・除外'
            )
            continue

        if n_active >= 10 and n_inactive >= 10:
            cv_on  = float(cv_array[active_mask].mean())
            cv_off = float(cv_array[~active_mask].mean())
            if cv_off > 0 and cv_on / cv_off < inverse_ratio_threshold:
                inverse_channels.append(ch)
                warnings_list.append(
                    f'{ch}: 稼働日CV={cv_on:.1f} vs 非稼働日CV={cv_off:.1f}'
                    f' (比={cv_on/cv_off:.2f}) → 季節性混在・コントロール変数化'
                )

    return {
        'sparse_channels': sparse_channels,
        'inverse_channels': inverse_channels,
        'warnings': warnings_list,
    }


def make_monthly_dummies(dates: np.ndarray) -> np.ndarray:
    """月次バイナリダミー列を生成する（M02〜M12、M01を基準として省略）。

    Returns: shape (n, 11) の float 配列
    """
    months = pd.DatetimeIndex(pd.to_datetime(dates)).month
    return np.column_stack([(months == m).astype(float) for m in range(2, 13)])


def _classify_dummies(dummy_dates: list, all_dates) -> list:
    """Classify dummy dates by day-of-week and known events."""
    import datetime
    GW_DATES = {'05-03', '05-04', '05-05', '05-06'}
    YEAR_END = {'12-29', '12-30', '12-31', '01-01', '01-02', '01-03'}

    info = []
    for i, d in enumerate(dummy_dates):
        dt = pd.Timestamp(d)
        dow = dt.dayofweek
        mmdd = d[5:][:5]
        category = '土日変動' if dow >= 5 else \
                   'GW' if mmdd in GW_DATES else \
                   '年末' if mmdd in YEAR_END else '要因不明'
        direction = '要因不明'
        info.append({
            'rank': i + 1,
            'name': f'D_{d[5:7]}{d[8:10]}' if len(d) == 10 else f'DUMMY_{i}',
            'date': d,
            'category': category,
            'dow': ['月', '火', '水', '木', '金', '土', '日'][dow],
        })
    return info
