#!/usr/bin/env python3
"""
下游任务验证：勒索加密 vs 50步基准
严格对应论文 4.3.6 节
"""

import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.utils import resample
import glob
import os

print("=" * 60)
print("下游任务验证：勒索加密 vs 50步基准")
print("=" * 60)

DATA_DIR = "output/groundtruth"

OP_MAP = {
    'UI_CLICK': 0, 'UI_SWIPE': 1, 'UI_INPUT': 2,
    'FILE_CREATE': 3, 'FILE_DELETE': 4, 'FILE_COPY': 5,
    'APP_START': 6, 'APP_STOP': 7, 'NET_DOWNLOAD': 8
}

def extract_features(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    features = []
    for ev in data.get('evidence', []):
        dur = ev.get('duration_ms', 0)
        op = ev.get('op_type', 'UNKNOWN')
        ts = ev.get('timestamp', 0)
        op_code = OP_MAP.get(op, -1)
        features.append([dur, op_code, ts % 1000])
    return np.array(features)

# ========== 正样本：勒索加密 ==========
malicious_files = [
    "real_execution_20260818_165523.json",
    "real_execution_20260818_164449.json",
]
malicious_files += glob.glob(os.path.join(DATA_DIR, "real_execution_20260818_0918*.json"))
malicious_files = sorted(set(malicious_files))[:3]  # 取前3个勒索加密文件

# ========== 负样本：50步基准 ==========
baseline_files = sorted(glob.glob(os.path.join(DATA_DIR, "real_execution_20260818_113*.json")))

print(f"勒索加密文件: {len(malicious_files)} 个")
for f in malicious_files:
    print(f"  - {os.path.basename(f)}")
print(f"50步基准文件: {len(baseline_files)} 个")

X_mal, X_norm = [], []

for f in malicious_files:
    X = extract_features(f)
    if len(X) > 0:
        X_mal.append(X)

for f in baseline_files:
    X = extract_features(f)
    if len(X) > 0:
        X_norm.append(X)

if not X_mal or not X_norm:
    print("❌ 数据不足！")
    exit(1)

X_mal = np.vstack(X_mal)
X_norm = np.vstack(X_norm)
y_mal = np.ones(len(X_mal))
y_norm = np.zeros(len(X_norm))

print(f"\n原始数据:")
print(f"  勒索加密（恶意）: {len(X_mal)} 样本")
print(f"  50步基准（正常）: {len(X_norm)} 样本")

# ========== 下采样：使正负样本 1:1 ==========
n_samples = min(len(X_mal), len(X_norm))
X_mal_down, y_mal_down = resample(X_mal, y_mal, n_samples=n_samples, random_state=42)
X_norm_down, y_norm_down = resample(X_norm, y_norm, n_samples=n_samples, random_state=42)

X_balanced = np.vstack([X_mal_down, X_norm_down])
y_balanced = np.concatenate([y_mal_down, y_norm_down])

print(f"\n平衡后数据:")
print(f"  恶意: {n_samples} 样本")
print(f"  正常: {n_samples} 样本")
print(f"  总计: {len(X_balanced)} 样本")

# ========== 训练 ==========
X_train, X_test, y_train, y_test = train_test_split(
    X_balanced, y_balanced, test_size=0.2, random_state=42, stratify=y_balanced
)

clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
clf.fit(X_train, y_train)
y_pred = clf.predict(X_test)

# ========== 评估 ==========
acc = accuracy_score(y_test, y_pred)
prec = precision_score(y_test, y_pred)
rec = recall_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)
cm = confusion_matrix(y_test, y_pred)

cv_scores = cross_val_score(clf, X_balanced, y_balanced, cv=5)
print(f"各折准确率: {[f'{s:.2%}' for s in cv_scores]}")

print("\n" + "=" * 60)
print("模型评估结果 (8:2 划分):")
print("=" * 60)
print(f"准确率 (Accuracy):  {acc:.2%}")
print(f"精确率 (Precision): {prec:.2%}")
print(f"召回率 (Recall):    {rec:.2%}")
print(f"F1 分数:            {f1:.2f}")
print(f"\n混淆矩阵:")
print(f"  TN={cm[0][0]}, FP={cm[0][1]}")
print(f"  FN={cm[1][0]}, TP={cm[1][1]}")
print(f"\n5折交叉验证平均准确率: {cv_scores.mean():.2%} ± {cv_scores.std():.2%}")
