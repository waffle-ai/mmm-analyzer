# -*- coding: utf-8 -*-
"""Pre-modeling channel data inspector.

Analyzes data structure before MMM fitting:
  - Detects data type (cost / count / binary / impression)
  - Flags sparsity, missing cost, all-zero channels
  - Identifies offline/non-digital channels from column name patterns
  - Generates clarifying questions for ambiguous channels
"""
import numpy as np
from typing import Dict, List, Tuple

# ── Offline / non-digital channel detection ─────────────────────────────────
# (name_fragments_lowercase, category_key, display_label, suggested_lambda_type)
# Checked in order; first match wins.
_OFFLINE_PATTERNS: List[Tuple] = [
    # テレビCM — 非常に長い残存効果
    (['tvcm', 'tv_', 'grp_', 'grp', 'テレビ', 'tvspot'],
     'tv',          'テレビCM',        'tv'),
    # ラジオ
    (['radio_', 'ラジオ'],
     'radio',       'ラジオ広告',      'awareness'),
    # 新聞・雑誌
    (['newspaper_', 'shimbun_', 'magazine_', '新聞', '雑誌'],
     'print',       '新聞・雑誌広告',  'awareness'),
    # OOH・交通広告
    (['ooh_', 'outdoor_', 'billboard_', 'transit_', 'train_ad_', 'kotsukokoku_', '屋外', '交通広告'],
     'ooh',         'OOH・交通広告',   'awareness'),
    # チラシ・折込・ポスティング・DM
    (['chirashi', 'flyer', 'flier', 'dm_', 'direct_mail', 'leaflet', 'pamphlet',
      'orikomi', '折込', 'posting_'],
     'offline_dm',  'チラシ・折込・DM', 'social'),
    # キャンペーン・プロモ
    (['campaign_', 'camp_', 'promo_', 'sale_'],
     'campaign',    'キャンペーン',    'campaign'),
    # PR・メディア掲載（アーンドメディア）
    (['pr_', 'press_', 'mention_', 'coverage_', 'article_', 'earned_', '掲載'],
     'pr',          'PR・メディア掲載', 'awareness'),
    # 展示会
    (['exhibition_', 'expo_', 'tradeshow_', 'trade_show_', '展示会'],
     'event',       '展示会',           'event'),
    # イベント・セミナー
    (['event_', 'seminar_', 'webinar_', 'イベント', 'セミナー', 'ウェビナー', 'offline_'],
     'event',       'イベント・セミナー', 'event'),
]

# GRP列名キーワード（テレビCM由来の特殊指標）
_GRP_KEYWORDS = ['grp', 'rating', 'reach_rate', 'reach_pct', 'viewing_rate']

_DATA_TYPE_LABELS = {
    'binary':           'バイナリ(0/1)',
    'flag_like':        'フラグ値',
    'count_int':        '整数カウント',
    'impression_large': 'IMP/大数値',
    'cost_like':        'コスト/浮動小数',
    'ratio_pct':        '比率(%)',
    'continuous':       '連続値',
    'all_zero':         '全ゼロ',
}


# ── Internal helpers ────────────────────────────────────────────────────────

def _detect_channel_category(ch_name: str) -> Tuple[str, str, str]:
    """Return (category, display_label, lambda_type) or ('digital', None, None)."""
    ch_lower = ch_name.lower()
    for patterns, cat, label, ltype in _OFFLINE_PATTERNS:
        for p in patterns:
            if p.lower() in ch_lower:
                return cat, label, ltype
    return 'digital', None, None


def _detect_data_type(arr: np.ndarray) -> str:
    """Classify the value distribution of a channel array."""
    if np.all(arr == 0):
        return 'all_zero'

    unique = np.unique(arr)
    nonzero = arr[arr > 0]

    # Strict binary: only 0 and 1
    if set(unique.tolist()).issubset({0.0, 1.0}):
        return 'binary'

    # Flag-like: very few distinct positive values, small magnitude
    if len(np.unique(nonzero)) <= 4 and float(nonzero.max()) <= 20:
        return 'flag_like'

    # Ratio / percentage: all values 0-100, mean < 70 (reach rate, viewing rate, etc.)
    if float(arr.max()) <= 100.0 and float(nonzero.mean()) < 70.0 and not np.all(arr == np.floor(arr)):
        return 'ratio_pct'

    # Integer check
    all_int = np.all(arr == np.floor(arr))
    if all_int:
        if float(nonzero.mean()) > 10_000:
            return 'impression_large'
        return 'count_int'

    # Large float → cost-like
    if float(nonzero.mean()) > 5_000:
        return 'cost_like'

    return 'continuous'


