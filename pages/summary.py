# -*- coding: utf-8 -*-
"""分析サマリ — 精度グレード・主要指標・推奨アクションの概要。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import streamlit as st
import runner as r

_COL_PRIMARY = '#315E6D'
_COL_GREEN   = '#7EBEAB'
_COL_AMBER   = '#CB8013'

st.title('分析サマリ')
st.markdown("""
<div style="background:#EAF4F0;border-left:4px solid #315E6D;border-radius:0 8px 8px 0;
     padding:12px 16px;margin-bottom:20px;">
  <span style="color:#314858;font-size:15px;">
    モデルの精度グレード・主要KPI・推奨アクションを一覧できます。
    各詳細ページへのリンクからさらに深掘りできます。
  </span>
</div>""", unsafe_allow_html=True)

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

st.markdown(f"""
<div style="background:#F3F7F4;border-radius:12px;padding:20px 24px 18px;
            margin-bottom:20px;border:1px solid #DAEBE5;">
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
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px;">
    <div style="background:#fff;border-radius:8px;padding:11px 14px;border:1px solid #DAEBE5;">
      <div style="color:#5C9291;font-size:10px;text-transform:uppercase;
           letter-spacing:.08em;margin-bottom:3px;">分析チャネル数</div>
      <div style="font-size:20px;font-weight:700;color:#314858;">
        {n_active_ch}<span style="font-size:12px;font-weight:400;color:#5C9291;"> ch</span>
      </div>
    </div>
    <div style="background:#fff;border-radius:8px;padding:11px 14px;border:1px solid #DAEBE5;">
      <div style="color:#5C9291;font-size:10px;text-transform:uppercase;
           letter-spacing:.08em;margin-bottom:3px;">CV 実績</div>
      <div style="font-size:20px;font-weight:700;color:#314858;">
        {_total_cv:,}<span style="font-size:12px;font-weight:400;color:#5C9291;"> 件</span>
      </div>
    </div>
    <div style="background:#fff;border-radius:8px;padding:11px 14px;border:1px solid #DAEBE5;">
      <div style="color:#5C9291;font-size:10px;text-transform:uppercase;
           letter-spacing:.08em;margin-bottom:3px;">同予算 CV改善</div>
      <div style="font-size:20px;font-weight:700;color:{_cv_lift_color};">
        {_pct_str(_cv_lift)}
      </div>
    </div>
    <div style="background:#fff;border-radius:8px;padding:11px 14px;border:1px solid #DAEBE5;">
      <div style="color:#5C9291;font-size:10px;text-transform:uppercase;
           letter-spacing:.08em;margin-bottom:3px;">平均{_eff_label}</div>
      <div style="font-size:20px;font-weight:700;color:#314858;">
        {_avg_eff_display}<span style="font-size:12px;font-weight:400;color:#5C9291;"> {_avg_eff_unit}</span>
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
  </div>
</div>""", unsafe_allow_html=True)

# ── 詳細分析へのナビゲーション ────────────────────────────────────────────
st.divider()
st.markdown('**詳細分析ページ**')
c1, c2, c3 = st.columns(3)
with c1:
    st.page_link('pages/6_model.py',  label='モデル精度 →')
    st.page_link('pages/5_detail.py', label='チャネル詳細 →')
with c2:
    st.page_link('pages/3_結果.py',   label='ROI・CPA分析 →')
    st.page_link('pages/4_budget.py', label='予算配分分析 →')
with c3:
    st.page_link('pages/7_frontier.py',      label='投資上限分析 →')
    st.page_link('pages/8_budget_change.py', label='予算増額・減額分析 →')
