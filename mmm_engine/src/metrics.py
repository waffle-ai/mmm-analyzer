# -*- coding: utf-8 -*-
"""Budget optimization & response curve computation."""
import numpy as np
from .transforms import apply_transforms, hill_transform, adstock_transform


def _cv_at_spend(ch_meta: dict, spend: float) -> float:
    """レスポンスカーブから spend 時の CV 貢献量を推定する。
    x_current に対する spend 比率で curve_data を補間。"""
    cd = ch_meta.get('curve_data') or {}
    cx = cd.get('current_x', 0.0)
    cs = ch_meta.get('spend', 0.0)
    cv_curr = ch_meta.get('cv_contrib', 0.0)
    x_pts = cd.get('x', np.array([]))
    y_pts = cd.get('y', np.array([]))
    if cx <= 0 or cs <= 0 or len(x_pts) == 0:
        return 0.0
    x_new = cx * (max(spend, 0.0) / cs)
    y_curr = float(np.interp(cx,    x_pts, y_pts))
    y_new  = float(np.interp(x_new, x_pts, y_pts))
    if y_curr < 1e-10:
        return 0.0
    return cv_curr * (y_new / y_curr)


def _recommend_action(delta_spend: float, cur_spend: float, is_zero: bool) -> str:
    if is_zero:
        return '停止・効果検証'
    if cur_spend <= 0:
        return '新規投資検討'
    ratio = delta_spend / cur_spend
    if ratio >= 0.20:
        return '増額推奨'
    elif ratio <= -0.20:
        return '削減推奨'
    else:
        return '現状維持'


