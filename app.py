# -*- coding: utf-8 -*-
"""SmartMMM — Streamlit エントリポイント。起動: streamlit run app.py"""
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import streamlit.components.v1 as components

try:
    from PIL import Image as _PIL
    _FAV_PATH = Path(__file__).parent / 'assets' / 'favicon.png'
    _favicon = _PIL.open(_FAV_PATH) if _FAV_PATH.exists() else '📊'
except Exception:
    _favicon = '📊'

st.set_page_config(page_title='SmartMMM｜大企業だけの分析力を中小・ベンチャー企業の手に。', page_icon=_favicon, layout='wide')

# ── ロゴ読み込み（base64埋め込み）──────────────────────────────────────────
_LOGO_PATH       = Path(__file__).parent / 'assets' / 'logo.png'
_LOGO_WHITE_PATH = Path(__file__).parent / 'assets' / 'logo-white.png'
_logo_src        = ''
_logo_white_src  = ''
if _LOGO_PATH.exists():
    _logo_src = 'data:image/png;base64,' + base64.b64encode(_LOGO_PATH.read_bytes()).decode()
if _LOGO_WHITE_PATH.exists():
    _logo_white_src = 'data:image/png;base64,' + base64.b64encode(_LOGO_WHITE_PATH.read_bytes()).decode()

# ── ナビアイコン読み込み ────────────────────────────────────────────────────
def _b64img(name: str) -> str:
    p = Path(__file__).parent / 'assets' / name
    return 'data:image/png;base64,' + base64.b64encode(p.read_bytes()).decode() if p.exists() else ''

_icon_upload   = _b64img('icon-upload.png')
_icon_mapping  = _b64img('icon-mapping.png')
_icon_analysis = _b64img('icon-analysis.png')

# ── ナビゲーション定義（認証状態に関わらず毎回登録する。switch_page から参照するため）──
pg = st.navigation({
    'データのアップロード': [
        st.Page('pages/1_アップロード.py', title='データのアップロード', default=True, url_path='upload'),
    ],
    'データのマッピング': [
        st.Page('pages/2_マッピング確認.py', title='マッピング設定',   url_path='mapping'),
        st.Page('pages/2b_preview.py',      title='データプレビュー', url_path='data-preview'),
    ],
    '分析結果': [
        st.Page('pages/summary.py',          title='分析サマリ',        url_path='summary'),
        st.Page('pages/6_model.py',          title='モデル精度',        url_path='accuracy'),
        st.Page('pages/5_detail.py',         title='チャネル分析',      url_path='channel'),
        st.Page('pages/3_結果.py',           title='ROI・CPA分析',     url_path='roi-cpa'),
        st.Page('pages/4_budget.py',         title='予算配分分析',      url_path='allocation'),
        st.Page('pages/7_frontier.py',       title='投資上限分析',      url_path='investment-cap'),
        st.Page('pages/8_budget_change.py',  title='予算増額・減額分析', url_path='budget-change'),
    ],
})

# ── ログイン設定 ──────────────────────────────────────────────────────────
_PASSWORD  = st.secrets.get('APP_PASSWORD',  os.environ.get('APP_PASSWORD',  ''))
_DEMO_USER = st.secrets.get('DEMO_USER',     os.environ.get('DEMO_USER',     'demo'))
_DEMO_PASS = st.secrets.get('DEMO_PASSWORD', os.environ.get('DEMO_PASSWORD', 'password'))

