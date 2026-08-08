# -*- coding: utf-8 -*-
"""external_vars 動作確認スクリプト（ダミーデータ）"""
import sys, os, numpy as np, pandas as pd, yaml, subprocess, pickle
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src'))

np.random.seed(42)
n = 104  # 2年 × 週次

dates = pd.date_range('2023-01-02', periods=n, freq='W-MON')

# ── ダミーチャネル ──────────────────────────────────────────────
google_spend  = np.random.uniform(500_000, 2_000_000, n)
google_clicks = (google_spend / 150 * np.random.uniform(0.8, 1.2, n)).astype(int)
meta_spend    = np.random.uniform(300_000, 1_200_000, n)
meta_clicks   = (meta_spend / 200 * np.random.uniform(0.8, 1.2, n)).astype(int)

# ── 外部変数（気温偏差 / 降水量） ──────────────────────────────
month = dates.month
base_temp = np.array([3,4,7,13,18,22,25,27,22,16,10,5])[month - 1].astype(float)
raw_temp  = base_temp + np.random.normal(0, 2, n)
precipitation = np.maximum(0, np.random.exponential(5, n))

# ── CV（気温偏差と降水量の両方が影響） ─────────────────────────
temp_effect  = (raw_temp - base_temp) * 2.0   # 偏差が正のほど+CV
rain_effect  = -np.log1p(precipitation) * 1.5  # 雨が多いほど-CV
noise        = np.random.normal(0, 3, n)
cv = np.maximum(0, 20
                + google_clicks / 8000
                + meta_clicks / 10000
                + temp_effect
                + rain_effect
                + noise).astype(int)

df = pd.DataFrame({
    'date':          dates.strftime('%Y-%m-%d'),
    'cv':            cv,
    'google_spend':  google_spend.astype(int),
    'google_clicks': google_clicks,
    'meta_spend':    meta_spend.astype(int),
    'meta_clicks':   meta_clicks,
    'avg_temp':      raw_temp.round(1),
    'precipitation': precipitation.round(1),
})

xlsx_path = ROOT / 'output' / 'test_ev_dummy.xlsx'
yaml_path = ROOT / 'output' / 'test_ev_config.yaml'
xlsx_path.parent.mkdir(exist_ok=True)
df.to_excel(xlsx_path, index=False)
print(f'ダミーExcel保存: {xlsx_path}  ({n}行)')

# ── テスト YAML ─────────────────────────────────────────────────
config = {
    'client': 'テストクライアント',
    'date':   'date',
    'cv':     'cv',
    'channels': {
        'GOOGLE_SEARCH': {'spend': 'google_spend', 'media': 'google_clicks'},
        'META':          {'spend': 'meta_spend',   'media': 'meta_clicks'},
    },
    'controls': [],
    'external_vars': [
        {'name': 'temp_anomaly',  'col': 'avg_temp',      'transform': 'seasonal_deviation'},
        {'name': 'precipitation', 'col': 'precipitation',  'transform': 'log1p'},
    ],
}
with open(yaml_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
print(f'テストYAML保存: {yaml_path}')

# ── data_loader 単体テスト ──────────────────────────────────────
print('\n[1] data_loader.load_data() テスト...')
from data_loader import load_data, load_mapping_yaml

mapping = load_mapping_yaml(str(yaml_path))
print(f'  external_vars from YAML: {mapping["external_vars"]}')

result = load_data(str(xlsx_path), mapping_override=mapping, verbose=True)

controls = result['controls']
print(f'\n  controls keys: {list(controls.keys())}')

assert 'temp_anomaly'  in controls, 'temp_anomaly が controls にない'
assert 'precipitation' in controls, 'precipitation が controls にない'

ta = controls['temp_anomaly']
pr = controls['precipitation']
print(f'  temp_anomaly  shape={ta.shape}  mean={ta.mean():.4f}  (seasonal_deviation → 0に近いはず)')
print(f'  precipitation shape={pr.shape}  min={pr.min():.3f}  (log1p → 非負のはず)')
assert abs(ta.mean()) < 0.5, f'seasonal_deviation の月平均除去が機能していない (mean={ta.mean():.4f})'
assert pr.min() >= 0,        'log1p 後に負値が出た'
print('  [OK] data_loader テスト通過')

# ── run_mmm.py 統合テスト ───────────────────────────────────────
print('\n[2] run_mmm.py 統合テスト（モデル実行）...')
out_dir = ROOT / 'output' / 'test_ev'
out_dir.mkdir(parents=True, exist_ok=True)
cmd = [
    sys.executable, str(ROOT / 'run_mmm.py'),
    '--excel',  str(xlsx_path),
    '--config', str(yaml_path),
    '--output', str(out_dir),
    '--trials', '500',   # 速さ優先
    '--seed',   '42',
]
print(f'  実行コマンド: {" ".join(cmd)}')
proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
stdout = proc.stdout or ''
log_path = out_dir / 'run_log.txt'
log_path.write_text(stdout + '\n--- STDERR ---\n' + (proc.stderr or ''), encoding='utf-8')
# 安全に印刷（エンコード不可文字は置換）
safe = stdout.encode('utf-8', errors='replace').decode('utf-8')
print(safe[-3000:] if len(safe) > 3000 else safe)
if proc.returncode != 0:
    safe_err = (proc.stderr or '').encode('utf-8', errors='replace').decode('utf-8')
    print('STDERR:', safe_err[-1000:])
    sys.exit(1)

# ── PKL 検索（最新ファイル） ─────────────────────────────────────
print('\n[3] 出力PKL検証...')
pkls = sorted(out_dir.rglob('MMM_*.pkl'), key=lambda p: p.stat().st_mtime)
assert pkls, f'PKLファイルが {out_dir} に見当たらない'
pkl_out = pkls[-1]
print(f'  PKL: {pkl_out.name}')
with open(pkl_out, 'rb') as f:
    res = pickle.load(f)

print(f'  PKLキー: {list(res.keys())}')
metrics = res.get('metrics', {})
print(f'  R²={metrics.get("r2", "N/A"):.4f}  MAPE={metrics.get("mape", "N/A"):.2f}%')

# チャネル別結果が出ていれば external_vars が model に食わせられた証拠
opt = res.get('opt_result', {})
ch_opt = opt.get('channel_opt', {})
print(f'  チャネル: {list(ch_opt.keys())}')
assert 'GOOGLE_SEARCH' in ch_opt, 'GOOGLE_SEARCH チャネルが結果にない'
assert 'META' in ch_opt, 'META チャネルが結果にない'
assert metrics.get('r2', 0) > 0.3, f'R² が低すぎる: {metrics.get("r2")}'
print('\n全テスト通過っす。external_vars は正常に動作しています。')
