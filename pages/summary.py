# -*- coding: utf-8 -*-
"""分析サマリ — 精度グレード・主要指標・推奨アクションの概要。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import datetime as _dt

import pandas as pd
import plotly.express as px
import streamlit as st
import runner as r

_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_AMBER   = '#CB8013'
_COL_LIGHT   = '#A2CEBF'

st.title('分析サマリ')
st.markdown('<p class="page-lede">モデルの精度グレード・主要KPI・推奨アクションを一覧できます。各詳細ページへのリンクからさらに深掘りできます。</p>', unsafe_allow_html=True)

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

def _pct_str(v):
    return f'+{v:.1f}%' if v >= 0 else f'{v:.1f}%'

_r2        = summary.get('r2', 0)
_nrmse_t   = summary.get('nrmse_train', 0)
_nrmse_h   = summary.get('nrmse_holdout', 0)
_rssd      = summary.get('rssd', None)
_total_cv  = summary.get('total_cv', 0)
_cv_lift   = summary.get('cv_lift_pct', 0)
_budget_inc = summary.get('budget_increase', 0.3)

channels, _dup_warn = r.dedup_channels(summary.get('channels', {}))
if _dup_warn:
    st.warning('同名の可能性があるチャネルが複数あります。マッピングを確認して再実行してください（' + '、'.join(_dup_warn) + '）。')
_ch_valid    = {ch: v for ch, v in channels.items() if not v.get('is_zero', False)}
_cv_type     = summary.get('cv_metric_type', 'count')
_is_monetary = _cv_type == 'monetary'
_eff_label   = 'ROAS / ROI' if _is_monetary else 'CPA'
_eff_unit    = '%' if _is_monetary else '円'
_total_spend = summary.get('total_spend', 0)

# ── 分析期間（実測/予測の時系列データから算出） ──────────────────────────
_avp = summary.get('actual_vs_pred', {})
_avp_dates = (_avp.get('dates_train') or []) + (_avp.get('dates_hold') or [])
if _avp_dates:
    _d0 = _dt.date.fromisoformat(_avp_dates[0])
    _d1 = _dt.date.fromisoformat(_avp_dates[-1])
    _period_str = f'{_d0.year}年{_d0.month}月<br>〜{_d1.year}年{_d1.month}月'
else:
    _period_str = None

# ── チャネル別 現状/最適配分・推奨アクション ──────────────────────────────
_channel_opt = summary.get('channel_opt', {})

def _derive_action(ch, opt):
    cur = channels.get(ch, {}).get('spend_man', 0) * 10000
    if 'action' in opt:
        return opt['action'], opt.get('delta_spend', opt.get('optimal_spend', 0) - cur), cur
    delta = opt.get('optimal_spend', 0) - cur
    is_zero = channels.get(ch, {}).get('is_zero', False)
    if is_zero:
        act = '停止・効果検証'
    elif cur <= 0:
        act = '新規投資検討'
    else:
        ratio = delta / cur
        act = '増額推奨' if ratio >= 0.20 else '削減推奨' if ratio <= -0.20 else '現状維持'
    return act, delta, cur

_ch_actions = {}
for _ch, _opt in _channel_opt.items():
    _act, _delta, _cur = _derive_action(_ch, _opt)
    _ch_actions[_ch] = {
        'action': _act, 'delta': _delta, 'current_spend': _cur,
        'optimal_spend': _opt.get('optimal_spend', 0),
    }

_inc_chs  = sorted([c for c, v in _ch_actions.items() if v['action'] == '増額推奨'],
                    key=lambda c: -_ch_actions[c]['delta'])
_dec_chs  = sorted([c for c, v in _ch_actions.items() if v['action'] == '削減推奨'],
                    key=lambda c: _ch_actions[c]['delta'])
_stop_chs = [c for c, v in _ch_actions.items() if v['action'] in ('停止・効果検証', '新規投資検討')]

_abs_cv_gain = round(_total_cv * (_cv_lift / 100), 0) if _total_cv else 0

def _r2_lbl(v):    return '◎' if v >= 0.90 else '○' if v >= 0.85 else '△' if v >= 0.80 else '×'
def _nrms_lbl(v):  return '◎' if v < 0.10  else '○' if v < 0.12  else '△' if v < 0.15  else '×'
def _nrmsh_lbl(v): return '◎' if v < 0.15  else '○' if v < 0.20  else '△' if v < 0.25  else '×'
def _rssd_lbl(v):
    if v is None: return '?'
    return '◎' if 0.10 <= v <= 0.20 else '○' if v <= 0.30 else '△' if v <= 0.40 else '×'

r2_l = _r2_lbl(_r2)
nt_l = _nrms_lbl(_nrmse_t)
nh_l = _nrmsh_lbl(_nrmse_h)
rs_l = _rssd_lbl(_rssd)

_grade_score = sum([
    3 if r2_l == '◎' else 2 if r2_l == '○' else 1 if r2_l == '△' else 0,
    3 if nt_l == '◎' else 2 if nt_l == '○' else 1 if nt_l == '△' else 0,
    3 if nh_l == '◎' else 2 if nh_l == '○' else 1 if nh_l == '△' else 0,
    2 if rs_l == '◎' else 1 if rs_l == '○' else 0,
])
if _grade_score >= 9:   _grade, _grade_color = 'A+', _COL_PRIMARY
elif _grade_score >= 7: _grade, _grade_color = 'A',  _COL_GREEN
elif _grade_score >= 4: _grade, _grade_color = 'B',  _COL_AMBER
else:                    _grade, _grade_color = 'C',  '#999'
_grade_msgs = {
    'A+': '非常に高い精度のモデルです。結果を本番施策に活用できます。',
    'A':  '十分な精度のモデルです。実務判断の参考として活用できます。',
    'B':  'やや低い精度です。傾向把握に留め、数値を過信しないでください。',
    'C':  '精度が低く、結果の信頼性が限定的です。データの見直しを推奨します。',
}
_grade_msg = _grade_msgs[_grade]

n_active_ch = len(_ch_valid)
if _ch_valid:
    if _is_monetary:
        _avg_eff   = sum(v.get('roi', 0) * 100 for v in _ch_valid.values()) / len(_ch_valid)
        _top_ch_s  = max(_ch_valid, key=lambda k: _ch_valid[k].get('roi', 0))
        _top_eff_s = _ch_valid[_top_ch_s].get('roi', 0) * 100
    else:
        _cpa_vals  = [v.get('cpa', 0) for v in _ch_valid.values() if v.get('cpa', 0) > 0]
        _avg_eff   = sum(_cpa_vals) / len(_cpa_vals) if _cpa_vals else 0
        _top_ch_s  = min(_ch_valid, key=lambda k: _ch_valid[k].get('cpa', float('inf')))
        _top_eff_s = _ch_valid[_top_ch_s].get('cpa', 0)
    _sat_chs_s = [ch for ch, v in _ch_valid.items() if v.get('saturation_label') == '飽和域']
else:
    _avg_eff, _top_ch_s, _top_eff_s, _sat_chs_s = 0, '—', 0, []

# 表示用フォーマット
_avg_eff_display = f'{_avg_eff:.1f}' if _is_monetary else f'¥{int(_avg_eff):,}'
_avg_eff_unit    = '%' if _is_monetary else '円'
if _is_monetary:
    _top_action_text = (
        f'<b>{_top_ch_s}</b>（{_eff_label} {_top_eff_s:.1f}%）。'
        f'投資効率がトップで、追加投資の効果が期待できます。'
    )
else:
    _top_action_text = (
        f'<b>{_top_ch_s}</b>（{_eff_label} ¥{int(_top_eff_s):,}）。'
        f'CPAが最小で、追加投資の効果が期待できます。'
    )
_opt_text = 'ROAS/ROI最大' if _is_monetary else 'CPA最小'

_cv_lift_color = '#315E6D' if _cv_lift >= 0 else '#CB8013'

if abs(_cv_lift) < 1:
    _realloc_badge = '現状維持'
    _realloc_text  = '現在の予算配分はすでに効率的です。配分変更による大きな改善余地は検出されませんでした。'
else:
    _realloc_badge = '配分最適化'
    _realloc_text  = (
        f'同一予算のまま配分を{_opt_text}に最適化するだけで'
        f'<b>CV {_pct_str(_cv_lift)}改善</b>が見込めます。'
    )

_sat_html = (
    f'<div style="display:flex;align-items:flex-start;gap:10px;">'
    f'<span style="background:#CB8013;color:#fff;border-radius:999px;padding:2px 8px;'
    f'font-size:11px;font-weight:700;flex-shrink:0;white-space:nowrap;">飽和注意</span>'
    f'<span style="font-size:13px;color:#314858;"><b>{_sat_chs_s[0]}</b> は飽和域に達しています。'
    f'追加投資の限界効用が低下中。他チャネルへの振り替えを検討してください。</span></div>'
) if _sat_chs_s else ''

def _ch_chip_row(badge_bg, badge_fg, badge_label, chs, empty_note=''):
    if not chs:
        if not empty_note:
            return ''
        chs_text = empty_note
    else:
        chs_text = '　／　'.join(f'<b>{c}</b>' for c in chs)
    return (
        f'<div style="display:flex;align-items:flex-start;gap:10px;">'
        f'<span style="background:{badge_bg};color:{badge_fg};border-radius:999px;padding:2px 8px;'
        f'font-size:11px;font-weight:700;flex-shrink:0;white-space:nowrap;">{badge_label}</span>'
        f'<span style="font-size:13px;color:#314858;">{chs_text}</span></div>'
    )

def _ch_action_card(badge_bg, badge_fg, badge_label, chs, empty_note='該当なし'):
    chs_text = '　／　'.join(f'<b>{c}</b>' for c in chs) if chs else f'<span style="color:#9AA3AA;">{empty_note}</span>'
    return (
        f'<div style="flex:1;min-width:180px;background:#fff;border-radius:8px;padding:10px 14px;'
        f'box-shadow:0 0 8px rgba(49,72,88,.08);display:flex;align-items:center;gap:10px;">'
        f'<span style="background:{badge_bg};color:{badge_fg};border-radius:999px;padding:2px 8px;'
        f'font-size:11px;font-weight:700;white-space:nowrap;flex-shrink:0;">{badge_label}</span>'
        f'<span style="font-size:13px;color:#314858;">{chs_text}</span>'
        f'</div>'
    )

_inc_dec_cards = (
    '<div style="display:flex;gap:10px;flex-wrap:wrap;">'
    + _ch_action_card('#315E6D', '#fff', f'増額推奨（{len(_inc_chs)}件）', _inc_chs)
    + _ch_action_card('#5C9291', '#fff', f'削減推奨（{len(_dec_chs)}件）', _dec_chs)
    + '</div>'
)
_stop_row = _ch_chip_row('#CB8013', '#fff', f'停止・要検討（{len(_stop_chs)}件）', _stop_chs)

st.markdown(f"""
<div style="background:#F3F7F4;border-radius:12px;padding:20px 24px 18px;
            margin-bottom:20px;box-shadow:0 1px 4px rgba(49,72,88,.10);">
  <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap;">
    <div style="background:{_grade_color};color:#fff;border-radius:10px;
         min-width:60px;height:60px;display:flex;align-items:center;justify-content:center;
         font-size:28px;font-weight:800;flex-shrink:0;">{_grade}</div>
    <div>
      <div style="font-weight:700;font-size:15px;color:#314858;">
        精度グレード {_grade}　{_grade_msg}
      </div>
      <div style="color:#5C9291;font-size:12px;margin-top:4px;">
        R² {_r2:.3f}&nbsp;｜&nbsp;NRMSE学習 {_nrmse_t:.3f}&nbsp;｜&nbsp;NRMSE検証
        {_nrmse_h:.3f}&nbsp;｜&nbsp;RSSD {f'{_rssd:.3f}' if _rssd is not None else 'N/A'}
      </div>
    </div>
  </div>
  <div class="mmm-card-grid" style="margin-bottom:18px;">
    {f'<div class="mmm-card"><div class="mmm-card-lbl">分析期間</div><div class="mmm-card-val" style="font-size:16px;line-height:1.4;">{_period_str}</div></div>' if _period_str else ''}
    <div class="mmm-card">
      <div class="mmm-card-lbl">分析チャネル数</div>
      <div class="mmm-card-val">
        {n_active_ch}<span class="mmm-card-unit">ch</span>
      </div>
    </div>
    <div class="mmm-card">
      <div class="mmm-card-lbl">CV 実績</div>
      <div class="mmm-card-val">
        {_total_cv:,}<span class="mmm-card-unit">件</span>
      </div>
    </div>
    <div class="mmm-card">
      <div class="mmm-card-lbl">分析期間の広告費合計</div>
      <div class="mmm-card-val">
        {_total_spend/10000:,.0f}<span class="mmm-card-unit">万円</span>
      </div>
    </div>
    <div class="mmm-card">
      <div class="mmm-card-lbl">同予算 CV改善余地</div>
      <div class="mmm-card-val" style="color:{_cv_lift_color};">
        {_pct_str(_cv_lift)}
      </div>
      <div style="font-size:11px;color:#5C9291;margin-top:2px;">
        {f'+{_abs_cv_gain:,.0f}件増加の試算' if _abs_cv_gain > 0 else ''}
      </div>
    </div>
    <div class="mmm-card">
      <div class="mmm-card-lbl">平均{_eff_label}</div>
      <div class="mmm-card-val">
        {_avg_eff_display}<span class="mmm-card-unit">{_avg_eff_unit}</span>
      </div>
    </div>
  </div>
  <div style="border-top:1px solid #DAEBE5;padding-top:14px;">
    <div style="font-weight:700;color:#314858;font-size:13px;margin-bottom:10px;">推奨アクション</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <div style="display:flex;align-items:flex-start;gap:10px;">
        <span style="background:#315E6D;color:#fff;border-radius:999px;padding:2px 8px;
             font-size:11px;font-weight:700;flex-shrink:0;white-space:nowrap;">増額</span>
        <span style="font-size:13px;color:#314858;">
          {_top_action_text}
        </span>
      </div>
      <div style="display:flex;align-items:flex-start;gap:10px;">
        <span style="background:#7EBEAB;color:#314858;border-radius:999px;padding:2px 8px;
             font-size:11px;font-weight:700;flex-shrink:0;white-space:nowrap;">{_realloc_badge}</span>
        <span style="font-size:13px;color:#314858;">
          {_realloc_text}
        </span>
      </div>{_sat_html}
    </div>
    <div style="margin-top:10px;">{_inc_dec_cards}</div>
    <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">{_stop_row}</div>
  </div>