if _PASSWORD and not st.session_state.get('_authenticated', False):

    st.markdown("""
    <style>
    #MainMenu, header, footer,
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    [data-testid="stToolbar"]                           { display: none !important; }
    section[data-testid="stSidebar"],
    [data-testid="stSidebarNav"],
    [data-testid="stSidebarContent"]                    { display: none !important; }
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"]                              { background-color: #F3F7F4 !important; }
    .block-container {
        max-width     : 460px !important;
        padding-top   : 14vh  !important;
        padding-left  : 24px  !important;
        padding-right : 24px  !important;
        margin        : 0 auto !important;
    }
    [data-testid="stForm"] { border:none !important; background:transparent !important; padding:0 !important; }
    div[data-baseweb="input"] {
        background:   #FFFFFF             !important;
        border:       1.5px solid #5C9291 !important;
        border-radius:4px                 !important;
    }
    div[data-baseweb="input"] > div,
    div[data-baseweb="input"] > div > div {
        background: #FFFFFF !important;
        border:     none    !important;
    }
    div[data-baseweb="input"]:focus-within {
        border-color: #315E6D !important;
        box-shadow:   none    !important;
    }
    div[data-baseweb="input"] input { color:#314858 !important; font-size:14px !important; height:42px !important; }
    /* Streamlit新バージョン(React Aria方式DOM)向けフォールバック — 本番と開発でStreamlitバージョンが
       異なる場合でもログイン枠線が消えないようにする */
    div[data-testid="stTextInputRootElement"] {
        background:   #FFFFFF             !important;
        border:       1.5px solid #5C9291 !important;
        border-radius:4px                 !important;
    }
    div[data-testid="stTextInputRootElement"]:focus-within {
        border-color: #315E6D !important;
        box-shadow:   none    !important;
    }
    div[data-testid="stTextInputRootElement"] input { color:#314858 !important; font-size:14px !important; }
    .stButton > button, .stFormSubmitButton > button {
        background-color:#315E6D !important; border:none !important; border-radius:4px !important;
        color:#FFFFFF !important; font-size:14px !important; font-weight:600 !important;
        height:44px !important; width:100% !important; margin-top:6px !important;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover { background-color:#314858 !important; }
    </style>
    """, unsafe_allow_html=True)

    logo_tag = (
        f'<img src="{_logo_src}" style="height:64px;display:block;margin:0 auto 14px;" alt="SmartMMM">'
        if _logo_src else
        '<div style="font-size:28px;font-weight:700;color:#315E6D;text-align:center;margin-bottom:14px;">SmartMMM</div>'
    )
    st.markdown(f'''
    <div style="text-align:center;margin-bottom:40px;">
      {logo_tag}
      <div style="color:#314858;font-size:14px;letter-spacing:.01em;white-space:nowrap;width:max-content;margin:0 auto;">大企業だけの分析力を中小・ベンチャー企業の手に。</div>
    </div>
    ''', unsafe_allow_html=True)

    with st.form('login_form', border=False):
        uid = st.text_input('ユーザー名', placeholder='ユーザー名', label_visibility='collapsed')
        pwd = st.text_input('パスワード', type='password', placeholder='パスワード', label_visibility='collapsed')
        submitted = st.form_submit_button('ログイン', use_container_width=True)

    if submitted:
        _uname = uid.strip().lower()
        if _uname == _DEMO_USER.lower() and pwd == _DEMO_PASS:
            st.session_state['_authenticated'] = True
            st.session_state['_is_demo_user']  = True
            st.switch_page('pages/1_アップロード.py')
        elif pwd == _PASSWORD:
            st.session_state['_authenticated'] = True
            st.switch_page('pages/1_アップロード.py')
        else:
            st.error('ユーザー名またはパスワードが違います。')

    st.stop()

