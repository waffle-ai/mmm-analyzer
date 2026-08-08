# -*- coding: utf-8 -*-
"""Page 2 — チャネルマッピング確認・修正 & 分析起動。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))  # repo root

import pandas as pd
import streamlit as st

from channel_ext import CHANNEL_OPTIONS
import runner

st.caption('Step 2 / 3')
st.title('マッピング確認・修正')

# ── 前ページからのデータ確認 ─────────────────────────────────────────
if not st.session_state.get('detect_result'):
    st.warning('先にExcelをアップロードしてください。')
    st.page_link('pages/1_アップロード.py', label='← アップロードページへ')
    st.stop()

detect_result = st.session_state['detect_result']
mapping       = detect_result['mapping']
excel_path    = st.session_state['excel_tmp_path']
client_name   = st.session_state['client_name']

st.markdown(f'**クライアント:** {client_name} ｜ **シート:** {detect_result["sheet_name"]} ｜ **{detect_result["n_rows"]}行** ｜ **頻度:** {detect_result["freq_guess"]}')
st.divider()

# ── DATE/CV列の確認 ──────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    date_col = st.text_input('DATE列', value=mapping.get('date_col', ''), help='日付が入っている列名')
with col2:
    cv_col = st.text_input('CV列（目的変数）', value=mapping.get('cv_col', ''), help='コンバージョン数が入っている列名')

st.divider()

# ── チャネルマッピングテーブル ────────────────────────────────────────
st.subheader('チャネルマッピング')
st.info(
    '自動検出の結果です。内容を確認し、問題なければ**このままページ下の「分析を開始する」を押してOKです。**'
    '　チャネル名や役割を変更したい場合はドロップダウンで修正できます。'
    '「（未マッピング）」にするとそのチャネルは分析から除外されます。'
)

channel_map = mapping.get('channel_map', {})

# テーブル化: 列名・役割・チャネル名（コスト列）・チャネル名（メディア列）
rows = []
for ch, m in channel_map.items():
    if m.get('cost'):
        rows.append({'列名': m['cost'], '役割': 'コスト', 'チャネル名': ch, '検出スコア': m.get('cost_score', 0)})
    if m.get('media'):
        rows.append({'列名': m['media'], '役割': 'メディア', 'チャネル名': ch, '検出スコア': m.get('media_score', 0)})

# 未マッピング列も表示
for col in mapping.get('unmapped', []):
    rows.append({'列名': col, '役割': '（未確定）', 'チャネル名': '（未マッピング）', '検出スコア': 0.0})

if rows:
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df,
        column_config={
            'チャネル名': st.column_config.SelectboxColumn(
                'チャネル名',
                options=CHANNEL_OPTIONS,
                required=True,
            ),
            '役割': st.column_config.SelectboxColumn(
                '役割',
                options=['コスト', 'メディア', '（未確定）'],
                required=True,
            ),
            '検出スコア': st.column_config.NumberColumn('スコア', format='%.2f', disabled=True),
            '列名': st.column_config.TextColumn('元の列名', disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        num_rows='dynamic',
    )
else:
    st.warning('マッピングされた列が見つかりませんでした。Excelの列名を確認してください。')
    edited = pd.DataFrame()

st.divider()

# ── 分析設定 ──────────────────────────────────────────────────────────
st.subheader('分析設定')
col_a, col_b, col_c = st.columns(3)
with col_a:
    n_trials = st.number_input(
        'パレート探索試行数',
        min_value=50, max_value=5000, value=2000, step=50,
        help='本番: 2000。動作テスト用: 50。少ないほど速いが精度が下がります。',
    )
with col_b:
    report_type = st.selectbox('レポートタイプ', ['full（フルレポート）', 'simple（簡易版）'])
    report_type_val = 'full' if 'full' in report_type else 'simple'
with col_c:
    budget_increase = st.number_input(
        'シナリオB増額率 (%)',
        min_value=10, max_value=100, value=30, step=5,
        help='予算最適化シナリオBの増額率。デフォルト30%。',
    ) / 100

st.divider()

# ── 所要時間の目安 ─────────────────────────────────────────────────────
if not edited.empty:
    n_active_ch = edited[
        (edited['チャネル名'] != '（未マッピング）') & (edited['役割'] != '（未確定）')
    ]['チャネル名'].nunique()
    if n_active_ch > 0:
        est = runner.estimate_duration(int(n_trials), n_active_ch)
        st.info(f'試行数 {int(n_trials):,} × {n_active_ch} チャネル ＝ 処理時間の目安 **{est}**（使用PCのスペックによって変動します）')

# ── 分析開始ボタン ────────────────────────────────────────────────────
if st.button('分析を開始する →', type='primary', disabled=edited.empty):
    # mapping_overrideを構築
    new_channel_map: dict = {}
    for _, row in edited.iterrows():
        ch   = row['チャネル名']
        role = row['役割']
        col  = row['列名']
        if ch == '（未マッピング）' or role == '（未確定）':
            continue
        if ch not in new_channel_map:
            new_channel_map[ch] = {'media': None, 'cost': None, 'media_score': 0, 'cost_score': 0}
        if role == 'コスト':
            new_channel_map[ch]['cost'] = col
        elif role == 'メディア':
            new_channel_map[ch]['media'] = col

    mapping_override = {
        'date_col':    date_col or mapping.get('date_col'),
        'cv_col':      cv_col or mapping.get('cv_col'),
        'channel_map': new_channel_map,
        'control_cols': mapping.get('control_cols', []),
        'unmapped':    [],
    }

    with st.spinner('分析ジョブを起動中...'):
        job_info = runner.start_analysis(
            excel_path=excel_path,
            client_name=client_name,
            mapping_override=mapping_override,
            n_trials=int(n_trials),
            report_type=report_type_val,
            budget_increase=budget_increase,
        )

    st.session_state['job_info']         = job_info
    st.session_state['mapping_override'] = mapping_override
    st.success('分析を開始しました！')
    st.page_link('pages/3_結果.py', label='結果ページへ →')