</div>""", unsafe_allow_html=True)

# ── チャネル別 現状 vs 最適配分 ────────────────────────────────────────────
if _ch_actions:
    st.subheader('予算配分：現状 vs 最適')
    st.caption('チャネルごとの現状の広告費と、モデルが試算した最適配分（万円）を比較します。')
    _bar_chs = sorted(_ch_actions.keys(),
                       key=lambda c: _ch_actions[c]['current_spend'], reverse=True)
    _bar_df = pd.DataFrame({
        'チャネル': _bar_chs * 2,
        '広告費 (万円)': (
            [round(_ch_actions[c]['current_spend'] / 10000, 1) for c in _bar_chs]
            + [round(_ch_actions[c]['optimal_spend'] / 10000, 1) for c in _bar_chs]
        ),
        '配分': ['現状'] * len(_bar_chs) + ['最適配分'] * len(_bar_chs),
    })
    fig_smry = px.bar(
        _bar_df, x='チャネル', y='広告費 (万円)', color='配分',
        barmode='group',
        color_discrete_map={'現状': _COL_LIGHT, '最適配分': _COL_PRIMARY},
        labels={'広告費 (万円)': '広告費（万円）'},
    )
    fig_smry.update_layout(
        margin=dict(l=10, r=20, t=10, b=10), height=320,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    fig_smry.update_yaxes(gridcolor='#DAEBE5')
    st.plotly_chart(fig_smry, use_container_width=True)
    st.caption('※ 最適配分はMMMモデルによる試算値です。詳細は「予算配分分析」ページを参照してください。')

# ── 詳細分析へのナビゲーション ────────────────────────────────────────────
st.divider()
st.markdown('**詳細分析ページ**')
c1, c2, c3 = st.columns(3)
with c1:
    st.page_link('pages/6_model.py',  label='モデル精度 →')
    st.page_link('pages/5_detail.py', label='チャネル分析 →')
with c2:
    st.page_link('pages/3_結果.py',   label='ROI・CPA分析 →')
    st.page_link('pages/4_budget.py', label='予算配分分析 →')
with c3:
    st.page_link('pages/7_frontier.py',      label='投資上限分析 →')
    st.page_link('pages/8_budget_change.py', label='予算増額・減額分析 →')
