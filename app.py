# -*- coding: utf-8 -*-
"""MMM SaaS — Streamlit エントリポイント。

起動: streamlit run app.py
"""
import sys
from pathlib import Path

# mmm_engineをimport可能にする（デプロイ時はmmm_engineがルートに同居）
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

# セッション状態の初期化（ページ遷移前に必ず実行）
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

st.switch_page('pages/1_アップロード.py')
