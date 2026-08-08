# -*- coding: utf-8 -*-
"""汎用チャネル定義。
既存エンジンの CHANNEL_KEYWORDS（秤社特化24ch）を国内主要チャネルで拡張する。
"""
from mmm_engine.src.data_loader import CHANNEL_KEYWORDS as _BASE

# 国内主要チャネルを追加（既存キーと重複しない名前を使用）
_EXTENDED = {
    # Google
    'Google_Search':  ['google', 'gg', 'gads', 'search', '検索'],
    'Google_Display': ['gdn', 'display', 'ディスプレイ', 'gg_display'],
    'YouTube':        ['youtube', 'yt', 'you_tube'],
    # SNS
    'Instagram':      ['instagram', 'ig', 'insta', 'インスタ'],
    'LINE':           ['line', 'line_ads', 'line広告'],
    'TikTok':         ['tiktok', 'tt', 'tik_tok'],
    'Pinterest':      ['pinterest', 'ピンタレスト'],
    # アドネットワーク
    'Criteo':         ['criteo', 'クリテオ'],
    'SmartNews':      ['smartnews', 'sn', 'smart_news'],
    'Amazon_DSP':     ['amazon', 'amz', 'dsp'],
    # その他
    # 注: 建設専門メディア(K_BUKKA/K_PLAZA/KEICHO/BSIJ/SALES_AD)は
    # mmm_engine/src/data_loader.py の CHANNEL_KEYWORDS に追加済みのため
    # ここでは定義しない（重複回避）
    'Naver':          ['naver', 'naver_blog'],
    'GDN':            ['gdn_ext'],  # Google Display Network 別表記
}

# ベース（秤社特化）+ 汎用拡張を結合
CHANNEL_KEYWORDS_EXT: dict = {**_BASE, **_EXTENDED}

# UIのドロップダウン用: チャネル名リスト（「未マッピング」を先頭に追加）
CHANNEL_OPTIONS: list[str] = ['（未マッピング）'] + list(CHANNEL_KEYWORDS_EXT.keys())
