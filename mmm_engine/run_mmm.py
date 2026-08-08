# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
"""MMM Auto-Execution Engine — main entry point.

Usage:
    # 列マッピング確認のみ（本番実行なし）
    python run_mmm.py --excel PATH --client NAME --detect-only

    # 本番実行
    python run_mmm.py --excel PATH --client NAME [--output DIR] [--trials N] [--holdout N]

    # レポートのみ再生成（計算スキップ）
    python run_mmm.py --report-only output/MMM_秤_20260623_2248.pkl

Example:
    python run_mmm.py \\
        --excel "../reference_file/hakari_data.xlsm" \\
        --client "株式会社秤" \\
        --output "./output"
"""
import sys
import os
import argparse
import time
import json
import pickle
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from src.data_loader import (load_data, detect_only, save_mapping_yaml, load_mapping_yaml,
                             load_from_sheets, detect_only_from_sheets)
from src.model import (pareto_search, local_optimize, auto_dummy_search,
                       compute_final_metrics,
                       detect_collinear_groups, redistribute_collinear_attribution,
                       _LAMBDA_PROFILES)
from src.metrics import budget_optimization, budget_increase_scenario, budget_decrease_scenario, efficient_budget_frontier
from src.report_generator import generate_report
from src.data_inspector import inspect_channels, print_inspection_report


def log(msg: str):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)


_MONETARY_KW = {'売上', '利益', '金額', '収益', '売り上げ', 'revenue', 'sales', 'profit', 'amount', 'gmv', 'ltv', 'roas'}

def _detect_cv_metric_type(cv_col: str) -> str:
    """cv_col名から金額系('monetary')かCV数系('count')かを判定。"""
    col = cv_col.lower()
    for kw in _MONETARY_KW:
        if kw in col:
            return 'monetary'
    return 'count'


# ── Holdout size based on frequency ────────────────────────────────────────
HOLDOUT_BY_FREQ = {'daily': 14, 'weekly': 4}

# RSSD がこの値を超えた場合、モデル採用前に一時停止してWaffleに確認する
_RSSD_ALERT_THRESHOLD = 0.30

# スパース検出閾値（稼働率ベース・データ期間に依存しない相対値）
_SPARSE_DUMMY_RATE    = 0.05   # 稼働率 < 5%: メディア変数として扱わず診断のみ
_SPARSE_EXCLUDE_RATE  = 0.015  # 稼働率 < 1.5%: 完全除外扱いの診断
_SPARSE_ABS_FLOOR     = {'daily': (10, 5), 'weekly': (4, 2)}  # (ダミー閾値, 除外閾値) 絶対数下限

# デバイス分割自動統合
_DEVICE_SUFFIXES       = ('_PC', '_MOBILE', '_TABLET', '_SP', '_IOS', '_ANDROID', '_DT', '_MB')
_SOFT_COLLINEAR_THRESH = 0.70  # デバイス分割統合の相関閾値


def _train_model(model_media_train, model_media_hold,
                 costs_train, controls_train, controls_hold,
                 y_train, y_hold, holdout_days,
                 cv_uu_train, dates, dates_train, costs,
                 n_trials, n_jobs, holdout_weight, seed, top_k_pareto,
                 max_dummies, target_r2, freq='daily', lambda_profile='default', label='',
                 cv_col='CV'):
    """Steps 4–7: pareto → optimize → dummies → final metrics."""
    import os as _os
    _n_cores = _os.cpu_count() or 1
    _actual_jobs = _n_cores if n_jobs == -1 else min(n_jobs, _n_cores)
    log(f'  パレート探索（{n_trials}試行 / {_actual_jobs}並列）{label}')
    pareto_results = pareto_search(
        model_media_train, costs_train, controls_train,
        y_train, y_hold,
        media_hold=model_media_hold,
        controls_hold=controls_hold,
        n_trials=n_trials,
        holdout_weight=holdout_weight,
        seed=seed,
        n_jobs=n_jobs,
        freq=freq,
        lambda_profile=lambda_profile,
    )
    best_pareto = pareto_results[0]
    log(f'  Best Pareto: R²={best_pareto["r2"]:.4f} '
        f'NRMSE_train={best_pareto["nrmse_train"]:.4f} '
        f'NRMSE_hold={best_pareto["nrmse_hold"]:.4f}')

    log(f'  L-BFGS-B 局所最適化{label}')
    local_candidates = []
    for trial in pareto_results[:top_k_pareto]:
        result = local_optimize(trial, model_media_train, costs_train, controls_train,
                                y_train, y_hold,
                                media_hold=model_media_hold, controls_hold=controls_hold,
                                holdout_weight=holdout_weight, freq=freq,
                                lambda_profile=lambda_profile)
        local_candidates.append(result)
    local_candidates.sort(key=lambda r: r['combined'])
    top3 = local_candidates[:3]

    # ── 候補モデル比較表 ──────────────────────────────────────
    log(f'\n  候補モデル比較（上位{len(top3)}件）:')
    log(f'  {"rank":<5} {"NRMSE_tr":<10} {"NRMSE_ho":<10} {"RSSD":<8} {"R²":<8}')
    for i, c in enumerate(top3):
        marker = ' <- 採用予定' if i == 0 else ''
        log(f'  #{i+1:<4} {c["nrmse_train"]:<10.4f} {c["nrmse_hold"]:<10.4f} '
            f'{c["rssd"]:<8.4f} {c["r2"]:<8.4f}{marker}')

    # ── RSSD異常値チェック → 一時停止 ────────────────────────
    if top3[0]['rssd'] > _RSSD_ALERT_THRESHOLD:
        log(f'\n  [警告] RSSD={top3[0]["rssd"]:.4f} が閾値 {_RSSD_ALERT_THRESHOLD} 超え')
        log(f'  メディア帰属比率と実支出シェアが大きく乖離しています')
        log(f'  チャネル間の多重共線性またはデータ不足が原因の可能性があります')
        if sys.stdin.isatty():
            print(f'\n  採用モデルを選択してください（Enter -> #1 を自動採用）:', flush=True)
            for i, c in enumerate(top3):
                print(f'    {i+1}: RSSD={c["rssd"]:.4f}  NRMSE_ho={c["nrmse_hold"]:.4f}'
                      f'  R2={c["r2"]:.4f}', flush=True)
            raw = input('  >> [1/2/3, Enter=#1]: ').strip()
            idx = (int(raw) - 1) if raw in ('1', '2', '3') else 0
            idx = max(0, min(idx, len(top3) - 1))
        else:
            log(f'  非インタラクティブモード: #1 を自動採用します')
            idx = 0
        best_local = top3[idx]
        if idx > 0:
            log(f'  -> #{idx+1} を採用 (RSSD={best_local["rssd"]:.4f})')
    else:
        best_local = top3[0]

    log(f'  最適化後: R²={best_local["r2"]:.4f} '
        f'NRMSE_train={best_local["nrmse_train"]:.4f} '
        f'NRMSE_hold={best_local["nrmse_hold"]:.4f}')

    _cap = max(1, int(len(y_train) * 0.05))
    _eff = min(max_dummies, _cap)
    log(f'  ダミー変数自動探索（上限{_eff}本: min({max_dummies}, n_train×5%={_cap}) / R²目標{target_r2} / patience=2）{label}')
    dummy_result = auto_dummy_search(
        best_local,
        model_media_train, costs_train, controls_train,
        y_train, y_hold,
        dates_train=dates_train,
        media_hold=model_media_hold,
        controls_hold=controls_hold,
        max_dummies=max_dummies,
        target_r2=target_r2,
        holdout_weight=holdout_weight,
    )
    n_dummies = len(dummy_result.get('dummy_dates', []))
    log(f'  採用ダミー: {n_dummies}本 / R²={dummy_result["r2"]:.4f} '
        f'NRMSE_train={dummy_result["nrmse_train"]:.4f} '
        f'NRMSE_hold={dummy_result["nrmse_hold"]:.4f}')

    log(f'  最終メトリクス算出{label}')
    final_metrics = compute_final_metrics(
        dummy_result, model_media_train, costs_train, controls_train,
        cv_uu_train, dates,
        y_train, y_hold, holdout_days,
        media_hold=model_media_hold, controls_hold=controls_hold,
    )
    final_metrics['cv_metric_type'] = _detect_cv_metric_type(cv_col)
    return final_metrics, n_dummies


