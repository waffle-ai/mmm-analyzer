# -*- coding: utf-8 -*-
"""Page 3 — 分析進捗モニター & 結果ダッシュボード & PPTXダウンロード。"""
import sys
import time
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))  # repo root

import pandas as pd
import streamlit as st

import runner as r
import sidebar_progress

st.set_page_config(page_title='結果 | MMM Analyzer', page_icon='📊', layout='wide')
sidebar_progress.show_step_progress(3)

st.title('📊 Step 3 / 3 — 分析結果')

# ── ジョブ確認 ────────────────────────────────────────────────────────
if not st.session_state.get('job_info'):
    st.warning('まだ分析が開始されていません。')
    st.page_link('pages/1_アップロード.py', label='← アップロードページへ', icon='📁')
    st.stop()

job_info = st.session_state['job_info']
status   = r.get_job_status(job_info)

# ── 実行中: ログをリアルタイム表示 ───────────────────────────────────
if status['status'] == 'running':
    st.info('分析を実行中です... 完了まで数分〜十数分かかります。ページは自動的に更新されます。')
    progress_placeholder = st.empty()
    log_placeholder      = st.empty()

    with progress_placeholder.container():
        st.progress(0, text='分析中...')

    log_text = status.get('log_tail', '')
    with log_placeholder.container():
        st.text_area('実行ログ', value=log_text, height=300, disabled=True)

    # ログキーワードからプログレスを推定（パレート探索中も進捗が見えるよう細分化）
    _MARKERS = [
        ('Step 9:',         95, 'レポート生成中...'),
        ('Step 8c:',        90, '投資効率フロンティア計算中...'),
        ('Step 8b-2:',      87, '予算削減シナリオ計算中...'),
        ('Step 8b:',        84, '予算増額シナリオ計算中...'),
        ('Step 8:',         80, '予算最適化中...'),
        ('最終メトリクス算出', 75, 'チャネル指標を集計中...'),
        ('採用ダミー:',      70, 'ダミー変数選定完了'),
        ('ダミー変数自動探索', 60, 'ダミー変数を探索中...'),
        ('最適化後:',        55, 'L-BFGS-B 最適化完了'),
        ('L-BFGS-B',        50, 'L-BFGS-B 局所最適化中...'),
        ('Best Pareto:',     45, 'パレート探索完了'),
        ('パレート探索',      35, 'パレート探索中（最も時間がかかります）...'),
        ('Steps 4',          32, 'モデル訓練を開始...'),
        ('Step 3.5:',        28, '多重共線性チェック中...'),
        ('Step 3:',          25, 'ホールドアウト分割中...'),
        ('Step 2.8:',        20, 'スパースチャネル処理中...'),
        ('Step 2.5:',        17, 'Prophetベースライン分解中...'),
        ('Step 2:',          13, '前処理中...'),
        ('Step 1.5:',        10, 'データ構造を分析中...'),
        ('Step 1:',           5, 'データを読み込み中...'),
    ]
    pct, label = 2, '分析を準備中...'
    for keyword, p, lbl in _MARKERS:
        if keyword in log_text:
            pct, label = p, lbl
            break
    progress_placeholder.progress(pct, text=label)

    time.sleep(3)
    st.rerun()

# ── 失敗 ──────────────────────────────────────────────────────────────
elif status['status'] == 'failed':
    st.error('分析が失敗しました。ログを確認してください。')
    st.text_area('エラーログ', value=status.get('log_tail', ''), height=400)
    st.page_link('pages/1_アップロード.py', label='← やり直す', icon='📁')
    st.stop()

