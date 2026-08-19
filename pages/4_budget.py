# -*- coding: utf-8 -*-
"""Page 4 — 予算配分（最適化シミュレーション）。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import runner as r

_MTERIA      = ['#315E6D', '#7EBEAB', '#5C9291', '#317680', '#A2CEBF', '#CB8013', '#C5DFD9']
_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_MID     = '#5C9291'
_COL_LIGHT   = '#A2CEBF'
_COL_AMBER   = '#CB8013'

st.title('予算配分分析')
st.markdown('<p class="page-lede">現在の予算配分をROI比例に最適化した場合のCV改善量と、チャネルごとの増減額（Before/After）が分かります。</p>', unsafe_allow_html=True)

if not st.session_state.get('job_info'):
    _recovered = r.find_latest_job(st.session_state.get('own_job_ids', set()))
    if _recovered:
        st.session_state['job_info'] = _recovered
        st.info('前回のジョブを表示しています。')
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

def _pct_str(v):
    return f'+{v:.1f}%' if v >= 0 else f'{v:.1f}%'

channels, _dup_warn = r.dedup_channels(summary.get('channels', {}))
if _dup_warn:
    st.warning('同名の可能性があるチャネルが複数あります。マッピングを確認して再実行してください（' + '、'.join(_dup_warn) + '）。')
_total_cv   = summary.get('total_cv', 0)
_cv_lift    = summary.get('cv_lift_pct', 0)
_cv_lift_b  = summary.get('cv_lift_pct_b', 0)
_budget_inc = summary.get('budget_increase', 0.3)
_max_eff    = summary.get('max_efficient_budget', 0)
_thr_cpa    = summary.get('threshold_cpa', 0)

_ch_valid    = {ch: v for ch, v in channels.items() if not v.get('is_zero', False)}
_cv_type     = summary.get('cv_metric_type', 'count')
_is_monetary = _cv_type == 'monetary'
_eff_label   = 'ROAS / ROI' if _is_monetary else 'CPA'
_eff_unit    = '%' if _is_monetary else '円'

if not _ch_valid:
    st.warning('有効なチャネルが見つかりません。')
    st.stop()

if _is_monetary:
    valid_df = pd.DataFrame([
        {'チャネル': ch, 'EFF': round(v.get('roi', 0) * 100, 1), '広告費 (万円)': round(v.get('spend_man', 0), 1)}
        for ch, v in _ch_valid.items()
    ]).sort_values('EFF', ascending=False).rename(columns={'EFF': _eff_label})
else:
    valid_df = pd.DataFrame([
        {'チャネル': ch, 'EFF': int(v.get('cpa', 0) or 0), '広告費 (万円)': round(v.get('spend_man', 0), 1)}
        for ch, v in _ch_valid.items()
    ]).sort_values('EFF', ascending=True).rename(columns={'EFF': _eff_label})

# ── サマリー指標 ────────────────────────────────────────────────────────
st.subheader('予算最適化シミュレーション')
_cv_lift_style   = f'color:{_COL_PRIMARY};' if _cv_lift   >= 0 else ''
_cv_lift_b_style = f'color:{_COL_AMBER};'   if _cv_lift_b >  0 else ''
st.markdown(f"""<div class="mmm-card-grid" style="margin-bottom:24px;">
  <div class="mmm-card">
    <div class="mmm-card-lbl">CV実績<span class="lq">?<span class="lq-tip">分析期間の合計コンバージョン数（広告起因・ベースライン含む）。</span></span></div>
    <div class="mmm-card-val">{_total_cv:,}<span class="mmm-card-unit">件</span></div>
  </div>
  <div class="mmm-card">
    <div class="mmm-card-lbl">同予算 CV改善<span class="lq">?<span class="lq-tip">同じ総広告費のまま配分をROI比例に最適化した場合の推定CV増加率。</span></span></div>
    <div class="mmm-card-val" style="{_cv_lift_style}">{_pct_str(_cv_lift)}</div>
  </div>
  <div class="mmm-card">
    <div class="mmm-card-lbl">増額{int(_budget_inc*100)}% CV改善<span class="lq">?<span class="lq-tip lq-tip-left">総広告費を{int(_budget_inc*100)}%増額かつ最適配分した場合の推定CV増加率。</span></span></div>
    <div class="mmm-card-val" style="{_cv_lift_b_style}">{_pct_str(_cv_lift_b)}</div>
  </div>