def run(excel_path: str,
        client_name: str,
        output_dir: str = './output',
        sheets_id: str = None,
        n_trials: int = 2000,
        n_jobs: int = -1,
        holdout_days: int = None,
        max_dummies: int = 32,
        target_r2: float = 0.95,
        holdout_weight: float = 0.3,
        seed: int = 42,
        top_k_pareto: int = 5,
        sheet_name: str = None,
        header_row: int = None,
        media_basis: str = 'auto',
        budget_increase: float = 0.30,
        max_cpa: float = None,
        constr_low: float = 0.5,
        constr_up: float  = 2.0,
        use_prophet: bool = True,
        holiday_path: str = None,
        lambda_profile: str = 'auto',
        report_type: str = 'simple',
        export_charts_dir: str = None,
        config_path: str = None):          # YAMLコンフィグパス（指定時はauto-detectをスキップ）

    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()

    # ── Step 1: Load data ───────────────────────────────────
    _override_mapping = load_mapping_yaml(config_path) if config_path else None
    if _override_mapping:
        log(f'  YAMLコンフィグ使用: {config_path}')
    if sheets_id:
        log(f'Step 1: Google Sheetsデータを読み込み中... ({sheets_id})')
        data = load_from_sheets(sheets_id, sheet_name=sheet_name,
                                verbose=True, mapping_override=_override_mapping)
    else:
        log('Step 1: Excelデータを読み込み中...')
        data = load_data(excel_path, sheet_name=sheet_name, header_row=header_row,
                         verbose=True, mapping_override=_override_mapping)
    dates    = data['dates']
    cv_uu    = data['cv_uu']
    media    = data['media']
    costs    = data['costs']
    controls = data['controls']
    n_days   = data['n_days']

    # For channels using impression metrics (no click data available),
    # use spend as proxy media metric (standard fallback per Robyn guidelines).
    # Impressions have weak direct correlation with CV after seasonal controls.
    _imp_swapped = []
    _ch_map = data.get('mapping', {}).get('channel_map', {})
    for ch in list(media.keys()):
        orig_col = _ch_map.get(ch, {}).get('media', '')
        cost_arr = costs.get(ch, np.zeros(n_days))
        if 'imp' in str(orig_col).lower() and np.any(cost_arr > 0):
            media[ch] = cost_arr.copy()
            _imp_swapped.append(ch)
    if _imp_swapped:
        log(f'  インプレッション→スペンド変換: {_imp_swapped} (クリックデータなし・スペンドで代替)')

    freq     = data['freq']
    cv_col   = data['mapping']['cv_col']

    log(f'  読込完了: {n_days}{"日" if freq == "daily" else "週"} / チャネル数: {len(media)} / CV総数: {int(cv_uu.sum())}')
    log(f'  期間: {pd.Timestamp(dates[0]).date()} → {pd.Timestamp(dates[-1]).date()}')
    log(f'  試行数: {n_trials}  media_basis: {media_basis}')
    if len(media) <= 2:
        log('')
        log('  [SMBモード] チャネルが少ない構成です。以下で精度が向上する可能性があります:')
        log('    1. Google Trends（主力KWの週次検索ボリューム）をコントロール変数に追加')
        log('    2. SEO / オーガニック流入数をコントロール変数に追加')
        log('    3. テンプレート使用時: python run_mmm.py --init-template smb --save-config output/CLIENT.yaml')
        log('')

    # ── Step 1.5: Pre-modeling data inspection ──────────────
    log('Step 1.5: データ構造事前分析...')
    _findings, _questions = inspect_channels(media, costs, freq=freq)
    print(print_inspection_report(_findings, _questions, freq=freq), flush=True)

    # S字カーブ判定（get_alpha_bounds がデータを評価）
    from src.model import get_alpha_bounds as _get_ab
    _scurve_enabled = [ch for ch in media if _get_ab(ch, costs[ch], n_days, freq) != (0.3, 1.0)]
    if _scurve_enabled:
        log(f'  S字カーブ許可チャネル（α最大2.0）: {_scurve_enabled}')

    # ── Step 2: Preprocess ──────────────────────────────────
    log('Step 2: 前処理（Sqrt変換）...')
    cv_sqrt = np.sqrt(np.maximum(cv_uu, 0))

    # ── Step 2.5: Prophet baseline decomposition ────────────
    # Robyn準拠: デフォルトで有効。--no-prophet で無効化可能。
    # 祝日ファイルは data/dt_japan_holidays.xlsx を自動読み込み（--holidays で上書き可能）。
    _DEFAULT_HOLIDAY_PATH = Path(__file__).parent / 'data' / 'dt_japan_holidays.xlsx'
    if holiday_path is None and _DEFAULT_HOLIDAY_PATH.exists():
        holiday_path = str(_DEFAULT_HOLIDAY_PATH)

    _prophet_active = False
    if use_prophet:
        log('Step 2.5: Prophetベースライン分解（trend + yearly_season'
            f'{" + holiday" if holiday_path else ""}）...')
        try:
            from src.prophet_baseline import compute_prophet_baseline
            prophet_comps = compute_prophet_baseline(
                dates, cv_uu,
                holiday_path=holiday_path,
            )
            controls['prophet_trend']  = prophet_comps['trend']
            controls['prophet_yearly'] = prophet_comps['yearly']
            if np.any(prophet_comps['holidays'] != 0):
                controls['prophet_holidays'] = prophet_comps['holidays']
            _has_holiday = np.any(prophet_comps['holidays'] != 0)
            _prophet_active = True
            log(f'  Prophet: trend + yearly_season'
                f'{" + holidays" if _has_holiday else ""} → コントロール変数に追加')
            log(f'  Prophet yhat 範囲: {prophet_comps["yhat"].min():.1f}〜{prophet_comps["yhat"].max():.1f} '
                f'(実績CV: {cv_uu.min():.1f}〜{cv_uu.max():.1f})')

            # Robyn準拠: Prophet が trend/season を担うため、手動のトレンド・季節性変数を除外する。
            # 除外しないと Prophet と手動変数が多重共線性を起こし RSSD=0・全チャネル同CPA になる。
            _SEASON_TREND_KEYWORDS = ('season', 'trend', 'year', 'month', 'quarter', 'week')
            _removed = [k for k in list(controls.keys())
                        if any(kw in k.lower() for kw in _SEASON_TREND_KEYWORDS)
                        and not k.startswith('prophet_')]
            if _removed:
                for k in _removed:
                    del controls[k]
                log(f'  手動トレンド・季節性変数を除外（Prophetが代替）: {_removed}')
        except Exception as e:
            log(f'  警告: Prophet失敗 ({e}) → スキップ')

    # ── Step 2.8: スパースチャネル自動処理 ──────────────────────
    # 稼働率（非ゼロ期間 / 総期間）< 5% のチャネルを自動処理する。
    # ・施策フラグ型（非ゼロ値の種類≤2 or 変動係数<5%）→ コントロール変数へ自動投入
    # ・それ以外 → モデルから除外（is_zero=True として報告）
    # ★ 両ケースとも media_train_m / costs_train_m からは除外される（Step 3.5 で反映）
    log('Step 2.8: スパースチャネル自動処理（稼働率<5% を検出）...')
    _abs_dummy, _abs_excl = _SPARSE_ABS_FLOOR.get(freq, (10, 5))
    _punit = '週' if freq == 'weekly' else '日'
    _sparse_reasons: dict[str, str] = {}
    _sparse_to_control: set[str] = set()

    def _looks_like_campaign_flag(cost_arr: np.ndarray, media_arr: np.ndarray) -> bool:
        """コスト or 媒体シグナルのどちらかが非ゼロ値の種類≤2 or 変動係数<5% → 施策フラグと判定"""
        for arr in (cost_arr, media_arr):
            nz = arr[arr > 0]
            if len(nz) == 0:
                continue
            if len(np.unique(nz)) <= 2 or float(np.std(nz) / np.mean(nz)) < 0.05:
                return True
        return False

    for _ch, _arr in costs.items():
        _nz   = int(np.sum(_arr > 0))
        _rate = _nz / n_days
        if _rate >= _SPARSE_DUMMY_RATE and _nz >= _abs_dummy:
            continue  # 稼働率 ≥ 5% → 通常処理
        _label = f'{n_days}{_punit}のうち{_nz}{_punit}しか支出がないため'
        if _looks_like_campaign_flag(_arr, media.get(_ch, np.zeros(n_days))):
            controls[f'sparse_flag_{_ch}'] = (_arr > 0).astype(float)
            _sparse_to_control.add(_ch)
            _sparse_reasons[_ch] = f'{n_days}{_punit}のうち{_nz}{_punit}しか支出がなく、CV効果の推定は困難ですが、施策フラグとしてベースラインに組み込まれたチャネルです'
        else:
            _sparse_reasons[_ch] = f'{_label}、CV効果を推定できないチャネルです'

    if _sparse_reasons:
        _n_flag = len(_sparse_to_control)
        _n_excl = len(_sparse_reasons) - _n_flag
        log(f'  スパース自動処理 {len(_sparse_reasons)}チャネル'
            f'（除外: {_n_excl} / フラグ→コントロール: {_n_flag}）:')
        for _ch, _rsn in _sparse_reasons.items():
            _tag = '[フラグ化]' if _ch in _sparse_to_control else '[除外]  '
            log(f'    {_tag} {_ch}: {_rsn}')
    else:
        log('  スパースチャネルなし')

    # ── Step 3: Split hold-out ─────────────────────────────
    if holdout_days is None:
        holdout_days = HOLDOUT_BY_FREQ.get(freq, 14)
    log(f'Step 3: ホールドアウト分割（最終{holdout_days}{"日" if freq == "daily" else "週"}）...')
    n_train = n_days - holdout_days
    y_train = cv_sqrt[:n_train]
    y_hold  = cv_sqrt[n_train:]
    media_train    = {ch: v[:n_train] for ch, v in media.items()}
    media_hold     = {ch: v[n_train:] for ch, v in media.items()}
    costs_train    = {ch: v[:n_train] for ch, v in costs.items()}
    costs_hold     = {ch: v[n_train:] for ch, v in costs.items()}
    controls_train = {k: v[:n_train] for k, v in controls.items()}
    controls_hold  = {k: v[n_train:] for k, v in controls.items()}
    dates_train    = dates[:n_train]
    log(f'  Train: {n_train}日 / Hold-out: {holdout_days}日')

    # ── Step 3.5: 多重共線性チェック ────────────────────────
    log('Step 3.5: 多重共線性チェック（r≥0.85 チャネルをグループ統合）...')
    collinear_groups = detect_collinear_groups(media_train, y_train, corr_threshold=0.85)
    merged_chs = {m for rep, mbs in collinear_groups.items() for m in mbs if m != rep}
    n_merged   = len(merged_chs)
    if n_merged > 0:
        log(f'  {n_merged}チャネルを統合（モデリングから除外→帰属を実スペンド比で再分配）:')
        for rep, mbs in collinear_groups.items():
            if len(mbs) > 1:
                log(f'    代表: {rep}  ← 統合: {[m for m in mbs if m != rep]}')
    else:
        log('  多重共線性なし（全チャネル独立でモデリング）')

    # 代表チャネル + スパース除外チャネルをモデリングから除外
    _exclude_from_model = merged_chs | set(_sparse_reasons.keys())
    media_train_m  = {ch: v for ch, v in media_train.items()  if ch not in _exclude_from_model}
    media_hold_m   = {ch: v for ch, v in media_hold.items()   if ch not in _exclude_from_model}
    costs_train_m  = {ch: v for ch, v in costs_train.items()  if ch not in _exclude_from_model}
    costs_hold_m   = {ch: v for ch, v in costs_hold.items()   if ch not in _exclude_from_model}

    # ── Step 3.25: デバイス分割軟性共線性チェック ────────────
    # _PC/_MOBILE/_TABLET など同一ベース名チャネルが r≥0.70 の場合に自動統合する。
    # Step 3.5 の r≥0.85 ハード統合とは別ロジック（デバイス分割専用）。
    log('Step 3.25: デバイス分割検出（同一ベース名 × r≥0.70 で自動統合）...')

    def _device_base(ch_: str) -> str | None:
        ch_up = ch_.upper()
        for sfx in _DEVICE_SUFFIXES:
            if ch_up.endswith(sfx):
                return ch_[:-len(sfx)]
        return None

    _dev_groups: dict[str, list[str]] = {}
    for _ch in list(media_train_m.keys()):
        _base = _device_base(_ch)
        if _base:
            _dev_groups.setdefault(_base, []).append(_ch)

    _device_merged: dict[str, list[str]] = {}
    for _base, _chs in _dev_groups.items():
        if len(_chs) < 2:
            continue
        _do_merge = False
        for _i in range(len(_chs)):
            for _j in range(_i + 1, len(_chs)):
                _a = media_train_m[_chs[_i]]
                _b = media_train_m[_chs[_j]]
                if np.std(_a) > 0 and np.std(_b) > 0:
                    _r = float(np.corrcoef(_a, _b)[0, 1])
                    if _r >= _SOFT_COLLINEAR_THRESH:
                        _do_merge = True
                        break
            if _do_merge:
                break
        if _do_merge:
            _device_merged[_base] = _chs

    if _device_merged:
        log(f'  {sum(len(v) for v in _device_merged.values())}チャネルをデバイス統合:')
        for _base, _chs in _device_merged.items():
            media_train_m[_base]  = sum(media_train_m.pop(_ch)  for _ch in _chs)
            media_hold_m[_base]   = sum(media_hold_m.pop(_ch)   for _ch in _chs)
            costs_train_m[_base]  = sum(costs_train_m.pop(_ch)  for _ch in _chs)
            costs_hold_m[_base]   = sum(costs_hold_m.pop(_ch)   for _ch in _chs)
            costs[_base]          = sum(costs[_ch]               for _ch in _chs)
            collinear_groups[_base] = [_base] + _chs   # 帰属再配分用
            merged_chs.update(_chs)
            n_merged += len(_chs)
            log(f'    {_chs} → {_base}')
    else:
        log('  デバイス分割なし（または共線性なし）')

    # ── Steps 4–7: モデル訓練 ────────────────────────────────
    # When Prophet is active, its yearly seasonality already explains major seasonal patterns.
    # Limit dummies to specific event days only (avoid double-counting seasonality with dummies).
    effective_max_dummies = max_dummies
    if _prophet_active and max_dummies > 10:
        effective_max_dummies = 10
        log(f'  Prophet有効: ダミー変数上限を{max_dummies}→{effective_max_dummies}本に自動調整（季節性の二重計上を防止）')

    # lambda_profile は組み合わせループで個別に渡すため common_args から除外
    common_args = dict(
        costs_train=costs_train_m, controls_train=controls_train,
        controls_hold=controls_hold,
        y_train=y_train, y_hold=y_hold, holdout_days=holdout_days,
        cv_uu_train=cv_uu[:n_train], dates=dates, dates_train=dates_train,
        costs=costs, n_trials=n_trials, n_jobs=n_jobs,
        holdout_weight=holdout_weight, seed=seed, top_k_pareto=top_k_pareto,
        max_dummies=effective_max_dummies, target_r2=target_r2,
        freq=freq, cv_col=cv_col,
    )

    # ── 2次元グリッドサーチ: media_basis × lambda_profile ────────
    bases_to_try    = ['media', 'spend'] if media_basis    == 'auto' else [media_basis]
    profiles_to_try = list(_LAMBDA_PROFILES.keys())        if lambda_profile == 'auto' else [lambda_profile]
    combinations    = [(b, p) for b in bases_to_try for p in profiles_to_try]

    n_combos = len(combinations)
    if n_combos > 1:
        log(f'Steps 4–7: [auto] {n_combos}パターンを訓練して最良モデルを自動選択...')
    else:
        b0, p0 = combinations[0]
        log(f'Steps 4–7: [{b0}ベース / {p0}プロファイル固定]')

    all_combo_results = {}
    for basis, profile in combinations:
        media_m = media_train_m if basis == 'media' else costs_train_m
        media_h = media_hold_m  if basis == 'media' else costs_hold_m
        label   = f' [{basis}/{profile}]'
        m, n_d  = _train_model(media_m, media_h, lambda_profile=profile, label=label, **common_args)
        all_combo_results[(basis, profile)] = (m, n_d)

    # NRMSE_hold 最小を選択
    best_key = min(all_combo_results, key=lambda k: all_combo_results[k][0]['nrmse_hold'])
    selected_basis, selected_profile = best_key
    final_metrics, n_dummies = all_combo_results[best_key]

    if n_combos > 1:
        score_summary = ' / '.join(
            f'{b}/{p}={all_combo_results[(b,p)][0]["nrmse_hold"]:.4f}'
            for b, p in combinations
        )
        log(f'  → {selected_basis}/{selected_profile} を採用 (NRMSE_hold: {score_summary})')

    final_metrics['auto_selection'] = {
        'selected_basis':   selected_basis,
        'selected_profile': selected_profile,
        'combo_scores':     {f'{b}/{p}': all_combo_results[(b,p)][0]['nrmse_hold'] for b, p in combinations},
    } if n_combos > 1 else None

    # ── Step 3.5 後処理: 統合チャネルの帰属再配分 ──────────────
    if n_merged > 0:
        final_metrics['channel_metrics'] = redistribute_collinear_attribution(
            final_metrics['channel_metrics'], collinear_groups, costs
        )
        # channels リストを元の全チャネル順序に復元
        final_metrics['channels'] = list(media_train.keys())
        final_metrics['n_valid']  = sum(
            1 for ch in final_metrics['channels']
            if not final_metrics['channel_metrics'].get(ch, {}).get('is_zero', True)
        )

    # ── Step 7.4: スパース除外チャネルを final_metrics に追加 ────
    # モデルに投入しなかったチャネルを is_zero=True で再挿入し、
    # 有効チャネル数・channels リストを全チャネル対象に更新する。
    if _sparse_reasons:
        _total_cost_all = sum(v.sum() for v in costs.values()) or 1.0
        _orig_ch_order  = list(media.keys())
        for _ch, _rsn in _sparse_reasons.items():
            if _ch in final_metrics['channel_metrics']:
                continue
            _ch_spend = float(costs.get(_ch, np.zeros(n_days)).sum())
            final_metrics['channel_metrics'][_ch] = {
                'lambda': 0.0, 'alpha': 0.0, 'gamma': 0.0,
                'coef': 0.0, 'is_zero': True, 'is_sparse': True,
                'zero_reason': _rsn,
                'cv_contrib': 0.0, 'spend': _ch_spend,
                'spend_man': _ch_spend / 10000,
                'cpa': None, 'roi': 0.0,
                'roi_ci_low': 0.0, 'roi_ci_high': 0.0,
                'cpa_ci_low': None, 'cpa_ci_high': None,
                'ci_available': False,
                'contrib_share': 0.0,
                'spend_share': _ch_spend / _total_cost_all,
                'curve_data': None,
                'marginal_roi': 0.0,
                'saturation_score': 0.0,
                'saturation_label': '係数ゼロ',
            }
        _all_chs = sorted(
            set(final_metrics['channels']) | set(_sparse_reasons.keys()),
            key=lambda c: _orig_ch_order.index(c) if c in _orig_ch_order else len(_orig_ch_order)
        )
        final_metrics['channels'] = _all_chs
        final_metrics['n_valid']  = sum(
            1 for c in _all_chs
            if not final_metrics['channel_metrics'].get(c, {}).get('is_zero', True)
        )

    # ── Step 7.5: ゼロ帰属チャネル理由分類 ─────────────────────
    # is_zero=True のチャネルに zero_reason を付与する（4分類）。
    # レポートの「CV効果が確認できないチャネルです」コメントを理由付きに更新。
    for _ch in final_metrics.get('channels', []):
        _cm = final_metrics['channel_metrics'].get(_ch, {})
        if not _cm.get('is_zero', False):
            continue
        # 1. スパース（稼働率 < 5% または絶対数不足）
        if _ch in _sparse_reasons:
            _cm['zero_reason'] = _sparse_reasons[_ch]
            continue
        # 2. デバイス統合による吸収（is_merged が立っている）
        if _cm.get('is_merged') and _cm.get('merged_into'):
            _rep = _cm['merged_into']
            _cm['zero_reason'] = f'{_rep}との共線性が見られるため、CV効果を推定できないチャネルです'
            continue
        # 3. 軟性共線性（有効チャネルとの r ≥ 0.70）
        _ch_arr   = costs.get(_ch, np.zeros(n_days))
        _best_r   = 0.0
        _best_ch  = None
        for _oth in final_metrics.get('channels', []):
            if _oth == _ch or final_metrics['channel_metrics'].get(_oth, {}).get('is_zero'):
                continue
            _oth_arr = costs.get(_oth, np.zeros(n_days))
            if np.std(_ch_arr) > 0 and np.std(_oth_arr) > 0:
                _r = float(np.corrcoef(_ch_arr, _oth_arr)[0, 1])
                if _r > _best_r:
                    _best_r, _best_ch = _r, _oth
        if _best_ch and _best_r >= _SOFT_COLLINEAR_THRESH:
            _cm['zero_reason'] = f'{_best_ch}との共線性が見られるため、CV効果を推定できないチャネルです'
            continue
        # 4. 低スペンド
        if costs.get(_ch, np.zeros(n_days)).sum() < 10_000:
            _cm['zero_reason'] = '支出金額が小さく、CV効果を推定できないチャネルです'
            continue
        # 5. 純粋ゼロ推定（デフォルト）
        _cm['zero_reason'] = 'CV効果が確認できないチャネルです'

    # ── Summary ─────────────────────────────────────────────
    _r2     = final_metrics['r2']
    _r2_pct = _r2 * 100
    _r2_note = (
        '精度は高い水準です' if _r2 >= 0.85 else
        'データ追加で更なる向上が見込めます' if _r2 >= 0.70 else
        'チャネル数・データ量が少ない場合は低めになります'
    )
    log('\n' + '='*50)
    log(f'  モデル基準    : {selected_basis} / λプロファイル: {selected_profile}')
    log(f'  モデル説明率  : 売上変動の{_r2_pct:.0f}%を説明（残り{100-_r2_pct:.0f}%はベースライン・測定外要因）')
    log(f'                  {_r2_note}  R²={_r2:.4f}')
    log(f'  NRMSE(train) : {final_metrics["nrmse"]:.4f}')
    log(f'  NRMSE(hold)  : {final_metrics["nrmse_hold"]:.4f}')
    log(f'  RSSD         : {final_metrics["rssd"]:.4f}')
    log(f'  MAPE         : {final_metrics["mape"]*100:.1f}%')
    log(f'  有効チャネル : {final_metrics["n_valid"]}/{len(media)}')
    log(f'  媒体帰属比率 : {final_metrics.get("media_fraction", 0)*100:.1f}% (ベースライン {final_metrics.get("baseline_fraction", 0)*100:.1f}%)')
    log(f'  ダミー変数   : {n_dummies}本')
    log('='*50)

    log('\nチャネル別結果:')
    for ch in final_metrics['channels']:
        cm = final_metrics['channel_metrics'].get(ch, {})
        cpa_s  = f'¥{cm["cpa"]:,.0f}' if cm.get('cpa') else 'N/A'
        roi_pt = cm.get('roi', 0)
        # CI表示
        if cm.get('ci_available') and not cm.get('is_zero') and roi_pt > 0:
            roi_lo = cm.get('roi_ci_low', roi_pt)
            roi_hi = cm.get('roi_ci_high', roi_pt)
            roi_s  = f'{roi_pt:.2f} [{roi_lo:.2f}〜{roi_hi:.2f}]'
        else:
            roi_s  = f'{roi_pt:.2f}'
        if cm.get('is_merged'):
            status = f'統合→{cm["merged_into"]}'
        elif cm.get('is_zero'):
            status = 'ゼロ⚠'
        else:
            status = '有効'
        log(f'  {ch:<20} CPA={cpa_s:<12} ROI={roi_s:<22} '
            f'λ={cm.get("lambda", 0):.3f} α={cm.get("alpha", 0):.3f} γ={cm.get("gamma", 0):.3f} '
            f'{status}')

    # ── Step 8: Budget optimization ────────────────────────
    # 有効チャネルの訓練期間支出をベースにする（スライドの「広告費合計」と一致させる）
    total_budget = float(final_metrics['total_spend'])
    log(f'\nStep 8: 予算最適化（シナリオA: 同予算再配分 / constr×{constr_low}〜×{constr_up}）...')
    opt_result = budget_optimization(
        final_metrics['channel_metrics'],
        total_budget=total_budget,
        constr_low=constr_low,
        constr_up=constr_up,
    )
    log(f'  現状CV: {opt_result["current_cv"]:.0f}件 → 最適CV: {opt_result["optimal_cv"]:.0f}件 (+{opt_result["cv_lift_pct"]:.1f}%)')

    log(f'\nStep 8b: 予算最適化（シナリオB: +{budget_increase*100:.0f}%増額）...')
    opt_result_b = budget_increase_scenario(
        final_metrics['channel_metrics'],
        current_budget=total_budget,
        increase_pct=budget_increase,
        constr_low=constr_low,
        constr_up=constr_up,
    )
    log(f'  +{budget_increase*100:.0f}%増額時: CV={opt_result_b["optimal_cv"]:.0f}件 (+{opt_result_b["cv_lift_pct"]:.1f}%)')

    log(f'\nStep 8b-2: 予算最適化（シナリオC: -{budget_increase*100:.0f}%減額）...')
    opt_result_dec = budget_decrease_scenario(
        final_metrics['channel_metrics'],
        current_budget=total_budget,
        decrease_pct=budget_increase,
        constr_low=0.0,
        constr_up=constr_up,
    )
    log(f'  -{budget_increase*100:.0f}%減額時: CV={opt_result_dec["optimal_cv"]:.0f}件 (+{opt_result_dec["cv_lift_pct"]:.1f}%)')

    log('\nStep 8c: 投資効率フロンティア計算（現状〜×2.0予算で20ステップ）...')
    _cv_metric_type = final_metrics.get('cv_metric_type', 'count')
    frontier = efficient_budget_frontier(
        final_metrics['channel_metrics'],
        current_budget=total_budget,
        max_cpa=max_cpa,
        constr_low=constr_low,
        constr_up=constr_up,
        cv_metric_type=_cv_metric_type,
    )
    max_eff = frontier['max_efficient_budget']
    if _cv_metric_type == 'monetary':
        log(f'  理論最大効率予算: ¥{max_eff/10000:.0f}万 (現状比 +{(max_eff/total_budget - 1)*100:.0f}% / 閾値ROI {frontier["threshold_roi"]:.2f})')
    else:
        log(f'  理論最大効率予算: ¥{max_eff/10000:.0f}万 (現状比 +{(max_eff/total_budget - 1)*100:.0f}% / 閾値CPA ¥{frontier["threshold_cpa"]:,.0f})')

    # ── Step 9: Generate PPTX ─────────────────────────────
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    client_slug  = client_name.replace('株式会社', '').replace(' ', '_').replace('　', '_')
    basis_tag    = f'auto-{selected_basis}' if media_basis == 'auto' else selected_basis
    type_tag     = '-simple' if report_type == 'simple' else ''
    client_dir   = os.path.join(output_dir, client_slug)
    report_dir   = os.path.join(client_dir, 'report')
    chart_dir    = os.path.join(client_dir, 'chart')
    os.makedirs(report_dir, exist_ok=True)
    output_path  = os.path.join(report_dir, f'MMM_{client_slug}_{ts}_{basis_tag}{type_tag}.pptx')
    _charts_dir  = chart_dir if export_charts_dir is not None else None
    if _charts_dir:
        os.makedirs(_charts_dir, exist_ok=True)

    log(f'\nStep 9: PPTXレポート生成中... [{"簡易版" if report_type == "simple" else "フル版"}]')
    log(f'  出力先: {output_path}')

    generated = generate_report(
        metrics=final_metrics,
        opt_result=opt_result,
        opt_result_b=opt_result_b,
        opt_result_dec=opt_result_dec,
        frontier=frontier,
        client_name=client_name,
        model_name='NNLS',
        output_path=output_path,
        cv_col=cv_col,
        media_basis=selected_basis,
        freq=freq,
        lambda_profile=selected_profile,
        budget_increase_pct=budget_increase,
        report_type=report_type,
        export_charts_dir=_charts_dir,
    )

    # Save report snapshot (for --report-only re-generation)
    pkl_path = os.path.join(client_dir, f'MMM_{client_slug}_{ts}.pkl')
    _report_snapshot = dict(
        metrics=final_metrics,
        opt_result=opt_result,
        opt_result_b=opt_result_b,
        opt_result_dec=opt_result_dec,
        frontier=frontier,
        client_name=client_name,
        cv_col=cv_col,
        media_basis=selected_basis,
        freq=freq,
        lambda_profile=selected_profile,
        budget_increase_pct=budget_increase,
    )
    with open(pkl_path, 'wb') as f:
        pickle.dump(_report_snapshot, f)
    log(f'PKL: {pkl_path}')

    # Save JSON summary
    summary_path = os.path.join(client_dir, f'MMM_{client_slug}_{ts}_summary.json')
    summary = {
        'client': client_name,
        'generated_at': ts,
        'media_basis': selected_basis,
        'media_basis_mode': media_basis,
        'lambda_profile': selected_profile,
        'lambda_profile_mode': lambda_profile,
        'auto_selection': final_metrics.get('auto_selection'),
        'analysis_period_days': n_days,
        'holdout_days': holdout_days,
        'r2': final_metrics['r2'],
        'nrmse_train': final_metrics['nrmse'],
        'nrmse_holdout': final_metrics['nrmse_hold'],
        'rssd': final_metrics['rssd'],
        'mape': final_metrics['mape'],
        'n_valid_channels': final_metrics['n_valid'],
        'n_zero_channels': final_metrics['n_zero'],
        'n_dummies': n_dummies,
        'total_cv': final_metrics['total_cv'],
        'total_spend': final_metrics['total_spend'],
        'cv_lift_pct':    opt_result['cv_lift_pct'],
        'cv_lift_pct_b':  opt_result_b['cv_lift_pct'],
        'budget_increase': budget_increase,
        'max_efficient_budget': frontier['max_efficient_budget'],
        'threshold_cpa':  frontier['threshold_cpa'],
        'channels': {
            ch: {
                'cpa':              cm['cpa'],
                'roi':              cm['roi'],
                'marginal_roi':     cm.get('marginal_roi', 0.0),
                'saturation_score': cm.get('saturation_score', 0.0),
                'saturation_label': cm.get('saturation_label', ''),
                'is_zero':          cm['is_zero'],
                'is_sparse':        cm.get('is_sparse', False),
                'is_inverse':       cm.get('is_inverse', False),
                'spend_man':        cm['spend_man'],
                'cv_contrib':       cm['cv_contrib'],
                'lambda':           cm['lambda'],
                'alpha':            cm['alpha'],
                'gamma':            cm['gamma'],
            }
            for ch, cm in final_metrics['channel_metrics'].items()
        },
    }
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    log(f'\n完了！ 処理時間: {elapsed:.1f}秒')
    log(f'PPTX: {generated}')
    log(f'JSON: {summary_path}')

    return {
        'pptx_path': generated,
        'json_path': summary_path,
        'metrics': final_metrics,
        'opt_result': opt_result,
    }