def _sparsity(arr: np.ndarray) -> float:
    return float((arr == 0).mean())


# ── Public API ───────────────────────────────────────────────────────────────

def inspect_channels(
    media: Dict[str, np.ndarray],
    costs: Dict[str, np.ndarray],
    freq: str = 'daily',
) -> Tuple[List[dict], List[str]]:
    """Inspect all channels before modeling.

    Parameters
    ----------
    media  : {ch_name: array} — the media metric used for modeling
    costs  : {ch_name: array} — raw cost / spend data
    freq   : 'daily' or 'weekly'

    Returns
    -------
    findings  : list of per-channel dicts
    questions : plain-text questions to ask the operator for ambiguous cases
    """
    findings: List[dict] = []
    questions: List[str] = []

    for ch in media:
        arr      = media[ch]
        cost_arr = costs.get(ch, np.zeros_like(arr))

        n_nonzero    = int((arr > 0).sum())
        sparsity     = _sparsity(arr)
        data_type    = _detect_data_type(arr)
        cost_total   = float(cost_arr.sum())
        cat, offline_label, offline_ltype = _detect_channel_category(ch)

        warnings:       List[str] = []
        recommendations: List[str] = []

        # ── [W1] Binary / flag data ──────────────────────────────────────
        if data_type in ('binary', 'flag_like'):
            warnings.append('バイナリ/フラグデータ')
            recommendations.append('Hill変換の効果なし → コントロール変数化を推奨')
            questions.append(
                f'[{ch}] 0/1のバイナリ（またはフラグ値）データです。'
                f'「実施有無」で表す施策（キャンペーン期間・展示会フラグなど）ですか？'
                f'\n       → 推奨: メディア列ではなくコントロール変数へ移動'
            )

        # ── [W2] Extremely sparse (< 10 active periods) ─────────────────
        elif n_nonzero > 0 and n_nonzero < 10:
            warnings.append(f'超疎データ（有効{n_nonzero}件のみ）')
            recommendations.append('ダミー変数化 or 除外を推奨')
            questions.append(
                f'[{ch}] 有効データが{n_nonzero}件しかありません（統計的推定が困難）。'
                f'\n       この施策は年数回のスポット施策（展示会・PR露出など）ですか？'
                f'\n       → 推奨: ダミー変数として手動追加 or 分析から除外'
            )

        # ── [W3] Moderately sparse ───────────────────────────────────────
        elif sparsity > 0.80 and data_type not in ('all_zero',):
            warnings.append(f'疎なデータ（{sparsity:.0%}がゼロ）')
            recommendations.append('Adstock推定が不安定になる可能性あり')

        # ── [W4] All zero ────────────────────────────────────────────────
        if data_type == 'all_zero':
            warnings.append('全期間ゼロ（未使用チャネル）')
            recommendations.append('分析から除外することを推奨')

        # ── [W5] Active channel with no cost data ────────────────────────
        # Binary/flag data is expected to have cost=0 — skip to avoid duplicate Q
        if (n_nonzero > 0 and data_type not in ('all_zero', 'binary', 'flag_like')
                and cost_total == 0):
            warnings.append('コストデータなし（アーンドメディア？）')
            recommendations.append('メンション数・リーチ数など量的指標の収集を検討')
            questions.append(
                f'[{ch}] チャネルは稼働しているが費用が0です。'
                f'PR記事・メディア掲載など費用が発生しないアーンドメディアですか？'
                f'\n       → 推奨: 量的指標（メンション数・リーチ）に置換 / コストがあれば補完'
            )

        # ── [W6] GRP / 視聴率データ（TV専用指標）────────────────────────
        ch_lower = ch.lower()
        _is_grp = any(kw in ch_lower for kw in _GRP_KEYWORDS)
        if _is_grp and data_type in ('count_int', 'continuous'):
            warnings.append('GRP/視聴率データの可能性')
            recommendations.append('GRPのままでもMMMに投入可能。リーチ換算も有効')
            questions.append(
                f'[{ch}] GRPまたは視聴率データと思われます。'
                f'\n       GRP（延べ視聴率ポイント）はそのまま投入可能ですが、'
                f'リーチ数（対象人口×GRP/100）への換算も検討してください。'
                f'\n       → 推奨: GRP合計のまま投入でも可。放送秒数合計との使い分けも有効'
            )

        # ── [W7] 比率データ（リーチ率・視聴率など）──────────────────────
        if data_type == 'ratio_pct':
            warnings.append('比率データ（%）を検出')
            recommendations.append('他チャネルとスケールが異なるためAdstockが不安定になる可能性あり')
            questions.append(
                f'[{ch}] 値が0〜100の比率データ（%）を検出しました。リーチ率・視聴率などですか？'
                f'\n       → 推奨: 実数値（リーチ人数 = 比率×母集団）への換算を検討。'
                f'そのまま投入する場合はスケールが他チャネルと乖離することに注意'
            )

        # ── [W8] Offline channel detected ───────────────────────────────
        if cat != 'digital' and offline_label:
            warnings.append(f'オフライン施策検知（{offline_label}）')

        findings.append({
            'channel':          ch,
            'data_type':        data_type,
            'n_nonzero':        n_nonzero,
            'sparsity':         sparsity,
            'cost_total':       cost_total,
            'category':         cat,
            'offline_label':    offline_label,
            'offline_ltype':    offline_ltype,
            'warnings':         warnings,
            'recommendations':  recommendations,
        })

    return findings, questions


