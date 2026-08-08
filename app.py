# -*- coding: utf-8 -*-
"""MMM SaaS — Streamlit エントリポイント。

起動: streamlit run app.py
"""
import sys
from pathlib import Path

# mmm_engineをimport可能にする（デプロイ時はmmm_engineがルートに同居）
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import sidebar_progress

st.set_page_config(
    page_title='MMM Analyzer',
    page_icon='📊',
    layout='wide',
    initial_sidebar_state='expanded',
)

# ── セッション状態の初期化 ────────────────────────────────────────────
defaults = {
    'excel_tmp_path':   None,   # アップロードされたExcelの一時パス
    'client_name':      '',
    'detect_result':    None,   # detect_only()の結果
    'mapping_override': None,   # UIで修正済みのマッピング
    'job_info':         None,   # runner.start_analysis()の戻り値
    'n_trials':         2000,
    'report_type':      'full',
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── サイドバー進捗 ────────────────────────────────────────────────────
sidebar_progress.show_step_progress(0)

# ── ホーム画面 ────────────────────────────────────────────────────────
st.title('広告費の効果を、数字で証明する。')
st.markdown(
    'Excelを1枚アップロードするだけで、チャネル別の広告貢献度と'
    '予算配分最適化を自動分析します。'
)
st.caption('⏱ 所要時間 5〜10分 &nbsp;｜&nbsp; 📊 最大15チャネル対応 &nbsp;｜&nbsp; 📄 PPTXレポート自動生成')

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown('### 📁 Step 1')
    st.markdown('**データを読み込む**')
    st.markdown('ExcelまたはGoogle Sheetsを渡すだけ。チャネル列を自動で認識します。')
with col2:
    st.markdown('### 🔍 Step 2')
    st.markdown('**設定を確認する**')
    st.markdown('自動検出の結果を確認。問題なければそのまま分析を開始できます。')
with col3:
    st.markdown('### 📊 Step 3')
    st.markdown('**結果を受け取る**')
    st.markdown('チャネル別ROI・予算最適化シナリオをダッシュボードで確認。PPTXも自動生成。')

st.divider()
st.page_link('pages/1_アップロード.py', label='分析をはじめる →', icon='📁')

st.caption('MMM Analyzer v0.1 MVP | Powered by WISEDOM Marketing')
