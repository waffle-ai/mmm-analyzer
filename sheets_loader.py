# -*- coding: utf-8 -*-
"""Google Sheets 公開URLからDataFrameを取得するユーティリティ。
公開設定（リンクを知っている全員が閲覧可）のシートのみ対応。
認証不要 — CSV export URL を使って pandas で直接読み込む。
"""
import re
import tempfile
from urllib.parse import parse_qs, urlparse

import pandas as pd


def parse_sheets_url(url: str) -> tuple[str, str]:
    """Google Sheets URLから (spreadsheet_id, gid) を返す。"""
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
    if not m:
        raise ValueError(
            'Google SheetsのURLとして認識できませんでした。\n'
            'URLは https://docs.google.com/spreadsheets/d/... の形式で入力してください。'
        )
    spreadsheet_id = m.group(1)

    gid = '0'
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if 'gid' in qs:
        gid = qs['gid'][0]
    else:
        frag_qs = parse_qs(parsed.fragment)
        if 'gid' in frag_qs:
            gid = frag_qs['gid'][0]

    return spreadsheet_id, gid


def sheets_to_excel_tmp(url: str) -> str:
    """公開スプシURLをCSVで取得し、一時xlsxとして保存してパスを返す。

    Raises
    ------
    ValueError
        URLが無効 or シートが非公開の場合
    """
    spreadsheet_id, gid = parse_sheets_url(url)
    csv_url = (
        f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}'
        f'/export?format=csv&gid={gid}'
    )

    try:
        df = pd.read_csv(csv_url)
    except Exception as e:
        raise ValueError(
            'シートの読み込みに失敗しました。\n'
            'シートが「リンクを知っている全員が閲覧可」に設定されているか確認してください。\n'
            f'詳細: {e}'
        ) from e

    if df.empty:
        raise ValueError('シートにデータが見つかりませんでした。タブを確認してください。')

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    df.to_excel(tmp.name, index=False)
    return tmp.name