def budget_optimization(channel_metrics: dict, total_budget: float,
                         constr_low: float = 0.5,
                         constr_up: float  = 2.0) -> dict:
    """レスポンスカーブベースの予算最適化（scipy SLSQP による CV 最大化）。

    Robyn 準拠の per-channel 上下限制約付き:
      constr_low: 現状スペンドの最低維持割合（デフォルト 0.5 = 50%まで削減可）
      constr_up:  現状スペンドの最大増額割合（デフォルト 2.0 = 2倍まで増額可）
    ゼロ係数チャネルは現状の 10% で固定。
    """
    try:
        from scipy.optimize import minimize as _minimize
        _has_scipy = True
    except ImportError:
        _has_scipy = False

    channels = list(channel_metrics.keys())
    valid_chs = [ch for ch in channels
                 if not channel_metrics[ch]['is_zero']
                 and channel_metrics[ch].get('curve_data')
                 and channel_metrics[ch]['spend'] > 0]
    other_chs = [ch for ch in channels if ch not in valid_chs]

    # ゼロ係数チャネルは 10% で固定（予算からあらかじめ確保）
    zero_reserved = sum(channel_metrics[ch]['spend'] * 0.1 for ch in other_chs)
    free_budget = max(total_budget - zero_reserved, 0.0)

    if _has_scipy and len(valid_chs) > 0:
        cur_spends = np.array([channel_metrics[ch]['spend'] for ch in valid_chs])

        # per-channel 上下限（Robyn の channel_constr_low / _up に相当）
        lo = cur_spends * constr_low
        hi = cur_spends * constr_up

        # 合計の下限が free_budget を超える場合は下限を比例縮小して辻褄を合わせる
        lo_sum = lo.sum()
        if lo_sum > free_budget:
            lo = lo * (free_budget / lo_sum)

        def neg_cv(spends):
            return -sum(_cv_at_spend(channel_metrics[ch], float(s))
                        for ch, s in zip(valid_chs, spends))

        bounds_list = list(zip(lo, hi))
        constraint  = {'type': 'eq', 'fun': lambda s: s.sum() - free_budget}
        slsqp_opts  = {'ftol': 1e-9, 'maxiter': 2000}

        # Robyn準拠: 複数スタート点でローカル最適を回避（3点試行）
        starts = []
        # 1) 現状比例配分
        x0_prop = np.clip(
            cur_spends / cur_spends.sum() * free_budget if cur_spends.sum() > 0
            else np.ones(len(valid_chs)) * free_budget / len(valid_chs),
            lo, hi,
        )
        starts.append(x0_prop)
        # 2) 均等配分
        x0_even = np.clip(
            np.ones(len(valid_chs)) * free_budget / len(valid_chs), lo, hi)
        starts.append(x0_even)
        # 3) ROI比例配分（高ROIに寄せた初期値）
        rois = np.array([channel_metrics[ch]['roi'] for ch in valid_chs])
        roi_sum = rois.sum()
        if roi_sum > 0:
            x0_roi = np.clip(rois / roi_sum * free_budget, lo, hi)
            starts.append(x0_roi)

        best_res = None
        for x0 in starts:
            r = _minimize(neg_cv, x0, method='SLSQP',
                          bounds=bounds_list, constraints=constraint,
                          options=slsqp_opts)
            if best_res is None or r.fun < best_res.fun:
                best_res = r

        opt_spends = np.clip(np.maximum(best_res.x, 0.0), lo, hi)
    else:
        # scipy なし: 現状維持
        opt_spends = np.array([channel_metrics[ch]['spend'] for ch in valid_chs],
                               dtype=float)

    opt_metrics = {}
    for ch, os in zip(valid_chs, opt_spends):
        cm = channel_metrics[ch]
        cs = cm['spend']
        cv_opt = _cv_at_spend(cm, float(os))
        opt_metrics[ch] = {
            'current_spend': cs,
            'optimal_spend': float(os),
            'delta_spend':   float(os) - cs,
            'current_cv':    cm['cv_contrib'],
            'optimal_cv':    cv_opt,
            'roi':           cm['roi'],
            'action': _recommend_action(float(os) - cs, cs, False),
        }
    for ch in other_chs:
        cm = channel_metrics[ch]
        cs = cm['spend']
        os = cs * 0.1
        opt_metrics[ch] = {
            'current_spend': cs,
            'optimal_spend': os,
            'delta_spend':   os - cs,
            'current_cv':    cm['cv_contrib'],
            'optimal_cv':    0.0,
            'roi':           0.0,
            'action': _recommend_action(os - cs, cs, cm['is_zero']),
        }

    current_total_cv = sum(channel_metrics[ch]['cv_contrib'] for ch in channels)
    opt_total_cv     = sum(opt_metrics[ch]['optimal_cv'] for ch in channels)
    cv_lift_pct = (opt_total_cv - current_total_cv) / max(current_total_cv, 1.0) * 100

    return {
        'channel_opt':  opt_metrics,
        'total_budget': total_budget,
        'current_cv':   current_total_cv,
        'optimal_cv':   opt_total_cv,
        'cv_lift_pct':  cv_lift_pct,
    }


def budget_increase_scenario(channel_metrics: dict, current_budget: float,
                              increase_pct: float = 0.30,
                              constr_low: float = 0.5,
                              constr_up: float  = 2.0) -> dict:
    """現状予算に increase_pct 増額した場合の最適配分を計算。"""
    new_budget = current_budget * (1.0 + increase_pct)
    # 増額分だけ上限を緩和: 増額比率に合わせて constr_up をスケール
    effective_up = constr_up * (1.0 + increase_pct)
    result = budget_optimization(channel_metrics, new_budget,
                                  constr_low=constr_low, constr_up=effective_up)
    result['increase_pct'] = increase_pct
    result['base_budget']  = current_budget
    return result


