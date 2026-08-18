# -*- coding: utf-8 -*-
"""Page 5 — チャネル詳細（スコアカード・レスポンスカーブ・アドストック減衰）。"""
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

_MTERIA      = ['#315E6D', '#7EBEAB', '#5C9291', '#317680', '#A2CEBF', '#CB8013', '#C5DFD9']
_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_MID     = '#5C9291'
_COL_LIGHT   = '#A2CEBF'
_COL_AMBER   = '#CB8013'

_SAT_COLORS = {
    '伸び代あり': '#315E6D',
    '適正域':     '#5C9291',
    '飽和域':     '#A2CEBF',
    '係数ゼロ':   '#C5DFD9',
}

st.title('チャネル詳細')
st.caption('チャネルごとの飽和曲線（どこで効果が頭打ちになるか）と、広告効果の持続期間（アドストック半減期）が視覚的に分かります。')

if not st.session_state.get('job_info'):
    _recovered = r.find_latest_job()
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
        st.page_link('pages/3_結果.py', label='← ROI分析ページで進捗を確認')
        st.stop()
    elif status['status'] == 'failed':
        st.error('分析が失敗しました。')
        st.page_link('pages/3_結果.py', label='← ROI分析ページを確認')
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

def _eff_val(ch_data):
    """主指標の値を返す。monetary=roi*100(%), count=cpa(円)"""
    if _is_monetary:
        return round(ch_data.get('roi', 0) * 100, 1)
    return int(ch_data.get('cpa', 0) or 0)

def _eff_fmt(v):
    """表示用フォーマット"""
    if _is_monetary:
        return f'{v:.1f}%'
    return f'¥{int(v):,}'

if not _ch_valid:
    st.warning('有効なチャネルが見つかりません。')
    st.stop()

# ── チャネルスコアカード ────────────────────────────────────────────────
st.subheader('チャネル別スコアカード')

valid_df = pd.DataFrame([
    {
        'チャネル':      ch,
        _eff_label:     _eff_val(v),
        'CPA (円)':     int(v.get('cpa', 0) or 0),
        '貢献CV数':     round(v.get('cv_contrib', 0), 1),
        '広告費 (万円)': round(v.get('spend_man', 0), 1),
        '飽和度':       v.get('saturation_label', ''),
        '限界ROI':      round(v.get('marginal_roi', 0), 2),
        'lambda':       v.get('lambda', 0),
        'alpha':        v.get('alpha', 0),
        'gamma':        v.get('gamma', 1.0),
        'sat_score':    v.get('saturation_score', 0),
    }
    for ch, v in _ch_valid.items()
]).sort_values(_eff_label, ascending=not _is_monetary)

def _sat_badge(lbl):
    c = _SAT_COLORS.get(lbl, '#C5DFD9')
    txt_c = '#ffffff' if lbl in ('伸び代あり', '適正域') else '#314858'
    return f'<span style="background:{c};color:{txt_c};padding:2px 8px;border-radius:999px;font-size:11px;">{lbl}</span>'

st.markdown("""<style>
.sc-table{width:100%;border-collapse:collapse;font-size:13px;}
.sc-table th{background:#F3F7F4;color:#5C9291;font-weight:600;font-size:11px;
             text-transform:uppercase;letter-spacing:.07em;padding:8px 12px;
             border-bottom:2px solid #DAEBE5;text-align:left;}
.sc-table td{padding:9px 12px;border-bottom:1px solid #DAEBE5;color:#314858;}
.sc-table tr:last-child td{border-bottom:none;}
.sc-table tr:hover td{background:#F9FDFC;}
.num-col{text-align:right!important;font-variant-numeric:tabular-nums;}
</style>""", unsafe_allow_html=True)

rows_html = ''
for _, row in valid_df.iterrows():
    eff_v   = row[_eff_label]
    eff_str = _eff_fmt(eff_v)
    rows_html += (
        f'<tr>'
        f'<td><b>{row["チャネル"]}</b></td>'
        f'<td class="num-col">{eff_str}</td>'
        f'<td class="num-col">¥{int(row["CPA (円)"]):,}</td>'
        f'<td class="num-col">{row["貢献CV数"]:.1f}</td>'
        f'<td class="num-col">{row["広告費 (万円)"]:.1f}万円</td>'
        f'<td class="num-col">{row["限界ROI"]:.2f}倍</td>'
        f'<td>{_sat_badge(row["飽和度"])}</td>'
        f'</tr>'
    )
st.markdown(
    '<table class="sc-table"><thead><tr>'
    f'<th>チャネル</th><th class="num-col">{_eff_label}</th><th class="num-col">CPA</th>'
    '<th class="num-col">貢献CV</th><th class="num-col">広告費</th>'
    f'<th class="num-col">限界{"ROAS/ROI" if _is_monetary else "CPA"}</th>'
    '<th>飽和度<span class="lq" style="vertical-align:middle;margin-left:5px;">?'
    '<span class="lq-tip">伸び代あり＝まだ余裕あり<br>適正域＝効率的<br>飽和域＝頭打ち（追加投資の効果が薄い）</span></span></th>'
    f'</tr></thead><tbody>{rows_html}</tbody></table>',
    unsafe_allow_html=True,
)

zero_chs = [ch for ch, v in channels.items() if v.get('is_zero')]
if zero_chs:
    st.warning(f'効果ゼロと判定されたチャネル: {", ".join(zero_chs)}')

st.divider()

# ── レスポンスカーブ ──────────────────────────────────────────────────────
st.subheader('レスポンスカーブ（飽和曲線）')
st.caption('各チャネルの広告費と広告効果の関係。●は現在の投資水準です。曲線が寝るほど追加投資の効果が薄れています。')

