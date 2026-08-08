# -*- coding: utf-8 -*-
"""NNLS vs BayesianRidge 比較スクリプト
PKLファイルから最適Adstock/Hillパラメータを読み込み、
同一条件でNNLS・BayesianRidgeを再フィットして係数・精度を比較する。
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pickle
import numpy as np
from pathlib import Path
from sklearn.linear_model import BayesianRidge
from sklearn.preprocessing import StandardScaler
from scipy.optimize import minimize

# ── パス設定 ────────────────────────────────────────────
PKL_PATH = Path(__file__).parent / 'output/data_v2/MMM_data_v2_20260728_2312.pkl'


def apply_adstock(x, lam):
    y = np.zeros_like(x, dtype=float)
    for i in range(len(x)):
        y[i] = x[i] + (y[i-1] * lam if i > 0 else 0.0)
    return y


def apply_hill(x, alpha, gamma):
    xm = np.percentile(x[x > 0], 50) if np.any(x > 0) else 1.0
    xn = x / xm
    return xn**alpha / (xn**alpha + gamma**alpha)


class NNRidgeModel:
    def __init__(self, alpha=1.0):
        self.alpha = float(alpha)
        self.coef_ = None
        self.intercept_ = 0.0

    def fit(self, X, y):
        n_feat = X.shape[1]
        def obj(params):
            beta, intercept = params[:n_feat], params[n_feat]
            r = y - (X @ beta + intercept)
            return float(r @ r + self.alpha * (beta @ beta))
        def jac(params):
            beta, intercept = params[:n_feat], params[n_feat]
            r = y - (X @ beta + intercept)
            return np.append(-2.0*(X.T @ r) + 2.0*self.alpha*beta, -2.0*r.sum())
        bounds = [(0.0, None)] * n_feat + [(None, None)]
        res = minimize(obj, np.zeros(n_feat+1), jac=jac, bounds=bounds,
                       method='L-BFGS-B', options={'maxiter':500,'ftol':1e-10})
        self.coef_ = res.x[:n_feat]
        self.intercept_ = float(res.x[n_feat])
        return self

    def predict(self, X):
        return X @ self.coef_ + self.intercept_


def build_X_from_channel_metrics(channel_metrics, raw_media, costs, n_days):
    """channel_metricsのλ/α/γを使ってX行列を構築（スパース除外チャネルを除く）"""
    cols = []
    ch_names = []
    for ch, cm in channel_metrics.items():
        if cm.get('is_zero') and cm.get('is_sparse'):
            continue
        if ch not in raw_media:
            continue
        arr = raw_media[ch].copy()
        lam = cm.get('lambda', 0.0)
        alpha = cm.get('alpha', 1.0)
        gamma = cm.get('gamma', 0.5)
        arr = apply_adstock(arr, lam)
        arr = apply_hill(arr, alpha, gamma)
        cols.append(arr)
        ch_names.append(ch)
    return np.column_stack(cols) if cols else np.zeros((n_days, 0)), ch_names


def r2_score(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred)**2)
    ss_tot = np.sum((y_true - y_true.mean())**2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else 0.0


def nrmse(y_true, y_pred):
    rng = y_true.max() - y_true.min()
    return np.sqrt(np.mean((y_true - y_pred)**2)) / rng if rng > 0 else 0.0


def main():
    print(f'\n読み込み中: {PKL_PATH}')
    with open(PKL_PATH, 'rb') as f:
        snap = pickle.load(f)

    metrics = snap['metrics']
    channels = metrics['channels']
    ch_metrics = metrics['channel_metrics']

    # コントロール変数を取得できないのでXのみ（媒体変数）で比較
    # raw_dfがあればそちらを使う
    raw_df = metrics.get('raw_df')
    if raw_df is None:
        print('raw_dfがPKLに含まれていません。data_loaderから直接再読み込みします...')
        sys.path.insert(0, str(Path(__file__).parent))
        from src.data_loader import load_from_sheets, load_mapping_yaml
        mapping_override = load_mapping_yaml('output/data_v2_config.yaml')
        data = load_from_sheets(
            '1shipMVitji-Na0WUJ9heAOVMgxfZL_VTQF6jz6r-BBw',
            sheet_name='data_v2',
            mapping_override=mapping_override,
            verbose=False,
        )
        raw_df = data['raw_df']
        raw_media = data['media']
        raw_costs = data['costs']
        n_days = data['n_days']
        cv_uu = data['cv_uu']
    else:
        # PKLからメディア・コストを復元するのは難しいため直接再読み込み
        sys.path.insert(0, str(Path(__file__).parent))
        from src.data_loader import load_from_sheets, load_mapping_yaml
        mapping_override = load_mapping_yaml('output/data_v2_config.yaml')
        data = load_from_sheets(
            '1shipMVitji-Na0WUJ9heAOVMgxfZL_VTQF6jz6r-BBw',
            sheet_name='data_v2',
            mapping_override=mapping_override,
            verbose=False,
        )
        raw_media = data['media']
        raw_costs = data['costs']
        n_days = data['n_days']
        cv_uu = data['cv_uu']

    # インプレッションチャネルはスペンド代替
    import numpy as _np
    _ch_map = data.get('mapping', {}).get('channel_map', {})
    for ch in list(raw_media.keys()):
        orig_col = _ch_map.get(ch, {}).get('media', '')
        cost_arr = raw_costs.get(ch, _np.zeros(n_days))
        if 'imp' in str(orig_col).lower() and _np.any(cost_arr > 0):
            raw_media[ch] = cost_arr.copy()

    y_sqrt = np.sqrt(np.maximum(cv_uu, 0))
    holdout = 14
    n_train = n_days - holdout

    y_tr = y_sqrt[:n_train]
    y_ho = y_sqrt[n_train:]

    # 最適パラメータでX行列構築（NNLSのchannel_metricsから）
    # is_zero=TrueでかつNNLSによるゼロ（スパースでない）チャネルは含める
    ch_list = [ch for ch in channels
               if ch in raw_media and not ch_metrics.get(ch, {}).get('is_sparse')]

    X_cols_tr, X_cols_ho = [], []
    ch_included = []
    for ch in ch_list:
        cm = ch_metrics.get(ch, {})
        arr = raw_media[ch].copy()
        lam = cm.get('lambda', 0.0)
        alpha = cm.get('alpha', 1.0)
        gamma = cm.get('gamma', 0.5)
        arr_ads = apply_adstock(arr, lam)
        arr_hill = apply_hill(arr_ads, alpha, gamma)
        X_cols_tr.append(arr_hill[:n_train])
        X_cols_ho.append(arr_hill[n_train:])
        ch_included.append(ch)

    X_tr_raw = np.column_stack(X_cols_tr) if X_cols_tr else np.zeros((n_train, 0))
    X_ho_raw = np.column_stack(X_cols_ho) if X_cols_ho else np.zeros((holdout, 0))

    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_tr_raw)
    X_ho = scaler.transform(X_ho_raw)

    print(f'\n比較対象チャネル ({len(ch_included)}件): {ch_included}')
    print(f'Train: {n_train}日 / Hold-out: {holdout}日')
    print()

    # ── NNLS ────────────────────────────────────────────
    nn = NNRidgeModel(alpha=1.0)
    nn.fit(X_tr, y_tr)
    pred_tr_nn = nn.predict(X_tr)
    pred_ho_nn = nn.predict(X_ho)

    # 非スケール係数
    coef_nn = nn.coef_ / scaler.scale_

    # ── BayesianRidge ────────────────────────────────────
    br = BayesianRidge(max_iter=1000, tol=1e-6)
    br.fit(X_tr, y_tr)
    pred_tr_br = br.predict(X_tr)
    pred_ho_br = br.predict(X_ho)

    # 非スケール係数
    coef_br = br.coef_ / scaler.scale_

    # ── 結果表示 ─────────────────────────────────────────
    print('='*72)
    print('  NNLS vs BayesianRidge 比較結果')
    print('  ※ 同一Adstock/Hillパラメータ（NNLSで最適化）で再フィット')
    print('='*72)
    print()

    print('【精度比較】')
    print(f'  {"指標":<16}  {"NNLS":>10}  {"BayesianRidge":>14}')
    print(f'  {"-"*45}')
    print(f'  {"R²(train)":<16}  {r2_score(y_tr, pred_tr_nn):>10.4f}  {r2_score(y_tr, pred_tr_br):>14.4f}')
    print(f'  {"NRMSE(train)":<16}  {nrmse(y_tr, pred_tr_nn):>10.4f}  {nrmse(y_tr, pred_tr_br):>14.4f}')
    print(f'  {"NRMSE(hold)":<16}  {nrmse(y_ho, pred_ho_nn):>10.4f}  {nrmse(y_ho, pred_ho_br):>14.4f}')
    print()

    print('【係数比較（非スケール）】')
    print(f'  {"チャネル":<20}  {"NNLS coef":>11}  {"BR coef":>11}  {"差分":>11}  {"NNLSゼロ制約"}')
    print(f'  {"-"*70}')
    for i, ch in enumerate(ch_included):
        nn_c = coef_nn[i]
        br_c = coef_br[i]
        diff = nn_c - br_c
        zero_flag = '*負→ゼロ' if br_c < 0 and nn_c == 0 else ('NNLSゼロ' if nn_c == 0 else '')
        print(f'  {ch:<20}  {nn_c:>11.6f}  {br_c:>11.6f}  {diff:>11.6f}  {zero_flag}')

    neg_br = sum(1 for c in coef_br if c < 0)
    zero_nn = sum(1 for c in coef_nn if c == 0)
    print()
    print(f'  BayesianRidgeの負の係数: {neg_br}件')
    print(f'  NNLSでゼロになった係数: {zero_nn}件')

    # ── 信頼区間幅比較 ───────────────────────────────────
    if hasattr(br, 'sigma_'):
        se_br = np.sqrt(np.maximum(np.diag(br.sigma_[:len(ch_included), :len(ch_included)]), 0)) / scaler.scale_
        ci_width_br = 1.96 * 2 * se_br
        print()
        print('【CI幅比較（BayesianRidge posterior vs NNLS bootstrap）】')
        print(f'  {"チャネル":<20}  {"BR CI幅":>12}  {"注記"}')
        print(f'  {"-"*50}')
        for i, ch in enumerate(ch_included):
            print(f'  {ch:<20}  {ci_width_br[i]:>12.6f}')

    print()
    print('='*72)
    print('比較完了')


if __name__ == '__main__':
    main()