def budget_decrease_scenario(channel_metrics: dict, current_budget: float,
                              decrease_pct: float = 0.20,
                              constr_low: float = 0.0,
                              constr_up: float  = 2.0) -> dict:
    """現状予算を decrease_pct 減額した場合の最適配分を計算。
    constr_low=0.0 でチャネルの完全停止を許容し、非効率チャネルを先に削減する。
    """
    new_budget = current_budget * (1.0 - decrease_pct)
    result = budget_optimization(channel_metrics, new_budget,
                                  constr_low=constr_low, constr_up=constr_up)
    result['decrease_pct'] = decrease_pct
    result['base_budget']  = current_budget
    return result


def efficient_budget_frontier(channel_metrics: dict, current_budget: float,
                               max_cpa: float = None, n_steps: int = 20,
                               constr_low: float = 0.5,
                               constr_up: float  = 2.0,
                               start_ratio: float = 0.3,
                               cv_metric_type: str = 'count',
                               min_roi: float = None) -> dict:
    """予算を段階的に増やし、限界CPA/ROIが閾値を超えた時点を理論上の最大投下額とする。

    cv_metric_type: 'count'（件数） or 'monetary'（金額）
    max_cpa:        許容最大CPA（count時、省略時は現状平均CPA × 1.5）
    min_roi:        最低限界ROI（monetary時、省略時は1.0 = 損益分岐点）
    n_steps:        start〜×2.0 の間で何段階計算するか
    start_ratio:    開始予算 = current_budget × start_ratio（デフォルト0.3）
    """
    is_monetary = (cv_metric_type == 'monetary')
    base_cv     = sum(m['cv_contrib'] for m in channel_metrics.values())

    if is_monetary:
        base_roi      = base_cv / max(current_budget, 1.0)
        threshold_roi = min_roi if min_roi else max(base_roi * 0.5, 1.0)
        threshold_cpa = None
    else:
        base_cpa      = current_budget / max(base_cv, 1.0)
        threshold_cpa = max_cpa if max_cpa else base_cpa * 1.5
        threshold_roi = None

    start_budget = current_budget * start_ratio
    budgets      = np.linspace(start_budget, current_budget * 2.0, n_steps + 1)
    step_size    = float(budgets[1] - budgets[0])

    curve   = []
    prev_cv = None

    for i, budget in enumerate(budgets):
        ratio        = float(budget) / current_budget
        effective_up = constr_up * ratio
        opt    = budget_optimization(channel_metrics, float(budget),
                                      constr_low=constr_low, constr_up=effective_up)
        cv_val = opt['optimal_cv']

        if i == 0:
            if is_monetary:
                marginal_roi = cv_val / max(float(budget), 1.0)
                marginal_cpa = -1.0
                is_efficient = True
            else:
                marginal_cpa = float(budget) / max(cv_val, 0.01)
                marginal_roi = -1.0
                is_efficient = True
        else:
            incr_cv = cv_val - prev_cv
            if is_monetary:
                if incr_cv > 0:
                    marginal_roi = incr_cv / step_size
                else:
                    marginal_roi = -1.0
                marginal_cpa = -1.0
                is_efficient = (marginal_roi > 0) and (marginal_roi >= threshold_roi)
            else:
                if incr_cv > 0.01:
                    marginal_cpa = step_size / incr_cv
                else:
                    marginal_cpa = -1.0
                marginal_roi = -1.0
                is_efficient = (marginal_cpa > 0) and (marginal_cpa <= threshold_cpa)

        curve.append({
            'budget':       float(budget),
            'cv':           float(cv_val),
            'marginal_cpa': marginal_cpa,
            'marginal_roi': marginal_roi,
            'is_efficient': is_efficient,
        })
        prev_cv = cv_val

    # max_efficient_budget: 閾値交差点を中点補間で算出
    _last_eff_idx    = None
    _first_ineff_idx = None
    for i in range(1, len(curve)):
        if curve[i].get('is_efficient', False):
            _last_eff_idx = i
        elif _last_eff_idx is not None:
            if is_monetary and curve[i].get('marginal_roi', -1) < threshold_roi:
                _first_ineff_idx = i
                break
            elif not is_monetary and curve[i].get('marginal_cpa', -1) > threshold_cpa:
                _first_ineff_idx = i
                break

    if _last_eff_idx is not None and _first_ineff_idx is not None:
        j, k  = _last_eff_idx, _first_ineff_idx
        mid_j = (curve[j-1]['budget'] + curve[j]['budget']) / 2
        mid_k = (curve[k-1]['budget'] + curve[k]['budget']) / 2
        if is_monetary:
            mr0, mr1 = curve[j]['marginal_roi'], curve[k]['marginal_roi']
            if mr0 > mr1:
                frac = max(0.0, min(1.0, (mr0 - threshold_roi) / (mr0 - mr1)))
                max_efficient_budget = mid_j + frac * (mid_k - mid_j)
            else:
                max_efficient_budget = curve[j]['budget']
        else:
            mc0, mc1 = curve[j]['marginal_cpa'], curve[k]['marginal_cpa']
            if mc1 > mc0:
                frac = max(0.0, min(1.0, (threshold_cpa - mc0) / (mc1 - mc0)))
                max_efficient_budget = mid_j + frac * (mid_k - mid_j)
            else:
                max_efficient_budget = curve[j]['budget']
    elif _last_eff_idx is not None:
        max_efficient_budget = curve[_last_eff_idx]['budget']
    else:
        max_efficient_budget = float(budgets[0])

    result = {
        'curve':                curve,
        'max_efficient_budget': max_efficient_budget,
        'current_budget':       float(current_budget),
        'cv_metric_type':       cv_metric_type,
    }
    if is_monetary:
        result['threshold_roi'] = float(threshold_roi)
        result['base_roi']      = float(base_roi)
        result['threshold_cpa'] = 0.0  # 後方互換用ダミー
    else:
        result['threshold_cpa'] = float(threshold_cpa)
        result['base_cpa']      = float(base_cv and current_budget / base_cv)
        result['threshold_roi'] = 0.0
    return result


