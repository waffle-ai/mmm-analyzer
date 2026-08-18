# -*- coding: utf-8 -*-
"""SmartMMM — Streamlit エントリポイント。起動: streamlit run app.py"""
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

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
        border-color: #315E6D                       !important;
        box-shadow:   0 0 0 3px rgba(49,94,109,.10) !important;
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
        border-color: #315E6D                       !important;
        box-shadow:   0 0 0 3px rgba(49,94,109,.10) !important;
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
    background-color: #253B4A !important;
}
a[data-testid="stSidebarNavLink"]:hover * {
    color: #ffffff !important;
}

/* ─ 選択中 ─ */
a[data-testid="stSidebarNavLink"][aria-current="page"] {
    background-color: #253B4A !important;
    border-left:      3px solid #7EBEAB !important;
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
    font-weight:      600     !important;
    transition:       background-color .15s;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background-color: #2A5160 !important;
}

/* ═══════════════════════════════════════════════════
   カスタム「?」ツールチップ — 全ページ共通
═══════════════════════════════════════════════════ */
.lbl-q { display:inline-flex; align-items:center; gap:5px; }
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
    background-color: #DAEBE5 !important;
    color:            #315E6D !important;
    font-weight:      600     !important;
    font-size:        12px    !important;
    letter-spacing:   .04em   !important;
}

/* 各分析結果ページ — 見出し直下のリード文 */
.page-lede {
    color:          #314858 !important;
    font-size:      15px    !important;
    line-height:    1.7     !important;
    padding-bottom: 14px    !important;
    margin:         0       !important;
}

/* 無効化されたテキスト入力（マッピング確認：元の列名）— 視認性確保 */
div[data-baseweb="input"] input:disabled,
div[data-testid="stTextInputRootElement"] input:disabled {
    color:                 #314858 !important;
    -webkit-text-fill-color: #314858 !important;
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

</style>
""", unsafe_allow_html=True)

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
