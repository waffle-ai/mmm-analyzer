# -*- coding: utf-8 -*-
"""サイドバーに Step 1/2/3 の進捗を表示するユーティリティ。"""
import streamlit as st

_STEPS = [
    (1, '📁', 'データ読み込み'),
    (2, '🔍', 'マッピング確認'),
    (3, '📊', '結果 & ダウンロード'),
]


def show_step_progress(current_step: int) -> None:
    """サイドバーに進捗インジケータを描画する。

    current_step: 0 = ホーム（未開始）, 1-3 = 各ステップ
    """
    with st.sidebar:
        st.markdown('**進行状況**')
        for num, icon, name in _STEPS:
            if num < current_step:
                st.markdown(f'✅ Step {num}&nbsp;&nbsp;{name}')
            elif num == current_step:
                st.markdown(f'**▶ Step {num}&nbsp;&nbsp;{name}**')
            else:
                st.markdown(f'◦ Step {num}&nbsp;&nbsp;{name}')
        st.markdown('---')