def response_curve(media_arr: np.ndarray, params: dict, coef: float,
                   n_points: int = 100) -> dict:
    """Generate response curve data for one channel."""
    adstocked = adstock_transform(media_arr, params['lambda'])
    non_zero = adstocked[adstocked > 0]
    if len(non_zero) == 0:
        return {'x': np.zeros(n_points), 'y': np.zeros(n_points), 'current_x': 0.0}

    x_max = np.percentile(non_zero, 99) * 1.5
    x_pts = np.linspace(0, x_max, n_points)
    y_pts = hill_transform(x_pts, params['alpha'], params['gamma']) * coef
    current_x = float(np.percentile(adstocked[adstocked > 0], 75)) if (adstocked > 0).any() else 0.0

    return {'x': x_pts, 'y': np.maximum(y_pts, 0), 'current_x': current_x}


def compute_marginal_roi(media_arr: np.ndarray, costs_arr: np.ndarray,
                         params: dict, coef: float,
                         pred_sqrt_mean: float = 1.0) -> float:
    """Marginal ROI = incremental CV per ¥1万 additional spend.

    モデルは sqrt(CV) 空間で動作するため、chain rule により
    dCV/dspend = 2 × sqrt(CV_mean) × d(sqrt(CV))/dspend で CV 単位に換算。
    """
    from .transforms import marginal_roi_hill
    adstocked = adstock_transform(media_arr, params['lambda'])
    cost_total = costs_arr.sum()
    media_total = media_arr.sum()
    if media_total <= 0 or cost_total <= 0:
        return 0.0
    cost_per_unit = cost_total / media_total
    current_adstock = float(adstocked.mean())
    mroi_sqrt = marginal_roi_hill(current_adstock, adstocked, coef,
                                   params['alpha'], params['gamma'],
                                   cost_per_unit, delta_cost=10000.0)
    return mroi_sqrt * 2.0 * max(pred_sqrt_mean, 1e-6)
