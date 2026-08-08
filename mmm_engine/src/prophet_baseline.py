# -*- coding: utf-8 -*-
"""Prophet-based baseline decomposition for MMM (Robyn-compatible)."""
import warnings
import numpy as np
import pandas as pd
from pathlib import Path


def load_japan_holidays(holiday_path: str | Path) -> pd.DataFrame:
    """Load Japan holiday data in Prophet-compatible format.

    Accepts the Robyn dt_japan_holidays Excel format:
        ds, holiday, country, year

    Returns DataFrame with columns: ds, holiday, lower_window, upper_window
    filtered to Japan (country == 'JP').
    """
    path = Path(holiday_path)
    if path.suffix.lower() in ('.xlsx', '.xls', '.xlsm'):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    # Normalize column names (handles Japanese headers too)
    rename = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl in ('ds', 'date', '日付'):
            rename[col] = 'ds'
        elif cl in ('holiday', 'name', 'holidays', '祝日', '休日', '名称'):
            rename[col] = 'holiday'
        elif cl in ('country', '国', '国コード'):
            rename[col] = 'country'
    df = df.rename(columns=rename)

    if 'country' in df.columns:
        df = df[df['country'] == 'JP'].copy()

    df['ds'] = pd.to_datetime(df['ds'])

    if 'lower_window' not in df.columns:
        df['lower_window'] = 0
    if 'upper_window' not in df.columns:
        df['upper_window'] = 0

    return df[['ds', 'holiday', 'lower_window', 'upper_window']].reset_index(drop=True)


def compute_prophet_baseline(
    dates: np.ndarray,
    cv_uu: np.ndarray,
    holiday_path: str | Path | None = None,
    yearly_seasonality: bool = True,
    weekly_seasonality: bool = False,   # False by default: weekly effects are better captured by media
    changepoint_prior_scale: float = 0.05,
) -> dict:
    """Fit Prophet on full dataset and return decomposed component arrays.

    Prophet is fitted on ALL data (train + holdout) to get stable seasonal
    estimates, following Robyn convention. The returned components are used
    as control variables in the media model so that trend/seasonality is
    absorbed into the baseline rather than mis-attributed to media channels.

    Returns dict with keys:
        trend, yearly, weekly, holidays, composite, yhat
        All numpy arrays of the same length as `dates`.
    """
    try:
        from prophet import Prophet
    except ImportError:
        raise ImportError(
            "prophetパッケージが未インストールです。 `pip install prophet` を実行してください。"
        )

    df = pd.DataFrame({
        'ds': pd.to_datetime(dates),
        'y': cv_uu.astype(float),
    })

    holidays = None
    if holiday_path is not None:
        try:
            holidays = load_japan_holidays(holiday_path)
        except Exception as e:
            warnings.warn(f"祝日ファイルの読み込みに失敗しました ({e}) → 祝日なしで実行します")

    m = Prophet(
        holidays=holidays,
        yearly_seasonality=yearly_seasonality,
        weekly_seasonality=weekly_seasonality,
        daily_seasonality=False,
        seasonality_mode='additive',
        changepoint_prior_scale=changepoint_prior_scale,
        seasonality_prior_scale=10.0,
    )

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        m.fit(df)

    forecast = m.predict(df[['ds']])

    def _get(col: str) -> np.ndarray:
        if col in forecast.columns:
            return forecast[col].values
        return np.zeros(len(dates))

    yearly   = _get('yearly')
    weekly   = _get('weekly')
    trend    = _get('trend')

    # Prophet may emit multiple holiday columns; sum them
    hol_cols = [c for c in forecast.columns if 'holiday' in c.lower() and c != 'holidays_upper' and c != 'holidays_lower']
    holidays_arr = np.zeros(len(dates))
    for hc in hol_cols:
        holidays_arr += forecast[hc].values

    composite = trend + yearly + weekly + holidays_arr

    return {
        'trend':     trend,
        'yearly':    yearly,
        'weekly':    weekly,
        'holidays':  holidays_arr,
        'composite': composite,
        'yhat':      _get('yhat'),
    }
