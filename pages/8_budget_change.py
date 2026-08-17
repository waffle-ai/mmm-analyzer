# -*- coding: utf-8 -*-
"""Page 8 — 予算増額・減額分析（シナリオ別CV予測）。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import runner as r

_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_MID     = '#5C9291'
_COL_LIGHT   = '#A2CEBF'
_COL_AMBER   = '#CB8013'
_MTERIA      = ['#315E6D', '#7EBEAB', '#5C9291', '#317680', '#A2CEBF', '#CB8013', '#C5DFD9']

st.title('予算増額・減額分析')
st.markdown("""
<div style="background:#EAF4F0;border-left:4px solid #315E6D;border-radius:0 8px 8px 0;
     padding:12px 16px;margin-bottom:20px;">
  <span style="color:#314858;font-size:15px;">
    総広告費を±30%の範囲で増減したときの成果変化を試算します。
    各シナリオの費用対効果を見比べ、予算規模の判断に使えます。
  </span>
</div>""", unsafe_allow_html=True)

if not st.session_state.get('job_info'):
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

channels    = summary.get('channels', {})
_total_cv   = summary.get('total_cv', 0)
_cv_lift    = summary.get('cv_lift_pct', 0)        # 同予算最適化後の増加率(%)
_cv_lift_b  = summary.get('cv_lift_pct_b', 0)     # budget_increase時の増加率(%)
_budget_inc = summary.get('budget_increase', 0.3)  # 例: 0.3 = +30%
_max_eff    = summary.get('max_efficient_budget', 0)

_ch_valid    = {ch: v for ch, v in channels.items() if not v.get('is_zero', False)}
_total_spend = sum(v.get('spend_man', 0) for v in _ch_valid.values())
_cv_type     = summary.get('cv_metric_type', 'count')
_is_monetary = _cv_type == 'monetary'

if not _ch_valid or _total_cv == 0:
    st.warning('分析データが不足しています。')
    st.stop()

# ── シナリオ生成 ─────────────────────────────────────────────────────────────
# 使える既知のアンカー:
#   delta=0      → 現状CV (_total_cv), lift=0%
#   delta=0      → 同予算最適化後 lift = _cv_lift%
#   delta=+budget_inc → _cv_lift_b%
# 中間点は marginal_roi の加重平均で線形補間 (飽和を簡易近似)

# 限界ROI加重平均（追加投資の効率）
_mroi_values = [v.get('marginal_roi', 0) for v in _ch_valid.values() if v.get('marginal_roi', 0) > 0]
_avg_mroi = sum(_mroi_values) / len(_mroi_values) if _mroi_values else 1.0

# 基準CV（同予算最適化後を分析出発点とする）
_base_cv   = _total_cv * (1 + _cv_lift / 100)
_delta_inc = _budget_inc  # e.g. 0.3

# _cv_lift_b は _base_cv に対して追加増分を表すか、_total_cv に対するかを統一する
# cv_lift_pct_b は現状CVに対する相対値として扱う
_anchor_cv_at_inc = _total_cv * (1 + _cv_lift_b / 100) if _cv_lift_b else None

# シナリオ: -30%, -20%, -10%, 0%(現状), 0%(最適化), +10%, +20%, +30%
# 減額シナリオ: 現状CVから限界ROIを使って線形外挿
def _estimate_cv_at_delta(delta: float) -> float:
    """delta: -0.3〜+budget_inc相対変化。現状CV基準で推定CVを返す。"""
    if abs(delta) < 1e-9:
        return float(_total_cv)
    if delta > 0:
        # 増額: anchored to _cv_lift_b at delta=_budget_inc
        if _anchor_cv_at_inc and abs(_delta_inc) > 1e-9:
            # 増額増分を _budget_inc で正規化
            incremental_at_full = _anchor_cv_at_inc - _total_cv
            # 飽和を考慮した補間: 非線形（log近似）
            import math
            frac = delta / _delta_inc
            factor = math.log1p(frac * (math.e - 1))  # 0→0, 1→1 の凹型
            return _total_cv + incremental_at_full * factor
        else:
            # フォールバック: 限界ROI比例
            spend_delta_man = _total_spend * delta
            cv_delta = spend_delta_man * _avg_mroi / 10  # 万円→CV概算
            return max(0.0, _total_cv + cv_delta)
    else:
        # 減額: 同様の凹型近似（下側は逆向き）
        frac = abs(delta) / 0.3  # -30%を最大として正規化
        import math
        factor = math.log1p(frac * (math.e - 1))
        # 減額でのCV減少は増額より効率が大きい（飽和の逆効果は少ない）
        _roi_values = [v.get('roi', 0) for v in _ch_valid.values() if v.get('roi', 0) > 0]
        _avg_roi = sum(_roi_values) / len(_roi_values) if _roi_values else 1.0
        cv_loss_at_30 = _total_spend * 0.3 * _avg_roi / 10
        return max(0.0, _total_cv - cv_loss_at_30 * factor)

scenarios = [-0.30, -0.20, -0.10, 0.00, 0.10, 0.20, 0.30]
# +budget_incが0.30以外の場合は追加
if abs(_budget_inc - 0.30) > 0.01:
    scenarios.append(_budget_inc)
    scenarios = sorted(set(scenarios))

rows = []
for delta in scenarios:
    pct_label = f'{int(delta*100):+d}%'
    is_current = abs(delta) < 1e-9
    est_cv     = _estimate_cv_at_delta(delta)
    change_pct = (est_cv / _total_cv - 1) * 100
    rows.append({
        'scenario':    delta,
        'label':       '現状' if is_current else pct_label,
        '推定CV':      round(est_cv),
        'CV増減(%)':   round(change_pct, 1),
        '推定広告費(万円)': round(_total_spend * (1 + delta), 1),
    })

# 最適化後の行を追加（delta=0 に並べる）
rows_opt = []
for row in rows:
    rows_opt.append(row)
    if abs(row['scenario']) < 1e-9:
        # 最適配分シナリオを挿入
        rows_opt.append({
            'scenario':    0.001,   # ソートキー用
            'label':       '現状\n(最適配分)',
            '推定CV':      round(_base_cv),
            'CV増減(%)':   round(_cv_lift, 1),
            '推定広告費(万円)': round(_total_spend, 1),
        })

rows_opt.sort(key=lambda x: x['scenario'])
df = pd.DataFrame(rows_opt)

# ── メインチャート：シナリオ別CV ─────────────────────────────────────────────
st.subheader('シナリオ別 推定CV')
st.caption('総広告費の増減シナリオごとに推定CVを表示。「現状（最適配分）」は同予算のまま配分を最適化した場合。')

# グラデーション用ヘルパー
def _interp_hex(c0, c1, t):
    r = int(int(c0[1:3],16) + (int(c1[1:3],16)-int(c0[1:3],16))*t)
    g = int(int(c0[3:5],16) + (int(c1[3:5],16)-int(c0[3:5],16))*t)
    b = int(int(c0[5:7],16) + (int(c1[5:7],16)-int(c0[5:7],16))*t)
    return f'#{r:02x}{g:02x}{b:02x}'

_neg_rows = [row for _, row in df.iterrows() if row['scenario'] < -0.001]
_pos_rows = [row for _, row in df.iterrows() if row['scenario'] > 0.001 and '最適配分' not in str(row['label'])]

bar_colors = []
_ni, _pi = 0, 0
for _, row in df.iterrows():
    if '最適配分' in str(row['label']):
        bar_colors.append(_COL_GREEN)
    elif abs(row['scenario']) < 0.001:
        bar_colors.append(_COL_MID)
    elif row['scenario'] < 0:
        t = _ni / max(len(_neg_rows)-1, 1)
        bar_colors.append(_interp_hex('#FBECD7', _COL_AMBER, t))
        _ni += 1
    else:
        t = _pi / max(len(_pos_rows)-1, 1)
        bar_colors.append(_interp_hex(_COL_LIGHT, _COL_PRIMARY, t))
        _pi += 1

fig_cv = go.Figure()
fig_cv.add_trace(go.Bar(
    x=df['label'],
    y=df['推定CV'],
    marker_color=bar_colors,
    text=[f"{int(v):,}" for v in df['推定CV']],
    textposition='outside',
    textfont=dict(size=12, color='#314858'),
    hovertemplate=(
        '<b>%{x}</b><br>'
        '推定CV: %{y:,}件<br>'
        '<extra></extra>'
    ),
))

# 現状CVに水平ライン
fig_cv.add_hline(
    y=_total_cv,
    line_dash='dot', line_color='#999999', line_width=1.5,
    annotation_text=f'現状CV: {int(_total_cv):,}件',
    annotation_position='bottom right',
    annotation_font_color='#888',
)

fig_cv.update_layout(
    height=400,
    margin=dict(l=10, r=10, t=30, b=10),
    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    yaxis=dict(gridcolor='#DAEBE5', zeroline=False),
    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
)
st.plotly_chart(fig_cv, use_container_width=True)

# 凡例説明
st.markdown(
    '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;">'
    f'<span style="font-size:12px;color:#5C9291;">■ <span style="color:{_COL_AMBER}">■</span> 減額シナリオ</span>'
    f'<span style="font-size:12px;color:#5C9291;">■ <span style="color:{_COL_MID}">■</span> 現状</span>'
    f'<span style="font-size:12px;color:#5C9291;">■ <span style="color:{_COL_GREEN}">■</span> 現状（最適配分）</span>'
    f'<span style="font-size:12px;color:#5C9291;">■ <span style="color:{_COL_PRIMARY}">■</span> 増額シナリオ</span>'
    '</div>',
    unsafe_allow_html=True,
)

st.divider()

# ── シナリオ詳細テーブル ──────────────────────────────────────────────────────
st.subheader('シナリオ詳細')

disp_df = df[['label', '推定広告費(万円)', '推定CV', 'CV増減(%)']].copy()
disp_df.columns = ['シナリオ', '推定広告費（万円）', '推定CV（件）', 'CV増減（%）']
disp_df['推定CV（件）'] = disp_df['推定CV（件）'].apply(lambda x: f'{int(x):,}')

def _color_pct(v):
    if isinstance(v, str):
        return ''
    if v > 0:
        return f'color: {_COL_PRIMARY}; font-weight: 600;'
    if v < 0:
        return f'color: {_COL_AMBER}; font-weight: 600;'
    return ''

st.dataframe(
    disp_df.style.map(_color_pct, subset=['CV増減（%）']),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── 費用対効果チャート（CPA / ROAS） ─────────────────────────────────────────
if _is_monetary:
    # 基準収益を現状チャネルデータから推定
    _base_rev = sum(v.get('roi', 0) * v.get('spend_man', 0) * 10000 for v in _ch_valid.values())
    _eff_title = 'シナリオ別 推定ROAS'
    _eff_cap   = '総広告費シナリオごとの推定ROAS（収益÷広告費）。投資規模が増えると逓減するのが通常です。'
    _eff_yaxis = 'ROAS（倍）'
else:
    _eff_title = 'シナリオ別 推定CPA（円）'
    _eff_cap   = '総広告費シナリオごとの推定CPA（1件あたり広告費）。投資規模が増えると上昇するのが通常です。'
    _eff_yaxis = 'CPA（円）'

st.subheader(_eff_title)
st.caption(_eff_cap)

eff_rows = []
for _, row in df.iterrows():
    spend_yen = row['推定広告費(万円)'] * 10000
    cv        = row['推定CV']
    if _is_monetary:
        est_rev = _base_rev * (cv / _total_cv) if _total_cv > 0 else 0
        eff = round(est_rev / spend_yen, 2) if spend_yen > 0 else 0
        eff_fmt = f'{eff:.2f}倍'
    else:
        eff = round(spend_yen / cv) if cv > 0 else 0
        eff_fmt = f'¥{int(eff):,}'
    eff_rows.append({'label': row['label'], 'scenario': row['scenario'], 'eff': eff, 'eff_fmt': eff_fmt})

eff_df = pd.DataFrame(eff_rows)

_ni2, _pi2 = 0, 0
eff_colors = []
for _, r2 in eff_df.iterrows():
    if '最適配分' in str(r2['label']):
        eff_colors.append(_COL_GREEN)
    elif abs(r2['scenario']) < 0.001:
        eff_colors.append(_COL_MID)
    elif r2['scenario'] < 0:
        t = _ni2 / max(len(_neg_rows)-1, 1)
        eff_colors.append(_interp_hex('#FBECD7', _COL_AMBER, t))
        _ni2 += 1
    else:
        t = _pi2 / max(len(_pos_rows)-1, 1)
        eff_colors.append(_interp_hex(_COL_LIGHT, _COL_PRIMARY, t))
        _pi2 += 1

fig_eff = go.Figure()
fig_eff.add_trace(go.Bar(
    x=eff_df['label'],
    y=eff_df['eff'],
    marker_color=eff_colors,
    text=eff_df['eff_fmt'],
    textposition='outside',
    textfont=dict(size=11),
    hovertemplate='<b>%{x}</b><br>' + _eff_yaxis + ': %{text}<extra></extra>',
))
fig_eff.update_layout(
    height=320,
    margin=dict(l=10, r=10, t=20, b=10),
    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    yaxis=dict(gridcolor='#DAEBE5', title=_eff_yaxis),
    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
)
st.plotly_chart(fig_eff, use_container_width=True)

# ── 投資上限の参考情報 ────────────────────────────────────────────────────────
if _max_eff > 0:
    _max_man = round(_max_eff / 10000, 0)
    _current_man = _total_spend
    _pct_used = (_current_man / _max_man * 100) if _max_man > 0 else 0
    st.info(
        f'参考: 効率的な投資上限は **{_max_man:,.0f} 万円**（現状の使用率 {_pct_used:.0f}%）です。'
        '詳細は「投資上限分析」ページをご確認ください。'
    )

st.caption('※ この数値はMMMパラメータによる試算値です。実配信環境・クリエイティブ・外部要因により、実績と差異が生じます。')