# ── --init-client: 業種・拠点から外部変数を推奨してYAMLを生成 ──────────────

_PREF_TO_STATION = {
    '北海道': '札幌', '青森県': '青森', '岩手県': '盛岡', '宮城県': '仙台',
    '秋田県': '秋田', '山形県': '山形', '福島県': '福島', '茨城県': '水戸',
    '栃木県': '宇都宮', '群馬県': '前橋', '埼玉県': 'さいたま', '千葉県': '千葉',
    '東京都': '東京', '神奈川県': '横浜', '新潟県': '新潟', '富山県': '富山',
    '石川県': '金沢', '福井県': '福井', '山梨県': '甲府', '長野県': '長野',
    '岐阜県': '岐阜', '静岡県': '静岡', '愛知県': '名古屋', '三重県': '津',
    '滋賀県': '大津', '京都府': '京都', '大阪府': '大阪', '兵庫県': '神戸',
    '奈良県': '奈良', '和歌山県': '和歌山', '鳥取県': '鳥取', '島根県': '松江',
    '岡山県': '岡山', '広島県': '広島', '山口県': '山口', '徳島県': '徳島',
    '香川県': '高松', '愛媛県': '松山', '高知県': '高知', '福岡県': '福岡',
    '佐賀県': '佐賀', '長崎県': '長崎', '熊本県': '熊本', '大分県': '大分',
    '宮崎県': '宮崎', '鹿児島県': '鹿児島', '沖縄県': '那覇',
}
_SNOW_PREFS = {'北海道', '青森', '岩手', '秋田', '山形', '新潟', '富山', '石川', '福井', '長野', '山梨'}

