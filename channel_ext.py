# -*- coding: utf-8 -*-
"""汎用チャネル定義。
既存エンジンの CHANNEL_KEYWORDS（秤社特化24ch）を国内主要チャネルで拡張する。
"""
from mmm_engine.src.data_loader import CHANNEL_KEYWORDS as _BASE

# _BASE に存在しないチャネルのみを追加（_BASE はすでに engine 側で Title_Case 変換済み）
_EXTENDED = {
    'Criteo':   ['criteo', 'クリテオ'],
    'Naver':    ['naver', 'naver_blog'],
}

# ベース（秤社特化）+ 汎用拡張を結合（_BASE はすでに Title_Case）
CHANNEL_KEYWORDS_EXT: dict = {**_BASE, **_EXTENDED}

# UIのドロップダウン用: チャネル名リスト（「未マッピング」を先頭に追加）
CHANNEL_OPTIONS: list[str] = ['（未マッピング）'] + list(CHANNEL_KEYWORDS_EXT.keys())
