# -*- coding: utf-8 -*-
"""MMM SaaS — Streamlit エントリポイント。起動: streamlit run app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

st.set_page_config(page_title='MMM Analyzer', page_icon='📊', layout='wide')

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

pg = st.navigation([
    st.Page('pages/1_アップロード.py', title='データ読み込み', default=True),
    st.Page('pages/2_マッピング確認.py', title='マッピング確認'),
    st.Page('pages/3_結果.py', title='結果'),
])
pg.run()