_INDUSTRY_WEATHER_VARS = {
    'EC・通販':        ['temp_anomaly', 'precipitation'],
    '実店舗小売':      ['temp_anomaly', 'precipitation'],
    '飲食・グルメ':    ['temp_anomaly', 'precipitation'],
    'レジャー・旅行':  ['temp_anomaly', 'precipitation'],
    '美容・健康':      ['temp_anomaly'],
    '教育・スクール':  [],
    '不動産・住宅':    [],
    'BtoB SaaS・IT':  [],
    '保険・金融':      [],
    'その他':          [],
}

_EV_SPEC = {
    'temp_anomaly':  {
        'name': 'temp_anomaly', 'col': '平均気温', 'transform': 'seasonal_deviation',
        'note': '気象庁 日別気温(℃) / seasonal_deviationで月別平年比偏差に変換',
    },
    'precipitation': {
        'name': 'precipitation', 'col': '降水量', 'transform': 'log1p',
        'note': '気象庁 日別降水量(mm) / log1pで圧縮',
    },
    'snowfall': {
        'name': 'snowfall', 'col': '積雪量', 'transform': 'log1p',
        'note': '気象庁 日別積雪量(cm) / log1pで圧縮',
    },
    'branded_search_imp': {
        'name': 'branded_search_imp', 'col': '指名検索Imp', 'transform': 'log1p',
        'note': 'GSC → パフォーマンス → クエリフィルタ「ブランド名を含む」でエクスポート / log1pで圧縮',
    },
    'pr_event': {
        'name': 'pr_event', 'col': 'PRフラグ', 'transform': 'none',
        'note': 'PR・メディア掲載があった日=1、それ以外=0 のフラグ列',
    },
}


