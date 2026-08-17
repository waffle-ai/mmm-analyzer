# -*- coding: utf-8 -*-
"""Page 2b — 入力データプレビュー（最初の 50 行）。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import pandas as pd
import streamlit as st

st.title('データプレビュー')

if not st.session_state.get('detect_result'):
    st.warning('先にExcelをアップロードしてください。')
    st.page_link('pages/1_アップロード.py', label='← アップロードページへ')
    st.stop()

_excel_path = st.session_state.get('excel_tmp_path')
_is_demo    = st.session_state.get('_is_demo_user', False) or st.session_state.get('demo_mode', False)

if _excel_path and Path(_excel_path).exists():
    try:
        with st.spinner('データを読み込み中...'):
            df_prev = pd.read_excel(_excel_path, nrows=50)
        st.caption(f'最初の {min(50, len(df_prev))} 行 ／ {len(df_prev.columns)} 列を表示しています。')
        st.dataframe(df_prev, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f'プレビュー読み込みエラー: {e}')
else:
    st.warning('データファイルが見つかりません。')

st.divider()

# ── 分析開始 CTA ──────────────────────────────────────────────────────────
if st.button('分析を開始する →', type='primary'):
    if _is_demo:
        import time
        _stages = [
            (5,   'データを読み込み中...',                0.5),
            (15,  '前処理・特徴量エンジニアリング中...',   1.0),
            (30,  'パレート探索を実行中 (1/3)...',        1.5),
            (50,  'パレート探索を実行中 (2/3)...',        1.8),
            (68,  'L-BFGS-B 最適化中...',               2.0),
            (82,  '予算最適化シナリオを計算中...',         1.5),
            (93,  'レポートを生成中...',                  1.2),
            (100, '分析完了',                             0.5),
        ]
        _bar = st.progress(0, text='分析を準備中...')
        _prev = 0
        for _pct, _label, _dur in _stages:
            _steps = max(1, _pct - _prev)
            _step_sleep = _dur / _steps
            for _s in range(1, _steps + 1):
                _bar.progress(_prev + _s, text=_label)
                time.sleep(_step_sleep)
            _prev = _pct
        time.sleep(0.3)
        st.switch_page('pages/summary.py')
    else:
        # 本番モードはマッピング設定ページへ（data_editor の設定が必要なため）
        st.switch_page('pages/2_マッピング確認.py')

st.page_link('pages/2_マッピング確認.py', label='← マッピング設定へ')
