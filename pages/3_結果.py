# -*- coding: utf-8 -*-
"""Page 3 — ROI分析（分析進捗モニター & ROI / CPA / 限界ROI）。"""
import sys
import time
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import pandas as pd
import plotly.express as px
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
    '適正域':     '#7EBEAB',
    '飽和域':     '#CB8013',
    '係数ゼロ':   '#CCCCCC',
}

st.title('ROI・CPA分析')
st.markdown('<p class="page-lede">各チャネルの費用対効果（ROI・CPA・限界ROI）を横断比較し、どこに投資すれば最も効率良くCVを増やせるかが分かります。</p>', unsafe_allow_html=True)

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
    summary  = r.load_summary(job_info['json_path'])
    log_text = Path(job_info['log_path']).read_text(encoding='utf-8', errors='replace')
    status   = {'status': 'completed', 'json_path': job_info['json_path'],
                 'log_tail': log_text, 'pptx_path': None}
else:
    status = r.get_job_status(job_info)

# ── 実行中 ───────────────────────────────────────────────────────────────
if status['status'] == 'running':
    st.info('分析を実行中です... 完了まで数分〜十数分かかります。ページは自動的に更新されます。')
    prog_ph = st.empty()
    prog_ph.progress(0, text='分析中...')

    log_text = status.get('log_tail', '')

    _MARKERS = [
        ('Step 9:',            95, 'レポートを生成中...'),
        ('Step 8c:',           90, '分析結果を最終調整中...'),
        ('Step 8b-2:',         87, '予算シナリオを計算中...'),
        ('Step 8b:',           84, '予算シナリオを計算中...'),
        ('Step 8:',            80, '予算配分を最適化中...'),
        ('最終メトリクス算出',  75, '指標を集計中...'),
        ('採用ダミー:',         70, 'データ処理を完了中...'),
        ('ダミー変数自動探索',  60, 'データパターンを分析中...'),
        ('最適化後:',           55, 'モデルを調整中...'),
        ('L-BFGS-B',           50, 'モデルを最適化中...'),
        ('Best Pareto:',        45, '最適な設定を選定中...'),
        ('パレート探索',         35, '複数パターンを検証中（最も時間がかかります）...'),
        ('Steps 4',             32, 'モデルを構築中...'),
        ('Step 3.5:',           28, 'データを検証中...'),
        ('Step 3:',             25, 'データを分割中...'),
        ('Step 2.8:',           20, 'データを前処理中...'),
        ('Step 2.5:',           17, '季節性を分析中...'),
        ('Step 2:',             13, 'データを前処理中...'),
        ('Step 1.5:',           10, 'データ構造を確認中...'),
        ('Step 1:',              5, 'データを読み込み中...'),
    ]
    pct, label = 2, '分析を準備中...'
    for keyword, p, lbl in _MARKERS:
        if keyword in log_text:
            pct, label = p, lbl
            break
    prog_ph.progress(pct, text=label)
    time.sleep(3)
    st.rerun()

# ── 失敗 ─────────────────────────────────────────────────────────────────
elif status['status'] == 'failed':
    st.error('分析が失敗しました。データ内容（ヘッダー行・DATE列・数値列）をご確認のうえ、再度お試しください。'
              '解消しない場合はサポートまでご連絡ください。')
    st.page_link('pages/1_アップロード.py', label='← やり直す')
    st.stop()

