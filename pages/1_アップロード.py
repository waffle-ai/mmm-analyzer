# -*- coding: utf-8 -*-
"""Page 1 — データ読み込み & 列マッピング自動検出。
Excel アップロード / Google Sheets URL の両方に対応。
"""
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))  # repo root (mmm_engine, runner, channel_ext, sheets_loader)

import mmm_engine.src.data_loader as _dl
import streamlit as st
from channel_ext import CHANNEL_KEYWORDS_EXT
import sheets_loader
def _dedup_channel_map(channel_map: dict) -> dict:
    """重複チャネルをマージし、同一列の二重割り当てをスコア優先で解消する。"""
    # Step 1: チャネル名の大文字小文字・アンダースコア揺れを吸収
    groups: dict[str, list] = {}
    for name, entry in channel_map.items():
        key = name.lower().replace('_', '').replace(' ', '')
        groups.setdefault(key, []).append((name, entry))

    merged: dict[str, dict] = {}
    for entries in groups.values():
        # ALL_CAPS でない名を優先、なければ最初の名前
        canonical = next(
            (n for n, _ in entries if n != n.upper()),
            entries[0][0],
        )
        base: dict = {'cost': None, 'media': None, 'cost_score': 0, 'media_score': 0}
        for _, entry in entries:
            for field in ('cost', 'media'):
                if entry.get(field) and not base[field]:
                    base[field] = entry[field]
            for field in ('cost_score', 'media_score'):
                base[field] = max(base[field], entry.get(field, 0))
        merged[canonical] = base

    # Step 2: 同一列が複数チャネルに割り当てられている場合、スコア最大を勝者にする
    for role, score_key in [('cost', 'cost_score'), ('media', 'media_score')]:
        col_best: dict[str, tuple[str, float]] = {}
        for ch, entry in merged.items():
            col = entry.get(role)
            if col:
                score = entry.get(score_key, 0)
                if col not in col_best or score > col_best[col][1]:
                    col_best[col] = (ch, score)

        for ch, entry in merged.items():
            col = entry.get(role)
            if col and col_best.get(col, (None,))[0] != ch:
                entry[role] = None
                entry[score_key] = 0

    # Step 3: cost も media も None になった空チャネルを除去
    return {ch: e for ch, e in merged.items() if e.get('cost') or e.get('media')}


def detect_only_ext(excel_path: str, **kwargs):
    """拡張チャネル定義＋_sコスト認識でdetect_onlyを実行する。"""
    _orig_ch   = _dl.CHANNEL_KEYWORDS
    _orig_role = _dl._detect_role

    _CONTROL_EXT = ['appt', 'appointment', 'アポ']

    def _detect_role_ext(col: str) -> str:
        c = col.lower()
        if any(kw in c for kw in _CONTROL_EXT):
            return 'control'
        if c.endswith('_s') and len(col) > 2:
            return 'cost'
        return _orig_role(col)

    try:
        _dl.CHANNEL_KEYWORDS = CHANNEL_KEYWORDS_EXT
        _dl._detect_role     = _detect_role_ext
        result = _dl.detect_only(excel_path, **kwargs)
        result['mapping']['channel_map'] = _dedup_channel_map(
            result['mapping']['channel_map']
        )
        return result
    finally:
        _dl.CHANNEL_KEYWORDS = _orig_ch
        _dl._detect_role     = _orig_role


def _save_result(tmp_path: str, client_name: str):
    """detect_only_ext を実行して session_state に保存する。成功したら True を返す。"""
    try:
        result = detect_only_ext(tmp_path)
        st.session_state['excel_tmp_path']   = tmp_path
        st.session_state['client_name']      = client_name
        st.session_state['detect_result']    = result
        st.session_state['mapping_override'] = None
        return result, None
    except Exception as e:
        return None, str(e)


st.title('MMM Analyzer')
st.markdown('ExcelデータからチャネルごとのROIと予算配分最適化を自動分析します。')
st.divider()

# ── ① プロジェクト名 ─────────────────────────────────────────────────
st.subheader('① プロジェクト名の入力')
client_name = st.text_input(
    'プロジェクト名',
    value=st.session_state.get('client_name', ''),
    placeholder='例: 株式会社サンプル',
    help='PPTXレポートの表紙に使用します。',
    label_visibility='collapsed',
)

# ── ② データのアップロード ────────────────────────────────────────────
st.subheader('② データのアップロード')
tab_excel, tab_sheets = st.tabs(['Excelアップロード', 'Google Sheetsから読み込む'])

# ── Tab A: Excel ──────────────────────────────────────────────────────
with tab_excel:
    uploaded = st.file_uploader(
        'Excelファイルを選択（.xlsx / .xlsm）',
        type=['xlsx', 'xlsm'],
        help='日次・週次データどちらでも対応。ヘッダー行は自動検出します。',
    )

    if uploaded and client_name:
        if st.button('列マッピングを自動検出する', type='primary'):
            with st.spinner('Excelを解析中...'):
                suffix = Path(uploaded.name).suffix
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(uploaded.read())
                tmp.flush()
                tmp.close()

                result, err = _save_result(tmp.name, client_name)
                if err:
                    st.error(f'解析エラー: {err}')
                    st.stop()
                else:
                    st.success(f'検出完了！ シート: {result["sheet_name"]} / {result["n_rows"]}行 / 頻度: {result["freq_guess"]}')
                    st.info('次のページでマッピングを確認・修正してから分析を開始してください。')
    elif not client_name:
        st.caption('クライアント名を入力するとアップロードできます。')

# ── Tab B: Google Sheets ──────────────────────────────────────────────
with tab_sheets:
    st.caption('シートを「リンクを知っている全員が閲覧可」に設定してからURLを貼ってください。')
    sheets_url = st.text_input(
        'Google SheetsのURL',
        placeholder='https://docs.google.com/spreadsheets/d/...',
        help='特定のタブを読み込む場合は、そのタブを開いた状態のURLをコピーしてください。',
    )

    if sheets_url and client_name:
        if st.button('シートを読み込む', type='primary'):
            with st.spinner('Google Sheetsからデータを取得中...'):
                try:
                    tmp_path = sheets_loader.sheets_to_excel_tmp(sheets_url)
                except ValueError as e:
                    st.error(str(e))
                    st.stop()

                result, err = _save_result(tmp_path, client_name)
                if err:
                    st.error(f'解析エラー: {err}')
                    st.stop()
                else:
                    st.success(f'読み込み完了！ {result["n_rows"]}行 / 頻度: {result["freq_guess"]}')
                    st.info('次のページでマッピングを確認・修正してから分析を開始してください。')
    elif not client_name:
        st.caption('クライアント名を入力するとURLを入力できます。')

# ── 検出済みの場合はプレビュー表示 ───────────────────────────────────
if st.session_state.get('detect_result'):
    result  = st.session_state['detect_result']
    mapping = result['mapping']
    st.divider()
    st.subheader('自動検出結果プレビュー')

    col1, col2 = st.columns(2)
    with col1:
        st.metric('DATE列', mapping['date_col'] or '未検出 ⚠')
        st.metric('CV列',   mapping['cv_col']   or '未検出 ⚠')
    with col2:
        st.metric('検出チャネル数',   len(mapping['channel_map']))
        st.metric('未マッピング列数', len(mapping.get('unmapped', [])))

    if mapping.get('unmapped'):
        st.warning(f'未マッピング列: {", ".join(mapping["unmapped"][:10])}')

    st.page_link('pages/2_マッピング確認.py', label='マッピング確認へ →')
