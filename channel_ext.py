# -*- coding: utf-8 -*-
"""汎用チャネル定義。
エンジンの CHANNEL_KEYWORDS（全チャネル）を UI 用に分離管理する。

- CHANNEL_KEYWORDS_EXT : エンジン自動検出用（全チャネル）
- CHANNEL_OPTIONS      : UI ドロップダウン用（汎用チャネルのみ）
"""
from mmm_engine.src.data_loader import (
    CHANNEL_KEYWORDS as _BASE,
    GENERIC_CHANNEL_KEYWORDS as _GENERIC,
)

# エンジン自動検出用は全チャネルを維持（秤・CORDER 専用も含む）
_EXTENDED = {
    'Criteo': ['criteo', 'クリテオ'],
    'Naver':  ['naver', 'naver_blog'],
}

CHANNEL_KEYWORDS_EXT: dict = {**_BASE, **_EXTENDED}

# UIドロップダウン用: 汎用チャネル + 拡張チャネルのみ
# 秤クライアント専用（SEM_PC/MOBILE/TABLET, MOVIE_*, DEMAND_*, Pmax_*, X_XT/LP/MV/TDL/OTHER 系）
# および CORDER クライアント専用（K_PLAZA, BSIJ 等）は除外済み
CHANNEL_OPTIONS: list[str] = ['（未マッピング）'] + list({**_GENERIC, **_EXTENDED}.keys())
