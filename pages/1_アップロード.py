# -*- coding: utf-8 -*-
"""Page 1 — データ読み込み & 列マッピング自動検出。
Excel アップロード / Google Sheets URL の両方に対応。
"""
import base64
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_REPO = _HERE.parent
sys.path.insert(0, str(_REPO))

_LOGO_PATH = _REPO / 'assets' / 'logo.png'
_logo_b64  = (
    'data:image/png;base64,' + base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    if _LOGO_PATH.exists() else ''
)

import mmm_engine.src.data_loader as _dl
import streamlit as st
from channel_ext import CHANNEL_KEYWORDS_EXT
import sheets_loader

_DEMO_JSON = _REPO / 'demo_data' / 'summary.json'
_DEMO_LOG  = _REPO / 'demo_data' / 'run.log'
_DEMO_XLSX = _REPO / 'mmm_engine' / 'data' / 'dt_smb_weekly_dummy.xlsx'


def _dedup_channel_map(channel_map: dict) -> dict:
    """重複チャネルをマージし、同一列の二重割り当てをスコア優先で解消する。"""
    groups: dict[str, list] = {}
    for name, entry in channel_map.items():
        key = name.lower().replace('_', '').replace(' ', '')
        groups.setdefault(key, []).append((name, entry))

    merged: dict[str, dict] = {}
    for entries in groups.values():
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
        st.session_state['demo_mode']        = False
        return result, None
    except Exception as e:
        return None, str(e)


# ── ヘッダー ──────────────────────────────────────────────────────────────
if _logo_b64:
    st.markdown(
        f'<img src="{_logo_b64}" style="height:56px;margin-bottom:4px;" alt="SmartMMM">',
        unsafe_allow_html=True,
    )
else:
    st.title('SmartMMM')
st.markdown(
    'マーケティングミックスモデリング（MMM）で、各チャネルのROIを可視化し、'
    '予算配分の最適解を算出します。'
)

# ── デモボタン ────────────────────────────────────────────────────────────
with st.container(border=True):
    col_demo_txt, col_demo_btn = st.columns([3, 1])
    with col_demo_txt:
        st.markdown(
            'サンプルデータ（7チャネル / 3年 / 週次）を使い、'
            'アップロードから結果確認まで一連の流れを体験できます。'
        )
    with col_demo_btn:
        if st.button('デモデータを読み込む', use_container_width=True):
            if not _DEMO_XLSX.exists():
                st.error(f'デモデータが見つかりません: {_DEMO_XLSX}')
            else:
                with st.spinner('デモデータを解析中...'):
                    result = detect_only_ext(str(_DEMO_XLSX))
                st.session_state['excel_tmp_path']   = str(_DEMO_XLSX)
                st.session_state['client_name']      = 'デモデータ（サンプル）'
                st.session_state['detect_result']    = result
                st.session_state['mapping_override'] = None
                st.session_state['demo_mode']        = True
                st.session_state['job_info'] = {
                    'demo':       True,
                    'job_id':     'demo',
                    'pid':        None,
                    'log_path':   str(_DEMO_LOG),
                    'output_dir': str(_REPO / 'demo_data'),
                    'config_path': None,
                    '_proc':      None,
                    '_log_file':  None,
                    'json_path':  str(_DEMO_JSON),
                }
                st.switch_page('pages/2_マッピング確認.py')

st.divider()

# ── ① プロジェクト名 ─────────────────────────────────────────────────────
st.subheader('① プロジェクト名の入力')
client_name = st.text_input(
    'プロジェクト名',
    value=st.session_state.get('client_name', ''),
    placeholder='例: 株式会社サンプル',
    help='PPTXレポートの表紙に使用します。',
    label_visibility='collapsed',
)

# ── ② データのアップロード ────────────────────────────────────────────────
st.subheader('② データのアップロード')
tab_excel, tab_sheets = st.tabs(['Excelアップロード', 'Google Sheetsから読み込む'])

# ── Tab A: Excel ──────────────────────────────────────────────────────────
with tab_excel:
    st.markdown(
        '<div class="lbl-q" style="margin-bottom:4px;">'
        'Excelファイルを選択（.xlsx / .xlsm）'
        '<span class="lq">?<span class="lq-tip">日次・週次データどちらでも対応。ヘッダー行は自動検出します。</span></span>'
        '</div>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        'Excelファイルを選択（.xlsx / .xlsm）',
        type=['xlsx', 'xlsm'],
        label_visibility='collapsed',
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
                    st.error('解析に失敗しました。ヘッダー行と日付列を確認してください。')
                    with st.expander('エラー詳細'):
                        st.code(str(err))
                    st.stop()
                else:
                    st.success(f'検出が完了しました。シート: {result["sheet_name"]} / {result["n_rows"]}行 / 頻度: {result["freq_guess"]}')
                    st.info('次のページでマッピングを確認・修正してから分析を開始してください。')
    elif not client_name:
        st.caption('クライアント名を入力するとアップロードできます。')

# ── Tab B: Google Sheets ──────────────────────────────────────────────────
with tab_sheets:
    st.caption('シートを「リンクを知っている全員が閲覧可」に設定してからURLを貼ってください。')
    st.markdown(
        '<div class="lbl-q" style="margin-bottom:4px;">'
        'Google SheetsのURL'
        '<span class="lq">?<span class="lq-tip">特定のタブを読み込む場合は、そのタブを開いた状態のURLをコピーしてください。</span></span>'
        '</div>',
        unsafe_allow_html=True,
    )
    sheets_url = st.text_input(
        'Google SheetsのURL',
        placeholder='https://docs.google.com/spreadsheets/d/...',
        label_visibility='collapsed',
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
                    st.error('解析に失敗しました。ヘッダー行と日付列を確認してください。')
                    with st.expander('エラー詳細'):
                        st.code(str(err))
                    st.stop()
                else:
                    st.success(f'読み込みが完了しました。{result["n_rows"]}行 / 頻度: {result["freq_guess"]}')
                    st.info('次のページでマッピングを確認・修正してから分析を開始してください。')
    elif not client_name:
        st.caption('クライアント名を入力するとURLを入力できます。')

# ── 検出済みの場合はプレビュー表示 ───────────────────────────────────────
if st.session_state.get('detect_result'):
    result  = st.session_state['detect_result']
    mapping = result['mapping']
    st.divider()
    st.subheader('自動検出結果プレビュー')

    col1, col2 = st.columns(2)
    with col1:
        st.metric('DATE列', mapping['date_col'] or '未検出 ⚠')
        st.metric('目的変数の列', mapping['cv_col'] or '未検出 ⚠')
    with col2:
        st.metric('検出チャネル数',   len(mapping['channel_map']))
        st.metric('未マッピング列数', len(mapping.get('unmapped', [])))

    if mapping.get('unmapped'):
        st.warning(f'未マッピング列: {", ".join(mapping["unmapped"][:10])}')

    st.page_link('pages/2_マッピング確認.py', label='マッピング確認へ →')
