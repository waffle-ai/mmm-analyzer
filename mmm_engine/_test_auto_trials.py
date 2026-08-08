# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from src.data_loader import load_data
from run_mmm import _auto_trials

excel = r"G:\マイドライブ\00_ai_company\01_claude_code\04_own_business\sales-marketing\mmm\reference_file\hakari_data.xlsm"
data = load_data(excel, verbose=False)
media = data['media']

n_trials, n_eff = _auto_trials(media, max_trials=2000)
print(f"チャネル数       : {len(media)}")
print(f"有効チャネル数   : {n_eff}  (相関0.85以上をグループ化)")
print(f"自動設定試行数   : {n_trials}")
