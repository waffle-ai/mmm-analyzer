# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, '.')
from src.data_loader import load_data
from src.model import pareto_search
import numpy as np

excel = r"G:\マイドライブ\00_ai_company\01_claude_code\04_own_business\sales-marketing\mmm\reference_file\hakari_data.xlsm"
data = load_data(excel, verbose=False)

cv_sqrt = np.sqrt(np.maximum(data['cv_uu'], 0))
n_train = len(cv_sqrt) - 14
y_train = cv_sqrt[:n_train]
y_hold  = cv_sqrt[n_train:]
media_train = {ch: v[:n_train] for ch, v in data['media'].items()}
media_hold  = {ch: v[n_train:] for ch, v in data['media'].items()}
costs_train = {ch: v[:n_train] for ch, v in data['costs'].items()}
controls_train = {k: v[:n_train] for k, v in data['controls'].items()}
controls_hold  = {k: v[n_train:] for k, v in data['controls'].items()}

N = 100

print(f"--- シングル（n_jobs=1）---")
t0 = time.time()
pareto_search(media_train, costs_train, controls_train, y_train, y_hold,
              media_hold=media_hold, controls_hold=controls_hold,
              n_trials=N, seed=42, n_jobs=1)
t1 = time.time() - t0
print(f"  {N}試行: {t1:.1f}秒")

print(f"--- 並列（n_jobs=-1）---")
t0 = time.time()
pareto_search(media_train, costs_train, controls_train, y_train, y_hold,
              media_hold=media_hold, controls_hold=controls_hold,
              n_trials=N, seed=42, n_jobs=-1)
t2 = time.time() - t0
print(f"  {N}試行: {t2:.1f}秒")
print(f"  速度向上: {t1/t2:.1f}x")