# ── セッション初期化 ────────────────────────────────────────────────────
defaults = {
    'excel_tmp_path':   None,
    'client_name':      '',
    'detect_result':    None,
    'mapping_override': None,
    'job_info':         None,
    'n_trials':         2000,
    'report_type':      'full',
    'demo_mode':        False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── グローバル CSS ─────────────────────────────────────────────────────────
st.markdown("""
<style>

/* ═══════════════════════════════════════════════════
   サイドバー — ベース
═══════════════════════════════════════════════════ */
section[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child,
[data-testid="stSidebarContent"] {
    background-color: #314858 !important;
}

/* サイドバー内全テキストのデフォルト色 */
[data-testid="stSidebar"] * {
    color: #ffffff !important;
}

/* ═══════════════════════════════════════════════════
   ナビゲーションコンテナ
═══════════════════════════════════════════════════ */
[data-testid="stSidebarNav"] {
    padding: 8px 0 0 0 !important;
    background: transparent !important;
}

/* ═══════════════════════════════════════════════════
   セクション区切り線（Streamlit が <hr> 挿入）
═══════════════════════════════════════════════════ */
[data-testid="stSidebarNav"] hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.14) !important;
    margin: 4px 0 !important;
}

/* ═══════════════════════════════════════════════════
   セクションヘッダーラベル
   — nav 内で a タグでない要素（span・p・div）を対象
═══════════════════════════════════════════════════ */
[data-testid="stSidebarNav"] li > *:not(a):not(hr) {
    padding: 14px 16px 4px 16px !important;
    display: block !important;
}
[data-testid="stSidebarNav"] li > *:not(a):not(hr) span,
[data-testid="stSidebarNav"] li > *:not(a):not(hr) p,
[data-testid="stSidebarNav"] li > *:not(a):not(hr) {
    color: rgba(255,255,255,0.50) !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: none !important;
    line-height: 1.4 !important;
}

/* ═══════════════════════════════════════════════════
   ページリンク（サブアイテム）
═══════════════════════════════════════════════════ */
a[data-testid="stSidebarNavLink"] {
    /* フル幅・角丸なし */
    display:        block     !important;
    border-radius:  0         !important;
    margin:         0         !important;
    /* インデント（サブアイテム感） */
    padding:        6px 16px 6px 28px !important;
    /* テキスト */
    color:          #ffffff   !important;
    font-size:      15px      !important;
    font-weight:    400       !important;
    line-height:    1.4       !important;
    /* アニメーション無効 */
    transition:     background-color 0.12s !important;
    animation:      none !important;
    /* 幅 */
    width: 100% !important;
    box-sizing: border-box !important;
}
a[data-testid="stSidebarNavLink"] *,
a[data-testid="stSidebarNavLink"] span,
a[data-testid="stSidebarNavLink"] p {
    color:     #ffffff !important;
    font-size: 15px    !important;
}

/* ─ ホバー ─ */
a[data-testid="stSidebarNavLink"]:hover {
    background-color: rgba(126,190,171,.14) !important;
}
a[data-testid="stSidebarNavLink"]:hover * {
    color: #ffffff !important;
}

/* ─ 選択中 ─ */
a[data-testid="stSidebarNavLink"][aria-current="page"] {
    background-color: #253B4A !important;
    font-weight:      600 !important;
    animation:        none !important;
}
a[data-testid="stSidebarNavLink"][aria-current="page"] *,
a[data-testid="stSidebarNavLink"][aria-current="page"] span {
    color:       #ffffff !important;
    font-weight: 600     !important;
}

/* ═══════════════════════════════════════════════════
   折りたたみボタン（サイドバー全体）
═══════════════════════════════════════════════════ */
[data-testid="stSidebarCollapseButton"] svg {
    fill: rgba(255,255,255,0.55) !important;
}

/* ═══════════════════════════════════════════════════
   セクションヘッダー — flex でアイコン＋テキスト＋矢印を横並び
═══════════════════════════════════════════════════ */
[data-testid="stNavSectionHeader"] {
    display:     flex          !important;
    align-items: center        !important;
    padding:     14px 16px 4px 12px !important;
    gap:         0             !important;
}

/* ═══════════════════════════════════════════════════
   ナビゲーションセクション折り畳み矢印を常時表示
   — Streamlit は <header> > <div> > <span> に visibility:hidden を設定
     → 常時 visible にする
═══════════════════════════════════════════════════ */
[data-testid="stNavSectionHeader"] > div > span {
    visibility: visible !important;
    opacity:    1       !important;
}

/* ═══════════════════════════════════════════════════
   フッターロゴ（サイドバー最下部）
═══════════════════════════════════════════════════ */
.sidebar-footer {
    padding:     20px 20px 22px !important;
    text-align:  center         !important;
    border-top:  1px solid rgba(255,255,255,0.12) !important;
    margin-top:  24px           !important;
}

/* ═══════════════════════════════════════════════════
   ネイティブ help= アイコンをグレーに
═══════════════════════════════════════════════════ */
button[data-testid="stTooltipHoverTarget"] svg,
[data-testid="stTooltipHoverTarget"] svg {
    color: #9fa6b0 !important;
    fill:  #9fa6b0 !important;
}
button[data-testid="stTooltipHoverTarget"]:hover svg,
[data-testid="stTooltipHoverTarget"]:hover svg {
    color: #6b7280 !important;
    fill:  #6b7280 !important;
}

/* ═══════════════════════════════════════════════════
   ページ内タブ・ボタン（グローバル）
═══════════════════════════════════════════════════ */
[data-baseweb="tab-highlight"]              { background-color: #315E6D !important; }
[data-baseweb="tab"][aria-selected="true"]  { color: #315E6D !important; }

.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background-color: #315E6D !important;
    border:           none    !important;
    color:            #FFFFFF !important;
    font-weight:      700     !important;
    transition:       background-color .15s;
}
.stButton > button[kind="primary"] p,
.stFormSubmitButton > button[kind="primary"] p {
    font-weight: 700 !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background-color: #2A5160 !important;
}

[data-testid="stPageLink"],
[data-testid="stPageLink"] * {
    font-weight: 700 !important;
}

/* ═══════════════════════════════════════════════════
   カスタム「?」ツールチップ — 全ページ共通
═══════════════════════════════════════════════════ */
.lbl-q { display:inline-flex; align-items:center; gap:5px; font-size:14px; font-weight:600; }
.lq {
    position:relative; display:inline-flex; align-items:center; justify-content:center;
    width:16px; height:16px; background:#9fa6b0; border-radius:50%;
    font-size:10px; font-weight:700; color:#fff; cursor:help; flex-shrink:0;
    vertical-align:middle; line-height:1;
}
:root[data-theme="dark"] .lq,
:root:not([data-theme="light"]) .lq { background:#6b7280; }
@media (prefers-color-scheme:dark) {
    :root:not([data-theme="light"]) .lq { background:#6b7280; }
}
.lq .lq-tip {
    display:none; position:absolute; left:20px; bottom:20px;
    width:230px; padding:8px 10px;
    background:#314858; color:#fff; font-size:11px; font-weight:400;
    border-radius:6px; z-index:9999; line-height:1.6;
    white-space:normal; box-shadow:0 2px 8px rgba(0,0,0,.3);
    text-transform:none; letter-spacing:normal;
}
.lq:hover .lq-tip { display:block; }
/* 画面右端付近のアイコン用 — ツールチップを左方向に開く */
.lq .lq-tip.lq-tip-left { left:auto; right:20px; }

/* ═══════════════════════════════════════════════════
   テーブルヘッダー — dataframe / data_editor 共通
═══════════════════════════════════════════════════ */
[data-testid="stDataFrame"] [role="columnheader"],
[data-testid="stDataEditorGrid"] [role="columnheader"] {
    background-color: #C5DFD9 !important;
    color:            #33625A !important;
    font-weight:      700     !important;
    font-size:        11px    !important;
    letter-spacing:   .07em   !important;
    text-align:       center  !important;
}

/* ═══════════════════════════════════════════════════
   カスタムHTMLテーブル — .sc-table（チャネル別スコアカード基準）
   全ページの表形式UIはこのクラスに統一する
═══════════════════════════════════════════════════ */
.sc-table { width:100%; border-collapse:collapse; font-size:13px; }
.sc-table th {
    background:#C5DFD9; color:#33625A; font-weight:700; font-size:11px;
    text-transform:uppercase; letter-spacing:.07em; padding:8px 12px;
    border-bottom:2px solid #C5DFD9; text-align:center;
}
.sc-table td { padding:9px 12px; border-bottom:1px solid #C5DFD9; color:#314858; }
.sc-table tr:last-child td { border-bottom:none; }
.sc-table tr:hover td { background:#F9FDFC; }
.sc-table .num-col { text-align:right !important; font-variant-numeric:tabular-nums; }
.sc-table th.num-col { text-align:center !important; }

/* ═══════════════════════════════════════════════════
   インフォボックス — 案内文・注記系で共通使用
═══════════════════════════════════════════════════ */
.mmm-info-box {
    background:    #E8F3EC;
    border-radius: 6px;
    padding:       12px 16px;
    color:         #315E6D;
    font-size:     14px;
    line-height:   1.75;
    margin-bottom: 16px;
}
.mmm-info-box strong { font-weight: 700; }

/* ═══════════════════════════════════════════════════
   カードUI — KPI・サマリー系で共通使用（summary.py基準）
═══════════════════════════════════════════════════ */
.mmm-card-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; }
.mmm-card { background:#fff; border-radius:8px; padding:11px 14px; box-shadow:0 0 12px rgba(49,72,88,.14); text-align:center; }
.mmm-card-lbl {
    color:#5C9291; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.08em;
    margin-bottom:3px; display:flex; align-items:center; justify-content:center; gap:5px;
}
.mmm-card-val { font-size:20px; font-weight:700; color:#314858; line-height:1.3; display:flex; align-items:center; justify-content:center; gap:6px; }
.mmm-card-unit { font-size:12px; font-weight:400; color:#5C9291; }

/* KPIグレードバッジ — 精度指標・ROI系で共通使用 */
.kpi-badge { font-size:11px; padding:2px 6px; border-radius:3px; flex-shrink:0; line-height:1.5; }
.b-s { background:#315E6D; color:#fff; }
.b-a { background:#7EBEAB; color:#314858; }
.b-b { background:#CB8013; color:#fff; }
.b-c { background:#999; color:#fff; }

/* 各分析結果ページ — 見出し直下のリード文 */
.page-lede {
    color:          #314858 !important;
    font-size:      15px    !important;
    line-height:    1.7     !important;
    padding-bottom: 14px    !important;
    margin:         0       !important;
}

/* 無効化されたテキスト入力（マッピング確認：元の列名）— 変更不可であることが伝わる淡色に統一 */
div[data-baseweb="input"] input:disabled,
div[data-testid="stTextInputRootElement"] input:disabled {
    color:                 #9AA3AA !important;
    -webkit-text-fill-color: #9AA3AA !important;
    opacity:               1        !important;
}

/* data_editor ヘッダーの help「?」を常時表示 */
[data-testid="stDataEditorGrid"] [data-testid="stTooltipHoverTarget"] {
    opacity: 1 !important;
    visibility: visible !important;
}
[data-testid="stDataEditorGrid"] [data-testid="stTooltipHoverTarget"] svg {
    color: #9fa6b0 !important;
    fill: #9fa6b0 !important;
}

/* ═══════════════════════════════════════════════════
   メインコンテンツ — H1上部の余白を削減
═══════════════════════════════════════════════════ */
[data-testid="stMainBlockContainer"],
.block-container:not([style*="14vh"]) {
    padding-top: 1.5rem !important;
}
[data-testid="stMainBlockContainer"] h1:first-of-type {
    margin-top: 0 !important;
    padding-top: 0 !important;
}

/* ═══════════════════════════════════════════════════
   グラフ描画アニメーション — 棒/線/ドーナツ共通演出
   画面内に入るまでは初期フレーム（非表示）で待機し、
   JS側（IntersectionObserver）が .mmm-in-view を付与した時点で再生する。
   縦棒=mmm-vert-bar（下→上）／横棒=mmm-horiz-bar（左→右）はJS側で判定して付与。
═══════════════════════════════════════════════════ */
@media (prefers-reduced-motion: no-preference) {
    .js-plotly-plot .bars .point path,
    .js-plotly-plot.mmm-horiz-bar .bars .point,
    .js-plotly-plot .scatterlayer .lines,
    .js-plotly-plot .scatterlayer .trace:has(.js-line) .points,
    .js-plotly-plot .scatterlayer .trace:not(:has(.js-line)) .points,
    .js-plotly-plot .pielayer,
    .js-plotly-plot .errorbars {
        animation-play-state: paused;
    }
    .js-plotly-plot.mmm-in-view .bars .point path,
    .js-plotly-plot.mmm-in-view.mmm-horiz-bar .bars .point,
    .js-plotly-plot.mmm-in-view .scatterlayer .lines,
    .js-plotly-plot.mmm-in-view .scatterlayer .trace:has(.js-line) .points,
    .js-plotly-plot.mmm-in-view .scatterlayer .trace:not(:has(.js-line)) .points,
    .js-plotly-plot.mmm-in-view .pielayer,
    .js-plotly-plot.mmm-in-view .errorbars {
        animation-play-state: running;
    }

    .js-plotly-plot.mmm-vert-bar .bars .point path {
        animation-name: mmm-bar-grow-v;
        animation-duration: .7s;
        animation-delay: .2s;
        animation-timing-function: cubic-bezier(.25,.8,.35,1);
        animation-fill-mode: both;
    }
    @keyframes mmm-bar-grow-v {
        from { clip-path: inset(100% 0 0 0); }
        to   { clip-path: inset(0% 0 0 0); }
    }

    /* 残差グラフ等、ゼロ基準線をまたぐ棒（負の値=JS側でmmm-bar-negを付与）:
       ゼロ線（棒の上端）から下向きに伸びるようにする */
    .js-plotly-plot.mmm-vert-bar .bars .point path.mmm-bar-neg {
        animation-name: mmm-bar-grow-v-down;
    }
    @keyframes mmm-bar-grow-v-down {
        from { clip-path: inset(0 0 100% 0); }
        to   { clip-path: inset(0 0 0% 0); }
    }

    /* 横棒: バー本体とデータラベル(<text>)は同じ<g class="point">の兄弟要素なので、
       グループごとclip-pathすることでラベルもバーの伸長と同じ歩調で現れる */
    .js-plotly-plot.mmm-horiz-bar .bars .point {
        animation-name: mmm-bar-grow-h;
        animation-duration: .7s;
        animation-delay: .2s;
        animation-timing-function: cubic-bezier(.25,.8,.35,1);
        animation-fill-mode: both;
    }
    @keyframes mmm-bar-grow-h {
        from { clip-path: inset(0 100% 0 0); }
        to   { clip-path: inset(0 0% 0 0); }
    }

    .js-plotly-plot .scatterlayer .lines {
        animation-name: mmm-line-draw;
        animation-duration: .9s;
        animation-delay: .2s;
        animation-timing-function: ease-out;
        animation-fill-mode: both;
    }
    /* 折れ線のドット(マーカー): 線と同じclip-pathアニメーションを適用し、
       線が伸びるのに合わせてドットも同じ歩調で現れるようにする */
    .js-plotly-plot .scatterlayer .trace:has(.js-line) .points {
        animation-name: mmm-line-draw;
        animation-duration: .9s;
        animation-delay: .2s;
        animation-timing-function: ease-out;
        animation-fill-mode: both;
    }
    @keyframes mmm-line-draw {
        from { clip-path: inset(0 100% 0 0); }
        to   { clip-path: inset(0 0% 0 0); }
    }

    /* レスポンスカーブ等、線を伴わない単独マーカーのみのトレース: 最初は非表示にしておき、
       画面内に入ったタイミングでフェードインさせる */
    .js-plotly-plot .scatterlayer .trace:not(:has(.js-line)) .points {
        animation-name: mmm-marker-fade-in;
        animation-duration: .5s;
        animation-delay: .2s;
        animation-timing-function: ease-out;
        animation-fill-mode: both;
    }
    @keyframes mmm-marker-fade-in {
        from { opacity: 0; }
        to   { opacity: 1; }
    }

    /* CPA信頼区間（フォレストプロット）: ■マーカーを中心に誤差バーが左右に広がる */
    .js-plotly-plot .errorbars {
        animation-name: mmm-errorbar-grow;
        animation-duration: .7s;
        animation-delay: .2s;
        animation-timing-function: cubic-bezier(.25,.8,.35,1);
        animation-fill-mode: both;
        transform-box: fill-box;
        transform-origin: center;
    }
    @keyframes mmm-errorbar-grow {
        from { transform: scaleX(0); }
        to   { transform: scaleX(1); }
    }

    @property --mmm-donut-p {
        syntax: '<number>';
        inherits: false;
        initial-value: 0;
    }
    .js-plotly-plot .pielayer {
        animation-name: mmm-donut-sweep;
        animation-duration: .9s;
        animation-delay: .2s;
        animation-timing-function: ease-out;
        animation-fill-mode: both;
        -webkit-mask-image: conic-gradient(from 0deg, #000 calc(var(--mmm-donut-p)*3.6deg), transparent calc(var(--mmm-donut-p)*3.6deg));
        mask-image: conic-gradient(from 0deg, #000 calc(var(--mmm-donut-p)*3.6deg), transparent calc(var(--mmm-donut-p)*3.6deg));
    }
    @keyframes mmm-donut-sweep {
        from { --mmm-donut-p: 0; }
        to   { --mmm-donut-p: 100; }
    }
}

</style>
""", unsafe_allow_html=True)

# ── グラフ描画アニメーション制御 ────────────────────────────────────────────
# Plotlyチャートの向き(縦棒/横棒)判定と、画面内に入った瞬間のアニメーション開始をJSで制御。
# st.markdown内の<script>はブラウザで実行されないため、components.htmlのiframe経由で
# window.parent.document（同一オリジン）にアクセスして親ページのDOMを監視する。
components.html("""
<script>
(function() {
    function setupOnce(doc) {
        if (doc.__mmmChartObsInit) return;
        doc.__mmmChartObsInit = true;

        var win = doc.defaultView || window.parent;
        var REVEAL_DEBOUNCE_MS = 250;
        var IDLE_STREAK_NEEDED = 3;
        var IDLE_FRAME_MAX_MS = 50;
        var IDLE_WAIT_CAP_MS = 4000;

        // 残差グラフ等、ゼロ基準線をまたぐ縦棒: SVGパス自体の形状(M x,y0 V y1 H x1 V y0 Z)から
        // 上端/下端を読み取り、ゼロ線(y0)より下に伸びる棒(y1 > y0 = 負の値)に mmm-bar-neg を付与する。
        // plot.data.y はPlotlyの内部シリアライズ形式(typed array等)で直接読めない場合があるため、
        // 描画済みパスの座標から判定する方が確実。
        function markBarSigns(plot) {
            try {
                if (!plot.classList.contains('mmm-vert-bar')) return;
                var paths = plot.querySelectorAll('.barlayer .points > .point > path');
                for (var i = 0; i < paths.length; i++) {
                    var d = paths[i].getAttribute('d');
                    if (!d) continue;
                    var m = d.match(/^M-?[\d.]+,(-?[\d.]+)V(-?[\d.]+)H/);
                    if (m && parseFloat(m[2]) > parseFloat(m[1])) {
                        paths[i].classList.add('mmm-bar-neg');
                    }
                }
            } catch (e) { /* noop */ }
        }

        function reveal(plot) {
            if (plot.classList.contains('mmm-in-view')) return;
            markBarSigns(plot);
            plot.classList.add('mmm-in-view');
            if (plot.__mmmRedrawObs) {
                plot.__mmmRedrawObs.disconnect();
                plot.__mmmRedrawObs = null;
            }
        }

        // ページ遷移直後はStreamlitの再描画やPlotlyの複数回の内部redrawでメインスレッドが
        // 塞がっていることがある。その間にmmm-in-viewを付与するとCSSアニメーションのタイムラインが
        // 裏側で進行してしまい、ブラウザが実際にペイントできる頃には完了済み(=途中から描画された
        // ように見える)になる。そのため直近の連続フレームが正常な間隔で描画できている(=メイン
        // スレッドが空いている)ことを確認してからmmm-in-viewを付与する。
        function whenPaintReady(cb) {
            var start = win.performance.now();
            var streak = 0;
            var last = null;
            function frame(now) {
                if (now - start > IDLE_WAIT_CAP_MS) { cb(); return; }
                if (last !== null) {
                    streak = (now - last) < IDLE_FRAME_MAX_MS ? streak + 1 : 0;
                }
                last = now;
                if (streak >= IDLE_STREAK_NEEDED) { cb(); return; }
                win.requestAnimationFrame(frame);
            }
            win.requestAnimationFrame(frame);
        }

        // Plotlyはコンテナ挿入後も複数回にわたり内部でpath要素を作り直す(オートサイズ確定等)。
        // 交差直後に即座にmmm-in-viewを付与すると、その後の再描画で生成されたpathが
        // 既にrunning状態で生まれてしまい、ブラウザが実際に描画するタイミングには
        // アニメーションが裏側で完了済み(=途中から描画されたように見える)になる。
        // そのため、対象プロット内のDOM変化が一定時間止まるまでmmm-in-view付与を遅延させる。
        function armReveal(plot) {
            if (plot.__mmmRevealTimer) clearTimeout(plot.__mmmRevealTimer);
            plot.__mmmRevealTimer = setTimeout(function() {
                if (plot.__mmmIntersecting) {
                    whenPaintReady(function() {
                        if (plot.__mmmIntersecting) reveal(plot);
                    });
                }
            }, REVEAL_DEBOUNCE_MS);
        }

        var io = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.__mmmIntersecting = true;
                    io.unobserve(entry.target);
                    armReveal(entry.target);
                }
            });
        }, { threshold: 0.2 });

        function markOrientation(plot) {
            try {
                var data = plot.data;
                if (!data) return;
                var hasBar = data.some(function(d) { return d.type === 'bar'; });
                if (hasBar) {
                    var horiz = data.some(function(d) { return d.orientation === 'h'; });
                    plot.classList.add(horiz ? 'mmm-horiz-bar' : 'mmm-vert-bar');
                }
            } catch (e) { /* noop */ }
        }

        function watchRedraw(plot) {
            var redrawObs = new MutationObserver(function() {
                if (plot.__mmmIntersecting) armReveal(plot);
            });
            redrawObs.observe(plot, { childList: true, subtree: true });
            plot.__mmmRedrawObs = redrawObs;
        }

        function scan() {
            doc.querySelectorAll('.js-plotly-plot:not([data-mmm-scanned])').forEach(function(plot) {
                plot.setAttribute('data-mmm-scanned', '1');
                markOrientation(plot);
                watchRedraw(plot);
                io.observe(plot);
            });
        }

        scan();
        var mo = new MutationObserver(function() { scan(); });
        mo.observe(doc.body, { childList: true, subtree: true });
    }

    try {
        setupOnce(window.parent.document);
    } catch (e) { /* 異なるオリジン等で失敗した場合は何もしない */ }
})();
</script>
""", height=0)

# ── ナビゲーション ────────────────────────────────────────────────────────
# ── サイドバーフッター（ロゴ）: pg.run() より前に配置しないと st.stop() で消える ──
with st.sidebar:
    _sb_logo_src = _logo_white_src or _logo_src
    logo_html = (
        f'<img src="{_sb_logo_src}" style="height:44px;opacity:0.95;{"" if _logo_white_src else "filter:brightness(0) invert(1);"}" alt="SmartMMM">'
        if _sb_logo_src else
        '<div style="font-size:16px;font-weight:700;color:#ffffff;letter-spacing:.05em;">SmartMMM</div>'
    )
    st.markdown(
        f'<div class="sidebar-footer">{logo_html}</div>',
        unsafe_allow_html=True,
    )

# ── セクションアイコン（JavaScript で DOM に直接注入）────────────────────
import streamlit.components.v1 as _components
_components.html(f"""
<script>
(function() {{
    var icons = ["{_icon_upload}", "{_icon_mapping}", "{_icon_analysis}"];

    function _inject() {{
        var hdrs = parent.document.querySelectorAll('[data-testid="stNavSectionHeader"]');
        if (!hdrs.length) {{ setTimeout(_inject, 400); return; }}
        hdrs.forEach(function(h, i) {{
            if (i >= icons.length || !icons[i]) return;
            if (h.querySelector('.mmm-nav-icon')) return;
            var img = parent.document.createElement('img');
            img.src = icons[i];
            img.className = 'mmm-nav-icon';
            img.style.cssText = 'width:18px;height:18px;object-fit:contain;opacity:0.8;'
                + 'margin-right:7px;flex-shrink:0;filter:brightness(0) invert(1);';
            h.insertBefore(img, h.firstChild);
        }});
    }}

    setTimeout(_inject, 600);
    var _obs = new MutationObserver(_inject);
    _obs.observe(parent.document.body, {{childList: true, subtree: true}});
}})();
</script>
""", height=0, scrolling=False)

pg.run()
