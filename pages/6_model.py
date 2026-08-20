# -*- coding: utf-8 -*-
"""Page 6 — モデル精度（精度指標・フォレストプロット・診断）。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import numpy as np

import runner as r

_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_MID     = '#5C9291'
_COL_LIGHT   = '#A2CEBF'
_COL_AMBER   = '#CB8013'

st.title('モデル精度')
st.markdown('<p class="page-lede">MMMモデルが実績値をどれだけ正確に再現しているか確認できます。精度グレードと各指標から、分析結果の信頼性を判断してください。</p>', unsafe_allow_html=True)

if not st.session_state.get('job_info'):
    _recovered = r.find_latest_job(st.session_state.get('own_job_ids', set()))
    if _recovered:
        st.session_state['job_info'] = _recovered
        st.info('前回の分析結果を表示しています。')
    else:
        st.warning('まだ分析が開始されていません。')
        st.page_link('pages/1_アップロード.py', label='← アップロードページへ')
        st.stop()

job_info = st.session_state['job_info']
_is_demo  = job_info.get('demo', False)

if _is_demo:
    summary = r.load_summary(job_info['json_path'])
else:
    status = r.get_job_status(job_info)
    if status['status'] == 'running':
        st.info('分析実行中です。完了後にご確認ください。')
        st.page_link('pages/3_結果.py', label='← ROI・CPA分析ページで進捗を確認')
        st.stop()
    elif status['status'] == 'failed':
        st.error('分析が失敗しました。')
        st.page_link('pages/3_結果.py', label='← ROI・CPA分析ページを確認')
        st.stop()
    summary = r.load_summary(status['json_path'])

channels, _dup_warn = r.dedup_channels(summary.get('channels', {}))
if _dup_warn:
    st.warning('同名の可能性があるチャネルが複数あります。マッピングを確認して再実行してください（' + '、'.join(_dup_warn) + '）。')
_ch_valid    = {ch: v for ch, v in channels.items() if not v.get('is_zero', False)}
_cv_type     = summary.get('cv_metric_type', 'count')
_is_monetary = _cv_type == 'monetary'
_eff_label   = 'ROAS / ROI' if _is_monetary else 'CPA'
_eff_unit    = '%' if _is_monetary else '円/件'

_r2      = summary.get('r2', 0)
_nrmse_t = summary.get('nrmse_train', 0)
_nrmse_h = summary.get('nrmse_holdout', 0)
_mape    = summary.get('mape', 0)
_rssd    = summary.get('rssd', None)
_mcr     = summary.get('media_fraction', 0) * 100   # エンジンのsqrt空間比率（0〜1）→ %変換

def _r2_lbl(v):    return '◎' if v >= 0.90 else '○' if v >= 0.85 else '△' if v >= 0.80 else '×'
def _nrms_lbl(v):  return '◎' if v < 0.10  else '○' if v < 0.12  else '△' if v < 0.15  else '×'
def _nrmsh_lbl(v): return '◎' if v < 0.15  else '○' if v < 0.20  else '△' if v < 0.25  else '×'
def _mape_lbl(v):  return '◎' if v < 0.08  else '○' if v < 0.10  else '△' if v < 0.12  else '×'
def _rssd_lbl(v):
    if v is None: return '?'
    return '◎' if 0.10 <= v <= 0.20 else '○' if v <= 0.30 else '△' if v <= 0.40 else '×'
def _mcr_lbl(v):   return '◎' if v >= 15   else '○' if v >= 8    else '△' if v >= 3    else '×'
def _badge_cls(l): return {'◎': 'b-s', '○': 'b-a', '△': 'b-b', '×': 'b-c'}.get(l, 'b-c')

r2_l  = _r2_lbl(_r2)
nt_l  = _nrms_lbl(_nrmse_t)
nh_l  = _nrmsh_lbl(_nrmse_h)
mp_l  = _mape_lbl(_mape)
rs_l  = _rssd_lbl(_rssd)
mc_l  = _mcr_lbl(_mcr)

# ── モデル精度指標カード ───────────────────────────────────────────────────
st.subheader('精度指標サマリー')

_mcr_str  = f'{_mcr:.1f}%'
_rssd_str = f'{_rssd:.3f}' if _rssd is not None else 'N/A'

st.markdown(f"""<div class="mmm-card-grid" style="margin-bottom:24px;">
  <div class="mmm-card">
    <div class="mmm-card-lbl">説明力<span class="lq">?<span class="lq-tip">R²（決定係数）。成果の何%をモデルが説明できているかを示します。<br>◎ ≥0.90 &nbsp;○ ≥0.85 &nbsp;△ ≥0.80 &nbsp;× それ未満<br><br>1.0に近いほどモデルが実績をよく再現しています。0.85以上が実務の合格ラインです。</span></span></div>
    <div class="mmm-card-badge"><span class="kpi-badge {_badge_cls(r2_l)}">{r2_l}</span></div>
    <div class="mmm-card-val">{_r2:.3f}</div>
  </div>
  <div class="mmm-card">
    <div class="mmm-card-lbl">予測精度<span class="lq">?<span class="lq-tip">NRMSE（学習データ）。モデルが学習データをどれだけ正確に予測できているかを示します。<br>◎ &lt;0.10 &nbsp;○ &lt;0.12 &nbsp;△ &lt;0.15 &nbsp;× それ以上<br><br>学習誤差と検証誤差の差が大きい場合は過学習の可能性があります。</span></span></div>
    <div class="mmm-card-badge"><span class="kpi-badge {_badge_cls(nt_l)}">{nt_l}</span></div>
    <div class="mmm-card-val">{_nrmse_t:.3f}</div>
  </div>
  <div class="mmm-card">
    <div class="mmm-card-lbl">汎化性能<span class="lq">?<span class="lq-tip">NRMSE（ホールドアウト）。未学習データへの予測誤差で汎化性能を示します。<br>◎ &lt;0.15 &nbsp;○ &lt;0.20 &nbsp;△ &lt;0.25 &nbsp;× それ以上<br><br>学習NRMSEと大きく乖離している場合、特定期間への過適合が起きている可能性があります。</span></span></div>
    <div class="mmm-card-badge"><span class="kpi-badge {_badge_cls(nh_l)}">{nh_l}</span></div>
    <div class="mmm-card-val">{_nrmse_h:.3f}</div>
  </div>
  <div class="mmm-card">
    <div class="mmm-card-lbl">配分整合性<span class="lq">?<span class="lq-tip">RSSD。モデルが推定するROI比率と、実際の広告費配分比率の乖離度です。<br>◎ 0.10〜0.20 &nbsp;○ ≤0.30 &nbsp;△ ≤0.40 &nbsp;× それ以外<br><br>低すぎる（&lt;0.10）とチャネル間の差別化が弱く、高すぎると配分とROIが大きく乖離しています。</span></span></div>
    <div class="mmm-card-badge"><span class="kpi-badge {_badge_cls(rs_l)}">{rs_l}</span></div>
    <div class="mmm-card-val">{_rssd_str}</div>
  </div>
  <div class="mmm-card">
    <div class="mmm-card-lbl">媒体帰属率<span class="lq">?<span class="lq-tip lq-tip-left">MCR（Media Contribution Rate）。全成果のうち広告施策が起因する割合（sqrt空間）です。<br>◎ ≥15% &nbsp;○ ≥8% &nbsp;△ ≥3% &nbsp;× それ未満<br><br>低い場合はブランド・自然流入など広告以外の要因が大きく、ROI推定精度に影響します。</span></span></div>
    <div class="mmm-card-badge"><span class="kpi-badge {_badge_cls(mc_l)}">{mc_l}</span></div>
    <div class="mmm-card-val">{_mcr_str}</div>
  </div>
