"""SMB向けダミーデータ生成スクリプト
総予算 約4,000万円 / 3年 / 7チャネル / CPA差別化版

設計方針:
- ジェネレーター内でadstockを掛けない（MMMが内部で推定するため二重適用を避ける）
- スペンドは「バースト週=高 / オフ週=低」のステップ関数で明確な変動を作る
- チャネルごとにバースト時期を完全に分離して相関を下げる
- ROIをチャネル間で3〜20倍の差をつけてCPAを差別化する
"""
import numpy as np
import pandas as pd

np.random.seed(42)

# ── 期間設定（3年・週次）────────────────────────────────────
dates = pd.date_range('2022-01-03', periods=156, freq='W-MON')
n = len(dates)

# 週番号（1〜52循環）
woy = pd.Series(dates).dt.isocalendar().week.astype(int).values % 52  # 0〜51

# ── チャネル別スペンドパターン ───────────────────────────────
# burst_weeks: 1年52週のうちバースト期（0-indexed）
# base_weekly: 3年平均週次予算（目安）
# burst_mult: バースト週の倍率（vs オフ週）

TARGET = 40_000_000   # 総予算4,000万

def step_spend(burst_weeks_set, share, burst_mult, noise_pct=0.08):
    """バースト週 / オフ週のステップ関数スペンド（小さいノイズ付き）"""
    off_weeks  = 52 - len(burst_weeks_set)
    # burst週の週数 * mult + off週の週数 * 1 = share合計
    unit = (TARGET * share) / (len(burst_weeks_set) * burst_mult + off_weeks * 1.0)
    off_base  = unit
    high_base = unit * burst_mult

    weeks_per_year = np.array([burst_mult if w in burst_weeks_set else 1.0 for w in range(52)])

    spend = np.zeros(n)
    for i in range(n):
        base = high_base if woy[i] in burst_weeks_set else off_base
        spend[i] = max(0, base * (1 + np.random.normal(0, noise_pct)))
    return spend

# ── 7チャネル：バースト時期を完全に分離 ───────────────────
#   チャネル        バースト期           配分    倍率   想定CPA(万)
# META           Q4年末(40-50週)      22%     3.5x   ~¥1.3万
# GOOGLE_SEARCH  春・秋(12-16, 38-42) 26%     2.5x   ~¥0.9万（最効率）
# LINE           夏(26-31週)          12%     3.0x   ~¥2.5万
# SEO            通年フラット          8%      1.0x   ~¥3.8万
# YAHOO          GW(17-21週)          13%     4.0x   ~¥1.5万
# YOUTUBE        年始・夏(1-4, 27-30) 13%     2.5x   ~¥3.0万
# CAMPAIGN       単発集中(8-10,35-37) 6%      8.0x   ~¥0.8万（高効率・単発）

meta_s     = step_spend({40,41,42,43,44,45,46,47,48,49,50}, share=0.22, burst_mult=3.5)
google_s   = step_spend({12,13,14,15,16, 38,39,40,41,42},   share=0.26, burst_mult=2.5)
line_s     = step_spend({26,27,28,29,30,31},                 share=0.12, burst_mult=3.0)
seo_s      = step_spend(set(),                               share=0.08, burst_mult=1.0, noise_pct=0.05)
yahoo_s    = step_spend({17,18,19,20,21},                    share=0.13, burst_mult=4.0)
youtube_s  = step_spend({1,2,3,4, 27,28,29,30},              share=0.13, burst_mult=2.5)
campaign_s = step_spend({8,9,10, 35,36,37},                  share=0.06, burst_mult=8.0)

# ── 合計を4,000万に正規化 ─────────────────────────────────
all_spends = [meta_s, google_s, line_s, seo_s, yahoo_s, youtube_s, campaign_s]
total_raw  = sum(s.sum() for s in all_spends)
scale = TARGET / total_raw
meta_s, google_s, line_s, seo_s = [s * scale for s in [meta_s, google_s, line_s, seo_s]]
yahoo_s, youtube_s, campaign_s  = [s * scale for s in [yahoo_s, youtube_s, campaign_s]]