def _init_client(save_path: str):
    """対話型クライアント初期設定 → YAML生成。"""
    import yaml as _yaml

    SEP = '─' * 52
    print(f'\n{SEP}')
    print('  MMM クライアント初期設定')
    print(SEP)

    client_name = input('\nクライアント名: ').strip() or 'クライアント'

    industries = list(_INDUSTRY_WEATHER_VARS.keys())
    print('\n業種を選択してください:')
    for i, name in enumerate(industries, 1):
        print(f'  {i:2}. {name}')
    while True:
        try:
            idx = int(input('番号: ').strip()) - 1
            if 0 <= idx < len(industries):
                industry = industries[idx]
                weather_vars = list(_INDUSTRY_WEATHER_VARS[industry])
                break
        except ValueError:
            pass
        print('  → 番号を入力してください')

    print('\n主な拠点・商圏の都道府県を入力してください')
    print('  例: 東京都 / 大阪府 / 全国')
    location = input('拠点: ').strip() or '全国'

    if weather_vars and any(p in location for p in _SNOW_PREFS):
        weather_vars.append('snowfall')

    print('\nGoogle サーチコンソール（GSC）にアクセスできますか？')
    print('  → 指名検索ボリュームを外部変数にすると中間変数分析が可能になります')
    gsc = input('  [y/n]: ').strip().lower() == 'y'

    print('\nPR・メディア掲載など広告以外のブランド露出活動はありますか？')
    has_pr = input('  [y/n]: ').strip().lower() == 'y'

    # 外部変数リストを組み立て
    ev_keys = list(weather_vars)
    if gsc:
        ev_keys.append('branded_search_imp')
    if has_pr:
        ev_keys.append('pr_event')

    ev_list = [{k: v for k, v in _EV_SPEC[k].items() if k != 'note'} for k in ev_keys]

    # YAMLコンフィグ生成
    config = {
        'client':   client_name,
        'industry': industry,
        'location': location,
        'date': '',
        'cv':   '',
        'channels': {
            'CHANNEL_1': {'spend': '', 'media': ''},
            'CHANNEL_2': {'spend': '', 'media': ''},
        },
        'controls': [],
    }
    if ev_list:
        config['external_vars'] = ev_list

    dst = Path(save_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        _yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # サマリー表示
    print(f'\n{SEP}')
    print(f'  設定ファイルを生成しました: {dst}')
    print(SEP)
    print(f'  クライアント: {client_name}')
    print(f'  業種:         {industry}')
    print(f'  拠点:         {location}')
    if ev_list:
        print(f'  外部変数 ({len(ev_list)}件):')
        for k, ev in zip(ev_keys, ev_list):
            note = _EV_SPEC[k]['note']
            print(f'    - {ev["name"]} (col="{ev["col"]}", transform={ev["transform"]})')
            print(f'      {note}')
    else:
        print('  外部変数: なし')

    print(f'\n次のステップ:')
    print(f'  1. {dst} を開いて channels / date / cv の列名を入力')
    if weather_vars:
        station = next((v for k, v in _PREF_TO_STATION.items() if k in location), None)
        station_disp = station or '最寄りの観測地点'
        print(f'  2. 気象庁データを取得して Excel に追加:')
        print(f'       https://www.data.jma.go.jp/obd/stats/etrn/index.php')
        print(f'       観測地点: {station_disp} → 日別値 → CSV保存')
    if gsc:
        step = 3 if weather_vars else 2
        print(f'  {step}. GSC → パフォーマンス → クエリフィルタ → ブランド名で絞り込み → CSV出力')
    print(f'\n実行コマンド:')
    print(f'  python run_mmm.py --excel CLIENT_DATA.xlsx --config {dst}')
    print(SEP)


def main():
    parser = argparse.ArgumentParser(description='MMM Auto-Execution Engine')
    parser.add_argument('--excel',       default=None,   help='Excelファイルパス (.xlsm or .xlsx)')
    parser.add_argument('--sheets',      default=None,   help='Google SpreadsheetsのIDまたはURL（サービスアカ認証が必要）')
    parser.add_argument('--client',      default='クライアント', help='クライアント名（レポート表紙に使用）')
    parser.add_argument('--output',      default='./output', help='出力ディレクトリ')
    parser.add_argument('--trials',      type=int,   default=2000,
                        help='パレート探索試行数（本番: 2000 / テスト: 50）')
    parser.add_argument('--holdout',     type=int,   default=None,  help='ホールドアウト日数（省略=自動: 日次14/週次4）')
    parser.add_argument('--dummies',     type=int,   default=32,    help='最大ダミー変数数（デフォルト: 32）')
    parser.add_argument('--target-r2',  type=float, default=0.95,  help='R²目標値（デフォルト: 0.95）')
    parser.add_argument('--ho-weight',  type=float, default=0.3,   help='ホールドアウト重み（デフォルト: 0.3）')
    parser.add_argument('--seed',        type=int,   default=42,    help='乱数シード')
    parser.add_argument('--jobs',        type=int,   default=-1,
                        help='並列数（デフォルト: -1=全コア使用、1=シングル）')
    parser.add_argument('--sheet',       default=None, help='シート名（省略=自動検出）')
    parser.add_argument('--header-row',  type=int,   default=None,  help='ヘッダー行番号（省略=自動検出）')
    parser.add_argument('--detect-only', action='store_true',
                        help='列マッピング確認のみ実行（本番分析はしない）')
    parser.add_argument('--media-basis', default='auto', choices=['auto', 'media', 'spend'],
                        help='モデル基準: auto=NRMSE_holdで自動選択（デフォルト）/ media=広告接触量固定 / spend=支出金額固定')
    parser.add_argument('--budget-increase', type=float, default=0.30,
                        help='シナリオB増額割合（デフォルト: 0.30=+30%%）')
    parser.add_argument('--max-cpa', type=float, default=None,
                        help='フロンティア計算の許容最大CPA（省略時=現状平均CPA×1.5）')
    parser.add_argument('--constr-low', type=float, default=0.5,
                        help='Robyn準拠: チャネル下限倍率（デフォルト: 0.5=50%%まで削減可）')
    parser.add_argument('--constr-up', type=float, default=2.0,
                        help='Robyn準拠: チャネル上限倍率（デフォルト: 2.0=2倍まで増額可）')
    parser.add_argument('--no-prophet', action='store_true',
                        help='Prophetベースライン分解を無効化（デフォルト: 有効）')
    parser.add_argument('--holidays', default=None,
                        help='日本祝日Excelパス（dt_japan_holidays.xlsx形式）。Prophetに祝日効果を追加')
    parser.add_argument('--lambda-profile', default='auto', choices=['auto', 'default', 'industry'],
                        help='λ境界プロファイル: auto=全プロファイル比較して最良選択（デフォルト）/ default=独自設計固定 / industry=Robyn週次相場固定')
    parser.add_argument('--report-only', default=None, metavar='PKL',
                        help='計算済み .pkl からレポートのみ再生成。例: output/MMM_秤_20260623_2248.pkl')
    parser.add_argument('--report-type', default='simple', choices=['full', 'simple'],
                        help='レポート形式: simple=SMB向け簡易版（デフォルト）/ full=フルレポート')
    parser.add_argument('--export-charts', action='store_true',
                        help='簡易レポートのグラフをPNGとして出力する（モック用途等）。output/charts_YYYYMMDD_HHMM/ に保存')
    parser.add_argument('--config',        default=None, metavar='YAML',
                        help='YAMLコンフィグパス。指定時はauto-detectをスキップして設定ファイルの列マッピングを使用。')
    parser.add_argument('--save-config',   default=None, metavar='YAML',
                        help='--detect-only と組み合わせて使用。自動検出結果をYAMLとして保存。例: --save-config output/corder.yaml')
    parser.add_argument('--init-template', default=None, metavar='TEMPLATE',
                        help='テンプレートYAMLを --save-config パスにコピーして初期設定を開始。'
                             '現在の選択肢: smb（Google+Meta 2チャネル）'
                             '例: --init-template smb --save-config output/client.yaml')
    parser.add_argument('--init-client', default=None, metavar='YAML',
                        help='対話型クライアント初期設定。業種・拠点を入力してexternal_vars入りYAMLを生成。'
                             '例: --init-client output/client.yaml')
    args = parser.parse_args()

    if args.init_client:
        # ── Init-client mode（対話型） ────────────────────────
        _init_client(args.init_client)
        return

    if args.init_template:
        # ── Init-template mode ───────────────────────────────
        _template_map = {
            'smb':              'smb_google_meta.yaml',
            'smb-google-meta':  'smb_google_meta.yaml',
            'smb_google_meta':  'smb_google_meta.yaml',
        }
        tpl_file = _template_map.get(args.init_template.lower())
        if tpl_file is None:
            print(f'エラー: 不明なテンプレート "{args.init_template}"')
            print(f'利用可能: {", ".join(_template_map.keys())}')
            sys.exit(1)
        tpl_src = Path(__file__).parent / 'templates' / tpl_file
        if not tpl_src.exists():
            print(f'エラー: テンプレートファイルが見つかりません: {tpl_src}')
            sys.exit(1)
        if not args.save_config:
            print('エラー: --save-config で出力先YAMLパスを指定してください。')
            print(f'例: --init-template {args.init_template} --save-config output/client.yaml')
            sys.exit(1)
        dst = Path(args.save_config)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(tpl_src.read_text(encoding='utf-8'), encoding='utf-8')
        print(f'\nテンプレートを作成しました: {dst}')
        print('─' * 60)
        print('次のステップ:')
        print(f'  1. {dst} を開いて列名を入力')
        print(f'     - date / cv / channels（spend・media）/ controls')
        print(f'  2. 列マッピングを確認:')
        print(f'     python run_mmm.py --excel CLIENT.xlsx --config {dst} --detect-only')
        print(f'  3. 本番実行:')
        print(f'     python run_mmm.py --excel CLIENT.xlsx --client CLIENT_NAME --config {dst}')
        print('─' * 60)

    elif args.report_only:
        # ── Report-only mode ─────────────────────────────────
        pkl_path = args.report_only
        if not os.path.exists(pkl_path):
            print(f'エラー: ファイルが見つかりません: {pkl_path}')
            sys.exit(1)
        print(f'[report-only] {pkl_path} からレポートを再生成します...')
        with open(pkl_path, 'rb') as f:
            snap = pickle.load(f)
        ts          = datetime.now().strftime('%Y%m%d_%H%M')
        base_dir    = str(Path(pkl_path).parent)
        client_slug = snap['client_name'].replace('株式会社', '').replace(' ', '_').replace('　', '_')
        basis_tag   = snap['media_basis']
        type_tag    = '-simple' if args.report_type == 'simple' else ''
        report_dir  = os.path.join(base_dir, 'report')
        chart_dir   = os.path.join(base_dir, 'chart')
        os.makedirs(report_dir, exist_ok=True)
        output_path = os.path.join(report_dir, f'MMM_{client_slug}_{ts}_{basis_tag}_report{type_tag}.pptx')
        if args.export_charts:
            os.makedirs(chart_dir, exist_ok=True)
        charts_dir  = chart_dir if args.export_charts else None
        generated   = generate_report(
            metrics=snap['metrics'],
            opt_result=snap['opt_result'],
            opt_result_b=snap.get('opt_result_b'),
            opt_result_dec=snap.get('opt_result_dec'),
            frontier=snap.get('frontier'),
            client_name=snap['client_name'],
            model_name='NNLS',
            output_path=output_path,
            cv_col=snap['cv_col'],
            media_basis=snap['media_basis'],
            freq=snap['freq'],
            lambda_profile=snap['lambda_profile'],
            budget_increase_pct=snap['budget_increase_pct'],
            report_type=args.report_type,
            export_charts_dir=charts_dir,
        )
        print(f'完了: {generated}')

    elif args.detect_only:
        # ── Detect-only mode ────────────────────────────────
        print('\n=== 列マッピング自動検出（--detect-only）===\n')
        if args.sheets:
            result = detect_only_from_sheets(args.sheets, sheet_name=args.sheet)
            print(f'シート: {result["sheet_name"]}')
        else:
            result = detect_only(
                excel_path=args.excel,
                sheet_name=args.sheet,
                header_row=args.header_row,
            )
            print(f'シート: {result["sheet_name"]}  ヘッダー行: {result["header_row"]}行目')
        print(f'データ行数: {result["n_rows"]}行  頻度推定: {result["freq_guess"]}')
        print()
        print(result['table'])
        if args.save_config:
            save_mapping_yaml(result['mapping'], args.save_config, client=args.client)
            print(f'\nYAML保存完了: {args.save_config}')
            print('必要に応じてYAMLを編集し、--config で本番実行してください。')
            print(f'例: python run_mmm.py --excel {args.excel} --client {args.client} --config {args.save_config}')
        else:
            print('\n確認後、--detect-only を外して本番実行してください。')
            print('YAMLコンフィグで列マッピングを固定する場合: --save-config output/config.yaml を追加してください。')
    else:
        if not args.excel and not args.sheets:
            parser.error('--excel か --sheets のどちらかを指定してください。レポート再生成は --report-only を使用してください。')
        run(
            excel_path=args.excel,
            sheets_id=args.sheets,
            client_name=args.client,
            output_dir=args.output,
            n_trials=args.trials,
            n_jobs=args.jobs,
            holdout_days=args.holdout,
            max_dummies=args.dummies,
            target_r2=args.target_r2,
            holdout_weight=args.ho_weight,
            seed=args.seed,
            sheet_name=args.sheet,
            header_row=args.header_row,
            media_basis=args.media_basis,
            budget_increase=args.budget_increase,
            max_cpa=args.max_cpa,
            constr_low=args.constr_low,
            constr_up=args.constr_up,
            use_prophet=not args.no_prophet,
            holiday_path=args.holidays,
            lambda_profile=args.lambda_profile,
            report_type=args.report_type,
            export_charts_dir=True if args.export_charts else None,
            config_path=args.config,
        )


if __name__ == '__main__':
    main()