# ── 完了 ─────────────────────────────────────────────────────────────────
else:
    if not _is_demo:
        summary = r.load_summary(status['json_path'])

    def _pct_str(v):
        return f'+{v:.1f}%' if v >= 0 else f'{v:.1f}%'

    _r2        = summary.get('r2', 0)
    _nrmse_t   = summary.get('nrmse_train', 0)
    _nrmse_h   = summary.get('nrmse_holdout', 0)
    _mape      = summary.get('mape', 0)
    _total_cv  = summary.get('total_cv', 0)
    _cv_lift   = summary.get('cv_lift_pct', 0)
    _cv_lift_b = summary.get('cv_lift_pct_b', 0)
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
    def _mape_lbl(v):  return '◎' if v < 0.08  else '○' if v < 0.10  else '△' if v < 0.12  else '×'
    def _badge_cls(l): return {'◎': 'b-s', '○': 'b-a', '△': 'b-b', '×': 'b-c'}.get(l, 'b-c')

    r2_l = _r2_lbl(_r2);    r2_c  = _badge_cls(r2_l)
    nt_l = _nrms_lbl(_nrmse_t); nt_c = _badge_cls(nt_l)
    nh_l = _nrmsh_lbl(_nrmse_h); nh_c = _badge_cls(nh_l)
    mp_l = _mape_lbl(_mape); mp_c = _badge_cls(mp_l)

    cv_cls  = 'kpi-up'    if _cv_lift   >= 0 else ''
    cvb_cls = 'kpi-amber' if _cv_lift_b >  0 else ''

    # ── KPI ストリップ（ホバーツールチップ付き）──────────────────────────
    st.markdown("""<style>
    .kpi-row{display:flex;gap:1px;background:#C5DFD9;border-radius:10px;overflow:visible;margin-bottom:24px;}
    .kpi-cell{flex:1;background:#F9FDFC;padding:12px 14px;min-width:0;position:relative;cursor:default;}
    .kpi-row .kpi-cell:first-child{border-radius:10px 0 0 10px;}
    .kpi-row .kpi-cell:last-child{border-radius:0 10px 10px 0;}
    .kpi-lbl{font-size:10px;color:#5C9291;text-transform:uppercase;letter-spacing:.08em;
             white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .kpi-val{font-size:20px;font-weight:700;color:#314858;line-height:1.3;margin-top:3px;
             display:flex;align-items:center;gap:6px;}
    .kpi-up{color:#315E6D!important;}
    .kpi-amber{color:#CB8013!important;}
    .kpi-tip{
        visibility:hidden;opacity:0;
        position:absolute;top:calc(100% + 8px);left:50%;transform:translateX(-50%);
        background:#314858;color:#F3F7F4;font-size:11.5px;padding:10px 14px;
        border-radius:6px;width:230px;z-index:9999;
        transition:opacity 0.15s;pointer-events:none;
        white-space:normal;line-height:1.55;
        box-shadow:0 4px 12px rgba(0,0,0,.25);
    }
    .kpi-cell:hover .kpi-tip{visibility:visible;opacity:1;}
    .kpi-row .kpi-cell:first-child .kpi-tip{left:0;transform:none;}
    .kpi-row .kpi-cell:last-child .kpi-tip{left:auto;right:0;transform:none;}
    </style>""", unsafe_allow_html=True)

    st.markdown(f"""<div class="kpi-row">
      <div class="kpi-cell">
        <div class="kpi-lbl">R²（決定係数）</div>
        <div class="kpi-val">{_r2:.3f}<span class="kpi-badge {r2_c}">{r2_l}</span></div>
        <div class="kpi-tip">成果の何%をモデルが説明できているかを示します。<br>◎ ≥0.90 &nbsp;○ ≥0.85 &nbsp;△ ≥0.80 &nbsp;× それ未満</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-lbl">NRMSE 学習</div>
        <div class="kpi-val">{_nrmse_t:.3f}<span class="kpi-badge {nt_c}">{nt_l}</span></div>
        <div class="kpi-tip">学習データに対する予測誤差（小さいほど良い）。<br>◎ &lt;0.10 &nbsp;○ &lt;0.12 &nbsp;△ &lt;0.15 &nbsp;× それ以上</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-lbl">NRMSE 検証</div>
        <div class="kpi-val">{_nrmse_h:.3f}<span class="kpi-badge {nh_c}">{nh_l}</span></div>
        <div class="kpi-tip">未学習データへの予測誤差（汎化性能の指標）。<br>◎ &lt;0.15 &nbsp;○ &lt;0.20 &nbsp;△ &lt;0.25 &nbsp;× それ以上</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-lbl">MAPE</div>
        <div class="kpi-val">{_mape*100:.1f}%<span class="kpi-badge {mp_c}">{mp_l}</span></div>
        <div class="kpi-tip">実績値とモデル予測の平均乖離率。<br>◎ &lt;8% &nbsp;○ &lt;10% &nbsp;△ &lt;12% &nbsp;× それ以上</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-lbl">CV 実績</div>
        <div class="kpi-val">{_total_cv:,}件</div>
        <div class="kpi-tip">分析期間の合計コンバージョン数（広告起因・ベースライン含む）。</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-lbl">同予算 CV改善</div>
        <div class="kpi-val {cv_cls}">{_pct_str(_cv_lift)}</div>
        <div class="kpi-tip">同じ総広告費のまま配分をROI比例に最適化した場合の推定CV増加率。</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-lbl">増額{int(_budget_inc*100)}% CV改善</div>
        <div class="kpi-val {cvb_cls}">{_pct_str(_cv_lift_b)}</div>
        <div class="kpi-tip">総広告費を{int(_budget_inc*100)}%増額かつ最適配分した場合の推定CV増加率。</div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── チャネル DataFrame ──────────────────────────────────────────────
    if channels:
        ch_df = pd.DataFrame([
            {
                'チャネル':       ch,
                'ROI':           round(v.get('roi', 0), 2),
                'CPA (円)':      int(v.get('cpa', 0) or 0),
                '貢献CV数':      round(v.get('cv_contrib', 0), 1),
                '広告費 (万円)':  round(v.get('spend_man', 0), 1),
                '飽和度':        v.get('saturation_label', ''),
                '限界ROI':       round(v.get('marginal_roi', 0), 2),
                '有効':          not v.get('is_zero', False),
            }
            for ch, v in channels.items()
        ]).sort_values('ROI', ascending=False)

        valid_df = ch_df[ch_df['有効']].drop(columns=['有効'])

        st.divider()
        st.caption(
            '飽和度: 伸び代あり=増額で効果が見込める / 適正域=現状が効率的 / '
            '飽和域=追加投資しても伸びにくい / 係数ゼロ=効果を検出できず'
        )

        if _is_monetary:
            # ── ROAS/ROI バー（monetary mode のみ） ──────────────────────
            # monetary: roi*100 を % として表示
            roi_pct_df = valid_df.copy()
            roi_pct_df['ROAS/ROI (%)'] = (roi_pct_df['ROI'] * 100).round(1)
            roi_sorted = roi_pct_df.sort_values('ROAS/ROI (%)')
            st.subheader(f'チャネル別 {_eff_label}')
            fig_roi = px.bar(
                roi_sorted, x='ROAS/ROI (%)', y='チャネル', orientation='h',
                color='ROAS/ROI (%)',
                color_continuous_scale=[[0, '#A2CEBF'], [0.5, '#5C9291'], [1.0, '#315E6D']],
                text='ROAS/ROI (%)',
                labels={'ROAS/ROI (%)': f'{_eff_label}（%）'},
            )
            fig_roi.update_traces(texttemplate='%{text:.1f}%', textposition='outside', textfont_size=12)
            fig_roi.update_layout(
                coloraxis_showscale=False,
                margin=dict(l=10, r=80, t=10, b=10),
                height=max(320, len(roi_sorted) * 58),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            )
            fig_roi.update_xaxes(gridcolor='#DAEBE5', gridwidth=1)
            fig_roi.update_yaxes(gridcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_roi, use_container_width=True)
            _top_roi_ch = roi_sorted.iloc[-1]['チャネル']
            st.caption(f'{_eff_label}が最も高いのは【{_top_roi_ch}】です。')

        # ── CPA バー ────────────────────────────────────────────────────
        # count mode: 主指標として先頭表示 / monetary mode: 補足として表示
        if not _is_monetary:
            st.subheader(f'チャネル別 {_eff_label}（主指標）')
        else:
            st.subheader('チャネル別 CPA（補足）')
        cpa_sorted = valid_df[valid_df['CPA (円)'] > 0].sort_values('CPA (円)', ascending=False)
        if not cpa_sorted.empty:
            fig_cpa = px.bar(
                cpa_sorted, x='CPA (円)', y='チャネル', orientation='h',
                color='CPA (円)',
                color_continuous_scale=[[0, '#315E6D'], [0.5, '#5C9291'], [1.0, '#A2CEBF']],
                text='CPA (円)',
                labels={'CPA (円)': 'CPA（円）'},
            )
            fig_cpa.update_traces(texttemplate='¥%{text:,}', textposition='outside', textfont_size=11)
            fig_cpa.update_layout(
                coloraxis_showscale=False,
                margin=dict(l=10, r=90, t=10, b=10),
                height=max(280, len(cpa_sorted) * 52),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            )
            fig_cpa.update_xaxes(gridcolor='#DAEBE5')
            fig_cpa.update_yaxes(gridcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_cpa, use_container_width=True)
            if not _is_monetary:
                _top_cpa_ch = cpa_sorted.iloc[-1]['チャネル']
                st.caption(f'CPAが最も低いのは【{_top_cpa_ch}】です。')

        # ── 貢献CV数バー（count mode のみ） ─────────────────────────────
        if not _is_monetary and valid_df['貢献CV数'].sum() > 0:
            st.subheader('チャネル別 貢献CV数')
            st.caption('分析期間中に各チャネルが起因したCV件数の推定値です。')
            cv_sorted = valid_df[valid_df['貢献CV数'] > 0].sort_values('貢献CV数')
            fig_cv = px.bar(
                cv_sorted, x='貢献CV数', y='チャネル', orientation='h',
                color='貢献CV数',
                color_continuous_scale=[[0, '#A2CEBF'], [0.5, '#5C9291'], [1.0, '#315E6D']],
                text='貢献CV数',
                labels={'貢献CV数': '貢献CV数（件）'},
            )
            fig_cv.update_traces(texttemplate='%{text:.0f}件', textposition='outside', textfont_size=11)
            fig_cv.update_layout(
                coloraxis_showscale=False,
                margin=dict(l=10, r=80, t=10, b=10),
                height=max(280, len(cv_sorted) * 52),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            )
            fig_cv.update_xaxes(gridcolor='#DAEBE5')
            fig_cv.update_yaxes(gridcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_cv, use_container_width=True)

        # ── 限界ROI バー（monetary mode のみ） ──────────────────────────
        if _is_monetary and valid_df['限界ROI'].sum() > 0:
            st.subheader(f'チャネル別 限界{_eff_label}（追加1円あたりの効果）')
            st.caption(f'限界{_eff_label} = 現在の投資水準で追加投資したときの{_eff_label}。平均より低いほど飽和が進んでいます。')
            mroi_sorted = valid_df[valid_df['限界ROI'] > 0].sort_values('限界ROI')
            if not mroi_sorted.empty:
                fig_mroi = px.bar(
                    mroi_sorted, x='限界ROI', y='チャネル', orientation='h',
                    color='限界ROI',
                    color_continuous_scale=[[0, '#A2CEBF'], [0.5, '#5C9291'], [1.0, '#315E6D']],
                    text='限界ROI',
                    labels={'限界ROI': f'限界{_eff_label}（倍）'},
                )
                fig_mroi.update_traces(texttemplate='%{text:.2f}倍', textposition='outside', textfont_size=11)
                fig_mroi.update_layout(
                    coloraxis_showscale=False,
                    margin=dict(l=10, r=80, t=10, b=10),
                    height=max(280, len(mroi_sorted) * 52),
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                )
                fig_mroi.update_xaxes(gridcolor='#DAEBE5')
                fig_mroi.update_yaxes(gridcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_mroi, use_container_width=True)

    # ── フッター ─────────────────────────────────────────────────────────
    st.divider()

    pptx_path = Path(status['pptx_path']) if status.get('pptx_path') else None
    if pptx_path and pptx_path.exists():
        st.subheader('レポートダウンロード')
        with open(pptx_path, 'rb') as f:
            st.download_button(
                label='PPTXレポートをダウンロード',
                data=f.read(),
                file_name=pptx_path.name,
                mime='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                type='primary',
            )

    st.divider()
    st.page_link('pages/1_アップロード.py', label='← 新しい分析を開始する')