</div>""", unsafe_allow_html=True)

st.divider()

# ── モデル診断 ────────────────────────────────────────────────────────────
st.subheader('モデル診断')

_grade_score = sum([
    3 if r2_l == '◎' else 2 if r2_l == '○' else 1 if r2_l == '△' else 0,
    3 if nt_l == '◎' else 2 if nt_l == '○' else 1 if nt_l == '△' else 0,
    3 if nh_l == '◎' else 2 if nh_l == '○' else 1 if nh_l == '△' else 0,
    2 if rs_l == '◎' else 1 if rs_l == '○' else 0,
])

if _grade_score >= 9:
    _grade, _grade_color, _grade_msg = 'A+', _COL_PRIMARY, '非常に高い精度です。分析結果を本番運用施策に活用できます。'
elif _grade_score >= 7:
    _grade, _grade_color, _grade_msg = 'A',  _COL_GREEN,   '十分な精度です。分析結果を実務判断の参考にできます。'
elif _grade_score >= 4:
    _grade, _grade_color, _grade_msg = 'B',  _COL_AMBER,   'やや低い精度です。傾向把握には使えますが、数値を過信しないでください。'
else:
    _grade, _grade_color, _grade_msg = 'C',  '#999',       '精度が低く、分析結果の信頼性が限定的です。データ品質や期間を見直してください。'

col_g, col_msg = st.columns([1, 4])
with col_g:
    st.markdown(
        f'<div style="background:{_grade_color};color:#fff;border-radius:12px;'
        f'text-align:center;padding:20px 0;font-size:40px;font-weight:800;">{_grade}</div>',
        unsafe_allow_html=True,
    )
with col_msg:
    st.markdown(f'**精度グレード {_grade}** {_grade_msg}')

# 過学習チェック
_overfit_gap = _nrmse_h - _nrmse_t
st.markdown('**過学習チェック**')
if _overfit_gap <= 0.03:
    st.success(f'過学習なし。学習/検証NRMSEの差 {_overfit_gap:.3f}（±0.03以内）')
elif _overfit_gap <= 0.07:
    st.warning(f'軽度の過学習の可能性。学習/検証NRMSEの差 {_overfit_gap:.3f}。特定期間への過適合を確認してください。')
else:
    st.error(f'過学習の疑い。学習/検証NRMSEの差 {_overfit_gap:.3f}（0.07超）。データ期間の延長やダミー変数の見直しを推奨します。')

# 配分整合性（RSSD）チェック
if _rssd is not None:
    st.markdown('**配分整合性（RSSD）**')
    if 0.10 <= _rssd <= 0.20:
        st.success(f'RSSD {_rssd:.3f}（適正範囲 0.10〜0.20）。ROI比率と広告費配分が整合しています。')
    elif _rssd < 0.10:
        st.warning(f'RSSD {_rssd:.3f}（0.10未満）。チャネル間のROI差が均質すぎます。配分の差別化が弱い可能性があります。')
    elif _rssd <= 0.30:
        st.warning(f'RSSD {_rssd:.3f}（0.20〜0.30）。ROI比率と広告費配分にやや乖離があります。解釈には注意が必要です。')
    elif _rssd <= 0.40:
        st.warning(f'RSSD {_rssd:.3f}（0.30〜0.40）。ROI比率と広告費配分の乖離が目立ちます。データを確認してください。')
    else:
        st.error(f'RSSD {_rssd:.3f}（0.40超）。ROI比率と広告費配分の乖離が大きく、モデルの信頼性に課題があります。')

# MAPE診断
st.markdown('**予測誤差（MAPE）**')
if _mape < 0.08:
    st.success(f'MAPE {_mape*100:.1f}%（8%未満）。予測誤差が小さく、安定したモデルです。')
elif _mape < 0.12:
    st.warning(f'MAPE {_mape*100:.1f}%（8〜12%）。許容範囲内ですが、改善余地があります。')
else:
    st.error(f'MAPE {_mape*100:.1f}%（12%以上）。予測誤差が大きく、モデルの見直しを推奨します。')

st.divider()

# ── 実測と予測の比較 ────────────────────────────────────────────────────────
_avp = summary.get('actual_vs_pred', {})
if _avp.get('dates_train'):
    st.subheader('実測と予測の比較')

    _dt_train = pd.to_datetime(_avp['dates_train'])
    _at_train = _avp['actual_train']
    _pd_train = _avp['pred_train']
    _dt_hold  = pd.to_datetime(_avp.get('dates_hold', []))
    _at_hold  = _avp.get('actual_hold', [])
    _pd_hold  = _avp.get('pred_hold', [])
    _cv_col   = 'CV（金額）' if _is_monetary else 'CV'

    fig_avp = go.Figure()
    fig_avp.add_trace(go.Scatter(x=_dt_train, y=_at_train, mode='lines', name='実測',
                                  line=dict(color=_COL_PRIMARY, width=2)))
    fig_avp.add_trace(go.Scatter(x=_dt_train, y=_pd_train, mode='lines', name='予測',
                                  line=dict(color=_COL_AMBER, width=1.6, dash='dash')))
    if len(_dt_hold):
        fig_avp.add_trace(go.Scatter(x=_dt_hold, y=_at_hold, mode='lines', name='実測（検証期間）',
                                      line=dict(color=_COL_GREEN, width=2)))
        fig_avp.add_trace(go.Scatter(x=_dt_hold, y=_pd_hold, mode='lines', name='予測（検証期間）',
                                      line=dict(color=_COL_AMBER, width=1.6, dash='dot')))
        fig_avp.add_vline(x=_dt_hold[0], line_dash='dash', line_color='#999',
                           annotation_text='検証期間', annotation_position='top right')
    fig_avp.update_layout(
        yaxis_title=_cv_col,
        xaxis=dict(gridcolor='#DAEBE5'),
        yaxis=dict(gridcolor='#DAEBE5'),
        height=340,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=10),
    )
    st.plotly_chart(fig_avp, use_container_width=True)

    _dt_all = list(_dt_train) + list(_dt_hold)
    _residuals = np.array(list(_at_train) + list(_at_hold)) - np.array(list(_pd_train) + list(_pd_hold))
    _res_colors = [_COL_PRIMARY if v >= 0 else _COL_AMBER for v in _residuals]

    fig_res = go.Figure(go.Bar(x=_dt_all, y=_residuals, marker_color=_res_colors))
    fig_res.add_hline(y=0, line_color='#999', line_width=1)
    fig_res.update_layout(
        yaxis_title='残差',
        xaxis=dict(gridcolor='#DAEBE5'),
        yaxis=dict(gridcolor='#DAEBE5'),
        height=180,
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=10, b=20),
    )
    st.plotly_chart(fig_res, use_container_width=True)

    _holdout_n = len(_dt_hold)
    st.caption(
        f'モデルが実際の{_cv_col}をどれだけ正確に予測できているかを示します'
        + (f'（右端{_holdout_n}期間は、未学習データによる検証期間）。' if _holdout_n else '。')
    )

    st.divider()

# ── フォレストプロット（ROI/ROAS信頼区間） ────────────────────────────────
st.subheader(f'{_eff_label} 信頼区間（フォレストプロット）')
st.caption(f'各チャネルの{_eff_label}推定値と95%信頼区間。横棒が短いほど推定の確度が高く、0をまたぐ場合は効果が不明確です。')

_ci_data = [
    {
        'ch':      ch,
        'roi':     v.get('roi', 0),
        'ci_low':  v.get('roi_ci_low', None),
        'ci_high': v.get('roi_ci_high', None),
        'avail':   v.get('ci_available', False),
    }
    for ch, v in _ch_valid.items()
]

_has_ci = any(d['avail'] for d in _ci_data)

if _has_ci:
    ci_df = pd.DataFrame(_ci_data).sort_values('roi', ascending=True)

    fig_fp = go.Figure()
    for _, row in ci_df.iterrows():
        color = _COL_PRIMARY if row['roi'] >= 1.0 else _COL_AMBER

        if row['avail'] and row['ci_low'] is not None and row['ci_high'] is not None:
            err_minus = max(0, row['roi'] - row['ci_low'])
            err_plus  = max(0, row['ci_high'] - row['roi'])
            fig_fp.add_trace(go.Scatter(
                x=[row['roi']],
                y=[row['ch']],
                mode='markers',
                marker=dict(color=color, size=12, symbol='square'),
                error_x=dict(
                    type='data',
                    symmetric=False,
                    array=[err_plus],
                    arrayminus=[err_minus],
                    color=color,
                    thickness=2.5,
                    width=6,
                ),
                name=row['ch'],
                showlegend=False,
                hovertemplate=(
                    f'<b>{row["ch"]}</b><br>'
                    f'{_eff_label}: {row["roi"]:.2f}<br>'
                    f'95%CI: [{row["ci_low"]:.2f}, {row["ci_high"]:.2f}]'
                    '<extra></extra>'
                ),
            ))
        else:
            fig_fp.add_trace(go.Scatter(
                x=[row['roi']],
                y=[row['ch']],
                mode='markers',
                marker=dict(color=color, size=10, symbol='diamond'),
                showlegend=False,
                hovertemplate=f'<b>{row["ch"]}</b><br>{_eff_label}: {row["roi"]:.2f}<extra></extra>',
            ))

    fig_fp.add_vline(x=1.0, line_dash='dot', line_color='#999',
                     annotation_text=f'{_eff_label}=1.0（損益分岐）', annotation_position='top right')

    fig_fp.update_layout(
        xaxis_title=f'{_eff_label}（{_eff_unit}）',
        xaxis=dict(gridcolor='#DAEBE5', zeroline=True, zerolinecolor='#DAEBE5'),
        yaxis=dict(showgrid=False),
        height=max(280, len(_ci_data) * 48 + 80),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=30, t=20, b=40),
    )
    st.plotly_chart(fig_fp, use_container_width=True)
    st.caption(f'■ = 95%CI付き推定値　◆ = 点推定値のみ（CI非対応モデル）　エラーバーが短いほど推定の確度が高い')

else:
    _ch_list  = sorted(_ch_valid.keys(), key=lambda c: _ch_valid[c].get('roi', 0))
    _roi_vals = [_ch_valid[c].get('roi', 0) for c in _ch_list]
    _colors   = [_COL_PRIMARY if v >= 1.0 else _COL_AMBER for v in _roi_vals]

    fig_fp = go.Figure(go.Scatter(
        x=_roi_vals, y=_ch_list,
        mode='markers',
        marker=dict(color=_colors, size=12, symbol='diamond'),
        showlegend=False,
        hovertemplate=f'<b>%{{y}}</b><br>{_eff_label}: %{{x:.2f}}<extra></extra>',
    ))
    fig_fp.add_vline(x=1.0, line_dash='dot', line_color='#999',
                     annotation_text=f'{_eff_label}=1.0（損益分岐）', annotation_position='top right')
    fig_fp.update_layout(
        xaxis_title=f'{_eff_label}（{_eff_unit}）',
        xaxis=dict(gridcolor='#DAEBE5'),
        yaxis=dict(showgrid=False),
        height=max(260, len(_ch_list) * 40 + 80),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=30, t=20, b=40),
    )
    st.plotly_chart(fig_fp, use_container_width=True)
    st.caption(f'◆ = {_eff_label}点推定値。このモデルでは信頼区間（CI）は未対応です。')