</div>""", unsafe_allow_html=True)

# 投資効率フロンティア情報
if _max_eff > 0:
    _max_eff_man = round(_max_eff / 10000, 0)
    st.markdown(
        '<div class="mmm-info-box">'
        f'<strong>投資効率の上限目安:</strong> 広告費 <strong>{_max_eff_man:,.0f} 万円</strong> が効率的な投資上限です。'
        + (f'　目安CPA: <strong>¥{_thr_cpa:,}</strong>' if _thr_cpa > 0 else '')
        + '　これ以上の増額は費用対効果が大きく低下します。'
        '</div>',
        unsafe_allow_html=True,
    )

st.divider()

# ── Before/After グループバー ────────────────────────────────────────────
_channel_opt = summary.get('channel_opt', {})

sim_df = valid_df.copy()
if _channel_opt:
    sim_df['最適配分 (万円)'] = sim_df['チャネル'].map(
        lambda ch: round(_channel_opt.get(ch, {}).get('optimal_spend', 0) / 10000, 1)
    )
else:
    total_spend = valid_df['広告費 (万円)'].sum()
    if _is_monetary:
        total_eff = valid_df[_eff_label].sum()
        sim_df['最適配分 (万円)'] = (sim_df[_eff_label] / total_eff * total_spend).round(1)
    else:
        # count mode: 逆CPA比例（CPA小=効率高=多く配分）
        inv_cpa = valid_df[_eff_label].apply(lambda x: 1 / x if x > 0 else 0)
        sim_df['最適配分 (万円)'] = (inv_cpa / inv_cpa.sum() * total_spend).round(1)
sim_df['差分 (万円)'] = (sim_df['最適配分 (万円)'] - sim_df['広告費 (万円)']).round(1)

_opt_label = '最適配分（非線形最適化）' if _channel_opt else f'最適配分（{_eff_label}最適化）'

compare_df = pd.DataFrame({
    'チャネル':      valid_df['チャネル'].tolist() * 2,
    '広告費 (万円)': valid_df['広告費 (万円)'].tolist() + sim_df['最適配分 (万円)'].tolist(),
    '配分':          ['現状'] * len(valid_df) + [_opt_label] * len(sim_df),
})
fig_bar = px.bar(
    compare_df,
    x='チャネル', y='広告費 (万円)', color='配分',
    barmode='group',
    color_discrete_map={'現状': _COL_LIGHT, _opt_label: _COL_PRIMARY},
    labels={'広告費 (万円)': '広告費（万円）'},
)
fig_bar.update_layout(
    margin=dict(l=10, r=20, t=10, b=10),
    height=340,
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
)
fig_bar.update_yaxes(gridcolor='#DAEBE5')
st.plotly_chart(fig_bar, use_container_width=True)

# 変化量テーブル
def _diff_color(x, is_monetary):
    if not isinstance(x, (int, float)):
        return ''
    good = x > 0 if is_monetary else x < 0
    bad  = x < 0 if is_monetary else x > 0
    if good:
        return 'color: #315E6D; font-weight: 600;'
    if bad:
        return 'color: #CB8013; font-weight: 600;'
    return ''

st.caption(f'現状 vs {_opt_label} の差分')
disp_sim = sim_df[['チャネル', _eff_label, '広告費 (万円)', '最適配分 (万円)', '差分 (万円)']].copy()
_num_cols = [_eff_label, '広告費 (万円)', '最適配分 (万円)', '差分 (万円)']
_html = r.sc_table_html(
    disp_sim,
    num_cols=_num_cols,
    cell_styles={'差分 (万円)': lambda x: _diff_color(x, _is_monetary)},
    formatters={
        _eff_label:       (lambda v: f'{v:.1f}%') if _is_monetary else (lambda v: f'¥{int(v):,}'),
        '広告費 (万円)':   lambda v: f'{v:.1f}万円',
        '最適配分 (万円)': lambda v: f'{v:.1f}万円',
        '差分 (万円)':     lambda v: f'{v:+.1f}万円',
    },
)
st.markdown(_html, unsafe_allow_html=True)

st.divider()

# ── 円グラフ（現状 vs 最適）───────────────────────────────────────────────
ch_order = valid_df['チャネル'].tolist()

def _grad_n(n, c0=_COL_PRIMARY, c1=_COL_LIGHT):
    if n == 1: return [c1]
    r0,g0,b0 = int(c0[1:3],16),int(c0[3:5],16),int(c0[5:7],16)
    r1,g1,b1 = int(c1[1:3],16),int(c1[3:5],16),int(c1[5:7],16)
    return [f'#{int(r0+(r1-r0)*i/(n-1)):02x}{int(g0+(g1-g0)*i/(n-1)):02x}{int(b0+(b1-b0)*i/(n-1)):02x}' for i in range(n)]

ch_colors = _grad_n(len(ch_order))

col_l, col_r = st.columns(2)
with col_l:
    st.markdown('**現状の広告費配分**')
    fig_cur = go.Figure(go.Pie(
        labels=ch_order,
        values=valid_df.set_index('チャネル').loc[ch_order, '広告費 (万円)'].tolist(),
        hole=0.4,
        marker_colors=ch_colors,
        sort=False,
        direction='clockwise',
        rotation=0,
        textposition='inside',
        textinfo='percent+label',
    ))
    fig_cur.update_layout(showlegend=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_cur, use_container_width=True)

with col_r:
    st.markdown(f'**{_opt_label}（シミュレーション）**')
    fig_sim = go.Figure(go.Pie(
        labels=ch_order,
        values=sim_df.set_index('チャネル').loc[ch_order, '最適配分 (万円)'].tolist(),
        hole=0.4,
        marker_colors=ch_colors,
        sort=False,
        direction='clockwise',
        rotation=0,
        textposition='inside',
        textinfo='percent+label',
    ))
    fig_sim.update_layout(showlegend=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_sim, use_container_width=True)

_note = 'レスポンスカーブに基づく非線形最適化' if _channel_opt else f'{_eff_label}最適化'
st.caption(f'※ 最適配分は{_note}の試算値です。実際の施策では配信面・在庫・最低予算等の制約を加味して判断してください。')
