# -*- coding: utf-8 -*-
"""Page 2 — チャネルマッピング確認・修正 & 分析起動。"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

import pandas as pd
import streamlit as st

from channel_ext import CHANNEL_OPTIONS
import runner

st.title('マッピング設定')

# ── 前ページからのデータ確認 ─────────────────────────────────────────
if not st.session_state.get('detect_result'):
    st.warning('先にExcelをアップロードしてください。')
    st.page_link('pages/1_アップロード.py', label='← アップロードページへ')
    st.stop()

_is_demo    = st.session_state.get('demo_mode', False)
detect_result = st.session_state['detect_result']
mapping       = detect_result['mapping']
excel_path    = st.session_state['excel_tmp_path']
client_name   = st.session_state['client_name']


@st.cache_data(show_spinner=False)
def _load_column_names(path: str, sheet_name: str, header_row: int) -> list[str]:
    """ヘッダー行だけ読んで全列名を取得する（DATE/CV列のプルダウン用）。"""
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, header=header_row - 1,
                            engine='openpyxl', nrows=0)
        return [str(c) for c in df.columns]
    except Exception:
        return []


_all_columns = _load_column_names(
    excel_path, detect_result.get('sheet_name'), detect_result.get('header_row', 1),
)

# ── デモバナー ────────────────────────────────────────────────────────
st.markdown(
    f'**プロジェクト**　{client_name}'
    f'　｜　**シート**　{detect_result["sheet_name"]}'
    f'　｜　**{detect_result["n_rows"]}行**'
    f'　｜　**頻度**　{detect_result["freq_guess"]}'
)

st.divider()

if True:  # 以前のタブを廃止し直接レンダリング

    # ── DATE/CV 列の確認 ─────────────────────────────────────────
    _date_default = mapping.get('date_col', '')
    _cv_default   = mapping.get('cv_col', '')
    _date_opts    = _all_columns if _all_columns else ([_date_default] if _date_default else [])
    _cv_opts      = _all_columns if _all_columns else ([_cv_default] if _cv_default else [])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="lbl-q">DATE列'
            '<span class="lq">?<span class="lq-tip">日付が入っている列名。'
            'YYYY-MM-DD 形式または Excel 日付シリアルを自動認識します。</span></span></div>',
            unsafe_allow_html=True,
        )
        date_col = st.selectbox(
            'DATE列', _date_opts,
            index=_date_opts.index(_date_default) if _date_default in _date_opts else 0,
            label_visibility='collapsed',
        ) if _date_opts else ''
    with col2:
        st.markdown(
            '<div class="lbl-q">目的変数の列'
            '<span class="lq">?<span class="lq-tip">CVや売上など、予測したい成果数値が入っている列名。'
            'モデルが最適化する目標値です。</span></span></div>',
            unsafe_allow_html=True,
        )
        cv_col = st.selectbox(
            '目的変数の列', _cv_opts,
            index=_cv_opts.index(_cv_default) if _cv_default in _cv_opts else 0,
            label_visibility='collapsed',
        ) if _cv_opts else ''

    st.divider()

    # ── チャネルマッピングテーブル ────────────────────────────────
    st.subheader('チャネルマッピング')
    st.markdown(
        '<div class="mmm-info-box">'
        '自動検出の結果です。内容を確認し、問題なければ<strong>このままページ下の「分析を開始する」を押してOKです。</strong>'
        '　チャネル名や役割を変更したい場合はドロップダウンで修正できます。'
        '「（未マッピング）」にするとそのチャネルは分析から除外されます。'
        '</div>',
        unsafe_allow_html=True,
    )

    def _match_badge(score: float) -> str:
        if score >= 0.8:
            return '◯'
        if score > 0:
            return '△'
        return '—'

    channel_map = mapping.get('channel_map', {})
    rows = []
    for ch, m in channel_map.items():
        if m.get('cost'):
            rows.append({'列名': m['cost'], '役割': 'コスト', 'チャネル名': ch,
                         'マッチ度': _match_badge(m.get('cost_score', 0))})
        if m.get('media'):
            rows.append({'列名': m['media'], '役割': 'メディア', 'チャネル名': ch,
                         'マッチ度': _match_badge(m.get('media_score', 0))})
    for col in mapping.get('unmapped', []):
        rows.append({'列名': col, '役割': '（未確定）', 'チャネル名': '（未マッピング）', 'マッチ度': '—'})

    if rows:
        _ROLE_OPTS = ['コスト', 'メディア', '（未確定）']

        st.markdown("""<style>
        .mp-hdr{display:grid;grid-template-columns:2fr 2fr 1.4fr 0.6fr;
                gap:0 4px;padding:0;
                border-bottom:2px solid #C5DFD9;margin-bottom:10px;}
        .mp-hdr > span{font-size:11px;font-weight:700;color:#33625A;
                     text-transform:uppercase;letter-spacing:.07em;text-align:center;
                     background:#C5DFD9;padding:8px 12px 6px;}
        </style>""", unsafe_allow_html=True)
        st.markdown(
            '<div class="mp-hdr">'
            '<span>元の列名</span><span>チャネル名</span>'
            '<span>役割</span>'
            '<span style="text-align:center;">マッチ度'
            '<span class="lq" style="margin-left:3px;">?<span class="lq-tip lq-tip-left">'
            '◯＝スコア80%以上・△＝一致度が低い・—＝未マッチ</span></span></span>'
            '</div>',
            unsafe_allow_html=True,
        )

        updated_rows = []
        for i, row in enumerate(rows):
            c1, c2, c3, c4 = st.columns([2, 2, 1.4, 0.6])
            with c1:
                st.text_input('col', value=row['列名'], disabled=True,
                              key=f'col_{i}', label_visibility='collapsed')
            with c2:
                default_ch = row['チャネル名'] if row['チャネル名'] in CHANNEL_OPTIONS else CHANNEL_OPTIONS[0]
                ch_name = st.selectbox('ch', CHANNEL_OPTIONS,
                                       index=CHANNEL_OPTIONS.index(default_ch),
                                       key=f'ch_{i}', label_visibility='collapsed')
            with c3:
                default_role = row['役割'] if row['役割'] in _ROLE_OPTS else _ROLE_OPTS[0]
                role = st.selectbox('role', _ROLE_OPTS,
                                    index=_ROLE_OPTS.index(default_role),
                                    key=f'role_{i}', label_visibility='collapsed')
            with c4:
                st.markdown(
                    f'<div style="padding:6px 0 0;text-align:center;font-size:14px;">'
                    f'{row["マッチ度"]}</div>',
                    unsafe_allow_html=True,
                )
            updated_rows.append({'列名': row['列名'], 'チャネル名': ch_name,
                                  '役割': role, 'マッチ度': row['マッチ度']})

        edited = pd.DataFrame(updated_rows)
    else:
        st.warning('マッピングされた列が見つかりませんでした。Excelの列名を確認してください。')
        edited = pd.DataFrame()

    st.divider()

    # ── 分析設定 ─────────────────────────────────────────────────
    n_trials        = 2000
    report_type_val = 'full'
    budget_increase = 0.3

    st.subheader('分析設定')
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            '<div class="lbl-q">分析精度（試行回数）'
            '<span class="lq">?<span class="lq-tip">'
            '本番は2000が目安。動作確認なら50でOK。少ないほど速いが精度は下がります。'
            '</span></span></div>',
            unsafe_allow_html=True,
        )
        _trial_presets = {
            'テスト（50回・動作確認用）': 50,
            '標準（2,000回・推奨）':      2000,
            '高精度（5,000回・時間がかかります）': 5000,
        }
        _trial_choice = st.radio(
            '分析精度（試行回数）',
            list(_trial_presets.keys()),
            index=1,
            label_visibility='collapsed',
        )
        n_trials = _trial_presets[_trial_choice]
    with col_b:
        report_type = st.selectbox('レポートタイプ', ['full（フルレポート）', 'simple（簡易版）'])
        report_type_val = 'full' if 'full' in report_type else 'simple'
    with col_c:
        st.markdown(
            '<div class="lbl-q">シナリオB増額率 (%)'
            '<span class="lq">?<span class="lq-tip lq-tip-left">'
            '予算最適化シナリオBで何%増額した場合を試算するか。デフォルトは30%。'
            '</span></span></div>',
            unsafe_allow_html=True,
        )
        budget_increase = st.number_input(
            'シナリオB増額率 (%)',
            min_value=10, max_value=100, value=30, step=5,
            label_visibility='collapsed',
        ) / 100

    st.divider()

    n_active_ch = 0
    if not edited.empty:
        n_active_ch = edited[
            (edited['チャネル名'] != '（未マッピング）') & (edited['役割'] != '（未確定）')
        ]['チャネル名'].nunique()

    if not _is_demo and n_active_ch > 0:
        est = runner.estimate_duration(int(n_trials), n_active_ch)
        st.info(
            f'試行数 {int(n_trials):,} × {n_active_ch} チャネル'
            f' ＝ 処理時間の目安 **{est}**（使用PCのスペックによって変動します）'
        )

    # ── mapping_override を構築（デモ・通常共通。比較にも使う） ─────
    new_channel_map: dict = {}
    for _, row in edited.iterrows():
        ch   = row['チャネル名']
        role = row['役割']
        col_name = row['列名']
        if ch == '（未マッピング）' or role == '（未確定）':
            continue
        if ch not in new_channel_map:
            new_channel_map[ch] = {'media': None, 'cost': None, 'media_score': 0, 'cost_score': 0}
        if role == 'コスト':
            new_channel_map[ch]['cost'] = col_name
        elif role == 'メディア':
            new_channel_map[ch]['media'] = col_name

    mapping_override = {
        'date_col':    date_col or mapping.get('date_col'),
        'cv_col':      cv_col or mapping.get('cv_col'),
        'channel_map': new_channel_map,
        'control_cols': mapping.get('control_cols', []),
        'unmapped':    [],
    }

    # ── 分析開始ボタンの有効化条件 ────────────────────────────────
    _job_running = False
    if not _is_demo and st.session_state.get('job_info'):
        _job_running = runner.get_job_status(st.session_state['job_info'])['status'] == 'running'

    # 同じデータ・同じマッピングで分析済みなら「結果を見る」に切り替える
    _current_source = 'demo' if _is_demo else excel_path
    _already_analyzed = (
        not _job_running
        and st.session_state.get('job_info') is not None
        and st.session_state.get('analyzed_source') == _current_source
        and st.session_state.get('mapping_override') == mapping_override
    )

    if _job_running:
        _missing = None
        st.warning('分析を実行中です。完了後に新しい分析を開始できます。')
        st.page_link('pages/summary.py', label='← 実行中の分析結果ページへ')
    elif not date_col:
        _missing = '日付列を選択してください'
        st.warning(_missing)
    elif not cv_col:
        _missing = '目的変数の列を選択してください'
        st.warning(_missing)
    elif n_active_ch == 0:
        _missing = '分析に使うチャネルを1つ以上選択してください'
        st.warning(_missing)
    else:
        _missing = None

    _start_disabled = _job_running or bool(_missing) or edited.empty

    # ── 分析開始 / 結果確認ボタン ────────────────────────────────
    if _already_analyzed:
        st.caption('前回分析したデータが読み込まれています。')
        if st.button('分析結果を見る →', type='primary'):
            st.switch_page('pages/summary.py')
    elif st.button('分析を開始する →', type='primary', disabled=_start_disabled):
        st.session_state['mapping_override'] = mapping_override
        st.session_state['analyzed_source']  = _current_source

        if _is_demo:
            import time
            _stages = [
                (5,   'データを読み込み中...',        0.5),
                (15,  'データを前処理中...',           1.0),
                (30,  'モデルを構築中 (1/3)...',       1.5),
                (50,  'モデルを構築中 (2/3)...',       1.8),
                (68,  'モデルを最適化中...',           2.0),
                (82,  '予算最適化シナリオを計算中...',  1.5),
                (93,  'レポートを生成中...',            1.2),
                (100, '分析完了',                       0.5),
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
            with st.spinner('分析ジョブを起動中...'):
                job_info = runner.start_analysis(
                    excel_path=excel_path,
                    client_name=client_name,
                    mapping_override=mapping_override,
                    n_trials=int(n_trials),
                    report_type=report_type_val,
                    budget_increase=budget_increase,
                )
            st.session_state['job_info'] = job_info
            st.session_state.setdefault('own_job_ids', set()).add(job_info['job_id'])
            st.switch_page('pages/summary.py')

st.page_link('pages/2b_preview.py', label='データプレビューを確認する →')
