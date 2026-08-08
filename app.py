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
    'excel_tmp_path':   None,
    'client_name':      '',
    'detect_result':    None,
    'mapping_override': None,
    'job_info':         None,
    'n_trials':         2000,
    'report_type':      'full',
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── ホーム画面 ────────────────────────────────────────────────────────
st.title('MMM Analyzer')
st.markdown('ExcelデータからチャネルごとのROIと予算配分最適化を自動分析します。')

st.divider()
st.page_link('pages/1_アップロード.py', label='分析を開始する', icon='▶')

st.caption('MMM Analyzer v0.1 | Powered by WISEDOM Marketing')