# ── CV生成（adstockなし・純ROI線形） ─────────────────────
# 注: MMMが内部でadstock/Hill変換を推定するため、ジェネレーターではシンプルな線形ROIを使う
baseline_cv = 3.5   # 週次ベースラインCV

# 全体CV用の季節性（メディアとは独立させる）
season_cv = 1.0 + 0.25 * np.sin(2 * np.pi * (woy - 10) / 52)
trend_cv  = np.linspace(1.0, 1.20, n)

# チャネル別ROI（spend 1円あたりのCV寄与） → CPA = 1/roi
roi_meta     = 7.7e-5   # CPA ~¥1.3万
roi_google   = 11.5e-5  # CPA ~¥0.9万（最効率）
roi_line     = 4.0e-5   # CPA ~¥2.5万
roi_seo      = 2.6e-5   # CPA ~¥3.8万
roi_yahoo    = 6.5e-5   # CPA ~¥1.5万
roi_youtube  = 3.3e-5   # CPA ~¥3.0万
roi_campaign = 12.5e-5  # CPA ~¥0.8万（高効率・集中型）

media_cv = (roi_meta     * meta_s
          + roi_google   * google_s
          + roi_line     * line_s
          + roi_seo      * seo_s
          + roi_yahoo    * yahoo_s
          + roi_youtube  * youtube_s
          + roi_campaign * campaign_s)

cv_true = baseline_cv * season_cv * trend_cv + media_cv
noise   = np.random.normal(0, cv_true * 0.08)  # 8%ノイズ
cv      = np.maximum(1, np.round(cv_true + noise)).astype(int)

# ── 確認出力 ─────────────────────────────────────────────────
total_spend = sum(s.sum() for s in [meta_s, google_s, line_s, seo_s, yahoo_s, youtube_s, campaign_s])
total_cv    = cv.sum()
print(f"期間      : {dates[0].date()} ~ {dates[-1].date()} ({n}週)")
print(f"総予算    : {total_spend/1e4:,.0f}万円")
for name, s in [('META', meta_s), ('GOOGLE_SEARCH', google_s), ('LINE', line_s), ('SEO', seo_s),
                ('YAHOO', yahoo_s), ('YOUTUBE', youtube_s), ('CAMPAIGN', campaign_s)]:
    print(f"  {name:<15}: {s.sum()/1e4:,.0f}万 ({s.sum()/total_spend*100:.1f}%)")
print(f"CV合計    : {total_cv:,}件")
print(f"平均CPA   : {total_spend/total_cv:,.0f}円")
print(f"週平均CV  : {total_cv/n:.1f}件/週")

# 理論チャネル別CPA確認
print("\n理論チャネル別CPA:")
for name, s, roi in [
    ('META',          meta_s,     roi_meta),
    ('GOOGLE_SEARCH', google_s,   roi_google),
    ('LINE',          line_s,     roi_line),
    ('SEO',           seo_s,      roi_seo),
    ('YAHOO',         yahoo_s,    roi_yahoo),
    ('YOUTUBE',       youtube_s,  roi_youtube),
    ('CAMPAIGN',      campaign_s, roi_campaign),
]:
    theoretical_cv  = roi * s.sum()
    theoretical_cpa = s.sum() / theoretical_cv if theoretical_cv > 0 else float('inf')
    print(f"  {name:<15}: CPA {theoretical_cpa:,.0f}en (ROI*spend={theoretical_cv:.0f}cv)")

# ── DataFrame 組み立て・出力 ─────────────────────────────────
df = pd.DataFrame({
    'date'            : dates,
    'cv'              : cv,
    'META_s'          : meta_s.round(0).astype(int),
    'GOOGLE_SEARCH_s' : google_s.round(0).astype(int),
    'LINE_s'          : line_s.round(0).astype(int),
    'SEO_s'           : seo_s.round(0).astype(int),
    'YAHOO_s'         : yahoo_s.round(0).astype(int),
    'YOUTUBE_s'       : youtube_s.round(0).astype(int),
    'CAMPAIGN_s'      : campaign_s.round(0).astype(int),
})

out = 'data/dt_smb_weekly_dummy.xlsx'
df.to_excel(out, index=False)
print(f"\n保存完了: {out}")
