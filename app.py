# -*- coding: utf-8 -*-
"""MMM SaaS — Streamlit エントリポイント。

起動: streamlit run app.py
"""
import sys
from pathlib import Path

# mmm_engineをimport可能にする（デプロイ時はmmm_engineがルートに同居）
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

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

# ── ホーム画面 ────────────────────────────────────────────────────────
st.title('📊 MMM Analyzer')
st.markdown('**マーケティングミックスモデリング** — Excelをアップロードするだけで分析・レポート生成まで自動実行します。')

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown('### 1. アップロード')
    st.markdown('広告・CVデータのExcelをアップロード。列マッピングを自動検出します。')
with col2:
    st.markdown('### 2. マッピング確認')
    st.markdown('自動検出結果を確認・修正してから分析を開始。')
with col3:
    st.markdown('### 3. 結果 & ダウンロード')
    st.markdown('KPIをダッシュボードで確認し、PPTXレポートをダウンロード。')

st.divider()
st.page_link('pages/1_アップロード.py', label='はじめる →', icon='📁')

st.caption('MMM Analyzer v0.1 MVP | Powered by WISEDOM Marketing')