_has_curves = valid_df[['alpha', 'gamma', 'sat_score']].apply(
    lambda r: r['gamma'] > 0 and r['sat_score'] > 0, axis=1
).any()

if _has_curves:
    n_ch  = len(valid_df)
    n_col = 2
    n_row = (n_ch + 1) // n_col

    subplot_titles = [row['チャネル'] for _, row in valid_df.iterrows()]
    fig_rc = make_subplots(
        rows=n_row, cols=n_col,
        subplot_titles=subplot_titles,
        shared_xaxes=False, shared_yaxes=False,
        horizontal_spacing=0.10, vertical_spacing=0.14,
    )

    for idx, (_, row) in enumerate(valid_df.iterrows()):
        r_i = idx // n_col + 1
        c_i = idx % n_col + 1
        color = _COL_PRIMARY

        spend   = row['広告費 (万円)']
        gamma   = max(row['gamma'], 0.1)
        sat_s   = max(min(row['sat_score'], 0.99), 0.01)

        # EC50: spend at 50% saturation
        # Hill: y = x^gamma / (EC50^gamma + x^gamma) → sat_s = spend^gamma / (EC50^gamma + spend^gamma)
        # → EC50^gamma = spend^gamma * (1 - sat_s) / sat_s
        ec50 = spend * ((1 - sat_s) / sat_s) ** (1.0 / gamma)

        x_max  = max(spend * 2.5, ec50 * 2)
        x_vals = np.linspace(0, x_max, 200)
        y_vals = x_vals**gamma / (ec50**gamma + x_vals**gamma)

        # y at current spend
        y_cur  = spend**gamma / (ec50**gamma + spend**gamma)

        fig_rc.add_trace(
            go.Scatter(
                x=x_vals, y=y_vals,
                mode='lines', line=dict(color=color, width=2.5),
                showlegend=False,
            ),
            row=r_i, col=c_i,
        )
        fig_rc.add_trace(
            go.Scatter(
                x=[spend], y=[y_cur],
                mode='markers',
                marker=dict(color=color, size=10, symbol='circle',
                            line=dict(color='white', width=2)),
                showlegend=False,
                hovertemplate=f'広告費: {spend:.1f}万円<br>飽和度: {sat_s*100:.0f}%<extra></extra>',
            ),
            row=r_i, col=c_i,
        )
        fig_rc.update_xaxes(
            title_text='広告費（万円）', row=r_i, col=c_i,
            gridcolor='#DAEBE5', showgrid=True,
        )
        fig_rc.update_yaxes(
            title_text='相対効果（0–1）', row=r_i, col=c_i,
            range=[0, 1.05], gridcolor='#DAEBE5', showgrid=True,
        )

    fig_rc.update_layout(
        height=n_row * 260,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_rc, use_container_width=True)
else:
    st.info('レスポンスカーブの生成に必要なパラメータが含まれていません。実際の分析データで確認できます。')

st.divider()

# ── アドストック減衰チャート ───────────────────────────────────────────────
st.subheader('アドストック減衰（広告効果の持ち越し）')
st.caption('広告の効果が翌週以降どれだけ持続するかを示します。λ（ラムダ）が高いほど長く効果が残ります。')

_has_lambda = (valid_df['lambda'] > 0).any()

if _has_lambda:
    weeks = np.arange(0, 13)  # 0〜12週
    _decay_colors = _MTERIA

    fig_decay = go.Figure()
    for idx, (_, row) in enumerate(valid_df.iterrows()):
        lam   = row['lambda']
        if lam <= 0:
            continue
        color = _decay_colors[idx % len(_decay_colors)]
        decay = lam ** weeks * 100  # %で表示
        fig_decay.add_trace(go.Scatter(
            x=weeks, y=decay,
            mode='lines+markers',
            name=f'{row["チャネル"]} (λ={lam:.2f})',
            line=dict(color=color, width=2),
            marker=dict(size=5),
        ))

    fig_decay.add_hline(y=50, line_dash='dot', line_color='#999', annotation_text='50%（半減期）')
    fig_decay.update_layout(
        xaxis_title='経過週数',
        yaxis_title='残存効果 (%)',
        yaxis_range=[0, 105],
        height=360,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig_decay.update_xaxes(gridcolor='#DAEBE5', dtick=1)
    fig_decay.update_yaxes(gridcolor='#DAEBE5')
    st.plotly_chart(fig_decay, use_container_width=True)

    # 半減期テーブル
    hl_data = []
    for _, row in valid_df.iterrows():
        lam = row['lambda']
        if lam > 0 and lam < 1:
            hl = round(-np.log(2) / np.log(lam), 1)
            hl_data.append({'チャネル': row['チャネル'], 'λ（減衰率）': f'{lam:.3f}', '効果の半減期（週）': f'{hl:.1f}週'})
    if hl_data:
        st.markdown(
            '<div class="lbl-q" style="font-size:13px;font-weight:400;color:#5C9291;margin-bottom:6px;">'
            'λ（減衰率）と半減期'
            '<span class="lq">?<span class="lq-tip">'
            'λ（ラムダ）＝ 1週後に残る効果の割合。<br>'
            '半減期 ＝ 効果が50%になるまでの週数。<br>'
            '例: λ=0.7 なら 1週後も70%が持続、半減期は約1.9週</span></span></div>',
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(hl_data), use_container_width=True, hide_index=True)
else:
    st.info('アドストックパラメータが含まれていません。実際の分析データで確認できます。')
