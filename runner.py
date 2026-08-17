# -*- coding: utf-8 -*-
"""MMMエンジン実行ラッパー。

subprocessでrun_mmm.pyを起動し、stdoutをログファイルに書き出す。
StreamlitはログファイルをポーリングしてUIに表示する。

なぜsubprocess方式か:
- Streamlitはシングルスレッドでスレッドセーフでない
- run_mmm.pyはすでに [HH:MM:SS] Step X... 形式でログを出している
- 既存エンジンのコードを一切変更せずに使える
"""
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import yaml

ENGINE_SCRIPT = Path(__file__).parent / 'mmm_engine' / 'run_mmm.py'
OUTPUT_BASE   = Path(__file__).parent / 'output'


def start_analysis(
    excel_path: str,
    client_name: str,
    mapping_override: dict | None = None,
    n_trials: int = 2000,
    report_type: str = 'full',
    budget_increase: float = 0.30,
) -> dict:
    """分析ジョブを起動してjob情報を返す。

    Parameters
    ----------
    excel_path       : アップロードされたExcelの一時パス
    client_name      : クライアント名（PPTXタイトルに使う）
    mapping_override : UIで修正済みのチャネルマッピング（Noneなら自動）
    n_trials         : パレート探索試行数（テスト時は50）
    report_type      : 'full' or 'simple'
    budget_increase  : シナリオB増額率（デフォルト30%）

    Returns
    -------
    dict: job_id, log_path, output_dir, config_path
    """
    job_id     = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = OUTPUT_BASE / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / 'run.log'

    # mapping_overrideをエンジンが読めるYAMLコンフィグに変換して --config で渡す
    config_path = None
    if mapping_override is not None:
        ch_map = mapping_override.get('channel_map', {})
        channels_out = {
            ch: {
                'spend': m.get('cost') or None,
                'media': m.get('media') or None,
            }
            for ch, m in ch_map.items()
        }
        config_doc = {
            'client':   client_name,
            'date':     mapping_override.get('date_col'),
            'cv':       mapping_override.get('cv_col'),
            'channels': channels_out,
            'controls': list(mapping_override.get('control_cols', [])),
        }
        config_path = output_dir / 'config.yaml'
        config_path.write_text(
            yaml.dump(config_doc, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding='utf-8',
        )

    cmd = [
        sys.executable,
        str(ENGINE_SCRIPT),
        '--excel',   excel_path,
        '--client',  client_name,
        '--output',  str(output_dir),
        '--trials',  str(n_trials),
        '--report-type', report_type,
        '--budget-increase', str(budget_increase),
    ]
    if config_path is not None:
        cmd += ['--config', str(config_path)]

    log_file = open(log_path, 'w', encoding='utf-8', buffering=1)
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    return {
        'job_id':      job_id,
        'pid':         proc.pid,
        'log_path':    str(log_path),
        'output_dir':  str(output_dir),
        'config_path': str(config_path) if config_path else None,
        '_proc':       proc,
        '_log_file':   log_file,
    }


def get_job_status(job_info: dict) -> dict:
    """ジョブの状態とログ末尾を返す。

    Returns
    -------
    dict: status ('running'|'completed'|'failed'), log_tail, pptx_path, json_path
    """
    output_dir = Path(job_info['output_dir'])
    log_path   = Path(job_info['log_path'])
    proc: subprocess.Popen = job_info.get('_proc')

    # ログ末尾100行を読む
    log_tail = ''
    if log_path.exists():
        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        log_tail = '\n'.join(lines[-100:])

    # PPTXとJSONの存在確認（エンジンはoutput_dir/CLIENT_SLUG/report/に出力するため再帰glob）
    pptx_files = list(output_dir.glob('**/*.pptx'))
    json_files = list(output_dir.glob('**/*_summary.json'))

    if pptx_files and json_files:
        return {
            'status':    'completed',
            'log_tail':  log_tail,
            'pptx_path': str(pptx_files[0]),
            'json_path': str(json_files[0]),
        }

    # プロセスが終了しているがPPTXがない → 失敗
    if proc is not None and proc.poll() is not None and proc.returncode != 0:
        return {
            'status':   'failed',
            'log_tail': log_tail,
            'pptx_path': None,
            'json_path': None,
        }

    return {
        'status':   'running',
        'log_tail': log_tail,
        'pptx_path': None,
        'json_path': None,
    }


def load_summary(json_path: str) -> dict:
    """分析結果のJSONを読み込む。"""
    return json.loads(Path(json_path).read_text(encoding='utf-8'))


def dedup_channels(channels: dict) -> tuple[dict, list[str]]:
    """表示直前のチャネル重複防御。

    入力段階のマッピング重複は解消済みだが、旧ジョブのJSONを開いた場合など
    大文字小文字・アンダースコア違いだけの同一チャネルが残っているケースがある。
    数値が同一なら片方だけ残し、異なる場合は両方残して警告名を返す。

    Returns
    -------
    (deduped, warn_names): 表示用チャネル辞書と、数値不一致で両方残した重複グループの
    代表名リスト（st.warning表示用）。
    """
    groups: dict[str, list[str]] = {}
    for name in channels:
        key = name.lower().replace('_', '').replace(' ', '')
        groups.setdefault(key, []).append(name)

    deduped: dict = {}
    warn_names: list[str] = []
    for names in groups.values():
        if len(names) == 1:
            deduped[names[0]] = channels[names[0]]
            continue

        canonical = next((n for n in names if n != n.upper()), names[0])
        _NUMERIC_KEYS = ('roi', 'cpa', 'cv_contrib', 'spend_man', 'marginal_roi')
        first_vals = {k: channels[names[0]].get(k) for k in _NUMERIC_KEYS}
        same = all(channels[n].get(k) == first_vals[k] for n in names[1:] for k in _NUMERIC_KEYS)

        if same:
            deduped[canonical] = channels[canonical]
        else:
            for n in names:
                deduped[n] = channels[n]
            warn_names.append(canonical)

    return deduped, warn_names


def estimate_duration(n_trials: int, n_channels: int) -> str:
    """試行数とチャネル数から処理時間を大まかに見積もる。"""
    minutes = max(1, int(n_trials * n_channels / 8000))
    if minutes < 5:
        return f'約{minutes}〜{minutes+2}分'
    return f'約{minutes}〜{minutes+5}分'