def print_inspection_report(
    findings: List[dict],
    questions: List[str],
    freq: str = 'daily',
) -> str:
    """Render inspection findings as a printable console report."""
    lines = []
    lines.append('=' * 70)
    lines.append('  Step 1.5: データ構造事前分析')
    lines.append('=' * 70)
    lines.append(
        f'  {"チャネル":<22} {"データ種別":<18} {"疎密度":>7}  判定'
    )
    lines.append('-' * 70)

    has_issues = False
    for f in findings:
        ch    = f['channel'][:22]
        dtype = _DATA_TYPE_LABELS.get(f['data_type'], f['data_type'])[:18]
        sp    = f'{f["sparsity"]:.0%}ゼロ'
        warns = f['warnings']

        if not warns:
            status = '✓ 問題なし'
        else:
            has_issues = True
            primary = warns[0]
            if any(kw in primary for kw in ['超疎', 'バイナリ', 'フラグ', '全期間', 'コストデータ', 'GRP', '比率']):
                status = f'❗ {primary}'
            else:
                status = f'⚠ {primary}'

        lines.append(f'  {ch:<22} {dtype:<18} {sp:>7}  {status}')

    # Offline channel summary
    offline_chs = [f for f in findings if f['category'] != 'digital' and f['offline_label']]
    if offline_chs:
        lines.append('')
        lines.append('  ── オフライン施策チャネル（λタイプ自動分類済み）')
        for f in offline_chs:
            lines.append(
                f'     {f["channel"]:<22} → {f["offline_label"]}'
                f'（λ: {f["offline_ltype"] or "-"}）'
                f'{"  ⚠ " + f["warnings"][0] if f["warnings"] else ""}'
            )

    # Questions block
    if questions:
        lines.append('')
        lines.append('-' * 70)
        lines.append('  ⚠ 要確認事項（モデリング前にご確認ください）:')
        for i, q in enumerate(questions, 1):
            for j, line in enumerate(q.split('\n')):
                prefix = f'  [{i}]' if j == 0 else '      '
                lines.append(f'{prefix} {line}')
    elif not has_issues:
        lines.append('')
        lines.append('  ✓ データ構造に問題なし。モデリングに進みます。')

    lines.append('=' * 70)
    return '\n'.join(lines)