# ── 完了 ──────────────────────────────────────────────────────────────
else:
    st.success('分析が完了しました！')

    summary = r.load_summary(status['json_path'])

    # ── 推奨アクション ────────────────────────────────────────────────
    _ch_all   = summary.get('channels', {})
    _ch_valid = {ch: v for ch, v in _ch_all.items() if not v.get('is_zero', False)}
    if _ch_valid:
        _by_roi   = sorted(_ch_valid.items(), key=lambda x: x[1].get('roi', 0), reverse=True)
        _top_ch, _top_v = _by_roi[0]
        _cv_lift  = summary.get('cv_lift_pct', 0)
        _lift_str = f'+{_cv_lift:.1f}%' if _cv_lift >= 0 else f'{_cv_lift:.1f}%'
        _sat_chs  = [ch for ch, v in _by_roi if v.get('saturation_label') == '高']

        st.subheader('推奨アクション')
        _n    = 3 if _sat_chs else 2
        _cols = st.columns(_n)
        _cols[0].success(
            f'**増額を検討: {_top_ch}**\n\n'
            f'ROI {_top_v["roi"]:.2f}x — 最も効率の高いチャネルです。'
        )
        _cols[1].info(
            f'**配分最適化で {_lift_str} CV向上**\n\n'
            '同じ予算のまま、下のROI表を参考に高ROIチャネルへ配分をシフトしましょう。'
        )
        if _sat_chs:
            _cols[2].warning(
                f'**飽和に注意: {_sat_chs[0]}**\n\n'
                '追加投資の限界効用が低下しています。他チャネルへの振り替えを検討してください。'
            )
        st.divider()

    # ── KPIサマリー ──────────────────────────────────────────────────
    st.subheader('モデル精度')
    m1, m2, m3, m4 = st.columns(4)
    m1.metric('R²',           f'{summary["r2"]:.3f}',              help='1.0が最高。0.9以上が目安。')
    m2.metric('NRMSE（学習）', f'{summary["nrmse_train"]:.3f}',    help='0.10以下が目標。')
    m3.metric('NRMSE（検証）', f'{summary["nrmse_holdout"]:.3f}',  help='汎化性能。学習と近い値が理想。')
    m4.metric('MAPE',          f'{summary["mape"]*100:.1f}%',      help='平均絶対誤差率。10%以下が目標。')

    st.divider()

    st.subheader('予算最適化サマリー')
    o1, o2, o3 = st.columns(3)
    def _pct_str(v: float) -> str:
        return f'+{v:.1f}%' if v >= 0 else f'{v:.1f}%'

    o1.metric('現状CV',             f'{summary["total_cv"]:,}件')
    o2.metric('最適配分後CV（同予算）', _pct_str(summary['cv_lift_pct']), help='同じ予算で配分を最適化した場合のCV増加率')
    o3.metric(f'増額{int(summary["budget_increase"]*100)}%後CV', _pct_str(summary['cv_lift_pct_b']))

    st.divider()

    # ── チャネル別ROIバー ─────────────────────────────────────────────
    st.subheader('チャネル別ROI')
    channels = summary.get('channels', {})
    if channels:
        ch_df = pd.DataFrame([
            {
                'チャネル':      ch,
                'ROI':          round(v.get('roi', 0), 2),
                'CPA (円)':     int(v.get('cpa', 0) or 0),
                '貢献CV数':     round(v.get('cv_contrib', 0), 1),
                'スペンド (万円)': round(v.get('spend_man', 0), 1),
                '飽和度':       v.get('saturation_label', ''),
                '有効':         not v.get('is_zero', False),
            }
            for ch, v in channels.items()
        ]).sort_values('ROI', ascending=False)

        # 有効チャネルのみ表示
        valid_df = ch_df[ch_df['有効']].drop(columns=['有効'])
        if not valid_df.empty:
            st.bar_chart(valid_df.set_index('チャネル')['ROI'])
            st.dataframe(
                valid_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'ROI':       st.column_config.NumberColumn(format='%.2f'),
                    'CPA (円)':  st.column_config.NumberColumn(format='%d'),
                },
            )

        zero_chs = [ch for ch, v in channels.items() if v.get('is_zero')]
        if zero_chs:
            st.warning(f'効果ゼロと判定されたチャネル: {", ".join(zero_chs)}')

    st.divider()

    # ── ログ表示（折りたたみ） ────────────────────────────────────────
    with st.expander('実行ログを見る'):
        log_text = Path(job_info['log_path']).read_text(encoding='utf-8', errors='replace')
        st.text_area('ログ', value=log_text, height=300, disabled=True)

    st.divider()

    # ── PPTXダウンロード ───────────────────────────────────────────────
    st.subheader('レポートダウンロード')
    pptx_path = Path(status['pptx_path'])
    if pptx_path.exists():
        with open(pptx_path, 'rb') as f:
            st.download_button(
                label='PPTXレポートをダウンロード',
                data=f.read(),
                file_name=pptx_path.name,
                mime='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                type='primary',
            )
    else:
        st.error('PPTXファイルが見つかりません。')

    st.divider()
    st.page_link('pages/1_アップロード.py', label='← 新しい分析を開始する', icon='📁')
