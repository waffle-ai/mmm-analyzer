# -*- coding: utf-8 -*-
"""Page 7 — 投資上限分析（投資効率フロンティア）。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import runner as r

_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_MID     = '#5C9291'
_COL_LIGHT   = '#A2CEBF'
_COL_AMBER   = '#CB8013'
_MTERIA      = ['#315E6D', '#7EBEAB', '#5C9291', '#317680', '#A2CEBF', '#CB8013', '#C5DFD9']

_SAT_COLORS = {
    '伸び代あり': '#315E6D',
    '適正域':     '#5C9291',
    '飽和域':     '#A2CEBF',
    '係数ゼロ':   '#C5DFD9',
}

st.title('投資上限分析')
st.markdown('<p class="page-lede">各チャネルの広告費が「効果の出るゾーン」にあるか「飽和域（費用対効果が低下するゾーン）」にあるかを可視化します。これ以上増額しても効果が薄くなる「投資上限」の目安が分かります。</p>', unsafe_allow_html=True)

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
        st.stop()
    elif status['status'] == 'failed':
        st.error('分析が失敗しました。')
        st.stop()
    summary = r.load_summary(status['json_path'])

channels, _dup_warn = r.dedup_channels(summary.get('channels', {}))
if _dup_warn:
    st.warning('同名の可能性があるチャネルが複数あります。マッピングを確認して再実行してください（' + '、'.join(_dup_warn) + '）。')
_ch_valid    = {ch: v for ch, v in channels.items() if not v.get('is_zero', False)}
_cv_type     = summary.get('cv_metric_type', 'count')
_is_monetary = _cv_type == 'monetary'
_eff_label   = 'ROAS / ROI' if _is_monetary else 'CPA'
_eff_unit    = '%' if _is_monetary else '円'
_max_eff    = summary.get('max_efficient_budget', 0)
_thr_cpa    = summary.get('threshold_cpa', 0)
_total_cv   = summary.get('total_cv', 0)

if not _ch_valid:
    st.warning('有効なチャネルが見つかりません。')
    st.stop()

# ── 投資効率上限サマリー ──────────────────────────────────────────────────
if _max_eff > 0:
    _max_man = round(_max_eff / 10000, 0)
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.markdown(f"""
        <div style="background:#F3F7F4;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(49,72,88,.08);">
          <div style="color:#5C9291;font-size:11px;text-transform:uppercase;letter-spacing:.08em;
               margin-bottom:6px;">効率的な投資上限（全チャネル合計）</div>
          <div style="font-size:32px;font-weight:800;color:#314858;">
            {_max_man:,.0f}<span style="font-size:16px;font-weight:400;color:#5C9291;"> 万円</span>
          </div>
          <div style="color:#5C9291;font-size:12px;margin-top:6px;">
            これ以上の総広告費増額は費用対効果が大きく低下します。
            {f'目安CPA: ¥{_thr_cpa:,}' if _thr_cpa > 0 else ''}
          </div>
        </div>""", unsafe_allow_html=True)
    with col_b:
        _total_spend = sum(v.get('spend_man', 0) for v in _ch_valid.values())
        _pct_to_max  = (_total_spend / _max_man * 100) if _max_man > 0 else 0
        _color_pct   = _COL_PRIMARY if _pct_to_max < 80 else _COL_AMBER if _pct_to_max < 100 else '#CB8013'
        st.markdown(f"""
        <div style="background:#F3F7F4;border-radius:10px;padding:18px 22px;
                    box-shadow:0 1px 3px rgba(49,72,88,.08);text-align:center;">
          <div style="color:#5C9291;font-size:11px;text-transform:uppercase;letter-spacing:.08em;
               margin-bottom:6px;">現在の使用率</div>
          <div style="font-size:32px;font-weight:800;color:{_color_pct};">
            {_pct_to_max:.0f}<span style="font-size:16px;font-weight:400;color:#5C9291;">%</span>
          </div>
          <div style="color:#5C9291;font-size:12px;margin-top:6px;">現状 {_total_spend:,.1f} 万円</div>
        </div>""", unsafe_allow_html=True)
    st.markdown('<div style="margin-bottom:20px;"></div>', unsafe_allow_html=True)

st.divider()

# ── フロンティア曲線（総予算 vs CV/ROAS） ────────────────────────────────
_frontier_curve = summary.get('frontier_curve', [])
if _frontier_curve:
    _fc_df = pd.DataFrame(_frontier_curve)
    _fc_df['budget_man'] = _fc_df['budget'] / 10000
    _y_col = 'cv'
    _y_label = '推定ROAS' if _is_monetary else '推定CV獲得数'
    _cap_metric = 'ROAS' if _is_monetary else 'CV獲得数'
    _max_eff_man_fc = round(_max_eff / 10000, 0) if _max_eff > 0 else None

    st.subheader('フロンティア曲線（予算 vs CV効率）')
    st.caption(
        f'総広告費を段階的に変化させたときの推定{_cap_metric}。'
        '点線の縦軸（効率上限）を超えると費用対効果が急落します。'
    )

    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(
        x=_fc_df['budget_man'], y=_fc_df[_y_col],
        mode='lines+markers',
        line=dict(color=_COL_PRIMARY, width=2.5),
        marker=dict(size=5, color=_COL_PRIMARY),
        hovertemplate=(
            '予算: %{x:,.0f}万円<br>'
            + _y_label + ': %{y:,.2f}<extra></extra>'
        ),
        name=_y_label,
    ))

    if _max_eff_man_fc:
        fig_fc.add_vline(
            x=_max_eff_man_fc,
            line=dict(color=_COL_AMBER, dash='dot', width=2),
            annotation_text=f'効率上限 {_max_eff_man_fc:,.0f}万円',
            annotation_position='top right',
            annotation_font_color=_COL_AMBER,
        )

    fig_fc.update_layout(
        height=320,
        margin=dict(l=10, r=20, t=20, b=10),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        xaxis=dict(title='総広告費（万円）', gridcolor='#DAEBE5'),
        yaxis=dict(title=_y_label, gridcolor='#DAEBE5'),
    )
    st.plotly_chart(fig_fc, use_container_width=True)
    st.divider()

# ── チャネル別 飽和度ゲージ ───────────────────────────────────────────────
st.subheader('チャネル別 飽和度（現在の投資水準）')
st.caption('飽和スコアが高いほど追加投資の効果が薄れています。100%で完全飽和。')

sat_rows = []
for ch, v in _ch_valid.items():
    sat_score = v.get('saturation_score', 0) * 100
    sat_label = v.get('saturation_label', '')
    roi       = v.get('roi', 0)
    mroi      = v.get('marginal_roi', 0)
    spend     = v.get('spend_man', 0)
    sat_rows.append({
        'チャネル':    ch,
        '飽和スコア':  round(sat_score, 1),
        '飽和度':      sat_label,
        'ROI':         round(roi, 2),
        '限界ROI':     round(mroi, 2),
        '広告費(万円)': round(spend, 1),
    })

sat_df = pd.DataFrame(sat_rows).sort_values('飽和スコア', ascending=False)

# 横棒ゲージチャート
fig_sat = go.Figure()
color_cycle = [_SAT_COLORS.get(row['飽和度'], '#999') for _, row in sat_df.iterrows()]

for idx, (_, row) in enumerate(sat_df.iterrows()):
    color = color_cycle[idx]
    # 背景バー（100%）
    fig_sat.add_trace(go.Bar(
        x=[100], y=[row['チャネル']], orientation='h',
        marker_color='#E8F2EF', showlegend=False,
        hoverinfo='skip',
    ))
    # 飽和度バー
    fig_sat.add_trace(go.Bar(
        x=[row['飽和スコア']], y=[row['チャネル']], orientation='h',
        marker_color=color, showlegend=False,
        text=f"{row['飽和スコア']:.0f}%  ({row['飽和度']})",
        textposition='outside', textfont_size=12,
        hovertemplate=(
            f"<b>{row['チャネル']}</b><br>"
            f"飽和スコア: {row['飽和スコア']:.1f}%<br>"
            f"状態: {row['飽和度']}<br>"
            + (
                f"ROAS/ROI: {row['ROI'] * 100:.1f}%<br>"
                f"限界ROAS/ROI: {row['限界ROI'] * 100:.1f}%"
                if _is_monetary else
                f"CPA: ¥{int(_ch_valid.get(row['チャネル'], {}).get('cpa', 0)):,}<br>"
                f"限界ROI: {row['限界ROI']:.2f}"
            )
            + "<extra></extra>"
        ),
    ))

fig_sat.update_layout(
    barmode='overlay',
    height=max(300, len(sat_df) * 60),
    margin=dict(l=10, r=130, t=10, b=10),
    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    xaxis=dict(range=[0, 130], showgrid=False, showticklabels=False),
    yaxis=dict(gridcolor='rgba(0,0,0,0)'),
)
st.plotly_chart(fig_sat, use_container_width=True)

# ── ROI/ROAS vs 限界ROI/ROAS 比較（monetary mode のみ） ──────────────────
if _is_monetary and sat_df['限界ROI'].sum() > 0:
    st.divider()
    st.subheader(f'平均{_eff_label} vs 限界{_eff_label}（追加投資効率）')
    st.caption(
        f'限界{_eff_label} = 現在の水準からさらに1円追加した場合の{_eff_label}。'
        f'平均より大きく下回るほど飽和が進んでいます。'
    )

    _avg_lbl = f'平均{_eff_label}'
    _mrg_lbl = f'限界{_eff_label}'
    cmp_df = pd.DataFrame({
        'チャネル':  sat_df['チャネル'].tolist() * 2,
        'ROI値':     sat_df['ROI'].tolist() + sat_df['限界ROI'].tolist(),
        '種別':      [_avg_lbl] * len(sat_df) + [_mrg_lbl] * len(sat_df),
    })
    fig_cmp = px.bar(
        cmp_df, x='ROI値', y='チャネル', color='種別', orientation='h',
        barmode='group',
        color_discrete_map={_avg_lbl: _COL_LIGHT, _mrg_lbl: _COL_PRIMARY},
        text='ROI値',
        labels={'ROI値': f'{_eff_label}（倍）'},
    )
    fig_cmp.update_traces(texttemplate='%{text:.2f}倍', textposition='outside', textfont_size=11)
    fig_cmp.update_layout(
        margin=dict(l=10, r=100, t=10, b=10),
        height=max(300, len(sat_df) * 60),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    fig_cmp.update_xaxes(gridcolor='#DAEBE5')
    fig_cmp.update_yaxes(gridcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_cmp, use_container_width=True)

# ── 飽和曲線（Hill関数）───────────────────────────────────────────────────
st.divider()
st.subheader('飽和曲線（投資効率フロンティア）')
st.caption('各チャネルの現在の投資水準（●）と、それ以上増額した場合の効果の伸び方を示します。')

_has_curves = any(
    v.get('gamma', 0) > 0 and v.get('saturation_score', 0) > 0
    for v in _ch_valid.values()
)

if _has_curves:
    n_ch  = len(_ch_valid)
    n_col = 2
    n_row = (n_ch + 1) // n_col
    ch_list = sorted(_ch_valid.items(), key=lambda kv: kv[1].get('saturation_score', 0), reverse=True)

    subplot_titles = [ch for ch, _ in ch_list]
    fig_rc = make_subplots(
        rows=n_row, cols=n_col,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.10, vertical_spacing=0.14,
    )
    for idx, (ch, v) in enumerate(ch_list):
        r_i = idx // n_col + 1
        c_i = idx % n_col + 1
        color = _COL_PRIMARY

        spend    = v.get('spend_man', 1)
        gamma    = max(v.get('gamma', 0.5), 0.1)
        sat_s    = max(min(v.get('saturation_score', 0.5), 0.99), 0.01)

        ec50 = spend * ((1 - sat_s) / sat_s) ** (1.0 / gamma)
        x_max  = max(spend * 3.0, ec50 * 2.5)
        x_vals = np.linspace(0, x_max, 300)
        y_vals = x_vals**gamma / (ec50**gamma + x_vals**gamma)
        y_cur  = spend**gamma / (ec50**gamma + spend**gamma)

        fig_rc.add_trace(
            go.Scatter(
                x=x_vals, y=y_vals,
                mode='lines', line=dict(color=color, width=2.5),
                showlegend=False,
            ),
            row=r_i, col=c_i,
        )
        # 飽和上限ライン
        fig_rc.add_shape(
            type='line', x0=0, x1=x_max, y0=0.8, y1=0.8,
            line=dict(color='#CB8013', dash='dot', width=1),
            row=r_i, col=c_i,
        )
        # 現在地マーカー
        fig_rc.add_trace(
            go.Scatter(
                x=[spend], y=[y_cur],
                mode='markers',
                marker=dict(color=color, size=11, symbol='circle',
                            line=dict(color='white', width=2.5)),
                showlegend=False,
                hovertemplate=(
                    f'<b>{ch}</b><br>'
                    f'広告費: {spend:.1f}万円<br>'
                    f'飽和度: {sat_s*100:.0f}%<extra></extra>'
                ),
            ),
            row=r_i, col=c_i,
        )
        fig_rc.update_xaxes(title_text='広告費（万円）', row=r_i, col=c_i, gridcolor='#DAEBE5')
        fig_rc.update_yaxes(title_text='相対効果（0–1）', row=r_i, col=c_i,
                             range=[0, 1.05], gridcolor='#DAEBE5')

    fig_rc.update_layout(
        height=n_row * 270,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_rc, use_container_width=True)
    st.caption('点線（80%）は飽和域の目安。●が点線を超えたチャネルは追加投資効果が低下しています。')
else:
    st.info('飽和曲線の生成に必要なパラメータが含まれていません。実際の分析データで確認できます。')
