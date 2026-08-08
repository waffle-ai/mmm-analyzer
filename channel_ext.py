# -*- coding: utf-8 -*-
"""汎用チャネル定義。
既存エンジンの CHANNEL_KEYWORDS（秤社特化24ch）を国内主要チャネルで拡張する。
"""
from mmm_engine.src.data_loader import CHANNEL_KEYWORDS as _BASE

# _BASE に存在しないチャネルのみを追加（重複するとMixed_Case/ALL_CAPSの混在が起きる）
_EXTENDED = {
    'Criteo':   ['criteo', 'クリテオ'],
    'Naver':    ['naver', 'naver_blog'],
}


def _to_title(name: str) -> str:
    """ALL_CAPSのチャネル名だけをTitle_Caseに変換。Mixed_Case / Camelはそのまま。

    例: GOOGLE_DEMAND → Google_Demand, META → Meta
        Pmax_PC → Pmax_PC（変換しない）, X_XT_en → X_XT_en（変換しない）
    """
    if name == name.upper():
        return '_'.join(s.capitalize() for s in name.split('_'))
    return name


# ベース（秤社特化）+ 汎用拡張を結合し、ALL_CAPSキーをTitle_Caseに統一
CHANNEL_KEYWORDS_EXT: dict = {
    _to_title(k): v
    for k, v in {**_BASE, **_EXTENDED}.items()
}

# UIのドロップダウン用: チャネル名リスト（「未マッピング」を先頭に追加）
CHANNEL_OPTIONS: list[str] = ['（未マッピング）'] + list(CHANNEL_KEYWORDS_EXT.keys())
